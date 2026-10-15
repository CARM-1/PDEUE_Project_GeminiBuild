"""Venue dispatch and audit metadata for trade and observation tapes."""
import json

from app.adapters.authentic_polymarket_tape_loader import DEFAULT_TAPE as POLYMARKET_TAPE, parse_authentic_polymarket_tape
from app.adapters.authentic_kalshi_tape_loader import DEFAULT_TAPE as KALSHI_TAPE, kalshi_records, parse_authentic_kalshi_tape
from app.adapters.authentic_weather_tape_loader import DEFAULT_TAPE as WEATHER_TAPE, WeatherTape, parse_authentic_weather_tape

DEFAULT_TAPES = {'polymarket': POLYMARKET_TAPE, 'kalshi': KALSHI_TAPE, 'weather': WEATHER_TAPE}
PARSERS = {'polymarket': parse_authentic_polymarket_tape,
           'kalshi': parse_authentic_kalshi_tape, 'weather': parse_authentic_weather_tape}


def parse_venue_tape(content: bytes | str, venue: str):
    if venue not in PARSERS:
        raise ValueError(f'unsupported replay venue: {venue}')
    return PARSERS[venue](content)


def raw_record_count(content: bytes | str, venue: str) -> int:
    if venue == 'kalshi':
        return len(kalshi_records(content))
    payload = json.loads(content)
    return len(payload.get('observations', payload.get('features', []))) if venue == 'weather' else len(payload)


def record_ids(tape) -> set[str]:
    if isinstance(tape, WeatherTape):
        return {observation.observation_id for observation in tape.observations}
    return {trade.trade_id for trade in tape}


def contract_ids(tape) -> set[str]:
    if isinstance(tape, WeatherTape):
        return {strike.contract_id for strike in tape.strike_ladder}
    return {trade.contract_id for trade in tape}
