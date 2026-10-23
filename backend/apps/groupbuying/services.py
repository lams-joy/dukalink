"""Group-buying business rules (chunk 5a: groups and commitments).

Rules (decisions.md, 2026-10-23):
* A group is for ONE live wholesaler offer. Commitments are quantities in that offer's unit.
* Joining, changing and withdrawing are free while the group is open and before its deadline.
  Nothing is binding yet; the binding point is the wholesaler's confirmation (chunk 5b).
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
from apps.suppliers import services as supplier_services
from apps.suppliers.models import SupplierOffer, WholesalerMembership

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
