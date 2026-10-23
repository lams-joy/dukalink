from rest_framework import serializers, status
from rest_framework.exceptions import NotFound
from rest_framework.generics import ListAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.shops.access import MANAGEMENT_ROLES, get_membership
from apps.suppliers.access import MANAGEMENT_ROLES as SUPPLIER_MANAGEMENT
from apps.suppliers.access import get_wholesaler_membership
from apps.sync.idempotency import run_idempotent, to_jsonable

from . import serializers as s
from . import services
from .models import Order


def _orders():
    return Order.objects.select_related("shop", "wholesaler").prefetch_related("items")


def _one(qs, order_id) -> Order:
    order = qs.filter(pk=order_id).first()
    if order is None:
        raise NotFound("Order not found.")
    return order


def _idempotent(request, membership, operation_type, data, handler):
    """Run once per idempotency key; a replay returns the stored result and flags it."""
    data = dict(data)
    key = data.pop("idempotency_key")
    result = run_idempotent(
        user=request.user, shop=membership.shop, operation_type=operation_type,
        operation_id=key, payload=to_jsonable(data), handler=handler,
    )  # fmt: skip
    response = Response(result.body, status=result.status)
    if result.replayed:
        response["Idempotent-Replayed"] = "true"
    return response


def _status_filter(qs, request):
    wanted = request.query_params.get("status")
    if wanted in Order.Status.values:
        qs = qs.filter(status=wanted)
    elif request.query_params.get("open") == "true":
        qs = qs.filter(status__in=Order.OPEN_STATUSES)
    return qs


# ------------------------------------------------------------------ shop side
class ShopScoped:
    def membership(self, roles=None):
        return get_membership(self.request.user, self.kwargs["shop_id"], roles=roles)

    @property
    def _fake(self) -> bool:
        return getattr(self, "swagger_fake_view", False)


class ShopOrderListCreateView(ShopScoped, ListAPIView):
    """GET: this shop's orders, newest first (?status= or ?open=true).
    POST (owner/manager): place an order with one wholesaler. Needs an idempotency_key."""

    serializer_class = s.OrderSerializer

    def get_queryset(self):
        if self._fake:
            return Order.objects.none()
        qs = _orders().filter(shop=self.membership().shop)
        return _status_filter(qs, self.request)

    def post(self, request, shop_id):
        membership = self.membership(roles=MANAGEMENT_ROLES)
        data = s.PlaceOrderIn(data=request.data)
        data.is_valid(raise_exception=True)
        payload = dict(data.validated_data)

        def handler():
            body = {k: v for k, v in payload.items() if k != "idempotency_key"}
            order = services.place_order(shop=membership.shop, user=request.user, **body)
            return status.HTTP_201_CREATED, s.OrderSerializer(_orders().get(pk=order.pk)).data

        return _idempotent(request, membership, "order_place", payload, handler)


class ShopOrderDetailView(ShopScoped, APIView):
    def get(self, request, shop_id, order_id):
        qs = _orders().filter(shop=self.membership().shop)
        return Response(s.OrderSerializer(_one(qs, order_id)).data)


class ShopOrderCancelView(ShopScoped, APIView):
    """Owner/manager. Allowed until the supplier dispatches. Body: {reason}."""

    def post(self, request, shop_id, order_id):
        membership = self.membership(roles=MANAGEMENT_ROLES)
        data = s.ReasonIn(data=request.data)
        data.is_valid(raise_exception=True)
        services.cancel_by_shop(
            shop=membership.shop,
            actor=request.user,
            order_id=order_id,
            reason=data.validated_data["reason"],
        )
        return Response(s.OrderSerializer(_orders().get(pk=order_id)).data)


class ShopOrderReceiveView(ShopScoped, APIView):
    """Any shop member. Record what actually arrived for EVERY line (0 = nothing).
    Body: {idempotency_key, items: [{item_id, received_quantity}], note?}. Adds the received
    goods to the shop's stock."""

    def post(self, request, shop_id, order_id):
        membership = self.membership()
        data = s.ReceiveOrderIn(data=request.data)
        data.is_valid(raise_exception=True)
        payload = dict(data.validated_data)

        def handler():
            services.receive_order(
                shop=membership.shop, actor=request.user, order_id=order_id,
                entries=payload["items"], note=payload["note"],
            )  # fmt: skip
            return status.HTTP_200_OK, s.OrderSerializer(_orders().get(pk=order_id)).data

        return _idempotent(request, membership, f"order_receive:{order_id}", payload, handler)


# ------------------------------------------------------------------ wholesaler side
class WholesalerScoped:
    def membership(self, roles=None):
        return get_wholesaler_membership(
            self.request.user, self.kwargs["wholesaler_id"], roles=roles
        )

    @property
    def _fake(self) -> bool:
        return getattr(self, "swagger_fake_view", False)


class WholesalerOrderListView(WholesalerScoped, ListAPIView):
    """This wholesaler's incoming orders, newest first (?status= or ?open=true)."""

    serializer_class = s.OrderSerializer

    def get_queryset(self):
        if self._fake:
            return Order.objects.none()
        qs = _orders().filter(wholesaler=self.membership().wholesaler)
        return _status_filter(qs, self.request)


class WholesalerOrderDetailView(WholesalerScoped, APIView):
    def get(self, request, wholesaler_id, order_id):
        qs = _orders().filter(wholesaler=self.membership().wholesaler)
        return Response(s.OrderSerializer(_one(qs, order_id)).data)


class _SupplierAction(WholesalerScoped, APIView):
    """Owner/manager only. Subclasses implement run(); the order is returned afterwards."""

    input_cls = None

    def post(self, request, wholesaler_id, order_id):
        membership = self.membership(roles=SUPPLIER_MANAGEMENT)
        data = (self.input_cls or serializers.Serializer)(data=request.data)
        data.is_valid(raise_exception=True)
        self.run(membership.wholesaler, request.user, order_id, data.validated_data)
        return Response(s.OrderSerializer(_orders().get(pk=order_id)).data)


class WholesalerOrderConfirmView(_SupplierAction):
    """Accept the order as placed; optionally add a delivery fee. Terms are frozen from here."""

    input_cls = s.ConfirmOrderIn

    def run(self, wholesaler, user, order_id, data):
        services.confirm_order(
            wholesaler=wholesaler, actor=user, order_id=order_id, delivery_fee=data["delivery_fee"]
        )


class WholesalerOrderRejectView(_SupplierAction):
    input_cls = s.ReasonIn

    def run(self, wholesaler, user, order_id, data):
        services.reject_order(
            wholesaler=wholesaler, actor=user, order_id=order_id, reason=data["reason"]
        )


class WholesalerOrderDispatchView(_SupplierAction):
    def run(self, wholesaler, user, order_id, data):
        services.dispatch_order(wholesaler=wholesaler, actor=user, order_id=order_id)


class WholesalerOrderCancelView(_SupplierAction):
    input_cls = s.ReasonIn

    def run(self, wholesaler, user, order_id, data):
        services.cancel_by_wholesaler(
            wholesaler=wholesaler, actor=user, order_id=order_id, reason=data["reason"]
        )
