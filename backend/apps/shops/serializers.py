import zoneinfo

from rest_framework import serializers

from .models import Shop, ShopMembership


class ShopSerializer(serializers.ModelSerializer):
    my_role = serializers.CharField(read_only=True, required=False)

    class Meta:
        model = Shop
        fields = (
            "id", "name", "location_text", "latitude", "longitude", "timezone",
            "default_tracking_mode", "onboarding_completed_at", "my_role",
            "created_at", "updated_at",
        )  # fmt: skip
        read_only_fields = ("id", "onboarding_completed_at", "created_at", "updated_at")

    def validate_timezone(self, value):
        try:
            zoneinfo.ZoneInfo(value)
        except (zoneinfo.ZoneInfoNotFoundError, ValueError):
            raise serializers.ValidationError("Unknown timezone.") from None
        return value


class AddMemberSerializer(serializers.Serializer):
    phone_number = serializers.CharField(max_length=20)
    role = serializers.ChoiceField(
        choices=[ShopMembership.Role.MANAGER.value, ShopMembership.Role.STAFF.value]
    )


class MembershipSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShopMembership
        fields = ("id", "user", "role", "status", "created_at")
        read_only_fields = fields
