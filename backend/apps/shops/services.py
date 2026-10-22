from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction

from apps.accounts.phone import normalise_phone
from apps.common.exceptions import DomainError, StateConflict

from .models import Shop, ShopMembership


@transaction.atomic
def create_shop(user, **fields) -> Shop:
    shop = Shop.objects.create(**fields)
    ShopMembership.objects.create(shop=shop, user=user, role=ShopMembership.Role.OWNER)
    return shop


@transaction.atomic
def add_member(*, shop: Shop, phone_number: str, role: str) -> ShopMembership:
    """Add an existing account to a shop. (Invitations for unregistered numbers: not decided.)"""
    if role == ShopMembership.Role.OWNER:
        raise DomainError("Owners cannot be added through this endpoint.", code="invalid_role")
    User = get_user_model()
    try:
        user = User.objects.get(phone_number=normalise_phone(phone_number))
    except (User.DoesNotExist, DjangoValidationError):
        raise DomainError("No account exists for that phone number.", code="user_not_found") from None

    membership, created = ShopMembership.objects.get_or_create(
        shop=shop, user=user, defaults={"role": role}
    )
    if created:
        return membership
    if membership.status == ShopMembership.Status.ACTIVE:
        raise StateConflict("That person is already a member of this shop.")
    if membership.role == ShopMembership.Role.OWNER:
        raise StateConflict("That person is the shop owner.")
    membership.status = ShopMembership.Status.ACTIVE
    membership.role = role
    membership.save(update_fields=["status", "role"])
    return membership
