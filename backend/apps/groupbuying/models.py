import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

MONEY = {"max_digits": 16, "decimal_places": 2}
QTY = {"max_digits": 18, "decimal_places": 6}


class GroupOrder(models.Model):
    """Several shops pooling demand for ONE wholesaler offer (one product, one unit).

    open -> closed -> confirmed        (5b: close, confirm)
      |        |-> failed / declined   (5b)
      +-> cancelled                    (organiser, while open)

    Joining is NOT binding. Commitment becomes binding only when the wholesaler confirms the
    final terms (decisions.md, 2026-10-23). `committed_quantity*` are caches of the active
    participants' commitments and are rewritten under the row lock on every change, so they
    always reconcile (see services.reconcile()).
    """

    class Status(models.TextChoices):
        OPEN = "open"
        CLOSED = "closed"
        CONFIRMED = "confirmed"
        FAILED = "failed"
        DECLINED = "declined"
        CANCELLED = "cancelled"

    class DeliveryMethod(models.TextChoices):
        DELIVERY = "delivery"
        COLLECTION = "collection"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organiser_shop = models.ForeignKey(
        "shops.Shop", on_delete=models.PROTECT, related_name="organised_groups"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    wholesaler = models.ForeignKey(
        "suppliers.Wholesaler", on_delete=models.PROTECT, related_name="group_orders"
    )
    offer = models.ForeignKey(
        "suppliers.SupplierOffer", on_delete=models.PROTECT, related_name="group_orders"
    )
    product = models.ForeignKey("catalog.Product", on_delete=models.PROTECT, related_name="+")
    product_unit = models.ForeignKey(
        "catalog.ProductUnit", on_delete=models.PROTECT, related_name="+"
    )
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    status_note = models.CharField(max_length=255, blank=True)

    # Snapshots taken when the group is created; the live offer may change afterwards.
    product_name_snapshot = models.CharField(max_length=200)
    unit_name_snapshot = models.CharField(max_length=50)
    unit_base_quantity_snapshot = models.DecimalField(**QTY)
    currency = models.CharField(max_length=3)
    list_price_snapshot = models.DecimalField(max_digits=14, decimal_places=2)
    minimum_per_shop = models.DecimalField(**QTY)  # the offer's minimum order, per shop

    target_quantity = models.DecimalField(**QTY)  # in the offer unit
    deadline = models.DateTimeField()
    delivery_method = models.CharField(max_length=12, choices=DeliveryMethod.choices)
    delivery_point = models.CharField(max_length=255)  # address, or the collection point
    estimated_delivery_fee = models.DecimalField(default=0, **MONEY)  # the cap (see decisions)
    note = models.CharField(max_length=255, blank=True)

    # Caches of the ACTIVE commitments.
    committed_quantity = models.DecimalField(default=0, **QTY)
    committed_quantity_base = models.DecimalField(default=0, **QTY)
    participant_count = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    closed_at = models.DateTimeField(null=True, blank=True)  # cancelled (5b: also closed/failed)

    class Meta:
        ordering = ["deadline", "id"]
        indexes = [
            models.Index(fields=["status", "deadline"], name="group_status_deadline_idx"),
            models.Index(fields=["wholesaler", "status"], name="group_whsl_status_idx"),
        ]
        constraints = [
            models.CheckConstraint(condition=Q(target_quantity__gt=0), name="group_target_positive"),
            models.CheckConstraint(
                condition=Q(estimated_delivery_fee__gte=0), name="group_fee_non_negative"
            ),
            models.CheckConstraint(
                condition=Q(committed_quantity__gte=0, committed_quantity_base__gte=0),
                name="group_committed_non_negative",
            ),
        ]

    def __str__(self):
        return f"Group {self.pk} ({self.status})"


class GroupParticipant(models.Model):
    """One shop's commitment to a group. One row per (group, shop): withdrawing marks it
    withdrawn and rejoining reactivates it, so there is never more than one active commitment."""

    class Status(models.TextChoices):
        ACTIVE = "active"
        WITHDRAWN = "withdrawn"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    group = models.ForeignKey(GroupOrder, on_delete=models.CASCADE, related_name="participants")
    shop = models.ForeignKey(
        "shops.Shop", on_delete=models.PROTECT, related_name="group_commitments"
    )
    committed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    quantity = models.DecimalField(**QTY)  # in the offer unit
    quantity_base = models.DecimalField(**QTY)
    joined_at = models.DateTimeField(default=timezone.now)  # reset on rejoin; rounding tie-break
    updated_at = models.DateTimeField(auto_now=True)
    withdrawn_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["joined_at", "id"]
        constraints = [
            models.UniqueConstraint(fields=["group", "shop"], name="uniq_shop_per_group"),
            models.CheckConstraint(condition=Q(quantity__gt=0), name="participant_qty_positive"),
        ]

    def __str__(self):
        return f"{self.shop_id} in {self.group_id}: {self.quantity} ({self.status})"
