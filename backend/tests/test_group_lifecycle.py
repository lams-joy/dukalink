"""Group buying, chunk 5b: deadlines, closing, failing, and the wholesaler's confirm/decline."""

from datetime import timedelta
from decimal import Decimal
from io import StringIO

import pytest
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.groupbuying import services
from apps.groupbuying.models import GroupOrder
from apps.suppliers import services as supplier_services
from apps.suppliers.models import WholesalerMembership

from .conftest import make_client
from .test_groups import G, change, detail, join, make_group, withdraw

pytestmark = pytest.mark.django_db

D = Decimal


def W(wholesaler, suffix=""):
    return f"/api/v1/wholesalers/{wholesaler.pk}/group-orders/{suffix}"


def expire(group):
    GroupOrder.objects.filter(pk=group["id"]).update(deadline=timezone.now() - timedelta(minutes=1))


def status_of(group):
    return GroupOrder.objects.get(pk=group["id"]).status


def confirm(client, wholesaler, group, **body):
    return client.post(W(wholesaler, f"{group['id']}/confirm/"), body, format="json")


def decline(client, wholesaler, group, reason="Cannot supply that much"):
    return client.post(
        W(wholesaler, f"{group['id']}/decline/"), {"reason": reason}, format="json"
    )


@pytest.fixture
def full_group(owner_client, other_client, shop, other_shop, offer):
    """Target 10 sacks, 4 + 6 committed: the target and the 10-sack tier (6,800) are both met."""
    group = make_group(owner_client, shop, offer)
    assert join(other_client, other_shop, group, "6").status_code == 200
    return group


@pytest.fixture
def closed_group(owner_client, shop, full_group):
    resp = owner_client.post(G(shop, f"{full_group['id']}/close/"))
    assert resp.status_code == 200, resp.content
    return resp.json()


@pytest.fixture
def small_closed_group(owner_client, other_client, shop, other_shop, offer):
    """Target 5, 4 + 3 = 7 committed: closed, but below the 10-sack tier, so the base price."""
    group = make_group(owner_client, shop, offer, target_quantity="5")
    assert join(other_client, other_shop, group, "3").status_code == 200
    resp = owner_client.post(G(shop, f"{group['id']}/close/"))
    assert resp.status_code == 200, resp.content
    return resp.json()


# ------------------------------------------------------------------ the deadline
def test_an_expired_group_that_met_its_target_closes_on_read(
    owner_client, other_client, shop, other_shop, full_group
):
    expire(full_group)
    body = detail(other_client, other_shop, full_group).json()
    assert body["status"] == "closed" and body["binding"] is False
    assert body["closed_at"] is not None and body["terms"] is None
    event = AuditEvent.objects.get(action="group.closed")
    assert event.actor is None and event.shop == shop  # a system action
    assert event.changes["reason"] == "deadline"


def test_an_expired_group_below_target_fails_and_binds_nobody(
    owner_client, other_client, shop, other_shop, offer
):
    group = make_group(owner_client, shop, offer)
    join(other_client, other_shop, group, "3")  # 7 of 10
    expire(group)
    body = detail(owner_client, shop, group).json()
    assert body["status"] == "failed" and body["binding"] is False
    assert "target" in body["status_note"].lower()
    assert AuditEvent.objects.get(action="group.failed").changes["reason"] == "deadline"
    # final: nobody can act on it any more, and the wholesaler cannot confirm it
    assert change(owner_client, shop, group, "5").status_code == 409
    assert withdraw(other_client, other_shop, group).status_code == 409


def test_settling_twice_records_one_event(owner_client, shop, other_client, other_shop, full_group):
    expire(full_group)
    detail(owner_client, shop, full_group)
    detail(other_client, other_shop, full_group)
    assert services.settle_expired() == 0
    assert AuditEvent.objects.filter(action="group.closed").count() == 1


def test_a_refused_write_after_the_deadline_still_settles_the_group(
    owner_client, shop, offer
):
    group = make_group(owner_client, shop, offer)  # 4 of 10
    expire(group)
    resp = change(owner_client, shop, group, "5")
    assert resp.status_code == 409 and resp.json()["error"]["code"] == "group_not_open"
    assert status_of(group) == "failed"  # the refusal did not roll the settlement back


def test_listing_my_groups_settles_expired_ones(owner_client, shop, full_group):
    expire(full_group)
    rows = owner_client.get(G(shop) + "?mine=true").json()["results"]
    assert [r["status"] for r in rows] == ["closed"]


def test_the_command_settles_everything_that_is_due(
    owner_client, other_client, shop, other_shop, offer, full_group
):
    short = make_group(other_client, other_shop, offer, quantity="3")  # 3 of 10
    fresh = make_group(owner_client, shop, offer)  # not due
    expire(full_group)
    expire(short)

    out = StringIO()
    call_command("close_expired_groups", stdout=out)
    assert "Settled 2 expired group order(s)." in out.getvalue()
    assert status_of(full_group) == "closed" and status_of(short) == "failed"
    assert status_of(fresh) == "open"

    again = StringIO()
    call_command("close_expired_groups", stdout=again)
    assert "Settled 0" in again.getvalue()


# ------------------------------------------------------------------ closing early
def test_the_organiser_can_close_once_the_target_is_met(
    owner_client, other_client, shop, other_shop, full_group
):
    resp = owner_client.post(G(shop, f"{full_group['id']}/close/"))
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "closed" and body["binding"] is False
    assert AuditEvent.objects.get(action="group.closed").changes["reason"] == "organiser"
    # quantities are frozen: no changes, withdrawals, joins or cancellations
    assert change(other_client, other_shop, full_group, "3").status_code == 409
    assert withdraw(other_client, other_shop, full_group).status_code == 409
    cancel = owner_client.post(
        G(shop, f"{full_group['id']}/cancel/"), {"reason": "x"}, format="json"
    )
    assert cancel.status_code == 409


def test_closing_needs_the_target_and_the_organiser(
    owner_client, other_client, staff_user, shop, other_shop, offer, full_group
):
    below = make_group(owner_client, shop, offer)  # 4 of 10
    resp = owner_client.post(G(shop, f"{below['id']}/close/"))
    assert resp.status_code == 400 and resp.json()["error"]["code"] == "target_not_reached"
    assert status_of(below) == "open"

    assert other_client.post(G(other_shop, f"{full_group['id']}/close/")).status_code == 403
    staff = make_client(staff_user)
    assert staff.post(G(shop, f"{full_group['id']}/close/")).status_code == 403


def test_a_closed_group_cannot_be_closed_again(owner_client, shop, closed_group):
    assert owner_client.post(G(shop, f"{closed_group['id']}/close/")).status_code == 409


# ------------------------------------------------------------------ the wholesaler's view
def test_the_wholesaler_sees_its_groups_but_not_the_shops_in_them(
    seller_client, owner_client, shop, verified, offer, closed_group
):
    make_group(owner_client, shop, offer)  # a second one, still open
    rows = seller_client.get(W(verified)).json()["results"]
    assert len(rows) == 2
    only_closed = seller_client.get(W(verified) + "?status=closed").json()["results"]
    assert [r["id"] for r in only_closed] == [closed_group["id"]]

    body = seller_client.get(W(verified, f"{closed_group['id']}/")).json()
    assert body["participant_count"] == 2 and body["committed_quantity"] == "10.000000"
    assert body["is_organiser"] is False and body["my_commitment"] is None
    assert "participants" not in body


def test_another_wholesaler_and_strangers_cannot_see_the_group(
    rival_user, rival, other_client, verified, closed_group
):
    rival_client = make_client(rival_user)
    url = W(verified, f"{closed_group['id']}/")
    assert rival_client.get(url).status_code == 404
    assert rival_client.get(W(verified)).status_code == 404  # not a member of that wholesaler
    assert other_client.get(url).status_code == 404
    # its own list never contains someone else's group
    assert rival_client.get(W(rival)).json()["results"] == []


def test_wholesaler_staff_can_look_but_not_decide(verified, closed_group, third_user):
    WholesalerMembership.objects.create(
        wholesaler=verified, user=third_user, role=WholesalerMembership.Role.STAFF
    )
    staff = make_client(third_user)
    assert staff.get(W(verified, f"{closed_group['id']}/")).status_code == 200
    assert confirm(staff, verified, closed_group).status_code == 403
    assert decline(staff, verified, closed_group).status_code == 403
    assert status_of(closed_group) == "closed"


def test_the_wholesaler_endpoints_need_a_login(verified, closed_group):
    from rest_framework.test import APIClient

    anon = APIClient()
    assert anon.get(W(verified)).status_code == 401
    assert confirm(anon, verified, closed_group).status_code == 401


# ------------------------------------------------------------------ confirming
def test_confirming_freezes_the_tier_price_and_the_terms(
    seller_client, owner_client, other_client, shop, other_shop, seller, verified, closed_group
):
    resp = confirm(seller_client, verified, closed_group, delivery_fee="1200")
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["status"] == "confirmed" and body["binding"] is True
    assert body["confirmed_unit_price"] == "6800.00"  # the tier for 10 sacks, not the 7,000 list
    assert body["confirmed_delivery_fee"] == "1200.00" and body["confirmed_at"] is not None
    terms = body["terms"]
    assert terms["unit_price"] == "6800" and terms["quantity"] == "10"
    assert terms["quantity_base"] == "500" and terms["participant_count"] == 2
    assert terms["goods_total"] == "68000" and terms["delivery_fee"] == "1200"
    assert terms["total"] == "69200" and terms["tier_minimum_quantity"] == "10"
    assert terms["delivery_method"] == "collection"
    assert terms["delivery_point"] == "Kondele market stage"

    event = AuditEvent.objects.get(action="group.confirmed")
    assert event.actor == seller and event.wholesaler == verified and event.shop == shop
    assert event.changes["after"]["unit_price"] == "6800"

    # participants see the same frozen terms
    mine = detail(other_client, other_shop, closed_group).json()
    assert mine["binding"] is True and mine["terms"]["total"] == "69200"


def test_the_wholesaler_may_confirm_below_the_cap(seller_client, verified, closed_group):
    body = confirm(
        seller_client, verified, closed_group, unit_price="6700", delivery_fee="0"
    ).json()
    assert body["confirmed_unit_price"] == "6700.00"
    assert body["terms"]["goods_total"] == "67000" and body["terms"]["total"] == "67000"


def test_below_the_tier_the_base_price_is_the_cap(
    seller_client, verified, small_closed_group
):
    body = confirm(seller_client, verified, small_closed_group).json()
    assert body["confirmed_unit_price"] == "7000.00"  # 7 sacks: the 10-sack tier does not apply
    assert body["terms"]["tier_minimum_quantity"] is None
    assert body["terms"]["goods_total"] == "49000"


def test_the_price_cannot_exceed_the_cap(seller_client, verified, closed_group):
    for price in ("6800.01", "7000"):
        resp = confirm(seller_client, verified, closed_group, unit_price=price)
        assert resp.status_code == 400 and resp.json()["error"]["code"] == "price_above_cap"
    assert status_of(closed_group) == "closed"


def test_a_price_rise_after_creation_cannot_reach_the_shops(
    seller_client, verified, seller, offer, small_closed_group
):
    supplier_services.update_offer(
        wholesaler=verified, offer_id=offer.pk, actor=seller,
        values={"price_per_unit": D("7500")},
    )  # fmt: skip
    over = confirm(seller_client, verified, small_closed_group, unit_price="7500")
    assert over.status_code == 400 and over.json()["error"]["code"] == "price_above_cap"
    body = confirm(seller_client, verified, small_closed_group).json()
    assert body["confirmed_unit_price"] == "7000.00"  # the list price the shops saw


def test_the_delivery_fee_cannot_exceed_the_published_estimate(
    seller_client, verified, closed_group
):
    resp = confirm(seller_client, verified, closed_group, delivery_fee="1500.01")
    assert resp.status_code == 400 and resp.json()["error"]["code"] == "fee_above_cap"
    assert confirm(seller_client, verified, closed_group, delivery_fee="1500").status_code == 200


def test_invalid_terms_input_is_rejected(seller_client, verified, closed_group):
    for body in ({"unit_price": "0"}, {"unit_price": "-5"}, {"delivery_fee": "-1"}):
        assert confirm(seller_client, verified, closed_group, **body).status_code == 400
    assert status_of(closed_group) == "closed"


def test_confirmed_terms_do_not_move_when_the_offer_changes(
    seller_client, verified, seller, offer, closed_group
):
    confirm(seller_client, verified, closed_group, delivery_fee="1000")
    supplier_services.update_offer(
        wholesaler=verified, offer_id=offer.pk, actor=seller,
        values={"price_per_unit": D("9000"), "is_active": False},
    )  # fmt: skip
    group = GroupOrder.objects.get(pk=closed_group["id"])
    assert group.confirmed_unit_price == D("6800") and group.terms_snapshot["total"] == "69000"
    body = seller_client.get(W(verified, f"{closed_group['id']}/")).json()
    assert body["terms"]["unit_price"] == "6800" and body["list_price"] == "7000.00"


def test_only_a_closed_group_can_be_confirmed(
    seller_client, owner_client, shop, verified, offer, full_group
):
    # open (even with the target met)
    resp = confirm(seller_client, verified, full_group)
    assert resp.status_code == 409 and resp.json()["error"]["code"] == "invalid_transition"
    # failed
    failed = make_group(owner_client, shop, offer)
    expire(failed)
    assert confirm(seller_client, verified, failed).status_code == 409
    # cancelled
    cancelled = make_group(owner_client, shop, offer)
    owner_client.post(G(shop, f"{cancelled['id']}/cancel/"), {"reason": "x"}, format="json")
    assert confirm(seller_client, verified, cancelled).status_code == 409
    assert status_of(full_group) == "open"


def test_confirming_twice_or_after_declining_is_refused(
    seller_client, verified, closed_group, small_closed_group
):
    assert confirm(seller_client, verified, closed_group).status_code == 200
    assert confirm(seller_client, verified, closed_group).status_code == 409
    assert decline(seller_client, verified, closed_group).status_code == 409
    assert status_of(closed_group) == "confirmed"

    assert decline(seller_client, verified, small_closed_group).status_code == 200
    assert confirm(seller_client, verified, small_closed_group).status_code == 409
    assert status_of(small_closed_group) == "declined"
    assert AuditEvent.objects.filter(action="group.confirmed").count() == 1


def test_a_past_deadline_group_still_sitting_open_is_settled_then_confirmed(
    seller_client, verified, full_group
):
    expire(full_group)  # nobody has read it since the deadline
    resp = confirm(seller_client, verified, full_group)
    assert resp.status_code == 200 and resp.json()["status"] == "confirmed"


def test_the_wholesaler_cannot_confirm_more_than_it_has(
    seller_client, verified, seller, offer, closed_group
):
    supplier_services.update_offer(
        wholesaler=verified, offer_id=offer.pk, actor=seller,
        values={"available_quantity": D("8")},
    )  # fmt: skip
    resp = confirm(seller_client, verified, closed_group)
    assert resp.status_code == 400 and resp.json()["error"]["code"] == "exceeds_availability"
    assert status_of(closed_group) == "closed"
    assert decline(seller_client, verified, closed_group).status_code == 200  # the way out


def test_a_suspended_wholesaler_cannot_confirm_but_can_decline(
    seller_client, admin_user, verified, closed_group
):
    supplier_services.suspend_wholesaler(
        wholesaler_id=verified.pk, actor=admin_user, note="Complaints"
    )
    resp = confirm(seller_client, verified, closed_group)
    assert resp.status_code == 409 and resp.json()["error"]["code"] == "supplier_not_verified"
    assert status_of(closed_group) == "closed"
    assert decline(seller_client, verified, closed_group).status_code == 200


def test_the_supplier_cannot_decide_for_a_group_their_own_shop_is_in(
    seller, seller_client, verified, closed_group, shop, owner
):
    # the supplier also works in the organising shop
    from apps.shops.models import ShopMembership

    ShopMembership.objects.create(shop=shop, user=seller, role=ShopMembership.Role.MANAGER)
    assert confirm(seller_client, verified, closed_group).status_code == 403
    assert decline(seller_client, verified, closed_group).status_code == 403
    assert status_of(closed_group) == "closed"


def test_a_shop_that_withdrew_does_not_block_the_supplier(
    seller, seller_client, owner_client, other_client, third_client, shop, other_shop,
    third_shop, verified, offer,
):
    from apps.shops.models import ShopMembership

    ShopMembership.objects.create(shop=third_shop, user=seller, role=ShopMembership.Role.MANAGER)
    group = make_group(owner_client, shop, offer)  # 4 of 10
    join(third_client, third_shop, group, "2")
    withdraw(third_client, third_shop, group)  # the supplier's shop is out again
    join(other_client, other_shop, group, "6")
    assert owner_client.post(G(shop, f"{group['id']}/close/")).status_code == 200
    assert confirm(seller_client, verified, group).status_code == 200


# ------------------------------------------------------------------ declining
def test_declining_is_final_and_binds_nobody(
    seller_client, owner_client, other_client, shop, other_shop, seller, verified, closed_group
):
    assert decline(seller_client, verified, closed_group, reason=" ").status_code == 400
    resp = decline(seller_client, verified, closed_group, reason="Out of stock until March")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "declined" and body["binding"] is False and body["terms"] is None
    assert body["status_note"] == "Out of stock until March"
    assert body["confirmed_unit_price"] is None

    event = AuditEvent.objects.get(action="group.declined")
    assert event.actor == seller and event.shop == shop and event.wholesaler == verified
    # participants see why; nothing more can be done
    assert detail(other_client, other_shop, closed_group).json()["status"] == "declined"
    assert withdraw(other_client, other_shop, closed_group).status_code == 409
    assert owner_client.post(G(shop, f"{closed_group['id']}/close/")).status_code == 409


def test_an_open_group_cannot_be_declined(seller_client, verified, full_group):
    resp = decline(seller_client, verified, full_group)
    assert resp.status_code == 409 and resp.json()["error"]["code"] == "invalid_transition"


# ------------------------------------------------------------------ the binding point
def test_nothing_is_binding_until_the_wholesaler_confirms(
    owner_client, other_client, shop, other_shop, seller_client, verified, full_group
):
    assert detail(owner_client, shop, full_group).json()["binding"] is False  # open
    owner_client.post(G(shop, f"{full_group['id']}/close/"))
    assert detail(other_client, other_shop, full_group).json()["binding"] is False  # closed
    confirm(seller_client, verified, full_group)
    assert detail(other_client, other_shop, full_group).json()["binding"] is True  # confirmed


def test_a_confirmed_group_is_locked(
    owner_client, other_client, shop, other_shop, seller_client, verified, closed_group
):
    confirm(seller_client, verified, closed_group)
    assert change(other_client, other_shop, closed_group, "3").status_code == 409
    assert withdraw(other_client, other_shop, closed_group).status_code == 409
    cancel = owner_client.post(
        G(shop, f"{closed_group['id']}/cancel/"), {"reason": "x"}, format="json"
    )
    assert cancel.status_code == 409
    assert owner_client.post(G(shop, f"{closed_group['id']}/close/")).status_code == 409
    assert status_of(closed_group) == "confirmed"


def test_the_database_refuses_a_confirmed_group_without_terms(full_group):
    with pytest.raises(IntegrityError), transaction.atomic():
        GroupOrder.objects.filter(pk=full_group["id"]).update(status="confirmed")


def test_the_cached_totals_still_reconcile_after_the_lifecycle(
    seller_client, verified, closed_group
):
    confirm(seller_client, verified, closed_group)
    group = GroupOrder.objects.get(pk=closed_group["id"])
    expected = services.reconcile(group)
    assert group.committed_quantity == expected["committed_quantity"] == D("10")
    assert group.committed_quantity_base == expected["committed_quantity_base"] == D("500")
    assert group.participant_count == expected["participant_count"] == 2


def test_audit_events_for_the_lifecycle_carry_no_personal_data(
    seller_client, verified, closed_group
):
    confirm(seller_client, verified, closed_group, delivery_fee="500")
    blob = " ".join(
        str(e.changes) for e in AuditEvent.objects.filter(action__startswith="group.")
    )
    for forbidden in ("0712345678", "0711111111", "Amina", "Wanjiku"):
        assert forbidden not in blob
