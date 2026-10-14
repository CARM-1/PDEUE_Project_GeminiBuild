from dataclasses import asdict, replace
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from app.adapters.authentic_polymarket_tape_loader import (
    DEFAULT_TAPE, MarketTradePrint, load_authentic_polymarket_tape,
)
from app.domain.walk_forward_replay_harness import (
    ReplayScenario, WalkForwardReplayHarness, build_auto_scenario, load_trade_prints,
    primary_contract_id,
)


def raw_trade(**changes):
    return {**dict(transactionHash='hash-a', conditionId=ReplayScenario().contract_id,
                   price=.46, size=10.9, timestamp=1735689600, side='SELL',
                   title='Bitcoin above $100,000?'), **changes}


def write_tape(tmp_path, rows):
    path = tmp_path / 'raw_trades_test.json'
    path.write_text(json.dumps(rows))
    return path


def test_descending_tape_and_same_second_ties_sort_ascending(tmp_path):
    path = write_tape(tmp_path, [raw_trade(transactionHash='hash-c', timestamp=1735689602),
                                 raw_trade(transactionHash='hash-b'), raw_trade()])
    prints = load_authentic_polymarket_tape(path)
    assert all(isinstance(trade, MarketTradePrint) for trade in prints)
    assert [trade.trade_id for trade in prints] == ['hash-a', 'hash-b', 'hash-c']
    assert prints[0].timestamp_ns == 1735689600 * 1_000_000_000
    assert all((a.timestamp_ns, a.trade_id) < (b.timestamp_ns, b.trade_id)
               for a, b in zip(prints, prints[1:]))
    assert prints[0].contract_spec == 'Bitcoin above $100,000?'


@pytest.mark.parametrize('price,expected', [(0, 0), (.005, 0), (.015, 2), (.465, 46), (.467, 47), (1, 100)])
def test_integer_cent_rounding_and_lot_flooring(tmp_path, price, expected):
    path = write_tape(tmp_path, [raw_trade(price=price, size='3.99'),
                                 raw_trade(transactionHash='dust', size=.99),
                                 raw_trade(transactionHash='negative', size=-1)])
    prints = load_authentic_polymarket_tape(path)
    assert len(prints) == 1
    assert prints[0].price_cents == expected
    assert prints[0].volume == 3
    assert type(prints[0].price_cents) is type(prints[0].volume) is int


def test_asset_fallback_and_numeric_strings(tmp_path):
    row = raw_trade(price='0.46', size='10.9', timestamp='1735689600')
    del row['conditionId']
    row['asset'] = 'asset-id'
    assert load_authentic_polymarket_tape(write_tape(tmp_path, [row]))[0].contract_id == 'asset-id'


@pytest.mark.parametrize('field', ['transactionHash', 'conditionId', 'price', 'size', 'timestamp', 'side', 'title'])
def test_missing_fields_fail_closed(tmp_path, field):
    row = raw_trade()
    del row[field]
    with pytest.raises(ValueError):
        load_authentic_polymarket_tape(write_tape(tmp_path, [row]))


@pytest.mark.parametrize('changes', [
    {'price': -.001}, {'price': 1.01}, {'price': float('nan')}, {'price': True},
    {'size': float('inf')}, {'size': None}, {'timestamp': -1},
    {'timestamp': 1735689600.5}, {'timestamp': True}, {'side': 'UNKNOWN'},
    {'title': ''}, {'transactionHash': ''},
])
def test_bad_records_fail_closed(tmp_path, changes):
    with pytest.raises(ValueError):
        load_authentic_polymarket_tape(write_tape(tmp_path, [raw_trade(**changes)]))


@pytest.mark.parametrize('size', [10, .1])
def test_duplicate_hashes_rejected_even_for_discarded_lots(tmp_path, size):
    with pytest.raises(ValueError, match='duplicate'):
        load_authentic_polymarket_tape(write_tape(tmp_path, [raw_trade(), raw_trade(size=size)]))


@pytest.mark.parametrize('rows', [[], {}, [None], [raw_trade(size=0)]])
def test_empty_or_invalid_arrays_rejected(tmp_path, rows):
    with pytest.raises(ValueError):
        load_authentic_polymarket_tape(write_tape(tmp_path, rows))


def test_replay_matches_static_execution_and_conserves_cents(tmp_path):
    # Synthetic raw-format qualification vector, explicitly not a venue capture.
    rows = [raw_trade(transactionHash=row['trade_id'], price=row['price_cents'] / 100,
                      size=row['volume'], timestamp=row['timestamp_ns'] // 1_000_000_000,
                      side=row['aggressor_side']) for row in load_trade_prints()]
    path = write_tape(tmp_path, rows[::-1])
    s = ReplayScenario()
    result = WalkForwardReplayHarness(s).run_authentic(path)
    static = WalkForwardReplayHarness(s).run()
    for field in ('fills', 'deployed_cents', 'net_pnl_cents', 'waterfall', 'p_fair', 'net_edge'):
        assert result[field] == static[field]
    assert result['reason'] == 'ADMITTED'
    assert result['fixture_sha256'] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert result['waterfall'] == {'scma_cents': 469, 'cfcp_cents': 55, 'faep_cents': 16}
    assert sum(result['waterfall'].values()) == result['net_pnl_cents']
    losing = WalkForwardReplayHarness(replace(s, settlement_spot=99000)).run_authentic(path)
    assert losing['fills'] == result['fills']
    assert losing['waterfall'] == {'scma_cents': -460, 'cfcp_cents': 0, 'faep_cents': 0}
    assert sum(losing['waterfall'].values()) == losing['net_pnl_cents']
    abstained = WalkForwardReplayHarness(replace(s, initial_capital_cents=0)).run_authentic(path)
    assert abstained['reason'] == 'ABSTAINED'
    assert abstained['net_pnl_cents'] == 0


def test_authentic_cli_abstains_without_independent_inputs(tmp_path):
    path = write_tape(tmp_path, [raw_trade()])
    backend = Path(__file__).resolve().parents[1]
    completed = subprocess.run(
        [sys.executable, str(backend / 'run_walk_forward_replay.py'), '--mode=authentic', f'--tape={path}'],
        cwd=tmp_path, env=dict(os.environ, PYTHONPATH=str(backend)),
        check=True, capture_output=True, text=True, timeout=10,
    )
    result = json.loads(completed.stdout)
    assert result['reason'] == 'ABSTAINED'
    assert result['abstention_detail'] == 'MISSING_INDEPENDENT_REPLAY_SCENARIO'
    assert result['trade_print_count'] == 1
    assert result['p_fair'] is result['net_edge'] is None
    assert result['fills'] == []
    assert result['deployed_cents'] == result['net_pnl_cents'] == 0
    assert sum(result['waterfall'].values()) == result['net_pnl_cents']


def test_replay_rejects_wrong_contract_and_nonmonotonic_prints(tmp_path):
    prints = load_authentic_polymarket_tape(write_tape(tmp_path, [raw_trade(), raw_trade(transactionHash='hash-b')]))
    with pytest.raises(ValueError):
        WalkForwardReplayHarness(ReplayScenario()).run_prints(prints[::-1], 'digest')
    with pytest.raises(ValueError):
        WalkForwardReplayHarness(replace(ReplayScenario(), contract_id='OTHER')).run_prints(prints, 'digest')
    with pytest.raises(ValueError):
        WalkForwardReplayHarness().run_prints([prints[0], prints[0]], 'digest')


def test_authentic_cli_with_explicit_scenario(tmp_path):
    path = write_tape(tmp_path, [raw_trade()])
    scenario = tmp_path / 'scenario.json'
    scenario.write_text(json.dumps(asdict(ReplayScenario())))
    backend = Path(__file__).resolve().parents[1]
    command = [sys.executable, str(backend / 'run_walk_forward_replay.py'),
               '--mode=authentic', f'--tape={path}', f'--scenario={scenario}']
    completed = subprocess.run(command, cwd=tmp_path, check=True, capture_output=True, text=True, timeout=10)
    result = json.loads(completed.stdout)
    assert result['reason'] == 'ADMITTED'
    assert result['filled_quantity'] == 10
    assert sum(result['waterfall'].values()) == result['net_pnl_cents']
    scenario.write_text(json.dumps({'contract_id': ReplayScenario().contract_id}))
    incomplete = subprocess.run(command, cwd=tmp_path, capture_output=True, text=True, timeout=10)
    assert incomplete.returncode != 0
    assert 'complete ReplayScenario' in incomplete.stderr


def test_captured_default_tape_end_to_end():
    if not DEFAULT_TAPE.is_file():
        pytest.skip(f'captured tape not supplied: {DEFAULT_TAPE}')
    prints = load_authentic_polymarket_tape(DEFAULT_TAPE)
    result = WalkForwardReplayHarness().run_authentic(DEFAULT_TAPE)
    assert result['trade_print_count'] == len(prints) > 0
    assert result['fixture_sha256'] == hashlib.sha256(DEFAULT_TAPE.read_bytes()).hexdigest()
    assert result['reason'] == 'ABSTAINED'
    split = result['waterfall']
    assert split['scma_cents'] + split['cfcp_cents'] + split['faep_cents'] == result['net_pnl_cents']


def test_authentic_filters_before_execution_and_hashes_entire_tape(tmp_path):
    path = write_tape(tmp_path, [raw_trade(transactionHash='foreign', conditionId='OTHER', size=999),
                                 raw_trade()])
    result = WalkForwardReplayHarness(ReplayScenario()).run_authentic(path)
    assert result['trade_print_count'] == 1
    assert result['parsed_trade_print_count'] == result['raw_trade_record_count'] == 2
    assert result['excluded_trade_print_count'] == 1
    assert result['filled_quantity'] == 10
    assert [fill['trade_id'] for fill in result['fills']] == ['hash-a']
    assert result['fixture_sha256'] == hashlib.sha256(path.read_bytes()).hexdigest()


def test_no_matching_contract_returns_full_audited_abstention(tmp_path):
    path = write_tape(tmp_path, [raw_trade(conditionId='OTHER')])
    result = WalkForwardReplayHarness(ReplayScenario()).run_authentic(path)
    assert result['status'] == result['reason'] == 'ABSTAINED'
    assert result['abstention_detail'] == 'NO_MATCHING_CONTRACT_PRINTS'
    assert result['trade_print_count'] == 0
    assert result['parsed_trade_print_count'] == result['excluded_trade_print_count'] == 1
    assert result['fills'] == []
    assert result['deployed_cents'] == result['net_pnl_cents'] == 0
    assert result['p_fair'] is result['net_edge'] is None
    assert result['final_capital_cents'] == result['initial_capital_cents']
    assert sum(result['waterfall'].values()) == result['net_pnl_cents']
    assert result['fixture_sha256'] == hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize('foreign', [raw_trade(conditionId='OTHER', price=-1),
                                     raw_trade(conditionId='OTHER')])
def test_corrupt_foreign_records_are_rejected_before_filtering(tmp_path, foreign):
    path = write_tape(tmp_path, [raw_trade(), foreign])
    with pytest.raises(ValueError):
        WalkForwardReplayHarness(ReplayScenario()).run_authentic(path)


def test_auto_scenario_primary_selection_time_bounds_and_fixed_quotes(tmp_path):
    path = write_tape(tmp_path, [raw_trade(conditionId='z', transactionHash='z'),
                                 raw_trade(conditionId='a', transactionHash='a'),
                                 raw_trade(conditionId='z', transactionHash='z2', timestamp=1735689605)])
    prints = load_authentic_polymarket_tape(path)
    assert primary_contract_id(prints) == 'z'
    result = WalkForwardReplayHarness().run_authentic(path, auto_scenario=True)
    assert result['contract_id'] == 'z'
    assert result['trade_print_count'] == 2
    assert result['excluded_trade_print_count'] == 1
    assert result['reason'] == 'ADMITTED'
    assert result['scenario_source'] == 'AUTO_SCENARIO_SIMULATION'
    assert result['pnl_basis'] == 'SIMULATED_SETTLEMENT'
    s = result['scenario']
    assert s['observed_at_ns'] == 1735689600 * 1_000_000_000 - 2_000_000_000
    assert s['decision_at_ns'] == 1735689600 * 1_000_000_000 - 1_000_000_000
    assert s['expiry_ns'] == 1735689605 * 1_000_000_000 + 300_000_000_000
    assert (s['best_bid_cents'], s['best_ask_cents']) == (1, 99)
    changed = [replace(trade, price_cents=99, volume=999) for trade in prints if trade.contract_id == 'z']
    assert asdict(build_auto_scenario(changed)) == s
    assert primary_contract_id(prints[:2]) == 'a'


def test_auto_scenario_does_not_mutate_original_harness(tmp_path):
    path = write_tape(tmp_path, [raw_trade()])
    harness = WalkForwardReplayHarness()
    assert harness.run_authentic(path, auto_scenario=True)['reason'] == 'ADMITTED'
    assert harness.run_authentic(path)['abstention_detail'] == 'MISSING_INDEPENDENT_REPLAY_SCENARIO'


@pytest.mark.parametrize('prints', [[], [MarketTradePrint('a', 'c', 2, 1, 1, 'SELL', 'title')]])
def test_auto_scenario_invalid_time_bounds_fail_closed(prints):
    with pytest.raises(ValueError):
        build_auto_scenario(prints)


def test_cli_auto_contract_override_missing_selection_and_explicit_precedence(tmp_path):
    path = write_tape(tmp_path, [raw_trade(), raw_trade(transactionHash='b', conditionId='OTHER'),
                                 raw_trade(transactionHash='c', conditionId='OTHER')])
    backend = Path(__file__).resolve().parents[1]
    command = [sys.executable, str(backend / 'run_walk_forward_replay.py'),
               '--mode=authentic', f'--tape={path}', '--auto-scenario']
    def run(*options):
        return subprocess.run(command + list(options), cwd=tmp_path, capture_output=True,
                              text=True, timeout=10)
    automatic = run()
    assert automatic.returncode == 0
    assert json.loads(automatic.stdout)['contract_id'] == 'OTHER'
    selected = json.loads(run(f'--contract-id={ReplayScenario().contract_id}').stdout)
    assert selected['trade_print_count'] == 1
    assert selected['reason'] == 'ADMITTED'
    missing = json.loads(run('--contract-id=MISSING').stdout)
    assert missing['abstention_detail'] == 'NO_MATCHING_CONTRACT_PRINTS'
    scenario = tmp_path / 'scenario.json'
    scenario.write_text(json.dumps(asdict(ReplayScenario())))
    explicit = json.loads(run(f'--scenario={scenario}').stdout)
    assert explicit['contract_id'] == ReplayScenario().contract_id
    assert explicit['limit_price_cents'] == 46
    assert 'scenario_source' not in explicit
    mismatch = run(f'--scenario={scenario}', '--contract-id=OTHER')
    assert mismatch.returncode != 0
    assert 'must match' in mismatch.stderr
