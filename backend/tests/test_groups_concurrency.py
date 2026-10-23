"""Races on group commitments. They need real row locks, so they only run on PostgreSQL
(CI's database); SQLite ignores select_for_update and would pass or fail by luck."""

import threading
from datetime import timedelta
from decimal import Decimal

import pytest
from django.db import connection
from django.utils import timezone
from rest_framework.exceptions import APIException

from apps.groupbuying import services
from apps.groupbuying.models import GroupOrder, GroupParticipant
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
