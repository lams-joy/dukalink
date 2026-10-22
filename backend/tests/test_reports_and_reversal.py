from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from apps.inventory import services
from apps.inventory.models import MovementType

from .conftest import make_client

pytestmark = pytest.mark.django_db

D = Decimal


def stock_in(shop, user, sugar, quantity="1"):
    return services.record_purchase_receipt(
        shop=shop, user=user,
        items=[{"product_id": sugar.product.pk, "product_unit_id": sugar.sack.pk,
                "quantity": D(quantity), "unit_cost": D("7000.00")}],
    )  # fmt: skip


def sell(shop, user, tracked, sugar, quantity="1.5"):
    return services.record_sale(
        shop=shop, user=user,
        items=[{"shop_product_id": tracked.pk, "product_unit_id": sugar.kg.pk,
                "quantity": D(quantity), "unit_price": D("180.00")}],
    )  # fmt: skip


# ------------------------------------------------------------------ alerts
def test_alerts_list_low_stock_largest_shortfall_first(owner_client, shop, owner, sugar, flour, tracked_sugar):
    tracked_flour = services.track_product(shop=shop, product_id=flour.product.pk, reorder_level_base=D("5"))
    stock_in(shop, owner, sugar)
    owner_client.patch(
        f"/api/v1/shops/{shop.pk}/inventory/{tracked_sugar.pk}/settings/",
        {"reorder_level_base": "60"},
        format="json",
    )  # sugar: 50 of 60 -> 10 below

    resp = owner_client.get(f"/api/v1/shops/{shop.pk}/alerts/")
    assert resp.status_code == 200
    results = resp.json()["results"]
    assert [a["product_name"] for a in results] == ["Sugar", "Maize flour"]
    assert results[0]["type"] == "low_stock"
    assert D(results[0]["shortfall_base"]) == D("10")
    assert D(results[1]["shortfall_base"]) == D("5")
    assert results[1]["shop_product_id"] == str(tracked_flour.pk)


def test_items_without_a_reorder_level_never_alert(owner_client, shop, tracked_sugar):
    assert owner_client.get(f"/api/v1/shops/{shop.pk}/alerts/").json()["count"] == 0


def test_alerts_are_shop_scoped(other_user, shop, tracked_sugar):
    assert make_client(other_user).get(f"/api/v1/shops/{shop.pk}/alerts/").status_code == 404


# ------------------------------------------------------------------ summary
def test_summary_totals(owner_client, shop, owner, sugar, tracked_sugar):
    stock_in(shop, owner, sugar)
    sell(shop, owner, tracked_sugar, sugar, "1.5")
    sell(shop, owner, tracked_sugar, sugar, "2")

    data = owner_client.get(f"/api/v1/shops/{shop.pk}/reports/summary/").json()
    assert data["sales"] == {"count": 2, "total_amount": "630.00"}
    assert data["purchases"] == {"count": 1, "total_cost": "7000.00"}
    assert data["stock"]["tracked_products"] == 1
    assert data["stock"]["out_of_stock_count"] == 0
    top = data["top_selling"][0]
    assert top["product_name"] == "Sugar"
    assert top["quantity_base"] == "3.500000"
    assert top["revenue"] == "630.00"


def test_summary_respects_the_period(owner_client, shop, owner, sugar, tracked_sugar):
    stock_in(shop, owner, sugar)
    sell(shop, owner, tracked_sugar, sugar)
    last_year = (date.today() - timedelta(days=400)).isoformat()
    last_year_end = (date.today() - timedelta(days=390)).isoformat()
    data = owner_client.get(
        f"/api/v1/shops/{shop.pk}/reports/summary/?from={last_year}&to={last_year_end}"
    ).json()
    assert data["sales"] == {"count": 0, "total_amount": "0.00"}
    assert data["top_selling"] == []


@pytest.mark.parametrize(
    "query",
    ["from=2026-10-10&to=2026-10-01", "from=not-a-date", "from=2024-01-01&to=2026-01-01"],
)
def test_summary_rejects_bad_periods(owner_client, shop, query):
    resp = owner_client.get(f"/api/v1/shops/{shop.pk}/reports/summary/?{query}")
    assert resp.status_code == 400


def test_summary_counts_low_and_out_of_stock(owner_client, shop, owner, sugar, tracked_sugar):
    owner_client.patch(
        f"/api/v1/shops/{shop.pk}/inventory/{tracked_sugar.pk}/settings/",
        {"reorder_level_base": "10"},
        format="json",
    )
    data = owner_client.get(f"/api/v1/shops/{shop.pk}/reports/summary/").json()
    assert data["stock"]["low_stock_count"] == 1
    assert data["stock"]["out_of_stock_count"] == 1


# ------------------------------------------------------------------ reversal endpoint
def reverse_url(shop, movement):
    return f"/api/v1/shops/{shop.pk}/stock-movements/{movement.pk}/reverse/"


def test_reversal_restores_stock_and_is_idempotent(owner_client, shop, owner, sugar, tracked_sugar):
    stock_in(shop, owner, sugar)
    sell(shop, owner, tracked_sugar, sugar, "10")
    sale_movement = tracked_sugar.movements.get(movement_type=MovementType.SALE)

    body = {"idempotency_key": str(uuid4()), "reason": "entered by mistake"}
    first = owner_client.post(reverse_url(shop, sale_movement), body, format="json")
    assert first.status_code == 201, first.content
    assert first.json()["movement_type"] == "reversal"
    tracked_sugar.refresh_from_db()
    assert tracked_sugar.quantity_base == D("50")

    replay = owner_client.post(reverse_url(shop, sale_movement), body, format="json")
    assert replay.status_code == 201
    assert replay["Idempotent-Replayed"] == "true"
    tracked_sugar.refresh_from_db()
    assert tracked_sugar.quantity_base == D("50")


def test_a_movement_cannot_be_reversed_twice(owner_client, shop, owner, sugar, tracked_sugar):
    stock_in(shop, owner, sugar)
    sell(shop, owner, tracked_sugar, sugar, "10")
    movement = tracked_sugar.movements.get(movement_type=MovementType.SALE)
    ok = owner_client.post(
        reverse_url(shop, movement), {"idempotency_key": str(uuid4()), "reason": "oops"}, format="json"
    )
    again = owner_client.post(
        reverse_url(shop, movement), {"idempotency_key": str(uuid4()), "reason": "oops"}, format="json"
    )
    assert ok.status_code == 201
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "state_conflict"


def test_reversal_needs_a_reason_and_a_manager(owner_client, staff_user, shop, owner, sugar, tracked_sugar):
    stock_in(shop, owner, sugar)
    movement = tracked_sugar.movements.get()
    no_reason = owner_client.post(
        reverse_url(shop, movement), {"idempotency_key": str(uuid4())}, format="json"
    )
    assert no_reason.status_code == 400
    as_staff = make_client(staff_user).post(
        reverse_url(shop, movement), {"idempotency_key": str(uuid4()), "reason": "x"}, format="json"
    )
    assert as_staff.status_code == 403


def test_cannot_reverse_another_shops_movement(other_user, other_shop, shop, owner, sugar, tracked_sugar):
    stock_in(shop, owner, sugar)
    movement = tracked_sugar.movements.get()
    resp = make_client(other_user).post(
        reverse_url(other_shop, movement), {"idempotency_key": str(uuid4()), "reason": "x"}, format="json"
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "movement_not_found"
    tracked_sugar.refresh_from_db()
    assert tracked_sugar.quantity_base == D("50")
