"""Ordinary-order business rules.

Rules worth knowing (see also models.Order):
* An order is for ONE wholesaler. Price, tier, unit and conversion are snapshotted per line at
  placement, so later offer edits never rewrite it.
* Only live offers from visible wholesalers can be ordered, at or above the minimum, and not
  beyond a stated available quantity. Placing does NOT reserve or decrement the supplier's
  availability: the supplier reconfirms it by confirming (or rejects).
* The supplier confirms the order as placed (adding an optional delivery fee) or rejects it.
  Nobody edits a confirmed order; changes go through cancellation.
* Cancelling is allowed until dispatch. After dispatch the only way to close an order is
  receipt, where shortages are recorded explicitly (never assumed away).
* Receipt writes an ordinary PurchaseReceipt into the shop's stock for what actually arrived.
* Conflict of interest: a person cannot order from a wholesaler they work for, nor act as
  supplier on an order placed by a shop they belong to.
"""

from decimal import Decimal

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied

from apps.accounts.phone import normalise_phone
from apps.audit import services as audit
from apps.common.exceptions import DomainError, StateConflict
from apps.common.money import money
from apps.inventory import services as inventory
from apps.inventory.models import ShopProduct
from apps.inventory.units import to_base
from apps.shops.models import ShopMembership
from apps.suppliers import services as supplier_services
from apps.suppliers.models import SupplierOffer, WholesalerMembership

from .models import Order, OrderItem

Status = Order.Status


class InvalidTransition(StateConflict):
    default_code = "invalid_transition"
    default_detail = "That is not possible in the order's current state."


class OverReceived(DomainError):
    default_code = "over_received"
    default_detail = "Cannot receive more than was ordered."


# ------------------------------------------------------------------ helpers
def _lock_order(order_id, **scope) -> Order:
    """Lock the order for this party only; anything else is 'not found' (no existence leak)."""
    try:
        return (
            Order.objects.select_for_update()
            .select_related("shop", "wholesaler")
            .get(pk=order_id, **scope)
        )
    except Order.DoesNotExist:
        raise NotFound("Order not found.") from None


def _require_status(order: Order, *allowed, doing: str) -> None:
    if order.status not in allowed:
        raise InvalidTransition(f"An order that is {order.status} cannot be {doing}.")


def _forbid_member_of_ordering_shop(order: Order, user) -> None:
    if ShopMembership.objects.filter(
        shop=order.shop, user=user, status=ShopMembership.Status.ACTIVE
    ).exists():
        raise PermissionDenied(
            "You belong to the ordering shop, so you cannot act on this order as the supplier."
        )


def _record(action, order, actor, changes=None):
    audit.record(
        action=action, obj_type="order", obj_id=order.pk, actor=actor, shop=order.shop,
        wholesaler=order.wholesaler, changes=changes or {},
    )  # fmt: skip


# ------------------------------------------------------------------ placing
@transaction.atomic
def place_order(
    *, shop, user, items, delivery_method=Order.DeliveryMethod.DELIVERY, delivery_address="",
    contact_phone="", note="",
) -> Order:  # fmt: skip
    """items: [{offer_id, quantity}] - all from the same wholesaler."""
    offer_ids = [i["offer_id"] for i in items]
    if len(offer_ids) != len(set(offer_ids)):
        raise DomainError(
            "List each offer once; combine quantities instead.", code="duplicate_item"
        )

    live = {
        o.pk: o
        for o in supplier_services.marketplace_offers()
        .filter(pk__in=offer_ids)
        .select_related("product", "product_unit", "wholesaler")
    }
    if set(offer_ids) - set(live):
        raise DomainError("One of those offers is not available.", code="offer_not_found")
    wholesalers = {o.wholesaler_id for o in live.values()}
    if len(wholesalers) != 1:
        raise DomainError(
            "An order can only include offers from one wholesaler.", code="mixed_wholesalers"
        )
    wholesaler = next(iter(live.values())).wholesaler
    if WholesalerMembership.objects.filter(
        wholesaler=wholesaler, user=user, status=WholesalerMembership.Status.ACTIVE
    ).exists():
        raise DomainError("You cannot order from a wholesaler you work for.", code="self_order")

    address = (delivery_address or "").strip() or shop.location_text
    if delivery_method == Order.DeliveryMethod.DELIVERY and not address:
        raise DomainError(
            "A delivery address is needed (or add a location to the shop).",
            code="delivery_address_required",
        )
    phone = ""
    if contact_phone:
        try:
            phone = normalise_phone(contact_phone)
        except DjangoValidationError:
            raise DomainError("Enter a valid phone number.", code="invalid_phone") from None

    lines, subtotal = [], Decimal("0")
    for entry in items:
        offer: SupplierOffer = live[entry["offer_id"]]
        quantity = entry["quantity"]
        _check_orderable(offer, quantity)
        unit_price = supplier_services.effective_unit_price(offer, quantity)
        line_total = money(quantity * unit_price)
        subtotal += line_total
        lines.append((offer, quantity, unit_price, line_total))

    order = Order.objects.create(
        shop=shop, wholesaler=wholesaler, currency=lines[0][0].currency, subtotal=subtotal,
        delivery_fee=Decimal("0"), total_amount=subtotal, delivery_method=delivery_method,
        delivery_address=address if delivery_method == Order.DeliveryMethod.DELIVERY else "",
        contact_phone=phone, note=(note or "").strip()[:255], placed_by=user,
    )  # fmt: skip
    OrderItem.objects.bulk_create(
        OrderItem(
            order=order, offer=offer, product=offer.product, product_unit=offer.product_unit,
            product_name_snapshot=offer.product.name,
            unit_name_snapshot=offer.product_unit.unit_name,
            unit_base_quantity_snapshot=offer.product_unit.base_quantity,
            quantity=quantity, quantity_base=to_base(offer.product_unit, quantity),
            list_price_snapshot=offer.price_per_unit, unit_price_snapshot=unit_price,
            line_total=line_total,
        )
        for offer, quantity, unit_price, line_total in lines
    )  # fmt: skip
    _record(
        "order.placed", order, user,
        {"after": {
            "subtotal": subtotal, "delivery_method": delivery_method,
            "items": [
                {"offer_id": o.pk, "quantity": q, "unit_price": p} for o, q, p, _ in lines
            ],
        }},
    )  # fmt: skip
    return order


def create_group_order(
    *, shop, placed_by, wholesaler, offer, quantity, quantity_base, unit_price, line_total,
    delivery_fee, delivery_method, delivery_point, confirmed_at, confirmed_by, group_id,
    product_name, unit_name, unit_base_quantity, list_price, currency,
) -> Order:  # fmt: skip
    """One shop's order generated when a wholesaler confirms a group. The terms were agreed at
    confirmation, so the order starts `confirmed` and continues as any other (dispatch, receive).
    Call inside the confirming transaction. `delivery_point` holds the address, or the
    collection point when the method is collection."""
    order = Order.objects.create(
        shop=shop, wholesaler=wholesaler, currency=currency, subtotal=line_total,
        delivery_fee=delivery_fee, total_amount=line_total + delivery_fee,
        status=Status.CONFIRMED, delivery_method=delivery_method,
        delivery_address=delivery_point, note=f"Group order {group_id}"[:255],
        placed_by=placed_by, submitted_at=confirmed_at, confirmed_at=confirmed_at,
    )  # fmt: skip
    OrderItem.objects.create(
        order=order, offer=offer, product=offer.product, product_unit=offer.product_unit,
        product_name_snapshot=product_name, unit_name_snapshot=unit_name,
        unit_base_quantity_snapshot=unit_base_quantity, quantity=quantity,
        quantity_base=quantity_base, list_price_snapshot=list_price,
        unit_price_snapshot=unit_price, line_total=line_total,
    )  # fmt: skip
    source = {"source": "group_order", "group_order_id": group_id}
    _record(
        "order.placed", order, placed_by,
        {**source, "after": {
            "subtotal": line_total, "delivery_method": delivery_method,
            "items": [{"offer_id": offer.pk, "quantity": quantity, "unit_price": unit_price}],
        }},
    )  # fmt: skip
    _record(
        "order.confirmed", order, confirmed_by,
        {**source, "after": {"delivery_fee": delivery_fee, "total_amount": order.total_amount}},
    )  # fmt: skip
    return order


def _check_orderable(offer: SupplierOffer, quantity: Decimal) -> None:
    if offer.availability == SupplierOffer.Availability.OUT_OF_STOCK:
        raise DomainError(
            f"'{offer.product.name}' is out of stock with this wholesaler.", code="out_of_stock"
        )
    if quantity < offer.minimum_order_quantity:
        raise DomainError(
            f"The minimum order for '{offer.product.name}' is {offer.minimum_order_quantity.normalize():f} "
            f"x {offer.product_unit.unit_name}.",
            code="below_minimum",
        )
    if offer.available_quantity is not None and quantity > offer.available_quantity:
        raise DomainError(
            f"Only {offer.available_quantity.normalize():f} x {offer.product_unit.unit_name} of "
            f"'{offer.product.name}' available.",
            code="exceeds_availability",
        )
    to_base(offer.product_unit, quantity)  # rejects over-precise quantities


# ------------------------------------------------------------------ supplier actions
@transaction.atomic
def confirm_order(*, wholesaler, actor, order_id, delivery_fee=Decimal("0")) -> Order:
    order = _lock_order(order_id, wholesaler=wholesaler)
    _forbid_member_of_ordering_shop(order, actor)
    _require_status(order, Status.SUBMITTED, doing="confirmed")
    supplier_services.require_can_trade(wholesaler)
    order.status = Status.CONFIRMED
    order.confirmed_at = timezone.now()
    order.delivery_fee = delivery_fee
    order.total_amount = order.subtotal + delivery_fee
    order.save(
        update_fields=["status", "confirmed_at", "delivery_fee", "total_amount", "updated_at"]
    )
    _record(
        "order.confirmed", order, actor,
        {"after": {"delivery_fee": delivery_fee, "total_amount": order.total_amount}},
    )  # fmt: skip
    return order


@transaction.atomic
def reject_order(*, wholesaler, actor, order_id, reason) -> Order:
    reason = _need_reason(reason)
    order = _lock_order(order_id, wholesaler=wholesaler)
    _forbid_member_of_ordering_shop(order, actor)
    _require_status(order, Status.SUBMITTED, doing="rejected")
    _close(order, Status.REJECTED, reason, cancelled_by="")
    _record("order.rejected", order, actor, {"reason": reason})
    return order


@transaction.atomic
def dispatch_order(*, wholesaler, actor, order_id) -> Order:
    order = _lock_order(order_id, wholesaler=wholesaler)
    _forbid_member_of_ordering_shop(order, actor)
    _require_status(order, Status.CONFIRMED, doing="dispatched")
    order.status = Status.DISPATCHED
    order.dispatched_at = timezone.now()
    order.save(update_fields=["status", "dispatched_at", "updated_at"])
    _record("order.dispatched", order, actor)
    return order


@transaction.atomic
def cancel_by_wholesaler(*, wholesaler, actor, order_id, reason) -> Order:
    reason = _need_reason(reason)
    order = _lock_order(order_id, wholesaler=wholesaler)
    _forbid_member_of_ordering_shop(order, actor)
    return _cancel(order, actor, reason, by="wholesaler")


# ------------------------------------------------------------------ shop actions
@transaction.atomic
def cancel_by_shop(*, shop, actor, order_id, reason) -> Order:
    reason = _need_reason(reason)
    order = _lock_order(order_id, shop=shop)
    return _cancel(order, actor, reason, by="shop")


def _cancel(order: Order, actor, reason: str, *, by: str) -> Order:
    _require_status(order, Status.SUBMITTED, Status.CONFIRMED, doing="cancelled")
    _close(order, Status.CANCELLED, reason, cancelled_by=by)
    _record("order.cancelled", order, actor, {"reason": reason, "by": by})
    return order


def _need_reason(reason) -> str:
    reason = (reason or "").strip()
    if not reason:
        raise DomainError("A reason is required.", code="reason_required")
    return reason[:255]


def _close(order: Order, status: str, reason: str, *, cancelled_by: str) -> None:
    order.status = status
    order.status_note = reason
    order.cancelled_by = cancelled_by
    order.closed_at = timezone.now()
    order.save(update_fields=["status", "status_note", "cancelled_by", "closed_at", "updated_at"])


@transaction.atomic
def receive_order(*, shop, actor, order_id, entries, note="") -> Order:
    """entries: [{item_id, received_quantity}] - EVERY line, explicitly (0 = nothing arrived).
    What arrived is added to the shop's stock as an ordinary purchase receipt."""
    order = _lock_order(order_id, shop=shop)
    _require_status(order, Status.DISPATCHED, doing="received")

    items = {i.pk: i for i in order.items.select_related("product", "product_unit")}
    given = {}
    for entry in entries:
        if entry["item_id"] in given:
            raise DomainError("List each line once.", code="duplicate_item")
        given[entry["item_id"]] = entry["received_quantity"]
    if set(given) - set(items):
        raise DomainError("One of those lines is not part of this order.", code="item_not_in_order")
    if set(items) - set(given):
        raise DomainError(
            "Record every line, using 0 for anything that did not arrive.",
            code="incomplete_receipt",
        )

    arrived = []
    for item_id, received in given.items():
        item = items[item_id]
        if received > item.quantity:
            raise OverReceived(
                f"'{item.product_name_snapshot}': {received.normalize():f} received but only "
                f"{item.quantity.normalize():f} ordered."
            )
        if received > 0:
            to_base(item.product_unit, received)  # precision check
            arrived.append(item)
        item.received_quantity = received
        item.save(update_fields=["received_quantity"])

    receipt = None
    if arrived:
        for item in arrived:
            _ensure_tracked(shop, item.product_id, actor)
        receipt = inventory.record_purchase_receipt(
            shop=shop, user=actor, supplier_name=order.wholesaler.business_name[:150],
            currency=order.currency,
            items=[
                {
                    "product_id": i.product_id, "product_unit_id": i.product_unit_id,
                    "quantity": i.received_quantity, "unit_cost": i.unit_price_snapshot,
                }
                for i in arrived
            ],
        )  # fmt: skip

    order.status = Status.RECEIVED
    order.received_at = timezone.now()
    order.receipt_note = (note or "").strip()[:255]
    order.purchase_receipt = receipt
    order.save(
        update_fields=["status", "received_at", "receipt_note", "purchase_receipt", "updated_at"]
    )

    shortages = [
        {
            "offer_id": i.offer_id,
            "ordered": i.quantity,
            "received": i.received_quantity,
            "short": i.quantity - i.received_quantity,
        }
        for i in items.values()
        if i.received_quantity < i.quantity
    ]
    _record(
        "order.received", order, actor,
        {
            "purchase_receipt_id": receipt.pk if receipt else None,
            "shortages": shortages, "note": order.receipt_note,
        },
    )  # fmt: skip
    return order


def _ensure_tracked(shop, product_id, actor) -> None:
    """Receiving a product the shop doesn't track yet starts tracking it (no stock is invented:
    only the received quantity is added)."""
    existing = ShopProduct.objects.filter(shop=shop, product_id=product_id).first()
    if existing is None:
        inventory.track_product(shop=shop, product_id=product_id, actor=actor)
    elif not existing.is_active:
        existing.is_active = True
        existing.save(update_fields=["is_active", "updated_at"])
