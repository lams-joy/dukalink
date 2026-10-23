import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

QTY = {"max_digits": 18, "decimal_places": 6}
MONEY = {"max_digits": 14, "decimal_places": 2}


class ShopProduct(models.Model):
    """A product tracked by one shop. quantity_base is a CACHE of the movement ledger."""

    class TrackingMode(models.TextChoices):
        SIMPLE = "simple"
        TRANSACTION = "transaction"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    shop = models.ForeignKey("shops.Shop", on_delete=models.PROTECT, related_name="inventory")
    product = models.ForeignKey("catalog.Product", on_delete=models.PROTECT, related_name="+")
    quantity_base = models.DecimalField(default=0, **QTY)
    reorder_level_base = models.DecimalField(null=True, blank=True, **QTY)
    tracking_mode = models.CharField(
        max_length=12, choices=TrackingMode.choices, default=TrackingMode.TRANSACTION
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["shop", "product"], name="uniq_product_per_shop"),
            models.CheckConstraint(
                condition=Q(reorder_level_base__isnull=True) | Q(reorder_level_base__gte=0),
                name="shopproduct_reorder_level_non_negative",
            ),
        ]

    def __str__(self):
        return f"{self.product_id}@{self.shop_id}"


class MovementType(models.TextChoices):
    OPENING_STOCK = "opening_stock"
    PURCHASE_RECEIPT = "purchase_receipt"
    SALE = "sale"
    RETURN = "return"
    DAMAGE = "damage"
    ADJUSTMENT = "adjustment"
    REVERSAL = "reversal"


POSITIVE_ONLY = [MovementType.OPENING_STOCK, MovementType.PURCHASE_RECEIPT]
NEGATIVE_ONLY = [MovementType.SALE, MovementType.DAMAGE]
EITHER_SIGN = [MovementType.RETURN, MovementType.ADJUSTMENT, MovementType.REVERSAL]


class AppendOnlyError(Exception):
    pass


class StockMovement(models.Model):
    """Append-only ledger. Corrections are new movements (reversal/adjustment)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    shop_product = models.ForeignKey(ShopProduct, on_delete=models.PROTECT, related_name="movements")
    movement_type = models.CharField(max_length=20, choices=MovementType.choices)
    quantity_base_delta = models.DecimalField(**QTY)
    balance_after_base = models.DecimalField(**QTY)
    unit_cost_base = models.DecimalField(null=True, blank=True, **QTY)
    # Snapshot of what the user entered (e.g. 1 x "50 kg sack" = 50), for audit/history.
    entered_quantity = models.DecimalField(null=True, blank=True, **QTY)
    entered_unit_name = models.CharField(max_length=50, blank=True)
    entered_unit_base_quantity = models.DecimalField(null=True, blank=True, **QTY)
    reference_type = models.CharField(max_length=40, blank=True)
    reference_id = models.UUIDField(null=True, blank=True)
    note = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        indexes = [
            models.Index(fields=["shop_product", "-created_at"]),
            models.Index(fields=["reference_type", "reference_id"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=~Q(quantity_base_delta=0), name="movement_delta_non_zero"
            ),
            models.CheckConstraint(
                condition=(
                    Q(movement_type__in=POSITIVE_ONLY, quantity_base_delta__gt=0)
                    | Q(movement_type__in=NEGATIVE_ONLY, quantity_base_delta__lt=0)
                    | Q(movement_type__in=EITHER_SIGN)
                ),
                name="movement_sign_matches_type",
            ),
            # A movement can be reversed at most once (reversal.reference_id = original id).
            models.UniqueConstraint(
                fields=["reference_id"],
                condition=Q(movement_type="reversal"),
                name="movement_reversed_once",
            ),
        ]

    def __str__(self):
        return f"{self.movement_type} {self.quantity_base_delta} ({self.pk})"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise AppendOnlyError("Stock movements are append-only.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise AppendOnlyError("Stock movements are append-only.")


class DocumentStatus(models.TextChoices):
    ACTIVE = "active"
    PARTIALLY_REVERSED = "partially_reversed"
    VOIDED = "voided"


def _document_status(items) -> str:
    """Derived from the lines, so it can never disagree with the ledger."""
    lines = list(items.all())
    reversed_count = sum(1 for i in lines if i.reversed_at is not None)
    if not lines or reversed_count == 0:
        return DocumentStatus.ACTIVE
    return DocumentStatus.VOIDED if reversed_count == len(lines) else DocumentStatus.PARTIALLY_REVERSED


class PurchaseReceipt(models.Model):
    """Goods actually received. A purchase order that has not arrived is NOT a receipt."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    shop = models.ForeignKey("shops.Shop", on_delete=models.PROTECT, related_name="+")
    supplier_name = models.CharField(max_length=150, blank=True)
    received_at = models.DateTimeField(default=timezone.now)
    currency = models.CharField(max_length=3)
    total_cost = models.DecimalField(null=True, blank=True, **MONEY)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Receipt {self.pk} ({self.currency})"

    @property
    def status(self) -> str:
        return _document_status(self.items)


class PurchaseItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    receipt = models.ForeignKey(PurchaseReceipt, on_delete=models.CASCADE, related_name="items")
    shop_product = models.ForeignKey(ShopProduct, on_delete=models.PROTECT, related_name="+")
    product_unit = models.ForeignKey("catalog.ProductUnit", on_delete=models.PROTECT, related_name="+")
    product_name_snapshot = models.CharField(max_length=200)
    unit_name_snapshot = models.CharField(max_length=50)
    unit_base_quantity_snapshot = models.DecimalField(**QTY)
    quantity = models.DecimalField(**QTY)
    quantity_base = models.DecimalField(**QTY)
    unit_cost = models.DecimalField(null=True, blank=True, **MONEY)
    line_total = models.DecimalField(null=True, blank=True, **MONEY)
    # The ledger movement this line created; set when the line is voided by a reversal.
    movement = models.OneToOneField(
        StockMovement, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    reversed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.product_name_snapshot} x {self.quantity} {self.unit_name_snapshot}"


class Sale(models.Model):
    class Source(models.TextChoices):
        ONLINE = "online"
        OFFLINE = "offline"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    shop = models.ForeignKey("shops.Shop", on_delete=models.PROTECT, related_name="+")
    sold_at = models.DateTimeField(default=timezone.now)
    recording_source = models.CharField(max_length=10, choices=Source.choices, default=Source.ONLINE)
    currency = models.CharField(max_length=3)
    total_amount = models.DecimalField(**MONEY)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Sale {self.pk} ({self.currency})"

    @property
    def status(self) -> str:
        return _document_status(self.items)


class SaleItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name="items")
    shop_product = models.ForeignKey(ShopProduct, on_delete=models.PROTECT, related_name="+")
    product_unit = models.ForeignKey("catalog.ProductUnit", on_delete=models.PROTECT, related_name="+")
    product_name_snapshot = models.CharField(max_length=200)
    unit_name_snapshot = models.CharField(max_length=50)
    unit_base_quantity_snapshot = models.DecimalField(**QTY)
    quantity = models.DecimalField(**QTY)
    quantity_base = models.DecimalField(**QTY)
    unit_price = models.DecimalField(**MONEY)
    line_total = models.DecimalField(**MONEY)
    movement = models.OneToOneField(
        StockMovement, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    reversed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.product_name_snapshot} x {self.quantity} {self.unit_name_snapshot}"


class StockCount(models.Model):
    """A physical count. It never changes stock by itself: only approval does."""

    class Status(models.TextChoices):
        IN_PROGRESS = "in_progress"
        SUBMITTED = "submitted"
        APPROVED = "approved"
        CANCELLED = "cancelled"

    OPEN_STATUSES = (Status.IN_PROGRESS, Status.SUBMITTED)

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    shop = models.ForeignKey("shops.Shop", on_delete=models.PROTECT, related_name="+")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.IN_PROGRESS)
    note = models.CharField(max_length=255, blank=True)
    started_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    started_at = models.DateTimeField(default=timezone.now)
    submitted_at = models.DateTimeField(null=True, blank=True)
    # Who approved or cancelled it, when, and (for a cancellation) why.
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolution_note = models.CharField(max_length=255, blank=True)

    class Meta:
        constraints = [
            # One open count per shop, so two counts can never fight over the same stock.
            models.UniqueConstraint(
                fields=["shop"],
                condition=Q(status__in=["in_progress", "submitted"]),
                name="one_open_stock_count_per_shop",
            ),
        ]
        indexes = [models.Index(fields=["shop", "-started_at"])]

    def __str__(self):
        return f"count {self.pk} ({self.status})"


class StockCountItem(models.Model):
    """expected/counted/variance are base units and are kept for audit after approval."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    stock_count = models.ForeignKey(StockCount, on_delete=models.CASCADE, related_name="items")
    shop_product = models.ForeignKey(ShopProduct, on_delete=models.PROTECT, related_name="+")
    # Snapshot of the ledger balance at the moment the count was entered.
    expected_quantity_base = models.DecimalField(null=True, blank=True, **QTY)
    counted_quantity_base = models.DecimalField(null=True, blank=True, **QTY)
    variance_base = models.DecimalField(null=True, blank=True, **QTY)  # counted - expected
    counted_at = models.DateTimeField(null=True, blank=True)
    # The adjustment written on approval (absent when there was no variance).
    adjustment = models.OneToOneField(
        StockMovement, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["stock_count", "shop_product"], name="uniq_product_per_stock_count"
            ),
            models.CheckConstraint(
                condition=Q(counted_quantity_base__isnull=True) | Q(counted_quantity_base__gte=0),
                name="stockcountitem_counted_non_negative",
            ),
        ]

    def __str__(self):
        return f"{self.shop_product_id} in {self.stock_count_id}"
