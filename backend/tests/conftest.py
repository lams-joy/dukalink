from decimal import Decimal
from types import SimpleNamespace

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.catalog.models import Product, ProductUnit
from apps.inventory import services as inventory
from apps.shops import services as shop_services
from apps.shops.models import ShopMembership
from apps.suppliers import services as supplier_services

PASSWORD = "S3cure-pass!"
D = Decimal


@pytest.fixture(autouse=True)
def _fast_password_hasher(settings):
    """PBKDF2 is deliberately slow (~0.2s per hash); every fixture user pays it. Tests only."""
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]


def make_client(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


@pytest.fixture
def owner():
    return User.objects.create_user("0712345678", PASSWORD, full_name="Amina Owner")


@pytest.fixture
def other_user():
    return User.objects.create_user("0722222222", PASSWORD, full_name="Brian Other")


@pytest.fixture
def shop(owner):
    return shop_services.create_shop(owner, name="Amina Duka")


@pytest.fixture
def other_shop(other_user):
    return shop_services.create_shop(other_user, name="Brian Duka")


@pytest.fixture
def staff_user(shop):
    user = User.objects.create_user("0733333333", PASSWORD, full_name="Chebet Staff")
    ShopMembership.objects.create(shop=shop, user=user, role=ShopMembership.Role.STAFF)
    return user


@pytest.fixture
def owner_client(owner):
    return make_client(owner)


@pytest.fixture
def sugar():
    product = Product.objects.create(name="Sugar", base_unit="kg")
    kg = product.ensure_base_unit()
    sack = ProductUnit.objects.create(
        product=product, unit_name="50 kg sack", base_quantity=Decimal("50")
    )
    return SimpleNamespace(product=product, kg=kg, sack=sack)


@pytest.fixture
def flour():
    product = Product.objects.create(name="Maize flour", base_unit="kg")
    kg = product.ensure_base_unit()
    return SimpleNamespace(product=product, kg=kg)


@pytest.fixture
def tracked_sugar(shop, sugar):
    return inventory.track_product(shop=shop, product_id=sugar.product.pk)


# ------------------------------------------------------------------ suppliers
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
    return supplier_services.register_wholesaler(
        seller, business_name="Kisumu Wholesale", contact_phone="0711000000",
        location_text="Kisumu",
    )  # fmt: skip


@pytest.fixture
def verified(wholesaler, admin_user):
    return supplier_services.verify_wholesaler(wholesaler_id=wholesaler.pk, actor=admin_user, note="ok")


@pytest.fixture
def rival_user():
    return User.objects.create_user("0744444444", PASSWORD, full_name="Rival Seller")


@pytest.fixture
def rival(rival_user, admin_user):
    w = supplier_services.register_wholesaler(
        rival_user, business_name="Rival Traders", contact_phone="0744000000"
    )
    return supplier_services.verify_wholesaler(wholesaler_id=w.pk, actor=admin_user)


# ------------------------------------------------------------------ group buying
@pytest.fixture
def offer(verified, seller, sugar):
    """7,000 per 50 kg sack, 6,800 from 10 sacks; at least 2 sacks per shop; 40 available."""
    return supplier_services.create_offer(
        wholesaler=verified, actor=seller, product_id=sugar.product.pk,
        product_unit_id=sugar.sack.pk, price_per_unit=D("7000"), minimum_order_quantity=D("2"),
        available_quantity=D("40"), tiers=[{"minimum_quantity": D("10"), "unit_price": D("6800")}],
    )  # fmt: skip


@pytest.fixture
def third_user():
    return User.objects.create_user("0744444444", PASSWORD, full_name="Faith Third")


@pytest.fixture
def third_shop(third_user):
    return shop_services.create_shop(third_user, name="Faith Duka")


@pytest.fixture
def other_client(other_user):
    return make_client(other_user)


@pytest.fixture
def third_client(third_user):
    return make_client(third_user)
