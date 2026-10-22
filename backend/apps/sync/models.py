import uuid

from django.conf import settings
from django.db import models


class SyncOperation(models.Model):
    """Idempotency record: one row per (user, client operation id)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    shop = models.ForeignKey("shops.Shop", on_delete=models.PROTECT)
    operation_id = models.UUIDField()  # the client's idempotency key
    operation_type = models.CharField(max_length=50)
    payload_hash = models.CharField(max_length=64)
    response_status = models.PositiveSmallIntegerField(null=True)
    response_body = models.JSONField(null=True)
    received_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "operation_id"], name="uniq_operation_per_user")
        ]
