"""Races on the order workflow. They need real row locks, so they only run on PostgreSQL
(CI's database); SQLite ignores select_for_update and would pass or fail by luck."""

import threading
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from django.db import connection
from rest_framework.exceptions import APIException

from apps.audit.models import AuditEvent
from apps.inventory.models import PurchaseReceipt, ShopProduct
from apps.orders import services
from apps.orders.models import Order
from apps.suppliers import services as supplier_services

from .conftest import make_client
from .test_orders import line, place, placed, receive_body, to_dispatched

pytestmark = [
    pytest.mark.django_db(transaction=True),
    pytest.mark.skipif(connection.vendor != "postgresql", reason="needs PostgreSQL row locking"),
]

D = Decimal


@pytest.fixture
def sugar_offer(verified, seller, sugar):
    return supplier_services.create_offer(
        wholesaler=verified, actor=seller, product_id=sugar.product.pk,
        product_unit_id=sugar.sack.pk, price_per_unit=D("7000"),
    )  # fmt: skip


def race(*jobs):
    """Run the callables at the same moment; return their outcomes in order:
    ("ok", result) or ("error", exception code/class name)."""
    barrier = threading.Barrier(len(jobs))
    outcomes = [None] * len(jobs)

    def runner(i, job):
        try:
            barrier.wait()
            outcomes[i] = ("ok", job())
        except APIException as exc:
            outcomes[i] = ("error", exc.get_codes())
        except Exception as exc:  # noqa: BLE001 - surfaced by the assertions below
            outcomes[i] = ("crash", repr(exc))
        finally:
            connection.close()

    threads = [threading.Thread(target=runner, args=(i, job)) for i, job in enumerate(jobs)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return outcomes


def kinds(outcomes):
    return sorted(kind for kind, _ in outcomes)


def order_audit(order_id, action):
    return AuditEvent.objects.filter(object_type="order", object_id=order_id, action=action).count()


def test_two_confirms_at_once_confirm_exactly_once(
    owner_client, seller_client, seller, shop, verified, sugar_offer
):
    order = placed(owner_client, shop, sugar_offer)
    confirm = lambda: services.confirm_order(  # noqa: E731
        wholesaler=verified, actor=seller, order_id=order["id"], delivery_fee=D("100")
    )
    outcomes = race(confirm, confirm)
    assert kinds(outcomes) == ["error", "ok"], outcomes
    assert Order.objects.get(pk=order["id"]).status == Order.Status.CONFIRMED
    assert order_audit(order["id"], "order.confirmed") == 1


def test_confirm_racing_a_reject_has_one_winner(owner_client, seller, shop, verified, sugar_offer):
    """Both need the order to still be 'submitted', so exactly one of them can win.
    (Confirm vs a shop cancel is not a race: a confirmed order may still be cancelled.)"""
    order = placed(owner_client, shop, sugar_offer)
    outcomes = race(
        lambda: services.confirm_order(wholesaler=verified, actor=seller, order_id=order["id"]),
        lambda: services.reject_order(
            wholesaler=verified, actor=seller, order_id=order["id"], reason="out of stock"
        ),
    )
    assert kinds(outcomes) == ["error", "ok"], outcomes
    final = Order.objects.get(pk=order["id"]).status
    assert final in (Order.Status.CONFIRMED, Order.Status.REJECTED)
    winner = "order.confirmed" if final == Order.Status.CONFIRMED else "order.rejected"
    loser = "order.rejected" if winner == "order.confirmed" else "order.confirmed"
    assert order_audit(order["id"], winner) == 1
    assert order_audit(order["id"], loser) == 0


def test_two_receipts_at_once_add_the_stock_once(
    owner_client, seller_client, owner, shop, verified, sugar_offer, sugar
):
    order = to_dispatched(owner_client, seller_client, shop, verified, sugar_offer, "2")
    entries = [
        {"item_id": UUID(item["id"]), "received_quantity": D("2")} for item in order["items"]
    ]
    receive = lambda: services.receive_order(  # noqa: E731
        shop=shop, actor=owner, order_id=order["id"], entries=entries
    )
    outcomes = race(receive, receive)
    assert kinds(outcomes) == ["error", "ok"], outcomes
    assert PurchaseReceipt.objects.filter(shop=shop).count() == 1
    assert ShopProduct.objects.get(shop=shop, product=sugar.product).quantity_base == D("100")
    assert order_audit(order["id"], "order.received") == 1


def test_receive_with_the_same_idempotency_key_applies_once(
    owner_client, seller_client, shop, owner, verified, sugar_offer, sugar
):
    order = to_dispatched(owner_client, seller_client, shop, verified, sugar_offer, "2")
    body = receive_body(order, ["2"])
    url = f"/api/v1/shops/{shop.pk}/orders/{order['id']}/receive/"
    client = make_client(owner)
    outcomes = race(
        lambda: client.post(url, body, format="json").status_code,
        lambda: client.post(url, body, format="json").status_code,
    )
    assert all(kind == "ok" for kind, _ in outcomes), outcomes
    assert PurchaseReceipt.objects.filter(shop=shop).count() == 1
    assert ShopProduct.objects.get(shop=shop, product=sugar.product).quantity_base == D("100")


def test_placing_with_the_same_idempotency_key_creates_one_order(
    owner, shop, sugar_offer
):
    key = str(uuid4())
    client = make_client(owner)
    outcomes = race(
        lambda: place(client, shop, line(sugar_offer, "2"), key=key).status_code,
        lambda: place(client, shop, line(sugar_offer, "2"), key=key).status_code,
    )
    assert all(kind == "ok" for kind, _ in outcomes), outcomes
    assert Order.objects.filter(shop=shop).count() == 1
