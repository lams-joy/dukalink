from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Count, DecimalField, ExpressionWrapper, F, Q
from rest_framework import status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.models import AuditEvent
from apps.audit.serializers import AuditEventSerializer
from apps.common.money import money

from . import serializers as s
from . import services
from .access import MANAGEMENT_ROLES, get_wholesaler_membership, require_platform_admin
from .models import SupplierOffer, Wholesaler, WholesalerMembership


class WholesalerScopedMixin:
    def membership(self, roles=None):
        return get_wholesaler_membership(
            self.request.user, self.kwargs["wholesaler_id"], roles=roles
        )

    @property
    def _fake(self) -> bool:  # drf-spectacular schema generation
        return getattr(self, "swagger_fake_view", False)


MAX_QUOTE_QUANTITY = Decimal("1000000000")


def _with_role(membership):
    membership.wholesaler.my_role = membership.role
    return membership.wholesaler


def _offers_qs():
    return SupplierOffer.objects.select_related(
        "product", "product_unit", "wholesaler"
    ).prefetch_related("tiers")


# ------------------------------------------------------------------ own wholesaler(s)
class WholesalerListCreateView(APIView):
    def get(self, request):
        memberships = (
            WholesalerMembership.objects.filter(
                user=request.user, status=WholesalerMembership.Status.ACTIVE
            )
            .select_related("wholesaler")
            .order_by("wholesaler__business_name")
        )
        return Response(
            s.WholesalerSerializer([_with_role(m) for m in memberships], many=True).data
        )

    def post(self, request):
        data = s.WholesalerSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        wholesaler = services.register_wholesaler(request.user, **data.validated_data)
        wholesaler.my_role = WholesalerMembership.Role.OWNER.value
        return Response(s.WholesalerSerializer(wholesaler).data, status=status.HTTP_201_CREATED)


class WholesalerDetailView(WholesalerScopedMixin, APIView):
    def get(self, request, wholesaler_id):
        return Response(s.WholesalerSerializer(_with_role(self.membership())).data)

    def patch(self, request, wholesaler_id):
        membership = self.membership(roles=MANAGEMENT_ROLES)
        data = s.WholesalerSerializer(membership.wholesaler, data=request.data, partial=True)
        data.is_valid(raise_exception=True)
        services.update_wholesaler(
            wholesaler=membership.wholesaler, actor=request.user, values=data.validated_data
        )
        return Response(s.WholesalerSerializer(_with_role(membership)).data)


class WholesalerMemberCreateView(WholesalerScopedMixin, APIView):
    def post(self, request, wholesaler_id):
        membership = self.membership(roles=(WholesalerMembership.Role.OWNER,))
        data = s.AddWholesalerMemberSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        new_member = services.add_member(
            wholesaler=membership.wholesaler, actor=request.user, **data.validated_data
        )
        return Response(
            s.WholesalerMembershipSerializer(new_member).data, status=status.HTTP_201_CREATED
        )


class WholesalerAuditView(WholesalerScopedMixin, ListAPIView):
    """Owner/manager. This wholesaler's audit trail, newest first (?action=)."""

    serializer_class = AuditEventSerializer

    def get_queryset(self):
        if self._fake:
            return AuditEvent.objects.none()
        qs = AuditEvent.objects.filter(
            wholesaler=self.membership(roles=MANAGEMENT_ROLES).wholesaler
        )
        if self.request.query_params.get("action"):
            qs = qs.filter(action=self.request.query_params["action"])
        return qs


# ------------------------------------------------------------------ own offers
class OfferListCreateView(WholesalerScopedMixin, ListAPIView):
    """GET: all of this wholesaler's offers, drafts included (?is_active=true|false).
    POST (owner/manager): create one. Unverified wholesalers may only save inactive drafts."""

    serializer_class = s.SupplierOfferSerializer

    def get_queryset(self):
        if self._fake:
            return SupplierOffer.objects.none()
        qs = _offers_qs().filter(wholesaler=self.membership().wholesaler)
        flag = self.request.query_params.get("is_active")
        if flag in ("true", "false"):
            qs = qs.filter(is_active=flag == "true")
        return qs.order_by("product__name", "price_per_unit")

    def post(self, request, wholesaler_id):
        membership = self.membership(roles=MANAGEMENT_ROLES)
        data = s.OfferCreateIn(data=request.data)
        data.is_valid(raise_exception=True)
        offer = services.create_offer(
            wholesaler=membership.wholesaler, actor=request.user, **data.validated_data
        )
        offer = _offers_qs().get(pk=offer.pk)
        return Response(s.SupplierOfferSerializer(offer).data, status=status.HTTP_201_CREATED)


class OfferDetailView(WholesalerScopedMixin, APIView):
    def get(self, request, wholesaler_id, offer_id):
        offer = _offers_qs().filter(wholesaler=self.membership().wholesaler, pk=offer_id).first()
        if offer is None:
            raise NotFound("Offer not found.")
        return Response(s.SupplierOfferSerializer(offer).data)

    def patch(self, request, wholesaler_id, offer_id):
        membership = self.membership(roles=MANAGEMENT_ROLES)
        data = s.OfferUpdateIn(data=request.data, partial=True)
        data.is_valid(raise_exception=True)
        services.update_offer(
            wholesaler=membership.wholesaler,
            offer_id=offer_id,
            actor=request.user,
            values=data.validated_data,
        )
        return Response(s.SupplierOfferSerializer(_offers_qs().get(pk=offer_id)).data)


class OfferTiersView(WholesalerScopedMixin, APIView):
    """PUT the complete list of price tiers (an empty list removes them all)."""

    def put(self, request, wholesaler_id, offer_id):
        membership = self.membership(roles=MANAGEMENT_ROLES)
        data = s.TiersReplaceIn(data=request.data)
        data.is_valid(raise_exception=True)
        services.replace_tiers(
            wholesaler=membership.wholesaler,
            offer_id=offer_id,
            actor=request.user,
            tiers=data.validated_data["tiers"],
        )
        return Response(s.SupplierOfferSerializer(_offers_qs().get(pk=offer_id)).data)


# ------------------------------------------------------------------ marketplace (any signed-in user)
class MarketplaceOfferListView(ListAPIView):
    """Live offers from visible wholesalers. Filters: ?product_id= ?q= ?wholesaler_id=
    ?area= ?available=true. Default order is cheapest per BASE unit first, so a 50 kg sack
    and a 2 kg packet compare fairly; ?ordering=updated shows the freshest first."""

    serializer_class = s.MarketOfferSerializer

    def get_queryset(self):
        qs = (
            services.marketplace_offers()
            .select_related("product", "product_unit", "wholesaler")
            .prefetch_related("tiers")
            .annotate(
                base_price=ExpressionWrapper(
                    F("price_per_unit") / F("product_unit__base_quantity"),
                    output_field=DecimalField(max_digits=24, decimal_places=8),
                )
            )
        )
        p = self.request.query_params
        for param, lookup in (("product_id", "product_id"), ("wholesaler_id", "wholesaler_id")):
            if p.get(param):
                try:
                    qs = qs.filter(**{lookup: p[param]})
                except (ValueError, DjangoValidationError):  # malformed UUID
                    raise ValidationError({param: ["Enter a valid UUID."]}) from None
        if p.get("q", "").strip():
            q = p["q"].strip()
            qs = qs.filter(
                Q(product__name__icontains=q) | Q(product__brand__icontains=q)
                | Q(wholesaler__business_name__icontains=q)
            )  # fmt: skip
        if p.get("area", "").strip():
            qs = qs.filter(delivery_areas__icontains=p["area"].strip())
        if p.get("available") == "true":
            qs = qs.exclude(availability=SupplierOffer.Availability.OUT_OF_STOCK)
        if p.get("ordering") == "updated":
            return qs.order_by("-updated_at", "id")
        return qs.order_by("base_price", "-updated_at", "id")


class MarketplaceOfferDetailView(RetrieveAPIView):
    serializer_class = s.MarketOfferSerializer
    lookup_url_kwarg = "offer_id"

    def get_queryset(self):
        return (
            services.marketplace_offers()
            .select_related("product", "product_unit", "wholesaler")
            .prefetch_related("tiers")
        )


class MarketplaceQuoteView(APIView):
    """GET ?quantity=<offer units>: the unit price and total that quantity would get today."""

    def get(self, request, offer_id):
        offer = (
            services.marketplace_offers().filter(pk=offer_id).select_related("product_unit").first()
        )
        if offer is None:
            raise NotFound("Offer not found.")
        try:
            quantity = Decimal(request.query_params.get("quantity", ""))
        except InvalidOperation:
            raise ValidationError({"quantity": ["Enter a number."]}) from None
        if not quantity.is_finite() or quantity <= 0 or quantity > MAX_QUOTE_QUANTITY:
            raise ValidationError({"quantity": ["Enter a quantity greater than zero."]})
        unit_price = services.effective_unit_price(offer, quantity)
        quote = {
            "offer_id": offer.pk,
            "quantity": quantity,
            "meets_minimum": quantity >= offer.minimum_order_quantity,
            "minimum_order_quantity": offer.minimum_order_quantity,
            "unit_price": unit_price,
            "line_total": money(quantity * unit_price),
            "currency": offer.currency,
            "quantity_base": quantity * offer.product_unit.base_quantity,
        }
        return Response(s.QuoteSerializer(quote).data)


class MarketplaceWholesalerListView(ListAPIView):
    """Visible wholesalers only (?q=). Includes how many live offers each has."""

    serializer_class = s.PublicWholesalerSerializer

    def get_queryset(self):
        qs = services.marketplace_wholesalers().annotate(
            offer_count=Count("offers", filter=Q(offers__is_active=True), distinct=True)
        )
        q = self.request.query_params.get("q", "").strip()
        if q:
            qs = qs.filter(Q(business_name__icontains=q) | Q(location_text__icontains=q))
        return qs.order_by("business_name")


class MarketplaceWholesalerDetailView(RetrieveAPIView):
    serializer_class = s.PublicWholesalerSerializer
    lookup_url_kwarg = "wholesaler_id"

    def get_queryset(self):
        return services.marketplace_wholesalers().annotate(
            offer_count=Count("offers", filter=Q(offers__is_active=True), distinct=True)
        )


# ------------------------------------------------------------------ platform admin
class PendingSuppliersView(ListAPIView):
    """Platform admins: wholesalers awaiting verification, oldest first."""

    serializer_class = s.AdminWholesalerSerializer

    def get_queryset(self):
        require_platform_admin(self.request.user)
        return Wholesaler.objects.filter(
            verification_status=Wholesaler.Verification.PENDING
        ).order_by("created_at")


class VerifySupplierView(APIView):
    def post(self, request, wholesaler_id):
        require_platform_admin(request.user)
        data = s.VerificationActionSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        wholesaler = services.verify_wholesaler(
            wholesaler_id=wholesaler_id, actor=request.user, note=data.validated_data["note"]
        )
        return Response(s.AdminWholesalerSerializer(wholesaler).data)


class SuspendSupplierView(APIView):
    def post(self, request, wholesaler_id):
        require_platform_admin(request.user)
        data = s.VerificationActionSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        wholesaler = services.suspend_wholesaler(
            wholesaler_id=wholesaler_id, actor=request.user, note=data.validated_data["note"]
        )
        return Response(s.AdminWholesalerSerializer(wholesaler).data)
