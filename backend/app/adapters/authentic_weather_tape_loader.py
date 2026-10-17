"""NOAA ASOS observation tapes and half-open Fahrenheit strike brackets.

Temperatures are evidence, never trade prices or aggressive execution flow.
Accepts a normalized observations array or NOAA GeoJSON features, with an
optional strike_ladder array supplied alongside the observations.
An optional execution_tape object carries distinct Kalshi-schema exchange prints;
the observation stream never supplies execution prices, size, or aggressor side.
"""
from dataclasses import dataclass
from decimal import Decimal
import json
from pathlib import Path

from app.adapters.authentic_tape_utils import finite_decimal, required_text, timestamp_ns
from app.adapters.authentic_kalshi_tape_loader import parse_authentic_kalshi_tape
from app.adapters.authentic_polymarket_tape_loader import MarketTradePrint

DEFAULT_TAPE = Path(__file__).resolve().parents[3] / 'data/venues/weather/raw_observations.json'


@dataclass(frozen=True)
class TemperatureObservation:
    observation_id: str
    station_id: str
    timestamp_ns: int
    available_at_ns: int
    temperature_f: Decimal


@dataclass(frozen=True)
class WeatherStrikeBracket:
    contract_id: str
    station_id: str
    expiry_ns: int
    lower_f: Decimal | None
    upper_f: Decimal | None

    def contains(self, temperature_f: Decimal) -> bool:
        return ((self.lower_f is None or temperature_f >= self.lower_f)
                and (self.upper_f is None or temperature_f < self.upper_f))


@dataclass(frozen=True)
class WeatherTape:
    observations: tuple[TemperatureObservation, ...]
    strike_ladder: tuple[WeatherStrikeBracket, ...]
    execution_prints: tuple[MarketTradePrint, ...] = ()


@dataclass(frozen=True)
class WeatherReplayScenario:
    contract_id: str
    station_id: str
    observed_at_ns: int
    decision_at_ns: int
    expiry_ns: int
    initial_capital_cents: int = 10000


def parse_authentic_weather_tape(content: bytes | str) -> WeatherTape:
    payload = json.loads(content, parse_float=Decimal)
    if not isinstance(payload, dict):
        raise ValueError('weather tape must be an observation/ladder object')
    rows = payload.get('observations', payload.get('features'))
    ladder = payload.get('strike_ladder', [])
    if not isinstance(rows, list) or not isinstance(ladder, list):
        raise ValueError('observations/features and strike_ladder must be arrays')
    observations, seen = [], set()
    for index, raw in enumerate(rows):
        try:
            if not isinstance(raw, dict):
                raise ValueError('observation must be an object')
            row = raw.get('properties', raw)
            if not isinstance(row, dict):
                raise ValueError('invalid observation properties')
            oid = required_text(raw.get('id', row.get('observation_id', row.get('id'))), 'observation_id')
            if oid in seen:
                raise ValueError('duplicate observation ID')
            seen.add(oid)
            station = required_text(row.get('station_id', row.get('station')), 'station_id').rstrip('/').split('/')[-1]
            instant = timestamp_ns(row['timestamp_ns'], nanoseconds=True) if 'timestamp_ns' in row else timestamp_ns(
                row.get('timestamp', row.get('observed_at', row.get('observed_at_iso'))))
            available = timestamp_ns(row.get('available_at')) if 'available_at' in row else instant
            if available < instant:
                raise ValueError('observation cannot be available before it is observed')
            if 'temperature_f' in row or 'temp_f' in row:
                temperature = finite_decimal(row.get('temperature_f', row.get('temp_f')), 'temperature_f')
            elif 'temperature_c' in row or 'temp_c' in row:
                temperature = finite_decimal(row.get('temperature_c', row.get('temp_c')), 'temperature_c') * 9 / 5 + 32
            else:
                native = row.get('temperature')
                if not isinstance(native, dict):
                    raise ValueError('missing surface temperature')
                temperature = finite_decimal(native.get('value'), 'temperature.value')
                if native.get('unitCode') == 'wmoUnit:degC':
                    temperature = temperature * 9 / 5 + 32
                elif native.get('unitCode') != 'wmoUnit:degF':
                    raise ValueError('unsupported temperature unit')
            observations.append(TemperatureObservation(oid, station, instant, available, temperature))
        except (ValueError, TypeError) as exc:
            raise ValueError(f'weather observation {index}: {exc}') from exc
    observations.sort(key=lambda observation: (observation.timestamp_ns, observation.observation_id))
    if not observations:
        raise ValueError('empty weather observation tape')
    strikes, seen_contracts = [], set()
    for row in ladder:
        if not isinstance(row, dict):
            raise ValueError('strike bracket must be an object')
        cid = required_text(row.get('contract_id'), 'contract_id')
        station = required_text(row.get('station_id'), 'station_id')
        if cid in seen_contracts:
            raise ValueError('duplicate strike contract ID')
        seen_contracts.add(cid)
        expiry = timestamp_ns(row['expiry_ns'], nanoseconds=True) if 'expiry_ns' in row else timestamp_ns(row.get('expiry'))
        lower = finite_decimal(row['lower_f'], 'lower_f') if row.get('lower_f') is not None else None
        upper = finite_decimal(row['upper_f'], 'upper_f') if row.get('upper_f') is not None else None
        if (lower is None and upper is None) or (lower is not None and upper is not None and lower >= upper):
            raise ValueError('invalid half-open strike bracket')
        strikes.append(WeatherStrikeBracket(cid, station, expiry, lower, upper))
    strikes.sort(key=lambda strike: (strike.expiry_ns, strike.station_id,
                                      strike.lower_f if strike.lower_f is not None else Decimal('-Infinity')))
    for a, b in zip(strikes, strikes[1:]):
        if a.station_id == b.station_id and a.expiry_ns == b.expiry_ns and (
                a.upper_f is None or b.lower_f is None or a.upper_f > b.lower_f):
            raise ValueError('overlapping strike ladder')
    # Exchange executions are separate evidence; temperatures never become prices.
    execution_prints = ()
    if 'execution_tape' in payload:
        execution_prints = tuple(parse_authentic_kalshi_tape(json.dumps(payload['execution_tape'], default=str)))
        if any(trade.contract_id not in seen_contracts for trade in execution_prints):
            raise ValueError('weather execution contract has no strike bracket')
    return WeatherTape(tuple(observations), tuple(strikes), execution_prints)


def load_authentic_weather_tape(path: str | Path = DEFAULT_TAPE) -> WeatherTape:
    return parse_authentic_weather_tape(Path(path).read_bytes())
