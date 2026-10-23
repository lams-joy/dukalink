from django.contrib import admin

from .models import GroupOrder, GroupParticipant


class ParticipantInline(admin.TabularInline):
    model = GroupParticipant
    extra = 0
    readonly_fields = ("shop", "committed_by", "quantity", "quantity_base", "joined_at")
    can_delete = False


@admin.register(GroupOrder)
class GroupOrderAdmin(admin.ModelAdmin):
    list_display = ("id", "product_name_snapshot", "status", "target_quantity", "committed_quantity", "deadline")
    list_filter = ("status",)
    readonly_fields = ("terms_snapshot",)
    inlines = [ParticipantInline]
