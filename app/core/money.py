"""Helpers for monetary values. Money is always `Decimal`, never `float`."""

from decimal import ROUND_HALF_UP, Decimal
from typing import Final

CENT: Final = Decimal("0.01")
ZERO: Final = Decimal("0.00")


def to_money(value: Decimal) -> Decimal:
    """Normalize an amount to exactly two decimal places (e.g. `10` -> `10.00`)."""
    return value.quantize(CENT, rounding=ROUND_HALF_UP)
