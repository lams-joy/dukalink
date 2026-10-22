"""Shop-specific (custom) products and their unit conversions."""

from decimal import Decimal

from django.db import IntegrityError, transaction

from apps.common.exceptions import CatalogueMatch, DomainError, InvalidUnit, StateConflict

from .models import Product, ProductUnit


def _clean(value: str) -> str:
    return " ".join((value or "").split())


def get_custom_product(shop, product_id) -> Product:
    """A custom product owned by this shop; anything else is 'not found' (never leaked)."""
    try:
        return Product.objects.get(pk=product_id, owner_shop=shop, is_active=True)
    except Product.DoesNotExist:
        raise DomainError("Product not found.", code="product_not_found") from None


def _validate_unit(product: Product, unit_name: str, base_quantity: Decimal, existing=()):
    name = _clean(unit_name)
    if not name:
        raise InvalidUnit("A unit needs a name.")
    if base_quantity <= 0:
        raise InvalidUnit("The conversion factor must be greater than zero.")
    taken = {u.lower() for u in existing} | {product.base_unit.lower()}
    if name.lower() in taken:
        raise InvalidUnit(f"The unit '{name}' already exists for this product.")
    return name


@transaction.atomic
def create_custom_product(
    *, shop, name, base_unit, brand="", barcode="", category="", units=()
) -> Product:
    """units: [{unit_name, base_quantity, is_purchase_unit, is_sale_unit}] in addition to the
    base unit, which is always created with a factor of 1."""
    name, brand, base_unit = _clean(name), _clean(brand), _clean(base_unit)
    barcode, category = _clean(barcode), _clean(category)
    if not name or not base_unit:
        raise DomainError("A product needs a name and a base unit.", code="invalid_product")

    # Do not shadow the shared catalogue: the shop should track the existing product, so
    # stock for "the same thing" is not split across two records.
    shared = Product.objects.filter(owner_shop__isnull=True, is_active=True)
    match = shared.filter(name__iexact=name, brand__iexact=brand).first()
    if match is None and barcode:
        match = shared.filter(barcode=barcode).first()
    if match is not None:
        raise CatalogueMatch(
            f"'{match.name}' already exists in the shared catalogue (product_id {match.pk}). "
            "Track that product instead of creating a custom one."
        )
    if Product.objects.filter(
        owner_shop=shop, is_active=True, name__iexact=name, brand__iexact=brand
    ).exists():
        raise StateConflict("This shop already has a custom product with that name and brand.")

    try:
        with transaction.atomic():  # savepoint: the unique index is the race-proof backstop
            product = Product.objects.create(
                owner_shop=shop, name=name, brand=brand, barcode=barcode,
                category=category, base_unit=base_unit,
            )  # fmt: skip
    except IntegrityError:
        raise StateConflict(
            "This shop already has a custom product with that name and brand."
        ) from None

    product.ensure_base_unit()
    seen: list[str] = []
    for spec in units:
        unit_name = _validate_unit(product, spec["unit_name"], spec["base_quantity"], seen)
        seen.append(unit_name)
        ProductUnit.objects.create(
            product=product,
            unit_name=unit_name,
            base_quantity=spec["base_quantity"],
            is_purchase_unit=spec.get("is_purchase_unit", True),
            is_sale_unit=spec.get("is_sale_unit", True),
        )
    return product


@transaction.atomic
def add_custom_unit(
    *, shop, product_id, unit_name, base_quantity, is_purchase_unit=True, is_sale_unit=True
) -> Product:
    """Add a unit to a custom product. Existing transactions keep their own snapshots."""
    product = get_custom_product(shop, product_id)
    existing = list(product.units.values_list("unit_name", flat=True))
    name = _validate_unit(product, unit_name, base_quantity, existing)
    ProductUnit.objects.create(
        product=product, unit_name=name, base_quantity=base_quantity,
        is_purchase_unit=is_purchase_unit, is_sale_unit=is_sale_unit,
    )  # fmt: skip
    return product
