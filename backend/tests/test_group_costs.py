"""Group buying, chunk 5c: per-shop orders, cost breakdown, and one full recruitment-to-receipt
scenario. (The fee-split maths has its own database-free file, test_group_cost_split.py.)"""

import json
from decimal import Decimal
from uuid import uuid4

import pytest

from apps.audit.models import AuditEvent
from apps.groupbuying import services
from apps.groupbuying.costs import CENT
from apps.groupbuying.models import GroupOrder, GroupParticipant
from apps.orders import services as order_services
from apps.orders.models import Order
from apps.suppliers.models import WholesalerMembership

from .conftest import make_client
from .test_group_lifecycle import W, confirm, decline, expire
from .test_groups import G, detail, join, make_group, withdraw
from .test_orders import WO, audit_actions, line, place, receive_body, stock

pytestmark = pytest.mark.django_db

D = Decimal


# ================================================================== fixtures (database)
@pytest.fixture
def pool(owner_client, other_client, third_client, shop, other_shop, third_shop, offer):
    """Three shops: 4 + 3 + 3 = 10 sacks (500 kg), the delivery fee estimate is 1,000.02.
    Joined in that order, so the tie-break is owner, then other, then third."""
    group = make_group(
        owner_client, shop, offer, estimated_delivery_fee="1000.02", quantity="4"
    )
    assert join(other_client, other_shop, group, "3").status_code == 200
    assert join(third_client, third_shop, group, "3").status_code == 200
    resp = owner_client.post(G(shop, f"{group['id']}/close/"))
    assert resp.status_code == 200, resp.content
    return resp.json()


@pytest.fixture
def confirmed(pool, seller_client, verified):
    resp = confirm(seller_client, verified, pool, delivery_fee="1000.02")
    assert resp.status_code == 200, resp.content
    return resp.json()


def orders_of(shop):
    return list(Order.objects.filter(shop=shop).prefetch_related("items"))


# ================================================================== orders generated on confirm
def test_confirming_creates_one_confirmed_order_per_shop(
    confirmed, shop, other_shop, third_shop, owner, other_user, third_user, seller, verified
):
    assert Order.objects.count() == 3
    expected = {  # shop, user, sacks, goods, delivery share (tie: owner, then other, then third)
        "owner": (shop, owner, D("4"), D("27200.00"), D("400.01")),
        "other": (other_shop, other_user, D("3"), D("20400.00"), D("300.01")),
        "third": (third_shop, third_user, D("3"), D("20400.00"), D("300.00")),
    }
    for who, (s, user, sacks, goods, share) in expected.items():
        (order,) = orders_of(s)
        assert order.status == "confirmed" and order.wholesaler == verified, who
        assert order.placed_by == user and order.currency == "KES"
        assert order.subtotal == goods and order.delivery_fee == share, who
        assert order.total_amount == goods + share
        assert order.confirmed_at == GroupOrder.objects.get().confirmed_at
        assert order.delivery_method == "collection"
        assert order.delivery_address == "Kondele market stage"
        assert str(confirmed["id"]) in order.note
        (item,) = order.items.all()
        assert item.quantity == sacks and item.quantity_base == sacks * 50
        assert item.unit_price_snapshot == D("6800") and item.list_price_snapshot == D("7000")
        assert item.line_total == goods and item.offer_id == GroupOrder.objects.get().offer_id
        assert item.product_name_snapshot == "Sugar" and item.unit_name_snapshot == "50 kg sack"
        assert item.unit_base_quantity_snapshot == D("50")
        participant = GroupParticipant.objects.get(group_id=confirmed["id"], shop=s)
        assert participant.order == order
        assert participant.goods_total == goods and participant.delivery_share == share


def test_each_party_sees_the_generated_orders_in_the_normal_order_lists(
    confirmed, owner_client, other_client, seller_client, shop, other_shop, verified
):
    mine = owner_client.get(f"/api/v1/shops/{shop.pk}/orders/").json()["results"]
    assert [(o["status"], o["subtotal"], o["delivery_fee"]) for o in mine] == [
        ("confirmed", "27200.00", "400.01")
    ]
    theirs = other_client.get(f"/api/v1/shops/{other_shop.pk}/orders/").json()["results"]
    assert [o["total_amount"] for o in theirs] == ["20700.01"]
    incoming = seller_client.get(f"/api/v1/wholesalers/{verified.pk}/orders/").json()["results"]
    assert len(incoming) == 3 and {o["status"] for o in incoming} == {"confirmed"}


def test_an_order_says_which_group_it_came_from_and_an_ordinary_one_does_not(
    confirmed, owner_client, shop, offer
):
    (generated,) = owner_client.get(f"/api/v1/shops/{shop.pk}/orders/").json()["results"]
    assert generated["group_order_id"] == confirmed["id"]
    ordinary = place(owner_client, shop, line(offer, "2"), key=str(uuid4()))
    assert ordinary.status_code == 201 and ordinary.json()["group_order_id"] is None


def test_the_group_totals_reconcile_with_the_per_shop_costs_and_orders(confirmed):
    group = GroupOrder.objects.get(pk=confirmed["id"])
    totals = services.reconcile_costs(group)
    assert totals["orders"] == group.participant_count == 3
    assert totals["quantity"] == group.committed_quantity == D("10")
    assert totals["quantity_base"] == group.committed_quantity_base == D("500")
    assert totals["goods_total"] == totals["order_subtotals"] == D("68000.00")
    assert totals["delivery_fee"] == totals["order_delivery_fees"] == group.confirmed_delivery_fee
    assert totals["delivery_fee"] == D("1000.02")
    assert totals["order_totals"] == D("69000.02")
    assert group.terms_snapshot["total"] == "69000.02"
    assert group.terms_snapshot["goods_total"] == "68000"


def test_rounding_per_shop_still_reconciles_exactly(
    owner_client, other_client, third_client, shop, other_shop, third_shop, offer, seller_client,
    verified,
):
    """Awkward fractional quantities and an odd price: the group's goods total is the SUM of the
    shops' rounded line totals, never a separately rounded figure that could drift a cent."""
    group = make_group(
        owner_client, shop, offer, target_quantity="9", quantity="3.333333",
        estimated_delivery_fee="100.00",
    )
    join(other_client, other_shop, group, "3.333333")
    join(third_client, third_shop, group, "3.333333")
    assert owner_client.post(G(shop, f"{group['id']}/close/")).status_code == 200
    resp = confirm(seller_client, verified, group, unit_price="6999.99", delivery_fee="100.00")
    assert resp.status_code == 200, resp.content

    row = GroupOrder.objects.get(pk=group["id"])
    totals = services.reconcile_costs(row)
    line = (D("3.333333") * D("6999.99")).quantize(CENT)
    assert totals["goods_total"] == totals["order_subtotals"] == line * 3
    assert D(row.terms_snapshot["goods_total"]) == line * 3
    assert totals["delivery_fee"] == D("100.00")
    assert sum(o.total_amount for o in Order.objects.all()) == line * 3 + D("100.00")


def test_a_zero_delivery_fee_gives_every_order_a_zero_share(pool, seller_client, verified):
    assert confirm(seller_client, verified, pool).status_code == 200  # fee defaults to 0
    assert {o.delivery_fee for o in Order.objects.all()} == {D("0.00")}
    assert Order.objects.count() == 3


def test_only_active_participants_get_an_order(
    owner_client, other_client, third_client, shop, other_shop, third_shop, offer, seller_client,
    verified,
):
    group = make_group(owner_client, shop, offer)  # 4
    join(third_client, third_shop, group, "2")
    withdraw(third_client, third_shop, group)
    join(other_client, other_shop, group, "6")
    owner_client.post(G(shop, f"{group['id']}/close/"))
    assert confirm(seller_client, verified, group).status_code == 200
    assert Order.objects.count() == 2 and not orders_of(third_shop)
    assert GroupParticipant.objects.get(shop=third_shop).order is None


def test_the_group_is_never_confirmed_with_only_some_of_its_orders(
    pool, verified, seller, monkeypatch
):
    real = order_services.create_group_order
    calls = []

    def flaky(**kwargs):
        calls.append(kwargs["shop"])
        if len(calls) == 2:
            raise RuntimeError("database hiccup")
        return real(**kwargs)

    monkeypatch.setattr(order_services, "create_group_order", flaky)
    with pytest.raises(RuntimeError, match="hiccup"):
        services.confirm_group(wholesaler=verified, actor=seller, group_id=pool["id"])
    monkeypatch.undo()

    group = GroupOrder.objects.get(pk=pool["id"])
    assert group.status == "closed" and group.confirmed_unit_price is None
    assert group.terms_snapshot == {}
    assert Order.objects.count() == 0
    assert not GroupParticipant.objects.filter(order__isnull=False).exists()
    assert not AuditEvent.objects.filter(action__in=("group.confirmed", "order.placed")).exists()
    # and it can be confirmed properly afterwards
    services.confirm_group(wholesaler=verified, actor=seller, group_id=pool["id"])
    assert Order.objects.count() == 3


def test_declined_failed_and_cancelled_groups_create_no_orders(
    owner_client, other_client, shop, other_shop, offer, seller_client, verified, pool
):
    assert decline(seller_client, verified, pool).status_code == 200  # declined
    failed = make_group(owner_client, shop, offer)
    expire(failed)
    detail(owner_client, shop, failed)  # failed
    cancelled = make_group(other_client, other_shop, offer, quantity="3")
    other_client.post(G(other_shop, f"{cancelled['id']}/cancel/"), {"reason": "x"}, format="json")
    assert Order.objects.count() == 0
    assert not GroupParticipant.objects.filter(order__isnull=False).exists()


def test_the_audit_trail_links_the_group_and_its_orders(confirmed, seller, owner):
    event = AuditEvent.objects.get(action="group.confirmed")
    assert event.changes["after"]["orders_created"] == 3
    order_ids = set(event.changes["after"]["order_ids"])
    assert order_ids == {str(o.pk) for o in Order.objects.all()}
    for order in Order.objects.all():
        assert audit_actions(str(order.pk)) == ["order.placed", "order.confirmed"]
        placed = AuditEvent.objects.get(action="order.placed", object_id=str(order.pk))
        assert placed.changes["group_order_id"] == confirmed["id"]
        confirmed_event = AuditEvent.objects.get(action="order.confirmed", object_id=str(order.pk))
        assert confirmed_event.actor == seller and confirmed_event.wholesaler == order.wholesaler


# ================================================================== the cost breakdown
def costs(client, shop, group):
    return client.get(G(shop, f"{group['id']}/cost-breakdown/"))


def test_a_shop_sees_the_group_totals_and_only_its_own_line(
    confirmed, owner_client, other_client, third_client, shop, other_shop, third_shop
):
    body = costs(owner_client, shop, confirmed).json()
    assert body["status"] == "confirmed" and body["currency"] == "KES"
    assert body["unit_price"] == "6800.00" and body["tier_minimum_quantity"] == "10.000000"
    assert body["quantity"] == "10.000000" and body["quantity_base"] == "500.000000"
    assert body["participant_count"] == 3
    assert body["goods_total"] == "68000.00" and body["delivery_fee"] == "1000.02"
    assert body["total"] == "69000.02"
    assert body["delivery_method"] == "collection"
    assert body["mine"]["quantity"] == "4.000000" and body["mine"]["goods_total"] == "27200.00"
    assert body["mine"]["delivery_share"] == "400.01" and body["mine"]["total"] == "27600.01"
    assert body["mine"]["order_status"] == "confirmed"
    assert body["mine"]["order_id"] == str(orders_of(shop)[0].pk)

    # the other shops' figures never appear in anyone else's response
    assert "orders" not in body
    theirs = costs(other_client, other_shop, confirmed).json()
    assert theirs["mine"]["delivery_share"] == "300.01" and theirs["mine"]["total"] == "20700.01"
    assert costs(third_client, third_shop, confirmed).json()["mine"]["delivery_share"] == "300.00"
    blob = json.dumps(body)
    for other in (other_shop, third_shop):
        assert str(orders_of(other)[0].pk) not in blob
    assert "300.01" not in blob and "20400.00" not in blob


def test_the_group_detail_also_carries_my_own_cost_line_and_order(
    confirmed, other_client, other_shop
):
    mine = detail(other_client, other_shop, confirmed).json()["my_commitment"]
    assert mine["order_id"] == str(orders_of(other_shop)[0].pk)
    assert mine["goods_total"] == "20400.00" and mine["delivery_share"] == "300.01"


def test_costs_are_final_only_after_confirmation(
    owner_client, shop, offer, pool, other_client, other_shop
):
    assert costs(owner_client, shop, pool).status_code == 409  # closed, not yet confirmed
    body = costs(owner_client, shop, pool).json()
    assert body["error"]["code"] == "not_confirmed"
    open_group = make_group(other_client, other_shop, offer, quantity="3")
    assert costs(other_client, other_shop, open_group).status_code == 409


def test_a_withdrawn_shop_sees_no_line_of_its_own(
    owner_client, other_client, third_client, shop, other_shop, third_shop, offer, seller_client,
    verified,
):
    group = make_group(owner_client, shop, offer)
    join(third_client, third_shop, group, "2")
    withdraw(third_client, third_shop, group)
    join(other_client, other_shop, group, "6")
    owner_client.post(G(shop, f"{group['id']}/close/"))
    confirm(seller_client, verified, group)
    body = costs(third_client, third_shop, group).json()
    assert body["mine"] is None and body["participant_count"] == 2


def test_strangers_and_staff_follow_the_usual_rules(
    confirmed, staff_user, other_user, owner_client, other_client, shop, third_shop
):
    assert costs(make_client(staff_user), shop, confirmed).status_code == 200  # staff may view
    # a shop that never took part cannot see a confirmed group at all
    from apps.shops import services as shop_services

    outsider = shop_services.create_shop(other_user, name="Outsider Duka")
    assert costs(other_client, outsider, confirmed).status_code == 404
    assert other_client.get(G(shop) + f"{confirmed['id']}/cost-breakdown/").status_code == 404


def test_the_wholesaler_sees_one_row_per_order_and_the_same_totals(
    confirmed, seller_client, verified, shop
):
    body = seller_client.get(W(verified, f"{confirmed['id']}/cost-breakdown/")).json()
    assert body["goods_total"] == "68000.00" and body["delivery_fee"] == "1000.02"
    assert "mine" not in body and len(body["orders"]) == 3
    assert [r["shop"]["name"] for r in body["orders"]] == [
        "Amina Duka", "Brian Duka", "Faith Duka",
    ]  # in joining order
    assert [r["delivery_share"] for r in body["orders"]] == ["400.01", "300.01", "300.00"]
    assert sum(D(r["goods_total"]) for r in body["orders"]) == D(body["goods_total"])
    assert sum(D(r["delivery_share"]) for r in body["orders"]) == D(body["delivery_fee"])
    assert sum(D(r["total"]) for r in body["orders"]) == D(body["total"])
    assert sum(D(r["quantity_base"]) for r in body["orders"]) == D(body["quantity_base"])


def test_the_wholesaler_breakdown_is_for_its_own_confirmed_groups_only(
    confirmed, pool, rival_user, rival, verified, other_client
):
    from apps.accounts.models import User

    dock = User.objects.create_user("0755555555", "S3cure-pass!", full_name="Dock Staff")
    url = W(verified, f"{confirmed['id']}/cost-breakdown/")
    assert make_client(rival_user).get(url).status_code == 404
    assert other_client.get(url).status_code == 404
    WholesalerMembership.objects.create(
        wholesaler=verified, user=dock, role=WholesalerMembership.Role.STAFF
    )
    assert make_client(dock).get(url).status_code == 200  # staff may view


def test_the_wholesaler_breakdown_needs_a_confirmed_group(
    seller_client, verified, pool
):
    resp = seller_client.get(W(verified, f"{pool['id']}/cost-breakdown/"))
    assert resp.status_code == 409 and resp.json()["error"]["code"] == "not_confirmed"


def test_frozen_costs_do_not_move_when_an_order_is_cancelled_or_the_offer_changes(
    confirmed, owner_client, seller_client, verified, seller, shop, offer
):
    from apps.suppliers import services as supplier_services

    order = orders_of(shop)[0]
    cancel = seller_client.post(
        WO(verified, f"{order.pk}/cancel/"), {"reason": "shop unreachable"}, format="json"
    )
    assert cancel.status_code == 200
    supplier_services.update_offer(
        wholesaler=verified, offer_id=offer.pk, actor=seller, values={"price_per_unit": D("9999")}
    )
    body = costs(owner_client, shop, confirmed).json()
    assert body["mine"]["order_status"] == "cancelled"  # the live status is shown...
    assert body["mine"]["goods_total"] == "27200.00"  # ...but what was agreed is not rewritten
    assert body["total"] == "69000.02" and body["unit_price"] == "6800.00"


# ================================================================== cancelling a group order
def test_a_shop_cannot_cancel_an_order_that_came_from_a_confirmed_group(
    confirmed, owner_client, shop
):
    order = orders_of(shop)[0]
    resp = owner_client.post(
        f"/api/v1/shops/{shop.pk}/orders/{order.pk}/cancel/", {"reason": "changed my mind"},
        format="json",
    )
    assert resp.status_code == 409 and resp.json()["error"]["code"] == "group_order_locked"
    order.refresh_from_db()
    assert order.status == "confirmed" and order.cancelled_by == ""
    assert "order.cancelled" not in audit_actions(str(order.pk))


def test_the_wholesaler_can_cancel_one_group_order_but_must_give_a_reason(
    confirmed, seller_client, verified, shop, other_shop
):
    order = orders_of(shop)[0]
    url = WO(verified, f"{order.pk}/cancel/")
    assert seller_client.post(url, {}, format="json").status_code == 400
    ok = seller_client.post(url, {"reason": "Shop closed, cannot deliver"}, format="json")
    assert ok.status_code == 200
    order.refresh_from_db()
    assert order.status == "cancelled" and order.cancelled_by == "wholesaler"
    assert Order.objects.get(shop=other_shop).status == "confirmed"  # the others are unaffected


def test_a_cancelled_group_order_shows_who_cancelled_and_why_without_moving_costs(
    confirmed, seller_client, owner_client, other_client, verified, shop, other_shop
):
    order = orders_of(shop)[0]
    url = WO(verified, f"{order.pk}/cancel/")
    assert seller_client.post(url, {"reason": "Shop closed"}, format="json").status_code == 200

    body = costs(owner_client, shop, confirmed).json()
    assert body["mine"]["order_status"] == "cancelled"
    assert body["mine"]["cancelled_by"] == "wholesaler"
    assert body["mine"]["cancel_reason"] == "Shop closed"
    assert body["total"] == "69000.02" and body["mine"]["total"] == "27600.01"

    theirs = costs(other_client, other_shop, confirmed).json()["mine"]
    assert theirs["order_status"] == "confirmed"
    assert theirs["cancelled_by"] == "" and theirs["cancel_reason"] == ""

    rows = seller_client.get(W(verified, f"{confirmed['id']}/cost-breakdown/")).json()["orders"]
    assert [r["cancelled_by"] for r in rows] == ["wholesaler", "", ""]

    event = AuditEvent.objects.get(action="order.cancelled", object_id=str(order.pk))
    assert event.changes["group_order_id"] == confirmed["id"]
    assert event.changes["by"] == "wholesaler"


# ================================================================== the whole journey
def test_recruitment_to_receipt(
    owner_client, other_client, third_client, seller_client, shop, other_shop, third_shop,
    verified, offer, sugar,
):
    """Scenario E from testing.md: create a group, add shops, reach the target, confirm terms,
    generate per-shop orders, allocate costs and record delivery (one shop short-shipped)."""
    # --- recruitment: nothing binds anyone
    group = make_group(owner_client, shop, offer, estimated_delivery_fee="1000.02")
    assert join(other_client, other_shop, group, "3").status_code == 200
    assert detail(third_client, third_shop, group).json()["binding"] is False
    assert join(third_client, third_shop, group, "3").status_code == 200
    assert Order.objects.count() == 0 and stock_total(sugar) == 0

    # --- target reached: freeze, then the wholesaler confirms the final terms
    assert owner_client.post(G(shop, f"{group['id']}/close/")).status_code == 200
    assert detail(other_client, other_shop, group).json()["binding"] is False
    assert confirm(seller_client, verified, group, delivery_fee="1000.02").status_code == 200
    assert detail(other_client, other_shop, group).json()["binding"] is True
    assert Order.objects.count() == 3 and stock_total(sugar) == 0

    # --- fulfilment through the ordinary order flow
    clients = {shop: owner_client, other_shop: other_client, third_shop: third_client}
    sacks_received = {shop: "4", other_shop: "2", third_shop: "3"}  # the second shop is 1 short
    for s, client in clients.items():
        (order,) = client.get(f"/api/v1/shops/{s.pk}/orders/").json()["results"]
        base = f"/api/v1/wholesalers/{verified.pk}/orders/{order['id']}/"
        assert seller_client.post(base + "dispatch/", {}, format="json").status_code == 200
        resp = client.post(
            f"/api/v1/shops/{s.pk}/orders/{order['id']}/receive/",
            receive_body(order, [sacks_received[s]], note="Delivered at the stage"),
            format="json",
        )
        assert resp.status_code == 200, resp.content

    # --- every shop's stock reflects what ARRIVED, in kilograms
    assert stock(shop, sugar.product) == D("200")
    assert stock(other_shop, sugar.product) == D("100")  # 2 of 3 sacks
    assert stock(third_shop, sugar.product) == D("150")
    short = Order.objects.get(shop=other_shop)
    assert short.status == "received" and short.has_shortage is True
    assert not Order.objects.get(shop=shop).has_shortage

    # --- the agreed costs are untouched by delivery, and still reconcile
    row = GroupOrder.objects.get(pk=group["id"])
    totals = services.reconcile_costs(row)
    assert totals["order_totals"] == D(row.terms_snapshot["total"]) == D("69000.02")
    assert totals["goods_total"] == D("68000.00") and totals["delivery_fee"] == D("1000.02")
    mine = costs(other_client, other_shop, group).json()["mine"]
    assert mine["order_status"] == "received" and mine["total"] == "20700.01"

    # --- one trail: group events, then each order's own events
    actions = list(
        AuditEvent.objects.filter(object_type="group_order", object_id=group["id"])
        .order_by("created_at", "id")
        .values_list("action", flat=True)
    )
    assert actions == [
        "group.created", "group.joined", "group.joined", "group.closed", "group.confirmed",
    ]
    for order in Order.objects.all():
        assert audit_actions(str(order.pk)) == [
            "order.placed", "order.confirmed", "order.dispatched", "order.received",
        ]


def stock_total(sugar):
    from apps.inventory.models import ShopProduct

    return sum(
        (sp.quantity_base for sp in ShopProduct.objects.filter(product=sugar.product)), D("0")
    )
