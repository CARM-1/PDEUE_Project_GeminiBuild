"""Spread-sensitive Kelly sizing using ADR-008 integer-cent accounting."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_FLOOR
from typing import Any, Mapping


def _probability(value: Any, name: str) -> Decimal:
    number = Decimal(str(value))
    if not Decimal("0") < number < Decimal("1"):
        raise ValueError(f"{name} must be strictly between 0 and 1")
    return number


def _cents(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer number of cents")
    if value > 9_223_372_036_854_775_807:
        raise OverflowError(f"{name} exceeds signed 64-bit integer range")
    return value


@dataclass(frozen=True)
class KellyAllocation:
    allocation_cents: int
    kelly_cents: int
    allocation_fraction: float
    full_kelly: float
    b_net: float

    def as_dict(self) -> dict[str, int | float]:
        return {
            "allocation_cents": self.allocation_cents,
            "kelly_cents": self.kelly_cents,
            "allocation_fraction": self.allocation_fraction,
            "full_kelly": self.full_kelly,
            "b_net": self.b_net,
        }


class DynamicSpreadKellyEngine:
    """Calculate a conservative allocation from an IF-008 market snapshot.

    Decimal arithmetic is used until the final, downward cent conversion.  The
    returned stake is therefore an integer and can never exceed five percent of
    total equity.
    """

    WATERFALL_RETENTION = Decimal("0.87")
    MAX_EQUITY_FRACTION = Decimal("0.05")

    @staticmethod
    def spread_fraction(spread: Any) -> Decimal:
        spread_decimal = Decimal(str(spread))
        if spread_decimal < 0:
            raise ValueError("spread cannot be negative")
        return max(Decimal("0.05"), min(Decimal("0.25"), Decimal("0.25") - Decimal("5.0") * (spread_decimal - Decimal("0.01"))))

    def calculate_allocation(
        self, *, model_probability: Any, market_probability: Any,
        spread: Any, total_equity_cents: int,
    ) -> KellyAllocation:
        probability = _probability(model_probability, "model_probability")
        market = _probability(market_probability, "market_probability")
        equity = _cents(total_equity_cents, "total_equity_cents")
        b_net = self.WATERFALL_RETENTION * ((Decimal("1") - market) / market)
        full_kelly = max(Decimal("0"), (b_net * probability - (Decimal("1") - probability)) / b_net)
        fraction = self.spread_fraction(spread)
        kelly_cents = int((Decimal(equity) * full_kelly * fraction).to_integral_value(rounding=ROUND_FLOOR))
        equity_cap = int((Decimal(equity) * self.MAX_EQUITY_FRACTION).to_integral_value(rounding=ROUND_FLOOR))
        allocation = min(kelly_cents, equity_cap)
        return KellyAllocation(allocation, kelly_cents, float(fraction), float(full_kelly), float(b_net))

    def calculate_from_snapshot(
        self, snapshot: Mapping[str, Any], *, model_probability: Any,
        total_equity_cents: int,
    ) -> KellyAllocation:
        """Size from the bid/ask fields of an IF-008 MarketSnapshot."""
        bid = _probability(snapshot["yes_bid"], "yes_bid")
        ask = _probability(snapshot["yes_ask"], "yes_ask")
        if ask < bid:
            raise ValueError("yes_ask cannot be below yes_bid")
        midpoint = (bid + ask) / Decimal("2")
        return self.calculate_allocation(
            model_probability=model_probability, market_probability=midpoint,
            spread=ask - bid, total_equity_cents=total_equity_cents,
        )


class DynamicSpreadKellyRegime:
    """Backward-compatible spread-fraction facade used by paper-soak tooling."""

    def __init__(self, base_fraction: float = 0.25, defensive_floor: float = 0.05, max_spread: float = 0.05):
        self.base_fraction = base_fraction
        self.defensive_floor = defensive_floor
        self.max_spread = max_spread

    def calculate_active_fraction(self, current_spread: float) -> float:
        return round(float(DynamicSpreadKellyEngine.spread_fraction(current_spread)), 4)
