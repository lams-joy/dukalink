"""Supplier business rules: profiles, verification, offers and price tiers.

Rules worth knowing:
* A wholesaler becomes visible/active in the marketplace only once a platform admin has
  verified it (when settings.SUPPLIER_VERIFICATION_REQUIRED). Until then it may prepare
  offers, but only as inactive drafts.
* A suspended wholesaler's offers vanish from the marketplace at once, without being edited.
* Offers are for SHARED catalogue products in a PURCHASE unit (never a shop's custom product).
* Quantities and tier thresholds are in the offer's unit; prices are per offer unit.
* Orders will snapshot the agreed terms, so editing an offer never rewrites history.
"""

from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from apps.accounts.phone import normalise_phone
from apps.audit import services as audit
from apps.catalog.models import Product, ProductUnit
from apps.common.exceptions import DomainError, InvalidUnit, StateConflict

from .models import SupplierOffer, SupplierPriceTier, Wholesaler, WholesalerMembership

Verification = Wholesaler.Verification


class SupplierNotVerified(DomainError):
    status_code = 409
    default_code = "supplier_not_verified"
    default_detail = "This wholesaler must be verified before offers can go live."


# ------------------------------------------------------------------ visibility
def marketplace_wholesalers():
    """Wholesalers whose offers shops may see and order from."""
    if settings.SUPPLIER_VERIFICATION_REQUIRED:
        return Wholesaler.objects.filter(verification_status=Verification.VERIFIED)
    return Wholesaler.objects.exclude(verification_status=Verification.SUSPENDED)


def marketplace_offers():
    """Offers a shop can see: live, from a visible wholesaler, for an active shared product."""
    return SupplierOffer.objects.filter(
        is_active=True,
        wholesaler__in=marketplace_wholesalers(),
        product__is_active=True,
        product__owner_shop__isnull=True,
        product_unit__is_active=True,
    )


# ------------------------------------------------------------------ profiles
@transaction.atomic
def register_wholesaler(user, *, contact_phone, **fields) -> Wholesaler:
    wholesaler = Wholesaler.objects.create(contact_phone=_phone(contact_phone), **fields)
    WholesalerMembership.objects.create(
        wholesaler=wholesaler, user=user, role=WholesalerMembership.Role.OWNER
    )
    audit.record(
        action="supplier.registered", obj_type="wholesaler", obj_id=wholesaler.pk, actor=user,
        wholesaler=wholesaler, changes={"after": {"business_name": wholesaler.business_name}},
    )  # fmt: skip
    return wholesaler


def _phone(raw) -> str:
    try:
        return normalise_phone(raw)
    except DjangoValidationError:
        raise DomainError("Enter a valid phone number.", code="invalid_phone") from None


@transaction.atomic
def update_wholesaler(*, wholesaler: Wholesaler, actor, values: dict) -> Wholesaler:
    """Profile edits. Verification fields are never changeable here."""
    values = dict(values)
    if "contact_phone" in values:
        values["contact_phone"] = _phone(values["contact_phone"])
    changes = audit.diff(wholesaler, values)
    if not changes["after"]:
        return wholesaler
    for field, value in values.items():
        setattr(wholesaler, field, value)
    wholesaler.save(update_fields=[*changes["after"].keys(), "updated_at"])
    audit.record(
        action="supplier.updated", obj_type="wholesaler", obj_id=wholesaler.pk, actor=actor,
        wholesaler=wholesaler, changes=changes,
    )  # fmt: skip
    return wholesaler


@transaction.atomic
def add_member(*, wholesaler: Wholesaler, phone_number, role, actor=None) -> WholesalerMembership:
    if role == WholesalerMembership.Role.OWNER:
        raise DomainError("Owners cannot be added through this endpoint.", code="invalid_role")
    User = get_user_model()
    try:
        user = User.objects.get(phone_number=normalise_phone(phone_number))
    except (User.DoesNotExist, DjangoValidationError):
        raise DomainError(
            "No account exists for that phone number.", code="user_not_found"
        ) from None

    membership, created = WholesalerMembership.objects.get_or_create(
        wholesaler=wholesaler, user=user, defaults={"role": role}
    )
    if not created:
        if membership.status == WholesalerMembership.Status.ACTIVE:
            raise StateConflict("That person is already a member of this wholesaler.")
        if membership.role == WholesalerMembership.Role.OWNER:
            raise StateConflict("That person is the owner.")
        membership.status = WholesalerMembership.Status.ACTIVE
        membership.role = role
        membership.save(update_fields=["status", "role"])
    audit.record(
        action="supplier.member_added", obj_type="wholesaler_membership", obj_id=membership.pk,
        actor=actor, wholesaler=wholesaler,
        changes={"after": {"user_id": membership.user_id, "role": membership.role}},
    )  # fmt: skip
    return membership


# ------------------------------------------------------------------ verification (platform admin)
@transaction.atomic
def verify_wholesaler(*, wholesaler_id, actor, note="") -> Wholesaler:
    wholesaler = _lock(wholesaler_id)
    if wholesaler.verification_status == Verification.VERIFIED:
        raise StateConflict("This wholesaler is already verified.")
    return _set_status(wholesaler, Verification.VERIFIED, actor, note, "supplier.verified")


@transaction.atomic
def suspend_wholesaler(*, wholesaler_id, actor, note) -> Wholesaler:
    if not (note or "").strip():
        raise DomainError("A reason is required to suspend a wholesaler.", code="reason_required")
    wholesaler = _lock(wholesaler_id)
    if wholesaler.verification_status == Verification.SUSPENDED:
        raise StateConflict("This wholesaler is already suspended.")
    return _set_status(wholesaler, Verification.SUSPENDED, actor, note, "supplier.suspended")


def _lock(wholesaler_id) -> Wholesaler:
    try:
        return Wholesaler.objects.select_for_update().get(pk=wholesaler_id)
    except Wholesaler.DoesNotExist:
        raise DomainError("Wholesaler not found.", code="wholesaler_not_found") from None


def _set_status(wholesaler, status, actor, note, action) -> Wholesaler:
    before = wholesaler.verification_status
    wholesaler.verification_status = status
    wholesaler.verification_note = (note or "").strip()[:255]
    wholesaler.verified_at = timezone.now() if status == Verification.VERIFIED else None
    wholesaler.save(
        update_fields=["verification_status", "verification_note", "verified_at", "updated_at"]
    )
    audit.record(
        action=action, obj_type="wholesaler", obj_id=wholesaler.pk, actor=actor,
        wholesaler=wholesaler,
        changes={
            "before": {"verification_status": before},
            "after": {"verification_status": status},
            "note": wholesaler.verification_note,
        },
    )  # fmt: skip
    return wholesaler


# ------------------------------------------------------------------ offers
def _require_can_publish(wholesaler: Wholesaler) -> None:
    if wholesaler.verification_status == Verification.SUSPENDED:
        raise SupplierNotVerified("This wholesaler is suspended.")
    if settings.SUPPLIER_VERIFICATION_REQUIRED and not wholesaler.is_verified:
        raise SupplierNotVerified()


def _resolve_product_and_unit(product_id, unit_id):
    try:
        product = Product.objects.get(pk=product_id, is_active=True, owner_shop__isnull=True)
    except Product.DoesNotExist:
        raise DomainError(
            "Product not found in the shared catalogue.", code="product_not_found"
        ) from None
    try:
        unit = ProductUnit.objects.get(pk=unit_id, product=product, is_active=True)
    except ProductUnit.DoesNotExist:
        raise InvalidUnit("That unit does not belong to this product.") from None
    if not unit.is_purchase_unit:
        raise InvalidUnit("That unit cannot be used for purchases.")
    return product, unit


def _validate_tiers(tiers, *, price: Decimal, moq: Decimal) -> list[dict]:
    seen = set()
    for tier in tiers:
        qty, unit_price = tier["minimum_quantity"], tier["unit_price"]
        if qty <= moq:
            raise DomainError(
                "A price tier must start above the minimum order quantity.", code="invalid_tier"
            )
        if unit_price >= price:
            raise DomainError(
                "A price tier must be cheaper than the base price.", code="invalid_tier"
            )
        if qty in seen:
            raise DomainError("Two tiers cannot start at the same quantity.", code="invalid_tier")
        seen.add(qty)
        start, end = tier.get("valid_from"), tier.get("valid_until")
        if start and end and end <= start:
            raise DomainError("A tier's end must be after its start.", code="invalid_tier")
    return list(tiers)


def _write_tiers(offer: SupplierOffer, tiers) -> None:
    offer.tiers.all().delete()
    SupplierPriceTier.objects.bulk_create(
        SupplierPriceTier(
            offer=offer, minimum_quantity=t["minimum_quantity"], unit_price=t["unit_price"],
            valid_from=t.get("valid_from"), valid_until=t.get("valid_until"),
        )
        for t in tiers
    )  # fmt: skip


def _tier_snapshot(offer) -> list[dict]:
    return [
        {"minimum_quantity": t.minimum_quantity, "unit_price": t.unit_price}
        for t in offer.tiers.order_by("minimum_quantity")
    ]


@transaction.atomic
def create_offer(
    *, wholesaler: Wholesaler, actor, product_id, product_unit_id, price_per_unit,
    minimum_order_quantity=Decimal("1"), availability=SupplierOffer.Availability.IN_STOCK,
    available_quantity=None, delivery_areas="", delivery_terms="", is_active=True, tiers=(),
) -> SupplierOffer:  # fmt: skip
    """Unverified wholesalers may only save inactive drafts."""
    if is_active:
        _require_can_publish(wholesaler)
    product, unit = _resolve_product_and_unit(product_id, product_unit_id)
    _validate_tiers(tiers, price=price_per_unit, moq=minimum_order_quantity)
    try:
        with transaction.atomic():  # savepoint: the partial unique index is the race-proof guard
            if (
                is_active
                and SupplierOffer.objects.filter(
                    wholesaler=wholesaler, product=product, product_unit=unit, is_active=True
                ).exists()
            ):
                raise StateConflict("You already have a live offer for this product and unit.")
            offer = SupplierOffer.objects.create(
                wholesaler=wholesaler, product=product, product_unit=unit,
                price_per_unit=price_per_unit, currency=settings.DEFAULT_CURRENCY,
                minimum_order_quantity=minimum_order_quantity, availability=availability,
                available_quantity=available_quantity, delivery_areas=delivery_areas,
                delivery_terms=delivery_terms, is_active=is_active,
            )  # fmt: skip
    except IntegrityError:
        raise StateConflict("You already have a live offer for this product and unit.") from None
    _write_tiers(offer, tiers)
    audit.record(
        action="offer.created", obj_type="supplier_offer", obj_id=offer.pk, actor=actor,
        wholesaler=wholesaler,
        changes={"after": {
            "product_id": product.pk, "product_unit_id": unit.pk,
            "price_per_unit": offer.price_per_unit, "minimum_order_quantity": offer.minimum_order_quantity,
            "is_active": offer.is_active, "tiers": _tier_snapshot(offer),
        }},
    )  # fmt: skip
    return offer


def get_offer(wholesaler: Wholesaler, offer_id) -> SupplierOffer:
    """Another wholesaler's offer is 'not found', never 'forbidden' (no existence leak)."""
    try:
        return SupplierOffer.objects.select_for_update().get(pk=offer_id, wholesaler=wholesaler)
    except SupplierOffer.DoesNotExist:
        raise DomainError("Offer not found.", code="offer_not_found") from None


_OFFER_FIELDS = (
    "price_per_unit", "minimum_order_quantity", "availability", "available_quantity",
    "delivery_areas", "delivery_terms", "is_active",
)  # fmt: skip


@transaction.atomic
def update_offer(*, wholesaler: Wholesaler, offer_id, actor, values: dict) -> SupplierOffer:
    """Partial update. The product and unit are fixed: list a different unit as a new offer."""
    offer = get_offer(wholesaler, offer_id)
    values = {k: v for k, v in values.items() if k in _OFFER_FIELDS}
    changes = audit.diff(offer, values)
    if not changes["after"]:
        return offer

    if values.get("is_active") is True and not offer.is_active:
        _require_can_publish(wholesaler)
        if (
            SupplierOffer.objects.filter(
                wholesaler=wholesaler,
                product=offer.product_id,
                product_unit=offer.product_unit_id,
                is_active=True,
            )
            .exclude(pk=offer.pk)
            .exists()
        ):
            raise StateConflict("You already have a live offer for this product and unit.")

    new_price = values.get("price_per_unit", offer.price_per_unit)
    new_moq = values.get("minimum_order_quantity", offer.minimum_order_quantity)
    if "price_per_unit" in values or "minimum_order_quantity" in values:
        # Existing tiers must still make sense against the new base price / minimum.
        _validate_tiers(
            [{"minimum_quantity": t.minimum_quantity, "unit_price": t.unit_price}
             for t in offer.tiers.all()],
            price=new_price, moq=new_moq,
        )  # fmt: skip

    for field, value in values.items():
        setattr(offer, field, value)
    try:
        offer.save(update_fields=[*changes["after"].keys(), "updated_at"])
    except IntegrityError:
        raise StateConflict("You already have a live offer for this product and unit.") from None
    audit.record(
        action="offer.updated", obj_type="supplier_offer", obj_id=offer.pk, actor=actor,
        wholesaler=wholesaler, changes=changes,
    )  # fmt: skip
    return offer


@transaction.atomic
def replace_tiers(*, wholesaler: Wholesaler, offer_id, actor, tiers) -> SupplierOffer:
    offer = get_offer(wholesaler, offer_id)
    _validate_tiers(tiers, price=offer.price_per_unit, moq=offer.minimum_order_quantity)
    before = _tier_snapshot(offer)
    _write_tiers(offer, tiers)
    offer.save(update_fields=["updated_at"])  # a tier change is a price change: bump the stamp
    audit.record(
        action="offer.tiers_replaced", obj_type="supplier_offer", obj_id=offer.pk, actor=actor,
        wholesaler=wholesaler, changes={"before": {"tiers": before}, "after": {"tiers": _tier_snapshot(offer)}},
    )  # fmt: skip
    return offer


# ------------------------------------------------------------------ pricing
def effective_unit_price(offer: SupplierOffer, quantity: Decimal, at=None) -> Decimal:
    """Unit price for `quantity` offer-units: the cheapest tier that applies, else the base price."""
    at = at or timezone.now()
    applicable = offer.tiers.filter(minimum_quantity__lte=quantity).filter(
        Q(valid_from__isnull=True) | Q(valid_from__lte=at),
        Q(valid_until__isnull=True) | Q(valid_until__gt=at),
    )
    best = applicable.order_by("unit_price").first()
    return best.unit_price if best else offer.price_per_unit
