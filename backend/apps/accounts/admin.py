from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.forms import BaseUserCreationForm, UserChangeForm

from .models import User


class UserCreationForm(BaseUserCreationForm):
    class Meta:
        model = User
        fields = ("phone_number", "full_name")


class UserChangeForm_(UserChangeForm):
    class Meta:
        model = User
        fields = "__all__"


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    form = UserChangeForm_
    add_form = UserCreationForm
    ordering = ("-created_at",)
    list_display = ("phone_number", "full_name", "is_active", "is_staff")
    search_fields = ("phone_number", "full_name")
    readonly_fields = ("last_login", "created_at")
    fieldsets = (
        (None, {"fields": ("phone_number", "password")}),
        ("Profile", {"fields": ("full_name",)}),
        (
            "Permissions",
            {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")},
        ),
        ("Dates", {"fields": ("last_login", "created_at")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("phone_number", "full_name", "password1", "password2"),
            },
        ),
    )
