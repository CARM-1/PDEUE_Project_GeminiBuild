"""Exact numeric and timestamp conversion at captured-tape boundaries."""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import re

EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
ISO_TIMESTAMP = re.compile(r'^(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2})(?:\.(\d{1,9}))?(Z|[+-]\d{2}:\d{2})$')


def finite_decimal(value, name: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ValueError(f'missing or invalid {name}')
    try:
        number = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f'invalid {name}') from exc
    if not number.is_finite():
        raise ValueError(f'{name} must be finite')
    return number


def timestamp_ns(value, *, nanoseconds: bool = False) -> int:
    """Parse timezone-aware ISO (up to 9 fractional digits), seconds, or ns."""
    if isinstance(value, str) and ('T' in value or ' ' in value):
        match = ISO_TIMESTAMP.fullmatch(value)
        if not match:
            raise ValueError('timestamp requires a timezone and at most nine fractional digits')
        base, fraction, zone = match.groups()
        moment = datetime.fromisoformat(base + ('+00:00' if zone == 'Z' else zone))
        delta = moment.astimezone(timezone.utc) - EPOCH
        result = (delta.days * 86400 + delta.seconds) * 1_000_000_000 + int((fraction or '').ljust(9, '0'))
    else:
        number = finite_decimal(value, 'timestamp')
        scaled = number if nanoseconds else number * 1_000_000_000
        if scaled != scaled.to_integral_value():
            raise ValueError('timestamp has sub-nanosecond precision')
        result = int(scaled)
    if result < 0:
        raise ValueError('timestamp must be nonnegative')
    return result


def required_text(value, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'missing or invalid {name}')
    return value
