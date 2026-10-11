"""
PDEUE Authentic Venue Tape Loader (WP-8E)
Parses and streams historical Central Limit Order Book (CLOB) Level 2 snapshots
and trade prints from Kalshi and Polymarket archives.

Governing Invariants:
- Monotonic Sequencing: Timestamps must advance chronologically; out-of-order ticks are rejected.
- ADR-008 Exact-Cent Bounds: All print prices must fall strictly within [1, 99] integer cents.
- Fail-Closed: Corrupted records trigger validation errors rather than synthetic fills.
"""

import json
from dataclasses import dataclass
from typing import List, Dict, Any, Generator, Optional
from pathlib import Path
from app.domain.venue_tape_ingestor import MarketTradePrint

@dataclass(frozen=True)
class HistoricalContractMetadata:
    contract_id: str
    venue: str
    category: str
    factor_group: str
    scheduled_release_timestamp_ns: Optional[int]
    settlement_price_cents: Optional[int]

class VenueTapeLoader:
    @staticmethod
    def parse_trade_print_record(row: Dict[str, Any]) -> MarketTradePrint:
        """Parses and validates a single trade tape record from authentic venue archives."""
        required_fields = ["trade_id", "contract_id", "category", "timestamp_ns", "price_cents", "volume", "aggressor_side"]
        for field in required_fields:
            if field not in row:
                raise ValueError(f"Missing required tape field: '{field}'")

        price = int(row["price_cents"])
        if price < 1 or price > 99:
            raise ValueError(f"ADR-008 Violation: Trade print price {price}¢ outside [1, 99]¢ bounds")

        volume = int(row["volume"])
        if volume <= 0:
            raise ValueError(f"Invalid volume: {volume} (must be > 0)")

        side = str(row["aggressor_side"]).upper()
        if side not in ("BUY", "SELL"):
            raise ValueError(f"Invalid aggressor side: '{side}' (must be BUY or SELL)")

        return MarketTradePrint(
            trade_id=str(row["trade_id"]),
            contract_id=str(row["contract_id"]),
            category=str(row["category"]),
            timestamp_ns=int(row["timestamp_ns"]),
            price_cents=price,
            volume=volume,
            aggressor_side=side
        )

    @classmethod
    def stream_tape_file(cls, file_path: Path) -> Generator[MarketTradePrint, None, None]:
        """Streams trade prints line-by-line, verifying monotonic time advancement."""
        last_timestamp_ns = -1
        with open(file_path, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                clean_line = line.strip()
                if not clean_line or clean_line.startswith("#"):
                    continue
                record = json.loads(clean_line)
                trade_print = cls.parse_trade_print_record(record)

                if trade_print.timestamp_ns < last_timestamp_ns:
                    raise ValueError(
                        f"Sequence Anomaly at line {line_num}: timestamp {trade_print.timestamp_ns}ns "
                        f"regressed from prior tick {last_timestamp_ns}ns"
                    )
                last_timestamp_ns = trade_print.timestamp_ns
                yield trade_print
