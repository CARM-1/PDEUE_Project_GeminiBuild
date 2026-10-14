"""Deterministic FIFO queue simulation for one resting YES limit bid."""
from dataclasses import dataclass


def nonnegative_integer(value: int, name: str) -> None:
    if type(value) is not int or value < 0:
        raise ValueError(f'{name} must be a nonnegative integer')


@dataclass
class MicrostructureQueueTracker:
    """Seller-initiated prints consume displayed queue before simulated fills.

    A print below our price does not prove our venue/order was executed; this
    default model never grants a fill from a price-through assumption.
    Strategy D explicitly opts into sells at or below the resting limit. Those
    fills execute at the resting bid, never at the observed sell print price.
    Queue cancellations and hidden liquidity are not inferred from prints.
    """

    limit_price_cents: int
    remaining_quantity: int
    q_ahead: int
    allow_price_through: bool = False

    def __post_init__(self) -> None:
        for name in ('limit_price_cents', 'remaining_quantity', 'q_ahead'):
            nonnegative_integer(getattr(self, name), name)
        if not 0 < self.limit_price_cents < 100:
            raise ValueError('limit must be between 1 and 99 cents')

    def process_trade(self, *, price_cents: int, volume: int, aggressor_side: str) -> int:
        nonnegative_integer(price_cents, 'price_cents')
        nonnegative_integer(volume, 'volume')
        if aggressor_side not in ('BUY', 'SELL'):
            raise ValueError('invalid aggressor side')
        if aggressor_side != 'SELL' or price_cents > self.limit_price_cents:
            return 0
        if price_cents != self.limit_price_cents and not self.allow_price_through:
            return 0
        consumed = min(self.q_ahead, volume)
        self.q_ahead -= consumed
        filled = min(self.remaining_quantity, volume - consumed)
        self.remaining_quantity -= filled
        return filled
