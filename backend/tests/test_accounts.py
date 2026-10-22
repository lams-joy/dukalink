import pytest
from django.core.exceptions import ValidationError
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.accounts.phone import normalise_phone

from .conftest import PASSWORD

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    "raw",
    ["0712 345 678", "254712345678", "+254712345678", "00254712345678", "0712-345-678"],
)
def test_phone_numbers_normalise_to_e164(raw):
    assert normalise_phone(raw) == "+254712345678"


@pytest.mark.parametrize("raw", ["", "12345", "+0123456789", "abc"])
def test_invalid_phone_numbers_rejected(raw):
    with pytest.raises(ValidationError):
        normalise_phone(raw)


def test_register_login_and_me():
    client = APIClient()
    resp = client.post(
        "/api/v1/auth/register/",
        {"phone_number": "0711000111", "full_name": "Wanjiru", "password": PASSWORD},
        format="json",
    )
    assert resp.status_code == 201
    assert resp.json()["phone_number"] == "+254711000111"

    # Log in with the local format: the same account must be found.
    login = client.post(
        "/api/v1/auth/login/",
        {"phone_number": "0711 000 111", "password": PASSWORD},
        format="json",
    )
    assert login.status_code == 200
    token = login.json()["access"]

    me = client.get("/api/v1/me/", HTTP_AUTHORIZATION=f"Bearer {token}")
    assert me.status_code == 200
    assert me.json()["full_name"] == "Wanjiru"


def test_duplicate_number_in_another_format_is_rejected():
    User.objects.create_user("0711000111", PASSWORD, full_name="First")
    resp = APIClient().post(
        "/api/v1/auth/register/",
        {"phone_number": "+254711000111", "full_name": "Second", "password": PASSWORD},
        format="json",
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "validation_error"


def test_unauthenticated_requests_get_the_error_envelope():
    resp = APIClient().get("/api/v1/me/")
    assert resp.status_code == 401
    error = resp.json()["error"]
    assert error["code"] == "not_authenticated"
    assert error["request_id"]
    assert resp["X-Request-ID"] == error["request_id"]


def test_health_endpoint_is_public():
    assert APIClient().get("/api/v1/health/").json() == {"status": "ok"}
