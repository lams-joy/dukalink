"""Write operations shared by the REST endpoints and the offline sync endpoint.

Each OperationSpec describes one idempotent stock write: how to validate it, which roles
may do it, what it calls in `services`, and how its result is serialised. Because REST and
sync both go through `run_operation`, an operation sent over REST and re-sent through sync
(same key, same payload) is recognised as a duplicate.
"""

from collections.abc import Callable
from dataclasses import dataclass

from rest_framework import serializers, status
from rest_framework.exceptions import PermissionDenied

from apps.shops.access import MANAGEMENT_ROLES
from apps.sync.idempotency import IdempotentResult, run_idempotent, to_jsonable

from . import counts, services
from . import serializers as s
from .models import Sale


@dataclass(frozen=True)
class OperationSpec:
    name: str  # also the stored operation_type
    input_cls: type[serializers.Serializer]
    output_cls: type[serializers.Serializer]
    build: Callable  # (membership, user, data, target_id) -> model instance
    management_only: bool = False
    target_field: str | None = None  # id taken from the URL (REST) or the payload (sync)


def authorise(spec: OperationSpec, membership) -> None:
    if spec.management_only and membership.role not in MANAGEMENT_ROLES:
        raise PermissionDenied("You do not have permission to do this in this shop.")


def run_operation(
    spec: OperationSpec, *, user, membership, data: dict, target_id=None, overrides=None
) -> IdempotentResult:
    """`data` is validated input including idempotency_key. `overrides` change how the
    operation is applied (e.g. recording_source) without changing its payload identity."""
    data = dict(data)
    key = data.pop("idempotency_key")
    operation_type = f"{spec.name}:{target_id}" if target_id else spec.name

    def handler():
        obj = spec.build(membership, user, {**data, **(overrides or {})}, target_id)
        return status.HTTP_201_CREATED, spec.output_cls(obj).data

    return run_idempotent(
        user=user,
        shop=membership.shop,
        operation_type=operation_type,
        operation_id=key,
        payload=to_jsonable(data),
        handler=handler,
    )


# ------------------------------------------------------------------ builders
def _opening_stock(m, user, d, target_id):
    return services.record_opening_stock(
        shop=m.shop, user=user, shop_product_id=target_id, unit_id=d["product_unit_id"],
        quantity=d["quantity"], unit_cost=d.get("unit_cost"), note=d["note"],
    )  # fmt: skip


def _adjustment(m, user, d, target_id):
    return services.record_adjustment(
        shop=m.shop, user=user, shop_product_id=d["shop_product_id"],
        delta_base=d["quantity_base_delta"], reason=d["reason"],
    )  # fmt: skip


def _receipt(m, user, d, target_id):
    return services.record_purchase_receipt(
        shop=m.shop, user=user, items=d["items"], supplier_name=d["supplier_name"],
        received_at=d.get("received_at"),
    )  # fmt: skip


def _sale(m, user, d, target_id):
    return services.record_sale(
        shop=m.shop, user=user, items=d["items"], sold_at=d.get("sold_at"),
        recording_source=d["recording_source"],
    )  # fmt: skip


def _reversal(m, user, d, target_id):
    return services.reverse_movement(
        shop=m.shop, user=user, movement_id=target_id, reason=d["reason"]
    )


def _count_start(m, user, d, target_id):
    return counts.start_stock_count(
        shop=m.shop, user=user, shop_product_ids=d.get("shop_product_ids"), note=d["note"]
    )


def _count_record(m, user, d, target_id):
    return counts.record_counts(shop=m.shop, user=user, count_id=target_id, entries=d["items"])


def _count_submit(m, user, d, target_id):
    return counts.submit_stock_count(shop=m.shop, user=user, count_id=target_id)


def _count_approve(m, user, d, target_id):
    return counts.approve_stock_count(shop=m.shop, user=user, count_id=target_id)


def _count_cancel(m, user, d, target_id):
    return counts.cancel_stock_count(shop=m.shop, user=user, count_id=target_id, reason=d["reason"])


OPENING_STOCK = OperationSpec(
    "opening_stock", s.OpeningStockIn, s.MovementSerializer, _opening_stock,
    management_only=True, target_field="shop_product_id",
)  # fmt: skip
ADJUSTMENT = OperationSpec(
    "stock_adjustment", s.AdjustmentIn, s.MovementSerializer, _adjustment, management_only=True
)  # fmt: skip
RECEIPT = OperationSpec("purchase_receipt", s.PurchaseReceiptIn, s.PurchaseReceiptOut, _receipt)
SALE = OperationSpec("sale", s.SaleIn, s.SaleOut, _sale)
REVERSAL = OperationSpec(
    "stock_reversal", s.ReversalIn, s.MovementSerializer, _reversal,
    management_only=True, target_field="movement_id",
)  # fmt: skip

# Stock counts are online-only for now (not in SYNCABLE). Anyone in the shop can count;
# only an owner/manager can approve or cancel.
_COUNT_OUT = s.StockCountOut
COUNT_START = OperationSpec("stock_count_start", s.StockCountStartIn, _COUNT_OUT, _count_start)
COUNT_RECORD = OperationSpec(
    "stock_count_record", s.StockCountRecordIn, _COUNT_OUT, _count_record, target_field="count_id"
)  # fmt: skip
COUNT_SUBMIT = OperationSpec(
    "stock_count_submit", s.StockCountActionIn, _COUNT_OUT, _count_submit, target_field="count_id"
)  # fmt: skip
COUNT_APPROVE = OperationSpec(
    "stock_count_approve", s.StockCountActionIn, _COUNT_OUT, _count_approve,
    management_only=True, target_field="count_id",
)  # fmt: skip
COUNT_CANCEL = OperationSpec(
    "stock_count_cancel", s.ReversalIn, _COUNT_OUT, _count_cancel,
    management_only=True, target_field="count_id",
)  # fmt: skip

# Operations an offline client may submit through POST /shops/{id}/sync/.
SYNCABLE = {
    spec.name: spec for spec in (OPENING_STOCK, ADJUSTMENT, RECEIPT, SALE, REVERSAL)
}
OFFLINE_OVERRIDES = {"sale": {"recording_source": Sale.Source.OFFLINE}}
