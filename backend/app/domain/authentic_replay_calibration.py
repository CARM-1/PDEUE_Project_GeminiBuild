"""Explicitly assumed offline maker scenarios, using only initial-time inputs.

Calibration is a simulation policy, not an estimator of fair value or settlement.
It never selects by future volume, sets expiry from the last print, or treats a
NOAA observation as exchange execution flow.
"""
from dataclasses import asdict
import hashlib
import json

from app.adapters.authentic_tape_router import parse_venue_tape, raw_record_count
from app.adapters.authentic_weather_tape_loader import WeatherReplayScenario, WeatherTape
from app.domain.microstructure_queue_tracker import nonnegative_integer
from app.domain.walk_forward_replay_harness import IndependentReplayScenario, WalkForwardReplayHarness

HORIZON_NS = 300_000_000_000
QUEUE_FLOOR = 5


def run_weather_with_execution(path, bounds, execution, queue_ahead=None):
    """Combine independent station bounds with an independent execution scenario."""
    result = WalkForwardReplayHarness(bounds).run_authentic(path, venue='weather')
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != result['fixture_sha256']:
        raise ValueError('weather capture changed during evaluation')
    tape = parse_venue_tape(content, 'weather')
    if 'weather_evaluation' not in result:
        raise ValueError('weather bounds did not qualify a station bracket')
    if any(getattr(bounds, field) != getattr(execution, field) for field in (
            'contract_id', 'observed_at_ns', 'decision_at_ns', 'expiry_ns', 'initial_capital_cents')):
        raise ValueError('weather and execution scenario bounds must match')
    selected = [p for p in tape.execution_prints if p.contract_id == execution.contract_id]
    if not selected:
        return result
    financial = WalkForwardReplayHarness(execution, strategy_d=True, queue_ahead=queue_ahead).run_prints(
        selected, result['fixture_sha256'], venue='weather')
    result.update(financial)
    result.pop('abstention_detail', None)
    if financial['reason'] == 'ABSTAINED':
        result['abstention_detail'] = financial['abstention_detail']
    result.update(raw_trade_record_count=len(tape.execution_prints),
                  parsed_trade_print_count=len(tape.execution_prints),
                  replayed_trade_print_count=len(selected), selected_trade_print_count=len(selected),
                  excluded_trade_print_count=len(tape.execution_prints) - len(selected))
    return result


def initial_scenario(prints, book=None, *, expiry_ns=None):
    """Select a contract/token at the first timestamp, with stable ID tie-breaks."""
    if not prints:
        raise ValueError('calibration requires execution prints')
    first_ns = prints[0].timestamp_ns
    if first_ns < 2_000_000_000:
        raise ValueError('invalid calibration initial timestamp')
    seed = min((p for p in prints if p.timestamp_ns == first_ns),
               key=lambda p: (p.contract_id, p.asset_id or '', p.trade_id))
    bid = max(1, min(97, seed.price_cents))
    ask, depth = bid + 2, 5
    if book is not None:
        if not isinstance(book, dict):
            raise ValueError('initial_book must be an object')
        nonnegative_integer(book.get('timestamp_ns'), 'book timestamp_ns')
        if book['timestamp_ns'] > first_ns or book.get('contract_id') != seed.contract_id:
            raise ValueError('initial book is future-dated or mismatches selected contract')
        if seed.asset_id is not None and book.get('asset_id') != seed.asset_id:
            raise ValueError('initial book mismatches selected outcome token')
        for side in ('bids', 'asks'):
            levels = book.get(side)
            if not isinstance(levels, list) or not levels:
                raise ValueError('initial book requires nonempty bids and asks')
            seen = set()
            for level in levels:
                if not isinstance(level, list) or len(level) != 2:
                    raise ValueError('book levels must be [integer cents, integer lots]')
                price, quantity = level
                nonnegative_integer(price, 'book price')
                nonnegative_integer(quantity, 'book quantity')
                if not 0 < price < 100 or quantity == 0 or price in seen:
                    raise ValueError('invalid or duplicate book level')
                seen.add(price)
        bid, depth = max(book['bids'])
        ask = min(price for price, _ in book['asks'])
        if bid >= ask:
            raise ValueError('crossed initial book')
    scenario = IndependentReplayScenario(
        seed.contract_id, first_ns, first_ns + 1,
        first_ns + HORIZON_NS if expiry_ns is None else expiry_ns,
        # Fixed assumptions, independent of all future prices and temperatures.
        .99, 100, bid, ask, {bid: depth},
    )
    if scenario.expiry_ns <= scenario.decision_at_ns:
        raise ValueError('expiry must follow initial decision')
    return scenario, max(QUEUE_FLOOR, depth), seed.asset_id


def run_calibrated(path, venue):
    content = path.read_bytes()
    digest = hashlib.sha256(content).hexdigest()
    parsed = parse_venue_tape(content, venue)  # Validate ALL rows before filtering.
    payload = json.loads(content)
    weather = isinstance(parsed, WeatherTape)
    prints = list(parsed.execution_prints) if weather else parsed
    book = payload.get('initial_book') if isinstance(payload, dict) else None
    observation_result = None
    expiry = None
    if weather:
        first = min(parsed.observations, key=lambda tick: (tick.available_at_ns, tick.observation_id))
        if prints:
            seed_contract = min(p.contract_id for p in prints if p.timestamp_ns == prints[0].timestamp_ns)
            bracket = next(strike for strike in parsed.strike_ladder if strike.contract_id == seed_contract)
            if not any(tick.station_id == bracket.station_id and tick.available_at_ns <= prints[0].timestamp_ns
                       for tick in parsed.observations):
                raise ValueError('no station observation available at initial execution timestamp')
            initial_ns = prints[0].timestamp_ns
        else:
            brackets = [strike for strike in parsed.strike_ladder
                        if strike.station_id == first.station_id and strike.expiry_ns > first.available_at_ns + 1]
            if not brackets:
                raise ValueError('no matching unexpired weather strike')
            bracket, initial_ns = brackets[0], first.available_at_ns
        expiry = bracket.expiry_ns  # Predeclared contract terms, never end-of-tape.
        bounds = WeatherReplayScenario(bracket.contract_id, bracket.station_id,
                                       initial_ns, initial_ns + 1, expiry)
        observation_result = WalkForwardReplayHarness(bounds).run_authentic(path, venue='weather')
        if observation_result['fixture_sha256'] != digest:
            raise ValueError('weather capture changed during calibration')
        if not prints:
            observation_result.update(scenario_source='CALIBRATED_OBSERVATION_BOUNDS', scenario=asdict(bounds))
            return observation_result
    scenario, queue, asset = initial_scenario(prints, book, expiry_ns=expiry)
    selected = [p for p in prints if p.contract_id == scenario.contract_id and p.asset_id == asset]
    replay = [p for p in selected if scenario.decision_at_ns < p.timestamp_ns < scenario.expiry_ns]
    harness = WalkForwardReplayHarness(scenario, strategy_d=True, queue_ahead=queue)
    result = harness.run_prints(replay, digest, venue=venue) if replay else harness._authentic_abstention(
        0, digest, 'NO_POST_DECISION_PRINTS')
    if observation_result:
        result.update({key: observation_result[key] for key in (
            'weather_evaluation', 'parsed_observation_count', 'raw_observation_count')})
    initialization = sum(p.timestamp_ns <= scenario.decision_at_ns for p in selected)
    result.update(
        venue=venue, contract_id=scenario.contract_id, asset_id=asset,
        raw_trade_record_count=len(prints) if weather else raw_record_count(content, venue),
        parsed_trade_print_count=len(prints), replayed_trade_print_count=len(replay),
        selected_trade_print_count=len(selected),
        contract_selected_trade_print_count=sum(p.contract_id == scenario.contract_id for p in prints),
        initialization_trade_print_count=initialization,
        excluded_trade_print_count=len(prints) - len(selected),
        outside_horizon_trade_print_count=len(selected) - initialization - len(replay),
        scenario_source='CALIBRATED_SIMULATION', scenario=asdict(scenario),
        pricing_source='INITIAL_L2_SNAPSHOT' if book is not None else 'INITIAL_PRINT_ASSUMED_SPREAD',
        execution_policy='STRATEGY_D_SELL_AT_OR_BELOW_LIMIT', queue_ahead_assumption=queue,
        model_source='FIXED_ASSUMED_FAIR_PROBABILITY_0.99', settlement_source='ASSUMED_WIN',
        pnl_basis='SIMULATED_SETTLEMENT',
        lookahead_disclosure='Contract/token and quote use only initial-time evidence. '
                            'Expiry is initial timestamp + 300s, or predeclared weather strike expiry. '
                            'Initial-time and out-of-horizon prints cannot execute.',
    )
    if isinstance(payload, dict):
        result['fixture_provenance'] = payload.get('provenance', {'kind': 'UNVERIFIED'})
    return result
