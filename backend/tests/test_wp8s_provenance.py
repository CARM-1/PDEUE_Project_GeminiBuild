from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import pytest

from app.adapters.archive_provenance import source_integrity
from app.adapters.authentic_venue_harvester import harvest_real_polymarket_archive
from app.adapters.authentic_weather_tape_loader import parse_authentic_weather_tape
from app.adapters.kalshi_archive_harvester import import_archive
from app.adapters.noaa_asos_harvester import parse_metar_archive, iem_url
from app.domain.authentic_replay_stress import stress_capture
from scripts.run_batch_authentic_replay import run_batch

ROOT = Path(__file__).resolve().parents[2]
REPRESENTATIVE = ROOT / 'backend/tests/fixtures/representative_venues'
RETRIEVED = '2026-10-17T04:00:00+00:00'
METAR = 'KORD 011151Z 27003KT 10SM CLR 21/19 A3002 RMK AO2 T02110194='


def test_metar_precision_retransmission_and_exact_nanosecond_timestamp():
    rows = parse_metar_archive(METAR + '\n' + METAR, year=2019, month=7, retrieved_at=RETRIEVED)
    assert len(rows) == 1
    assert rows[0]['temperature_c'] == '21.1'
    assert rows[0]['timestamp_ns'] == 1561981860000000000
    tape = parse_authentic_weather_tape(json.dumps({'observations': rows}))
    assert str(tape.observations[0].temperature_f) == '69.98'
    assert tape.observations[0].available_at_ns > tape.observations[0].timestamp_ns
    assert not tape.execution_prints and not tape.strike_ladder


def test_metar_negative_tenth_degree_and_rounded_fallback():
    text = 'KDEN 011153Z AUTO M02/M06 A3016 RMK T10221056='
    rows = parse_metar_archive(text, year=2019, month=7, retrieved_at=RETRIEVED)
    assert rows[0]['temperature_c'] == '-2.2'
    rows = parse_metar_archive(text.replace(' RMK T10221056', ''), year=2019, month=7, retrieved_at=RETRIEVED)
    assert rows[0]['temperature_c'] == '-2'


@pytest.mark.parametrize('text,retrieved', [
    (METAR + METAR.replace('T02110194', 'T02210194'), RETRIEVED),
    ('KORD 321151Z 21/19=', RETRIEVED),
    ('KORD 011151Z /////=', RETRIEVED),
    (METAR, '2018-01-01T00:00:00+00:00'),
    (METAR, '2026-10-17T00:00:00'),
])
def test_metar_rejects_conflicts_missing_temperatures_and_unusable_time(text, retrieved):
    with pytest.raises(ValueError):
        parse_metar_archive(text, year=2019, month=7, retrieved_at=retrieved)


def test_iem_url_selects_station_and_utc_historical_interval():
    url = iem_url('KDEN', datetime(2019, 7, 1, tzinfo=timezone.utc),
                  datetime(2019, 7, 2, tzinfo=timezone.utc))
    assert 'station=DEN' in url and 'tz=Etc%2FUTC' in url and 'data=tmpf' in url
    with pytest.raises(ValueError):
        iem_url('OTHER', datetime(2019, 7, 1), datetime(2019, 7, 2))


def test_production_weather_is_three_archived_stations_without_invented_contracts():
    paths = sorted((ROOT / 'data/venues/weather').glob('raw_observations_*.json'))
    stations = set()
    for path in paths:
        payload = json.loads(path.read_bytes())
        assert source_integrity(path, payload['provenance'])
        raw = (path.parent / payload['provenance']['source_file']).read_text()
        expected = parse_metar_archive(raw, year=2019, month=7,
                                      retrieved_at=payload['provenance']['retrieved_at'])
        assert payload['observations'] == [row for row in expected
                                          if row['station_id'] == payload['observations'][0]['station_id']]
        tape = parse_authentic_weather_tape(path.read_bytes())
        stations.update(row.station_id for row in tape.observations)
        assert not tape.strike_ladder and not tape.execution_prints
    assert stations == {'KORD', 'KDEN', 'KJFK'}


def test_source_integrity_rejects_tampering_and_directory_escape(tmp_path):
    path = tmp_path / 'tape.json'
    source = tmp_path / 'sources/raw.txt'
    source.parent.mkdir()
    source.write_text('original')
    provenance = dict(kind='ARCHIVED_TRADES', source_url='https://example.org/archive',
                      source_file='sources/raw.txt', source_sha256=hashlib.sha256(b'original').hexdigest())
    assert source_integrity(path, provenance)
    source.write_text('changed')
    assert not source_integrity(path, provenance)
    provenance['source_file'] = '../raw.txt'
    assert not source_integrity(path, provenance)


def test_offline_polymarket_iteration_preserves_source_and_rejects_truncation(tmp_path):
    cid = '0x' + 'a' * 64
    offline, output = tmp_path / 'offline', tmp_path / 'output'
    offline.mkdir()
    output.mkdir()
    manifest = [dict(conditionId=cid, closed=True, question='Archive test',
                     outcomes=['Yes', 'No'], outcomePrices=['1', '0'], clobTokenIds=['YES', 'NO'])]
    (output / 'raw_settled_markets_manifest.json').write_text(json.dumps(manifest))
    row = dict(transactionHash='first', conditionId=cid, asset='YES', price='.45',
               size='10', timestamp=1735689600, side='SELL', title='Archive test')
    archived = dict(condition_id=cid, page_size=1, pages=[[row], []], retrieved_at=RETRIEVED,
                    source_url=f'https://data-api.polymarket.com/trades?market={cid}')
    source = offline / f'{cid}.json'
    source.write_text(json.dumps(archived))
    result = harvest_real_polymarket_archive(data_dir=output, offline_dir=offline, page_size=1)
    assert len(result) == 1 and result[0]['yes_won']
    assert (output / f'sources/{cid}.json').read_bytes() == source.read_bytes()
    receipt = json.loads((output / 'provenance_manifest.json').read_bytes())[f'raw_trades_{cid}.json']
    assert source_integrity(output / f'raw_trades_{cid}.json', receipt)
    archived['pages'].pop()
    source.write_text(json.dumps(archived))
    with pytest.raises(RuntimeError, match='terminal page'):
        harvest_real_polymarket_archive(data_dir=output, offline_dir=offline, page_size=1)


def test_kalshi_import_requires_settled_matching_contract_and_historical_book(tmp_path):
    # A representative vector tests importer mechanics, never authentic coverage.
    sample = json.loads((REPRESENTATIVE / 'kalshi/raw_trades_macro.json').read_bytes())
    sample.update(source_url='https://example.org/public/archive', retrieved_at=RETRIEVED,
                  market={'ticker': sample['trades'][0]['ticker'], 'status': 'settled', 'result': 'yes'})
    sample.pop('provenance')
    source = tmp_path / 'capture.json'
    source.write_text(json.dumps(sample))
    target = import_archive(source, tmp_path / 'out')
    result = json.loads(target.read_bytes())
    assert source_integrity(target, result['provenance'])
    assert result['provenance']['official_settlement_verified'] is False
    sample.pop('initial_book')
    source.write_text(json.dumps(sample))
    with pytest.raises(ValueError, match='L2'):
        import_archive(source, tmp_path / 'out')


def test_stress_blocks_wide_spreads_exhausts_queue_and_keeps_loss_conservation():
    path = REPRESENTATIVE / 'kalshi/raw_trades_macro.json'
    before = path.read_bytes()
    cases = stress_capture(path, 'kalshi')['cases']
    assert cases['baseline']['filled_quantity'] == 10
    assert cases['wide_spread_12c_guard_8c']['posted_quantity'] == 0
    assert cases['queue_depth_exhaustion']['filled_quantity'] == 0
    assert cases['slippage_barrier_2c']['filled_quantity'] <= 10
    loss = cases['adverse_resolution_zero_payout']
    assert loss['net_pnl_cents'] == -loss['deployed_cents'] < 0
    assert all(case['exact_cent_conservation'] for case in cases.values())
    assert path.read_bytes() == before


def test_strict_production_gate_reports_missing_venues_and_zero_execution():
    report = run_batch(venue_dirs={venue: ROOT / 'data/venues' / venue
                                  for venue in ('polymarket', 'kalshi', 'weather')},
                       require_authentic=True, auto_scenario=False, stress=True)
    assert report['status'] == 'INCOMPLETE'
    assert report['missing_venues'] == ['polymarket', 'kalshi']
    assert report['unique_summary']['total_unique_observations'] == 3
    assert report['unique_summary']['net_pnl_cents'] == report['unique_summary']['maker_fill_count'] == 0
    assert report['data_qualification']['archived_source_integrity_tape_count'] == 3
    assert report['data_qualification']['authentic_provenance_verified'] is False
    assert report['stress']['status'] == 'NO_EXECUTION_TAPES'
