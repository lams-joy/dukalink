from rest_framework import serializers

from .models import AuditEvent


class AuditEventSerializer(serializers.ModelSerializer):
    actor_id = serializers.UUIDField(read_only=True, allow_null=True)

    class Meta:
        model = AuditEvent
        fields = (
            "id", "action", "object_type", "object_id", "actor_id", "changes",
            "request_id", "created_at",
        )  # fmt: skip
        read_only_fields = fields
