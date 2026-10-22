from decimal import Decimal
from uuid import uuid4

import pytest
from django.db import transaction

from apps.audit.models import AppendOnlyError, AuditEvent
from apps.inventory import services
from apps.inventory.models import MovementType

from .conftest import make_client

pytestmark = pytest.mark.django_db

D = Decimal


def events(shop, action=None):
    qs = AuditEvent.objects.filter(shop=shop)
    return qs.filter(action=action) if action else qs


def feed(client, shop, **params):
    resp = client.get(f"/api/v1/shops/{shop.pk}/audit-events/", params)
    assert resp.status_code == 200, resp.content
    return resp.json()["results"]


def stock_in(shop, user, sugar, sacks="1"):
    services.record_purchase_receipt(
        shop=shop, user=user,
        items=[{"product_id": sugar.product.pk, "product_unit_id": sugar.sack.pk,
                "quantity": D(sacks)}],
    )  # fmt: skip


# ------------------------------------------------------------------ shop events
def test_shop_creation_is_audited(shop, owner):
    event = events(shop, "shop.created").get()
    assert event.actor == owner and event.object_id == str(shop.pk)


def test_shop_update_records_only_what_changed(owner_client, shop, owner):
    resp = owner_client.patch(
        f"/api/v1/shops/{shop.pk}/",
        {"name": "Amina Mini-Mart", "timezone": shop.timezone},
        format="json",
    )
    assert resp.status_code == 200
    event = events(shop, "shop.updated").get()
    assert event.actor == owner
    assert event.changes == {
        "before": {"name": "Amina Duka"}, "after": {"name": "Amina Mini-Mart"}
    }


def test_a_no_op_update_writes_no_event(owner_client, shop):
    owner_client.patch(f"/api/v1/shops/{shop.pk}/", {"name": shop.name}, format="json")
    assert not events(shop, "shop.updated").exists()


def test_member_added_is_audited_without_phone_or_name(owner_client, shop, other_user):
    resp = owner_client.post(
        f"/api/v1/shops/{shop.pk}/members/",
        {"phone_number": other_user.phone_number, "role": "staff"},
        format="json",
    )
    assert resp.status_code == 201
    event = events(shop, "shop.member_added").get()
    assert event.changes["after"]["role"] == "staff"
    assert event.changes["after"]["user_id"] == str(other_user.pk)
    blob = str(event.changes) + event.action
    assert other_user.phone_number not in blob and other_user.full_name not in blob


def test_onboarding_completion_is_audited_once(owner_client, shop, tracked_sugar):
    url = f"/api/v1/shops/{shop.pk}/onboarding/complete/"
    assert owner_client.post(url).status_code == 200
    assert owner_client.post(url).status_code == 200
    assert events(shop, "shop.onboarding_completed").count() == 1


# ------------------------------------------------------------------ stock events
def test_tracking_and_settings_changes_are_audited(owner_client, shop, owner, sugar):
    resp = owner_client.post(
        f"/api/v1/shops/{shop.pk}/inventory/",
        {"product_id": str(sugar.product.pk), "reorder_level_base": "10"},
        format="json",
    )
    assert resp.status_code == 201
    item_id = resp.json()["id"]
    tracked = events(shop, "product.tracked").get()
    assert tracked.actor == owner and tracked.object_id == item_id

    owner_client.patch(
        f"/api/v1/shops/{shop.pk}/inventory/{item_id}/settings/",
        {"reorder_level_base": "20"},
        format="json",
    )
    changed = events(shop, "product.settings_updated").get()
    assert changed.changes == {
        "before": {"reorder_level_base": "10"}, "after": {"reorder_level_base": "20"}
    }


def test_adjustment_is_audited_with_balances_and_reason(
    owner_client, shop, owner, sugar, tracked_sugar
):
    stock_in(shop, owner, sugar)
    resp = owner_client.post(
        f"/api/v1/shops/{shop.pk}/stock-adjustments/",
        {"idempotency_key": str(uuid4()), "shop_product_id": str(tracked_sugar.pk),
         "quantity_base_delta": "-2", "reason": "spillage"},
        format="json",
    )  # fmt: skip
    assert resp.status_code == 201, resp.content
    event = events(shop, "stock.adjustment").get()
    assert event.actor == owner and event.object_id == resp.json()["id"]
    assert event.changes["reason"] == "spillage"
    assert event.changes["before"] == {"quantity_base": "50"}
    assert event.changes["after"] == {"quantity_base": "48"}


def test_reversal_is_audited(owner_client, shop, owner, sugar, tracked_sugar):
    stock_in(shop, owner, sugar)
    original = tracked_sugar.movements.get(movement_type=MovementType.PURCHASE_RECEIPT)
    resp = owner_client.post(
        f"/api/v1/shops/{shop.pk}/stock-movements/{original.pk}/reverse/",
        {"idempotency_key": str(uuid4()), "reason": "wrong shop"},
        format="json",
    )
    assert resp.status_code == 201, resp.content
    event = events(shop, "stock.reversal").get()
    assert event.changes["reverses_movement_id"] == str(original.pk)
    assert event.changes["reason"] == "wrong shop"


def test_stock_count_approval_and_cancellation_are_audited(
    owner_client, shop, owner, sugar, tracked_sugar
):
    stock_in(shop, owner, sugar)
    base = f"/api/v1/shops/{shop.pk}/stock-counts/"
    key = lambda: {"idempotency_key": str(uuid4())}  # noqa: E731

    count = owner_client.post(base, key(), format="json").json()
    owner_client.put(
        f"{base}{count['id']}/items/",
        {**key(), "items": [{"shop_product_id": str(tracked_sugar.pk),
                             "product_unit_id": str(sugar.kg.pk), "quantity": "46.5"}]},
        format="json",
    )  # fmt: skip
    owner_client.post(f"{base}{count['id']}/submit/", key(), format="json")
    assert owner_client.post(f"{base}{count['id']}/approve/", key(), format="json").status_code == 201
    approved = events(shop, "stock_count.approved").get()
    assert approved.object_id == count["id"]
    [line] = approved.changes["adjustments"]
    assert line["variance_base"] == "-3.5" and line["expected_base"] == "50"

    second = owner_client.post(base, key(), format="json").json()
    owner_client.post(
        f"{base}{second['id']}/cancel/", {**key(), "reason": "miscounted"}, format="json"
    )
    assert events(shop, "stock_count.cancelled").get().changes == {"reason": "miscounted"}


def test_custom_product_events(owner_client, shop, owner):
    resp = owner_client.post(
        f"/api/v1/shops/{shop.pk}/products/",
        {"idempotency_key": str(uuid4()), "name": "Mandazi mix", "base_unit": "kg",
         "units": [{"unit_name": "2 kg packet", "base_quantity": "2"}]},
        format="json",
    )  # fmt: skip
    assert resp.status_code == 201, resp.content
    created = events(shop, "custom_product.created").get()
    assert created.actor == owner and created.changes["after"]["extra_units"] == ["2 kg packet"]
    assert events(shop, "product.tracked").count() == 1  # tracked in the same call

    owner_client.post(
        f"/api/v1/shops/{shop.pk}/products/{resp.json()['id']}/units/",
        {"idempotency_key": str(uuid4()), "unit_name": "carton", "base_quantity": "24"},
        format="json",
    )
    assert events(shop, "custom_product.unit_added").get().changes["after"]["unit_name"] == "carton"


# ------------------------------------------------------------------ correctness
def test_idempotent_replay_does_not_duplicate_the_event(
    owner_client, shop, owner, sugar, tracked_sugar
):
    stock_in(shop, owner, sugar)
    payload = {"idempotency_key": str(uuid4()), "shop_product_id": str(tracked_sugar.pk),
               "quantity_base_delta": "-1", "reason": "spillage"}  # fmt: skip
    url = f"/api/v1/shops/{shop.pk}/stock-adjustments/"
    assert owner_client.post(url, payload, format="json").status_code == 201
    replay = owner_client.post(url, payload, format="json")
    assert replay["Idempotent-Replayed"] == "true"
    assert events(shop, "stock.adjustment").count() == 1


def test_a_failed_operation_leaves_no_event(owner, shop, sugar, tracked_sugar):
    with pytest.raises(Exception):  # noqa: B017 - InsufficientStock, nothing in stock
        services.record_adjustment(
            shop=shop, user=owner, shop_product_id=tracked_sugar.pk,
            delta_base=D("-5"), reason="oops",
        )  # fmt: skip
    assert not events(shop, "stock.adjustment").exists()


def test_event_rolls_back_with_the_change(shop, owner, sugar):
    class Boom(Exception):
        pass

    with pytest.raises(Boom), transaction.atomic():
        services.track_product(shop=shop, product_id=sugar.product.pk, actor=owner)
        raise Boom
    assert not events(shop, "product.tracked").exists()


def test_events_carry_the_request_id(owner_client, shop):
    resp = owner_client.patch(
        f"/api/v1/shops/{shop.pk}/", {"name": "New name"}, format="json",
        headers={"X-Request-ID": "req-abc-123"},
    )  # fmt: skip
    assert resp.status_code == 200
    assert events(shop, "shop.updated").get().request_id == "req-abc-123"


def test_sensitive_keys_are_scrubbed(shop, owner):
    from apps.audit import services as audit

    event = audit.record(
        action="test.scrub", obj_type="x", obj_id=1, actor=owner, shop=shop,
        changes={"after": {"phone_number": "0712345678", "password": "x", "qty": 3}},
    )  # fmt: skip
    assert event.changes == {"after": {"qty": 3}}


# ------------------------------------------------------------------ append-only
def test_events_cannot_be_edited_or_deleted(shop):
    event = events(shop, "shop.created").get()
    event.action = "tampered"
    with pytest.raises(AppendOnlyError):
        event.save()
    with pytest.raises(AppendOnlyError):
        event.delete()
    with pytest.raises(AppendOnlyError):
        AuditEvent.objects.filter(pk=event.pk).update(action="tampered")
    with pytest.raises(AppendOnlyError):
        AuditEvent.objects.filter(pk=event.pk).delete()
    assert events(shop, "shop.created").count() == 1


# ------------------------------------------------------------------ read API & isolation
def test_owner_and_manager_can_read_but_staff_cannot(
    owner_client, shop, staff_user, other_user
):
    assert len(feed(owner_client, shop)) >= 1
    staff = make_client(staff_user)
    assert staff.get(f"/api/v1/shops/{shop.pk}/audit-events/").status_code == 403


def test_other_shops_events_are_not_readable_or_listed(
    owner_client, shop, other_shop, other_user
):
    outsider = make_client(other_user)
    assert outsider.get(f"/api/v1/shops/{shop.pk}/audit-events/").status_code == 404
    mine = {e["id"] for e in feed(owner_client, shop)}
    theirs = set(map(str, events(other_shop).values_list("id", flat=True)))
    assert theirs and not (mine & theirs)


def test_feed_filters_and_orders_newest_first(owner_client, shop, tracked_sugar):
    owner_client.patch(f"/api/v1/shops/{shop.pk}/", {"name": "B"}, format="json")
    owner_client.patch(f"/api/v1/shops/{shop.pk}/", {"name": "C"}, format="json")
    updates = feed(owner_client, shop, action="shop.updated")
    assert [e["changes"]["after"]["name"] for e in updates] == ["C", "B"]
    assert all(e["action"] == "shop.updated" for e in updates)
    assert feed(owner_client, shop, object_type="shop_product")[0]["action"] == "product.tracked"
    assert feed(owner_client, shop, actor_id="not-a-uuid") == []


def test_unauthenticated_cannot_read(shop):
    from rest_framework.test import APIClient

    resp = APIClient().get(f"/api/v1/shops/{shop.pk}/audit-events/")
    assert resp.status_code == 401
