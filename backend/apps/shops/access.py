"""Shop-scoped authorisation. Every shop-scoped view must go through get_membership()."""

from rest_framework.exceptions import NotFound, PermissionDenied

from .models import ShopMembership

MANAGEMENT_ROLES = (ShopMembership.Role.OWNER, ShopMembership.Role.MANAGER)


def get_membership(user, shop_id, *, roles=None) -> ShopMembership:
    """Return the user's active membership or raise.

    Non-members get 404 so another shop's existence is not revealed.
    Members lacking a required role get 403.
    """
    try:
        membership = ShopMembership.objects.select_related("shop").get(
            shop_id=shop_id, user=user, status=ShopMembership.Status.ACTIVE
        )
    except ShopMembership.DoesNotExist:
        raise NotFound("Shop not found.") from None
    if roles is not None and membership.role not in roles:
        raise PermissionDenied("You do not have permission to do this in this shop.")
    return membership
