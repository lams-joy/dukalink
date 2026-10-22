"""Physical stock counts (database.md section 4).

Workflow: start -> record counted quantities -> submit -> approve | cancel.

* A count never touches stock until it is approved (testing.md: "A stock count does not
  change stock until approved").
* `expected_quantity_base` is snapshotted when a product's count is *entered*, under the
  product row lock, so sales recorded while the shopkeeper is counting do not distort the
  variance. Approval applies the variance as an ADJUSTMENT movement (a delta, not "set
  to"), so anything recorded after the count stays in the ledger.
* If a later movement means the delta can no longer be applied (it would take stock
  negative), approval fails with 409 and the whole approval rolls back; recount that product.
"""

from decimal import Decimal

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.audit import services as audit
from apps.common.exceptions import DomainError, InvalidQuantity, ProductNotTracked, StateConflict

from .models import MovementType, ShopProduct, StockCount, StockCountItem
from .services import _apply, _lock_shop_products
from .units import QUANT, get_unit

Status = StockCount.Status


def _get_count_for_update(shop, count_id) -> StockCount:
    try:
        return StockCount.objects.select_for_update().get(pk=count_id, shop=shop)
    except StockCount.DoesNotExist:
        raise DomainError("Stock count not found.", code="stock_count_not_found") from None


def _require_status(count: StockCount, *allowed: str, action: str) -> None:
    if count.status not in allowed:
        raise StateConflict(f"A {count.status.replace('_', ' ')} stock count cannot be {action}.")


def _counted_to_base(unit, quantity: Decimal) -> Decimal:
    """Like to_base, but zero is valid here: an empty shelf is a legitimate count."""
    if quantity < 0:
        raise InvalidQuantity("A counted quantity cannot be negative.")
    base = quantity * unit.base_quantity
    exact = base.quantize(QUANT)
    if base != exact:
        raise InvalidQuantity("That quantity has more precision than is supported.")
    return exact


@transaction.atomic
def start_stock_count(*, shop, user, shop_product_ids=None, note="") -> StockCount:
    """Open a count over the given products (default: every active tracked product)."""
    if StockCount.objects.filter(shop=shop, status__in=StockCount.OPEN_STATUSES).exists():
        raise StateConflict("This shop already has an open stock count.")

    products = ShopProduct.objects.filter(shop=shop, is_active=True)
    if shop_product_ids:
        wanted = set(shop_product_ids)
        products = products.filter(pk__in=wanted)
        if products.count() != len(wanted):
            raise ProductNotTracked()
    ids = list(products.values_list("pk", flat=True))
    if not ids:
        raise DomainError("There are no tracked products to count.", code="nothing_to_count")

    try:
        with transaction.atomic():  # savepoint: the unique index is the race-proof backstop
            count = StockCount.objects.create(shop=shop, started_by=user, note=note)
    except IntegrityError:
        raise StateConflict("This shop already has an open stock count.") from None
    StockCountItem.objects.bulk_create(
        StockCountItem(stock_count=count, shop_product_id=pk) for pk in ids
    )
    return count


@transaction.atomic
def record_counts(*, shop, user, count_id, entries) -> StockCount:
    """entries: [{shop_product_id, product_unit_id, quantity}] - re-entering a product
    replaces its earlier count (and re-snapshots the expected balance)."""
    count = _get_count_for_update(shop, count_id)
    _require_status(count, Status.IN_PROGRESS, action="edited")

    items = {
        i.shop_product_id: i
        for i in count.items.filter(shop_product_id__in=[e["shop_product_id"] for e in entries])
    }
    if len(items) != len({e["shop_product_id"] for e in entries}):
        raise DomainError("That product is not part of this count.", code="product_not_in_count")

    locked = _lock_shop_products(shop, items.keys())
    now = timezone.now()
    for entry in entries:
        sp = locked[entry["shop_product_id"]]
        unit = get_unit(sp.product_id, entry["product_unit_id"])
        item = items[sp.pk]
        item.expected_quantity_base = sp.quantity_base
        item.counted_quantity_base = _counted_to_base(unit, entry["quantity"])
        item.variance_base = item.counted_quantity_base - sp.quantity_base
        item.counted_at = now
        item.save(
            update_fields=[
                "expected_quantity_base", "counted_quantity_base", "variance_base", "counted_at",
            ]  # fmt: skip
        )
    return count


@transaction.atomic
def submit_stock_count(*, shop, user, count_id) -> StockCount:
    count = _get_count_for_update(shop, count_id)
    _require_status(count, Status.IN_PROGRESS, action="submitted")
    if not count.items.filter(counted_quantity_base__isnull=False).exists():
        raise DomainError("Record at least one counted quantity first.", code="nothing_counted")
    count.status = Status.SUBMITTED
    count.submitted_at = timezone.now()
    count.save(update_fields=["status", "submitted_at"])
    return count


@transaction.atomic
def approve_stock_count(*, shop, user, count_id) -> StockCount:
    """Write one ADJUSTMENT per non-zero variance. All-or-nothing. Uncounted products are
    left alone."""
    count = _get_count_for_update(shop, count_id)
    _require_status(count, Status.SUBMITTED, action="approved")

    counted = list(count.items.filter(counted_quantity_base__isnull=False).order_by("pk"))
    locked = _lock_shop_products(shop, [i.shop_product_id for i in counted])
    for item in counted:
        if item.variance_base == 0:
            continue
        movement = _apply(
            locked[item.shop_product_id],
            user=user,
            movement_type=MovementType.ADJUSTMENT,
            delta=item.variance_base,
            reference_type="stock_count",
            reference_id=count.pk,
            note=(
                f"Stock count: expected {item.expected_quantity_base}, "
                f"counted {item.counted_quantity_base}"
            )[:255],
        )
        item.adjustment = movement
        item.save(update_fields=["adjustment"])

    count.status = Status.APPROVED
    count.resolved_by = user
    count.resolved_at = timezone.now()
    count.save(update_fields=["status", "resolved_by", "resolved_at"])
    adjusted = [i for i in counted if i.variance_base != 0]
    audit.record(
        action="stock_count.approved", obj_type="stock_count", obj_id=count.pk, actor=user,
        shop=shop,
        changes={
            "products_counted": len(counted),
            "adjustments": [
                {
                    "shop_product_id": i.shop_product_id, "movement_id": i.adjustment_id,
                    "expected_base": i.expected_quantity_base,
                    "counted_base": i.counted_quantity_base, "variance_base": i.variance_base,
                }
                for i in adjusted
            ],
        },
    )  # fmt: skip
    return count


@transaction.atomic
def cancel_stock_count(*, shop, user, count_id, reason: str) -> StockCount:
    """Reject or abandon an open count. No stock changes."""
    count = _get_count_for_update(shop, count_id)
    _require_status(count, *StockCount.OPEN_STATUSES, action="cancelled")
    count.status = Status.CANCELLED
    count.resolved_by = user
    count.resolved_at = timezone.now()
    count.resolution_note = reason[:255]
    count.save(update_fields=["status", "resolved_by", "resolved_at", "resolution_note"])
    audit.record(
        action="stock_count.cancelled", obj_type="stock_count", obj_id=count.pk, actor=user,
        shop=shop, changes={"reason": reason[:255]},
    )  # fmt: skip
    return count
