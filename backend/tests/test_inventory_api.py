from decimal import Decimal
from uuid import uuid4

import pytest

from apps.inventory.models import PurchaseReceipt, StockMovement

from .conftest import make_client

pytestmark = pytest.mark.django_db

D = Decimal


def receipt_payload(sugar, key=None, quantity="1"):
    return {
        "idempotency_key": str(key or uuid4()),
        "supplier_name": "Example Wholesale",
        "items": [
            {
                "product_id": str(sugar.product.pk),
                "product_unit_id": str(sugar.sack.pk),
                "quantity": quantity,
                "unit_cost": "7000.00",
            }
        ],
    }


def sale_payload(tracked, sugar, quantity="1.500", key=None):
    return {
        "idempotency_key": str(key or uuid4()),
        "items": [
            {
                "shop_product_id": str(tracked.pk),
                "product_unit_id": str(sugar.kg.pk),
                "quantity": quantity,
                "unit_price": "180.00",
            }
        ],
    }


def test_receipt_then_sale_through_the_api(owner_client, shop, sugar, tracked_sugar):
    base = f"/api/v1/shops/{shop.pk}"
    r = owner_client.post(f"{base}/purchase-receipts/", receipt_payload(sugar), format="json")
    assert r.status_code == 201, r.content
    assert D(r.json()["items"][0]["quantity_base"]) == D("50")

    s = owner_client.post(f"{base}/sales/", sale_payload(tracked_sugar, sugar), format="json")
    assert s.status_code == 201, s.content
    assert D(s.json()["total_amount"]) == D("270.00")

    detail = owner_client.get(f"{base}/inventory/{tracked_sugar.pk}/").json()
    assert D(detail["quantity_base"]) == D("48.5")

    history = owner_client.get(f"{base}/stock-movements/").json()
    assert history["count"] == 2
    assert [D(m["quantity_base_delta"]) for m in history["results"]] == [D("-1.5"), D("50")]


def test_retrying_a_receipt_with_the_same_key_does_not_double_apply(
    owner_client, shop, sugar, tracked_sugar
):
    url = f"/api/v1/shops/{shop.pk}/purchase-receipts/"
    payload = receipt_payload(sugar)

    first = owner_client.post(url, payload, format="json")
    second = owner_client.post(url, payload, format="json")

    assert first.status_code == second.status_code == 201
    assert second.json() == first.json()
    assert second["Idempotent-Replayed"] == "true"
    assert PurchaseReceipt.objects.count() == 1
    tracked_sugar.refresh_from_db()
    assert tracked_sugar.quantity_base == D("50")


def test_same_key_with_a_different_payload_is_a_conflict(owner_client, shop, sugar, tracked_sugar):
    url = f"/api/v1/shops/{shop.pk}/purchase-receipts/"
    key = uuid4()
    assert owner_client.post(url, receipt_payload(sugar, key, "1"), format="json").status_code == 201
    resp = owner_client.post(url, receipt_payload(sugar, key, "2"), format="json")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "idempotency_conflict"
    tracked_sugar.refresh_from_db()
    assert tracked_sugar.quantity_base == D("50")


def test_a_failed_request_can_be_retried_with_the_same_key(owner_client, shop, sugar, tracked_sugar):
    base = f"/api/v1/shops/{shop.pk}"
    key = uuid4()
    payload = sale_payload(tracked_sugar, sugar, "10", key)

    failed = owner_client.post(f"{base}/sales/", payload, format="json")
    assert failed.status_code == 409
    assert failed.json()["error"]["code"] == "insufficient_stock"

    owner_client.post(f"{base}/purchase-receipts/", receipt_payload(sugar), format="json")
    retried = owner_client.post(f"{base}/sales/", payload, format="json")
    assert retried.status_code == 201


def test_validation_errors_use_the_envelope(owner_client, shop, sugar, tracked_sugar):
    payload = sale_payload(tracked_sugar, sugar, quantity="-1")
    resp = owner_client.post(f"/api/v1/shops/{shop.pk}/sales/", payload, format="json")
    assert resp.status_code == 400
    error = resp.json()["error"]
    assert error["code"] == "validation_error"
    assert "items" in error["details"]
    assert error["request_id"]


def test_missing_idempotency_key_is_rejected(owner_client, shop, sugar, tracked_sugar):
    payload = sale_payload(tracked_sugar, sugar)
    payload.pop("idempotency_key")
    resp = owner_client.post(f"/api/v1/shops/{shop.pk}/sales/", payload, format="json")
    assert resp.status_code == 400


def test_other_shops_users_cannot_read_or_write(other_user, shop, sugar, tracked_sugar):
    client = make_client(other_user)
    base = f"/api/v1/shops/{shop.pk}"
    assert client.get(f"{base}/inventory/").status_code == 404
    assert client.get(f"{base}/stock-movements/").status_code == 404
    assert client.post(f"{base}/sales/", sale_payload(tracked_sugar, sugar), format="json").status_code == 404
    assert client.post(f"{base}/purchase-receipts/", receipt_payload(sugar), format="json").status_code == 404


def test_a_users_own_shop_cannot_touch_another_shops_stock(
    other_user, other_shop, sugar, tracked_sugar
):
    # other_user is a valid member of other_shop but references a ShopProduct of `shop`.
    resp = make_client(other_user).post(
        f"/api/v1/shops/{other_shop.pk}/sales/", sale_payload(tracked_sugar, sugar), format="json"
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "product_not_tracked"
    assert StockMovement.objects.count() == 0


def test_staff_can_trade_but_not_adjust_or_set_opening_stock(
    staff_user, shop, sugar, tracked_sugar, owner_client
):
    client = make_client(staff_user)
    base = f"/api/v1/shops/{shop.pk}"
    assert client.post(f"{base}/purchase-receipts/", receipt_payload(sugar), format="json").status_code == 201
    adjust = {
        "idempotency_key": str(uuid4()),
        "shop_product_id": str(tracked_sugar.pk),
        "quantity_base_delta": "-1",
        "reason": "spillage",
    }
    assert client.post(f"{base}/stock-adjustments/", adjust, format="json").status_code == 403
    assert owner_client.post(f"{base}/stock-adjustments/", adjust, format="json").status_code == 201


def test_opening_stock_endpoint(owner_client, shop, sugar, tracked_sugar):
    url = f"/api/v1/shops/{shop.pk}/inventory/{tracked_sugar.pk}/opening-stock/"
    payload = {"idempotency_key": str(uuid4()), "product_unit_id": str(sugar.kg.pk), "quantity": "12.5"}
    assert owner_client.post(url, payload, format="json").status_code == 201
    again = {**payload, "idempotency_key": str(uuid4())}
    resp = owner_client.post(url, again, format="json")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "state_conflict"


def test_track_product_list_search_and_low_stock(owner_client, shop, sugar, flour):
    base = f"/api/v1/shops/{shop.pk}/inventory/"
    resp = owner_client.post(
        base, {"product_id": str(sugar.product.pk), "reorder_level_base": "10"}, format="json"
    )
    assert resp.status_code == 201
    assert resp.json()["is_low_stock"] is True  # 0 kg <= reorder level 10
    owner_client.post(base, {"product_id": str(flour.product.pk)}, format="json")

    assert owner_client.get(base).json()["count"] == 2
    assert owner_client.get(f"{base}?q=sug").json()["count"] == 1
    # Sugar has stock 0 <= reorder level 10, flour has no reorder level.
    low = owner_client.get(f"{base}?low_stock=true").json()
    assert [i["product_name"] for i in low["results"]] == ["Sugar"]
    assert owner_client.post(base, {"product_id": str(sugar.product.pk)}, format="json").status_code == 409


def test_inventory_settings_update(owner_client, shop, tracked_sugar):
    url = f"/api/v1/shops/{shop.pk}/inventory/{tracked_sugar.pk}/settings/"
    resp = owner_client.patch(url, {"reorder_level_base": "25"}, format="json")
    assert resp.status_code == 200
    assert D(resp.json()["reorder_level_base"]) == D("25")
    assert owner_client.patch(url, {"reorder_level_base": "-1"}, format="json").status_code == 400
