from decimal import Decimal

from rest_framework import serializers

from .models import Product, ProductUnit


class ProductUnitSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductUnit
        fields = ("id", "unit_name", "base_quantity", "is_purchase_unit", "is_sale_unit")
        read_only_fields = fields


class ProductSerializer(serializers.ModelSerializer):
    units = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = ("id", "name", "brand", "barcode", "category", "base_unit", "units")
        read_only_fields = fields

    def get_units(self, obj):
        active = [u for u in obj.units.all() if u.is_active]
        return ProductUnitSerializer(active, many=True).data


class CustomProductSerializer(ProductSerializer):
    """A shop's own product. `shop_product_id` is set when it was tracked on creation."""

    shop_product_id = serializers.SerializerMethodField()

    class Meta(ProductSerializer.Meta):
        fields = (*ProductSerializer.Meta.fields, "shop_product_id")
        read_only_fields = fields

    def get_shop_product_id(self, obj) -> str | None:
        value = getattr(obj, "shop_product_id", None)
        return str(value) if value else None


# ------------------------------------------------------------------ platform admin: shared catalogue
class AdminUnitSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductUnit
        fields = ("id", "unit_name", "base_quantity", "is_purchase_unit", "is_sale_unit", "is_active")
        read_only_fields = fields


class AdminProductSerializer(serializers.ModelSerializer):
    """Everything an administrator needs, including retired units."""

    units = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = ("id", "name", "brand", "barcode", "category", "base_unit", "is_active", "units")
        read_only_fields = fields

    def get_units(self, obj):
        return AdminUnitSerializer(sorted(obj.units.all(), key=lambda u: (u.base_quantity, u.unit_name)), many=True).data


class AdminUnitIn(serializers.Serializer):
    unit_name = serializers.CharField(max_length=50)
    base_quantity = serializers.DecimalField(max_digits=18, decimal_places=6, min_value=Decimal("0.000001"))
    is_purchase_unit = serializers.BooleanField(default=True)
    is_sale_unit = serializers.BooleanField(default=True)


class AdminProductCreateIn(serializers.Serializer):
    name = serializers.CharField(max_length=200)
    brand = serializers.CharField(max_length=100, allow_blank=True, default="")
    barcode = serializers.CharField(max_length=32, allow_blank=True, default="")
    category = serializers.CharField(max_length=100, allow_blank=True, default="")
    base_unit = serializers.CharField(max_length=50)
    units = AdminUnitIn(many=True, required=False)


class AdminProductPatchIn(serializers.Serializer):
    """The base unit is deliberately not editable: stock everywhere is counted in it."""

    name = serializers.CharField(max_length=200, required=False)
    brand = serializers.CharField(max_length=100, allow_blank=True, required=False)
    barcode = serializers.CharField(max_length=32, allow_blank=True, required=False)
    category = serializers.CharField(max_length=100, allow_blank=True, required=False)
    is_active = serializers.BooleanField(required=False)


class AdminUnitPatchIn(serializers.Serializer):
    """The conversion factor is deliberately not editable: add a new unit instead."""

    unit_name = serializers.CharField(max_length=50, required=False)
    is_purchase_unit = serializers.BooleanField(required=False)
    is_sale_unit = serializers.BooleanField(required=False)
    is_active = serializers.BooleanField(required=False)
