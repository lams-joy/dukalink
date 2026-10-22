from decimal import Decimal

import pytest

from apps.inventory import services
from apps.shops.models import Shop

from .conftest import make_client

pytestmark = pytest.mark.django_db


def complete_url(shop):
    return f"/api/v1/shops/{shop.pk}/onboarding/complete/"


def test_needs_at_least_one_tracked_product(owner_client, shop):
    resp = owner_client.post(complete_url(shop))
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "no_tracked_products"
    shop.refresh_from_db()
    assert shop.onboarding_completed_at is None


def test_completes_without_opening_stock_and_reports_what_is_missing(
    owner_client, shop, owner, sugar, flour, tracked_sugar
):
    tracked_flour = services.track_product(shop=shop, product_id=flour.product.pk)
    services.record_opening_stock(
        shop=shop, user=owner, shop_product_id=tracked_flour.pk, unit_id=flour.kg.pk,
        quantity=Decimal("20"),
    )  # fmt: skip
    resp = owner_client.post(complete_url(shop))
    assert resp.status_code == 200, resp.content
    data = resp.json()
    assert data["onboarding"] == {
        "tracked_products": 2,
        "with_opening_stock": 1,
        "awaiting_opening_stock": 1,  # sugar was skipped, not invented
    }
    assert data["shop"]["onboarding_completed_at"] is not None


def test_completing_twice_keeps_the_first_timestamp(owner_client, shop, tracked_sugar):
    first = owner_client.post(complete_url(shop)).json()["shop"]["onboarding_completed_at"]
    second = owner_client.post(complete_url(shop)).json()["shop"]["onboarding_completed_at"]
    assert first == second


def test_state_is_visible_on_the_shop_and_the_list(owner_client, shop, tracked_sugar):
    assert owner_client.get(f"/api/v1/shops/{shop.pk}/").json()["onboarding_completed_at"] is None
    owner_client.post(complete_url(shop))
    assert owner_client.get(f"/api/v1/shops/{shop.pk}/").json()["onboarding_completed_at"]
    assert owner_client.get("/api/v1/shops/").json()[0]["onboarding_completed_at"]


def test_clients_cannot_set_the_completion_time_directly(owner_client, shop):
    owner_client.patch(
        f"/api/v1/shops/{shop.pk}/", {"onboarding_completed_at": "2026-01-01T00:00:00Z"}, format="json"
    )
    shop.refresh_from_db()
    assert shop.onboarding_completed_at is None


def test_staff_cannot_complete_onboarding(staff_user, shop, tracked_sugar):
    assert make_client(staff_user).post(complete_url(shop)).status_code == 403


def test_outsiders_get_404(other_user, shop, tracked_sugar):
    assert make_client(other_user).post(complete_url(shop)).status_code == 404


# ------------------------------------------------------------------ recording preference
def test_recording_preference_sets_the_default_for_new_products(owner_client, shop, sugar, flour):
    assert Shop.objects.get(pk=shop.pk).default_tracking_mode == "transaction"
    resp = owner_client.patch(
        f"/api/v1/shops/{shop.pk}/", {"default_tracking_mode": "simple"}, format="json"
    )
    assert resp.status_code == 200
    shop.refresh_from_db()
    item = services.track_product(shop=shop, product_id=sugar.product.pk)
    assert item.tracking_mode == "simple"
    # an explicit per-product change still wins
    owner_client.patch(
        f"/api/v1/shops/{shop.pk}/inventory/{item.pk}/settings/",
        {"tracking_mode": "transaction"},
        format="json",
    )
    item.refresh_from_db()
    assert item.tracking_mode == "transaction"


def test_invalid_recording_preference_is_rejected(owner_client, shop):
    resp = owner_client.patch(
        f"/api/v1/shops/{shop.pk}/", {"default_tracking_mode": "chaos"}, format="json"
    )
    assert resp.status_code == 400


def test_shop_can_be_created_with_a_preference(owner_client):
    resp = owner_client.post(
        "/api/v1/shops/", {"name": "Wanjiku Duka", "default_tracking_mode": "simple"}, format="json"
    )
    assert resp.status_code == 201
    assert resp.json()["default_tracking_mode"] == "simple"
