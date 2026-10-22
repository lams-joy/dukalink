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
