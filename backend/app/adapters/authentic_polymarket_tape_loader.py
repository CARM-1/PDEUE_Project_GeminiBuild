"""Normalize captured Polymarket JSON trades without deriving model inputs."""
from dataclasses import dataclass
import json
import math
from pathlib import Path


DEFAULT_TAPE = Path(__file__).resolve().parents[3] / 'data/venues/polymarket/raw_trades_verified.json'


@dataclass(frozen=True)
class MarketTradePrint:
    trade_id: str
    contract_id: str
    price_cents: int
    volume: int
    timestamp_ns: int
    aggressor_side: str
    contract_spec: str
    asset_id: str | None = None


def _text(record: dict, field: str) -> str:
    value = record.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'missing or invalid {field}')
    return value


def _number(record: dict, field: str) -> float:
    value = record.get(field)
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise ValueError(f'missing or invalid {field}')
    try:
        value = float(value)
    except ValueError as exc:
        raise ValueError(f'invalid {field}') from exc
    if not math.isfinite(value):
        raise ValueError(f'{field} must be finite')
    return value


def parse_authentic_polymarket_tape(content: bytes | str) -> list[MarketTradePrint]:
    """Validate every raw row, discard nonpositive lots, then sort by (time, ID).

    Duplicate transaction hashes are rejected even in discarded rows. Equal
    timestamps are allowed; the composite sequence key must strictly increase.
    Price conversion follows the directive's Python round-to-even rule.
    """
    records = json.loads(content)
    if not isinstance(records, list):
        raise ValueError('trade tape must be a JSON array')
    prints = []
    seen = set()
    for index, record in enumerate(records):
        try:
            if not isinstance(record, dict):
                raise ValueError('trade must be an object')
            trade_id = _text(record, 'transactionHash')
            if trade_id in seen:
                raise ValueError('duplicate trade ID')
            seen.add(trade_id)
            contract_id = _text(record, 'conditionId' if record.get('conditionId') else 'asset')
            spec = _text(record, 'title')
            side = _text(record, 'side')
            if side not in ('BUY', 'SELL'):
                raise ValueError('invalid aggressor side')
            price = _number(record, 'price')
            if not 0 <= price <= 1:
                raise ValueError('price must be between zero and one')
            size = _number(record, 'size')
            timestamp = _number(record, 'timestamp')
            if timestamp < 0 or not timestamp.is_integer():
                raise ValueError('timestamp must be nonnegative integer seconds')
            volume = int(math.floor(size))
            if volume <= 0:
                continue
            prints.append(MarketTradePrint(
                trade_id, contract_id, int(round(price * 100)), volume,
                int(record['timestamp']) * 1_000_000_000, side, spec,
                _text(record, 'asset') if 'asset' in record else None,
            ))
        except (ValueError, TypeError, OverflowError) as exc:
            raise ValueError(f'raw trade {index}: {exc}') from exc
    prints.sort(key=lambda trade: (trade.timestamp_ns, trade.trade_id))
    if any((a.timestamp_ns, a.trade_id) >= (b.timestamp_ns, b.trade_id)
           for a, b in zip(prints, prints[1:])):
        raise ValueError('trade sequence must strictly increase')
    if not prints:
        raise ValueError('empty trade tape after integer lot filtering')
    return prints


def load_authentic_polymarket_tape(path: Path | str = DEFAULT_TAPE) -> list[MarketTradePrint]:
    return parse_authentic_polymarket_tape(Path(path).read_bytes())
