from dataclasses import asdict, replace
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from app.adapters.authentic_weather_tape_loader import (
    WeatherReplayScenario, load_authentic_weather_tape, parse_authentic_weather_tape,
)
from app.domain.walk_forward_replay_harness import WalkForwardReplayHarness

BASE_NS = 1735689600 * 1_000_000_000


def observation(**changes):
    return {**dict(observation_id='a', station_id='KJFK', timestamp='2025-01-01T00:00:00Z', temperature_f='70'), **changes}


def bracket(**changes):
    return {**dict(contract_id='JFK-70-72', station_id='KJFK', expiry='2025-01-01T00:05:00Z', lower_f='70', upper_f='72'), **changes}


def tape(tmp_path, observations=None, ladder=None):
    path = tmp_path / 'raw_observations_jfk.json'
    path.write_text(json.dumps({'observations': observations if observations is not None else [observation()],
                               'strike_ladder': ladder if ladder is not None else [bracket()]}))
    return path


def scenario():
    return WeatherReplayScenario('JFK-70-72', 'KJFK', BASE_NS, BASE_NS + 1, BASE_NS + 300_000_000_000)


def test_chronological_ticks_preserve_nanoseconds_and_same_second_ties(tmp_path):
    path = tape(tmp_path, [observation(observation_id='b', timestamp='2025-01-01T00:00:00.123456789Z'),
                           observation(observation_id='a', timestamp='2024-12-31T19:00:00.123456789-05:00'),
                           observation(observation_id='c', timestamp='2025-01-01T00:00:00.123456790Z')])
    ticks = load_authentic_weather_tape(path).observations
    assert [tick.observation_id for tick in ticks] == ['a', 'b', 'c']
    assert ticks[0].timestamp_ns == BASE_NS + 123456789
    assert ticks[-1].timestamp_ns == BASE_NS + 123456790


def test_native_noaa_geojson_celsius_and_station_url(tmp_path):
    path = tmp_path / 'native_noaa.json'
    path.write_text(json.dumps({'features': [{'id': 'NOAA-1', 'properties': {
        'station': 'https://api.weather.gov/stations/KJFK', 'timestamp': '2025-01-01T00:00:00Z',
        'temperature': {'value': '20', 'unitCode': 'wmoUnit:degC'},
    }}], 'strike_ladder': [bracket()]}))
    result = load_authentic_weather_tape(path)
    assert result.observations[0].station_id == 'KJFK'
    assert result.observations[0].temperature_f == Decimal('68')


def test_normalized_celsius_and_half_open_ladder_boundaries(tmp_path):
    row = observation(temperature_c='20')
    del row['temperature_f']
    result = load_authentic_weather_tape(tape(tmp_path, [row], [bracket(), bracket(contract_id='JFK-72-74', lower_f='72', upper_f='74')]))
    assert result.observations[0].temperature_f == Decimal(68)
    lower, upper = result.strike_ladder
    assert lower.contains(Decimal(70))
    assert not lower.contains(Decimal(72))
    assert upper.contains(Decimal(72))


@pytest.mark.parametrize('changes', [{'temperature_f': 'NaN'}, {'temperature_f': True},
                                     {'temperature_f': None}, {'station_id': ''},
                                     {'timestamp': '2025-01-01T00:00:00'},
                                     {'available_at': '2024-12-31T23:59:59Z'}])
def test_bad_observations_rejected(tmp_path, changes):
    with pytest.raises(ValueError):
        load_authentic_weather_tape(tape(tmp_path, [observation(**changes)]))


@pytest.mark.parametrize('field', ['observation_id', 'station_id', 'timestamp', 'temperature_f'])
def test_missing_observation_fields_rejected(tmp_path, field):
    row = observation()
    del row[field]
    with pytest.raises(ValueError):
        load_authentic_weather_tape(tape(tmp_path, [row]))


@pytest.mark.parametrize('rows', [[], [None], [observation(), observation(temperature_f='71')]])
def test_empty_or_duplicate_observations_rejected(tmp_path, rows):
    with pytest.raises(ValueError):
        load_authentic_weather_tape(tape(tmp_path, rows))


@pytest.mark.parametrize('ladder', [
    [bracket(), bracket()], [bracket(lower_f='72', upper_f='70')], [bracket(lower_f=None, upper_f=None)],
    [bracket(), bracket(contract_id='overlap', lower_f='71', upper_f='73')],
    [bracket(expiry=None)], [bracket(lower_f='Infinity')],
])
def test_bad_or_overlapping_strike_ladders_rejected(tmp_path, ladder):
    with pytest.raises(ValueError):
        load_authentic_weather_tape(tape(tmp_path, ladder=ladder))


def test_expiry_barrier_excludes_future_and_late_published_observations(tmp_path):
    path = tape(tmp_path, [observation(),
        observation(observation_id='replay', timestamp='2025-01-01T00:03:00Z', temperature_f='71'),
        observation(observation_id='boundary', timestamp='2025-01-01T00:05:00Z', temperature_f='72'),
        observation(observation_id='future', timestamp='2025-01-01T00:05:00.000000001Z', temperature_f='100'),
        observation(observation_id='late', timestamp='2025-01-01T00:04:00Z', available_at='2025-01-01T00:06:00Z', temperature_f='99'),
        observation(observation_id='other', station_id='KLAX', temperature_f='80'),
    ])
    result = WalkForwardReplayHarness(scenario()).run_authentic(path, venue='weather')
    weather = result['weather_evaluation']
    assert result['abstention_detail'] == 'NO_EXECUTION_TAPE'
    assert weather['pre_decision_observation_count'] == 1
    assert weather['replay_observation_count'] == 2
    assert weather['post_expiry_excluded_count'] == 2
    assert weather['other_station_excluded_count'] == 1
    assert weather['last_observed_temperature_f'] == '72'
    assert weather['last_observation_in_bracket'] is False
    assert weather['settlement_verified'] is False
    assert result['fills'] == []
    assert result['trade_print_count'] == result['deployed_cents'] == result['net_pnl_cents'] == 0
    assert result['parsed_observation_count'] == 6
    assert result['fixture_sha256'] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert sum(result['waterfall'].values()) == 0


def test_weather_never_auto_fabricates_scenario_or_execution_prices(tmp_path):
    path = tape(tmp_path)
    for auto in (False, True):
        result = WalkForwardReplayHarness().run_authentic(path, venue='weather', auto_scenario=auto)
        assert result['abstention_detail'] == 'MISSING_INDEPENDENT_REPLAY_SCENARIO'
        assert result['p_fair'] is result['net_edge'] is None
        assert result['fills'] == []


def test_scenario_must_match_station_expiry_and_contract_selection(tmp_path):
    path = tape(tmp_path)
    for s in (replace(scenario(), station_id='KLAX'), replace(scenario(), expiry_ns=BASE_NS + 1),
              replace(scenario(), decision_at_ns=BASE_NS)):
        with pytest.raises(ValueError):
            WalkForwardReplayHarness(s).run_authentic(path, venue='weather')
    with pytest.raises(ValueError):
        WalkForwardReplayHarness(scenario()).run_authentic(path, venue='weather', contract_id='OTHER')
    missing = WalkForwardReplayHarness(replace(scenario(), contract_id='OTHER')).run_authentic(path, venue='weather')
    assert missing['abstention_detail'] == 'NO_MATCHING_STRIKE_BRACKET'


def test_weather_cli_uses_weather_bounds_without_bitcoin_model(tmp_path):
    path = tape(tmp_path)
    config = tmp_path / 'weather_scenario.json'
    config.write_text(json.dumps(asdict(scenario())))
    backend = Path(__file__).resolve().parents[1]
    completed = subprocess.run([sys.executable, str(backend / 'run_walk_forward_replay.py'), '--mode=authentic',
                                '--venue=weather', f'--tape={path}', f'--scenario={config}'],
                               cwd=tmp_path, check=True, capture_output=True, text=True, timeout=10)
    assert json.loads(completed.stdout)['abstention_detail'] == 'NO_EXECUTION_TAPE'
