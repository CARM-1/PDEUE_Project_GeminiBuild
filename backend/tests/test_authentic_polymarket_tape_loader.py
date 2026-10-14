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
    ReplayScenario, WalkForwardReplayHarness, load_trade_prints,
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
