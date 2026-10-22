from django.contrib import admin

from .models import AuditEvent


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    """Read-only: the audit trail must not be editable from the admin site."""

    list_display = ("created_at", "action", "object_type", "object_id", "shop", "actor")
    list_filter = ("action",)
    search_fields = ("object_id", "request_id")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
