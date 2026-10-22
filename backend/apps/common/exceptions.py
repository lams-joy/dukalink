from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.views import exception_handler as drf_exception_handler


class DomainError(APIException):
    """Base class for business-rule failures raised by service functions."""

    status_code = status.HTTP_400_BAD_REQUEST
    default_code = "domain_error"
    default_detail = "The request could not be completed."


class InvalidUnit(DomainError):
    default_code = "invalid_unit"
    default_detail = "That unit is not valid for this product."


class InvalidQuantity(DomainError):
    default_code = "invalid_quantity"
    default_detail = "That quantity is not valid."


class ProductNotTracked(DomainError):
    default_code = "product_not_tracked"
    default_detail = "That product is not tracked in this shop."


class InsufficientStock(DomainError):
    status_code = status.HTTP_409_CONFLICT
    default_code = "insufficient_stock"
    default_detail = "Not enough stock to complete this operation."


class StateConflict(DomainError):
    status_code = status.HTTP_409_CONFLICT
    default_code = "state_conflict"
    default_detail = "The request conflicts with the current state."


class IdempotencyConflict(DomainError):
    status_code = status.HTTP_409_CONFLICT
    default_code = "idempotency_conflict"
    default_detail = "This idempotency key was already used with a different payload."


def api_exception_handler(exc, context):
    """Wrap every handled error in one envelope: {"error": {...}}."""
    response = drf_exception_handler(exc, context)
    if response is None:
        return None  # unhandled -> Django logs it and handler500 renders the envelope

    request = context.get("request")
    request_id = getattr(request, "request_id", None)
    data = response.data

    if isinstance(data, dict) and "detail" in data:
        detail = data["detail"]
        code = getattr(detail, "code", None) or data.get("code") or "error"
        message, details = str(detail), None
    else:
        code, message, details = "validation_error", "The request was invalid.", data

    response.data = {
        "error": {"code": code, "message": message, "details": details, "request_id": request_id}
    }
    return response
