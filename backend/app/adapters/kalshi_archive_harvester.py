"""Validate offline public Kalshi settled-market captures and historical L2.

No reconstructed book, generated trade IDs, or inferred settlement is accepted.
The input is an archive envelope with source_url, market, trades, initial_book,
and retrieved_at. Source attribution is retained, never upgraded to certification.
"""
import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import urlparse

from app.adapters.authentic_kalshi_tape_loader import parse_authentic_kalshi_tape
from app.domain.authentic_replay_calibration import initial_scenario


def import_archive(source: Path, output_dir: Path) -> Path:
    raw = source.read_bytes()
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError('expected archived response envelope')
    url = urlparse(payload.get('source_url', ''))
    if url.scheme != 'https' or not url.netloc or not payload.get('retrieved_at'):
        raise ValueError('missing archive URL or retrieval timestamp')
    market = payload.get('market', {})
    if (market.get('status') != 'settled' or market.get('result') not in ('yes', 'no')
            or not isinstance(market.get('ticker'), str) or not market['ticker']):
        raise ValueError('official settled market response required')
    trades = parse_authentic_kalshi_tape(json.dumps({'trades': payload.get('trades')}))
    if any(trade.contract_id != market['ticker'] for trade in trades):
        raise ValueError('trade ticker differs from settlement contract')
    book = payload.get('initial_book')
    if book is None:
        raise ValueError('archived initial L2 snapshot required')
    initial_scenario(trades, book)  # validates contract, integer levels, time, spread
    ticker = market['ticker']
    if any(char not in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_' for char in ticker):
        raise ValueError('unsafe ticker')
    output_dir.mkdir(parents=True, exist_ok=True)
    sources = output_dir / 'sources'
    sources.mkdir(exist_ok=True)
    digest = hashlib.sha256(raw).hexdigest()
    source_file = sources / f'{digest}.json'
    result = {'trades': payload['trades'], 'initial_book': book, 'market': market,
              'provenance': {'kind': 'ARCHIVED_TRADES', 'source_url': payload['source_url'],
                  'source_file': str(source_file.relative_to(output_dir)), 'source_sha256': digest,
                  'retrieved_at': payload['retrieved_at'], 'official_settlement_verified': False,
                  'scope': 'Validated archived response; source attribution requires independent review'}}
    target = output_dir / f'raw_trades_{ticker}.json'
    if target.exists() and json.loads(target.read_bytes()) != result:
        raise ValueError('refusing to overwrite a different contract capture')
    source_file.write_bytes(raw)
    target.write_text(json.dumps(result, indent=2) + '\n')
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('--output-dir', type=Path,
                        default=Path(__file__).resolve().parents[3] / 'data/venues/kalshi')
    args = parser.parse_args()
    print(import_archive(args.archive, args.output_dir))


if __name__ == '__main__':
    main()
