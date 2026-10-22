"""Inventory business rules. Views stay thin and call these functions.

Invariants (database.md section 10):
* every stock change = one StockMovement + the cached balance update, in ONE transaction;
* rows are locked (SELECT ... FOR UPDATE) in a stable order, so concurrent writes cannot
  lose updates or deadlock on multi-line operations;
* quantities and money are Decimal, never float.
"""

from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.catalog.models import Product
from apps.common.exceptions import (
    DomainError,
    InsufficientStock,
    InvalidQuantity,
    ProductNotTracked,
    StateConflict,
)
from apps.common.money import money, per_base_unit_cost

from .models import (
    MovementType,
    PurchaseItem,
    PurchaseReceipt,
    Sale,
    SaleItem,
    ShopProduct,
    StockMovement,
)
from .units import get_unit, to_base


# ---------------------------------------------------------------- internals
def _lock_shop_products(shop, ids) -> dict:
    """Lock the shop's rows for these ids in a stable order; error if any is missing."""
    unique_ids = sorted(set(ids), key=str)
    rows = (
        ShopProduct.objects.select_for_update()
        .filter(shop=shop, pk__in=unique_ids, is_active=True)
        .order_by("pk")
    )
    found = {sp.pk: sp for sp in rows}
    if set(unique_ids) - set(found):
        raise ProductNotTracked()
    return found


def _apply(
    sp: ShopProduct,
    *,
    user,
    movement_type,
    delta: Decimal,
    unit=None,
    entered_quantity=None,
    unit_cost_base=None,
    reference_type="",
    reference_id=None,
    note="",
) -> StockMovement:
    """Write one movement and update the cached balance. `sp` must already be locked."""
    new_balance = sp.quantity_base + delta
    if new_balance < 0 and not settings.ALLOW_NEGATIVE_STOCK:
        raise InsufficientStock(
            f"Only {sp.quantity_base} available; this would leave {new_balance}."
        )
    movement = StockMovement.objects.create(
        shop_product=sp,
        movement_type=movement_type,
        quantity_base_delta=delta,
        balance_after_base=new_balance,
        unit_cost_base=unit_cost_base,
        entered_quantity=entered_quantity,
        entered_unit_name=unit.unit_name if unit else "",
        entered_unit_base_quantity=unit.base_quantity if unit else None,
        reference_type=reference_type,
        reference_id=reference_id,
        note=note,
        created_by=user,
    )
    sp.quantity_base = new_balance
    sp.save(update_fields=["quantity_base", "updated_at"])
    return movement


# ---------------------------------------------------------------- tracking
@transaction.atomic
def track_product(*, shop, product_id, reorder_level_base=None) -> ShopProduct:
    try:
        # Shared catalogue entries, or this shop's own custom products - never another shop's.
        product = Product.objects.get(
            Q(owner_shop__isnull=True) | Q(owner_shop=shop), pk=product_id, is_active=True
        )
    except Product.DoesNotExist:
        raise DomainError("Product not found.", code="product_not_found") from None
    if ShopProduct.objects.filter(shop=shop, product=product).exists():
        raise StateConflict("This product is already tracked in the shop.")
    return ShopProduct.objects.create(
        shop=shop,
        product=product,
        reorder_level_base=reorder_level_base,
        tracking_mode=shop.default_tracking_mode,
    )


# ---------------------------------------------------------------- stock writes
@transaction.atomic
def record_opening_stock(*, shop, user, shop_product_id, unit_id, quantity, unit_cost=None, note=""):
    sp = _lock_shop_products(shop, [shop_product_id])[shop_product_id]
    if sp.movements.exists():
        raise StateConflict("Opening stock can only be set before any other movement.")
    unit = get_unit(sp.product_id, unit_id)
    return _apply(
        sp,
        user=user,
        movement_type=MovementType.OPENING_STOCK,
        delta=to_base(unit, quantity),
        unit=unit,
        entered_quantity=quantity,
        unit_cost_base=per_base_unit_cost(unit_cost, unit.base_quantity) if unit_cost else None,
        note=note,
    )


@transaction.atomic
def record_purchase_receipt(
    *, shop, user, items, supplier_name="", received_at=None, currency=None
) -> PurchaseReceipt:
    """items: [{product_id, product_unit_id, quantity, unit_cost?}]"""
    wanted = [i["product_id"] for i in items]
    mapping = dict(
        ShopProduct.objects.filter(shop=shop, product_id__in=wanted, is_active=True).values_list(
            "product_id", "pk"
        )
    )
    if set(wanted) - set(mapping):
        raise ProductNotTracked()
    locked = _lock_shop_products(shop, mapping.values())

    receipt = PurchaseReceipt.objects.create(
        shop=shop,
        supplier_name=supplier_name,
        received_at=received_at or timezone.now(),
        currency=currency or settings.DEFAULT_CURRENCY,
        created_by=user,
    )
    total, any_cost = Decimal("0"), False
    for item in items:
        sp = locked[mapping[item["product_id"]]]
        unit = get_unit(sp.product_id, item["product_unit_id"], purpose="purchase")
        quantity = item["quantity"]
        base = to_base(unit, quantity)
        unit_cost = item.get("unit_cost")
        line_total = money(quantity * unit_cost) if unit_cost is not None else None
        if line_total is not None:
            total, any_cost = total + line_total, True
        movement = _apply(
            sp,
            user=user,
            movement_type=MovementType.PURCHASE_RECEIPT,
            delta=base,
            unit=unit,
            entered_quantity=quantity,
            unit_cost_base=(
                per_base_unit_cost(unit_cost, unit.base_quantity) if unit_cost is not None else None
            ),
            reference_type="purchase_receipt",
            reference_id=receipt.pk,
            note=f"Supplier: {supplier_name}"[:255] if supplier_name else "",
        )
        PurchaseItem.objects.create(
            receipt=receipt,
            shop_product=sp,
            product_unit=unit,
            product_name_snapshot=unit.product.name,
            unit_name_snapshot=unit.unit_name,
            unit_base_quantity_snapshot=unit.base_quantity,
            quantity=quantity,
            quantity_base=base,
            unit_cost=unit_cost,
            line_total=line_total,
            movement=movement,
        )
    if any_cost:
        receipt.total_cost = total
        receipt.save(update_fields=["total_cost"])
    return receipt


@transaction.atomic
def record_sale(
    *, shop, user, items, sold_at=None, recording_source=Sale.Source.ONLINE, currency=None
) -> Sale:
    """items: [{shop_product_id, product_unit_id, quantity, unit_price}]"""
    locked = _lock_shop_products(shop, [i["shop_product_id"] for i in items])
    sale = Sale.objects.create(
        shop=shop,
        sold_at=sold_at or timezone.now(),
        recording_source=recording_source,
        currency=currency or settings.DEFAULT_CURRENCY,
        total_amount=Decimal("0"),
        created_by=user,
    )
    total = Decimal("0")
    for item in items:
        sp = locked[item["shop_product_id"]]
        unit = get_unit(sp.product_id, item["product_unit_id"], purpose="sale")
        quantity = item["quantity"]
        base = to_base(unit, quantity)
        line_total = money(quantity * item["unit_price"])
        total += line_total
        movement = _apply(
            sp,
            user=user,
            movement_type=MovementType.SALE,
            delta=-base,
            unit=unit,
            entered_quantity=quantity,
            reference_type="sale",
            reference_id=sale.pk,
        )
        SaleItem.objects.create(
            sale=sale,
            shop_product=sp,
            product_unit=unit,
            product_name_snapshot=unit.product.name,
            unit_name_snapshot=unit.unit_name,
            unit_base_quantity_snapshot=unit.base_quantity,
            quantity=quantity,
            quantity_base=base,
            unit_price=item["unit_price"],
            line_total=line_total,
            movement=movement,
        )
    sale.total_amount = total
    sale.save(update_fields=["total_amount"])
    return sale


@transaction.atomic
def record_adjustment(*, shop, user, shop_product_id, delta_base: Decimal, reason: str):
    """Signed correction in base units. A reason is mandatory."""
    if delta_base == 0:
        raise InvalidQuantity("An adjustment cannot be zero.")
    if not reason.strip():
        raise DomainError("A reason is required.", code="reason_required")
    sp = _lock_shop_products(shop, [shop_product_id])[shop_product_id]
    return _apply(
        sp, user=user, movement_type=MovementType.ADJUSTMENT, delta=delta_base, note=reason.strip()
    )


@transaction.atomic
def reverse_movement(*, shop, user, movement_id, reason: str = ""):
    """Compensate a movement with an equal and opposite one (never edit/delete the original)."""
    try:
        original = StockMovement.objects.select_related("shop_product").get(
            pk=movement_id, shop_product__shop=shop
        )
    except StockMovement.DoesNotExist:
        raise DomainError("Movement not found.", code="movement_not_found") from None
    if original.movement_type == MovementType.REVERSAL:
        raise StateConflict("A reversal cannot itself be reversed.")
    if StockMovement.objects.filter(
        movement_type=MovementType.REVERSAL, reference_id=original.pk
    ).exists():
        raise StateConflict("This movement has already been reversed.")
    sp = _lock_shop_products(shop, [original.shop_product_id])[original.shop_product_id]
    reversal = _apply(
        sp,
        user=user,
        movement_type=MovementType.REVERSAL,
        delta=-original.quantity_base_delta,
        reference_type="stock_movement",
        reference_id=original.pk,
        note=reason[:255],
    )
    # Void the sale/receipt line this movement belongs to, so reports stop counting it.
    now = timezone.now()
    SaleItem.objects.filter(movement=original).update(reversed_at=now)
    PurchaseItem.objects.filter(movement=original).update(reversed_at=now)
    return reversal
