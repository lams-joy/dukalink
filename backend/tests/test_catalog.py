from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.catalog.models import Product, ProductUnit

pytestmark = pytest.mark.django_db


def test_zero_or_negative_conversion_factor_rejected_by_database(sugar):
    for bad in (Decimal("0"), Decimal("-1")):
        with pytest.raises(IntegrityError), transaction.atomic():
            ProductUnit.objects.create(product=sugar.product, unit_name=f"bad {bad}", base_quantity=bad)


def test_unit_names_are_unique_per_product(sugar):
    with pytest.raises(IntegrityError), transaction.atomic():
        ProductUnit.objects.create(
            product=sugar.product, unit_name="50 kg sack", base_quantity=Decimal("25")
        )


def test_base_unit_must_have_factor_one():
    product = Product.objects.create(name="Milk", base_unit="litre")
    unit = ProductUnit(product=product, unit_name="litre", base_quantity=Decimal("2"))
    with pytest.raises(ValidationError):
        unit.clean()


def test_ensure_base_unit_is_idempotent(sugar):
    sugar.product.ensure_base_unit()
    assert sugar.product.units.filter(unit_name="kg").count() == 1


def test_catalogue_search_returns_units(owner_client, sugar, flour):
    resp = owner_client.get("/api/v1/catalog/products/?q=sug")
    assert resp.status_code == 200
    results = resp.json()["results"]
    assert [p["name"] for p in results] == ["Sugar"]
    assert {u["unit_name"] for u in results[0]["units"]} == {"kg", "50 kg sack"}
