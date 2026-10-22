from rest_framework.response import Response
from rest_framework.views import APIView

from apps.shops.access import get_membership

from .dispatch import process_operation
from .serializers import SyncBatchIn


class SyncView(APIView):
    """POST /shops/{shop_id}/sync/ - submit queued offline operations, oldest first.

    Body:     {"operations": [{"operation_id": uuid, "operation_type": str, "payload": {...}}]}
    Response: {"results": [{"operation_id", "operation_type", "status", "result", "error"}]}
    One result per operation, in the same order. See dispatch.py for the status meanings.
    """

    def post(self, request, shop_id):
        membership = get_membership(request.user, shop_id)
        batch = SyncBatchIn(data=request.data)
        batch.is_valid(raise_exception=True)
        results = [
            process_operation(user=request.user, membership=membership, operation=op)
            for op in batch.validated_data["operations"]
        ]
        return Response({"results": results})
