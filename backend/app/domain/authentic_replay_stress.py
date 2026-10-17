"""Deterministic adverse execution simulations; historical records stay unchanged."""
from dataclasses import replace
import hashlib

from app.adapters.authentic_tape_router import parse_venue_tape
from app.adapters.authentic_weather_tape_loader import WeatherTape
from app.domain.authentic_replay_calibration import run_calibrated
from app.domain.walk_forward_replay_harness import IndependentReplayScenario, WalkForwardReplayHarness


def stress_capture(path, venue, *, scenario=None, queue_ahead=None):
    if scenario is None:
        baseline = run_calibrated(path, venue)
        if baseline.get('scenario_source') != 'CALIBRATED_SIMULATION':
            return {'status': 'NOT_APPLICABLE', 'reason': 'NO_EXCHANGE_EXECUTION_SCENARIO', 'cases': {}}
        scenario = IndependentReplayScenario(**baseline['scenario'])
        digest, queue = baseline['fixture_sha256'], baseline['queue_ahead_assumption']
        asset = baseline.get('asset_id')
        filter_asset = True
    elif isinstance(scenario, IndependentReplayScenario):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        queue = scenario.bid_depth.get(scenario.best_bid_cents + 1, 0) if queue_ahead is None else queue_ahead
        filter_asset, asset = False, None
    else:
        return {'status': 'NOT_APPLICABLE', 'reason': 'NO_INDEPENDENT_EXCHANGE_EXECUTION_SCENARIO', 'cases': {}}
    tape = parse_venue_tape(path.read_bytes(), venue)
    prints = list(tape.execution_prints) if isinstance(tape, WeatherTape) else tape
    selected = [p for p in prints if p.contract_id == scenario.contract_id
                and (not filter_asset or p.asset_id == asset)
                and scenario.decision_at_ns < p.timestamp_ns < scenario.expiry_ns]
    limit = scenario.best_bid_cents + 1
    barrier_prints = [p for p in selected if p.aggressor_side != 'SELL' or p.price_cents <= limit - 2]
    queue_exhaustion = 1 + sum(p.volume for p in selected
                               if p.aggressor_side == 'SELL' and p.price_cents <= limit)
    wide = replace(scenario, best_ask_cents=min(99, scenario.best_bid_cents + 12))
    # A fixed eight-cent spread limit is a risk barrier, not a reconstructed book.
    guarded = replace(wide, quantity=0) if wide.best_ask_cents - wide.best_bid_cents > 8 else wide
    cases = {}
    for name, assumed, flow, depth in (
        ('baseline', scenario, selected, queue),
        ('slippage_barrier_2c', scenario, barrier_prints, queue),
        ('wide_spread_12c_guard_8c', guarded, selected, queue),
        ('queue_depth_exhaustion', scenario, selected, max(queue, queue_exhaustion)),
        ('adverse_resolution_zero_payout', replace(scenario, settlement_payout_cents=0), selected, queue),
    ):
        result = WalkForwardReplayHarness(assumed, strategy_d=True, queue_ahead=depth).run_prints(
            flow, digest, venue=venue)
        result['fill_rate'] = result['filled_quantity'] / result['posted_quantity'] if result['posted_quantity'] else 0
        result['exact_cent_conservation'] = sum(result['waterfall'].values()) == result['net_pnl_cents']
        cases[name] = result
    return {'status': 'SIMULATED', 'cases': cases,
            'scope': 'Assumed initial-time scenarios, not observed venue profit. Queue exhaustion uses '
                     'full-horizon seller volume solely to construct an ex-post adversarial bound.'}
