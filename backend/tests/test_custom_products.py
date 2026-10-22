from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from apps.catalog.models import Product
from apps.inventory import services
from apps.inventory.models import ShopProduct

from .conftest import make_client

pytestmark = pytest.mark.django_db

D = Decimal


def url(shop, suffix=""):
    return f"/api/v1/shops/{shop.pk}/products/{suffix}"


def body(**extra):
    return {
        "idempotency_key": str(uuid4()),
        "name": "Mandazi mix",
        "base_unit": "kg",
        "units": [{"unit_name": "2 kg packet", "base_quantity": "2"}],
        **extra,
    }


def create(client, shop, **extra):
    return client.post(url(shop), body(**extra), format="json")


# ------------------------------------------------------------------ creation
def test_create_tracks_it_and_creates_units(owner_client, shop):
    resp = create(owner_client, shop, reorder_level_base="5")
    assert resp.status_code == 201, resp.content
    data = resp.json()
    assert data["name"] == "Mandazi mix"
    assert {u["unit_name"]: u["base_quantity"] for u in data["units"]} == {
        "kg": "1.000000",
        "2 kg packet": "2.000000",
    }
    item = ShopProduct.objects.get(pk=data["shop_product_id"])
    assert item.shop == shop and item.reorder_level_base == D("5")
    assert Product.objects.get(pk=data["id"]).owner_shop == shop


def test_can_create_without_tracking(owner_client, shop):
    data = create(owner_client, shop, track=False).json()
    assert data["shop_product_id"] is None
    assert not ShopProduct.objects.filter(shop=shop).exists()


def test_a_new_custom_product_is_usable_straight_away(owner_client, shop, owner):
    data = create(owner_client, shop).json()
    packet = next(u for u in data["units"] if u["unit_name"] == "2 kg packet")
    receipt = services.record_purchase_receipt(
        shop=shop, user=owner,
        items=[{"product_id": UUID(data["id"]), "product_unit_id": UUID(packet["id"]),
                "quantity": D("3")}],
    )  # fmt: skip
    assert receipt.items.get().quantity_base == D("6")
    assert ShopProduct.objects.get(pk=data["shop_product_id"]).quantity_base == D("6")


def test_create_is_idempotent(owner_client, shop):
    payload = body()
    first = owner_client.post(url(shop), payload, format="json")
    replay = owner_client.post(url(shop), payload, format="json")
    assert replay.status_code == 201 and replay["Idempotent-Replayed"] == "true"
    assert replay.json()["id"] == first.json()["id"]
    assert Product.objects.filter(owner_shop=shop).count() == 1


# ------------------------------------------------------------------ duplicate protection
def test_cannot_shadow_a_shared_catalogue_product(owner_client, shop, sugar):
    resp = create(owner_client, shop, name="  SUGAR ", base_unit="kg", units=[])
    assert resp.status_code == 409
    err = resp.json()["error"]
    assert err["code"] == "matches_catalogue_product"
    assert str(sugar.product.pk) in err["message"]
    assert not Product.objects.filter(owner_shop=shop).exists()


def test_cannot_shadow_a_shared_barcode(owner_client, shop):
    Product.objects.create(name="Brookside Milk", base_unit="piece", barcode="6161100")
    resp = create(owner_client, shop, name="My milk", base_unit="piece", barcode="6161100", units=[])
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "matches_catalogue_product"


def test_same_name_with_a_different_brand_is_allowed(owner_client, shop, sugar):
    resp = create(owner_client, shop, name="Sugar", brand="Mumias Gold", units=[])
    assert resp.status_code == 201


def test_no_duplicate_custom_product_in_one_shop(owner_client, shop):
    assert create(owner_client, shop).status_code == 201
    again = create(owner_client, shop, name="mandazi MIX")
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "state_conflict"
    assert Product.objects.filter(owner_shop=shop).count() == 1


def test_two_shops_may_have_the_same_custom_name(owner_client, other_user, other_shop, shop):
    assert create(owner_client, shop).status_code == 201
    assert create(make_client(other_user), other_shop).status_code == 201


@pytest.mark.parametrize(
    "units",
    [
        [{"unit_name": "bad", "base_quantity": "0"}],
        [{"unit_name": "bad", "base_quantity": "-2"}],
        [{"unit_name": "kg", "base_quantity": "1"}],  # duplicates the base unit
        [{"unit_name": "Packet", "base_quantity": "2"}, {"unit_name": "packet", "base_quantity": "3"}],
        [{"unit_name": "   ", "base_quantity": "2"}],
    ],
)
def test_invalid_units_are_rejected_and_nothing_is_created(owner_client, shop, units):
    resp = create(owner_client, shop, units=units)
    assert resp.status_code == 400
    assert not Product.objects.filter(owner_shop=shop).exists()
    assert not ShopProduct.objects.filter(shop=shop).exists()


# ------------------------------------------------------------------ isolation (privacy)
def test_custom_products_are_private_to_their_shop(owner_client, other_user, other_shop, shop):
    mine = create(owner_client, shop).json()
    stranger = make_client(other_user)

    assert stranger.get(url(shop)).status_code == 404  # not a member
    assert stranger.get(url(other_shop)).json()["count"] == 0  # not in their own list
    shared = stranger.get("/api/v1/catalog/products/").json()["results"]
    assert mine["id"] not in [p["id"] for p in shared]
    assert mine["id"] not in [
        p["id"] for p in owner_client.get("/api/v1/catalog/products/").json()["results"]
    ]  # nor in the shared catalogue for its own owner: that list is shared-only


def test_another_shop_cannot_track_my_custom_product(owner_client, shop, other_shop):
    from apps.common.exceptions import DomainError

    product_id = create(owner_client, shop, track=False).json()["id"]
    with pytest.raises(DomainError) as exc:
        services.track_product(shop=other_shop, product_id=UUID(product_id))
    assert exc.value.get_codes() == "product_not_found"


def test_tracking_endpoint_rejects_another_shops_custom_product(
    owner_client, other_user, other_shop, shop
):
    mine = create(owner_client, shop, track=False).json()
    resp = make_client(other_user).post(
        f"/api/v1/shops/{other_shop.pk}/inventory/", {"product_id": mine["id"]}, format="json"
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "product_not_found"


def test_own_custom_product_can_be_tracked_later(owner_client, shop):
    mine = create(owner_client, shop, track=False).json()
    resp = owner_client.post(
        f"/api/v1/shops/{shop.pk}/inventory/", {"product_id": mine["id"]}, format="json"
    )
    assert resp.status_code == 201


# ------------------------------------------------------------------ units + permissions
def test_add_a_unit_to_a_custom_product(owner_client, shop):
    mine = create(owner_client, shop).json()
    resp = owner_client.post(
        url(shop, f"{mine['id']}/units/"),
        {"idempotency_key": str(uuid4()), "unit_name": "10 kg bag", "base_quantity": "10"},
        format="json",
    )
    assert resp.status_code == 201, resp.content
    assert "10 kg bag" in [u["unit_name"] for u in resp.json()["units"]]


def test_cannot_add_a_duplicate_unit(owner_client, shop):
    mine = create(owner_client, shop).json()
    resp = owner_client.post(
        url(shop, f"{mine['id']}/units/"),
        {"idempotency_key": str(uuid4()), "unit_name": "2 KG PACKET", "base_quantity": "2"},
        format="json",
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "invalid_unit"


def test_cannot_add_units_to_shared_or_foreign_products(owner_client, other_user, other_shop, shop, sugar):
    payload = {"idempotency_key": str(uuid4()), "unit_name": "x", "base_quantity": "3"}
    shared = owner_client.post(url(shop, f"{sugar.product.pk}/units/"), payload, format="json")
    assert shared.status_code == 400
    assert shared.json()["error"]["code"] == "product_not_found"

    theirs = create(make_client(other_user), other_shop).json()
    foreign = owner_client.post(
        url(shop, f"{theirs['id']}/units/"), {**payload, "idempotency_key": str(uuid4())}, format="json"
    )
    assert foreign.status_code == 400
    assert foreign.json()["error"]["code"] == "product_not_found"


def test_staff_can_list_but_not_create_or_add_units(owner_client, staff_user, shop):
    mine = create(owner_client, shop).json()
    staff = make_client(staff_user)
    assert staff.get(url(shop)).json()["count"] == 1
    assert create(staff, shop, name="Other thing").status_code == 403
    add = staff.post(
        url(shop, f"{mine['id']}/units/"),
        {"idempotency_key": str(uuid4()), "unit_name": "bag", "base_quantity": "9"},
        format="json",
    )
    assert add.status_code == 403


def test_search_filters_the_shop_list(owner_client, shop):
    create(owner_client, shop)
    create(owner_client, shop, name="Chapati flour", units=[])
    results = owner_client.get(url(shop) + "?q=chapati").json()["results"]
    assert [p["name"] for p in results] == ["Chapati flour"]
