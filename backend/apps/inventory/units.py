from decimal import Decimal

from django.conf import settings

from apps.catalog.models import ProductUnit
from apps.common.exceptions import InvalidQuantity, InvalidUnit

QUANT = Decimal(1).scaleb(-settings.QUANTITY_PLACES)


def get_unit(product_id, unit_id, *, purpose: str | None = None) -> ProductUnit:
    """Resolve a unit that belongs to the product. purpose: "purchase" | "sale" | None."""
    try:
        unit = ProductUnit.objects.select_related("product").get(pk=unit_id, product_id=product_id, is_active=True)
    except ProductUnit.DoesNotExist:
        raise InvalidUnit("That unit does not belong to this product.") from None
    if purpose == "purchase" and not unit.is_purchase_unit:
        raise InvalidUnit("That unit cannot be used for purchases.")
    if purpose == "sale" and not unit.is_sale_unit:
        raise InvalidUnit("That unit cannot be used for sales.")
    return unit


def to_base(unit: ProductUnit, quantity: Decimal) -> Decimal:
    """quantity (in `unit`) -> base units. Rejects non-positive or over-precise results."""
    if quantity <= 0:
        raise InvalidQuantity("Quantity must be greater than zero.")
    base = quantity * unit.base_quantity
    exact = base.quantize(QUANT)
    if base != exact:
        raise InvalidQuantity("That quantity has more precision than is supported.")
    return exact
