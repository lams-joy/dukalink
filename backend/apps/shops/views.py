from django.db.models import OuterRef, Subquery
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services
from .access import MANAGEMENT_ROLES, get_membership
from .models import Shop, ShopMembership
from .serializers import AddMemberSerializer, MembershipSerializer, ShopSerializer


class ShopListCreateView(APIView):
    def get(self, request):
        role = ShopMembership.objects.filter(shop=OuterRef("pk"), user=request.user).values("role")
        shops = (
            Shop.objects.filter(
                memberships__user=request.user, memberships__status=ShopMembership.Status.ACTIVE
            )
            .annotate(my_role=Subquery(role[:1]))
            .order_by("name")
        )
        return Response(ShopSerializer(shops, many=True).data)

    def post(self, request):
        serializer = ShopSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        shop = services.create_shop(request.user, **serializer.validated_data)
        shop.my_role = ShopMembership.Role.OWNER.value
        return Response(ShopSerializer(shop).data, status=status.HTTP_201_CREATED)


class ShopDetailView(APIView):
    def get(self, request, shop_id):
        membership = get_membership(request.user, shop_id)
        membership.shop.my_role = membership.role
        return Response(ShopSerializer(membership.shop).data)

    def patch(self, request, shop_id):
        membership = get_membership(request.user, shop_id, roles=MANAGEMENT_ROLES)
        shop = membership.shop
        serializer = ShopSerializer(shop, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        services.update_shop(shop=shop, actor=request.user, values=serializer.validated_data)
        shop.my_role = membership.role
        return Response(ShopSerializer(shop).data)


class ShopMemberCreateView(APIView):
    def post(self, request, shop_id):
        membership = get_membership(
            request.user, shop_id, roles=(ShopMembership.Role.OWNER,)
        )
        serializer = AddMemberSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        new_member = services.add_member(
            shop=membership.shop, actor=request.user, **serializer.validated_data
        )
        return Response(MembershipSerializer(new_member).data, status=status.HTTP_201_CREATED)


class OnboardingCompleteView(APIView):
    """Owner/manager. Finishes shop setup; see services.complete_onboarding."""

    def post(self, request, shop_id):
        membership = get_membership(request.user, shop_id, roles=MANAGEMENT_ROLES)
        summary = services.complete_onboarding(membership.shop, actor=request.user)
        membership.shop.my_role = membership.role
        return Response({"shop": ShopSerializer(membership.shop).data, "onboarding": summary})
