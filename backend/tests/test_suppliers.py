from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounts.models import User
from apps.audit.models import AuditEvent
from apps.catalog import services as catalog_services
from apps.catalog.models import ProductUnit
from apps.suppliers import services
from apps.suppliers.models import SupplierOffer, Wholesaler, WholesalerMembership

from .conftest import PASSWORD, make_client

pytestmark = pytest.mark.django_db

D = Decimal


# ------------------------------------------------------------------ fixtures & helpers
@pytest.fixture
def admin_user():
    return User.objects.create_user("0700000001", PASSWORD, full_name="Admin", is_staff=True)


@pytest.fixture
def admin_client(admin_user):
    return make_client(admin_user)


@pytest.fixture
def seller():
    return User.objects.create_user("0711111111", PASSWORD, full_name="Wanjiku Seller")


@pytest.fixture
def seller_client(seller):
    return make_client(seller)


@pytest.fixture
def wholesaler(seller):
    return services.register_wholesaler(
        seller, business_name="Kisumu Wholesale", contact_phone="0711000000",
        location_text="Kisumu",
    )  # fmt: skip


@pytest.fixture
def verified(wholesaler, admin_user):
    return services.verify_wholesaler(wholesaler_id=wholesaler.pk, actor=admin_user, note="ok")


@pytest.fixture
def rival_user():
    return User.objects.create_user("0744444444", PASSWORD, full_name="Rival Seller")


@pytest.fixture
def rival(rival_user, admin_user):
    w = services.register_wholesaler(
        rival_user, business_name="Rival Traders", contact_phone="0744000000"
    )
    return services.verify_wholesaler(wholesaler_id=w.pk, actor=admin_user)


def W(w, suffix=""):
    return f"/api/v1/wholesalers/{w.pk}/{suffix}"


def offer_body(item, **extra):
    unit = getattr(item, "sack", None) or item.kg  # sugar has a sack; flour only kg
    return {
        "product_id": str(item.product.pk),
        "product_unit_id": str(unit.pk),
        "price_per_unit": "7000.00",
        "minimum_order_quantity": "1",
        **extra,
    }


def make_offer(client, w, sugar, **extra):
    resp = client.post(W(w, "offers/"), offer_body(sugar, **extra), format="json")
    assert resp.status_code == 201, resp.content
    return resp.json()


def market(client, **params):
    resp = client.get("/api/v1/marketplace/offers/", params)
    assert resp.status_code == 200, resp.content
    return resp.json()["results"]


# ------------------------------------------------------------------ profiles
def test_registering_creates_a_pending_wholesaler_owned_by_the_caller(seller_client, seller):
    resp = seller_client.post(
        "/api/v1/wholesalers/",
        {"business_name": "Nyanza Foods", "contact_phone": "0722 111 222", "location_text": "Kisumu"},
        format="json",
    )
    assert resp.status_code == 201, resp.content
    body = resp.json()
    assert body["verification_status"] == "pending" and body["my_role"] == "owner"
    assert body["contact_phone"] == "+254722111222"
    w = Wholesaler.objects.get(pk=body["id"])
    assert w.memberships.get().user == seller
    assert AuditEvent.objects.filter(wholesaler=w, action="supplier.registered").count() == 1


def test_a_bad_phone_number_is_rejected(seller_client):
    resp = seller_client.post(
        "/api/v1/wholesalers/", {"business_name": "X", "contact_phone": "abc"}, format="json"
    )
    assert resp.status_code == 400 and resp.json()["error"]["code"] == "invalid_phone"


def test_a_wholesaler_cannot_verify_itself_through_its_profile(seller_client, wholesaler):
    resp = seller_client.patch(
        W(wholesaler),
        {"verification_status": "verified", "verified_at": "2026-01-01T00:00:00Z",
         "business_name": "Renamed"},
        format="json",
    )  # fmt: skip
    assert resp.status_code == 200
    wholesaler.refresh_from_db()
    assert wholesaler.business_name == "Renamed"
    assert wholesaler.verification_status == "pending" and wholesaler.verified_at is None


def test_profile_edit_is_audited_with_before_and_after(seller_client, wholesaler):
    seller_client.patch(W(wholesaler), {"location_text": "Kondele"}, format="json")
    event = AuditEvent.objects.get(wholesaler=wholesaler, action="supplier.updated")
    assert event.changes == {"before": {"location_text": "Kisumu"}, "after": {"location_text": "Kondele"}}


def test_non_members_get_404_and_staff_get_403(seller_client, wholesaler, rival_user):
    assert make_client(rival_user).get(W(wholesaler)).status_code == 404
    staff = User.objects.create_user("0755555555", PASSWORD, full_name="Staffer")
    WholesalerMembership.objects.create(
        wholesaler=wholesaler, user=staff, role=WholesalerMembership.Role.STAFF
    )
    staff_client = make_client(staff)
    assert staff_client.get(W(wholesaler)).status_code == 200
    assert staff_client.patch(W(wholesaler), {"business_name": "Hax"}, format="json").status_code == 403
    assert staff_client.get(W(wholesaler, "audit-events/")).status_code == 403


def test_only_the_owner_can_add_members_and_the_audit_has_no_phone(seller_client, wholesaler, rival_user):
    resp = seller_client.post(
        W(wholesaler, "members/"), {"phone_number": rival_user.phone_number, "role": "manager"},
        format="json",
    )  # fmt: skip
    assert resp.status_code == 201
    event = AuditEvent.objects.get(wholesaler=wholesaler, action="supplier.member_added")
    assert rival_user.phone_number not in str(event.changes)
    # the new manager can manage offers but not add members
    manager = make_client(rival_user)
    assert manager.post(
        W(wholesaler, "members/"), {"phone_number": "0711111111", "role": "staff"}, format="json"
    ).status_code == 403  # fmt: skip


def test_my_wholesalers_lists_only_mine(seller_client, wholesaler, rival):
    ids = [w["id"] for w in seller_client.get("/api/v1/wholesalers/").json()]
    assert ids == [str(wholesaler.pk)]


# ------------------------------------------------------------------ verification
def test_pending_list_and_verify_are_admin_only(seller_client, admin_client, wholesaler):
    assert seller_client.get("/api/v1/admin/suppliers/pending/").status_code == 403
    for action in ("verify", "suspend"):
        url = f"/api/v1/admin/suppliers/{wholesaler.pk}/{action}/"
        assert seller_client.post(url, {"note": "x"}, format="json").status_code == 403
    pending = admin_client.get("/api/v1/admin/suppliers/pending/").json()["results"]
    assert [p["id"] for p in pending] == [str(wholesaler.pk)]


def test_unauthenticated_cannot_reach_admin_or_marketplace(wholesaler):
    from rest_framework.test import APIClient

    anon = APIClient()
    assert anon.get("/api/v1/admin/suppliers/pending/").status_code == 401
    assert anon.get("/api/v1/marketplace/offers/").status_code == 401


def test_verify_then_suspend_then_reinstate_is_audited(admin_client, admin_user, wholesaler):
    base = f"/api/v1/admin/suppliers/{wholesaler.pk}/"
    assert admin_client.post(base + "verify/", {"note": "ID seen"}, format="json").status_code == 200
    wholesaler.refresh_from_db()
    assert wholesaler.is_verified and wholesaler.verified_at is not None

    assert admin_client.post(base + "verify/", {}, format="json").status_code == 409
    assert admin_client.post(base + "suspend/", {}, format="json").status_code == 400  # reason needed
    assert admin_client.post(base + "suspend/", {"note": "complaints"}, format="json").status_code == 200
    assert admin_client.post(base + "verify/", {"note": "resolved"}, format="json").status_code == 200

    actions = list(
        AuditEvent.objects.filter(wholesaler=wholesaler)
        .exclude(action="supplier.registered")
        .order_by("created_at", "id")
        .values_list("action", flat=True)
    )
    assert actions == ["supplier.verified", "supplier.suspended", "supplier.verified"]
    suspended = AuditEvent.objects.get(action="supplier.suspended")
    assert suspended.actor == admin_user and suspended.shop is None
    assert suspended.changes["before"] == {"verification_status": "verified"}
    assert suspended.changes["note"] == "complaints"


def test_verification_note_is_visible_to_the_supplier_but_not_to_shops(
    admin_client, seller_client, owner_client, wholesaler
):
    admin_client.post(
        f"/api/v1/admin/suppliers/{wholesaler.pk}/verify/", {"note": "internal remark"}, format="json"
    )
    assert seller_client.get(W(wholesaler)).json()["status_note"] == "internal remark"
    public = owner_client.get(f"/api/v1/marketplace/wholesalers/{wholesaler.pk}/").json()
    assert "internal remark" not in str(public) and "verification_note" not in public


# ------------------------------------------------------------------ offers: gating
def test_unverified_wholesaler_can_draft_but_not_publish(seller_client, wholesaler, sugar):
    resp = seller_client.post(W(wholesaler, "offers/"), offer_body(sugar), format="json")
    assert resp.status_code == 409 and resp.json()["error"]["code"] == "supplier_not_verified"

    draft = make_offer(seller_client, wholesaler, sugar, is_active=False)
    assert draft["is_active"] is False
    activate = seller_client.patch(
        W(wholesaler, f"offers/{draft['id']}/"), {"is_active": True}, format="json"
    )
    assert activate.status_code == 409 and activate.json()["error"]["code"] == "supplier_not_verified"


def test_activation_works_after_verification(seller_client, wholesaler, admin_user, sugar):
    draft = make_offer(seller_client, wholesaler, sugar, is_active=False)
    services.verify_wholesaler(wholesaler_id=wholesaler.pk, actor=admin_user)
    resp = seller_client.patch(
        W(wholesaler, f"offers/{draft['id']}/"), {"is_active": True}, format="json"
    )
    assert resp.status_code == 200 and resp.json()["is_active"] is True


def test_suspended_wholesaler_cannot_publish(seller_client, verified, admin_user, sugar):
    services.suspend_wholesaler(wholesaler_id=verified.pk, actor=admin_user, note="x")
    resp = seller_client.post(W(verified, "offers/"), offer_body(sugar), format="json")
    assert resp.status_code == 409


def test_verification_can_be_switched_off_for_the_pilot(settings, seller_client, wholesaler, sugar):
    settings.SUPPLIER_VERIFICATION_REQUIRED = False
    assert make_offer(seller_client, wholesaler, sugar)["is_active"] is True
    assert len(market(seller_client)) == 1  # pending wholesalers show up when not required


# ------------------------------------------------------------------ offers: rules
def test_create_offer_with_tiers_and_per_base_unit_price(seller_client, verified, sugar):
    data = make_offer(
        seller_client, verified, sugar,
        tiers=[{"minimum_quantity": "10", "unit_price": "6800.00"},
               {"minimum_quantity": "5", "unit_price": "6900.00"}],
        delivery_areas="Kisumu, Kakamega", delivery_terms="Free above 10 sacks",
    )  # fmt: skip
    assert data["price_per_base_unit"] == "140.0000"  # 7,000 / 50 kg
    assert [t["minimum_quantity"] for t in data["tiers"]] == ["5.000000", "10.000000"]
    assert data["unit"]["unit_name"] == "50 kg sack" and data["updated_at"]


@pytest.mark.parametrize(
    "extra",
    [
        {"price_per_unit": "0"},
        {"price_per_unit": "-5"},
        {"minimum_order_quantity": "0"},
        {"available_quantity": "-1"},
    ],
)
def test_nonsense_numbers_are_rejected(seller_client, verified, sugar, extra):
    resp = seller_client.post(W(verified, "offers/"), offer_body(sugar, **extra), format="json")
    assert resp.status_code == 400


@pytest.mark.parametrize(
    "tiers",
    [
        [{"minimum_quantity": "1", "unit_price": "6500"}],  # not above the MOQ
        [{"minimum_quantity": "5", "unit_price": "7000"}],  # not cheaper than base
        [{"minimum_quantity": "5", "unit_price": "7500"}],  # dearer than base
        [{"minimum_quantity": "5", "unit_price": "6900"}, {"minimum_quantity": "5", "unit_price": "6800"}],
    ],
)
def test_invalid_tiers_are_rejected(seller_client, verified, sugar, tiers):
    resp = seller_client.post(W(verified, "offers/"), offer_body(sugar, tiers=tiers), format="json")
    assert resp.status_code == 400 and resp.json()["error"]["code"] == "invalid_tier"


def test_only_shared_products_and_purchase_units_can_be_offered(
    seller_client, verified, sugar, shop, flour
):
    custom = catalog_services.create_custom_product(shop=shop, name="Shop special", base_unit="kg")
    resp = seller_client.post(
        W(verified, "offers/"),
        {**offer_body(sugar), "product_id": str(custom.pk), "product_unit_id": str(custom.units.get().pk)},
        format="json",
    )
    assert resp.status_code == 400 and resp.json()["error"]["code"] == "product_not_found"

    # a unit that belongs to a different product
    resp = seller_client.post(
        W(verified, "offers/"),
        {**offer_body(sugar), "product_unit_id": str(flour.kg.pk)}, format="json",
    )  # fmt: skip
    assert resp.status_code == 400 and resp.json()["error"]["code"] == "invalid_unit"

    ProductUnit.objects.filter(pk=sugar.sack.pk).update(is_purchase_unit=False)
    resp = seller_client.post(W(verified, "offers/"), offer_body(sugar), format="json")
    assert resp.status_code == 400 and resp.json()["error"]["code"] == "invalid_unit"


def test_one_live_offer_per_product_and_unit(seller_client, verified, sugar):
    first = make_offer(seller_client, verified, sugar)
    again = seller_client.post(W(verified, "offers/"), offer_body(sugar), format="json")
    assert again.status_code == 409 and again.json()["error"]["code"] == "state_conflict"

    make_offer(seller_client, verified, sugar, is_active=False)  # drafts may coexist
    # ... but re-activating one while another is live is refused
    draft = SupplierOffer.objects.filter(wholesaler=verified, is_active=False).get()
    resp = seller_client.patch(W(verified, f"offers/{draft.pk}/"), {"is_active": True}, format="json")
    assert resp.status_code == 409

    # retiring the first frees the slot
    seller_client.patch(W(verified, f"offers/{first['id']}/"), {"is_active": False}, format="json")
    assert seller_client.patch(
        W(verified, f"offers/{draft.pk}/"), {"is_active": True}, format="json"
    ).status_code == 200  # fmt: skip


def test_price_change_is_audited_and_bumps_the_timestamp(seller_client, verified, sugar):
    offer = make_offer(seller_client, verified, sugar)
    resp = seller_client.patch(
        W(verified, f"offers/{offer['id']}/"), {"price_per_unit": "7200.00"}, format="json"
    )
    assert resp.status_code == 200 and resp.json()["price_per_unit"] == "7200.00"
    assert resp.json()["updated_at"] > offer["updated_at"]
    event = AuditEvent.objects.get(wholesaler=verified, action="offer.updated")
    assert event.changes == {
        "before": {"price_per_unit": "7000"}, "after": {"price_per_unit": "7200"}
    }


def test_the_product_and_unit_of_an_offer_cannot_be_changed(seller_client, verified, sugar, flour):
    offer = make_offer(seller_client, verified, sugar)
    seller_client.patch(
        W(verified, f"offers/{offer['id']}/"),
        {"product_id": str(flour.product.pk), "product_unit_id": str(flour.kg.pk)}, format="json",
    )  # fmt: skip
    stored = SupplierOffer.objects.get(pk=offer["id"])
    assert stored.product_id == sugar.product.pk and stored.product_unit_id == sugar.sack.pk


def test_price_cannot_drop_below_an_existing_tier(seller_client, verified, sugar):
    offer = make_offer(
        seller_client, verified, sugar, tiers=[{"minimum_quantity": "10", "unit_price": "6800"}]
    )
    resp = seller_client.patch(
        W(verified, f"offers/{offer['id']}/"), {"price_per_unit": "6700"}, format="json"
    )
    assert resp.status_code == 400 and resp.json()["error"]["code"] == "invalid_tier"


def test_replacing_tiers_is_audited_and_empty_removes_all(seller_client, verified, sugar):
    offer = make_offer(seller_client, verified, sugar)
    url = W(verified, f"offers/{offer['id']}/tiers/")
    resp = seller_client.put(
        url, {"tiers": [{"minimum_quantity": "10", "unit_price": "6800"}]}, format="json"
    )
    assert resp.status_code == 200 and len(resp.json()["tiers"]) == 1
    assert seller_client.put(url, {"tiers": []}, format="json").json()["tiers"] == []
    events = AuditEvent.objects.filter(action="offer.tiers_replaced").order_by("created_at", "id")
    assert events.count() == 2 and events.first().changes["before"] == {"tiers": []}


def test_staff_can_read_but_not_write_offers(verified, sugar, seller_client):
    offer = make_offer(seller_client, verified, sugar)
    staff = User.objects.create_user("0766666666", PASSWORD, full_name="Staffer")
    WholesalerMembership.objects.create(
        wholesaler=verified, user=staff, role=WholesalerMembership.Role.STAFF
    )
    client = make_client(staff)
    assert client.get(W(verified, "offers/")).status_code == 200
    assert client.post(W(verified, "offers/"), offer_body(sugar), format="json").status_code == 403
    assert client.patch(
        W(verified, f"offers/{offer['id']}/"), {"price_per_unit": "1"}, format="json"
    ).status_code == 403  # fmt: skip


# ------------------------------------------------------------------ isolation between suppliers
def test_a_supplier_cannot_see_or_change_another_suppliers_offers(
    seller_client, verified, rival, rival_user, sugar
):
    mine = make_offer(seller_client, verified, sugar)
    rival_client = make_client(rival_user)

    # no membership -> 404 on the other wholesaler's workspace
    assert rival_client.get(W(verified, "offers/")).status_code == 404
    assert rival_client.get(W(verified, f"offers/{mine['id']}/")).status_code == 404
    assert rival_client.patch(
        W(verified, f"offers/{mine['id']}/"), {"price_per_unit": "1"}, format="json"
    ).status_code == 404  # fmt: skip

    # ... and addressing it through their OWN workspace finds nothing either
    for call in (
        lambda: rival_client.get(W(rival, f"offers/{mine['id']}/")),
        lambda: rival_client.patch(
            W(rival, f"offers/{mine['id']}/"), {"price_per_unit": "1"}, format="json"
        ),
        lambda: rival_client.put(
            W(rival, f"offers/{mine['id']}/tiers/"), {"tiers": []}, format="json"
        ),
    ):
        assert call().status_code in (400, 404)
    assert SupplierOffer.objects.get(pk=mine["id"]).price_per_unit == D("7000.00")
    assert rival_client.get(W(rival, "offers/")).json()["results"] == []


def test_audit_trails_are_per_wholesaler(seller_client, verified, rival, rival_user, sugar):
    make_offer(seller_client, verified, sugar)
    mine = seller_client.get(W(verified, "audit-events/")).json()["results"]
    assert any(e["action"] == "offer.created" for e in mine)
    theirs = make_client(rival_user).get(W(rival, "audit-events/")).json()["results"]
    assert {e["id"] for e in mine}.isdisjoint({e["id"] for e in theirs})
    assert make_client(rival_user).get(W(verified, "audit-events/")).status_code == 404


# ------------------------------------------------------------------ marketplace
def test_only_live_offers_of_verified_wholesalers_are_listed(
    seller_client, owner_client, wholesaler, admin_user, sugar, flour
):
    make_offer(seller_client, wholesaler, sugar, is_active=False)  # draft, unverified
    assert market(owner_client) == []

    services.verify_wholesaler(wholesaler_id=wholesaler.pk, actor=admin_user)
    assert market(owner_client) == []  # still only a draft
    live = make_offer(seller_client, wholesaler, flour, product_id=str(flour.product.pk),
                      product_unit_id=str(flour.kg.pk), price_per_unit="150")  # fmt: skip
    assert [o["id"] for o in market(owner_client)] == [live["id"]]

    services.suspend_wholesaler(wholesaler_id=wholesaler.pk, actor=admin_user, note="x")
    assert market(owner_client) == []  # vanishes without anyone editing the offer
    assert owner_client.get(f"/api/v1/marketplace/offers/{live['id']}/").status_code == 404

    services.verify_wholesaler(wholesaler_id=wholesaler.pk, actor=admin_user)
    assert len(market(owner_client)) == 1  # and returns on reinstatement


def test_offers_are_compared_per_base_unit_across_pack_sizes(
    owner_client, seller_client, verified, rival, rival_user, sugar
):
    packet = ProductUnit.objects.create(product=sugar.product, unit_name="2 kg packet", base_quantity=D("2"))
    sack = make_offer(seller_client, verified, sugar, price_per_unit="7000")  # 140/kg
    rival_client = make_client(rival_user)
    pk = make_offer(rival_client, rival, sugar, product_unit_id=str(packet.pk), price_per_unit="270")  # 135/kg
    dear = make_offer(rival_client, rival, sugar, price_per_unit="7500")  # 150/kg

    ranked = market(owner_client, product_id=str(sugar.product.pk))
    assert [o["id"] for o in ranked] == [pk["id"], sack["id"], dear["id"]]
    assert [o["price_per_base_unit"] for o in ranked] == ["135.0000", "140.0000", "150.0000"]
    assert ranked[0]["wholesaler"]["business_name"] == "Rival Traders"
    assert ranked[0]["updated_at"]


def test_marketplace_filters(owner_client, seller_client, verified, sugar, flour):
    a = make_offer(seller_client, verified, sugar, delivery_areas="Kisumu, Siaya")
    b = make_offer(
        seller_client, verified, flour, product_id=str(flour.product.pk),
        product_unit_id=str(flour.kg.pk), price_per_unit="150", availability="out_of_stock",
    )  # fmt: skip
    ids = lambda **p: {o["id"] for o in market(owner_client, **p)}  # noqa: E731
    assert ids() == {a["id"], b["id"]}
    assert ids(q="sugar") == {a["id"]} and ids(q="kisumu wholesale") == {a["id"], b["id"]}
    assert ids(area="siaya") == {a["id"]} and ids(area="nairobi") == set()
    assert ids(available="true") == {a["id"]}
    assert ids(product_id=str(flour.product.pk)) == {b["id"]}
    assert owner_client.get("/api/v1/marketplace/offers/", {"product_id": "nope"}).status_code == 400


def test_expired_and_future_tiers_are_hidden_and_not_applied(owner_client, seller_client, verified, sugar):
    now = timezone.now()
    offer = make_offer(
        seller_client, verified, sugar,
        tiers=[
            {"minimum_quantity": "5", "unit_price": "6900"},
            {"minimum_quantity": "10", "unit_price": "6000", "valid_until": (now - timedelta(days=1)).isoformat()},
            {"minimum_quantity": "20", "unit_price": "5000", "valid_from": (now + timedelta(days=1)).isoformat()},
        ],
    )  # fmt: skip
    shown = market(owner_client)[0]["tiers"]
    assert [t["unit_price"] for t in shown] == ["6900.00"]

    def quote(qty):
        return owner_client.get(f"/api/v1/marketplace/offers/{offer['id']}/quote/", {"quantity": qty}).json()

    assert quote("12")["unit_price"] == "6900.00"  # expired 6,000 and future 5,000 ignored
    assert quote("2")["unit_price"] == "7000.00"


def test_quote_applies_tiers_and_flags_the_minimum(owner_client, seller_client, verified, sugar):
    offer = make_offer(
        seller_client, verified, sugar, minimum_order_quantity="2",
        tiers=[{"minimum_quantity": "10", "unit_price": "6800"}],
    )  # fmt: skip
    url = f"/api/v1/marketplace/offers/{offer['id']}/quote/"
    base = owner_client.get(url, {"quantity": "2"}).json()
    assert base["unit_price"] == "7000.00" and base["line_total"] == "14000.00"
    assert base["meets_minimum"] is True and base["quantity_base"] == "100.000000"
    tier = owner_client.get(url, {"quantity": "10"}).json()
    assert tier["unit_price"] == "6800.00" and tier["line_total"] == "68000.00"
    assert owner_client.get(url, {"quantity": "1"}).json()["meets_minimum"] is False
    assert owner_client.get(url, {"quantity": "0"}).status_code == 400
    assert owner_client.get(url, {"quantity": "abc"}).status_code == 400
    for bad in ("Infinity", "NaN", "-Infinity", "1e30"):
        assert owner_client.get(url, {"quantity": bad}).status_code == 400, bad
    assert owner_client.get(url).status_code == 400


def test_marketplace_wholesalers_only_verified_with_offer_counts(
    owner_client, seller_client, verified, rival_user, sugar, admin_user
):
    pending = services.register_wholesaler(rival_user, business_name="Pending Co", contact_phone="0744000000")
    make_offer(seller_client, verified, sugar)
    make_offer(seller_client, verified, sugar, is_active=False)
    rows = owner_client.get("/api/v1/marketplace/wholesalers/").json()["results"]
    assert [(r["business_name"], r["offer_count"]) for r in rows] == [("Kisumu Wholesale", 1)]
    assert owner_client.get(f"/api/v1/marketplace/wholesalers/{pending.pk}/").status_code == 404
    detail = owner_client.get(f"/api/v1/marketplace/wholesalers/{verified.pk}/").json()
    assert detail["offer_count"] == 1 and "my_role" not in detail
    assert owner_client.get("/api/v1/marketplace/wholesalers/", {"q": "zzz"}).json()["results"] == []


def test_marketplace_never_exposes_members_or_drafts(owner_client, seller_client, verified, seller, sugar):
    make_offer(seller_client, verified, sugar)
    blob = str(owner_client.get("/api/v1/marketplace/offers/").json()) + str(
        owner_client.get("/api/v1/marketplace/wholesalers/").json()
    )
    assert seller.phone_number not in blob and "Wanjiku" not in blob


def test_a_shops_private_product_never_reaches_the_marketplace_even_if_an_offer_exists(
    owner_client, verified, shop
):
    """Creation already refuses custom products; this proves the read side holds on its own
    (e.g. against bad data or a future code path that skips the service)."""
    custom = catalog_services.create_custom_product(shop=shop, name="Private blend", base_unit="kg")
    SupplierOffer.objects.create(
        wholesaler=verified, product=custom, product_unit=custom.units.get(),
        price_per_unit=D("100"), is_active=True,
    )  # fmt: skip
    assert market(owner_client) == []
