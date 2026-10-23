from decimal import Decimal
from uuid import uuid4

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.audit.models import AuditEvent
from apps.inventory import services as inventory
from apps.inventory.models import PurchaseReceipt, ShopProduct
from apps.orders.models import Order
from apps.shops import services as shop_services
from apps.shops.models import ShopMembership
from apps.suppliers import services as supplier_services
from apps.suppliers.models import SupplierOffer, WholesalerMembership

from .conftest import PASSWORD, make_client

pytestmark = pytest.mark.django_db

D = Decimal
ADDRESS = "Kondele, Kisumu"


# ------------------------------------------------------------------ fixtures & helpers
@pytest.fixture
def sugar_offer(verified, seller, sugar):
    """7,000 per 50 kg sack, 6,800 from 10 sacks."""
    return supplier_services.create_offer(
        wholesaler=verified, actor=seller, product_id=sugar.product.pk,
        product_unit_id=sugar.sack.pk, price_per_unit=D("7000"),
        tiers=[{"minimum_quantity": D("10"), "unit_price": D("6800")}],
    )  # fmt: skip


@pytest.fixture
def flour_offer(verified, seller, flour):
    return supplier_services.create_offer(
        wholesaler=verified, actor=seller, product_id=flour.product.pk,
        product_unit_id=flour.kg.pk, price_per_unit=D("150"),
    )  # fmt: skip


@pytest.fixture
def wholesaler_staff(verified):
    user = User.objects.create_user("0777777777", PASSWORD, full_name="Dock Staff")
    WholesalerMembership.objects.create(
        wholesaler=verified, user=user, role=WholesalerMembership.Role.STAFF
    )
    return make_client(user)


def S(shop, suffix=""):
    return f"/api/v1/shops/{shop.pk}/orders/{suffix}"


def WO(w, suffix=""):
    return f"/api/v1/wholesalers/{w.pk}/orders/{suffix}"


def line(offer, quantity):
    return {"offer_id": str(offer.pk), "quantity": str(quantity)}


def place(client, shop, *lines, key=None, **extra):
    body = {
        "idempotency_key": key or str(uuid4()),
        "items": list(lines),
        "delivery_address": ADDRESS,
        **extra,
    }
    return client.post(S(shop), body, format="json")


def placed(client, shop, offer, quantity="2", **extra):
    resp = place(client, shop, line(offer, quantity), **extra)
    assert resp.status_code == 201, resp.content
    return resp.json()


def act(client, w, order, action, **body):
    return client.post(WO(w, f"{order['id']}/{action}/"), body, format="json")


def receive_body(order, quantities, **extra):
    return {
        "idempotency_key": str(uuid4()),
        "items": [
            {"item_id": item["id"], "received_quantity": str(q)}
            for item, q in zip(order["items"], quantities, strict=True)
        ],
        **extra,
    }


def to_dispatched(client, seller_client, shop, w, offer, quantity="2"):
    order = placed(client, shop, offer, quantity)
    assert act(seller_client, w, order, "confirm").status_code == 200
    assert act(seller_client, w, order, "dispatch").status_code == 200
    return order


def stock(shop, product):
    return ShopProduct.objects.get(shop=shop, product=product).quantity_base


def audit_actions(order_id):
    return list(
        AuditEvent.objects.filter(object_type="order", object_id=order_id)
        .order_by("created_at", "id")
        .values_list("action", flat=True)
    )


# ------------------------------------------------------------------ placing
def test_placing_snapshots_the_agreed_terms(owner_client, shop, owner, verified, sugar_offer):
    order = placed(owner_client, shop, sugar_offer, "2", note="Morning please")
    assert order["status"] == "submitted"
    assert order["subtotal"] == "14000.00" and order["total_amount"] == "14000.00"
    assert order["delivery_fee"] == "0.00" and order["currency"] == "KES"
    assert order["delivery_address"] == ADDRESS and order["note"] == "Morning please"
    assert order["wholesaler"]["business_name"] == "Kisumu Wholesale"
    [item] = order["items"]
    assert item["product_name"] == "Sugar" and item["unit_name"] == "50 kg sack"
    assert item["quantity"] == "2.000000" and item["quantity_base"] == "100.000000"
    assert item["unit_base_quantity"] == "50.000000"
    assert item["unit_price"] == "7000.00" and item["line_total"] == "14000.00"
    assert item["received_quantity"] is None

    event = AuditEvent.objects.get(action="order.placed")
    assert event.shop == shop and event.wholesaler == verified and event.actor == owner


def test_volume_tier_is_applied_and_recorded(owner_client, shop, sugar_offer):
    [item] = placed(owner_client, shop, sugar_offer, "10")["items"]
    assert item["list_price"] == "7000.00" and item["unit_price"] == "6800.00"
    assert item["line_total"] == "68000.00"


def test_several_lines_are_totalled(owner_client, shop, sugar_offer, flour_offer):
    resp = place(owner_client, shop, line(sugar_offer, "1"), line(flour_offer, "20"))
    assert resp.status_code == 201
    assert resp.json()["subtotal"] == "10000.00"  # 7,000 + 20 x 150
    assert {i["product_name"] for i in resp.json()["items"]} == {"Sugar", "Maize flour"}


def test_minimum_availability_and_stock_rules(owner_client, shop, verified, seller, sugar, flour_offer):
    supplier_services.update_offer(
        wholesaler=verified, offer_id=flour_offer.pk, actor=seller,
        values={"minimum_order_quantity": D("5"), "available_quantity": D("50")},
    )  # fmt: skip
    below = place(owner_client, shop, line(flour_offer, "2"))
    assert below.status_code == 400 and below.json()["error"]["code"] == "below_minimum"
    over = place(owner_client, shop, line(flour_offer, "60"))
    assert over.status_code == 400 and over.json()["error"]["code"] == "exceeds_availability"
    assert place(owner_client, shop, line(flour_offer, "50")).status_code == 201

    supplier_services.update_offer(
        wholesaler=verified, offer_id=flour_offer.pk, actor=seller,
        values={"availability": "out_of_stock", "available_quantity": None},
    )  # fmt: skip
    out = place(owner_client, shop, line(flour_offer, "10"))
    assert out.status_code == 400 and out.json()["error"]["code"] == "out_of_stock"


def test_placing_does_not_change_the_suppliers_availability(owner_client, shop, verified, seller, flour_offer):
    supplier_services.update_offer(
        wholesaler=verified, offer_id=flour_offer.pk, actor=seller,
        values={"available_quantity": D("100")},
    )  # fmt: skip
    placed(owner_client, shop, flour_offer, "40")
    flour_offer.refresh_from_db()
    assert flour_offer.available_quantity == D("100")  # the supplier reconfirms on confirm


def test_a_line_may_only_be_listed_once(owner_client, shop, sugar_offer):
    resp = place(owner_client, shop, line(sugar_offer, "1"), line(sugar_offer, "2"))
    assert resp.status_code == 400 and resp.json()["error"]["code"] == "duplicate_item"


@pytest.mark.parametrize("how", ["draft", "suspended", "pending", "unknown"])
def test_offers_that_are_not_live_cannot_be_ordered(
    how, owner_client, shop, sugar_offer, verified, admin_user, seller
):
    target = sugar_offer
    if how == "draft":
        supplier_services.update_offer(
            wholesaler=verified, offer_id=sugar_offer.pk, actor=seller, values={"is_active": False}
        )
    elif how == "suspended":
        supplier_services.suspend_wholesaler(wholesaler_id=verified.pk, actor=admin_user, note="x")
    elif how == "pending":
        verified.verification_status = "pending"
        verified.save()
    else:
        target = SupplierOffer(pk=uuid4())
    resp = place(owner_client, shop, line(target, "1"))
    assert resp.status_code == 400 and resp.json()["error"]["code"] == "offer_not_found"
    assert not Order.objects.exists()


def test_an_order_cannot_span_wholesalers(owner_client, shop, sugar_offer, rival, rival_user, flour):
    theirs = supplier_services.create_offer(
        wholesaler=rival, actor=rival_user, product_id=flour.product.pk,
        product_unit_id=flour.kg.pk, price_per_unit=D("140"),
    )  # fmt: skip
    resp = place(owner_client, shop, line(sugar_offer, "1"), line(theirs, "5"))
    assert resp.status_code == 400 and resp.json()["error"]["code"] == "mixed_wholesalers"


def test_only_owners_and_managers_place_orders(owner_client, shop, staff_user, other_user, sugar_offer):
    assert place(make_client(staff_user), shop, line(sugar_offer, "1")).status_code == 403
    assert place(make_client(other_user), shop, line(sugar_offer, "1")).status_code == 404
    assert place(APIClient(), shop, line(sugar_offer, "1")).status_code == 401
    assert not Order.objects.exists()


def test_a_person_cannot_order_from_their_own_wholesaler(seller, seller_client, verified, sugar_offer):
    own_shop = shop_services.create_shop(seller, name="Wanjiku Duka")
    resp = place(seller_client, own_shop, line(sugar_offer, "1"))
    assert resp.status_code == 400 and resp.json()["error"]["code"] == "self_order"


def test_delivery_address_rules(owner_client, shop, sugar_offer):
    no_address = owner_client.post(
        S(shop),
        {"idempotency_key": str(uuid4()), "items": [line(sugar_offer, "1")]}, format="json",
    )  # fmt: skip
    assert no_address.status_code == 400
    assert no_address.json()["error"]["code"] == "delivery_address_required"

    shop.location_text = "Milimani"
    shop.save()
    defaulted = owner_client.post(
        S(shop), {"idempotency_key": str(uuid4()), "items": [line(sugar_offer, "1")]}, format="json"
    )
    assert defaulted.status_code == 201 and defaulted.json()["delivery_address"] == "Milimani"

    pickup = place(owner_client, shop, line(sugar_offer, "1"), delivery_method="collection")
    assert pickup.status_code == 201
    assert pickup.json()["delivery_method"] == "collection" and pickup.json()["delivery_address"] == ""


def test_contact_phone_is_normalised_or_rejected(owner_client, shop, sugar_offer):
    ok = place(owner_client, shop, line(sugar_offer, "1"), contact_phone="0712 345 678")
    assert ok.json()["contact_phone"] == "+254712345678"
    bad = place(owner_client, shop, line(sugar_offer, "1"), contact_phone="abc")
    assert bad.status_code == 400 and bad.json()["error"]["code"] == "invalid_phone"


def test_placing_is_idempotent(owner_client, shop, sugar_offer):
    key = str(uuid4())
    first = place(owner_client, shop, line(sugar_offer, "2"), key=key)
    again = place(owner_client, shop, line(sugar_offer, "2"), key=key)
    assert first.status_code == again.status_code == 201
    assert again["Idempotent-Replayed"] == "true" and again.json()["id"] == first.json()["id"]
    assert Order.objects.count() == 1
    assert AuditEvent.objects.filter(action="order.placed").count() == 1

    clash = place(owner_client, shop, line(sugar_offer, "3"), key=key)
    assert clash.status_code == 409 and clash.json()["error"]["code"] == "idempotency_conflict"
    assert Order.objects.count() == 1


# ------------------------------------------------------------------ agreed terms never move
def test_later_offer_edits_never_rewrite_an_order(
    owner_client, seller_client, shop, verified, seller, sugar_offer, sugar
):
    order = placed(owner_client, shop, sugar_offer, "10")  # 6,800 tier price
    act(seller_client, verified, order, "confirm", delivery_fee="300")

    supplier_services.update_offer(
        wholesaler=verified, offer_id=sugar_offer.pk, actor=seller,
        values={"price_per_unit": D("9000"), "is_active": False},
    )  # fmt: skip
    supplier_services.replace_tiers(wholesaler=verified, offer_id=sugar_offer.pk, actor=seller, tiers=[])
    sugar.product.name = "Sugar (renamed)"
    sugar.product.save()

    for body in (
        owner_client.get(S(shop, f"{order['id']}/")).json(),
        seller_client.get(WO(verified, f"{order['id']}/")).json(),
    ):
        [item] = body["items"]
        assert item["unit_price"] == "6800.00" and item["list_price"] == "7000.00"
        assert item["product_name"] == "Sugar" and item["line_total"] == "68000.00"
        assert body["subtotal"] == "68000.00" and body["total_amount"] == "68300.00"


# ------------------------------------------------------------------ lifecycle
def test_full_happy_path_with_audit_trail(owner_client, seller_client, shop, verified, sugar_offer):
    order = placed(owner_client, shop, sugar_offer, "2")
    confirmed = act(seller_client, verified, order, "confirm", delivery_fee="500.00").json()
    assert confirmed["status"] == "confirmed" and confirmed["confirmed_at"]
    assert confirmed["delivery_fee"] == "500.00" and confirmed["total_amount"] == "14500.00"
    assert confirmed["subtotal"] == "14000.00"

    dispatched = act(seller_client, verified, order, "dispatch").json()
    assert dispatched["status"] == "dispatched" and dispatched["dispatched_at"]

    resp = owner_client.post(S(shop, f"{order['id']}/receive/"), receive_body(order, ["2"]), format="json")
    assert resp.status_code == 200, resp.content
    done = resp.json()
    assert done["status"] == "received" and done["received_at"] and done["has_shortage"] is False
    assert audit_actions(order["id"]) == [
        "order.placed", "order.confirmed", "order.dispatched", "order.received"
    ]  # fmt: skip


def test_reject_needs_a_reason_and_is_final(owner_client, seller_client, shop, verified, sugar_offer):
    order = placed(owner_client, shop, sugar_offer)
    assert act(seller_client, verified, order, "reject").status_code == 400
    rejected = act(seller_client, verified, order, "reject", reason="Out of stock")
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected" and rejected.json()["status_note"] == "Out of stock"
    for action in ("confirm", "dispatch", "reject"):
        assert act(seller_client, verified, order, action, reason="x").status_code == 409
    assert owner_client.post(
        S(shop, f"{order['id']}/cancel/"), {"reason": "x"}, format="json"
    ).status_code == 409  # fmt: skip


def test_invalid_transitions_are_refused(owner_client, seller_client, shop, verified, sugar_offer):
    order = placed(owner_client, shop, sugar_offer)
    assert act(seller_client, verified, order, "dispatch").status_code == 409  # not confirmed yet
    receive = S(shop, f"{order['id']}/receive/")
    assert owner_client.post(receive, receive_body(order, ["2"]), format="json").status_code == 409

    assert act(seller_client, verified, order, "confirm").status_code == 200
    assert act(seller_client, verified, order, "confirm").status_code == 409  # twice
    assert owner_client.post(receive, receive_body(order, ["2"]), format="json").status_code == 409

    assert act(seller_client, verified, order, "dispatch").status_code == 200
    cancel = owner_client.post(S(shop, f"{order['id']}/cancel/"), {"reason": "x"}, format="json")
    assert cancel.status_code == 409 and cancel.json()["error"]["code"] == "invalid_transition"
    assert act(seller_client, verified, order, "cancel", reason="x").status_code == 409
    assert Order.objects.get(pk=order["id"]).status == "dispatched"


@pytest.mark.parametrize("confirm_first", [False, True])
def test_a_shop_can_cancel_until_dispatch(owner_client, seller_client, shop, verified, sugar_offer, confirm_first):
    order = placed(owner_client, shop, sugar_offer)
    if confirm_first:
        act(seller_client, verified, order, "confirm")
    url = S(shop, f"{order['id']}/cancel/")
    assert owner_client.post(url, {}, format="json").status_code == 400  # reason needed
    resp = owner_client.post(url, {"reason": "Changed my mind"}, format="json")
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled" and resp.json()["cancelled_by"] == "shop"
    assert AuditEvent.objects.get(action="order.cancelled").changes["by"] == "shop"


def test_a_wholesaler_can_cancel_a_confirmed_order(owner_client, seller_client, shop, verified, sugar_offer):
    order = placed(owner_client, shop, sugar_offer)
    act(seller_client, verified, order, "confirm")
    assert act(seller_client, verified, order, "cancel").status_code == 400
    resp = act(seller_client, verified, order, "cancel", reason="Truck broke down")
    assert resp.json()["status"] == "cancelled" and resp.json()["cancelled_by"] == "wholesaler"


def test_suspension_blocks_confirming_but_not_winding_down(
    owner_client, seller_client, shop, verified, admin_user, sugar_offer
):
    waiting = placed(owner_client, shop, sugar_offer)
    shipped = to_dispatched(owner_client, seller_client, shop, verified, sugar_offer)
    supplier_services.suspend_wholesaler(wholesaler_id=verified.pk, actor=admin_user, note="x")

    blocked = act(seller_client, verified, waiting, "confirm")
    assert blocked.status_code == 409 and blocked.json()["error"]["code"] == "supplier_not_verified"
    assert act(seller_client, verified, waiting, "reject", reason="suspended").status_code == 200
    # goods already on the road can still be received
    resp = owner_client.post(S(shop, f"{shipped['id']}/receive/"), receive_body(shipped, ["2"]), format="json")
    assert resp.status_code == 200


# ------------------------------------------------------------------ who may do what
def test_only_wholesaler_owners_and_managers_act_on_orders(
    owner_client, seller_client, wholesaler_staff, shop, verified, sugar_offer
):
    order = placed(owner_client, shop, sugar_offer)
    for action, body in (("confirm", {}), ("reject", {"reason": "x"}), ("dispatch", {}), ("cancel", {"reason": "x"})):
        assert act(wholesaler_staff, verified, order, action, **body).status_code == 403
    assert wholesaler_staff.get(WO(verified)).status_code == 200  # but may look
    assert Order.objects.get(pk=order["id"]).status == "submitted"


def test_shop_staff_can_receive_but_not_cancel(
    owner_client, seller_client, staff_user, shop, verified, sugar_offer
):
    order = to_dispatched(owner_client, seller_client, shop, verified, sugar_offer)
    staff = make_client(staff_user)
    assert staff.get(S(shop, f"{order['id']}/")).status_code == 200
    assert staff.post(S(shop, f"{order['id']}/cancel/"), {"reason": "x"}, format="json").status_code == 403
    resp = staff.post(S(shop, f"{order['id']}/receive/"), receive_body(order, ["2"]), format="json")
    assert resp.status_code == 200


def test_a_shop_cannot_act_as_the_supplier(owner_client, shop, verified, sugar_offer):
    order = placed(owner_client, shop, sugar_offer)
    for action in ("confirm", "dispatch"):
        # the shop owner is not a member of the wholesaler
        assert act(owner_client, verified, order, action).status_code == 404
    assert owner_client.get(WO(verified)).status_code == 404
    assert Order.objects.get(pk=order["id"]).status == "submitted"


def test_a_supplier_cannot_see_or_act_on_another_suppliers_orders(
    owner_client, seller_client, rival, rival_user, shop, verified, sugar_offer
):
    order = placed(owner_client, shop, sugar_offer)
    rival_client = make_client(rival_user)
    assert rival_client.get(WO(rival)).json()["results"] == []
    assert rival_client.get(WO(rival, f"{order['id']}/")).status_code == 404
    assert rival_client.get(WO(verified)).status_code == 404  # not their workspace
    for action in ("confirm", "dispatch"):
        assert act(rival_client, rival, order, action).status_code == 404  # right workspace, wrong order
    assert act(rival_client, rival, order, "reject", reason="x").status_code == 404
    assert act(rival_client, rival, order, "cancel", reason="x").status_code == 404
    assert Order.objects.get(pk=order["id"]).status == "submitted"


def test_a_shop_cannot_see_or_act_on_another_shops_orders(
    owner_client, other_shop, other_user, shop, verified, sugar_offer
):
    order = placed(owner_client, shop, sugar_offer)
    intruder = make_client(other_user)
    assert intruder.get(S(other_shop)).json()["results"] == []
    assert intruder.get(S(shop)).status_code == 404
    assert intruder.get(S(other_shop, f"{order['id']}/")).status_code == 404
    assert intruder.post(S(other_shop, f"{order['id']}/cancel/"), {"reason": "x"}, format="json").status_code == 404
    assert intruder.post(S(other_shop, f"{order['id']}/receive/"), receive_body(order, ["2"]), format="json").status_code == 404
    assert Order.objects.get(pk=order["id"]).status == "submitted"


def test_conflict_of_interest_is_blocked_on_the_supplier_side(
    owner_client, seller_client, seller, shop, verified, sugar_offer
):
    """A person who belongs to the ordering shop must not confirm that shop's orders."""
    ShopMembership.objects.create(shop=shop, user=seller, role=ShopMembership.Role.STAFF)
    order = placed(owner_client, shop, sugar_offer)
    for action, body in (("confirm", {}), ("reject", {"reason": "x"}), ("cancel", {"reason": "x"})):
        assert act(seller_client, verified, order, action, **body).status_code == 403
    assert Order.objects.get(pk=order["id"]).status == "submitted"


def test_the_supplier_sees_only_what_it_needs_about_the_shop(owner_client, seller_client, shop, verified, sugar_offer, owner):
    order = placed(owner_client, shop, sugar_offer, contact_phone="0733000111")
    body = seller_client.get(WO(verified, f"{order['id']}/")).json()
    assert body["shop"] == {"name": "Amina Duka"}
    assert body["delivery_address"] == ADDRESS and body["contact_phone"] == "+254733000111"
    blob = str(body)
    assert str(shop.pk) not in blob and owner.phone_number not in blob and "Amina Owner" not in blob


def test_order_lists_filter_by_status(owner_client, seller_client, shop, verified, sugar_offer):
    a = placed(owner_client, shop, sugar_offer)
    b = placed(owner_client, shop, sugar_offer)
    act(seller_client, verified, b, "confirm")
    ids = lambda r: {o["id"] for o in r.json()["results"]}  # noqa: E731
    assert ids(owner_client.get(S(shop))) == {a["id"], b["id"]}
    assert ids(owner_client.get(S(shop), {"status": "confirmed"})) == {b["id"]}
    assert ids(seller_client.get(WO(verified), {"status": "submitted"})) == {a["id"]}
    act(seller_client, verified, a, "reject", reason="x")
    assert ids(seller_client.get(WO(verified), {"open": "true"})) == {b["id"]}
    newest_first = [o["id"] for o in owner_client.get(S(shop)).json()["results"]]
    assert newest_first == [b["id"], a["id"]]


# ------------------------------------------------------------------ receiving goods
def test_full_receipt_adds_stock_at_the_agreed_cost(
    owner_client, seller_client, shop, verified, sugar, sugar_offer
):
    inventory.track_product(shop=shop, product_id=sugar.product.pk)
    order = to_dispatched(owner_client, seller_client, shop, verified, sugar_offer, "2")
    resp = owner_client.post(S(shop, f"{order['id']}/receive/"), receive_body(order, ["2"], note="All good"), format="json")
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["has_shortage"] is False and body["receipt_note"] == "All good"
    assert body["items"][0]["received_quantity"] == "2.000000" and body["items"][0]["shortage"] == "0.000000"

    assert stock(shop, sugar.product) == D("100")  # 2 sacks x 50 kg
    receipt = PurchaseReceipt.objects.get(pk=body["purchase_receipt_id"])
    assert receipt.supplier_name == "Kisumu Wholesale" and receipt.total_cost == D("14000.00")
    [line_] = receipt.items.all()
    assert line_.unit_cost == D("7000.00") and line_.quantity_base == D("100")


def test_partial_delivery_records_the_shortage(
    owner_client, seller_client, shop, verified, sugar, sugar_offer
):
    order = to_dispatched(owner_client, seller_client, shop, verified, sugar_offer, "5")
    resp = owner_client.post(
        S(shop, f"{order['id']}/receive/"),
        receive_body(order, ["3"], note="2 sacks short"), format="json",
    )  # fmt: skip
    body = resp.json()
    assert resp.status_code == 200 and body["status"] == "received" and body["has_shortage"] is True
    assert body["items"][0]["shortage"] == "2.000000"
    assert stock(shop, sugar.product) == D("150")  # only what arrived
    assert PurchaseReceipt.objects.get().total_cost == D("21000.00")
    event = AuditEvent.objects.get(action="order.received")
    assert event.changes["shortages"] == [
        {"offer_id": str(sugar_offer.pk), "ordered": "5", "received": "3", "short": "2"}
    ]
    assert event.changes["note"] == "2 sacks short"


def test_nothing_arriving_closes_the_order_without_inventing_stock(
    owner_client, seller_client, shop, verified, sugar, sugar_offer
):
    order = to_dispatched(owner_client, seller_client, shop, verified, sugar_offer)
    body = owner_client.post(S(shop, f"{order['id']}/receive/"), receive_body(order, ["0"]), format="json").json()
    assert body["status"] == "received" and body["has_shortage"] is True
    assert body["purchase_receipt_id"] is None
    assert not PurchaseReceipt.objects.exists()
    assert not ShopProduct.objects.filter(shop=shop).exists()  # nothing tracked either


def test_receiving_more_than_ordered_is_refused_and_changes_nothing(
    owner_client, seller_client, shop, verified, sugar, sugar_offer
):
    order = to_dispatched(owner_client, seller_client, shop, verified, sugar_offer, "2")
    resp = owner_client.post(S(shop, f"{order['id']}/receive/"), receive_body(order, ["3"]), format="json")
    assert resp.status_code == 400 and resp.json()["error"]["code"] == "over_received"
    stored = Order.objects.get(pk=order["id"])
    assert stored.status == "dispatched" and stored.items.get().received_quantity is None
    assert not PurchaseReceipt.objects.exists() and not ShopProduct.objects.filter(shop=shop).exists()


def test_every_line_must_be_accounted_for(
    owner_client, seller_client, shop, verified, sugar_offer, flour_offer
):
    order = placed_two = owner_client.post(
        S(shop),
        {"idempotency_key": str(uuid4()), "delivery_address": ADDRESS,
         "items": [line(sugar_offer, "1"), line(flour_offer, "10")]},
        format="json",
    ).json()  # fmt: skip
    act(seller_client, verified, order, "confirm")
    act(seller_client, verified, order, "dispatch")
    url = S(shop, f"{order['id']}/receive/")

    partial = receive_body(order, ["1", "10"])
    partial["items"] = partial["items"][:1]
    assert owner_client.post(url, partial, format="json").json()["error"]["code"] == "incomplete_receipt"

    stranger = receive_body(order, ["1", "10"])
    stranger["items"][1]["item_id"] = str(uuid4())
    assert owner_client.post(url, stranger, format="json").json()["error"]["code"] == "item_not_in_order"

    twice = receive_body(order, ["1", "10"])
    twice["items"][1]["item_id"] = twice["items"][0]["item_id"]
    assert owner_client.post(url, twice, format="json").json()["error"]["code"] == "duplicate_item"
    assert Order.objects.get(pk=placed_two["id"]).status == "dispatched"


def test_receiving_is_idempotent(owner_client, seller_client, shop, verified, sugar, sugar_offer):
    order = to_dispatched(owner_client, seller_client, shop, verified, sugar_offer, "2")
    body = receive_body(order, ["2"])
    url = S(shop, f"{order['id']}/receive/")
    first = owner_client.post(url, body, format="json")
    again = owner_client.post(url, body, format="json")
    assert first.status_code == again.status_code == 200
    assert again["Idempotent-Replayed"] == "true"
    assert stock(shop, sugar.product) == D("100")  # not 200
    assert PurchaseReceipt.objects.count() == 1

    clash = owner_client.post(url, {**body, "items": receive_body(order, ["1"])["items"]}, format="json")
    assert clash.status_code == 409 and clash.json()["error"]["code"] == "idempotency_conflict"
    assert stock(shop, sugar.product) == D("100")


def test_receiving_tracks_a_new_product_and_adds_to_existing_stock(
    owner_client, seller_client, shop, verified, owner, sugar, flour, sugar_offer, flour_offer
):
    # flour is already tracked with some stock; sugar is new to the shop
    flour_item = inventory.track_product(shop=shop, product_id=flour.product.pk)
    inventory.record_opening_stock(
        shop=shop, user=owner, shop_product_id=flour_item.pk, unit_id=flour.kg.pk, quantity=D("30")
    )
    order = owner_client.post(
        S(shop),
        {"idempotency_key": str(uuid4()), "delivery_address": ADDRESS,
         "items": [line(sugar_offer, "1"), line(flour_offer, "20")]},
        format="json",
    ).json()  # fmt: skip
    act(seller_client, verified, order, "confirm")
    act(seller_client, verified, order, "dispatch")
    by_name = {i["product_name"]: i["id"] for i in order["items"]}
    resp = owner_client.post(
        S(shop, f"{order['id']}/receive/"),
        {"idempotency_key": str(uuid4()),
         "items": [{"item_id": by_name["Sugar"], "received_quantity": "1"},
                   {"item_id": by_name["Maize flour"], "received_quantity": "20"}]},
        format="json",
    )  # fmt: skip
    assert resp.status_code == 200, resp.content
    assert stock(shop, sugar.product) == D("50")  # newly tracked, only what arrived
    assert stock(shop, flour.product) == D("50")  # 30 + 20
    assert AuditEvent.objects.filter(action="product.tracked", shop=shop).count() == 2


def test_an_order_placed_before_a_unit_edit_still_receives(
    owner_client, seller_client, shop, verified, sugar, sugar_offer
):
    """Snapshots, not live catalogue rows, drive what is recorded as received."""
    order = to_dispatched(owner_client, seller_client, shop, verified, sugar_offer, "1")
    resp = owner_client.post(S(shop, f"{order['id']}/receive/"), receive_body(order, ["1"]), format="json")
    assert resp.status_code == 200
    assert stock(shop, sugar.product) == D("50")


def test_the_received_stock_shows_in_the_shops_movement_history(
    owner_client, seller_client, shop, verified, sugar, sugar_offer
):
    order = to_dispatched(owner_client, seller_client, shop, verified, sugar_offer, "1")
    owner_client.post(S(shop, f"{order['id']}/receive/"), receive_body(order, ["1"]), format="json")
    moves = owner_client.get(f"/api/v1/shops/{shop.pk}/stock-movements/").json()["results"]
    assert [m["movement_type"] for m in moves] == ["purchase_receipt"]


def test_a_bad_line_leaves_the_earlier_lines_untouched(
    owner_client, seller_client, shop, verified, sugar, flour, sugar_offer, flour_offer
):
    """All-or-nothing: line 1 is fine, line 2 over-receives -> nothing is recorded at all."""
    order = owner_client.post(
        S(shop),
        {"idempotency_key": str(uuid4()), "delivery_address": ADDRESS,
         "items": [line(sugar_offer, "1"), line(flour_offer, "10")]},
        format="json",
    ).json()  # fmt: skip
    act(seller_client, verified, order, "confirm")
    act(seller_client, verified, order, "dispatch")
    by_name = {i["product_name"]: i["id"] for i in order["items"]}
    resp = owner_client.post(
        S(shop, f"{order['id']}/receive/"),
        {"idempotency_key": str(uuid4()),
         "items": [{"item_id": by_name["Sugar"], "received_quantity": "1"},
                   {"item_id": by_name["Maize flour"], "received_quantity": "11"}]},
        format="json",
    )  # fmt: skip
    assert resp.status_code == 400 and resp.json()["error"]["code"] == "over_received"
    stored = Order.objects.get(pk=order["id"])
    assert stored.status == "dispatched"
    assert all(i.received_quantity is None for i in stored.items.all())
    assert not PurchaseReceipt.objects.exists() and not ShopProduct.objects.filter(shop=shop).exists()
