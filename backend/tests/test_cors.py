"""Browser clients (the Expo web build) call the API from another origin."""

import pytest
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db

ORIGIN = "http://localhost:8081"
PORTAL_ORIGIN = "http://localhost:5173"


def test_the_dev_web_origin_is_allowed_and_can_read_our_headers():
    resp = APIClient().get("/api/v1/health/", HTTP_ORIGIN=ORIGIN)
    assert resp["Access-Control-Allow-Origin"] == ORIGIN
    exposed = resp["Access-Control-Expose-Headers"]
    assert "X-Request-ID" in exposed and "Idempotent-Replayed" in exposed


def test_a_preflight_for_an_authenticated_json_request_is_answered():
    resp = APIClient().options(
        "/api/v1/auth/login/",
        HTTP_ORIGIN=ORIGIN,
        HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
        HTTP_ACCESS_CONTROL_REQUEST_HEADERS="authorization,content-type",
    )
    assert resp.status_code == 200
    assert resp["Access-Control-Allow-Origin"] == ORIGIN
    assert "authorization" in resp["Access-Control-Allow-Headers"]


def test_other_origins_get_no_cors_headers():
    resp = APIClient().get("/api/v1/health/", HTTP_ORIGIN="https://evil.example")
    assert "Access-Control-Allow-Origin" not in resp


def test_the_wholesaler_portal_dev_origin_is_allowed():
    resp = APIClient().get("/api/v1/health/", HTTP_ORIGIN=PORTAL_ORIGIN)
    assert resp["Access-Control-Allow-Origin"] == PORTAL_ORIGIN
