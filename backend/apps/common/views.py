from django.db import connection
from django.http import JsonResponse
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


class HealthView(APIView):
    authentication_classes: list = []
    permission_classes = [AllowAny]

    def get(self, request):
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        return Response({"status": "ok"})


def server_error(request, *args, **kwargs):
    """JSON 500 using the standard envelope, with a correlation ID and no internals."""
    return JsonResponse(
        {
            "error": {
                "code": "server_error",
                "message": "An unexpected error occurred.",
                "details": None,
                "request_id": getattr(request, "request_id", None),
            }
        },
        status=500,
    )
