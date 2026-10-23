"""Group buying, chunk 5a: creating groups, joining, changing, withdrawing, cancelling."""

from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from django.utils import timezone

from apps.accounts.models import User
from apps.audit.models import AuditEvent
from apps.groupbuying import services
from apps.groupbuying.models import GroupOrder, GroupParticipant
from apps.shops import services as shop_services
from apps.shops.models import ShopMembership
from apps.suppliers import services as supplier_services

from .conftest import PASSWORD, make_client

pytestmark = pytest.mark.django_db

D = Decimal


# ------------------------------------------------------------------ fixtures & helpers
def G(shop, suffix=""):
    return f"/api/v1/shops/{shop.pk}/group-orders/{suffix}"


def deadline(days=3):
    return (timezone.now() + timedelta(days=days)).isoformat()


def create_body(offer, **extra):
    return {
        "idempotency_key": str(uuid4()),
        "offer_id": str(offer.pk),
        "target_quantity": "10",
        "quantity": "4",
        "deadline": deadline(),
        "delivery_method": "collection",
        "delivery_point": "Kondele market stage",
        "estimated_delivery_fee": "1500",
        **extra,
    }


def make_group(client, shop, offer, **extra):
    resp = client.post(G(shop), create_body(offer, **extra), format="json")
    assert resp.status_code == 201, resp.content
    return resp.json()


def join(client, shop, group, quantity="3", key=None):
    body = {"idempotency_key": key or str(uuid4()), "quantity": str(quantity)}
    return client.post(G(shop, f"{group['id']}/join/"), body, format="json")


def change(client, shop, group, quantity):
    body = {"idempotency_key": str(uuid4()), "quantity": str(quantity)}
    return client.patch(G(shop, f"{group['id']}/my-commitment/"), body, format="json")


def withdraw(client, shop, group):
    body = {"idempotency_key": str(uuid4())}
    return client.post(G(shop, f"{group['id']}/withdraw/"), body, format="json")


def detail(client, shop, group):
    return client.get(G(shop, f"{group['id']}/"))


def assert_reconciled(group_id):
    group = GroupOrder.objects.get(pk=group_id)
    expected = services.reconcile(group)
    assert group.committed_quantity == expected["committed_quantity"]
    assert group.committed_quantity_base == expected["committed_quantity_base"]
    assert group.participant_count == expected["participant_count"]


# ------------------------------------------------------------------ creating
def test_creating_a_group_commits_the_organiser_and_snapshots_the_terms(
    owner_client, owner, shop, verified, offer
):
    group = make_group(owner_client, shop, offer)
    assert group["status"] == "open" and group["binding"] is False
    assert group["product_name"] == "Sugar" and group["unit_name"] == "50 kg sack"
    assert group["unit_base_quantity"] == "50.000000" and group["currency"] == "KES"
    assert group["list_price"] == "7000.00" and group["minimum_per_shop"] == "2.000000"
    assert group["target_quantity"] == "10.000000" and group["committed_quantity"] == "4.000000"
    assert group["committed_quantity_base"] == "200.000000" and group["participant_count"] == 1
    assert group["progress"] == "0.4000" and group["is_organiser"] is True
    assert group["delivery_method"] == "collection"
    assert group["delivery_point"] == "Kondele market stage"
    assert group["estimated_delivery_fee"] == "1500.00"
    assert group["my_commitment"]["quantity"] == "4.000000"
    assert group["wholesaler"]["business_name"] == "Kisumu Wholesale"

    event = AuditEvent.objects.get(action="group.created")
    assert event.shop == shop and event.wholesaler == verified and event.actor == owner
    assert_reconciled(group["id"])


def test_the_estimated_price_follows_the_volume_tier(
    owner_client, other_client, shop, other_shop, offer
):
    group = make_group(owner_client, shop, offer)
    assert group["estimated_unit_price"] == "7000.00"  # 4 sacks: no tier yet
    assert group["unit_price_at_target"] == "6800.00"  # the target of 10 reaches the tier
    assert join(other_client, other_shop, group, "6").status_code == 200
    assert detail(owner_client, shop, group).json()["estimated_unit_price"] == "6800.00"


def test_a_repeated_create_returns_the_same_group(owner_client, shop, offer):
    body = create_body(offer)
    first = owner_client.post(G(shop), body, format="json")
    again = owner_client.post(G(shop), body, format="json")
    assert first.status_code == again.status_code == 201
    assert again["Idempotent-Replayed"] == "true" and again.json()["id"] == first.json()["id"]
    assert GroupOrder.objects.count() == 1 and GroupParticipant.objects.count() == 1


def test_the_same_key_with_another_payload_is_a_conflict(owner_client, shop, offer):
    body = create_body(offer)
    assert owner_client.post(G(shop), body, format="json").status_code == 201
    clash = owner_client.post(G(shop), {**body, "target_quantity": "20"}, format="json")
    assert clash.status_code == 409 and clash.json()["error"]["code"] == "idempotency_conflict"


@pytest.mark.parametrize(
    ("days", "code"),
    [(0.01, "invalid_deadline"), (45, "invalid_deadline")],
)
def test_the_deadline_must_be_in_range(owner_client, shop, offer, days, code):
    resp = owner_client.post(G(shop), create_body(offer, deadline=deadline(days)), format="json")
    assert resp.status_code == 400 and resp.json()["error"]["code"] == code


@pytest.mark.parametrize(
    ("extra", "code"),
    [
        ({"target_quantity": "1"}, "invalid_target"),  # below the offer's minimum order
        ({"target_quantity": "50"}, "exceeds_availability"),  # only 40 available
        ({"quantity": "1"}, "below_minimum"),
        ({"quantity": "41", "target_quantity": "40"}, "exceeds_availability"),
        ({"quantity": "2.0000001"}, "validation_error"),
        ({"delivery_point": "   "}, "validation_error"),
        ({"offer_id": str(uuid4())}, "offer_not_found"),
    ],
)
def test_invalid_groups_are_rejected(owner_client, shop, offer, extra, code):
    resp = owner_client.post(G(shop), create_body(offer, **extra), format="json")
    assert resp.status_code == 400, resp.content
    assert resp.json()["error"]["code"] == code
    assert not GroupOrder.objects.exists()


def test_an_offer_that_is_not_live_cannot_be_grouped(
    owner_client, shop, verified, seller, offer
):
    supplier_services.update_offer(
        wholesaler=verified, offer_id=offer.pk, actor=seller, values={"is_active": False}
    )
    resp = owner_client.post(G(shop), create_body(offer), format="json")
    assert resp.status_code == 400 and resp.json()["error"]["code"] == "offer_not_found"


def test_a_person_cannot_group_buy_from_their_own_wholesaler(seller, seller_client, offer):
    own_shop = shop_services.create_shop(seller, name="Seller's own duka")
    resp = seller_client.post(G(own_shop), create_body(offer), format="json")
    assert resp.status_code == 400 and resp.json()["error"]["code"] == "self_order"


def test_staff_can_view_but_not_create_or_join(
    owner_client, staff_user, shop, other_client, other_shop, offer
):
    staff = make_client(staff_user)
    assert staff.post(G(shop), create_body(offer), format="json").status_code == 403
    group = make_group(owner_client, shop, offer)
    assert staff.get(G(shop, f"{group['id']}/")).status_code == 200
    assert staff.get(G(shop)).status_code == 200
    assert join(staff, shop, group).status_code == 403


def test_a_stranger_cannot_use_another_shops_group_endpoints(other_client, shop, offer):
    assert other_client.get(G(shop)).status_code == 404
    assert other_client.post(G(shop), create_body(offer), format="json").status_code == 404


# ------------------------------------------------------------------ joining
def test_other_shops_can_join_and_see_totals_but_not_each_other(
    owner_client, other_client, third_client, shop, other_shop, third_shop, offer
):
    group = make_group(owner_client, shop, offer)
    resp = join(other_client, other_shop, group, "3")
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["committed_quantity"] == "7.000000" and body["participant_count"] == 2
    assert body["is_organiser"] is False and body["binding"] is False
    assert body["my_commitment"]["quantity"] == "3.000000"

    third_view = detail(third_client, third_shop, group).json()
    assert third_view["my_commitment"] is None and third_view["participant_count"] == 2
    text = str(third_view) + str(body)
    assert "Brian Duka" not in text and "Amina Duka" not in text
    assert_reconciled(group["id"])


def test_a_shop_cannot_join_twice(owner_client, other_client, shop, other_shop, offer):
    group = make_group(owner_client, shop, offer)
    assert join(other_client, other_shop, group).status_code == 200
    again = join(other_client, other_shop, group, "5")
    assert again.status_code == 409 and again.json()["error"]["code"] == "already_joined"
    assert detail(owner_client, shop, group).json()["committed_quantity"] == "7.000000"


def test_a_replayed_join_is_applied_once(owner_client, other_client, shop, other_shop, offer):
    group = make_group(owner_client, shop, offer)
    key = str(uuid4())
    first = join(other_client, other_shop, group, "3", key=key)
    again = join(other_client, other_shop, group, "3", key=key)
    assert first.status_code == again.status_code == 200
    assert again["Idempotent-Replayed"] == "true"
    assert detail(owner_client, shop, group).json()["committed_quantity"] == "7.000000"
    assert AuditEvent.objects.filter(action="group.joined").count() == 1


@pytest.mark.parametrize(
    ("quantity", "code"),
    [("1", "below_minimum"), ("37", "exceeds_availability")],  # 4 already committed, 40 available
)
def test_commitments_respect_the_minimum_and_the_availability(
    owner_client, other_client, shop, other_shop, offer, quantity, code
):
    group = make_group(owner_client, shop, offer)
    resp = join(other_client, other_shop, group, quantity)
    assert resp.status_code == 400 and resp.json()["error"]["code"] == code
    assert detail(owner_client, shop, group).json()["participant_count"] == 1


def test_over_precise_quantities_are_rejected(owner_client, other_client, shop, other_shop, offer):
    group = make_group(owner_client, shop, offer)
    # 50 kg per sack, 6 decimal places of base unit: 2.0000001 sacks is not representable.
    resp = join(other_client, other_shop, group, "2.0000001")
    assert resp.status_code == 400


def test_joining_after_the_deadline_is_refused(
    owner_client, other_client, shop, other_shop, offer
):
    group = make_group(owner_client, shop, offer)
    GroupOrder.objects.filter(pk=group["id"]).update(deadline=timezone.now() - timedelta(minutes=1))
    resp = join(other_client, other_shop, group)
    assert resp.status_code == 404  # no longer open to outsiders
    mine = change(owner_client, shop, group, "5")  # a participant is told why
    assert mine.status_code == 409 and mine.json()["error"]["code"] == "group_not_open"


def test_joining_stops_when_the_offer_is_withdrawn(
    owner_client, other_client, shop, other_shop, verified, seller, offer
):
    group = make_group(owner_client, shop, offer)
    supplier_services.update_offer(
        wholesaler=verified, offer_id=offer.pk, actor=seller, values={"is_active": False}
    )
    resp = join(other_client, other_shop, group)
    assert resp.status_code == 400 and resp.json()["error"]["code"] == "offer_unavailable"
    resp = change(owner_client, shop, group, "5")
    assert resp.status_code == 400 and resp.json()["error"]["code"] == "offer_unavailable"
    assert detail(other_client, other_shop, group).status_code == 404  # gone from discovery


# ------------------------------------------------------------------ changing and leaving
def test_a_shop_can_change_its_commitment(owner_client, other_client, shop, other_shop, offer):
    group = make_group(owner_client, shop, offer)
    join(other_client, other_shop, group, "3")
    resp = change(other_client, other_shop, group, "8")
    assert resp.status_code == 200 and resp.json()["committed_quantity"] == "12.000000"
    assert resp.json()["my_commitment"]["quantity_base"] == "400.000000"
    event = AuditEvent.objects.get(action="group.commitment_changed")
    assert D(event.changes["before"]["quantity"]) == D("3")
    assert D(event.changes["after"]["quantity"]) == D("8")
    assert_reconciled(group["id"])


def test_changing_without_a_commitment_is_refused(
    owner_client, other_client, shop, other_shop, offer
):
    group = make_group(owner_client, shop, offer)
    resp = change(other_client, other_shop, group, "3")
    assert resp.status_code == 409 and resp.json()["error"]["code"] == "not_participating"


def test_withdrawing_removes_the_commitment_and_allows_rejoining(
    owner_client, other_client, shop, other_shop, offer
):
    group = make_group(owner_client, shop, offer)
    join(other_client, other_shop, group, "3")
    resp = withdraw(other_client, other_shop, group)
    assert resp.status_code == 200 and resp.json()["committed_quantity"] == "4.000000"
    assert resp.json()["participant_count"] == 1
    assert resp.json()["my_commitment"]["status"] == "withdrawn"
    assert change(other_client, other_shop, group, "3").status_code == 409

    rejoin = join(other_client, other_shop, group, "5")
    assert rejoin.status_code == 200 and rejoin.json()["committed_quantity"] == "9.000000"
    assert GroupParticipant.objects.filter(group_id=group["id"], shop=other_shop).count() == 1
    assert_reconciled(group["id"])


def test_withdrawing_twice_is_refused(owner_client, other_client, shop, other_shop, offer):
    group = make_group(owner_client, shop, offer)
    join(other_client, other_shop, group)
    assert withdraw(other_client, other_shop, group).status_code == 200
    again = withdraw(other_client, other_shop, group)
    assert again.status_code == 409 and again.json()["error"]["code"] == "not_participating"


# ------------------------------------------------------------------ cancelling
def test_only_the_organiser_can_cancel_and_it_binds_nobody(
    owner_client, other_client, shop, other_shop, offer
):
    group = make_group(owner_client, shop, offer)
    join(other_client, other_shop, group)
    denied = other_client.post(
        G(other_shop, f"{group['id']}/cancel/"), {"reason": "nope"}, format="json"
    )
    assert denied.status_code == 403

    url = G(shop, f"{group['id']}/cancel/")
    assert owner_client.post(url, {"reason": " "}, format="json").status_code == 400
    done = owner_client.post(url, {"reason": "Wholesaler changed prices"}, format="json")
    assert done.status_code == 200
    assert done.json()["status"] == "cancelled" and done.json()["binding"] is False
    assert done.json()["status_note"] == "Wholesaler changed prices"
    assert AuditEvent.objects.get(action="group.cancelled").shop == shop

    # a participant is told why they cannot act any more; the commitment is left as it was
    assert change(other_client, other_shop, group, "5").status_code == 409
    assert withdraw(other_client, other_shop, group).status_code == 409
    assert owner_client.post(url, {"reason": "again"}, format="json").status_code == 409
    assert_reconciled(group["id"])


# ------------------------------------------------------------------ discovery
def test_listing_shows_open_groups_and_my_groups(
    owner_client, other_client, third_client, shop, other_shop, third_shop, offer
):
    group = make_group(owner_client, shop, offer)
    listed = third_client.get(G(third_shop)).json()["results"]
    assert [g["id"] for g in listed] == [group["id"]]
    assert third_client.get(G(third_shop) + "?mine=true").json()["results"] == []
    assert [g["id"] for g in owner_client.get(G(shop) + "?mine=true").json()["results"]] == [
        group["id"]
    ]
    assert third_client.get(G(third_shop) + f"?product={uuid4()}").json()["results"] == []

    owner_client.post(G(shop, f"{group['id']}/cancel/"), {"reason": "x"}, format="json")
    assert third_client.get(G(third_shop)).json()["results"] == []  # closed: not discoverable
    assert detail(third_client, third_shop, group).status_code == 404
    assert detail(owner_client, shop, group).status_code == 200  # but participants still see it
    assert other_client.get(G(other_shop)).status_code == 200


def test_groups_for_a_suspended_wholesaler_disappear_from_discovery(
    owner_client, third_client, shop, third_shop, verified, admin_user, offer
):
    group = make_group(owner_client, shop, offer)
    supplier_services.suspend_wholesaler(
        wholesaler_id=verified.pk, actor=admin_user, note="complaints"
    )
    assert third_client.get(G(third_shop)).json()["results"] == []
    assert detail(third_client, third_shop, group).status_code == 404


def test_audit_events_carry_no_personal_data(
    owner_client, other_client, shop, other_shop, offer
):
    group = make_group(owner_client, shop, offer)
    join(other_client, other_shop, group)
    for event in AuditEvent.objects.filter(object_type="group_order"):
        flat = str(event.changes)
        assert "0712345678" not in flat and "Amina" not in flat


def test_a_staff_member_added_later_still_cannot_commit(
    owner_client, other_client, shop, other_shop, offer
):
    group = make_group(owner_client, shop, offer)
    extra = User.objects.create_user("0755555555", PASSWORD, full_name="New Staff")
    ShopMembership.objects.create(shop=other_shop, user=extra, role=ShopMembership.Role.STAFF)
    assert join(make_client(extra), other_shop, group).status_code == 403
