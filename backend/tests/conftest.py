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
