from django.contrib import admin

from .models import ShopProduct, StockCount, StockMovement


class ReadOnlyAdmin(admin.ModelAdmin):
    """Ledger data is never edited by hand; corrections go through services."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ShopProduct)
class ShopProductAdmin(ReadOnlyAdmin):
    list_display = ("product", "shop", "quantity_base", "reorder_level_base", "is_active")
    list_select_related = ("product", "shop")


@admin.register(StockMovement)
class StockMovementAdmin(ReadOnlyAdmin):
    list_display = ("created_at", "shop_product", "movement_type", "quantity_base_delta")
    list_filter = ("movement_type",)


@admin.register(StockCount)
class StockCountAdmin(ReadOnlyAdmin):
    list_display = ("started_at", "shop", "status", "resolved_at")
    list_filter = ("status",)
