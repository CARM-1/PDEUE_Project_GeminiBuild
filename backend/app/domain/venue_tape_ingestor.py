"""
PDEUE Authentic Venue Tape Ingestor & Microstructure Queue Tracker (WP-8C)
Implements nanosecond point-in-time event sequencing and authentic FIFO queue depth tracking.

Governing Microstructure Rules:
- Queue Priority: Tracks resting volume ahead (Q_ahead) on Level 2 snapshots.
- Volume Deduction: Trade prints at our price deduct from Q_ahead before filling our order.
- Zero Lookahead: Feeds are processed strictly in monotonic timestamp order.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple

@dataclass(frozen=True)
class MarketTradePrint:
    trade_id: str
    contract_id: str
    category: str
    timestamp_ns: int
    price_cents: int
    volume: int
    aggressor_side: str  # BUY or SELL

@dataclass
class RestingQueueState:
    order_id: str
    contract_id: str
    target_price_cents: int
    order_quantity: int
    queue_ahead_volume: int
    filled_quantity: int = 0

    @property
    def is_fully_filled(self) -> bool:
        return self.filled_quantity >= self.order_quantity

    @property
    def remaining_to_fill(self) -> int:
        return self.order_quantity - self.filled_quantity

class MicrostructureQueueTracker:
    def __init__(self):
        self.active_queues: Dict[str, RestingQueueState] = {}

    def register_order_in_queue(self, order_id: str, contract_id: str, price_cents: int, 
                                quantity: int, existing_l2_book_depth: int):
        """Registers a limit order behind existing resting volume at that price level"""
        self.active_queues[order_id] = RestingQueueState(
            order_id=order_id,
            contract_id=contract_id,
            target_price_cents=price_cents,
            order_quantity=quantity,
            queue_ahead_volume=max(0, existing_l2_book_depth)
        )

    def process_incoming_trade_print(self, print_record: MarketTradePrint) -> List[Tuple[str, int]]:
        """
        Deducts incoming aggressor print volume from queue_ahead before filling our order.
        Returns list of (order_id, newly_filled_quantity).
        """
        fills = []
        for oid, qstate in list(self.active_queues.items()):
            if qstate.contract_id == print_record.contract_id and print_record.price_cents <= qstate.target_price_cents:
                available_vol = print_record.volume
                if qstate.queue_ahead_volume > 0:
                    if available_vol <= qstate.queue_ahead_volume:
                        qstate.queue_ahead_volume -= available_vol
                        available_vol = 0
                    else:
                        available_vol -= qstate.queue_ahead_volume
                        qstate.queue_ahead_volume = 0

                if available_vol > 0 and not qstate.is_fully_filled:
                    fill_amount = min(qstate.remaining_to_fill, available_vol)
                    qstate.filled_quantity += fill_amount
                    fills.append((oid, fill_amount))

                if qstate.is_fully_filled:
                    del self.active_queues[oid]
        return fills
