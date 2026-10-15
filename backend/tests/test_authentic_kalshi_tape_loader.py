from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from app.adapters.authentic_kalshi_tape_loader import load_authentic_kalshi_tape, parse_authentic_kalshi_tape
from app.domain.walk_forward_replay_harness import IndependentReplayScenario, WalkForwardReplayHarness

BASE_NS = 1735689600 * 1_000_000_000


def trade(**changes):
    return {**dict(trade_id='a', ticker='KX-TEST-YES', yes_price_dollars='0.46',
                   count_fp='10.9', created_time='2025-01-01T00:00:00.123456789Z', taker_side='no'), **changes}


def tape(tmp_path, rows, wrapper='trades'):
    path = tmp_path / 'raw_trades_kalshi.json'
    path.write_text(json.dumps({wrapper: rows} if wrapper else rows))
    return path


def scenario(**changes):
    return replace(IndependentReplayScenario('KX-TEST-YES', BASE_NS - 2_000_000_000,
                    BASE_NS - 1_000_000_000, BASE_NS + 10_000_000_000, .7, 100), **changes)


def test_descending_rows_preserve_nanoseconds_timezone_and_tie_order(tmp_path):
    path = tape(tmp_path, [trade(trade_id='c', created_time='2025-01-01T00:00:00.123456790Z'),
                           trade(trade_id='b', created_time='2024-12-31T19:00:00.123456789-05:00'), trade()])
    prints = load_authentic_kalshi_tape(path)
    assert [p.trade_id for p in prints] == ['a', 'b', 'c']
    assert [p.timestamp_ns for p in prints] == [BASE_NS + 123456789, BASE_NS + 123456789, BASE_NS + 123456790]
    assert all((a.timestamp_ns, a.trade_id) < (b.timestamp_ns, b.trade_id) for a, b in zip(prints, prints[1:]))


@pytest.mark.parametrize('price,expected', [('0', 0), ('0.005', 0), ('0.015', 2), ('0.465', 46), ('0.475', 48), ('1', 100)])
def test_exact_cent_rounding_and_lot_flooring(tmp_path, price, expected):
    path = tape(tmp_path, [trade(yes_price_dollars=price, count_fp='3.999'),
                           trade(trade_id='dust', count_fp='.9'), trade(trade_id='zero', count_fp='0')])
    prints = load_authentic_kalshi_tape(path)
    assert len(prints) == 1
    assert prints[0].price_cents == expected
    assert prints[0].volume == 3
    assert type(prints[0].price_cents) is type(prints[0].volume) is int


@pytest.mark.parametrize('wrapper', ['fills', 'executions', None])
def test_private_execution_no_token_price_and_liquidity_role(tmp_path, wrapper):
    row = dict(fill_id='fill', market_ticker='KX-TEST-YES', no_price_dollars='.535', count='2.8',
               ts='1735689600.000000001', action='buy', side='no', is_taker=True)
    result = load_authentic_kalshi_tape(tape(tmp_path, [row], wrapper))[0]
    assert result.price_cents == 46
    assert result.aggressor_side == 'SELL'
    assert result.timestamp_ns == BASE_NS + 1
    row.update(side='yes', is_taker=False, no_price_dollars='.54')
    assert load_authentic_kalshi_tape(tape(tmp_path, [row], wrapper))[0].aggressor_side == 'SELL'


def test_legacy_cent_price_and_explicit_nanosecond_fields(tmp_path):
    row = trade(timestamp_ns=str(BASE_NS + 1), yes_price='46.5', count=4)
    del row['yes_price_dollars']
    del row['count_fp']
    print_record = load_authentic_kalshi_tape(tape(tmp_path, [row]))[0]
    assert print_record.price_cents == 46
    assert print_record.timestamp_ns == BASE_NS + 1


@pytest.mark.parametrize('field', ['trade_id', 'ticker', 'yes_price_dollars', 'count_fp', 'created_time', 'taker_side'])
def test_missing_fields_are_rejected(tmp_path, field):
    row = trade()
    del row[field]
    with pytest.raises(ValueError):
        load_authentic_kalshi_tape(tape(tmp_path, [row]))


@pytest.mark.parametrize('changes', [
    {'yes_price_dollars': '-.01'}, {'yes_price_dollars': '1.01'}, {'yes_price_dollars': 'NaN'},
    {'yes_price_dollars': True}, {'count_fp': 'Infinity'}, {'count_fp': None}, {'ticker': ''},
    {'created_time': '2025-01-01T00:00:00'}, {'created_time': '2025-01-01T00:00:00.1234567891Z'},
    {'ts': -1, 'created_time': -1}, {'timestamp_ns': True}, {'taker_side': 'unknown'},
])
def test_bad_records_fail_closed(tmp_path, changes):
    with pytest.raises(ValueError):
        load_authentic_kalshi_tape(tape(tmp_path, [trade(**changes)]))


@pytest.mark.parametrize('rows', [[], [None], [trade(), trade(count_fp='.1')]])
def test_empty_or_duplicate_rows_rejected(tmp_path, rows):
    with pytest.raises(ValueError):
        load_authentic_kalshi_tape(tape(tmp_path, rows))


def test_unfilled_order_or_private_fill_without_aggressor_evidence_is_rejected(tmp_path):
    for row in (dict(order_id='open', ticker='KX-TEST-YES', status='resting'),
                dict(fill_id='fill', ticker='KX-TEST-YES', side='yes', action='buy', yes_price=46, count=2, ts=1735689600)):
        with pytest.raises(ValueError):
            load_authentic_kalshi_tape(tape(tmp_path, [row], 'executions'))


def test_routed_kalshi_replay_filters_contract_and_uses_independent_model(tmp_path):
    path = tape(tmp_path, [trade(trade_id='queue', count_fp=3),
                           trade(trade_id='buy', taker_side='yes', count_fp=999, created_time='2025-01-01T00:00:01Z'),
                           trade(trade_id='fill', yes_price_dollars='.45', count_fp=12, created_time='2025-01-01T00:00:02Z'),
                           trade(trade_id='foreign', ticker='OTHER', count_fp=999)])
    result = WalkForwardReplayHarness(scenario(), queue_ahead=5).run_authentic(path, venue='kalshi')
    assert result['venue'] == 'kalshi'
    assert result['reason'] == 'ADMITTED'
    assert result['p_fair'] == .7
    assert result['trade_print_count'] == 3
    assert result['excluded_trade_print_count'] == 1
    assert result['fills'] == [{'trade_id': 'fill', 'timestamp_ns': BASE_NS + 2_000_000_000, 'quantity': 10, 'price_cents': 46}]
    assert result['deployed_cents'] == 460
    assert result['payout_cents'] == 1000
    assert result['waterfall'] == {'scma_cents': 469, 'cfcp_cents': 55, 'faep_cents': 16}
    assert sum(result['waterfall'].values()) == result['net_pnl_cents']
    assert result['fixture_sha256'] == hashlib.sha256(path.read_bytes()).hexdigest()
    losing = WalkForwardReplayHarness(scenario(settlement_payout_cents=0), queue_ahead=5).run_authentic(path, venue='kalshi')
    assert losing['fills'] == result['fills']
    assert losing['waterfall'] == {'scma_cents': -460, 'cfcp_cents': 0, 'faep_cents': 0}


def test_kalshi_never_auto_fabricates_independent_bounds(tmp_path):
    path = tape(tmp_path, [trade()])
    for auto in (False, True):
        result = WalkForwardReplayHarness().run_authentic(path, venue='kalshi', auto_scenario=auto)
        assert result['abstention_detail'] == 'MISSING_INDEPENDENT_REPLAY_SCENARIO'
        assert result['fills'] == []
        assert result['p_fair'] is None


@pytest.mark.parametrize('changes', [{'fair_probability': -1}, {'fair_probability': True},
                                     {'fair_probability': float('nan')}, {'fair_probability': '0.7'},
                                     {'settlement_payout_cents': 50}])
def test_independent_bounds_fail_closed(tmp_path, changes):
    with pytest.raises(ValueError):
        WalkForwardReplayHarness(scenario(**changes)).run_authentic(tape(tmp_path, [trade()]), venue='kalshi')


def test_kalshi_cli_requires_and_accepts_external_scenario(tmp_path):
    path = tape(tmp_path, [trade()])
    backend = Path(__file__).resolve().parents[1]
    command = [sys.executable, str(backend / 'run_walk_forward_replay.py'), '--mode=authentic', '--venue=kalshi', f'--tape={path}']
    missing = subprocess.run(command, cwd=tmp_path, capture_output=True, text=True, check=True, timeout=10)
    assert json.loads(missing.stdout)['abstention_detail'] == 'MISSING_INDEPENDENT_REPLAY_SCENARIO'
    config = tmp_path / 'scenario.json'
    config.write_text(json.dumps(asdict(scenario())))
    admitted = subprocess.run(command + [f'--scenario={config}', '--queue-ahead=5'], cwd=tmp_path,
                              capture_output=True, text=True, check=True, timeout=10)
    assert json.loads(admitted.stdout)['reason'] == 'ADMITTED'


def test_unsupported_venue_rejected_before_file_io(tmp_path):
    with pytest.raises(ValueError, match='unsupported'):
        WalkForwardReplayHarness().run_authentic(tmp_path / 'missing', venue='unknown')


def test_numeric_json_seconds_do_not_pass_through_binary_float():
    content = ('[{"trade_id":"a","ticker":"KX-TEST-YES","ts":1735689600.123456789,'
               '"yes_price_dollars":0.465,"count_fp":3.99,"taker_side":"no"}]')
    result = parse_authentic_kalshi_tape(content)[0]
    assert result.timestamp_ns == BASE_NS + 123456789
    assert result.price_cents == 46


@pytest.mark.parametrize('changes', [{'no_price': -1}, {'no_price': 53}, {'yes_price': 47}])
def test_conflicting_or_invalid_alternate_price_fields_are_rejected(tmp_path, changes):
    with pytest.raises(ValueError):
        load_authentic_kalshi_tape(tape(tmp_path, [trade(**changes)]))
