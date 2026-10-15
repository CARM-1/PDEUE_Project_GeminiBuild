"""Offline, point-in-time replay of a static Bitcoin binary-contract tape.

The tape is a synthetic historical test vector, not a captured exchange feed.
Independent underlying inputs and the initial L2 snapshot are explicit scenario
assumptions. Prints cannot reconstruct a book or estimate Bitcoin spot prices.
One inside maker bid is decided before the first print; future prints only drive
queue execution. The settlement spot is used only after replay ends.
"""
from dataclasses import asdict, dataclass, field
from collections import Counter
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path

from app.domain.microstructure_queue_tracker import MicrostructureQueueTracker, nonnegative_integer
from app.domain.settlement_engine import SettlementEngine
from app.adapters.authentic_polymarket_tape_loader import (
    DEFAULT_TAPE, MarketTradePrint, parse_authentic_polymarket_tape,
)

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


def primary_contract_id(prints: list[MarketTradePrint]) -> str:
    """Choose the highest-count contract, with a stable ID tie-break."""
    counts = Counter(trade.contract_id for trade in prints)
    if not counts:
        raise ValueError('empty trade tape')
    return min(counts, key=lambda contract_id: (-counts[contract_id], contract_id))


def build_auto_scenario(prints: list[MarketTradePrint]) -> ReplayScenario:
    """Build an explicitly assumed simulation, never a reconstructed L2 book.

    Callers supply one chronological contract. The first print seeds an assumed
    spread, and cannot execute our order. Selection and expiry use capture metadata;
    model and settlement inputs are assumptions, not venue observations.
    """
    if not prints or any(trade.contract_id != prints[0].contract_id for trade in prints):
        raise ValueError('auto scenario requires one nonempty contract')
    first_ns, last_ns = prints[0].timestamp_ns, prints[-1].timestamp_ns
    if first_ns < 2_000_000_000 or first_ns > last_ns:
        raise ValueError('invalid auto-scenario time bounds')
    best_bid = max(1, min(97, prints[0].price_cents))
    return ReplayScenario(
        contract_id=prints[0].contract_id,
        observed_at_ns=first_ns,
        decision_at_ns=first_ns + 1,
        expiry_ns=last_ns + 300_000_000_000,
        spot=102000.0, strike=100000.0, volatility=0.60, rate=0.0,
        settlement_spot=101000.0,
        best_bid_cents=best_bid, best_ask_cents=best_bid + 2, bid_depth={best_bid: 5},
        quantity=10, fee_cents_per_contract=0, initial_capital_cents=10000,
    )


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
    def __init__(self, scenario: ReplayScenario | None = None, *,
                 strategy_d: bool = False, queue_ahead: int | None = None):
        self.explicit_scenario = scenario is not None
        self.scenario = scenario or ReplayScenario()
        self.strategy_d = strategy_d
        if queue_ahead is not None:
            nonnegative_integer(queue_ahead, 'queue_ahead')
        self.queue_ahead = queue_ahead

    def run(self, fixture_path: Path = DEFAULT_FIXTURE) -> dict:
        s = self.scenario
        # Read once so the digest and the replay refer to the same static tape.
        tape_bytes = Path(fixture_path).read_bytes()
        rows = _parse_trade_prints(tape_bytes.decode('utf-8'), s.contract_id)
        return self._run_rows(rows, hashlib.sha256(tape_bytes).hexdigest(),
                              'synthetic static historical test vector')

    def run_authentic(self, tape_path: Path = DEFAULT_TAPE, *,
                      contract_id: str | None = None, auto_scenario: bool = False) -> dict:
        """Validate the entire tape before selecting one contract for replay."""
        tape_bytes = Path(tape_path).read_bytes()
        digest = hashlib.sha256(tape_bytes).hexdigest()
        prints = parse_authentic_polymarket_tape(tape_bytes)
        parsed_count = len(prints)
        if self.explicit_scenario:
            if contract_id is not None and contract_id != self.scenario.contract_id:
                raise ValueError('contract selection contradicts explicit scenario')
            contract_id = self.scenario.contract_id
        elif auto_scenario and contract_id is None:
            contract_id = primary_contract_id(prints)
        if contract_id is not None:
            prints = [trade for trade in prints if trade.contract_id == contract_id]
        contract_selected_count = len(prints)
        asset_id = None
        if auto_scenario and not self.explicit_scenario and prints:
            asset_id = prints[0].asset_id
            prints = [trade for trade in prints if trade.asset_id == asset_id]
        harness = self
        selected_count = len(prints)
        initialization_count = 0
        generated = auto_scenario and not self.explicit_scenario and bool(prints)
        if not prints:
            result = self._authentic_abstention(0, digest, 'NO_MATCHING_CONTRACT_PRINTS')
        else:
            if generated:
                harness = WalkForwardReplayHarness(build_auto_scenario(prints),
                                                   strategy_d=True, queue_ahead=5)
                prints = [trade for trade in prints if trade.timestamp_ns > harness.scenario.decision_at_ns]
                initialization_count = selected_count - len(prints)
            result = harness.run_prints(prints, digest) if prints else harness._authentic_abstention(
                0, digest, 'NO_POST_DECISION_PRINTS')
        result.update({
            'contract_id': contract_id,
            'asset_id': asset_id,
            'raw_trade_record_count': len(json.loads(tape_bytes)),
            'parsed_trade_print_count': parsed_count,
            'selected_trade_print_count': selected_count,
            'contract_selected_trade_print_count': contract_selected_count,
            'initialization_trade_print_count': initialization_count,
            'excluded_trade_print_count': parsed_count - selected_count,
        })
        if generated:
            result.update({
                'scenario_source': 'AUTO_SCENARIO_SIMULATION',
                'scenario': asdict(harness.scenario),
                'pricing_source': 'INITIAL_PRINT_ASSUMED_SPREAD',
                'execution_policy': 'STRATEGY_D_SELL_AT_OR_BELOW_LIMIT',
                'queue_ahead_assumption': 5,
                'model_source': 'FIXED_SYNTHETIC_LOG_NORMAL_INPUTS',
                'settlement_source': 'ASSUMED_WIN',
                'pnl_basis': 'SIMULATED_SETTLEMENT',
                'lookahead_disclosure': 'Contract selection and expiry bounds use full-capture '
                                        'metadata. The first timestamp seeds the quote and is '
                                        'excluded from execution; later prices do not change it.',
            })
        return result

    def _authentic_abstention(self, count: int, digest: str, detail: str) -> dict:
        return {
            'status': 'ABSTAINED', 'reason': 'ABSTAINED', 'abstention_detail': detail,
            'trade_print_count': count, 'p_fair': None, 'net_edge': None,
            'limit_price_cents': None, 'posted_quantity': 0,
            'initial_q_ahead': 0, 'remaining_q_ahead': 0,
            'unfilled_quantity': 0, 'filled_quantity': 0, 'fills': [],
            'deployed_cents': 0, 'fee_cents': 0, 'payout_cents': 0, 'net_pnl_cents': 0,
            'waterfall': SettlementEngine().calculate_waterfall_split(0),
            'initial_capital_cents': self.scenario.initial_capital_cents,
            'final_capital_cents': self.scenario.initial_capital_cents,
            'fixture_sha256': digest, 'data_provenance': 'captured Polymarket raw trade tape',
        }

    def run_prints(self, prints: list[MarketTradePrint], fixture_sha256: str) -> dict:
        """Replay normalized prints with explicitly supplied independent inputs.

        Raw trade feeds alone cannot establish fair probability, visible queue,
        or settlement. Without a scenario the audited result is an abstention.
        """
        if not prints:
            raise ValueError('empty trade tape')
        seen = set()
        previous = (-1, '')
        for trade in prints:
            if not isinstance(trade, MarketTradePrint):
                raise ValueError('expected MarketTradePrint')
            key = (trade.timestamp_ns, trade.trade_id)
            for name in ('timestamp_ns', 'price_cents', 'volume'):
                nonnegative_integer(getattr(trade, name), name)
            if (not trade.trade_id or trade.trade_id in seen or key <= previous or
                    not trade.contract_id or not trade.contract_spec or
                    trade.price_cents > 100 or trade.volume == 0 or
                    trade.aggressor_side not in ('BUY', 'SELL')):
                raise ValueError('invalid or duplicate trade print')
            seen.add(trade.trade_id)
            previous = key
        if not self.explicit_scenario:
            return self._authentic_abstention(len(prints), fixture_sha256,
                                              'MISSING_INDEPENDENT_REPLAY_SCENARIO')
        if any(trade.contract_id != self.scenario.contract_id for trade in prints):
            raise ValueError('unexpected contract in authentic replay')
        result = self._run_rows([asdict(trade) for trade in prints], fixture_sha256,
                                'captured Polymarket raw trade tape')
        if result['reason'] != 'ADMITTED':
            result['abstention_detail'] = result['reason']
            result['reason'] = 'ABSTAINED'
        return result

    def _run_rows(self, rows, fixture_sha256: str, provenance: str) -> dict:
        s = self.scenario
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
        q_ahead = s.bid_depth.get(limit, 0) if self.queue_ahead is None else self.queue_ahead
        tracker = MicrostructureQueueTracker(limit, quantity, q_ahead,
                                              allow_price_through=self.strategy_d)
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
            'initial_q_ahead': q_ahead, 'remaining_q_ahead': tracker.q_ahead,
            'unfilled_quantity': tracker.remaining_quantity, 'filled_quantity': filled_quantity,
            'fills': fills, 'deployed_cents': deployed, 'fee_cents': fees,
            'payout_cents': payout, 'net_pnl_cents': pnl, 'waterfall': waterfall,
            'initial_capital_cents': s.initial_capital_cents,
            'final_capital_cents': s.initial_capital_cents + pnl,
            'fixture_sha256': fixture_sha256,
            'data_provenance': provenance,
        }
