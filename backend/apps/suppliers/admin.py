from django.contrib import admin

from .models import SupplierOffer, Wholesaler


@admin.register(Wholesaler)
class WholesalerAdmin(admin.ModelAdmin):
    list_display = ("business_name", "verification_status", "created_at")
    list_filter = ("verification_status",)
    search_fields = ("business_name",)
    # Verification must go through the API/services so it is audited.
    readonly_fields = ("verification_status", "verified_at", "verification_note")


@admin.register(SupplierOffer)
class SupplierOfferAdmin(admin.ModelAdmin):
    list_display = ("wholesaler", "product", "product_unit", "price_per_unit", "is_active")
    list_filter = ("is_active",)
