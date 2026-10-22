from decimal import Decimal
from uuid import uuid4

import pytest

from apps.inventory.models import PurchaseReceipt, Sale, StockMovement

from .conftest import make_client

pytestmark = pytest.mark.django_db

D = Decimal


def op(operation_type, payload, operation_id=None):
    return {
        "operation_id": str(operation_id or uuid4()),
        "operation_type": operation_type,
        "payload": payload,
    }


def receipt(sugar, quantity="1"):
    return op(
        "purchase_receipt",
        {
            "supplier_name": "Example Wholesale",
            "items": [
                {
                    "product_id": str(sugar.product.pk),
                    "product_unit_id": str(sugar.sack.pk),
                    "quantity": quantity,
                    "unit_cost": "7000.00",
                }
            ],
        },
    )


def sale(tracked, sugar, quantity="1.5", operation_id=None):
    return op(
        "sale",
        {
            "sold_at": "2026-10-20T09:15:00Z",
            "items": [
                {
                    "shop_product_id": str(tracked.pk),
                    "product_unit_id": str(sugar.kg.pk),
                    "quantity": quantity,
                    "unit_price": "180.00",
                }
            ],
        },
        operation_id,
    )


def post(client, shop, operations):
    return client.post(f"/api/v1/shops/{shop.pk}/sync/", {"operations": operations}, format="json")


def statuses(resp):
    return [r["status"] for r in resp.json()["results"]]


def test_a_batch_is_applied_in_order_and_marked_offline(owner_client, shop, sugar, tracked_sugar):
    resp = post(owner_client, shop, [receipt(sugar), sale(tracked_sugar, sugar)])
    assert resp.status_code == 200
    assert statuses(resp) == ["accepted", "accepted"]

    tracked_sugar.refresh_from_db()
    assert tracked_sugar.quantity_base == D("48.5")
    recorded = Sale.objects.get()
    assert recorded.recording_source == "offline"
    assert recorded.sold_at.isoformat().startswith("2026-10-20T09:15")


def test_resending_a_batch_returns_duplicates_and_changes_nothing(
    owner_client, shop, sugar, tracked_sugar
):
    batch = [receipt(sugar), sale(tracked_sugar, sugar)]
    first = post(owner_client, shop, batch)
    second = post(owner_client, shop, batch)

    assert statuses(second) == ["duplicate", "duplicate"]
    assert second.json()["results"][0]["result"] == first.json()["results"][0]["result"]
    assert PurchaseReceipt.objects.count() == 1
    assert Sale.objects.count() == 1
    tracked_sugar.refresh_from_db()
    assert tracked_sugar.quantity_base == D("48.5")


def test_one_conflict_does_not_block_later_operations(owner_client, shop, sugar, tracked_sugar):
    batch = [
        receipt(sugar),  # 50 kg in
        sale(tracked_sugar, sugar, "80"),  # cannot be satisfied
        sale(tracked_sugar, sugar, "2"),  # fine
    ]
    resp = post(owner_client, shop, batch)
    assert statuses(resp) == ["accepted", "conflict", "accepted"]
    conflict = resp.json()["results"][1]
    assert conflict["error"]["code"] == "insufficient_stock"
    assert conflict["result"] is None
    tracked_sugar.refresh_from_db()
    assert tracked_sugar.quantity_base == D("48")


def test_invalid_and_unknown_operations_are_rejected_individually(
    owner_client, shop, sugar, tracked_sugar
):
    bad_qty = sale(tracked_sugar, sugar, "-3")
    unknown = op("teleport_stock", {})
    resp = post(owner_client, shop, [bad_qty, unknown, receipt(sugar)])
    assert statuses(resp) == ["rejected", "rejected", "accepted"]
    results = resp.json()["results"]
    assert results[0]["error"]["code"] == "validation_error"
    assert "items" in results[0]["error"]["details"]
    assert results[1]["error"]["code"] == "unknown_operation_type"


def test_a_rejected_operation_can_be_fixed_and_resent_with_the_same_id(
    owner_client, shop, sugar, tracked_sugar
):
    post(owner_client, shop, [receipt(sugar)])
    op_id = uuid4()
    assert statuses(post(owner_client, shop, [sale(tracked_sugar, sugar, "-1", op_id)])) == ["rejected"]
    assert statuses(post(owner_client, shop, [sale(tracked_sugar, sugar, "1", op_id)])) == ["accepted"]


def test_same_operation_id_with_a_different_payload_is_a_conflict(
    owner_client, shop, sugar, tracked_sugar
):
    post(owner_client, shop, [receipt(sugar)])
    op_id = uuid4()
    assert statuses(post(owner_client, shop, [sale(tracked_sugar, sugar, "1", op_id)])) == ["accepted"]
    resp = post(owner_client, shop, [sale(tracked_sugar, sugar, "2", op_id)])
    assert statuses(resp) == ["conflict"]
    assert resp.json()["results"][0]["error"]["code"] == "idempotency_conflict"


def test_an_operation_sent_over_rest_is_a_duplicate_when_synced(
    owner_client, shop, sugar, tracked_sugar
):
    owner_client.post(
        f"/api/v1/shops/{shop.pk}/purchase-receipts/",
        {"idempotency_key": str(uuid4()), **receipt(sugar)["payload"]},
        format="json",
    )
    key = uuid4()
    body = sale(tracked_sugar, sugar, "1", key)["payload"]
    body.pop("sold_at")  # let the server time-stamp it on the REST path
    rest = owner_client.post(
        f"/api/v1/shops/{shop.pk}/sales/", {"idempotency_key": str(key), **body}, format="json"
    )
    assert rest.status_code == 201

    resp = post(owner_client, shop, [op("sale", body, key)])
    assert statuses(resp) == ["duplicate"]
    assert Sale.objects.count() == 1


def test_staff_cannot_sync_management_operations(staff_user, shop, sugar, tracked_sugar):
    client = make_client(staff_user)
    adjust = op(
        "stock_adjustment",
        {"shop_product_id": str(tracked_sugar.pk), "quantity_base_delta": "5", "reason": "found"},
    )
    resp = post(client, shop, [receipt(sugar), adjust])
    assert statuses(resp) == ["accepted", "rejected"]
    assert resp.json()["results"][1]["error"]["code"] == "permission_denied"


def test_opening_stock_and_reversal_over_sync(owner_client, shop, sugar, tracked_sugar):
    opening = op(
        "opening_stock",
        {
            "shop_product_id": str(tracked_sugar.pk),
            "product_unit_id": str(sugar.kg.pk),
            "quantity": "20",
        },
    )
    assert statuses(post(owner_client, shop, [opening])) == ["accepted"]
    movement = StockMovement.objects.get()

    reverse = op("stock_reversal", {"movement_id": str(movement.pk), "reason": "wrong count"})
    assert statuses(post(owner_client, shop, [reverse])) == ["accepted"]
    tracked_sugar.refresh_from_db()
    assert tracked_sugar.quantity_base == D("0")


def test_a_missing_target_id_is_rejected(owner_client, shop):
    resp = post(owner_client, shop, [op("opening_stock", {"quantity": "1"})])
    assert statuses(resp) == ["rejected"]


def test_non_members_get_404(other_user, shop, sugar):
    assert post(make_client(other_user), shop, [receipt(sugar)]).status_code == 404


@pytest.mark.parametrize("operations", [[], None])
def test_empty_or_missing_operations_are_a_400(owner_client, shop, operations):
    body = {} if operations is None else {"operations": operations}
    resp = owner_client.post(f"/api/v1/shops/{shop.pk}/sync/", body, format="json")
    assert resp.status_code == 400


def test_batches_are_capped_at_100_operations(owner_client, shop, sugar):
    resp = post(owner_client, shop, [receipt(sugar) for _ in range(101)])
    assert resp.status_code == 400
