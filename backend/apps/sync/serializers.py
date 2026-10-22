from rest_framework import serializers

MAX_OPERATIONS_PER_BATCH = 100


class SyncOperationIn(serializers.Serializer):
    operation_id = serializers.UUIDField()
    operation_type = serializers.CharField(max_length=50)
    payload = serializers.DictField()


class SyncBatchIn(serializers.Serializer):
    operations = SyncOperationIn(many=True, allow_empty=False, max_length=MAX_OPERATIONS_PER_BATCH)
