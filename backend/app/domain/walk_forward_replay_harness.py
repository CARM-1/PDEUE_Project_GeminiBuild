"""Offline, point-in-time replay of a static Bitcoin binary-contract tape.

The tape is a synthetic historical test vector, not a captured exchange feed.
Independent underlying inputs and the initial L2 snapshot are explicit scenario
assumptions. Prints cannot reconstruct a book or estimate Bitcoin spot prices.
One inside maker bid is decided before the first print; future prints only drive
queue execution. The settlement spot is used only after replay ends.
"""
from dataclasses import dataclass, field
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path

from app.domain.microstructure_queue_tracker import MicrostructureQueueTracker, nonnegative_integer
from app.domain.settlement_engine import SettlementEngine

DEFAULT_FIXTURE = Path(__file__).resolve().parents[2] / 'tests/fixtures/static_crypto_history.jsonl'
YEAR_NS = 365 * 24 * 60 * 60 * 1_000_000_000
MIN_NET_EDGE = Decimal('0.03')
CONTRACT_ID = 'BTC-20250102-100000-YES'


def black_scholes_probability(spot: float, strike: float, volatility: float,
                              years: float, rate: float = 0.0) -> float:
    """Risk-neutral P(S_T >= K) = Phi(d2), without any contract quote input."""
    if not all(math.isfinite(x) for x in (spot, strike, volatility, years, rate)):
        raise ValueError('model inputs must be finite')
    if spot <= 0 or strike <= 0 or volatility < 0 or years < 0:
        raise ValueError('invalid log-normal model inputs')
    if years == 0:
        return float(spot >= strike)
    if volatility == 0:
        return float(math.log(spot / strike) + rate * years >= 0)
    d2 = (math.log(spot / strike) + (rate - volatility**2 / 2) * years) / (volatility * math.sqrt(years))
    return 0.5 * math.erfc(-d2 / math.sqrt(2))


@dataclass(frozen=True)
class ReplayScenario:
    contract_id: str = CONTRACT_ID
    observed_at_ns: int = 1735689598000000000
    decision_at_ns: int = 1735689599000000000
    expiry_ns: int = 1735776000000000000
    spot: float = 100000.0
    strike: float = 100000.0
    volatility: float = 0.60
    rate: float = 0.0
    settlement_spot: float = 101000.0
    best_bid_cents: int = 45
    best_ask_cents: int = 49
    # The inside price has zero visible queue; existing best bid has 20 units.
    bid_depth: dict[int, int] = field(default_factory=lambda: {45: 20})
    quantity: int = 10
    fee_cents_per_contract: int = 0
    initial_capital_cents: int = 10000


def load_trade_prints(path: Path = DEFAULT_FIXTURE, contract_id: str = CONTRACT_ID) -> tuple[dict, ...]:
    """Reject corrupt tapes rather than sort, coerce, or silently discard rows."""
    return _parse_trade_prints(Path(path).read_text(), contract_id)


def _parse_trade_prints(content: str, contract_id: str) -> tuple[dict, ...]:
    rows = []
    seen = set()
    previous = -1
    fields = {'trade_id', 'contract_id', 'category', 'timestamp_ns', 'price_cents', 'volume', 'aggressor_side'}
    for line in content.splitlines():
        row = json.loads(line)
        if not isinstance(row, dict) or set(row) != fields:
            raise ValueError('invalid trade schema')
        if not isinstance(row['trade_id'], str) or not row['trade_id'] or row['trade_id'] in seen:
            raise ValueError('invalid or duplicate trade ID')
        if row['contract_id'] != contract_id or row['category'] != 'CRYPTO':
            raise ValueError('unexpected contract or category')
        for name in ('timestamp_ns', 'price_cents', 'volume'):
            nonnegative_integer(row[name], name)
        if row['timestamp_ns'] <= previous or not 0 < row['price_cents'] < 100 or row['volume'] == 0:
            raise ValueError('invalid chronology, price, or volume')
        if row['aggressor_side'] not in ('BUY', 'SELL'):
            raise ValueError('invalid aggressor side')
        previous = row['timestamp_ns']
        seen.add(row['trade_id'])
        rows.append(row)
    if not rows:
        raise ValueError('empty trade tape')
    return tuple(rows)


class WalkForwardReplayHarness:
    def __init__(self, scenario: ReplayScenario | None = None):
        self.scenario = scenario or ReplayScenario()

    def run(self, fixture_path: Path = DEFAULT_FIXTURE) -> dict:
        s = self.scenario
        # Read once so the digest and the replay refer to the same static tape.
        tape_bytes = Path(fixture_path).read_bytes()
        rows = _parse_trade_prints(tape_bytes.decode('utf-8'), s.contract_id)
        for name in ('observed_at_ns', 'decision_at_ns', 'expiry_ns', 'quantity',
                     'fee_cents_per_contract', 'initial_capital_cents', 'best_bid_cents', 'best_ask_cents'):
            nonnegative_integer(getattr(s, name), name)
        if not s.observed_at_ns < s.decision_at_ns < rows[0]['timestamp_ns'] <= rows[-1]['timestamp_ns'] < s.expiry_ns:
            raise ValueError('observations/decision/prints/settlement violate point-in-time ordering')
        if not math.isfinite(s.settlement_spot) or s.settlement_spot <= 0:
            raise ValueError('invalid settlement spot')
        if not 0 < s.best_bid_cents < s.best_ask_cents < 100:
            raise ValueError('invalid initial book')
        for price, depth in s.bid_depth.items():
            nonnegative_integer(price, 'depth price')
            nonnegative_integer(depth, 'depth quantity')
            if not 0 < price <= s.best_bid_cents:
                raise ValueError('bid depth contradicts best bid')
        if s.bid_depth.get(s.best_bid_cents, 0) == 0:
            raise ValueError('missing displayed depth at best bid')
        p_fair = black_scholes_probability(s.spot, s.strike, s.volatility,
                                          (s.expiry_ns - s.decision_at_ns) / YEAR_NS, s.rate)
        limit = s.best_bid_cents + 1
        edge = Decimal(str(p_fair)) - Decimal(limit + s.fee_cents_per_contract) / 100
        admissible = limit < s.best_ask_cents and edge >= MIN_NET_EDGE
        affordable = s.initial_capital_cents // (limit + s.fee_cents_per_contract)
        quantity = min(s.quantity, affordable) if admissible else 0
        tracker = MicrostructureQueueTracker(limit, quantity, s.bid_depth.get(limit, 0))
        fills = []
        for row in rows:
            filled = tracker.process_trade(price_cents=row['price_cents'], volume=row['volume'],
                                           aggressor_side=row['aggressor_side'])
            if filled:
                fills.append({'trade_id': row['trade_id'], 'timestamp_ns': row['timestamp_ns'],
                              'quantity': filled, 'price_cents': limit})
        filled_quantity = sum(fill['quantity'] for fill in fills)
        deployed = filled_quantity * limit
        fees = filled_quantity * s.fee_cents_per_contract
        payout = filled_quantity * (100 if s.settlement_spot >= s.strike else 0)
        pnl = payout - deployed - fees
        waterfall = SettlementEngine().calculate_waterfall_split(pnl)
        return {
            'status': 'COMPLETED' if quantity else 'ABSTAINED',
            'reason': 'NET_EDGE_BELOW_MINIMUM' if edge < MIN_NET_EDGE else
                      ('NO_INSIDE_PRICE' if limit >= s.best_ask_cents else
                       ('NO_CAPACITY' if not quantity else 'ADMITTED')),
            'trade_print_count': len(rows), 'p_fair': p_fair, 'net_edge': str(edge),
            'limit_price_cents': limit, 'posted_quantity': quantity,
            'initial_q_ahead': s.bid_depth.get(limit, 0), 'remaining_q_ahead': tracker.q_ahead,
            'unfilled_quantity': tracker.remaining_quantity, 'filled_quantity': filled_quantity,
            'fills': fills, 'deployed_cents': deployed, 'fee_cents': fees,
            'payout_cents': payout, 'net_pnl_cents': pnl, 'waterfall': waterfall,
            'initial_capital_cents': s.initial_capital_cents,
            'final_capital_cents': s.initial_capital_cents + pnl,
            'fixture_sha256': hashlib.sha256(tape_bytes).hexdigest(),
            'data_provenance': 'synthetic static historical test vector',
        }
