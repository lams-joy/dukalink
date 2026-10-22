from decimal import Decimal
from types import SimpleNamespace

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.catalog.models import Product, ProductUnit
from apps.inventory import services as inventory
from apps.shops import services as shop_services
from apps.shops.models import ShopMembership

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
