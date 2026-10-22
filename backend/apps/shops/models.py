import uuid

from django.conf import settings
from django.db import models


class Shop(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=150)
    location_text = models.CharField(max_length=255, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    timezone = models.CharField(max_length=64, default="Africa/Nairobi")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class ShopMembership(models.Model):
    class Role(models.TextChoices):
        OWNER = "owner"
        MANAGER = "manager"
        STAFF = "staff"

    class Status(models.TextChoices):
        ACTIVE = "active"
        SUSPENDED = "suspended"
        REMOVED = "removed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="shop_memberships"
    )
    role = models.CharField(max_length=10, choices=Role.choices)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["shop", "user"], name="uniq_membership_per_shop_user")
        ]

    def __str__(self):
        return f"{self.user_id} -> {self.shop_id} ({self.role})"
