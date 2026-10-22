from uuid import UUID

from django.db.models import F, Q
from rest_framework import status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.generics import ListAPIView, ListCreateAPIView, RetrieveAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.shops.access import MANAGEMENT_ROLES, get_membership
from apps.sync.idempotency import run_idempotent, to_jsonable

from . import serializers as s
from . import services
from .models import ShopProduct, StockMovement


class ShopScopedMixin:
    """Resolve and authorise the shop from the URL before touching any data."""

    def membership(self, roles=None):
        return get_membership(self.request.user, self.kwargs["shop_id"], roles=roles)

    @property
    def _fake(self) -> bool:  # drf-spectacular schema generation
        return getattr(self, "swagger_fake_view", False)


def _idempotent_write(request, membership, operation_type, input_cls, build, output_cls):
    """Validate -> run once per idempotency key -> return the stored result on replays."""
    serializer = input_cls(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = dict(serializer.validated_data)
    key = data.pop("idempotency_key")

    def handler():
        obj = build(data)
        return status.HTTP_201_CREATED, output_cls(obj).data

    result = run_idempotent(
        user=request.user,
        shop=membership.shop,
        operation_type=operation_type,
        operation_id=key,
        payload=to_jsonable(data),
        handler=handler,
    )
    response = Response(result.body, status=result.status)
    if result.replayed:
        response["Idempotent-Replayed"] = "true"
    return response


# ------------------------------------------------------------------ inventory
class InventoryListCreateView(ShopScopedMixin, ListCreateAPIView):
    serializer_class = s.InventoryItemSerializer

    def get_queryset(self):
        if self._fake:
            return ShopProduct.objects.none()
        shop = self.membership().shop
        qs = ShopProduct.objects.filter(shop=shop, is_active=True).select_related("product")
        q = self.request.query_params.get("q", "").strip()
        if q:
            qs = qs.filter(Q(product__name__icontains=q) | Q(product__brand__icontains=q))
        if self.request.query_params.get("low_stock") == "true":
            qs = qs.filter(reorder_level_base__isnull=False, quantity_base__lte=F("reorder_level_base"))
        return qs.order_by("product__name")

    def create(self, request, *args, **kwargs):
        membership = self.membership(roles=MANAGEMENT_ROLES)
        data = s.TrackProductIn(data=request.data)
        data.is_valid(raise_exception=True)
        item = services.track_product(shop=membership.shop, **data.validated_data)
        item = ShopProduct.objects.select_related("product").get(pk=item.pk)
        return Response(s.InventoryItemSerializer(item).data, status=status.HTTP_201_CREATED)


class InventoryDetailView(ShopScopedMixin, RetrieveAPIView):
    serializer_class = s.InventoryItemSerializer
    lookup_url_kwarg = "item_id"

    def get_queryset(self):
        if self._fake:
            return ShopProduct.objects.none()
        return ShopProduct.objects.filter(shop=self.membership().shop).select_related("product")


class InventorySettingsView(ShopScopedMixin, APIView):
    def patch(self, request, shop_id, item_id):
        membership = self.membership(roles=MANAGEMENT_ROLES)
        item = ShopProduct.objects.select_related("product").filter(
            shop=membership.shop, pk=item_id
        ).first()
        if item is None:
            raise NotFound()
        data = s.InventorySettingsIn(data=request.data, partial=True)
        data.is_valid(raise_exception=True)
        for field, value in data.validated_data.items():
            setattr(item, field, value)
        item.save(update_fields=[*data.validated_data.keys(), "updated_at"])
        return Response(s.InventoryItemSerializer(item).data)


class OpeningStockView(ShopScopedMixin, APIView):
    def post(self, request, shop_id, item_id):
        membership = self.membership(roles=MANAGEMENT_ROLES)

        def build(data):
            return services.record_opening_stock(
                shop=membership.shop, user=request.user, shop_product_id=item_id,
                unit_id=data["product_unit_id"], quantity=data["quantity"],
                unit_cost=data.get("unit_cost"), note=data["note"],
            )  # fmt: skip

        return _idempotent_write(
            request, membership, f"opening_stock:{item_id}", s.OpeningStockIn, build, s.MovementSerializer
        )


class StockAdjustmentView(ShopScopedMixin, APIView):
    def post(self, request, shop_id):
        membership = self.membership(roles=MANAGEMENT_ROLES)

        def build(data):
            return services.record_adjustment(
                shop=membership.shop, user=request.user,
                shop_product_id=data["shop_product_id"],
                delta_base=data["quantity_base_delta"], reason=data["reason"],
            )  # fmt: skip

        return _idempotent_write(
            request, membership, "stock_adjustment", s.AdjustmentIn, build, s.MovementSerializer
        )


class PurchaseReceiptView(ShopScopedMixin, APIView):
    def post(self, request, shop_id):
        membership = self.membership()

        def build(data):
            return services.record_purchase_receipt(
                shop=membership.shop, user=request.user, items=data["items"],
                supplier_name=data["supplier_name"], received_at=data.get("received_at"),
            )  # fmt: skip

        return _idempotent_write(
            request, membership, "purchase_receipt", s.PurchaseReceiptIn, build, s.PurchaseReceiptOut
        )


class SaleView(ShopScopedMixin, APIView):
    def post(self, request, shop_id):
        membership = self.membership()

        def build(data):
            return services.record_sale(
                shop=membership.shop, user=request.user, items=data["items"],
                sold_at=data.get("sold_at"), recording_source=data["recording_source"],
            )  # fmt: skip

        return _idempotent_write(request, membership, "sale", s.SaleIn, build, s.SaleOut)


class StockMovementListView(ShopScopedMixin, ListAPIView):
    """History. Filters: ?shop_product_id=<uuid>&movement_type=<type>"""

    serializer_class = s.MovementSerializer

    def get_queryset(self):
        if self._fake:
            return StockMovement.objects.none()
        shop = self.membership().shop
        qs = StockMovement.objects.filter(shop_product__shop=shop)
        params = self.request.query_params
        if params.get("shop_product_id"):
            try:
                product_filter = UUID(params["shop_product_id"])
            except ValueError:
                raise ValidationError({"shop_product_id": ["Enter a valid UUID."]}) from None
            qs = qs.filter(shop_product_id=product_filter)
        if params.get("movement_type") in s.MOVEMENT_TYPES:
            qs = qs.filter(movement_type=params["movement_type"])
        return qs.order_by("-created_at", "-id")
