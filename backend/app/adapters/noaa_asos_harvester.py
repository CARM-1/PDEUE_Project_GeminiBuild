"""Import archived METAR bulletins or fetch IEM ASOS CSV without inventing trades.

METAR day/time groups require an explicit archive year/month. Publication time
is not in a METAR: availability is conservatively set to archive retrieval time.
An observation is not a daily climate maximum or verified venue settlement.
"""
import argparse
import calendar
import csv
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import io
import json
from pathlib import Path
import re
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.adapters.authentic_weather_tape_loader import parse_authentic_weather_tape

STATIONS = ('KORD', 'KDEN', 'KJFK')
DATA_DIR = Path(__file__).resolve().parents[3] / 'data/venues/weather'


def parse_metar_archive(content: str, *, year: int, month: int, retrieved_at: str) -> list[dict]:
    """Extract target-station temperatures; collapse bulletin retransmissions.

    Prefer the ASOS signed tenth-degree T group over the rounded temperature.
    Conflicting temperatures at one station/time fail closed (no correction
    arrival ordering is available in an offline bulletin).
    """
    available = datetime.fromisoformat(retrieved_at.replace('Z', '+00:00'))
    if available.tzinfo is None:
        raise ValueError('retrieved_at must include a timezone')
    records = {}
    for match in re.finditer(r'\b(KORD|KDEN|KJFK) (\d{2})(\d{2})(\d{2})Z\b([^=]*)=', content):
        station, day, hour, minute, body = match.groups()
        instant = datetime(year, month, int(day), int(hour), int(minute), tzinfo=timezone.utc)
        if available < instant:
            raise ValueError('retrieval precedes observation')
        precise = re.search(r'\bT([01])(\d{3})[01]\d{3}\b', body)
        rounded = re.search(r'(?:^|\s)(M?\d{2})/(?:M?\d{2}|//)(?=\s|$)', body)
        if precise:
            temperature = Decimal(precise[2]) / 10 * (-1 if precise[1] == '1' else 1)
        elif rounded:
            temperature = Decimal(rounded[1].replace('M', '-'))
        else:
            raise ValueError(f'missing surface temperature for {station}')
        ns = calendar.timegm(instant.utctimetuple()) * 1_000_000_000
        key = station, ns
        if key in records:
            if records[key]['temperature_c'] != str(temperature):
                raise ValueError(f'conflicting temperature for {station} at {ns}')
            continue
        records[key] = dict(observation_id=f'{station}:{ns}', station_id=station,
                            timestamp_ns=ns, available_at=retrieved_at,
                            temperature_c=str(temperature),
                            raw_metar=' '.join(match[0].split()))
    if not records:
        raise ValueError('no target station observations')
    return sorted(records.values(), key=lambda row: (row['timestamp_ns'], row['station_id']))


def iem_url(station: str, start: datetime, end: datetime) -> str:
    if station not in STATIONS or start >= end:
        raise ValueError('invalid station or archive interval')
    return 'https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py?' + urlencode({
        'station': station[1:], 'data': 'tmpf', 'tz': 'Etc/UTC', 'format': 'onlycomma',
        'year1': start.year, 'month1': start.month, 'day1': start.day,
        'year2': end.year, 'month2': end.month, 'day2': end.day,
        'latlon': 'no', 'elev': 'no', 'missing': 'M', 'trace': 'T', 'direct': 'no',
        'report_type': '3',
    })


def fetch_iem(station: str, start: datetime, end: datetime, *, retrieved_at: str) -> dict:
    """Fetch public historical ASOS temperatures, retaining exact response bytes."""
    url = iem_url(station, start, end)
    with urlopen(Request(url, headers={'User-Agent': 'PDEUE-ASOS/1.0'}), timeout=60) as response:
        raw = response.read()
    observations, seen = [], {}
    for row in csv.DictReader(io.StringIO(raw.decode('utf-8'))):
        if row.get('station') not in (station, station[1:]):
            raise ValueError('IEM returned a foreign station')
        if row.get('tmpf') in ('M', '', None):
            continue
        temperature = Decimal(row['tmpf'])
        if not temperature.is_finite():
            raise ValueError('non-finite IEM temperature')
        instant = datetime.fromisoformat(row['valid']).replace(tzinfo=timezone.utc)
        if not start <= instant < end:
            raise ValueError('IEM observation outside requested interval')
        ns = calendar.timegm(instant.utctimetuple()) * 1_000_000_000
        if ns in seen:
            if seen[ns] != temperature:
                raise ValueError('conflicting IEM observation')
            continue
        seen[ns] = temperature
        observations.append(dict(observation_id=f'{station}:{ns}', station_id=station,
                                 timestamp_ns=ns, available_at=retrieved_at,
                                 temperature_f=str(temperature)))
    payload = dict(observations=observations, strike_ladder=[], provenance={
        'kind': 'ARCHIVED_OBSERVATIONS', 'source_url': url,
        'source_sha256': hashlib.sha256(raw).hexdigest(), 'retrieved_at': retrieved_at,
        'availability': 'Retrieval time; historical publication time unknown',
        'official_settlement_verified': False,
    })
    parse_authentic_weather_tape(json.dumps(payload))
    return {'payload': payload, 'raw': raw}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, help='Offline METAR bulletin')
    parser.add_argument('--year', type=int)
    parser.add_argument('--month', type=int)
    parser.add_argument('--source-url', help='Original archive URL for offline import')
    parser.add_argument('--start', help='IEM inclusive UTC date, YYYY-MM-DD')
    parser.add_argument('--end', help='IEM exclusive UTC date, YYYY-MM-DD')
    parser.add_argument('--output-dir', type=Path, default=DATA_DIR)
    args = parser.parse_args()
    retrieved = datetime.now(timezone.utc).isoformat()
    if args.archive:
        if not all((args.year, args.month, args.source_url)):
            parser.error('offline imports require --year, --month, and --source-url')
        raw = args.archive.read_bytes()
        rows = parse_metar_archive(raw.decode(), year=args.year, month=args.month, retrieved_at=retrieved)
        missing = set(STATIONS) - {row['station_id'] for row in rows}
        if missing:
            raise ValueError(f'archive missing target stations: {sorted(missing)}')
        batches = [(station, {'observations': [row for row in rows if row['station_id'] == station],
                    'strike_ladder': [], 'provenance': {'kind': 'ARCHIVED_OBSERVATIONS',
                    'source_url': args.source_url, 'source_sha256': hashlib.sha256(raw).hexdigest(),
                    'retrieved_at': retrieved, 'archive_year': args.year, 'archive_month': args.month,
                    'availability': 'Retrieval time; historical publication time unknown',
                    'official_settlement_verified': False}}, raw)
                   for station in STATIONS]
    else:
        if not args.start or not args.end:
            parser.error('fetch mode requires --start and --end')
        start, end = (datetime.fromisoformat(value).replace(tzinfo=timezone.utc)
                      for value in (args.start, args.end))
        batches = []
        for station in STATIONS:
            result = fetch_iem(station, start, end, retrieved_at=retrieved)
            batches.append((station, result['payload'], result['raw']))
    # Validate all stations before writing any tape. Never generate strike terms.
    for _, payload, _ in batches:
        parse_authentic_weather_tape(json.dumps(payload))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    sources = args.output_dir / 'sources'
    sources.mkdir(exist_ok=True)
    for station, payload, raw in batches:
        digest = hashlib.sha256(raw).hexdigest()
        source = sources / f'{digest}.txt'
        source.write_bytes(raw)
        payload['provenance']['source_file'] = str(source.relative_to(args.output_dir))
        target = args.output_dir / f'raw_observations_{station.lower()}.json'
        target.write_text(json.dumps(payload, indent=2) + '\n')


if __name__ == '__main__':
    main()
