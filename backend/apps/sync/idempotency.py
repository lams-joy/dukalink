"""Idempotent execution of write operations.

Same key + same payload  -> the original response is returned, nothing is re-applied.
Same key + other payload -> 409 idempotency_conflict.

The idempotency row and the domain writes share ONE transaction: if the handler raises,
everything (including the row) rolls back, so a failed attempt can be retried. Two
concurrent requests with the same key serialise on the unique index; the loser then
finds the winner's committed row and replays it.
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from apps.common.exceptions import IdempotencyConflict

from .models import SyncOperation


def _default(value):
    if isinstance(value, Decimal):
        return format(value.normalize(), "f")
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    raise TypeError(f"Cannot serialise {type(value)!r}")


def to_jsonable(obj):
    """Round-trip through JSON so the result is safe for a JSONField."""
    return json.loads(json.dumps(obj, default=_default))


def payload_hash(payload) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=_default)
    return hashlib.sha256(canonical.encode()).hexdigest()


@dataclass
class IdempotentResult:
    status: int
    body: dict
    replayed: bool


@transaction.atomic
def run_idempotent(*, user, shop, operation_type, operation_id, payload, handler) -> IdempotentResult:
    """handler() -> (status_code, json-safe body). It runs inside the transaction."""
    digest = payload_hash(payload)
    op, created = SyncOperation.objects.get_or_create(
        user=user,
        operation_id=operation_id,
        defaults={"shop": shop, "operation_type": operation_type, "payload_hash": digest},
    )
    if not created:
        if (
            op.payload_hash != digest
            or op.operation_type != operation_type
            or op.shop_id != shop.pk
        ):
            raise IdempotencyConflict()
        return IdempotentResult(op.response_status, op.response_body, replayed=True)

    status, body = handler()
    op.response_status = status
    op.response_body = to_jsonable(body)
    op.processed_at = timezone.now()
    op.save(update_fields=["response_status", "response_body", "processed_at"])
    return IdempotentResult(status, op.response_body, replayed=False)
