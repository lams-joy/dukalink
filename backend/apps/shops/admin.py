from django.contrib import admin

from .models import Shop, ShopMembership


class MembershipInline(admin.TabularInline):
    model = ShopMembership
    extra = 0


@admin.register(Shop)
class ShopAdmin(admin.ModelAdmin):
    list_display = ("name", "location_text", "created_at")
    search_fields = ("name",)
    inlines = [MembershipInline]
