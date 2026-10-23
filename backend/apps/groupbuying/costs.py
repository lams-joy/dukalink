"""Pure money maths for group orders (no database), so the rules are easy to test.

Delivery fee split (decisions.md, 2026-10-23): proportional to each shop's committed quantity
in BASE units, rounded to 2 decimal places by the largest-remainder method. Shares always sum
exactly to the fee. Ties go to the earlier entry in the list the caller passes in, which the
caller orders by earliest `joined_at`, then shop id, so the result is deterministic.
"""

from decimal import ROUND_DOWN, Decimal, localcontext

CENT = Decimal("0.01")


def allocate_delivery_fee(fee: Decimal, weighted: list[tuple[object, Decimal]]) -> dict:
    """weighted: [(key, weight)] in tie-break order. Returns {key: share}, summing to `fee`."""
    if not weighted:
        raise ValueError("Nothing to allocate the fee to.")
    total_weight = sum(weight for _, weight in weighted)
    if total_weight <= 0 or any(weight <= 0 for _, weight in weighted):
        raise ValueError("Every weight must be positive.")
    if fee < 0 or fee != fee.quantize(CENT):
        raise ValueError("The fee must be a non-negative amount in whole cents.")

    with localcontext() as ctx:
        ctx.prec = 60
        exact = [fee * weight / total_weight for _, weight in weighted]
        floors = [value.quantize(CENT, rounding=ROUND_DOWN) for value in exact]
        leftover_cents = int((fee - sum(floors)) / CENT)
        # Largest fractional remainder first; equal remainders keep the caller's order.
        by_remainder = sorted(range(len(exact)), key=lambda i: (-(exact[i] - floors[i]), i))
        for i in by_remainder[:leftover_cents]:
            floors[i] += CENT
    return {key: floors[i] for i, (key, _) in enumerate(weighted)}
