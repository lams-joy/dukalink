from decimal import Decimal

from django.utils import timezone
from rest_framework import serializers

from .models import SupplierOffer, SupplierPriceTier, Wholesaler, WholesalerMembership

PRICE = {"max_digits": 14, "decimal_places": 2, "min_value": Decimal("0.01")}
QTY = {"max_digits": 18, "decimal_places": 6, "min_value": Decimal("0.000001")}


# ------------------------------------------------------------------ wholesalers
class WholesalerSerializer(serializers.ModelSerializer):
    """What a wholesaler's own members see. Verification is read-only here."""

    my_role = serializers.CharField(read_only=True, required=False)
    status_note = serializers.CharField(source="verification_note", read_only=True)

    class Meta:
        model = Wholesaler
        fields = (
            "id", "business_name", "contact_phone", "location_text", "latitude", "longitude",
            "verification_status", "verified_at", "status_note", "my_role",
            "created_at", "updated_at",
        )  # fmt: skip
        read_only_fields = (
            "id", "verification_status", "verified_at", "created_at", "updated_at",
        )  # fmt: skip


class PublicWholesalerSerializer(serializers.ModelSerializer):
    """What shops see: no internal verification notes, no member details."""

    offer_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Wholesaler
        fields = (
            "id", "business_name", "contact_phone", "location_text", "latitude", "longitude",
            "verified_at", "offer_count",
        )  # fmt: skip
        read_only_fields = fields


class AdminWholesalerSerializer(WholesalerSerializer):
    class Meta(WholesalerSerializer.Meta):
        fields = (*WholesalerSerializer.Meta.fields,)
        read_only_fields = fields


class AddWholesalerMemberSerializer(serializers.Serializer):
    phone_number = serializers.CharField(max_length=20)
    role = serializers.ChoiceField(
        choices=[WholesalerMembership.Role.MANAGER.value, WholesalerMembership.Role.STAFF.value]
    )


class WholesalerMembershipSerializer(serializers.ModelSerializer):
    class Meta:
        model = WholesalerMembership
        fields = ("id", "user", "role", "status", "created_at")
        read_only_fields = fields


class VerificationActionSerializer(serializers.Serializer):
    note = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")


class QuoteSerializer(serializers.Serializer):
    """Money and quantities as strings, like every other endpoint."""

    offer_id = serializers.UUIDField()
    quantity = serializers.DecimalField(max_digits=18, decimal_places=6)
    meets_minimum = serializers.BooleanField()
    minimum_order_quantity = serializers.DecimalField(max_digits=18, decimal_places=6)
    unit_price = serializers.DecimalField(max_digits=14, decimal_places=2)
    line_total = serializers.DecimalField(max_digits=16, decimal_places=2)
    currency = serializers.CharField()
    quantity_base = serializers.DecimalField(max_digits=24, decimal_places=6)


# ------------------------------------------------------------------ offers: input
class TierIn(serializers.Serializer):
    minimum_quantity = serializers.DecimalField(**QTY)
    unit_price = serializers.DecimalField(**PRICE)
    valid_from = serializers.DateTimeField(required=False, allow_null=True)
    valid_until = serializers.DateTimeField(required=False, allow_null=True)


class OfferCreateIn(serializers.Serializer):
    product_id = serializers.UUIDField()
    product_unit_id = serializers.UUIDField()
    price_per_unit = serializers.DecimalField(**PRICE)
    minimum_order_quantity = serializers.DecimalField(default=Decimal("1"), **QTY)
    availability = serializers.ChoiceField(
        choices=SupplierOffer.Availability.choices, required=False
    )
    available_quantity = serializers.DecimalField(
        max_digits=18, decimal_places=6, min_value=Decimal("0"), required=False, allow_null=True
    )
    delivery_areas = serializers.CharField(max_length=255, required=False, allow_blank=True)
    delivery_terms = serializers.CharField(max_length=255, required=False, allow_blank=True)
    is_active = serializers.BooleanField(required=False)
    tiers = TierIn(many=True, required=False)


class OfferUpdateIn(serializers.Serializer):
    price_per_unit = serializers.DecimalField(required=False, **PRICE)
    minimum_order_quantity = serializers.DecimalField(required=False, **QTY)
    availability = serializers.ChoiceField(
        choices=SupplierOffer.Availability.choices, required=False
    )
    available_quantity = serializers.DecimalField(
        max_digits=18, decimal_places=6, min_value=Decimal("0"), required=False, allow_null=True
    )
    delivery_areas = serializers.CharField(max_length=255, required=False, allow_blank=True)
    delivery_terms = serializers.CharField(max_length=255, required=False, allow_blank=True)
    is_active = serializers.BooleanField(required=False)


class TiersReplaceIn(serializers.Serializer):
    tiers = TierIn(many=True)


# ------------------------------------------------------------------ offers: output
class TierSerializer(serializers.ModelSerializer):
    class Meta:
        model = SupplierPriceTier
        fields = ("minimum_quantity", "unit_price", "valid_from", "valid_until")
        read_only_fields = fields


class _OfferBase(serializers.ModelSerializer):
    product = serializers.SerializerMethodField()
    unit = serializers.SerializerMethodField()
    price_per_base_unit = serializers.SerializerMethodField()

    def get_product(self, obj):
        p = obj.product
        return {"id": p.pk, "name": p.name, "brand": p.brand, "base_unit": p.base_unit}

    def get_unit(self, obj):
        u = obj.product_unit
        return {"id": u.pk, "unit_name": u.unit_name, "base_quantity": u.base_quantity}

    def get_price_per_base_unit(self, obj) -> str:
        """Comparable across pack sizes: 7,000 per 50 kg sack = 140.00 per kg."""
        value = obj.price_per_unit / obj.product_unit.base_quantity
        return format(value.quantize(Decimal("0.0001")), "f")


class SupplierOfferSerializer(_OfferBase):
    """A wholesaler's own view of an offer: every tier, drafts included."""

    tiers = TierSerializer(many=True, read_only=True)

    class Meta:
        model = SupplierOffer
        fields = (
            "id", "product", "unit", "price_per_unit", "price_per_base_unit", "currency",
            "minimum_order_quantity", "availability", "available_quantity", "delivery_areas",
            "delivery_terms", "is_active", "tiers", "created_at", "updated_at",
        )  # fmt: skip
        read_only_fields = fields


class MarketOfferSerializer(_OfferBase):
    """A shop's view: live offers only, current tiers only, public wholesaler summary."""

    wholesaler = serializers.SerializerMethodField()
    tiers = serializers.SerializerMethodField()

    class Meta:
        model = SupplierOffer
        fields = (
            "id", "wholesaler", "product", "unit", "price_per_unit", "price_per_base_unit",
            "currency", "minimum_order_quantity", "availability", "available_quantity",
            "delivery_areas", "delivery_terms", "tiers", "updated_at",
        )  # fmt: skip
        read_only_fields = fields

    def get_wholesaler(self, obj):
        w = obj.wholesaler
        return {"id": w.pk, "business_name": w.business_name, "location_text": w.location_text}

    def get_tiers(self, obj):
        now = timezone.now()
        live = [
            t for t in obj.tiers.all()
            if (t.valid_from is None or t.valid_from <= now)
            and (t.valid_until is None or t.valid_until > now)
        ]  # fmt: skip
        return TierSerializer(live, many=True).data
