"""Process one offline operation and classify the outcome.

Statuses (api.md section 9):
  accepted   applied now
  duplicate  same operation_id + same payload was applied before; original result returned
  conflict   valid, but clashes with current state (e.g. insufficient stock, key reused with a
             different payload). The client must reconcile; resending unchanged will not help.
  rejected   invalid or not permitted. Nothing was applied; the operation is NOT recorded, so
             the client may fix it and resend (same or new operation_id).

Operations are independent: each commits or fails on its own, in submission order. An
unexpected server error aborts the request (HTTP 500); earlier operations stay applied and
the client simply resends the whole batch, because applied operations come back as duplicates.
"""

from rest_framework import serializers
from rest_framework.exceptions import APIException

from apps.inventory import operations as inventory_ops
from apps.sync.idempotency import to_jsonable

ACCEPTED, DUPLICATE, CONFLICT, REJECTED = "accepted", "duplicate", "conflict", "rejected"


def _error(exc: APIException) -> dict:
    if isinstance(exc, serializers.ValidationError):
        return {"code": "validation_error", "message": "The operation was invalid.",
                "details": to_jsonable(exc.detail)}  # fmt: skip
    return {"code": exc.get_codes(), "message": str(exc.detail), "details": None}


def _outcome(operation_id, operation_type, status, result=None, error=None) -> dict:
    return {
        "operation_id": str(operation_id),
        "operation_type": operation_type,
        "status": status,
        "result": result,
        "error": error,
    }


def process_operation(*, user, membership, operation: dict) -> dict:
    op_id, op_type = operation["operation_id"], operation["operation_type"]

    spec = inventory_ops.SYNCABLE.get(op_type)
    if spec is None:
        return _outcome(
            op_id, op_type, REJECTED,
            error={"code": "unknown_operation_type",
                   "message": f"Unsupported operation_type '{op_type}'.", "details": None},
        )  # fmt: skip

    try:
        inventory_ops.authorise(spec, membership)

        payload = dict(operation["payload"])
        payload["idempotency_key"] = str(op_id)

        target_id = None
        if spec.target_field:
            target_id = serializers.UUIDField().run_validation(
                payload.pop(spec.target_field, None)
            )

        serializer = spec.input_cls(data=payload)
        serializer.is_valid(raise_exception=True)

        result = inventory_ops.run_operation(
            spec,
            user=user,
            membership=membership,
            data=dict(serializer.validated_data),
            target_id=target_id,
            overrides=inventory_ops.OFFLINE_OVERRIDES.get(spec.name),
        )
    except APIException as exc:
        status = CONFLICT if exc.status_code == 409 else REJECTED
        return _outcome(op_id, op_type, status, error=_error(exc))

    return _outcome(op_id, op_type, DUPLICATE if result.replayed else ACCEPTED, result=result.body)
