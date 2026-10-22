import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class AppendOnlyError(RuntimeError):
    pass


class AuditQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise AppendOnlyError("Audit events cannot be modified.")

    def delete(self):
        raise AppendOnlyError("Audit events cannot be deleted.")


class AuditEvent(models.Model):
    """One sensitive business action: who did what to which object, and the relevant
    before/after values. Append-only: rows are never edited or deleted through the ORM.

    `shop` is empty only for platform-level events (e.g. supplier verification, later).
    `actor` is empty for system actions, or if the account is later closed.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    shop = models.ForeignKey(
        "shops.Shop", null=True, blank=True, on_delete=models.PROTECT, related_name="audit_events"
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    action = models.CharField(max_length=64)  # "<area>.<verb>", e.g. "stock.adjustment"
    object_type = models.CharField(max_length=64)
    object_id = models.CharField(max_length=64)
    changes = models.JSONField(default=dict, blank=True)  # {"before": {...}, "after": {...}, ...}
    request_id = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    objects = AuditQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["shop", "-created_at"], name="audit_shop_created_idx"),
            models.Index(fields=["shop", "action"], name="audit_shop_action_idx"),
        ]

    def __str__(self):
        return f"{self.action} {self.object_type}:{self.object_id}"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise AppendOnlyError("Audit events cannot be modified.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise AppendOnlyError("Audit events cannot be deleted.")
