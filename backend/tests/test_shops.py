import pytest

from apps.shops.models import ShopMembership

from .conftest import make_client

pytestmark = pytest.mark.django_db


def test_creating_a_shop_makes_the_creator_owner(owner_client, owner):
    resp = owner_client.post("/api/v1/shops/", {"name": "New Duka"}, format="json")
    assert resp.status_code == 201
    assert resp.json()["my_role"] == "owner"
    assert ShopMembership.objects.get(user=owner, shop_id=resp.json()["id"]).role == "owner"


def test_list_returns_only_my_shops(owner_client, shop, other_shop):
    names = [s["name"] for s in owner_client.get("/api/v1/shops/").json()]
    assert names == ["Amina Duka"]


def test_non_member_cannot_see_or_change_a_shop(other_user, shop):
    client = make_client(other_user)
    assert client.get(f"/api/v1/shops/{shop.pk}/").status_code == 404
    assert client.patch(f"/api/v1/shops/{shop.pk}/", {"name": "x"}, format="json").status_code == 404


def test_staff_can_read_but_not_edit(staff_user, shop):
    client = make_client(staff_user)
    assert client.get(f"/api/v1/shops/{shop.pk}/").status_code == 200
    resp = client.patch(f"/api/v1/shops/{shop.pk}/", {"name": "Hijacked"}, format="json")
    assert resp.status_code == 403


def test_invalid_timezone_rejected(owner_client):
    resp = owner_client.post("/api/v1/shops/", {"name": "X", "timezone": "Mars/Base"}, format="json")
    assert resp.status_code == 400


def test_owner_adds_member_who_then_gains_access(owner_client, other_user, shop):
    resp = owner_client.post(
        f"/api/v1/shops/{shop.pk}/members/",
        {"phone_number": other_user.phone_number, "role": "staff"},
        format="json",
    )
    assert resp.status_code == 201
    assert make_client(other_user).get(f"/api/v1/shops/{shop.pk}/").status_code == 200


def test_staff_cannot_add_members(staff_user, other_user, shop):
    resp = make_client(staff_user).post(
        f"/api/v1/shops/{shop.pk}/members/",
        {"phone_number": other_user.phone_number, "role": "staff"},
        format="json",
    )
    assert resp.status_code == 403


def test_owner_role_cannot_be_granted_through_the_api(owner_client, other_user, shop):
    resp = owner_client.post(
        f"/api/v1/shops/{shop.pk}/members/",
        {"phone_number": other_user.phone_number, "role": "owner"},
        format="json",
    )
    assert resp.status_code == 400
