from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.generics import ListAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.shops.access import MANAGEMENT_ROLES, get_membership
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
        qs = _groups(shop)
        if self.request.query_params.get("mine") == "true":
            qs = qs.filter(participants__shop=shop)
        else:
            qs = qs.filter(status=GroupOrder.Status.OPEN)
        product = self.request.query_params.get("product")
        if product:
            qs = qs.filter(product_id=product)
        return qs

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
    def get(self, request, shop_id, group_id):
        return Response(self.output(group_id, self.membership().shop))


class GroupJoinView(ShopScoped, APIView):
    """Owner/manager. Commit a quantity (in the offer's unit). Not binding yet.
    Body: {idempotency_key, quantity}."""

    def post(self, request, shop_id, group_id):
        membership = self.membership(roles=MANAGEMENT_ROLES)
        data = s.CommitmentIn(data=request.data)
        data.is_valid(raise_exception=True)
        payload = dict(data.validated_data)

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

    def patch(self, request, shop_id, group_id):
        membership = self.membership(roles=MANAGEMENT_ROLES)
        data = s.CommitmentIn(data=request.data)
        data.is_valid(raise_exception=True)
        payload = dict(data.validated_data)

        def handler():
            services.change_commitment(
                shop=membership.shop, user=request.user, group_id=group_id,
                quantity=payload["quantity"],
            )  # fmt: skip
            return status.HTTP_200_OK, self.output(group_id, membership.shop)

        return _idempotent(request, membership, f"group_change:{group_id}", payload, handler)


class GroupWithdrawView(ShopScoped, APIView):
    """Owner/manager. Leave the group; allowed only while it is open. Body: {idempotency_key}."""

    def post(self, request, shop_id, group_id):
        membership = self.membership(roles=MANAGEMENT_ROLES)
        data = s.WithdrawIn(data=request.data)
        data.is_valid(raise_exception=True)
        payload = dict(data.validated_data)

        def handler():
            services.withdraw(shop=membership.shop, user=request.user, group_id=group_id)
            return status.HTTP_200_OK, self.output(group_id, membership.shop)

        return _idempotent(request, membership, f"group_withdraw:{group_id}", payload, handler)


class GroupCancelView(ShopScoped, APIView):
    """Organising shop's owner/manager, while the group is open. Body: {reason}."""

    def post(self, request, shop_id, group_id):
        membership = self.membership(roles=MANAGEMENT_ROLES)
        data = s.ReasonIn(data=request.data)
        data.is_valid(raise_exception=True)
        services.cancel_group(
            shop=membership.shop, user=request.user, group_id=group_id,
            reason=data.validated_data["reason"],
        )  # fmt: skip
        return Response(self.output(group_id, membership.shop))
