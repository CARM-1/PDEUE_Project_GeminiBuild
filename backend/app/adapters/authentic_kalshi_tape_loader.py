"""Normalize Kalshi public trades and identified executions to YES prints.

    Public trades use taker_side=yes/no. Private executions must identify their
    liquidity role (is_taker) so a maker's own action is not called aggressor flow.
"""
from decimal import Decimal, ROUND_FLOOR, ROUND_HALF_EVEN
import json
from pathlib import Path

from app.adapters.authentic_polymarket_tape_loader import MarketTradePrint
from app.adapters.authentic_tape_utils import finite_decimal, required_text, timestamp_ns

DEFAULT_TAPE = Path(__file__).resolve().parents[3] / 'data/venues/kalshi/raw_trades.json'


def kalshi_records(content: bytes | str) -> list:
    payload = json.loads(content, parse_float=Decimal)
    if isinstance(payload, dict):
        keys = [name for name in ('trades', 'fills', 'executions') if name in payload]
        if len(keys) != 1:
            raise ValueError('expected exactly one trades/fills/executions array')
        payload = payload[keys[0]]
    if not isinstance(payload, list):
        raise ValueError('Kalshi tape must be an array or trade response object')
    return payload


def _yes_price_cents(row: dict) -> int:
    candidates = []
    for field, dollars, complement in (
        ('yes_price_dollars', True, False), ('yes_price', False, False),
        ('no_price_dollars', True, True), ('no_price', False, True),
    ):
        if field in row:
            price = finite_decimal(row[field], field) * (100 if dollars else 1)
            if not 0 <= price <= 100:
                raise ValueError('price outside binary payout bounds')
            if complement:
                price = 100 - price
            candidates.append(int(price.to_integral_value(rounding=ROUND_HALF_EVEN)))
    if not candidates:
        raise ValueError('missing explicitly denominated YES/NO price')
    if len(set(candidates)) != 1:
        raise ValueError('inconsistent YES/NO price fields')
    return candidates[0]


def _aggressor(row: dict) -> str:
    if 'taker_side' in row:
        side = required_text(row['taker_side'], 'taker_side').lower()
        if side not in ('yes', 'no'):
            raise ValueError('taker_side must be yes or no')
        return 'BUY' if side == 'yes' else 'SELL'
    if 'aggressor_side' in row:
        side = row['aggressor_side']
        if side not in ('BUY', 'SELL'):
            raise ValueError('invalid aggressor_side')
        return side
    side, action, is_taker = row.get('side'), row.get('action'), row.get('is_taker')
    if side not in ('yes', 'no') or action not in ('buy', 'sell') or type(is_taker) is not bool:
        raise ValueError('execution requires side, action, and is_taker aggressor evidence')
    buys_yes = (side == 'yes') == (action == 'buy')
    if not is_taker:
        buys_yes = not buys_yes
    return 'BUY' if buys_yes else 'SELL'


def parse_authentic_kalshi_tape(content: bytes | str) -> list[MarketTradePrint]:
    prints, seen = [], set()
    for index, row in enumerate(kalshi_records(content)):
        try:
            if not isinstance(row, dict):
                raise ValueError('trade must be an object')
            trade_id = required_text(row.get('trade_id', row.get('fill_id')), 'trade_id/fill_id')
            if trade_id in seen:
                raise ValueError('duplicate trade ID')
            seen.add(trade_id)
            ticker = required_text(row.get('ticker', row.get('market_ticker')), 'ticker')
            if 'timestamp_ns' in row:
                instant = timestamp_ns(row['timestamp_ns'], nanoseconds=True)
            else:
                instant = timestamp_ns(row.get('created_time', row.get('ts', row.get('timestamp'))))
            price = _yes_price_cents(row)
            size = finite_decimal(row.get('count_fp', row.get('count', row.get('size'))), 'count')
            volume = int(size.to_integral_value(rounding=ROUND_FLOOR))
            aggressor = _aggressor(row)
            if volume <= 0:
                continue
            prints.append(MarketTradePrint(trade_id, ticker, price, volume, instant,
                                           aggressor, required_text(row.get('title', ticker), 'title')))
        except (ValueError, TypeError, OverflowError) as exc:
            raise ValueError(f'Kalshi trade {index}: {exc}') from exc
    prints.sort(key=lambda trade: (trade.timestamp_ns, trade.trade_id))
    if not prints:
        raise ValueError('empty Kalshi tape after lot filtering')
    if any((a.timestamp_ns, a.trade_id) >= (b.timestamp_ns, b.trade_id)
           for a, b in zip(prints, prints[1:])):
        raise ValueError('Kalshi trade sequence must strictly increase')
    return prints


def load_authentic_kalshi_tape(path: str | Path = DEFAULT_TAPE) -> list[MarketTradePrint]:
    return parse_authentic_kalshi_tape(Path(path).read_bytes())
