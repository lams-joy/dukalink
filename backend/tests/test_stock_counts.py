from decimal import Decimal
from uuid import uuid4

import pytest

from apps.inventory import services
from apps.inventory.models import MovementType, StockCount

from .conftest import make_client

pytestmark = pytest.mark.django_db

D = Decimal


def base(shop):
    return f"/api/v1/shops/{shop.pk}/stock-counts/"


def key():
    return {"idempotency_key": str(uuid4())}


def stock_in(shop, user, sugar, sacks="1"):
    services.record_purchase_receipt(
        shop=shop, user=user,
        items=[{"product_id": sugar.product.pk, "product_unit_id": sugar.sack.pk,
                "quantity": D(sacks), "unit_cost": D("7000.00")}],
    )  # fmt: skip


def start(client, shop, **extra):
    resp = client.post(base(shop), {**key(), **extra}, format="json")
    assert resp.status_code == 201, resp.content
    return resp.json()


def record(client, shop, count_id, tracked, sugar, quantity, unit="kg"):
    unit_id = (sugar.kg if unit == "kg" else sugar.sack).pk
    resp = client.put(
        f"{base(shop)}{count_id}/items/",
        {**key(), "items": [{"shop_product_id": str(tracked.pk), "product_unit_id": str(unit_id),
                             "quantity": quantity}]},
        format="json",
    )  # fmt: skip
    return resp


def act(client, shop, count_id, action, **extra):
    return client.post(f"{base(shop)}{count_id}/{action}/", {**key(), **extra}, format="json")


def balance(tracked):
    tracked.refresh_from_db()
    return tracked.quantity_base


# ------------------------------------------------------------------ happy path
def test_full_count_applies_the_variance_only_on_approval(owner_client, shop, owner, sugar, tracked_sugar):
    stock_in(shop, owner, sugar)  # ledger says 50 kg
    count = start(owner_client, shop)
    assert count["status"] == "in_progress"
    assert count["total_items"] == 1 and count["counted_items"] == 0

    assert record(owner_client, shop, count["id"], tracked_sugar, sugar, "46.5").status_code == 201
    assert act(owner_client, shop, count["id"], "submit").json()["status"] == "submitted"
    assert balance(tracked_sugar) == D("50")  # untouched until approved

    approved = act(owner_client, shop, count["id"], "approve")
    assert approved.status_code == 201, approved.content
    body = approved.json()
    assert body["status"] == "approved"
    item = body["items"][0]
    assert D(item["expected_quantity_base"]) == D("50")
    assert D(item["counted_quantity_base"]) == D("46.5")
    assert D(item["variance_base"]) == D("-3.5")
    assert balance(tracked_sugar) == D("46.5")

    movement = tracked_sugar.movements.get(movement_type=MovementType.ADJUSTMENT)
    assert movement.quantity_base_delta == D("-3.5")
    assert movement.reference_type == "stock_count"
    assert str(movement.reference_id) == body["id"]
    assert item["adjustment_movement_id"] == str(movement.pk)


def test_counting_in_a_larger_unit_converts_to_base(owner_client, shop, owner, sugar, tracked_sugar):
    stock_in(shop, owner, sugar, "2")  # 100 kg
    count = start(owner_client, shop)
    record(owner_client, shop, count["id"], tracked_sugar, sugar, "1", unit="sack")  # 50 kg
    item = owner_client.get(f"{base(shop)}{count['id']}/").json()["items"][0]
    assert D(item["counted_quantity_base"]) == D("50")
    assert D(item["variance_base"]) == D("-50")


def test_zero_variance_writes_no_movement(owner_client, shop, owner, sugar, tracked_sugar):
    stock_in(shop, owner, sugar)
    count = start(owner_client, shop)
    record(owner_client, shop, count["id"], tracked_sugar, sugar, "50")
    act(owner_client, shop, count["id"], "submit")
    assert act(owner_client, shop, count["id"], "approve").status_code == 201
    assert not tracked_sugar.movements.filter(movement_type=MovementType.ADJUSTMENT).exists()


def test_counting_zero_is_allowed(owner_client, shop, owner, sugar, tracked_sugar):
    stock_in(shop, owner, sugar)
    count = start(owner_client, shop)
    assert record(owner_client, shop, count["id"], tracked_sugar, sugar, "0").status_code == 201
    act(owner_client, shop, count["id"], "submit")
    act(owner_client, shop, count["id"], "approve")
    assert balance(tracked_sugar) == D("0")


def test_sales_while_counting_are_preserved(owner_client, shop, owner, sugar, tracked_sugar):
    """Expected is snapshotted at entry and the variance is applied as a delta."""
    stock_in(shop, owner, sugar)  # 50
    count = start(owner_client, shop)
    record(owner_client, shop, count["id"], tracked_sugar, sugar, "48")  # expected 50, variance -2
    services.record_sale(
        shop=shop, user=owner,
        items=[{"shop_product_id": tracked_sugar.pk, "product_unit_id": sugar.kg.pk,
                "quantity": D("10"), "unit_price": D("180.00")}],
    )  # fmt: skip
    act(owner_client, shop, count["id"], "submit")
    act(owner_client, shop, count["id"], "approve")
    assert balance(tracked_sugar) == D("38")  # 50 - 10 sold - 2 variance


def test_recounting_a_product_resnapshots_expected(owner_client, shop, owner, sugar, tracked_sugar):
    stock_in(shop, owner, sugar)
    count = start(owner_client, shop)
    record(owner_client, shop, count["id"], tracked_sugar, sugar, "40")
    services.record_adjustment(
        shop=shop, user=owner, shop_product_id=tracked_sugar.pk, delta_base=D("-5"), reason="spill"
    )
    record(owner_client, shop, count["id"], tracked_sugar, sugar, "44")  # expected is now 45
    item = owner_client.get(f"{base(shop)}{count['id']}/").json()["items"][0]
    assert D(item["expected_quantity_base"]) == D("45")
    assert D(item["variance_base"]) == D("-1")


def test_start_can_limit_the_products(owner_client, shop, owner, sugar, flour, tracked_sugar):
    services.track_product(shop=shop, product_id=flour.product.pk)
    count = start(owner_client, shop, shop_product_ids=[str(tracked_sugar.pk)])
    assert count["total_items"] == 1
    assert count["items"][0]["product_name"] == "Sugar"


# ------------------------------------------------------------------ rules
def test_only_one_open_count_per_shop(owner_client, shop, tracked_sugar):
    start(owner_client, shop)
    again = owner_client.post(base(shop), key(), format="json")
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "state_conflict"


def test_a_new_count_is_allowed_after_the_last_one_closes(owner_client, shop, tracked_sugar):
    first = start(owner_client, shop)
    assert act(owner_client, shop, first["id"], "cancel", reason="wrong shelf").status_code == 201
    assert start(owner_client, shop)["status"] == "in_progress"


def test_cancel_leaves_stock_alone_and_records_why(owner_client, shop, owner, sugar, tracked_sugar):
    stock_in(shop, owner, sugar)
    count = start(owner_client, shop)
    record(owner_client, shop, count["id"], tracked_sugar, sugar, "10")
    act(owner_client, shop, count["id"], "submit")
    body = act(owner_client, shop, count["id"], "cancel", reason="counted the wrong shelf").json()
    assert body["status"] == "cancelled"
    assert body["resolution_note"] == "counted the wrong shelf"
    assert balance(tracked_sugar) == D("50")
    assert act(owner_client, shop, count["id"], "approve").status_code == 409


def test_cannot_submit_with_nothing_counted(owner_client, shop, tracked_sugar):
    count = start(owner_client, shop)
    resp = act(owner_client, shop, count["id"], "submit")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "nothing_counted"


def test_cannot_approve_before_submit_or_edit_after_submit(owner_client, shop, owner, sugar, tracked_sugar):
    stock_in(shop, owner, sugar)
    count = start(owner_client, shop)
    assert act(owner_client, shop, count["id"], "approve").status_code == 409
    record(owner_client, shop, count["id"], tracked_sugar, sugar, "49")
    act(owner_client, shop, count["id"], "submit")
    assert record(owner_client, shop, count["id"], tracked_sugar, sugar, "1").status_code == 409


def test_cannot_approve_twice(owner_client, shop, owner, sugar, tracked_sugar):
    stock_in(shop, owner, sugar)
    count = start(owner_client, shop)
    record(owner_client, shop, count["id"], tracked_sugar, sugar, "49")
    act(owner_client, shop, count["id"], "submit")
    assert act(owner_client, shop, count["id"], "approve").status_code == 201
    assert act(owner_client, shop, count["id"], "approve").status_code == 409
    assert balance(tracked_sugar) == D("49")


def test_uncounted_products_are_left_alone(owner_client, shop, owner, sugar, flour, tracked_sugar):
    tracked_flour = services.track_product(shop=shop, product_id=flour.product.pk)
    stock_in(shop, owner, sugar)
    services.record_opening_stock(
        shop=shop, user=owner, shop_product_id=tracked_flour.pk, unit_id=flour.kg.pk, quantity=D("20")
    )
    count = start(owner_client, shop)
    assert count["total_items"] == 2
    record(owner_client, shop, count["id"], tracked_sugar, sugar, "49")
    act(owner_client, shop, count["id"], "submit")
    body = act(owner_client, shop, count["id"], "approve").json()
    assert body["counted_items"] == 1
    assert balance(tracked_flour) == D("20")


def test_approval_that_would_go_negative_rolls_back_entirely(
    owner_client, shop, owner, sugar, flour, tracked_sugar
):
    tracked_flour = services.track_product(shop=shop, product_id=flour.product.pk)
    stock_in(shop, owner, sugar)  # 50
    services.record_opening_stock(
        shop=shop, user=owner, shop_product_id=tracked_flour.pk, unit_id=flour.kg.pk, quantity=D("20")
    )
    count = start(owner_client, shop)
    record(owner_client, shop, count["id"], tracked_sugar, sugar, "100")  # +50
    owner_client.put(
        f"{base(shop)}{count['id']}/items/",
        {**key(), "items": [{"shop_product_id": str(tracked_flour.pk),
                             "product_unit_id": str(flour.kg.pk), "quantity": "15"}]},
        format="json",
    )  # fmt: skip  # -5
    services.record_sale(  # now flour can no longer absorb the -5 variance
        shop=shop, user=owner,
        items=[{"shop_product_id": tracked_flour.pk, "product_unit_id": flour.kg.pk,
                "quantity": D("18"), "unit_price": D("100.00")}],
    )  # fmt: skip
    act(owner_client, shop, count["id"], "submit")
    resp = act(owner_client, shop, count["id"], "approve")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "insufficient_stock"
    assert balance(tracked_sugar) == D("50")  # sugar's +50 was rolled back too
    assert StockCount.objects.get(pk=count["id"]).status == "submitted"


def test_negative_or_over_precise_counts_are_rejected(owner_client, shop, owner, sugar, tracked_sugar):
    count = start(owner_client, shop)
    assert record(owner_client, shop, count["id"], tracked_sugar, sugar, "-1").status_code == 400
    assert record(owner_client, shop, count["id"], tracked_sugar, sugar, "1.0000001").status_code == 400


def test_product_outside_the_count_is_rejected(owner_client, shop, sugar, flour, tracked_sugar):
    tracked_flour = services.track_product(shop=shop, product_id=flour.product.pk)
    count = start(owner_client, shop, shop_product_ids=[str(tracked_sugar.pk)])
    resp = owner_client.put(
        f"{base(shop)}{count['id']}/items/",
        {**key(), "items": [{"shop_product_id": str(tracked_flour.pk),
                             "product_unit_id": str(flour.kg.pk), "quantity": "1"}]},
        format="json",
    )  # fmt: skip
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "product_not_in_count"


# ------------------------------------------------------------------ idempotency
def test_start_and_approve_are_idempotent(owner_client, shop, owner, sugar, tracked_sugar):
    stock_in(shop, owner, sugar)
    start_body = {**key()}
    first = owner_client.post(base(shop), start_body, format="json")
    replay = owner_client.post(base(shop), start_body, format="json")
    assert replay["Idempotent-Replayed"] == "true"
    assert replay.json()["id"] == first.json()["id"]
    assert StockCount.objects.filter(shop=shop).count() == 1

    cid = first.json()["id"]
    record(owner_client, shop, cid, tracked_sugar, sugar, "40")
    act(owner_client, shop, cid, "submit")
    approve_body = key()
    a1 = owner_client.post(f"{base(shop)}{cid}/approve/", approve_body, format="json")
    a2 = owner_client.post(f"{base(shop)}{cid}/approve/", approve_body, format="json")
    assert a1.status_code == 201 and a2["Idempotent-Replayed"] == "true"
    assert balance(tracked_sugar) == D("40")  # applied once


# ------------------------------------------------------------------ permissions and scoping
def test_staff_can_count_and_submit_but_not_approve_or_cancel(
    owner_client, staff_user, shop, owner, sugar, tracked_sugar
):
    stock_in(shop, owner, sugar)
    staff = make_client(staff_user)
    count = start(staff, shop)
    assert record(staff, shop, count["id"], tracked_sugar, sugar, "49").status_code == 201
    assert act(staff, shop, count["id"], "submit").status_code == 201
    assert act(staff, shop, count["id"], "approve").status_code == 403
    assert act(staff, shop, count["id"], "cancel", reason="x").status_code == 403
    assert balance(tracked_sugar) == D("50")
    assert staff.get(f"{base(shop)}{count['id']}/").status_code == 200  # may read


def test_counts_are_shop_scoped(other_user, other_shop, owner_client, shop, tracked_sugar):
    count = start(owner_client, shop)
    stranger = make_client(other_user)
    assert stranger.get(base(shop)).status_code == 404
    assert stranger.get(f"{base(shop)}{count['id']}/").status_code == 404
    # a member of another shop cannot reach this count through their own shop's URL
    assert stranger.get(f"{base(other_shop)}{count['id']}/").status_code == 404
    assert act(stranger, other_shop, count["id"], "submit").status_code == 400


def test_list_filters_by_status(owner_client, shop, tracked_sugar):
    first = start(owner_client, shop)
    act(owner_client, shop, first["id"], "cancel", reason="redo")
    start(owner_client, shop)
    assert owner_client.get(base(shop)).json()["count"] == 2
    cancelled = owner_client.get(f"{base(shop)}?status=cancelled").json()
    assert cancelled["count"] == 1 and cancelled["results"][0]["id"] == first["id"]
