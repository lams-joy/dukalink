import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q


class Wholesaler(models.Model):
    class Verification(models.TextChoices):
        PENDING = "pending"
        VERIFIED = "verified"
        SUSPENDED = "suspended"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business_name = models.CharField(max_length=200)
    contact_phone = models.CharField(max_length=20)  # public business line, not a personal account
    location_text = models.CharField(max_length=255, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    verification_status = models.CharField(
        max_length=10, choices=Verification.choices, default=Verification.PENDING
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    # Internal: why the platform verified/suspended. Never serialised to shops.
    verification_note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["verification_status"])]

    def __str__(self):
        return self.business_name

    @property
    def is_verified(self) -> bool:
        return self.verification_status == self.Verification.VERIFIED


class WholesalerMembership(models.Model):
    class Role(models.TextChoices):
        OWNER = "owner"
        MANAGER = "manager"
        STAFF = "staff"

    class Status(models.TextChoices):
        ACTIVE = "active"
        SUSPENDED = "suspended"
        REMOVED = "removed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    wholesaler = models.ForeignKey(Wholesaler, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="wholesaler_memberships"
    )
    role = models.CharField(max_length=10, choices=Role.choices)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["wholesaler", "user"], name="uniq_membership_per_wholesaler_user"
            )
        ]

    def __str__(self):
        return f"{self.user_id} -> {self.wholesaler_id} ({self.role})"


class SupplierOffer(models.Model):
    """A wholesaler's listing: one shared-catalogue product in one purchase unit, with a
    base price, a minimum order and optional volume price tiers. Quantities are in the
    OFFER unit (e.g. sacks), not the product's base unit."""

    class Availability(models.TextChoices):
        IN_STOCK = "in_stock"
        LIMITED = "limited"
        OUT_OF_STOCK = "out_of_stock"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    wholesaler = models.ForeignKey(Wholesaler, on_delete=models.PROTECT, related_name="offers")
    product = models.ForeignKey("catalog.Product", on_delete=models.PROTECT, related_name="offers")
    product_unit = models.ForeignKey(
        "catalog.ProductUnit", on_delete=models.PROTECT, related_name="offers"
    )
    price_per_unit = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3, default="KES")
    minimum_order_quantity = models.DecimalField(max_digits=18, decimal_places=6, default=1)
    availability = models.CharField(
        max_length=12, choices=Availability.choices, default=Availability.IN_STOCK
    )
    available_quantity = models.DecimalField(  # in offer units; null = not tracked
        max_digits=18, decimal_places=6, null=True, blank=True
    )
    delivery_areas = models.CharField(max_length=255, blank=True)
    delivery_terms = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)  # shown on every listing

    class Meta:
        indexes = [models.Index(fields=["product", "is_active"])]
        constraints = [
            # Two live listings for the same product+unit from one wholesaler would be ambiguous.
            models.UniqueConstraint(
                fields=["wholesaler", "product", "product_unit"],
                condition=Q(is_active=True),
                name="uniq_active_offer_per_wholesaler_unit",
            ),
            models.CheckConstraint(condition=Q(price_per_unit__gt=0), name="offer_price_positive"),
            models.CheckConstraint(
                condition=Q(minimum_order_quantity__gt=0), name="offer_moq_positive"
            ),
            models.CheckConstraint(
                condition=Q(available_quantity__isnull=True) | Q(available_quantity__gte=0),
                name="offer_available_non_negative",
            ),
        ]

    def __str__(self):
        return f"{self.wholesaler_id}: {self.product_id} @ {self.price_per_unit}"


class SupplierPriceTier(models.Model):
    """Volume price: from `minimum_quantity` (offer units) the unit price is `unit_price`."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    offer = models.ForeignKey(SupplierOffer, on_delete=models.CASCADE, related_name="tiers")
    minimum_quantity = models.DecimalField(max_digits=18, decimal_places=6)
    unit_price = models.DecimalField(max_digits=14, decimal_places=2)
    valid_from = models.DateTimeField(null=True, blank=True)
    valid_until = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["minimum_quantity"]
        constraints = [
            models.UniqueConstraint(
                fields=["offer", "minimum_quantity"], name="uniq_tier_quantity_per_offer"
            ),
            models.CheckConstraint(condition=Q(unit_price__gt=0), name="tier_price_positive"),
            models.CheckConstraint(condition=Q(minimum_quantity__gt=0), name="tier_qty_positive"),
        ]

    def __str__(self):
        return f"{self.offer_id}: >= {self.minimum_quantity} @ {self.unit_price}"
