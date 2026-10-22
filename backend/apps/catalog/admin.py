from django.contrib import admin

from .models import Product, ProductUnit


class ProductUnitInline(admin.TabularInline):
    model = ProductUnit
    extra = 1


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "brand", "category", "base_unit", "is_active")
    search_fields = ("name", "brand", "barcode")
    list_filter = ("is_active", "category")
    inlines = [ProductUnitInline]

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        form.instance.ensure_base_unit()
