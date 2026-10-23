"""Races on group commitments. They need real row locks, so they only run on PostgreSQL
(CI's database); SQLite ignores select_for_update and would pass or fail by luck."""

import threading
from datetime import timedelta
from decimal import Decimal

import pytest
from django.db import connection
from django.utils import timezone
from rest_framework.exceptions import APIException

from apps.audit.models import AuditEvent
from apps.groupbuying import services
from apps.groupbuying.models import GroupOrder, GroupParticipant
from apps.orders.models import Order
from apps.suppliers import services as supplier_services

pytestmark = [
    pytest.mark.django_db(transaction=True),
    pytest.mark.skipif(connection.vendor != "postgresql", reason="needs PostgreSQL row locking"),
]

D = Decimal


@pytest.fixture
def group(owner, shop, offer):
    return services.create_group(
        shop=shop, user=owner, offer_id=offer.pk, target_quantity=D("10"), quantity=D("4"),
        deadline=timezone.now() + timedelta(days=3), delivery_method="collection",
        delivery_point="Kondele market stage",
    )  # fmt: skip


def race(*jobs):
    """Run the callables at the same moment; outcomes in order: ("ok", result) or ("error", code)."""
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


def assert_reconciled(group_id):
    group = GroupOrder.objects.get(pk=group_id)
    expected = services.reconcile(group)
    assert group.committed_quantity == expected["committed_quantity"]
    assert group.committed_quantity_base == expected["committed_quantity_base"]
    assert group.participant_count == expected["participant_count"]


def test_simultaneous_joins_from_different_shops_all_count(
    group, other_user, other_shop, third_user, third_shop
):
    outcomes = race(
        lambda: services.join_group(
            shop=other_shop, user=other_user, group_id=group.pk, quantity=D("3")
        ),
        lambda: services.join_group(
            shop=third_shop, user=third_user, group_id=group.pk, quantity=D("2")
        ),
    )
    assert kinds(outcomes) == ["ok", "ok"], outcomes
    group.refresh_from_db()
    assert group.committed_quantity == D("9") and group.participant_count == 3
    assert_reconciled(group.pk)


def test_the_same_shop_joining_twice_at_once_commits_once(group, other_user, other_shop):
    join = lambda: services.join_group(  # noqa: E731
        shop=other_shop, user=other_user, group_id=group.pk, quantity=D("3")
    )
    outcomes = race(join, join)
    assert kinds(outcomes) == ["error", "ok"], outcomes
    assert GroupParticipant.objects.filter(group=group, shop=other_shop).count() == 1
    group.refresh_from_db()
    assert group.committed_quantity == D("7")
    assert_reconciled(group.pk)


def test_two_joins_cannot_oversubscribe_the_offer(
    group, verified, seller, offer, other_user, other_shop, third_user, third_shop
):
    supplier_services.update_offer(
        wholesaler=verified, offer_id=offer.pk, actor=seller,
        values={"available_quantity": D("10")},
    )  # fmt: skip
    # 4 already committed of 10 available: 5 fits, but 5 + 5 does not.
    outcomes = race(
        lambda: services.join_group(
            shop=other_shop, user=other_user, group_id=group.pk, quantity=D("5")
        ),
        lambda: services.join_group(
            shop=third_shop, user=third_user, group_id=group.pk, quantity=D("5")
        ),
    )
    assert kinds(outcomes) == ["error", "ok"], outcomes
    group.refresh_from_db()
    assert group.committed_quantity == D("9") and group.participant_count == 2
    assert_reconciled(group.pk)


def test_a_change_and_a_withdrawal_at_once_leave_consistent_totals(
    group, other_user, other_shop
):
    services.join_group(shop=other_shop, user=other_user, group_id=group.pk, quantity=D("3"))
    outcomes = race(
        lambda: services.change_commitment(
            shop=other_shop, user=other_user, group_id=group.pk, quantity=D("6")
        ),
        lambda: services.withdraw(shop=other_shop, user=other_user, group_id=group.pk),
    )
    # Either order is legal (change then withdraw, or withdraw then a refused change).
    assert all(kind in ("ok", "error") for kind, _ in outcomes), outcomes
    assert ("ok", outcomes[1][1]) == outcomes[1]  # the withdrawal always goes through
    group.refresh_from_db()
    assert group.committed_quantity == D("4") and group.participant_count == 1
    assert_reconciled(group.pk)


def test_a_join_racing_a_cancel_never_corrupts_the_group(
    group, owner, shop, other_user, other_shop
):
    race(
        lambda: services.join_group(
            shop=other_shop, user=other_user, group_id=group.pk, quantity=D("3")
        ),
        lambda: services.cancel_group(
            shop=shop, user=owner, group_id=group.pk, reason="changed plan"
        ),
    )
    group.refresh_from_db()
    assert group.status == GroupOrder.Status.CANCELLED
    assert_reconciled(group.pk)


# ------------------------------------------------------------------ lifecycle races (5b)
@pytest.fixture
def full_group(group, other_user, other_shop, owner, shop):
    """Target 10; 4 + 6 committed, still open."""
    services.join_group(shop=other_shop, user=other_user, group_id=group.pk, quantity=D("6"))
    group.refresh_from_db()
    return group


@pytest.fixture
def closed(full_group, owner, shop):
    return services.close_group(shop=shop, user=owner, group_id=full_group.pk)


def test_confirm_racing_a_decline_has_one_winner(closed, verified, seller):
    outcomes = race(
        lambda: services.confirm_group(wholesaler=verified, actor=seller, group_id=closed.pk),
        lambda: services.decline_group(
            wholesaler=verified, actor=seller, group_id=closed.pk, reason="No stock"
        ),
    )
    assert kinds(outcomes) == ["error", "ok"], outcomes
    closed.refresh_from_db()
    assert closed.status in (GroupOrder.Status.CONFIRMED, GroupOrder.Status.DECLINED)
    # orders exist exactly when the group was confirmed, never after a decline
    assert Order.objects.count() == (2 if closed.status == GroupOrder.Status.CONFIRMED else 0)
    # the loser never left half-written terms behind (the DB constraint also guarantees it)
    assert (closed.confirmed_unit_price is not None) == (
        closed.status == GroupOrder.Status.CONFIRMED
    )


def test_two_confirms_at_once_confirm_once(closed, verified, seller):
    confirm = lambda: services.confirm_group(  # noqa: E731
        wholesaler=verified, actor=seller, group_id=closed.pk
    )
    outcomes = race(confirm, confirm)
    assert kinds(outcomes) == ["error", "ok"], outcomes
    assert AuditEvent.objects.filter(action="group.confirmed").count() == 1
    assert Order.objects.count() == 2  # one per participating shop, never doubled


def test_many_readers_settling_an_expired_group_settle_it_once(full_group):
    GroupOrder.objects.filter(pk=full_group.pk).update(
        deadline=timezone.now() - timedelta(minutes=1)
    )
    settle = lambda: services.settle_expired()  # noqa: E731
    outcomes = race(settle, settle, settle)
    assert kinds(outcomes) == ["ok", "ok", "ok"], outcomes
    assert sorted(result for _, result in outcomes) == [0, 0, 1]  # exactly one did the work
    full_group.refresh_from_db()
    assert full_group.status == GroupOrder.Status.CLOSED
    assert AuditEvent.objects.filter(action="group.closed").count() == 1


def test_a_withdrawal_racing_an_early_close_never_closes_below_target(
    full_group, owner, shop, other_user, other_shop
):
    outcomes = race(
        lambda: services.close_group(shop=shop, user=owner, group_id=full_group.pk),
        lambda: services.withdraw(shop=other_shop, user=other_user, group_id=full_group.pk),
    )
    assert kinds(outcomes) == ["error", "ok"], outcomes  # one of them is always refused
    full_group.refresh_from_db()
    if full_group.status == GroupOrder.Status.CLOSED:
        assert full_group.committed_quantity >= full_group.target_quantity
    else:
        assert full_group.status == GroupOrder.Status.OPEN
        assert full_group.committed_quantity == D("4")
    assert_reconciled(full_group.pk)
