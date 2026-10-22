"""Wholesaler-scoped authorisation, mirroring shops.access. Non-members get 404 so another
wholesaler's existence is not revealed; members lacking the role get 403."""

from rest_framework.exceptions import NotFound, PermissionDenied

from .models import WholesalerMembership

MANAGEMENT_ROLES = (WholesalerMembership.Role.OWNER, WholesalerMembership.Role.MANAGER)


def get_wholesaler_membership(user, wholesaler_id, *, roles=None) -> WholesalerMembership:
    try:
        membership = WholesalerMembership.objects.select_related("wholesaler").get(
            wholesaler_id=wholesaler_id, user=user, status=WholesalerMembership.Status.ACTIVE
        )
    except WholesalerMembership.DoesNotExist:
        raise NotFound("Wholesaler not found.") from None
    if roles is not None and membership.role not in roles:
        raise PermissionDenied("You do not have permission to do this for this wholesaler.")
    return membership


def require_platform_admin(user) -> None:
    if not (user and user.is_authenticated and user.is_staff):
        raise PermissionDenied("Platform administrators only.")
