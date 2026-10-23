import uuid
from decimal import Decimal

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from .models import Order, OrderItem

QTY = {"max_digits": 18, "decimal_places": 6, "min_value": Decimal("0.000001")}


# ------------------------------------------------------------------ input
class OrderLineIn(serializers.Serializer):
    offer_id = serializers.UUIDField()
    quantity = serializers.DecimalField(**QTY)  # in the offer's unit, e.g. sacks


class PlaceOrderIn(serializers.Serializer):
    idempotency_key = serializers.UUIDField()
    items = OrderLineIn(many=True, allow_empty=False, max_length=50)
    delivery_method = serializers.ChoiceField(
        choices=Order.DeliveryMethod.choices, default=Order.DeliveryMethod.DELIVERY
    )
    delivery_address = serializers.CharField(
        max_length=255, required=False, allow_blank=True, default=""
    )
    contact_phone = serializers.CharField(
        max_length=20, required=False, allow_blank=True, default=""
    )
    note = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")


class ConfirmOrderIn(serializers.Serializer):
    delivery_fee = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        min_value=Decimal("0"),
        required=False,
        default=Decimal("0"),
    )


class ReasonIn(serializers.Serializer):
    reason = serializers.CharField(max_length=255)


class ReceiveLineIn(serializers.Serializer):
    item_id = serializers.UUIDField()
    received_quantity = serializers.DecimalField(
        max_digits=18, decimal_places=6, min_value=Decimal("0")
    )


class ReceiveOrderIn(serializers.Serializer):
    idempotency_key = serializers.UUIDField()
    items = ReceiveLineIn(many=True, allow_empty=False, max_length=50)
    note = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")


# ------------------------------------------------------------------ output
class OrderItemSerializer(serializers.ModelSerializer):
    shortage = serializers.SerializerMethodField()

    class Meta:
        model = OrderItem
        fields = (
            "id", "offer_id", "product_id", "product_unit_id", "product_name", "unit_name",
            "unit_base_quantity", "quantity", "quantity_base", "list_price", "unit_price",
            "line_total", "received_quantity", "shortage",
        )  # fmt: skip
        read_only_fields = fields

    product_name = serializers.CharField(source="product_name_snapshot", read_only=True)
    unit_name = serializers.CharField(source="unit_name_snapshot", read_only=True)
    unit_base_quantity = serializers.DecimalField(
        source="unit_base_quantity_snapshot", max_digits=18, decimal_places=6, read_only=True
    )
    list_price = serializers.DecimalField(
        source="list_price_snapshot", max_digits=14, decimal_places=2, read_only=True
    )
    unit_price = serializers.DecimalField(
        source="unit_price_snapshot", max_digits=14, decimal_places=2, read_only=True
    )

    def get_shortage(self, obj) -> str | None:
        if obj.received_quantity is None:
            return None
        return format(obj.quantity - obj.received_quantity, "f")


class ShopRefOut(serializers.Serializer):
    """All a supplier learns about the ordering shop."""

    name = serializers.CharField()


class WholesalerRefOut(serializers.Serializer):
    id = serializers.UUIDField()
    business_name = serializers.CharField()
    contact_phone = serializers.CharField()


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    shop = serializers.SerializerMethodField()
    wholesaler = serializers.SerializerMethodField()
    group_order_id = serializers.SerializerMethodField()
    has_shortage = serializers.BooleanField(read_only=True)
    purchase_receipt_id = serializers.UUIDField(read_only=True, allow_null=True)

    class Meta:
        model = Order
        fields = (
            "id", "status", "status_note", "cancelled_by", "shop", "wholesaler", "currency",
            "subtotal", "delivery_fee", "total_amount", "delivery_method", "delivery_address",
            "contact_phone", "note", "submitted_at", "confirmed_at", "dispatched_at",
            "received_at", "closed_at", "receipt_note", "has_shortage", "purchase_receipt_id",
            "group_order_id", "items",
        )  # fmt: skip
        read_only_fields = fields

    @extend_schema_field(ShopRefOut)
    def get_shop(self, obj):
        # Only what the supplier needs to fulfil the order: never inventory or other shop data.
        return {"name": obj.shop.name}

    def get_group_order_id(self, obj) -> uuid.UUID | None:
        """The group this order was generated from, if any. Such an order cannot be cancelled by
        the shop (the wholesaler cancels it)."""
        link = getattr(obj, "group_participation", None)
        return link.group_id if link else None

    @extend_schema_field(WholesalerRefOut)
    def get_wholesaler(self, obj):
        w = obj.wholesaler
        return {"id": w.pk, "business_name": w.business_name, "contact_phone": w.contact_phone}
