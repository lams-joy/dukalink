import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

MONEY = {"max_digits": 16, "decimal_places": 2}
QTY = {"max_digits": 18, "decimal_places": 6}


class Order(models.Model):
    """One shop's order to one wholesaler. Once confirmed its terms are frozen: later changes
    to the offer's price never touch it, and the only ways out are dispatch, cancel or receive.

    submitted -> confirmed -> dispatched -> received
        |            |
        +-> rejected +-> cancelled   (cancel is also allowed from submitted)
    """

    class Status(models.TextChoices):
        SUBMITTED = "submitted"
        CONFIRMED = "confirmed"
        DISPATCHED = "dispatched"
        RECEIVED = "received"
        REJECTED = "rejected"
        CANCELLED = "cancelled"

    class DeliveryMethod(models.TextChoices):
        DELIVERY = "delivery"
        COLLECTION = "collection"

    OPEN_STATUSES = (Status.SUBMITTED, Status.CONFIRMED, Status.DISPATCHED)

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    shop = models.ForeignKey("shops.Shop", on_delete=models.PROTECT, related_name="orders")
    wholesaler = models.ForeignKey(
        "suppliers.Wholesaler", on_delete=models.PROTECT, related_name="orders"
    )
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.SUBMITTED)
    status_note = models.CharField(max_length=255, blank=True)  # rejection / cancellation reason
    cancelled_by = models.CharField(max_length=10, blank=True)  # "shop" | "wholesaler"

    currency = models.CharField(max_length=3)
    subtotal = models.DecimalField(**MONEY)
    delivery_fee = models.DecimalField(default=0, **MONEY)  # set by the supplier on confirmation
    total_amount = models.DecimalField(**MONEY)

    delivery_method = models.CharField(
        max_length=12, choices=DeliveryMethod.choices, default=DeliveryMethod.DELIVERY
    )
    delivery_address = models.CharField(max_length=255, blank=True)
    contact_phone = models.CharField(max_length=20, blank=True)  # what the shop chose to share
    note = models.CharField(max_length=255, blank=True)

    placed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    submitted_at = models.DateTimeField(default=timezone.now)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    dispatched_at = models.DateTimeField(null=True, blank=True)
    received_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)  # rejected / cancelled
    receipt_note = models.CharField(max_length=255, blank=True)  # shortage / discrepancy remarks
    # The stock receipt written into the shop's inventory when goods arrived.
    purchase_receipt = models.OneToOneField(
        "inventory.PurchaseReceipt", null=True, blank=True, on_delete=models.PROTECT,
        related_name="+",
    )  # fmt: skip
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-submitted_at", "-id"]
        indexes = [
            models.Index(fields=["shop", "-submitted_at"], name="order_shop_submitted_idx"),
            models.Index(fields=["wholesaler", "status"], name="order_whsl_status_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(subtotal__gte=0), name="order_subtotal_non_negative"
            ),
            models.CheckConstraint(condition=Q(delivery_fee__gte=0), name="order_fee_non_negative"),
        ]

    def __str__(self):
        return f"Order {self.pk} ({self.status})"

    @property
    def has_shortage(self) -> bool:
        if self.status != self.Status.RECEIVED:
            return False
        return any((i.received_quantity or 0) < i.quantity for i in self.items.all())


class OrderItem(models.Model):
    """The agreed terms of one line, copied from the offer at placement. Nothing here is
    recomputed from the live offer afterwards."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    offer = models.ForeignKey("suppliers.SupplierOffer", on_delete=models.PROTECT, related_name="+")
    product = models.ForeignKey("catalog.Product", on_delete=models.PROTECT, related_name="+")
    product_unit = models.ForeignKey(
        "catalog.ProductUnit", on_delete=models.PROTECT, related_name="+"
    )
    product_name_snapshot = models.CharField(max_length=200)
    unit_name_snapshot = models.CharField(max_length=50)
    unit_base_quantity_snapshot = models.DecimalField(**QTY)
    quantity = models.DecimalField(**QTY)  # in the offer unit
    quantity_base = models.DecimalField(**QTY)
    list_price_snapshot = models.DecimalField(max_digits=14, decimal_places=2)  # offer base price
    unit_price_snapshot = models.DecimalField(max_digits=14, decimal_places=2)  # after any tier
    line_total = models.DecimalField(**MONEY)
    received_quantity = models.DecimalField(null=True, blank=True, **QTY)  # set on receipt

    class Meta:
        ordering = ["product_name_snapshot", "id"]
        constraints = [
            models.UniqueConstraint(fields=["order", "offer"], name="uniq_offer_per_order"),
            models.CheckConstraint(condition=Q(quantity__gt=0), name="orderitem_quantity_positive"),
            models.CheckConstraint(
                condition=Q(unit_price_snapshot__gt=0), name="orderitem_price_positive"
            ),
            models.CheckConstraint(
                condition=Q(received_quantity__isnull=True) | Q(received_quantity__gte=0),
                name="orderitem_received_non_negative",
            ),
        ]

    def __str__(self):
        return f"{self.product_name_snapshot} x {self.quantity}"
