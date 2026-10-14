from dataclasses import replace
from decimal import Decimal
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys

import pytest

from app.domain.microstructure_queue_tracker import MicrostructureQueueTracker
from app.domain.walk_forward_replay_harness import (
    DEFAULT_FIXTURE, ReplayScenario, WalkForwardReplayHarness,
    black_scholes_probability, load_trade_prints,
)


def test_fixture_is_frozen_chronological_and_replay_is_deterministic():
    assert hashlib.sha256(DEFAULT_FIXTURE.read_bytes()).hexdigest() == 'bc43fc32bb4ce91f16f3900d9de46ae1c38e2d0f1faa9f94212e657b1ae03370'
    rows = load_trade_prints()
    assert len(rows) == 100
    assert all(a['timestamp_ns'] < b['timestamp_ns'] for a, b in zip(rows, rows[1:]))
    a = WalkForwardReplayHarness().run()
    assert a == WalkForwardReplayHarness().run()
    assert a['filled_quantity'] == 10
    assert a['deployed_cents'] == 460
    assert a['payout_cents'] == 1000
    assert a['final_capital_cents'] == 10540
    assert a['waterfall'] == {'scma_cents': 469, 'cfcp_cents': 55, 'faep_cents': 16}
    assert sum(a['waterfall'].values()) == a['net_pnl_cents']


def test_log_normal_probability_uses_d2_and_is_independent_of_quotes():
    assert black_scholes_probability(math.exp(0.5 * 0.2**2), 1, .2, 1) == pytest.approx(.5)
    assert black_scholes_probability(100, 100, .2, 1) == pytest.approx(.460172162722971)
    base = ReplayScenario()
    a = WalkForwardReplayHarness(base).run()
    b = WalkForwardReplayHarness(replace(base, best_bid_cents=60, best_ask_cents=64, bid_depth={60: 20})).run()
    assert a['p_fair'] == b['p_fair']
    assert b['status'] == 'ABSTAINED'
    assert b['deployed_cents'] == b['fee_cents'] == b['payout_cents'] == 0


def test_gate_exact_boundary_and_friction(monkeypatch):
    import app.domain.walk_forward_replay_harness as module
    for probability, fee, admitted in ((.489999, 0, False), (.49, 0, True), (.49, 1, False)):
        monkeypatch.setattr(module, 'black_scholes_probability', lambda *args: probability)
        result = WalkForwardReplayHarness(replace(ReplayScenario(), fee_cents_per_contract=fee)).run()
        assert (result['posted_quantity'] > 0) == admitted
        if not admitted:
            assert result['deployed_cents'] == result['net_pnl_cents'] == 0
        else:
            assert Decimal(result['net_edge']) == Decimal('.03')


def test_fifo_queue_exhaustion_partial_fills_and_wrong_side():
    tracker = MicrostructureQueueTracker(46, 5, 7)
    assert tracker.process_trade(price_cents=46, volume=100, aggressor_side='BUY') == 0
    assert tracker.process_trade(price_cents=45, volume=100, aggressor_side='SELL') == 0
    assert tracker.process_trade(price_cents=47, volume=100, aggressor_side='SELL') == 0
    assert tracker.q_ahead == 7
    assert tracker.process_trade(price_cents=46, volume=7, aggressor_side='SELL') == 0
    assert tracker.q_ahead == 0
    assert tracker.process_trade(price_cents=46, volume=2, aggressor_side='SELL') == 2
    assert tracker.remaining_quantity == 3
    assert tracker.process_trade(price_cents=46, volume=100, aggressor_side='SELL') == 3
    assert tracker.process_trade(price_cents=46, volume=100, aggressor_side='SELL') == 0


def test_no_same_tick_execution_and_no_settlement_lookahead():
    s = ReplayScenario()
    winning = WalkForwardReplayHarness(s).run()
    losing = WalkForwardReplayHarness(replace(s, settlement_spot=99000)).run()
    assert winning['fills'] == losing['fills']
    assert winning['p_fair'] == losing['p_fair']
    assert all(fill['timestamp_ns'] > s.decision_at_ns for fill in winning['fills'])
    assert losing['net_pnl_cents'] == -460
    assert losing['waterfall'] == {'scma_cents': -460, 'cfcp_cents': 0, 'faep_cents': 0}
    assert losing['final_capital_cents'] == 9540


def test_partial_unfilled_capacity_and_fee_accounting():
    s = replace(ReplayScenario(), initial_capital_cents=47, fee_cents_per_contract=1, spot=102000)
    result = WalkForwardReplayHarness(s).run()
    assert result['posted_quantity'] == result['filled_quantity'] == 1
    assert result['deployed_cents'] == 46
    assert result['fee_cents'] == 1
    assert result['final_capital_cents'] == 100
    empty = WalkForwardReplayHarness(replace(s, initial_capital_cents=0)).run()
    assert empty['deployed_cents'] == 0
    large = WalkForwardReplayHarness(replace(s, quantity=10000, initial_capital_cents=100000)).run()
    assert large['unfilled_quantity'] > 0
    assert large['filled_quantity'] < large['posted_quantity']


@pytest.mark.parametrize('changes', [
    {'observed_at_ns': 1735689599000000000},
    {'decision_at_ns': 1735689600000000000},
    {'expiry_ns': 1735695540000000000},
    {'best_ask_cents': 45}, {'bid_depth': {46: 1}}, {'quantity': 1.5},
    {'fee_cents_per_contract': -1}, {'spot': float('nan')}, {'volatility': -1},
    {'settlement_spot': float('nan')},
])
def test_invalid_scenario_fails_closed(changes):
    with pytest.raises(ValueError):
        WalkForwardReplayHarness(replace(ReplayScenario(), **changes)).run()


@pytest.mark.parametrize('mutation', ['duplicate', 'reverse', 'wrong_contract', 'fractional', 'side', 'missing'])
def test_bad_tape_is_rejected(tmp_path, mutation):
    rows = list(load_trade_prints())
    if mutation == 'duplicate':
        rows[1]['trade_id'] = rows[0]['trade_id']
    elif mutation == 'reverse':
        rows.reverse()
    elif mutation == 'wrong_contract':
        rows[0]['contract_id'] = 'OTHER'
    elif mutation == 'fractional':
        rows[0]['price_cents'] = 46.5
    elif mutation == 'side':
        rows[0]['aggressor_side'] = 'UNKNOWN'
    else:
        del rows[0]['volume']
    path = tmp_path / 'bad.jsonl'
    path.write_text('\n'.join(json.dumps(row) for row in rows))
    with pytest.raises(ValueError):
        WalkForwardReplayHarness().run(path)


def test_no_inside_spread_and_no_eligible_prints(tmp_path):
    s = ReplayScenario()
    tight = WalkForwardReplayHarness(replace(s, best_ask_cents=46)).run()
    assert tight['status'] == 'ABSTAINED'
    assert tight['deployed_cents'] == 0
    rows = list(load_trade_prints())
    for row in rows:
        row['aggressor_side'] = 'BUY'
    path = tmp_path / 'no_sellers.jsonl'
    path.write_text('\n'.join(json.dumps(row) for row in rows))
    result = WalkForwardReplayHarness().run(path)
    assert result['posted_quantity'] == result['unfilled_quantity'] == 10
    assert result['deployed_cents'] == result['payout_cents'] == 0


def test_stdlib_imports_from_domain_directory_and_runner(tmp_path):
    backend = Path(__file__).resolve().parents[1]
    env = dict(os.environ, PYTHONPATH=str(backend / 'app/domain'))
    subprocess.run([sys.executable, '-c', 'import operator, dataclasses, collections; assert operator.add(2, 3) == 5'],
                   cwd=backend / 'app/domain', env=env, check=True, timeout=10)
    result = subprocess.run([sys.executable, str(backend / 'run_walk_forward_replay.py')],
                            cwd=tmp_path, capture_output=True, text=True, check=True, timeout=10)
    assert json.loads(result.stdout)['trade_print_count'] == 100
