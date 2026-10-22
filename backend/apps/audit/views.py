from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.generics import ListAPIView

from apps.shops.access import MANAGEMENT_ROLES, get_membership

from .models import AuditEvent
from .serializers import AuditEventSerializer


class AuditEventListView(ListAPIView):
    """Owner/manager only. Newest first. Filters: ?action=, ?object_type=, ?object_id=, ?actor_id="""

    serializer_class = AuditEventSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return AuditEvent.objects.none()
        membership = get_membership(
            self.request.user, self.kwargs["shop_id"], roles=MANAGEMENT_ROLES
        )
        qs = AuditEvent.objects.filter(shop=membership.shop)
        params = self.request.query_params
        for param, lookup in (
            ("action", "action"), ("object_type", "object_type"),
            ("object_id", "object_id"), ("actor_id", "actor_id"),
        ):  # fmt: skip
            if params.get(param):
                try:
                    qs = qs.filter(**{lookup: params[param]})
                except (ValueError, TypeError, DjangoValidationError):
                    return qs.none()
        return qs
