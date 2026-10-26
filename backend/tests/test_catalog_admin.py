import csv

import pytest
from django.core.management import call_command

from apps.catalog.models import Product, ProductUnit

pytestmark = pytest.mark.django_db
URL = "/api/v1/admin/catalog/products/"
NEW = {"name": "Rice", "base_unit": "kg", "category": "Staples", "units": [{"unit_name": "25 kg sack", "base_quantity": "25"}]}


def test_only_platform_staff_can_use_the_admin_catalogue(owner_client, admin_client):
    assert owner_client.get(URL).status_code == 403
    assert owner_client.post(URL, NEW, format="json").status_code == 403
    assert admin_client.get(URL).status_code == 200


def test_admin_creates_a_product_with_units_and_shops_can_search_it(owner_client, admin_client):
    resp = admin_client.post(URL, NEW, format="json")
    assert resp.status_code == 201
    names = {u["unit_name"]: u["base_quantity"] for u in resp.json()["units"]}
    assert set(names) == {"kg", "25 kg sack"}
    found = owner_client.get("/api/v1/catalog/products/?q=rice").json()["results"]
    assert [p["name"] for p in found] == ["Rice"]


def test_duplicate_names_are_rejected(admin_client):
    admin_client.post(URL, NEW, format="json")
    again = admin_client.post(URL, {**NEW, "name": "rice"}, format="json")
    assert again.status_code == 400
    assert again.json()["error"]["code"] == "duplicate_product"


def test_deactivating_hides_a_product_from_shops_but_not_from_admins(owner_client, admin_client):
    pid = admin_client.post(URL, NEW, format="json").json()["id"]
    assert admin_client.patch(f"{URL}{pid}/", {"is_active": False}, format="json").status_code == 200
    assert owner_client.get("/api/v1/catalog/products/?q=rice").json()["results"] == []
    listed = admin_client.get(f"{URL}?include_inactive=true").json()["results"]
    assert [p["name"] for p in listed] == ["Rice"]


def test_base_unit_and_conversion_factors_cannot_be_changed(admin_client):
    product = admin_client.post(URL, NEW, format="json").json()
    sack = next(u for u in product["units"] if u["unit_name"] == "25 kg sack")
    base = next(u for u in product["units"] if u["unit_name"] == "kg")
    admin_client.patch(f"{URL}{product['id']}/", {"base_unit": "g"}, format="json")
    assert Product.objects.get(pk=product["id"]).base_unit == "kg"
    admin_client.patch(f"{URL}{product['id']}/units/{sack['id']}/", {"base_quantity": "5"}, format="json")
    assert str(ProductUnit.objects.get(pk=sack["id"]).base_quantity).startswith("25")
    blocked = admin_client.patch(f"{URL}{product['id']}/units/{base['id']}/", {"is_active": False}, format="json")
    assert blocked.status_code == 400 and blocked.json()["error"]["code"] == "base_unit_protected"


def test_admin_can_add_and_retire_a_unit(admin_client):
    product = admin_client.post(URL, NEW, format="json").json()
    added = admin_client.post(f"{URL}{product['id']}/units/", {"unit_name": "1 kg packet", "base_quantity": "1"}, format="json")
    assert added.status_code == 201
    dup = admin_client.post(f"{URL}{product['id']}/units/", {"unit_name": "1 kg packet", "base_quantity": "2"}, format="json")
    assert dup.status_code == 400
    unit = next(u for u in added.json()["units"] if u["unit_name"] == "1 kg packet")
    assert admin_client.patch(f"{URL}{product['id']}/units/{unit['id']}/", {"is_active": False}, format="json").status_code == 200


def test_me_reports_staff_status(owner_client, admin_client):
    assert owner_client.get("/api/v1/me/").json()["is_staff"] is False
    assert admin_client.get("/api/v1/me/").json()["is_staff"] is True


def test_seed_command_is_idempotent_and_loads_the_bundled_list():
    call_command("seed_catalog")
    count = Product.objects.filter(owner_shop__isnull=True).count()
    assert count >= 40
    call_command("seed_catalog")
    assert Product.objects.filter(owner_shop__isnull=True).count() == count
    sugar = Product.objects.get(name="Sugar")
    assert {u.unit_name: u.base_quantity for u in sugar.units.all()}["50 kg sack"] == 50


def test_seed_command_accepts_an_edited_file(tmp_path):
    f = tmp_path / "mine.csv"
    with f.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["name", "brand", "category", "base_unit", "units"])
        w.writerow(["Millet", "", "Staples", "kg", "90 kg sack=90"])
    call_command("seed_catalog", file=str(f))
    assert ProductUnit.objects.get(product__name="Millet", unit_name="90 kg sack").base_quantity == 90
