from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone

from apps.accounts.phone import normalise_phone
from apps.audit import services as audit
from apps.common.exceptions import DomainError, StateConflict

from .models import Shop, ShopMembership


@transaction.atomic
def create_shop(user, **fields) -> Shop:
    shop = Shop.objects.create(**fields)
    ShopMembership.objects.create(shop=shop, user=user, role=ShopMembership.Role.OWNER)
    audit.record(
        action="shop.created", obj_type="shop", obj_id=shop.pk, actor=user, shop=shop,
        changes={"after": {"name": shop.name}},
    )  # fmt: skip
    return shop


@transaction.atomic
def update_shop(*, shop: Shop, actor, values: dict) -> Shop:
    """Apply validated changes to a shop's own details, auditing what actually changed."""
    changes = audit.diff(shop, values)
    if not changes["after"]:
        return shop
    for field, value in values.items():
        setattr(shop, field, value)
    shop.save(update_fields=[*changes["after"].keys(), "updated_at"])
    audit.record(
        action="shop.updated", obj_type="shop", obj_id=shop.pk, actor=actor, shop=shop,
        changes=changes,
    )  # fmt: skip
    return shop


@transaction.atomic
def add_member(*, shop: Shop, phone_number: str, role: str, actor=None) -> ShopMembership:
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
        _record_member_added(shop, membership, actor)
        return membership
    if membership.status == ShopMembership.Status.ACTIVE:
        raise StateConflict("That person is already a member of this shop.")
    if membership.role == ShopMembership.Role.OWNER:
        raise StateConflict("That person is the shop owner.")
    membership.status = ShopMembership.Status.ACTIVE
    membership.role = role
    membership.save(update_fields=["status", "role"])
    _record_member_added(shop, membership, actor)
    return membership


def _record_member_added(shop, membership, actor):
    # The member is identified by account id only: no phone number or name in the audit trail.
    audit.record(
        action="shop.member_added", obj_type="shop_membership", obj_id=membership.pk,
        actor=actor, shop=shop,
        changes={"after": {"user_id": membership.user_id, "role": membership.role}},
    )  # fmt: skip


@transaction.atomic
def complete_onboarding(shop: Shop, actor=None) -> dict:
    """Mark setup finished. Needs at least one tracked product; opening stock is NOT required
    (unknown quantities are skipped, never invented). Safe to call twice: the first completion
    time is kept. Returns a summary of what is still missing."""
    from apps.inventory.models import ShopProduct  # local import: inventory depends on shops

    tracked = ShopProduct.objects.filter(shop=shop, is_active=True)
    total = tracked.count()
    if total == 0:
        raise DomainError(
            "Add at least one product before finishing setup.", code="no_tracked_products"
        )
    if shop.onboarding_completed_at is None:
        shop.onboarding_completed_at = timezone.now()
        shop.save(update_fields=["onboarding_completed_at", "updated_at"])
        audit.record(
            action="shop.onboarding_completed", obj_type="shop", obj_id=shop.pk, actor=actor,
            shop=shop, changes={"after": {"tracked_products": total}},
        )  # fmt: skip
    awaiting = tracked.filter(movements__isnull=True).count()
    return {
        "tracked_products": total,
        "with_opening_stock": total - awaiting,
        "awaiting_opening_stock": awaiting,
    }
