import re
import uuid
from contextvars import ContextVar

_SAFE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_current_request_id: ContextVar[str] = ContextVar("request_id", default="")


def get_request_id() -> str:
    """The current request's correlation ID (empty outside a request, e.g. in tests/commands)."""
    return _current_request_id.get()


class RequestIDMiddleware:
    """Attach a correlation ID to every request/response (X-Request-ID)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        incoming = request.headers.get("X-Request-ID", "")
        request.request_id = incoming if _SAFE.match(incoming) else uuid.uuid4().hex
        token = _current_request_id.set(request.request_id)
        try:
            response = self.get_response(request)
        finally:
            _current_request_id.reset(token)
        response["X-Request-ID"] = request.request_id
        return response
