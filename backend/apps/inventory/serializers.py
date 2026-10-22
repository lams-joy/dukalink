from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.utils import timezone
from rest_framework import serializers

from .models import (
    MovementType,
    PurchaseItem,
    PurchaseReceipt,
    Sale,
    SaleItem,
    ShopProduct,
    StockCount,
    StockCountItem,
    StockMovement,
)


def qty_field(**kw):
    return serializers.DecimalField(
        max_digits=18, decimal_places=6, min_value=settings.MIN_QUANTITY, **kw
    )


def money_field(**kw):
    return serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0"), **kw)


def not_in_future(value):
    if value > timezone.now() + timedelta(minutes=5):
        raise serializers.ValidationError("Time cannot be in the future.")
    return value


# ------------------------------------------------------------------ outputs
class InventoryItemSerializer(serializers.ModelSerializer):
    product_id = serializers.UUIDField(read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)
    base_unit = serializers.CharField(source="product.base_unit", read_only=True)
    is_low_stock = serializers.SerializerMethodField()

    class Meta:
        model = ShopProduct
        fields = (
            "id", "product_id", "product_name", "base_unit", "quantity_base",
            "reorder_level_base", "tracking_mode", "is_low_stock", "updated_at",
        )  # fmt: skip
        read_only_fields = fields

    def get_is_low_stock(self, obj) -> bool:
        return obj.reorder_level_base is not None and obj.quantity_base <= obj.reorder_level_base


class MovementSerializer(serializers.ModelSerializer):
    shop_product_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = StockMovement
        fields = (
            "id", "shop_product_id", "movement_type", "quantity_base_delta",
            "balance_after_base", "unit_cost_base", "entered_quantity", "entered_unit_name",
            "entered_unit_base_quantity", "reference_type", "reference_id", "note", "created_at",
        )  # fmt: skip
        read_only_fields = fields


class PurchaseItemOut(serializers.ModelSerializer):
    shop_product_id = serializers.UUIDField(read_only=True)
    product_unit_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = PurchaseItem
        fields = (
            "id", "shop_product_id", "product_unit_id", "product_name_snapshot",
            "unit_name_snapshot", "unit_base_quantity_snapshot", "quantity", "quantity_base",
            "unit_cost", "line_total", "reversed_at",
        )  # fmt: skip
        read_only_fields = fields


class PurchaseReceiptOut(serializers.ModelSerializer):
    items = PurchaseItemOut(many=True, read_only=True)
    status = serializers.CharField(read_only=True)

    class Meta:
        model = PurchaseReceipt
        fields = (
            "id", "supplier_name", "received_at", "currency", "total_cost", "status", "items",
        )  # fmt: skip
        read_only_fields = fields


class SaleItemOut(serializers.ModelSerializer):
    shop_product_id = serializers.UUIDField(read_only=True)
    product_unit_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = SaleItem
        fields = (
            "id", "shop_product_id", "product_unit_id", "product_name_snapshot",
            "unit_name_snapshot", "unit_base_quantity_snapshot", "quantity", "quantity_base",
            "unit_price", "line_total", "reversed_at",
        )  # fmt: skip
        read_only_fields = fields


class SaleOut(serializers.ModelSerializer):
    items = SaleItemOut(many=True, read_only=True)
    status = serializers.CharField(read_only=True)

    class Meta:
        model = Sale
        fields = (
            "id", "sold_at", "recording_source", "currency", "total_amount", "status", "items",
        )  # fmt: skip
        read_only_fields = fields


# ------------------------------------------------------------------ inputs
class TrackProductIn(serializers.Serializer):
    product_id = serializers.UUIDField()
    reorder_level_base = serializers.DecimalField(
        max_digits=18, decimal_places=6, min_value=Decimal("0"), required=False, allow_null=True
    )


class InventorySettingsIn(serializers.Serializer):
    reorder_level_base = serializers.DecimalField(
        max_digits=18, decimal_places=6, min_value=Decimal("0"), required=False, allow_null=True
    )
    tracking_mode = serializers.ChoiceField(choices=ShopProduct.TrackingMode.choices, required=False)


class OpeningStockIn(serializers.Serializer):
    idempotency_key = serializers.UUIDField()
    product_unit_id = serializers.UUIDField()
    quantity = qty_field()
    unit_cost = money_field(required=False, allow_null=True)
    note = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")


class AdjustmentIn(serializers.Serializer):
    idempotency_key = serializers.UUIDField()
    shop_product_id = serializers.UUIDField()
    quantity_base_delta = serializers.DecimalField(max_digits=18, decimal_places=6)
    reason = serializers.CharField(max_length=255)

    def validate_quantity_base_delta(self, value):
        if value == 0:
            raise serializers.ValidationError("An adjustment cannot be zero.")
        return value


class ReceiptItemIn(serializers.Serializer):
    product_id = serializers.UUIDField()
    product_unit_id = serializers.UUIDField()
    quantity = qty_field()
    unit_cost = money_field(required=False, allow_null=True)


class PurchaseReceiptIn(serializers.Serializer):
    idempotency_key = serializers.UUIDField()
    supplier_name = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")
    received_at = serializers.DateTimeField(required=False, validators=[not_in_future])
    items = ReceiptItemIn(many=True, allow_empty=False, max_length=200)


class SaleItemIn(serializers.Serializer):
    shop_product_id = serializers.UUIDField()
    product_unit_id = serializers.UUIDField()
    quantity = qty_field()
    unit_price = money_field()


class SaleIn(serializers.Serializer):
    idempotency_key = serializers.UUIDField()
    sold_at = serializers.DateTimeField(required=False, validators=[not_in_future])
    recording_source = serializers.ChoiceField(
        choices=Sale.Source.choices, default=Sale.Source.ONLINE
    )
    items = SaleItemIn(many=True, allow_empty=False, max_length=200)


class ReversalIn(serializers.Serializer):
    idempotency_key = serializers.UUIDField()
    reason = serializers.CharField(max_length=255)  # required, non-blank: this is an audit trail


class LowStockAlertSerializer(serializers.ModelSerializer):
    type = serializers.SerializerMethodField()
    shop_product_id = serializers.UUIDField(source="id", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)
    base_unit = serializers.CharField(source="product.base_unit", read_only=True)
    shortfall_base = serializers.SerializerMethodField()

    class Meta:
        model = ShopProduct
        fields = (
            "type", "shop_product_id", "product_name", "base_unit",
            "quantity_base", "reorder_level_base", "shortfall_base",
        )  # fmt: skip
        read_only_fields = fields

    def get_type(self, obj) -> str:
        return "low_stock"

    def get_shortfall_base(self, obj) -> str:
        return str(obj.reorder_level_base - obj.quantity_base)


# ------------------------------------------------------------------ custom products
class CustomUnitIn(serializers.Serializer):
    unit_name = serializers.CharField(max_length=50)
    base_quantity = qty_field()  # how many BASE units one of this unit holds
    is_purchase_unit = serializers.BooleanField(default=True)
    is_sale_unit = serializers.BooleanField(default=True)


class CustomProductIn(serializers.Serializer):
    idempotency_key = serializers.UUIDField()
    name = serializers.CharField(max_length=200)
    base_unit = serializers.CharField(max_length=50)  # e.g. kg, litre, piece
    brand = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    barcode = serializers.CharField(max_length=32, required=False, allow_blank=True, default="")
    category = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    units = CustomUnitIn(many=True, required=False, max_length=20, default=list)
    track = serializers.BooleanField(default=True)  # also start tracking it in this shop
    reorder_level_base = serializers.DecimalField(
        max_digits=18, decimal_places=6, min_value=Decimal("0"), required=False, allow_null=True
    )


class AddUnitIn(CustomUnitIn):
    idempotency_key = serializers.UUIDField()


# ------------------------------------------------------------------ stock counts
class StockCountItemOut(serializers.ModelSerializer):
    shop_product_id = serializers.UUIDField(read_only=True)
    product_name = serializers.CharField(source="shop_product.product.name", read_only=True)
    base_unit = serializers.CharField(source="shop_product.product.base_unit", read_only=True)
    adjustment_movement_id = serializers.UUIDField(source="adjustment_id", read_only=True)

    class Meta:
        model = StockCountItem
        fields = (
            "id", "shop_product_id", "product_name", "base_unit", "expected_quantity_base",
            "counted_quantity_base", "variance_base", "counted_at", "adjustment_movement_id",
        )  # fmt: skip
        read_only_fields = fields


class StockCountOut(serializers.ModelSerializer):
    items = StockCountItemOut(many=True, read_only=True)
    counted_items = serializers.SerializerMethodField()
    total_items = serializers.SerializerMethodField()

    class Meta:
        model = StockCount
        fields = (
            "id", "status", "note", "started_at", "submitted_at", "resolved_at",
            "resolution_note", "total_items", "counted_items", "items",
        )  # fmt: skip
        read_only_fields = fields

    def get_total_items(self, obj) -> int:
        return len(obj.items.all())

    def get_counted_items(self, obj) -> int:
        return sum(1 for i in obj.items.all() if i.counted_quantity_base is not None)


class StockCountStartIn(serializers.Serializer):
    idempotency_key = serializers.UUIDField()
    shop_product_ids = serializers.ListField(
        child=serializers.UUIDField(), required=False, allow_empty=False, max_length=500
    )
    note = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")


class CountEntryIn(serializers.Serializer):
    shop_product_id = serializers.UUIDField()
    product_unit_id = serializers.UUIDField()
    # Zero is allowed here (an empty shelf), unlike every other quantity in the API.
    quantity = serializers.DecimalField(max_digits=18, decimal_places=6, min_value=Decimal("0"))


class StockCountRecordIn(serializers.Serializer):
    idempotency_key = serializers.UUIDField()
    items = CountEntryIn(many=True, allow_empty=False, max_length=500)

    def validate_items(self, items):
        ids = [i["shop_product_id"] for i in items]
        if len(ids) != len(set(ids)):
            raise serializers.ValidationError("Each product can appear only once per request.")
        return items


class StockCountActionIn(serializers.Serializer):
    """Submit / approve: no body beyond the idempotency key."""

    idempotency_key = serializers.UUIDField()


MOVEMENT_TYPES = [c for c, _ in MovementType.choices]
