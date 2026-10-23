from django.db.models import Q
from drf_spectacular.utils import extend_schema
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
from .models import GroupOrder


def _groups(shop):
    return (
        services.visible_groups(shop)
        .select_related("wholesaler", "offer")
        .prefetch_related("participants")
    )


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


class ShopScoped:
    def membership(self, roles=None):
        return get_membership(self.request.user, self.kwargs["shop_id"], roles=roles)

    @property
    def _fake(self) -> bool:
        return getattr(self, "swagger_fake_view", False)

    def settle(self, group_id):
        """Lazily close/fail this group if its deadline has passed. Runs and commits BEFORE the
        action, so an action that is then refused ('deadline passed') cannot undo it."""
        services.settle_expired(Q(pk=group_id))

    def output(self, group_id, shop):
        group = _groups(shop).filter(pk=group_id).first()
        if group is None:
            raise NotFound("Group not found.")
        return s.GroupOrderSerializer(group, context={"shop": shop}).data


class GroupListCreateView(ShopScoped, ListAPIView):
    """GET: groups this shop can join (open, before the deadline). ?mine=true lists the groups
    the shop has taken part in, any status. ?product=<id> filters by product.
    POST (owner/manager): start a group on a wholesaler offer. Needs an idempotency_key."""

    serializer_class = s.GroupOrderSerializer

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        if not self._fake:
            ctx["shop"] = self.membership().shop
        return ctx

    def get_queryset(self):
        if self._fake:
            return GroupOrder.objects.none()
        shop = self.membership().shop
        services.settle_for_shop(shop)
        qs = _groups(shop)
        if self.request.query_params.get("mine") == "true":
            qs = qs.filter(participants__shop=shop)
        else:
            qs = qs.filter(status=GroupOrder.Status.OPEN)
        product = self.request.query_params.get("product")
        if product:
            qs = qs.filter(product_id=product)
        return qs

    @extend_schema(request=s.CreateGroupIn, responses={201: s.GroupOrderSerializer})
    def post(self, request, shop_id):
        membership = self.membership(roles=MANAGEMENT_ROLES)
        data = s.CreateGroupIn(data=request.data)
        data.is_valid(raise_exception=True)
        payload = dict(data.validated_data)

        def handler():
            body = {k: v for k, v in payload.items() if k != "idempotency_key"}
            group = services.create_group(shop=membership.shop, user=request.user, **body)
            return status.HTTP_201_CREATED, self.output(group.pk, membership.shop)

        return _idempotent(request, membership, "group_create", payload, handler)


class GroupDetailView(ShopScoped, APIView):
    @extend_schema(responses=s.GroupOrderSerializer)
    def get(self, request, shop_id, group_id):
        shop = self.membership().shop
        self.settle(group_id)
        return Response(self.output(group_id, shop))


class GroupJoinView(ShopScoped, APIView):
    """Owner/manager. Commit a quantity (in the offer's unit). Not binding yet.
    Body: {idempotency_key, quantity}."""

    @extend_schema(request=s.CommitmentIn, responses=s.GroupOrderSerializer)
    def post(self, request, shop_id, group_id):
        membership = self.membership(roles=MANAGEMENT_ROLES)
        data = s.CommitmentIn(data=request.data)
        data.is_valid(raise_exception=True)
        payload = dict(data.validated_data)
        self.settle(group_id)

        def handler():
            services.join_group(
                shop=membership.shop, user=request.user, group_id=group_id,
                quantity=payload["quantity"],
            )  # fmt: skip
            return status.HTTP_200_OK, self.output(group_id, membership.shop)

        return _idempotent(request, membership, f"group_join:{group_id}", payload, handler)


class GroupMyCommitmentView(ShopScoped, APIView):
    """Owner/manager. Change this shop's quantity while the group is open.
    Body: {idempotency_key, quantity}."""

    @extend_schema(request=s.CommitmentIn, responses=s.GroupOrderSerializer)
    def patch(self, request, shop_id, group_id):
        membership = self.membership(roles=MANAGEMENT_ROLES)
        data = s.CommitmentIn(data=request.data)
        data.is_valid(raise_exception=True)
        payload = dict(data.validated_data)
        self.settle(group_id)

        def handler():
            services.change_commitment(
                shop=membership.shop, user=request.user, group_id=group_id,
                quantity=payload["quantity"],
            )  # fmt: skip
            return status.HTTP_200_OK, self.output(group_id, membership.shop)

        return _idempotent(request, membership, f"group_change:{group_id}", payload, handler)


class GroupWithdrawView(ShopScoped, APIView):
    """Owner/manager. Leave the group; allowed only while it is open. Body: {idempotency_key}."""

    @extend_schema(request=s.WithdrawIn, responses=s.GroupOrderSerializer)
    def post(self, request, shop_id, group_id):
        membership = self.membership(roles=MANAGEMENT_ROLES)
        data = s.WithdrawIn(data=request.data)
        data.is_valid(raise_exception=True)
        payload = dict(data.validated_data)
        self.settle(group_id)

        def handler():
            services.withdraw(shop=membership.shop, user=request.user, group_id=group_id)
            return status.HTTP_200_OK, self.output(group_id, membership.shop)

        return _idempotent(request, membership, f"group_withdraw:{group_id}", payload, handler)


class GroupCancelView(ShopScoped, APIView):
    """Organising shop's owner/manager, while the group is open. Body: {reason}."""

    @extend_schema(request=s.ReasonIn, responses=s.GroupOrderSerializer)
    def post(self, request, shop_id, group_id):
        membership = self.membership(roles=MANAGEMENT_ROLES)
        data = s.ReasonIn(data=request.data)
        data.is_valid(raise_exception=True)
        self.settle(group_id)
        services.cancel_group(
            shop=membership.shop, user=request.user, group_id=group_id,
            reason=data.validated_data["reason"],
        )  # fmt: skip
        return Response(self.output(group_id, membership.shop))


class GroupCostBreakdownView(ShopScoped, APIView):
    """Any member of a shop that can see the group. Once the wholesaler has confirmed it: the
    group's totals and this shop's own line and delivery share. Never other shops' lines."""

    @extend_schema(responses=s.ShopCostBreakdownOut)
    def get(self, request, shop_id, group_id):
        shop = self.membership().shop
        self.settle(group_id)
        group = _groups(shop).filter(pk=group_id).first()
        if group is None:
            raise NotFound("Group not found.")
        return Response(services.cost_breakdown(group, shop=shop))


class GroupCloseView(ShopScoped, APIView):
    """Organising shop's owner/manager. Close an open group early, once the target is met.
    Freezes the quantities (no more joining, changing or withdrawing) and sends it to the
    wholesaler. No body."""

    @extend_schema(request=None, responses=s.GroupOrderSerializer)
    def post(self, request, shop_id, group_id):
        membership = self.membership(roles=MANAGEMENT_ROLES)
        self.settle(group_id)
        services.close_group(shop=membership.shop, user=request.user, group_id=group_id)
        return Response(self.output(group_id, membership.shop))


# ------------------------------------------------------------------ wholesaler side
def _wholesaler_groups(wholesaler):
    return (
        GroupOrder.objects.filter(wholesaler=wholesaler)
        .select_related("wholesaler", "offer")
        .prefetch_related("participants")
    )


class WholesalerScoped:
    def membership(self, roles=None):
        return get_wholesaler_membership(
            self.request.user, self.kwargs["wholesaler_id"], roles=roles
        )

    @property
    def _fake(self) -> bool:
        return getattr(self, "swagger_fake_view", False)

    def output(self, group_id, wholesaler):
        group = _wholesaler_groups(wholesaler).filter(pk=group_id).first()
        if group is None:
            raise NotFound("Group not found.")
        return s.GroupOrderSerializer(group, context={}).data


class WholesalerGroupListView(WholesalerScoped, ListAPIView):
    """This wholesaler's group orders, soonest deadline first (?status= to filter). Shows
    totals only, never which shops took part."""

    serializer_class = s.GroupOrderSerializer

    def get_queryset(self):
        if self._fake:
            return GroupOrder.objects.none()
        wholesaler = self.membership().wholesaler
        services.settle_for_wholesaler(wholesaler)
        qs = _wholesaler_groups(wholesaler)
        wanted = self.request.query_params.get("status")
        if wanted in GroupOrder.Status.values:
            qs = qs.filter(status=wanted)
        return qs


class WholesalerGroupDetailView(WholesalerScoped, APIView):
    @extend_schema(responses=s.GroupOrderSerializer)
    def get(self, request, wholesaler_id, group_id):
        wholesaler = self.membership().wholesaler
        services.settle_expired(Q(pk=group_id, wholesaler=wholesaler))
        return Response(self.output(group_id, wholesaler))


class WholesalerGroupCostBreakdownView(WholesalerScoped, APIView):
    """Any member of the wholesaler. Group totals plus one row per generated order."""

    @extend_schema(responses=s.WholesalerCostBreakdownOut)
    def get(self, request, wholesaler_id, group_id):
        wholesaler = self.membership().wholesaler
        group = _wholesaler_groups(wholesaler).filter(pk=group_id).first()
        if group is None:
            raise NotFound("Group not found.")
        return Response(services.cost_breakdown(group))


class _SupplierGroupAction(WholesalerScoped, APIView):
    """Owner/manager only. Subclasses implement run(); the group is returned afterwards."""

    input_cls = None

    def post(self, request, wholesaler_id, group_id):
        membership = self.membership(roles=SUPPLIER_MANAGEMENT)
        data = (self.input_cls or serializers.Serializer)(data=request.data)
        data.is_valid(raise_exception=True)
        wholesaler = membership.wholesaler
        services.settle_expired(Q(pk=group_id, wholesaler=wholesaler))
        self.run(wholesaler, request.user, group_id, data.validated_data)
        return Response(self.output(group_id, wholesaler))


@extend_schema(request=s.ConfirmGroupIn, responses=s.GroupOrderSerializer)
class WholesalerGroupConfirmView(_SupplierGroupAction):
    """THE binding point: accept the full committed quantity. Optional `unit_price` (never above
    the tier price for the committed total) and `delivery_fee` (never above the published
    estimate). The terms are frozen from here."""

    input_cls = s.ConfirmGroupIn

    def run(self, wholesaler, user, group_id, data):
        services.confirm_group(
            wholesaler=wholesaler, actor=user, group_id=group_id,
            unit_price=data["unit_price"], delivery_fee=data["delivery_fee"],
        )  # fmt: skip


@extend_schema(request=s.ReasonIn, responses=s.GroupOrderSerializer)
class WholesalerGroupDeclineView(_SupplierGroupAction):
    """Turn a closed group down. Final; binds nobody. Body: {reason}."""

    input_cls = s.ReasonIn

    def run(self, wholesaler, user, group_id, data):
        services.decline_group(
            wholesaler=wholesaler, actor=user, group_id=group_id, reason=data["reason"]
        )
