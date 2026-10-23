"""Group-buying business rules (5a: groups and commitments, 5b: lifecycle and confirmation).

Rules (decisions.md, 2026-10-23):
* A group is for ONE live wholesaler offer. Commitments are quantities in that offer's unit.
* Confirming generates ONE ordinary, already-confirmed order per active participant, in the same
  transaction (all or nothing). Every shop pays the same unit price; the delivery fee is split by
  base-unit quantity, largest remainder (costs.allocate_delivery_fee). The group's goods total is
  the SUM of the shops' rounded line totals, so shares and totals always reconcile exactly.
* Joining, changing and withdrawing are free while the group is open and before its deadline.
  Nothing is binding yet; the binding point is the wholesaler's confirmation (confirm_group).
* At the deadline an open group becomes `closed` (target met, quantities frozen) or `failed`.
  There is no scheduler: this happens lazily on the next read or write (settle_expired) and via
  the `close_expired_groups` command. The wholesaler then confirms the FULL committed quantity
  or declines. The confirmed price can never exceed the tier price for the committed total (which
  itself never exceeds the list price at creation) and the delivery fee can never exceed the
  group's published estimate, so nobody can be surprised upwards.
* Each commitment must meet the offer's minimum order (it becomes one ordinary order later)
  and the total may not exceed a stated available quantity.
* A shop has one commitment per group. Re-joining after a withdrawal reuses the same row.
* Every change locks the group row, then rewrites the cached totals from the active
  commitments, so concurrent joins can neither lose an update nor oversubscribe the offer.
* A person cannot take part in a group for a wholesaler they work for.
"""

from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Count, Q, Sum
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied

from apps.audit import services as audit
from apps.common.exceptions import DomainError, StateConflict
from apps.common.money import money
from apps.inventory.units import to_base
from apps.orders import services as order_services
from apps.shops.models import ShopMembership
from apps.suppliers import services as supplier_services
from apps.suppliers.models import SupplierOffer, WholesalerMembership
from apps.sync.idempotency import to_jsonable

from .costs import allocate_delivery_fee
from .models import GroupOrder, GroupParticipant

Status = GroupOrder.Status

MIN_DEADLINE_LEAD = timedelta(hours=1)
MAX_DEADLINE_LEAD = timedelta(days=30)


class GroupNotOpen(StateConflict):
    default_code = "group_not_open"
    default_detail = "This group is no longer open for changes."


class AlreadyJoined(StateConflict):
    default_code = "already_joined"
    default_detail = "Your shop has already joined this group. Change the commitment instead."


class NotParticipating(StateConflict):
    default_code = "not_participating"
    default_detail = "Your shop has no active commitment in this group."


class InvalidTransition(StateConflict):
    default_code = "invalid_transition"
    default_detail = "That is not possible in the group's current state."


# ------------------------------------------------------------------ queries
def visible_groups(shop):
    """Groups a shop may see: open ones it can still join, plus any it has taken part in."""
    now = timezone.now()
    live_offers = supplier_services.marketplace_offers().values("pk")
    return GroupOrder.objects.filter(
        Q(status=Status.OPEN, deadline__gt=now, offer__in=live_offers)
        | Q(participants__shop=shop)
    ).distinct()


# ------------------------------------------------------------------ helpers
def _record(action, group, actor, shop, changes=None):
    audit.record(
        action=action, obj_type="group_order", obj_id=group.pk, actor=actor, shop=shop,
        wholesaler=group.wholesaler, changes=changes or {},
    )  # fmt: skip


def _lock_group(group_id, shop) -> GroupOrder:
    """Lock the group for this shop. A group the shop cannot see is 'not found'."""
    try:
        group = (
            GroupOrder.objects.select_for_update(of=("self",))
            .select_related("offer", "wholesaler", "product_unit")
            .get(pk=group_id)
        )
    except GroupOrder.DoesNotExist:
        raise NotFound("Group not found.") from None
    takes_part = GroupParticipant.objects.filter(group=group, shop=shop).exists()
    open_to_all = group.status == Status.OPEN and group.deadline > timezone.now()
    if not (takes_part or open_to_all):
        raise NotFound("Group not found.")
    return group


def _require_open(group: GroupOrder) -> None:
    if group.status != Status.OPEN:
        raise GroupNotOpen(f"This group is {group.status}, so it cannot be changed.")
    if group.deadline <= timezone.now():
        raise GroupNotOpen("The deadline for this group has passed.")


def _forbid_own_wholesaler(group_or_wholesaler, user) -> None:
    wholesaler = getattr(group_or_wholesaler, "wholesaler", group_or_wholesaler)
    if WholesalerMembership.objects.filter(
        wholesaler=wholesaler, user=user, status=WholesalerMembership.Status.ACTIVE
    ).exists():
        raise DomainError(
            "You cannot join a group for a wholesaler you work for.", code="self_order"
        )


def _require_offer_live(group: GroupOrder) -> None:
    live = supplier_services.marketplace_offers().filter(pk=group.offer_id).exists()
    if not live or group.offer.availability == SupplierOffer.Availability.OUT_OF_STOCK:
        raise DomainError(
            "The wholesaler's offer for this group is no longer available.",
            code="offer_unavailable",
        )


def _check_quantity(group: GroupOrder, quantity: Decimal) -> Decimal:
    """Validate one shop's commitment; returns it in base units."""
    if quantity < group.minimum_per_shop:
        raise DomainError(
            f"The minimum per shop is {group.minimum_per_shop.normalize():f} "
            f"x {group.unit_name_snapshot}.",
            code="below_minimum",
        )
    return to_base(group.product_unit, quantity)  # also rejects over-precise quantities


def _others_committed(group: GroupOrder, shop) -> Decimal:
    total = (
        group.participants.filter(status=GroupParticipant.Status.ACTIVE)
        .exclude(shop=shop)
        .aggregate(total=Sum("quantity"))["total"]
    )
    return total or Decimal("0")


def _check_capacity(group: GroupOrder, total: Decimal) -> None:
    available = group.offer.available_quantity
    if available is not None and total > available:
        raise DomainError(
            f"Only {available.normalize():f} x {group.unit_name_snapshot} is available, "
            "so the group cannot take more.",
            code="exceeds_availability",
        )


def _recompute(group: GroupOrder) -> None:
    """Rewrite the cached totals from the active commitments (call with the row locked)."""
    agg = group.participants.filter(status=GroupParticipant.Status.ACTIVE).aggregate(
        qty=Sum("quantity"), base=Sum("quantity_base"), n=Count("id")
    )
    group.committed_quantity = agg["qty"] or Decimal("0")
    group.committed_quantity_base = agg["base"] or Decimal("0")
    group.participant_count = agg["n"]
    group.save(
        update_fields=[
            "committed_quantity", "committed_quantity_base", "participant_count", "updated_at",
        ]
    )  # fmt: skip


def reconcile(group: GroupOrder) -> dict:
    """What the caches SHOULD be, straight from the commitments. Used by tests and ops checks."""
    agg = group.participants.filter(status=GroupParticipant.Status.ACTIVE).aggregate(
        qty=Sum("quantity"), base=Sum("quantity_base"), n=Count("id")
    )
    return {
        "committed_quantity": agg["qty"] or Decimal("0"),
        "committed_quantity_base": agg["base"] or Decimal("0"),
        "participant_count": agg["n"],
    }


# ------------------------------------------------------------------ actions
@transaction.atomic
def create_group(
    *, shop, user, offer_id, target_quantity, quantity, deadline, delivery_method,
    delivery_point, estimated_delivery_fee=Decimal("0"), note="",
) -> GroupOrder:  # fmt: skip
    """Start a group on a live offer; the organising shop commits `quantity` straight away."""
    offer = (
        supplier_services.marketplace_offers()
        .select_related("product", "product_unit", "wholesaler")
        .filter(pk=offer_id)
        .first()
    )
    if offer is None:
        raise DomainError("That offer is not available.", code="offer_not_found")
    if offer.availability == SupplierOffer.Availability.OUT_OF_STOCK:
        raise DomainError("That offer is out of stock.", code="out_of_stock")
    _forbid_own_wholesaler(offer.wholesaler, user)

    now = timezone.now()
    if not (now + MIN_DEADLINE_LEAD <= deadline <= now + MAX_DEADLINE_LEAD):
        raise DomainError(
            "The deadline must be between 1 hour and 30 days from now.", code="invalid_deadline"
        )
    point = (delivery_point or "").strip()
    if not point:
        raise DomainError(
            "Give the delivery address or the collection point.", code="delivery_point_required"
        )
    if target_quantity < offer.minimum_order_quantity:
        raise DomainError(
            "The target cannot be below the offer's minimum order.", code="invalid_target"
        )
    to_base(offer.product_unit, target_quantity)  # precision check
    if offer.available_quantity is not None and target_quantity > offer.available_quantity:
        raise DomainError(
            "The target is more than the wholesaler has available.", code="exceeds_availability"
        )

    group = GroupOrder(
        organiser_shop=shop, created_by=user, wholesaler=offer.wholesaler, offer=offer,
        product=offer.product, product_unit=offer.product_unit,
        product_name_snapshot=offer.product.name, unit_name_snapshot=offer.product_unit.unit_name,
        unit_base_quantity_snapshot=offer.product_unit.base_quantity, currency=offer.currency,
        list_price_snapshot=offer.price_per_unit, minimum_per_shop=offer.minimum_order_quantity,
        target_quantity=target_quantity, deadline=deadline, delivery_method=delivery_method,
        delivery_point=point[:255], estimated_delivery_fee=money(estimated_delivery_fee),
        note=(note or "").strip()[:255],
    )  # fmt: skip
    base = _check_quantity(group, quantity)
    _check_capacity(group, quantity)
    group.save()
    GroupParticipant.objects.create(
        group=group, shop=shop, committed_by=user, quantity=quantity, quantity_base=base
    )
    _recompute(group)
    _record(
        "group.created", group, user, shop,
        {"after": {
            "offer_id": offer.pk, "target_quantity": target_quantity, "deadline": deadline,
            "delivery_method": delivery_method, "estimated_delivery_fee": group.estimated_delivery_fee,
            "organiser_quantity": quantity,
        }},
    )  # fmt: skip
    return group


@transaction.atomic
def join_group(*, shop, user, group_id, quantity) -> GroupOrder:
    group = _lock_group(group_id, shop)
    _require_open(group)
    _forbid_own_wholesaler(group, user)
    _require_offer_live(group)

    existing = GroupParticipant.objects.filter(group=group, shop=shop).first()
    if existing and existing.status == GroupParticipant.Status.ACTIVE:
        raise AlreadyJoined()
    base = _check_quantity(group, quantity)
    _check_capacity(group, _others_committed(group, shop) + quantity)

    if existing:
        existing.status = GroupParticipant.Status.ACTIVE
        existing.quantity, existing.quantity_base = quantity, base
        existing.committed_by, existing.joined_at, existing.withdrawn_at = (
            user, timezone.now(), None,
        )
        existing.save()
    else:
        GroupParticipant.objects.create(
            group=group, shop=shop, committed_by=user, quantity=quantity, quantity_base=base
        )
    _recompute(group)
    _record("group.joined", group, user, shop, {"after": {"quantity": quantity}})
    return group


@transaction.atomic
def change_commitment(*, shop, user, group_id, quantity) -> GroupOrder:
    group = _lock_group(group_id, shop)
    _require_open(group)
    _forbid_own_wholesaler(group, user)
    _require_offer_live(group)

    mine = GroupParticipant.objects.filter(
        group=group, shop=shop, status=GroupParticipant.Status.ACTIVE
    ).first()
    if mine is None:
        raise NotParticipating()
    base = _check_quantity(group, quantity)
    _check_capacity(group, _others_committed(group, shop) + quantity)

    before = mine.quantity
    mine.quantity, mine.quantity_base, mine.committed_by = quantity, base, user
    mine.save()
    _recompute(group)
    _record(
        "group.commitment_changed", group, user, shop,
        {"before": {"quantity": before}, "after": {"quantity": quantity}},
    )  # fmt: skip
    return group


@transaction.atomic
def withdraw(*, shop, user, group_id) -> GroupOrder:
    group = _lock_group(group_id, shop)
    _require_open(group)

    mine = GroupParticipant.objects.filter(
        group=group, shop=shop, status=GroupParticipant.Status.ACTIVE
    ).first()
    if mine is None:
        raise NotParticipating()
    before = mine.quantity
    mine.status, mine.withdrawn_at = GroupParticipant.Status.WITHDRAWN, timezone.now()
    mine.save()
    _recompute(group)
    _record("group.withdrawn", group, user, shop, {"before": {"quantity": before}})
    return group


@transaction.atomic
def cancel_group(*, shop, user, group_id, reason) -> GroupOrder:
    """Only the organising shop, and only while the group is open. Binds nobody, creates nothing."""
    reason = (reason or "").strip()
    if not reason:
        raise DomainError("A reason is required.", code="reason_required")
    group = _lock_group(group_id, shop)
    if group.organiser_shop_id != shop.pk:
        raise PermissionDenied("Only the organising shop can cancel this group.")
    if group.status != Status.OPEN:
        raise GroupNotOpen(f"This group is {group.status}, so it cannot be cancelled.")
    group.status, group.status_note, group.closed_at = (
        Status.CANCELLED, reason[:255], timezone.now(),
    )
    group.save(update_fields=["status", "status_note", "closed_at", "updated_at"])
    _record("group.cancelled", group, user, shop, {"reason": reason[:255]})
    return group


# ------------------------------------------------------------------ lifecycle (5b)
def _settle_locked(group: GroupOrder, now=None) -> bool:
    """Move an expired open group to closed (target met) or failed. Call with the row locked.
    Returns True if it changed anything. Idempotent: a settled group is left alone."""
    now = now or timezone.now()
    if group.status != Status.OPEN or group.deadline > now:
        return False
    reached = group.committed_quantity >= group.target_quantity
    group.status = Status.CLOSED if reached else Status.FAILED
    group.status_note = "" if reached else "The target was not reached by the deadline."
    group.closed_at = now
    group.save(update_fields=["status", "status_note", "closed_at", "updated_at"])
    _record(
        "group.closed" if reached else "group.failed", group, None, group.organiser_shop,
        {
            "reason": "deadline",
            "after": {
                "committed_quantity": group.committed_quantity,
                "target_quantity": group.target_quantity,
            },
        },
    )  # fmt: skip
    return True


def settle_expired(scope: Q | None = None) -> int:
    """Settle every open group past its deadline (optionally only those matching `scope`).

    Each group is settled in its own short transaction, so one problem cannot hold up the rest
    and two callers racing on the same group settle it exactly once. Returns how many changed.
    Call it OUTSIDE the transaction of a write that may fail: it must commit on its own.
    """
    now = timezone.now()
    due = GroupOrder.objects.filter(status=Status.OPEN, deadline__lte=now)
    if scope is not None:
        due = due.filter(scope)
    settled = 0
    for group_id in list(due.values_list("pk", flat=True)):
        with transaction.atomic():
            group = (
                GroupOrder.objects.select_for_update(of=("self",))
                .select_related("organiser_shop")
                .filter(pk=group_id, status=Status.OPEN, deadline__lte=now)
                .first()
            )
            if group is not None and _settle_locked(group, now):
                settled += 1
    return settled


def settle_for_shop(shop) -> int:
    return settle_expired(Q(participants__shop=shop))


def settle_for_wholesaler(wholesaler) -> int:
    return settle_expired(Q(wholesaler=wholesaler))


def _lock_for_wholesaler(group_id, wholesaler) -> GroupOrder:
    """Lock the group for its own wholesaler only; anyone else gets 'not found'."""
    try:
        return (
            GroupOrder.objects.select_for_update(of=("self",))
            .select_related("offer", "wholesaler", "organiser_shop")
            .get(pk=group_id, wholesaler=wholesaler)
        )
    except GroupOrder.DoesNotExist:
        raise NotFound("Group not found.") from None


def _forbid_member_of_participating_shop(group: GroupOrder, user) -> None:
    """Conflict of interest: the supplier cannot answer for a group their own shop is in."""
    if ShopMembership.objects.filter(
        user=user, status=ShopMembership.Status.ACTIVE,
        shop__group_commitments__group=group,
        shop__group_commitments__status=GroupParticipant.Status.ACTIVE,
    ).exists():  # fmt: skip
        raise PermissionDenied(
            "You belong to a participating shop, so you cannot act on this group as the supplier."
        )


def _need_reason(reason) -> str:
    reason = (reason or "").strip()
    if not reason:
        raise DomainError("A reason is required.", code="reason_required")
    return reason[:255]


@transaction.atomic
def close_group(*, shop, user, group_id) -> GroupOrder:
    """The organiser closes an open group early. Only once the target is met: otherwise the
    right move is to wait for more shops or to cancel. Freezes the quantities."""
    group = _lock_group(group_id, shop)
    if group.organiser_shop_id != shop.pk:
        raise PermissionDenied("Only the organising shop can close this group.")
    _require_open(group)
    if group.committed_quantity < group.target_quantity:
        raise DomainError(
            "The target has not been reached yet. Wait for more shops, or cancel the group.",
            code="target_not_reached",
        )
    group.status, group.closed_at = Status.CLOSED, timezone.now()
    group.save(update_fields=["status", "closed_at", "updated_at"])
    _record(
        "group.closed", group, user, shop,
        {
            "reason": "organiser",
            "after": {
                "committed_quantity": group.committed_quantity,
                "target_quantity": group.target_quantity,
            },
        },
    )  # fmt: skip
    return group


def _terms_cap(group: GroupOrder, now) -> tuple[Decimal, Decimal | None]:
    """(highest unit price the wholesaler may confirm, tier minimum applied).

    The tier for the TOTAL committed quantity applies, and never above the list price the
    shops saw when the group was created, even if the live offer has been raised since."""
    price, tier_min = supplier_services.price_for(group.offer, group.committed_quantity, now)
    return min(price, group.list_price_snapshot), tier_min


@transaction.atomic
def confirm_group(
    *, wholesaler, actor, group_id, unit_price=None, delivery_fee=Decimal("0")
) -> GroupOrder:
    """THE binding point. The wholesaler accepts the FULL committed quantity on frozen terms.

    `unit_price` defaults to the cap (tier price for the total) and may only go lower.
    `delivery_fee` may not exceed the group's published estimate.
    """
    group = _lock_for_wholesaler(group_id, wholesaler)
    _forbid_member_of_participating_shop(group, actor)
    _settle_locked(group)  # a group past its deadline may still be sitting open
    if group.status != Status.CLOSED:
        raise InvalidTransition(f"A group that is {group.status} cannot be confirmed.")
    supplier_services.require_can_trade(wholesaler)

    available = group.offer.available_quantity
    if available is not None and group.committed_quantity > available:
        raise DomainError(
            f"Only {available.normalize():f} x {group.unit_name_snapshot} is available, which is "
            "less than the group has committed. Decline the group instead.",
            code="exceeds_availability",
        )

    now = timezone.now()
    cap, tier_min = _terms_cap(group, now)
    price = cap if unit_price is None else money(unit_price)
    if price <= 0 or price > cap:
        raise DomainError(
            f"The unit price cannot be above {cap:.2f} {group.currency} "
            "(the tier price for the committed total).",
            code="price_above_cap",
        )
    fee = money(delivery_fee)
    if fee < 0 or fee > group.estimated_delivery_fee:
        raise DomainError(
            f"The delivery fee cannot be above the published estimate of "
            f"{group.estimated_delivery_fee:.2f} {group.currency}.",
            code="fee_above_cap",
        )

    # Frozen per-shop costs, then one ordinary order each. Any failure rolls the whole
    # confirmation back, so a group is never confirmed with only some of its orders.
    participants = list(
        group.participants.filter(status=GroupParticipant.Status.ACTIVE)
        .select_related("shop")
        .order_by("joined_at", "shop_id")
    )
    shares = allocate_delivery_fee(fee, [(p.pk, p.quantity_base) for p in participants])
    goods = Decimal("0")
    order_ids = []
    for p in participants:
        p.goods_total = money(p.quantity * price)
        p.delivery_share = shares[p.pk]
        goods += p.goods_total
        order = order_services.create_group_order(
            shop=p.shop, placed_by=p.committed_by, wholesaler=wholesaler, offer=group.offer,
            quantity=p.quantity, quantity_base=p.quantity_base, unit_price=price,
            line_total=p.goods_total, delivery_fee=p.delivery_share,
            delivery_method=group.delivery_method, delivery_point=group.delivery_point,
            confirmed_at=now, confirmed_by=actor, group_id=group.pk, product_name=group.product_name_snapshot,
            unit_name=group.unit_name_snapshot,
            unit_base_quantity=group.unit_base_quantity_snapshot,
            list_price=group.list_price_snapshot, currency=group.currency,
        )  # fmt: skip
        p.order = order
        p.save(update_fields=["goods_total", "delivery_share", "order", "updated_at"])
        order_ids.append(order.pk)

    group.status = Status.CONFIRMED
    group.confirmed_unit_price, group.confirmed_delivery_fee = price, fee
    group.confirmed_at, group.confirmed_by = now, actor
    group.terms_snapshot = to_jsonable(
        {
            "product_id": group.product_id, "product_name": group.product_name_snapshot,
            "unit_name": group.unit_name_snapshot,
            "unit_base_quantity": group.unit_base_quantity_snapshot,
            "currency": group.currency, "list_price": group.list_price_snapshot,
            "tier_minimum_quantity": tier_min, "unit_price": price,
            "quantity": group.committed_quantity, "quantity_base": group.committed_quantity_base,
            "participant_count": group.participant_count, "goods_total": goods,
            "delivery_fee": fee, "total": goods + fee,
            "delivery_method": group.delivery_method, "delivery_point": group.delivery_point,
            "confirmed_at": now,
        }
    )  # fmt: skip
    group.save(
        update_fields=[
            "status", "confirmed_unit_price", "confirmed_delivery_fee", "confirmed_at",
            "confirmed_by", "terms_snapshot", "updated_at",
        ]
    )  # fmt: skip
    _record(
        "group.confirmed", group, actor, group.organiser_shop,
        {"after": {
            "unit_price": price, "delivery_fee": fee, "quantity": group.committed_quantity,
            "goods_total": goods, "orders_created": len(order_ids), "order_ids": order_ids,
        }},
    )  # fmt: skip
    return group


@transaction.atomic
def decline_group(*, wholesaler, actor, group_id, reason) -> GroupOrder:
    """The wholesaler turns a closed group down. Final; creates no orders and binds nobody.
    Allowed even if the wholesaler is no longer in good standing: winding down is always OK."""
    reason = _need_reason(reason)
    group = _lock_for_wholesaler(group_id, wholesaler)
    _forbid_member_of_participating_shop(group, actor)
    _settle_locked(group)
    if group.status != Status.CLOSED:
        raise InvalidTransition(f"A group that is {group.status} cannot be declined.")
    group.status, group.status_note = Status.DECLINED, reason
    group.save(update_fields=["status", "status_note", "updated_at"])
    _record("group.declined", group, actor, group.organiser_shop, {"reason": reason})
    return group


# ------------------------------------------------------------------ costs (5c)
def _money_str(value) -> str:
    return f"{Decimal(str(value)):.2f}"


def _qty_str(value) -> str:
    return f"{Decimal(str(value)):.6f}"


def _row(p: GroupParticipant, unit_price: Decimal) -> dict:
    return {
        "order_id": p.order_id, "order_status": p.order.status,
        "quantity": _qty_str(p.quantity), "quantity_base": _qty_str(p.quantity_base),
        "unit_price": _money_str(unit_price), "goods_total": _money_str(p.goods_total),
        "delivery_share": _money_str(p.delivery_share),
        "total": _money_str(p.goods_total + p.delivery_share),
    }  # fmt: skip


def cost_breakdown(group: GroupOrder, *, shop=None) -> dict:
    """The frozen costs of a CONFIRMED group.

    A shop gets the group totals plus ONLY its own line (`mine`); it never learns what the
    other shops committed or pay. The wholesaler (shop=None) also gets one row per generated
    order: it already sees those shops through the orders it must fulfil.
    """
    if group.status != Status.CONFIRMED:
        raise StateConflict(
            "Costs are final only once the wholesaler confirms the group.", code="not_confirmed"
        )
    terms = group.terms_snapshot
    unit_price = Decimal(group.confirmed_unit_price)
    data = {
        "group_id": group.pk, "status": group.status, "currency": group.currency,
        "unit_price": _money_str(unit_price),
        "tier_minimum_quantity": (
            None if terms.get("tier_minimum_quantity") is None
            else _qty_str(terms["tier_minimum_quantity"])
        ),
        "quantity": _qty_str(terms["quantity"]), "quantity_base": _qty_str(terms["quantity_base"]),
        "participant_count": terms["participant_count"],
        "goods_total": _money_str(terms["goods_total"]),
        "delivery_fee": _money_str(terms["delivery_fee"]), "total": _money_str(terms["total"]),
        "delivery_method": group.delivery_method, "delivery_point": group.delivery_point,
        "confirmed_at": group.confirmed_at,
    }  # fmt: skip
    rows = (
        group.participants.filter(status=GroupParticipant.Status.ACTIVE, order__isnull=False)
        .select_related("order", "shop")
        .order_by("joined_at", "shop_id")
    )
    if shop is not None:
        mine = next((p for p in rows if p.shop_id == shop.pk), None)
        data["mine"] = _row(mine, unit_price) if mine else None
    else:
        data["orders"] = [{"shop": {"name": p.shop.name}, **_row(p, unit_price)} for p in rows]
    return data


def reconcile_costs(group: GroupOrder) -> dict:
    """Sums of the per-shop allocations and generated orders, to compare with the group's frozen
    totals. Used by tests and ops checks; every pair must be equal for a confirmed group."""
    rows = list(
        group.participants.filter(status=GroupParticipant.Status.ACTIVE).select_related("order")
    )
    return {
        "quantity": sum((p.quantity for p in rows), Decimal("0")),
        "quantity_base": sum((p.quantity_base for p in rows), Decimal("0")),
        "goods_total": sum((p.goods_total or 0 for p in rows), Decimal("0")),
        "delivery_fee": sum((p.delivery_share or 0 for p in rows), Decimal("0")),
        "order_subtotals": sum((p.order.subtotal for p in rows if p.order), Decimal("0")),
        "order_delivery_fees": sum((p.order.delivery_fee for p in rows if p.order), Decimal("0")),
        "order_totals": sum((p.order.total_amount for p in rows if p.order), Decimal("0")),
        "orders": sum(1 for p in rows if p.order),
    }


def close_expired_groups() -> int:
    """For cron: settle every open group past its deadline. See the management command."""
    return settle_expired()
