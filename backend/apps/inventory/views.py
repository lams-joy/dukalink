from uuid import UUID

from django.db.models import F, Q
from rest_framework import serializers as drf_serializers
from rest_framework import status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.generics import ListAPIView, ListCreateAPIView, RetrieveAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.catalog.models import Product
from apps.catalog.serializers import CustomProductSerializer
from apps.shops.access import MANAGEMENT_ROLES, get_membership

from . import operations as ops
from . import reports, services
from . import serializers as s
from .models import ShopProduct, StockCount, StockMovement


class ShopScopedMixin:
    """Resolve and authorise the shop from the URL before touching any data."""

    def membership(self, roles=None):
        return get_membership(self.request.user, self.kwargs["shop_id"], roles=roles)

    @property
    def _fake(self) -> bool:  # drf-spectacular schema generation
        return getattr(self, "swagger_fake_view", False)


def _execute(request, membership, spec: ops.OperationSpec, target_id=None):
    """Authorise -> validate -> run once per idempotency key; replays return the stored result."""
    ops.authorise(spec, membership)
    serializer = spec.input_cls(data=request.data)
    serializer.is_valid(raise_exception=True)
    result = ops.run_operation(
        spec,
        user=request.user,
        membership=membership,
        data=dict(serializer.validated_data),
        target_id=target_id,
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
            qs = qs.filter(
                reorder_level_base__isnull=False, quantity_base__lte=F("reorder_level_base")
            )
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
        item = (
            ShopProduct.objects.select_related("product")
            .filter(shop=membership.shop, pk=item_id)
            .first()
        )
        if item is None:
            raise NotFound()
        data = s.InventorySettingsIn(data=request.data, partial=True)
        data.is_valid(raise_exception=True)
        for field, value in data.validated_data.items():
            setattr(item, field, value)
        item.save(update_fields=[*data.validated_data.keys(), "updated_at"])
        return Response(s.InventoryItemSerializer(item).data)


# ------------------------------------------------------------------ writes
class OpeningStockView(ShopScopedMixin, APIView):
    def post(self, request, shop_id, item_id):
        return _execute(request, self.membership(), ops.OPENING_STOCK, target_id=item_id)


class StockAdjustmentView(ShopScopedMixin, APIView):
    def post(self, request, shop_id):
        return _execute(request, self.membership(), ops.ADJUSTMENT)


class PurchaseReceiptView(ShopScopedMixin, APIView):
    def post(self, request, shop_id):
        return _execute(request, self.membership(), ops.RECEIPT)


class SaleView(ShopScopedMixin, APIView):
    def post(self, request, shop_id):
        return _execute(request, self.membership(), ops.SALE)


class StockReversalView(ShopScopedMixin, APIView):
    """Compensate a movement with an equal and opposite one. Body: {idempotency_key, reason}."""

    def post(self, request, shop_id, movement_id):
        return _execute(request, self.membership(), ops.REVERSAL, target_id=movement_id)


# ------------------------------------------------------------------ custom products
class CustomProductListCreateView(ShopScopedMixin, ListAPIView):
    """GET: this shop's own products (?q=). POST: create one (owner/manager) - optionally
    tracking it straight away. Shared-catalogue products are listed at /catalog/products/."""

    serializer_class = CustomProductSerializer

    def get_queryset(self):
        if self._fake:
            return Product.objects.none()
        shop = self.membership().shop
        qs = Product.objects.filter(owner_shop=shop, is_active=True).prefetch_related("units")
        q = self.request.query_params.get("q", "").strip()
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(brand__icontains=q) | Q(barcode=q))
        return qs.order_by("name")

    def post(self, request, shop_id):
        return _execute(request, self.membership(), ops.CUSTOM_PRODUCT)


class CustomProductUnitView(ShopScopedMixin, APIView):
    """Add a unit (e.g. "carton of 24" = 24 piece) to one of this shop's custom products."""

    def post(self, request, shop_id, product_id):
        return _execute(request, self.membership(), ops.CUSTOM_UNIT, target_id=product_id)


# ------------------------------------------------------------------ stock counts
def _counts_for(shop):
    return StockCount.objects.filter(shop=shop).prefetch_related(
        "items__shop_product__product"
    )


class StockCountListCreateView(ShopScopedMixin, ListAPIView):
    """GET: history, newest first (?status=). POST: start a count (idempotency_key, optional
    shop_product_ids, note)."""

    serializer_class = s.StockCountOut

    def get_queryset(self):
        if self._fake:
            return StockCount.objects.none()
        qs = _counts_for(self.membership().shop)
        wanted = self.request.query_params.get("status")
        if wanted in StockCount.Status.values:
            qs = qs.filter(status=wanted)
        return qs.order_by("-started_at", "-id")

    def post(self, request, shop_id):
        return _execute(request, self.membership(), ops.COUNT_START)


class StockCountDetailView(ShopScopedMixin, RetrieveAPIView):
    serializer_class = s.StockCountOut
    lookup_url_kwarg = "count_id"

    def get_queryset(self):
        if self._fake:
            return StockCount.objects.none()
        return _counts_for(self.membership().shop)


class StockCountItemsView(ShopScopedMixin, APIView):
    """PUT counted quantities: {idempotency_key, items: [{shop_product_id, product_unit_id, quantity}]}."""

    def put(self, request, shop_id, count_id):
        return _execute(request, self.membership(), ops.COUNT_RECORD, target_id=count_id)


class StockCountSubmitView(ShopScopedMixin, APIView):
    def post(self, request, shop_id, count_id):
        return _execute(request, self.membership(), ops.COUNT_SUBMIT, target_id=count_id)


class StockCountApproveView(ShopScopedMixin, APIView):
    """Owner/manager. Applies every non-zero variance as an adjustment, all or nothing."""

    def post(self, request, shop_id, count_id):
        return _execute(request, self.membership(), ops.COUNT_APPROVE, target_id=count_id)


class StockCountCancelView(ShopScopedMixin, APIView):
    """Owner/manager. Reject or abandon an open count; stock is unchanged. Body: {idempotency_key, reason}."""

    def post(self, request, shop_id, count_id):
        return _execute(request, self.membership(), ops.COUNT_CANCEL, target_id=count_id)


# ------------------------------------------------------------------ reads
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


class AlertListView(ShopScopedMixin, ListAPIView):
    """Low-stock alerts, largest shortfall first. (Expiry alerts arrive with batch tracking.)"""

    serializer_class = s.LowStockAlertSerializer

    def get_queryset(self):
        if self._fake:
            return ShopProduct.objects.none()
        return reports.low_stock_queryset(self.membership().shop)


class SummaryQuerySerializer(drf_serializers.Serializer):
    date_from = drf_serializers.DateField(required=False)
    date_to = drf_serializers.DateField(required=False)

    def validate(self, attrs):
        start, end = attrs.get("date_from"), attrs.get("date_to")
        if start and end:
            if start > end:
                raise drf_serializers.ValidationError("`from` must not be after `to`.")
            if (end - start).days + 1 > reports.MAX_SPAN_DAYS:
                raise drf_serializers.ValidationError(
                    f"The period cannot exceed {reports.MAX_SPAN_DAYS} days."
                )
        return attrs


class SummaryReportView(ShopScopedMixin, APIView):
    """GET ?from=YYYY-MM-DD&to=YYYY-MM-DD (inclusive, shop-local dates; default last 30 days)."""

    def get(self, request, shop_id):
        membership = self.membership()
        raw = {}
        if request.query_params.get("from"):
            raw["date_from"] = request.query_params["from"]
        if request.query_params.get("to"):
            raw["date_to"] = request.query_params["to"]
        params = SummaryQuerySerializer(data=raw)
        params.is_valid(raise_exception=True)
        return Response(
            reports.summary(
                membership.shop,
                params.validated_data.get("date_from"),
                params.validated_data.get("date_to"),
            )
        )
