"""Group buying 5c: the delivery-fee split. Pure maths, no database."""

import random
from decimal import Decimal

import pytest

from apps.groupbuying.costs import CENT, allocate_delivery_fee

D = Decimal


# ================================================================== the fee split (no database)
def shares(fee, *weights):
    keys = list(range(len(weights)))
    result = allocate_delivery_fee(D(fee), list(zip(keys, map(D, weights), strict=True)))
    return [result[k] for k in keys]


def test_an_even_split_that_does_not_divide_gives_the_extra_cent_to_the_first():
    assert shares("1000.00", 1, 1, 1) == [D("333.34"), D("333.33"), D("333.33")]


def test_shares_are_proportional_to_the_quantities():
    assert shares("1500.00", 200, 300, 500) == [D("300.00"), D("450.00"), D("750.00")]


def test_the_largest_remainder_wins_not_the_first_in_line():
    # exact 0.0333.. and 0.0667..: the second has the bigger remainder, so it gets the cent
    assert shares("0.10", 1, 2) == [D("0.03"), D("0.07")]


def test_ties_follow_the_order_given_so_the_result_is_deterministic():
    assert shares("0.05", 1, 1, 1) == [D("0.02"), D("0.02"), D("0.01")]
    keys = ["first-in", "second-in", "third-in"]
    again = allocate_delivery_fee(D("0.05"), [(k, D(1)) for k in keys])
    assert again == {"first-in": D("0.02"), "second-in": D("0.02"), "third-in": D("0.01")}
    reordered = allocate_delivery_fee(D("0.05"), [(k, D(1)) for k in reversed(keys)])
    assert reordered["third-in"] == D("0.02") and reordered["first-in"] == D("0.01")


def test_one_shop_pays_the_whole_fee_and_a_zero_fee_is_all_zeros():
    assert shares("1234.56", 7) == [D("1234.56")]
    assert shares("0.00", 3, 4) == [D("0.00"), D("0.00")]


def test_shares_always_sum_exactly_and_stay_within_a_cent_of_the_exact_share():
    rng = random.Random(20261023)
    for _ in range(500):
        n = rng.randint(1, 12)
        weights = [D(rng.randint(1, 5000)) / D(rng.choice([1, 10, 1000])) for _ in range(n)]
        fee = D(rng.randint(0, 5_000_000)) / 100
        result = shares(fee, *weights)
        assert sum(result) == fee
        total = sum(weights)
        for share, weight in zip(result, weights, strict=True):
            assert share >= 0 and abs(share - fee * weight / total) < CENT


@pytest.mark.parametrize(
    ("fee", "weighted"),
    [
        (D("10.00"), []),
        (D("10.00"), [("a", D(0))]),
        (D("10.00"), [("a", D(1)), ("b", D(-1))]),
        (D("-1.00"), [("a", D(1))]),
        (D("10.005"), [("a", D(1))]),
    ],
)
def test_impossible_allocations_are_refused(fee, weighted):
    with pytest.raises(ValueError, match=r"."):
        allocate_delivery_fee(fee, weighted)
