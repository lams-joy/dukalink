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


class ConfirmGroupIn(serializers.Serializer):
    """Both optional. `unit_price` defaults to (and may not exceed) the tier price for the
    committed total; `delivery_fee` defaults to 0 and may not exceed the group's estimate."""

    unit_price = serializers.DecimalField(
        max_digits=14, decimal_places=2, min_value=Decimal("0.01"), required=False,
        allow_null=True, default=None,
    )  # fmt: skip
    delivery_fee = serializers.DecimalField(
        max_digits=14, decimal_places=2, min_value=Decimal("0"), required=False,
        default=Decimal("0"),
    )  # fmt: skip


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
    terms = serializers.SerializerMethodField()

    class Meta:
        model = GroupOrder
        fields = (
            "id", "status", "status_note", "offer_id", "product_id", "product_unit_id",
            "product_name", "unit_name", "unit_base_quantity", "currency", "list_price",
            "minimum_per_shop", "target_quantity", "committed_quantity", "committed_quantity_base",
            "participant_count", "progress", "estimated_unit_price", "unit_price_at_target",
            "deadline", "delivery_method", "delivery_point", "estimated_delivery_fee", "note",
            "wholesaler", "is_organiser", "my_commitment", "binding", "confirmed_unit_price",
            "confirmed_delivery_fee", "confirmed_at", "terms", "created_at", "closed_at",
        )  # fmt: skip
        read_only_fields = fields

    def _shop(self):
        """The viewing shop; absent when the wholesaler is looking."""
        return self.context.get("shop")

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
        shop = self._shop()
        return shop is not None and obj.organiser_shop_id == shop.pk

    def get_my_commitment(self, obj) -> dict | None:
        shop = self._shop()
        if shop is None:
            return None
        for p in obj.participants.all():
            if p.shop_id == shop.pk:
                return {
                    "status": p.status,
                    "quantity": f"{p.quantity:.6f}",
                    "quantity_base": f"{p.quantity_base:.6f}",
                    "joined_at": p.joined_at,
                    # filled in once the wholesaler confirms the group
                    "order_id": p.order_id,
                    "goods_total": None if p.goods_total is None else f"{p.goods_total:.2f}",
                    "delivery_share": (
                        None if p.delivery_share is None else f"{p.delivery_share:.2f}"
                    ),
                }
        return None

    def get_binding(self, obj) -> bool:
        """Joining is never binding; commitments bind only once the wholesaler confirms."""
        return obj.status == GroupOrder.Status.CONFIRMED

    def get_terms(self, obj) -> dict | None:
        """The frozen terms, once confirmed; null before that."""
        return obj.terms_snapshot if obj.status == GroupOrder.Status.CONFIRMED else None


# ------------------------------------------------------------------ cost breakdown (documentation)
# The breakdown is built by services.cost_breakdown() as a plain dict; these describe its shape
# for the API schema. Money and quantities are strings, exactly as sent.
class CostLineOut(serializers.Serializer):
    order_id = serializers.UUIDField()
    order_status = serializers.CharField()
    cancelled_by = serializers.CharField(help_text="'shop' or 'wholesaler'; empty unless cancelled")
    cancel_reason = serializers.CharField(help_text="Empty unless the order was cancelled")
    quantity = serializers.CharField()
    quantity_base = serializers.CharField()
    unit_price = serializers.CharField()
    goods_total = serializers.CharField()
    delivery_share = serializers.CharField()
    total = serializers.CharField()


class CostShopRefOut(serializers.Serializer):
    name = serializers.CharField()


class WholesalerCostLineOut(CostLineOut):
    shop = CostShopRefOut()


class CostBreakdownOut(serializers.Serializer):
    group_id = serializers.UUIDField()
    status = serializers.CharField()
    currency = serializers.CharField()
    unit_price = serializers.CharField()
    tier_minimum_quantity = serializers.CharField(allow_null=True)
    quantity = serializers.CharField()
    quantity_base = serializers.CharField()
    participant_count = serializers.IntegerField()
    goods_total = serializers.CharField()
    delivery_fee = serializers.CharField()
    total = serializers.CharField()
    delivery_method = serializers.CharField()
    delivery_point = serializers.CharField()
    confirmed_at = serializers.DateTimeField()


class ShopCostBreakdownOut(CostBreakdownOut):
    """A shop sees the group totals and only its own line (null if it did not take part)."""

    mine = CostLineOut(allow_null=True)


class WholesalerCostBreakdownOut(CostBreakdownOut):
    """The wholesaler sees one row per generated order."""

    orders = WholesalerCostLineOut(many=True)
