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
from app.adapters.authentic_tape_router import DEFAULT_TAPES, parse_venue_tape, raw_record_count
from app.adapters.authentic_weather_tape_loader import WeatherReplayScenario, WeatherTape

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


@dataclass(frozen=True)
class IndependentReplayScenario:
    """External fair value and binary settlement for non-crypto contracts."""
    contract_id: str
    observed_at_ns: int
    decision_at_ns: int
    expiry_ns: int
    fair_probability: float
    settlement_payout_cents: int
    best_bid_cents: int = 45
    best_ask_cents: int = 49
    bid_depth: dict[int, int] = field(default_factory=lambda: {45: 5})
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
    def __init__(self, scenario: ReplayScenario | IndependentReplayScenario | WeatherReplayScenario | None = None, *,
                 strategy_d: bool = False, queue_ahead: int | None = None):
        self.explicit_scenario = scenario is not None
        self.scenario = scenario or ReplayScenario()
        if type(strategy_d) is not bool:
            raise ValueError('strategy_d must be a boolean')
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

    def run_authentic(self, tape_path: Path | None = None, *, venue: str = 'polymarket',
                      contract_id: str | None = None, auto_scenario: bool = False) -> dict:
        """Validate the entire tape before selecting one contract for replay."""
        if venue not in DEFAULT_TAPES:
            raise ValueError(f'unsupported replay venue: {venue}')
        tape_bytes = Path(tape_path if tape_path is not None else DEFAULT_TAPES[venue]).read_bytes()
        digest = hashlib.sha256(tape_bytes).hexdigest()
        prints = parse_venue_tape(tape_bytes, venue)
        if isinstance(prints, WeatherTape):
            return self._run_weather(prints, digest, contract_id)
        if venue == 'kalshi' and self.explicit_scenario and not isinstance(self.scenario, IndependentReplayScenario):
            raise ValueError('Kalshi requires an IndependentReplayScenario')
        auto_scenario = auto_scenario and venue == 'polymarket'
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
            if venue == 'kalshi' and self.explicit_scenario:
                harness = WalkForwardReplayHarness(self.scenario, strategy_d=True, queue_ahead=self.queue_ahead)
            result = harness.run_prints(prints, digest, venue=venue) if prints else harness._authentic_abstention(
                0, digest, 'NO_POST_DECISION_PRINTS')
        result.update({
            'contract_id': contract_id,
            'venue': venue,
            'data_provenance': f'captured {venue} raw trade tape',
            'asset_id': asset_id,
            'raw_trade_record_count': raw_record_count(tape_bytes, venue),
            'parsed_trade_print_count': parsed_count,
            'replayed_trade_print_count': len(prints) if harness.explicit_scenario else 0,
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

    def _run_weather(self, tape: WeatherTape, digest: str, contract_id: str | None) -> dict:
        """Evaluate observations through expiry without synthesizing executions."""
        result = self._authentic_abstention(0, digest, 'MISSING_INDEPENDENT_REPLAY_SCENARIO')
        result.update({
            'venue': 'weather', 'contract_id': contract_id,
            'data_provenance': 'NOAA ASOS surface observations and strike ladder',
            'raw_trade_record_count': len(tape.execution_prints),
            'parsed_trade_print_count': len(tape.execution_prints),
            'replayed_trade_print_count': 0,
            'excluded_trade_print_count': len(tape.execution_prints), 'initialization_trade_print_count': 0,
            'selected_trade_print_count': 0, 'parsed_observation_count': len(tape.observations),
            'raw_observation_count': len(tape.observations),
        })
        if not self.explicit_scenario:
            return result
        s = self.scenario
        if not isinstance(s, WeatherReplayScenario):
            raise ValueError('weather requires a WeatherReplayScenario')
        if contract_id is not None and contract_id != s.contract_id:
            raise ValueError('contract selection contradicts weather scenario')
        for name in ('observed_at_ns', 'decision_at_ns', 'expiry_ns', 'initial_capital_cents'):
            nonnegative_integer(getattr(s, name), name)
        if not s.observed_at_ns < s.decision_at_ns < s.expiry_ns:
            raise ValueError('invalid weather scenario time bounds')
        result['contract_id'] = s.contract_id
        bracket = next((strike for strike in tape.strike_ladder if strike.contract_id == s.contract_id), None)
        if bracket is None:
            result['abstention_detail'] = 'NO_MATCHING_STRIKE_BRACKET'
            return result
        if bracket.station_id != s.station_id or bracket.expiry_ns != s.expiry_ns:
            raise ValueError('weather scenario contradicts station or expiry barrier')
        station = [tick for tick in tape.observations if tick.station_id == s.station_id]
        if not station:
            result['abstention_detail'] = 'NO_MATCHING_STATION_OBSERVATIONS'
            return result
        eligible = [tick for tick in station if tick.timestamp_ns <= s.expiry_ns and tick.available_at_ns <= s.expiry_ns]
        latest = eligible[-1] if eligible else None
        result['abstention_detail'] = 'NO_EXECUTION_TAPE'
        result['weather_evaluation'] = {
            'station_id': s.station_id, 'expiry_ns': s.expiry_ns,
            'lower_f': str(bracket.lower_f) if bracket.lower_f is not None else None,
            'upper_f': str(bracket.upper_f) if bracket.upper_f is not None else None,
            'pre_decision_observation_count': sum(tick.available_at_ns <= s.decision_at_ns for tick in eligible),
            'replay_observation_count': sum(tick.available_at_ns > s.decision_at_ns for tick in eligible),
            'post_expiry_excluded_count': len(station) - len(eligible),
            'other_station_excluded_count': len(tape.observations) - len(station),
            'last_observation_ns': latest.timestamp_ns if latest else None,
            'last_observed_temperature_f': str(latest.temperature_f) if latest else None,
            'last_observation_in_bracket': bracket.contains(latest.temperature_f) if latest else None,
            'settlement_verified': False,
        }
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

    def run_prints(self, prints: list[MarketTradePrint], fixture_sha256: str, *, venue: str = 'polymarket') -> dict:
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
                                f'captured {venue} raw trade tape')
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
        if isinstance(s, IndependentReplayScenario):
            nonnegative_integer(s.settlement_payout_cents, 'settlement_payout_cents')
            if s.settlement_payout_cents not in (0, 100):
                raise ValueError('binary settlement payout must be 0 or 100 cents')
            if (type(s.fair_probability) not in (int, float) or not 0 <= s.fair_probability <= 1
                    or not math.isfinite(s.fair_probability)):
                raise ValueError('invalid independent fair probability')
        elif not math.isfinite(s.settlement_spot) or s.settlement_spot <= 0:
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
        p_fair = s.fair_probability if isinstance(s, IndependentReplayScenario) else black_scholes_probability(
            s.spot, s.strike, s.volatility, (s.expiry_ns - s.decision_at_ns) / YEAR_NS, s.rate)
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
        payout_per_contract = s.settlement_payout_cents if isinstance(s, IndependentReplayScenario) else (
            100 if s.settlement_spot >= s.strike else 0)
        payout = filled_quantity * payout_per_contract
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
