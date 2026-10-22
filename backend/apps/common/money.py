from decimal import ROUND_HALF_UP, Decimal

MONEY_QUANT = Decimal("0.01")
UNIT_COST_QUANT = Decimal("0.000001")


def money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)


def per_base_unit_cost(unit_cost: Decimal, base_quantity: Decimal) -> Decimal:
    """Cost of one base unit, given the cost of one entry/purchase unit."""
    return (unit_cost / base_quantity).quantize(UNIT_COST_QUANT, rounding=ROUND_HALF_UP)
