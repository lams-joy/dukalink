"""Platform administrators maintain the shared catalogue here (shops cannot edit it)."""
from django.db import IntegrityError, transaction
from django.db.models import Q
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.generics import ListAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit import services as audit
from apps.common.exceptions import DomainError
from apps.suppliers.access import require_platform_admin

from . import serializers as s
from .models import Product, ProductUnit


def _shared():
    return Product.objects.filter(owner_shop__isnull=True).prefetch_related("units")


def _get_product(pk) -> Product:
    try:
        return _shared().get(pk=pk)
    except Product.DoesNotExist:
        raise NotFound("Product not found.") from None


def _check_not_duplicate(name: str, brand: str, *, exclude=None):
    clash = _shared().filter(is_active=True, name__iexact=name.strip(), brand__iexact=brand.strip())
    if exclude is not None:
        clash = clash.exclude(pk=exclude)
    if clash.exists():
        raise DomainError("The catalogue already has an active product with this name and brand.", code="duplicate_product")


def _is_base_unit(unit: ProductUnit) -> bool:
    return unit.unit_name == unit.product.base_unit


class AdminProductListCreateView(ListAPIView):
    """GET ?q=&include_inactive=true | POST a new shared product with its units."""

    serializer_class = s.AdminProductSerializer

    def get_queryset(self):
        require_platform_admin(self.request.user)
        qs = _shared().order_by("name", "brand")
        if self.request.query_params.get("include_inactive") != "true":
            qs = qs.filter(is_active=True)
        q = self.request.query_params.get("q", "").strip()
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(brand__icontains=q) | Q(barcode=q) | Q(category__icontains=q))
        return qs

    @extend_schema(request=s.AdminProductCreateIn, responses={201: s.AdminProductSerializer})
    @transaction.atomic
    def post(self, request):
        require_platform_admin(request.user)
        data = s.AdminProductCreateIn(data=request.data)
        data.is_valid(raise_exception=True)
        v = data.validated_data
        _check_not_duplicate(v["name"], v["brand"])
        product = Product.objects.create(
            name=v["name"].strip(), brand=v["brand"].strip(), barcode=v["barcode"].strip(),
            category=v["category"].strip(), base_unit=v["base_unit"].strip(),
        )
        product.ensure_base_unit()
        for u in v.get("units", []):
            if u["unit_name"].strip() == product.base_unit:
                continue  # the base unit already exists with factor 1
            try:
                with transaction.atomic():
                    ProductUnit.objects.create(product=product, **{**u, "unit_name": u["unit_name"].strip()})
            except IntegrityError:
                raise DomainError(f"Unit \"{u['unit_name']}\" appears twice.", code="duplicate_unit") from None
        audit.record(action="catalog.product_created", obj_type="product", obj_id=product.pk, actor=request.user,
                     changes={"after": {"name": product.name, "base_unit": product.base_unit}})
        return Response(s.AdminProductSerializer(_get_product(product.pk)).data, status=status.HTTP_201_CREATED)


class AdminProductDetailView(APIView):
    @extend_schema(responses=s.AdminProductSerializer)
    def get(self, request, product_id):
        require_platform_admin(request.user)
        return Response(s.AdminProductSerializer(_get_product(product_id)).data)

    @extend_schema(request=s.AdminProductPatchIn, responses=s.AdminProductSerializer)
    @transaction.atomic
    def patch(self, request, product_id):
        require_platform_admin(request.user)
        product = _get_product(product_id)
        data = s.AdminProductPatchIn(data=request.data)
        data.is_valid(raise_exception=True)
        v = data.validated_data
        before = {k: getattr(product, k) for k in v}
        name, brand = v.get("name", product.name), v.get("brand", product.brand)
        if v.get("is_active", product.is_active):
            _check_not_duplicate(name, brand, exclude=product.pk)
        for k, val in v.items():
            setattr(product, k, val.strip() if isinstance(val, str) else val)
        product.save()
        audit.record(action="catalog.product_updated", obj_type="product", obj_id=product.pk, actor=request.user,
                     changes={"before": before, "after": v})
        return Response(s.AdminProductSerializer(_get_product(product.pk)).data)


class AdminUnitCreateView(APIView):
    @extend_schema(request=s.AdminUnitIn, responses={201: s.AdminProductSerializer})
    @transaction.atomic
    def post(self, request, product_id):
        require_platform_admin(request.user)
        product = _get_product(product_id)
        data = s.AdminUnitIn(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                unit = ProductUnit.objects.create(product=product, **data.validated_data)
        except IntegrityError:
            raise DomainError("This product already has a unit with that name.", code="duplicate_unit") from None
        audit.record(action="catalog.unit_added", obj_type="product", obj_id=product.pk, actor=request.user,
                     changes={"after": {"unit_name": unit.unit_name, "base_quantity": str(unit.base_quantity)}})
        return Response(s.AdminProductSerializer(_get_product(product.pk)).data, status=status.HTTP_201_CREATED)


class AdminUnitDetailView(APIView):
    @extend_schema(request=s.AdminUnitPatchIn, responses=s.AdminProductSerializer)
    @transaction.atomic
    def patch(self, request, product_id, unit_id):
        require_platform_admin(request.user)
        product = _get_product(product_id)
        unit = product.units.filter(pk=unit_id).first()
        if unit is None:
            raise NotFound("Unit not found.")
        data = s.AdminUnitPatchIn(data=request.data)
        data.is_valid(raise_exception=True)
        v = data.validated_data
        if _is_base_unit(unit) and (v.get("is_active") is False or ("unit_name" in v and v["unit_name"] != unit.unit_name)):
            raise DomainError("The base unit cannot be renamed or retired.", code="base_unit_protected")
        before = {k: getattr(unit, k) for k in v}
        for k, val in v.items():
            setattr(unit, k, val.strip() if isinstance(val, str) else val)
        try:
            with transaction.atomic():
                unit.save()
        except IntegrityError:
            raise DomainError("This product already has a unit with that name.", code="duplicate_unit") from None
        audit.record(action="catalog.unit_updated", obj_type="product", obj_id=product.pk, actor=request.user,
                     changes={"before": before, "after": v})
        return Response(s.AdminProductSerializer(_get_product(product.pk)).data)
