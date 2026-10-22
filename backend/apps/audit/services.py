"""Writing audit events.

Call `record()` from the service function that performs the change, inside its transaction:
the event commits or rolls back together with the change, and an idempotent replay (which
never re-runs the handler) cannot write a duplicate.

Keep payloads small and free of secrets and personal data: ids, roles, quantities, reasons.
Phone numbers, names and credentials are scrubbed even if a caller passes them by mistake.
"""

from apps.common.middleware import get_request_id
from apps.sync.idempotency import to_jsonable

from .models import AuditEvent

_FORBIDDEN_KEYS = {
    "password", "token", "access", "refresh", "secret", "authorization",
    "phone_number", "phone", "full_name", "email",
}  # fmt: skip


def _scrub(value):
    if isinstance(value, dict):
        return {k: _scrub(v) for k, v in value.items() if str(k).lower() not in _FORBIDDEN_KEYS}
    if isinstance(value, list | tuple):
        return [_scrub(v) for v in value]
    return value


def diff(instance, new_values: dict) -> dict:
    """{"before": {...}, "after": {...}} for only the fields that actually change."""
    before, after = {}, {}
    for field, value in new_values.items():
        old = getattr(instance, field)
        if old != value:
            before[field], after[field] = old, value
    return {"before": before, "after": after}


def record(*, action, obj_type, obj_id, actor=None, shop=None, changes=None) -> AuditEvent:
    return AuditEvent.objects.create(
        shop=shop,
        actor=actor if getattr(actor, "pk", None) else None,
        action=action,
        object_type=obj_type,
        object_id=str(obj_id),
        changes=_scrub(to_jsonable(changes or {})),
        request_id=get_request_id(),
    )
