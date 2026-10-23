from decimal import Decimal

from rest_framework import serializers

from apps.suppliers import services as supplier_services

from .models import GroupOrder

QTY = {"max_digits": 18, "decimal_places": 6, "min_value": Decimal("0.000001")}


# ------------------------------------------------------------------ input
class CreateGroupIn(serializers.Serializer):
    idempotency_key = serializers.UUIDField()
    offer_id = serializers.UUIDField()
    target_quantity = serializers.DecimalField(**QTY)  # in the offer unit, e.g. sacks
    quantity = serializers.DecimalField(**QTY)  # the organising shop's own commitment
    deadline = serializers.DateTimeField()
    delivery_method = serializers.ChoiceField(choices=GroupOrder.DeliveryMethod.choices)
    delivery_point = serializers.CharField(max_length=255)
    estimated_delivery_fee = serializers.DecimalField(
        max_digits=14, decimal_places=2, min_value=Decimal("0"), required=False,
        default=Decimal("0"),
    )  # fmt: skip
    note = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")


class CommitmentIn(serializers.Serializer):
    idempotency_key = serializers.UUIDField()
    quantity = serializers.DecimalField(**QTY)


class WithdrawIn(serializers.Serializer):
    idempotency_key = serializers.UUIDField()


class ReasonIn(serializers.Serializer):
    reason = serializers.CharField(max_length=255)


# ------------------------------------------------------------------ output
def _price(value) -> str:
    return f"{value:.2f}"


class GroupOrderSerializer(serializers.ModelSerializer):
    """Never lists other shops: only counts, totals and the caller's own commitment."""

    wholesaler = serializers.SerializerMethodField()
    product_name = serializers.CharField(source="product_name_snapshot", read_only=True)
    unit_name = serializers.CharField(source="unit_name_snapshot", read_only=True)
    unit_base_quantity = serializers.DecimalField(
        source="unit_base_quantity_snapshot", max_digits=18, decimal_places=6, read_only=True
    )
    list_price = serializers.DecimalField(
        source="list_price_snapshot", max_digits=14, decimal_places=2, read_only=True
    )
    progress = serializers.SerializerMethodField()
    estimated_unit_price = serializers.SerializerMethodField()
    unit_price_at_target = serializers.SerializerMethodField()
    is_organiser = serializers.SerializerMethodField()
    my_commitment = serializers.SerializerMethodField()
    binding = serializers.SerializerMethodField()

    class Meta:
        model = GroupOrder
        fields = (
            "id", "status", "status_note", "offer_id", "product_id", "product_unit_id",
            "product_name", "unit_name", "unit_base_quantity", "currency", "list_price",
            "minimum_per_shop", "target_quantity", "committed_quantity", "committed_quantity_base",
            "participant_count", "progress", "estimated_unit_price", "unit_price_at_target",
            "deadline", "delivery_method", "delivery_point", "estimated_delivery_fee", "note",
            "wholesaler", "is_organiser", "my_commitment", "binding", "created_at", "closed_at",
        )  # fmt: skip
        read_only_fields = fields

    def _shop(self):
        return self.context["shop"]

    def get_wholesaler(self, obj) -> dict:
        w = obj.wholesaler
        return {"id": w.pk, "business_name": w.business_name}

    def get_progress(self, obj) -> str:
        return f"{obj.committed_quantity / obj.target_quantity:.4f}"

    def get_estimated_unit_price(self, obj) -> str:
        """The tier price for what is committed so far. The FINAL price is set at confirmation
        and can never be higher than the list price."""
        if obj.committed_quantity <= 0:
            return _price(obj.list_price_snapshot)
        return _price(supplier_services.effective_unit_price(obj.offer, obj.committed_quantity))

    def get_unit_price_at_target(self, obj) -> str:
        return _price(supplier_services.effective_unit_price(obj.offer, obj.target_quantity))

    def get_is_organiser(self, obj) -> bool:
        return obj.organiser_shop_id == self._shop().pk

    def get_my_commitment(self, obj) -> dict | None:
        for p in obj.participants.all():
            if p.shop_id == self._shop().pk:
                return {
                    "status": p.status,
                    "quantity": f"{p.quantity:.6f}",
                    "quantity_base": f"{p.quantity_base:.6f}",
                    "joined_at": p.joined_at,
                }
        return None

    def get_binding(self, obj) -> bool:
        """Joining is never binding; commitments bind only once the wholesaler confirms."""
        return obj.status == GroupOrder.Status.CONFIRMED
