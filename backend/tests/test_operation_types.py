"""operation_type is stored as "<name>:<target uuid>" for operations aimed at one object.
That combined string once overflowed varchar(50), which only PostgreSQL enforces (SQLite does
not), so these tests check the column width directly and would fail on either database."""

from uuid import uuid4

import pytest

from apps.inventory import operations
from apps.sync.models import SyncOperation

pytestmark = pytest.mark.django_db

UUID_LEN = len(str(uuid4()))


def all_specs():
    return [v for v in vars(operations).values() if isinstance(v, operations.OperationSpec)]


def test_the_column_fits_the_longest_name_with_a_target_id():
    width = SyncOperation._meta.get_field("operation_type").max_length
    longest = max(len(spec.name) + 1 + UUID_LEN for spec in all_specs())
    assert width >= longest, f"operation_type is {width} wide but needs {longest}"


def test_order_operation_types_also_fit():
    width = SyncOperation._meta.get_field("operation_type").max_length
    assert width >= len("order_receive:") + UUID_LEN


def test_a_long_operation_type_round_trips(owner, shop):
    longest = max(all_specs(), key=lambda spec: len(spec.name))
    operation_type = f"{longest.name}:{uuid4()}"
    row = SyncOperation.objects.create(
        user=owner, shop=shop, operation_id=uuid4(), operation_type=operation_type,
        payload_hash="0" * 64,
    )  # fmt: skip
    row.refresh_from_db()
    assert row.operation_type == operation_type
