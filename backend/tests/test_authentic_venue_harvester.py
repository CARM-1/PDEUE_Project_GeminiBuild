import json
from urllib.parse import parse_qs, urlparse

import pytest

from app.adapters import authentic_venue_harvester as harvester

CID_A = '0x' + 'a' * 64
CID_B = '0x' + 'b' * 64


def trade(trade_id, cid=CID_A, token='token-a', timestamp=100):
    return dict(transactionHash=trade_id, conditionId=cid, asset=token,
                price=.465, size=3.9, timestamp=timestamp, side='SELL', title='Test market')


def market(cid=CID_A, token='token-a'):
    return dict(conditionId=cid, closed=True, question='Test market',
                outcomes='["No", "Yes"]', outcomePrices='["0", "1"]',
                clobTokenIds=json.dumps(['no-token', token]))


def test_market_pagination_advances_offsets_and_deduplicates_overlap(monkeypatch):
    a, b, c = trade('a'), trade('b'), trade('c', timestamp=101)
    pages = [[a, b], [b, c], []]
    calls = []
    def fetch(url):
        query = parse_qs(urlparse(url).query)
        assert query['market'] == [CID_A]
        assert query['takerOnly'] == ['false']
        assert 'asset_id' not in query
        calls.append(int(query['offset'][0]))
        return pages.pop(0)
    monkeypatch.setattr(harvester, 'fetch_json', fetch)
    rows = harvester.fetch_market_trade_pages(CID_A, 'token-a', page_size=2)
    assert calls == [0, 2, 4]
    assert [row['transactionHash'] for row in rows] == ['a', 'b', 'c']


def test_other_outcome_advances_cursor_without_polluting_yes_tape(monkeypatch):
    pages = [[trade('no', token='no-token')], []]
    monkeypatch.setattr(harvester, 'fetch_json', lambda url: pages.pop(0))
    assert harvester.fetch_market_trade_pages(CID_A, 'token-a', page_size=1) == []


@pytest.mark.parametrize('page', [[trade('foreign', cid=CID_B)], None, {'error': 'failed'}])
def test_foreign_market_or_failed_page_fails_closed(monkeypatch, page):
    monkeypatch.setattr(harvester, 'fetch_json', lambda url: page)
    with pytest.raises((ValueError, RuntimeError)):
        harvester.fetch_market_trade_pages(CID_A, 'token-a')


def test_repeated_pages_and_page_cap_do_not_certify_partial_archive(monkeypatch):
    monkeypatch.setattr(harvester, 'fetch_json', lambda url: [trade('a')])
    with pytest.raises(RuntimeError, match='no progress'):
        harvester.fetch_market_trade_pages(CID_A, 'token-a', page_size=1)
    with pytest.raises(RuntimeError, match='incomplete'):
        harvester.fetch_market_trade_pages(CID_A, 'token-a', page_size=1, max_pages=1)


def test_conflicting_duplicate_hash_is_rejected(monkeypatch):
    changed = trade('a')
    changed['size'] = 8
    pages = [[trade('a')], [changed]]
    monkeypatch.setattr(harvester, 'fetch_json', lambda url: pages.pop(0))
    with pytest.raises(ValueError, match='conflicting'):
        harvester.fetch_market_trade_pages(CID_A, 'token-a', page_size=1)


def test_distinct_settled_markets_produce_nonoverlapping_verified_files(tmp_path, monkeypatch):
    manifest = tmp_path / 'raw_settled_markets_manifest.json'
    manifest.write_text(json.dumps([market(), market(), market(CID_B, 'token-b')]))
    calls = []
    def fetch(url):
        query = parse_qs(urlparse(url).query)
        cid = query['market'][0]
        calls.append(cid)
        return [trade(cid[-1], cid, 'token-a' if cid == CID_A else 'token-b')]
    monkeypatch.setattr(harvester, 'fetch_json', fetch)
    result = harvester.harvest_real_polymarket_archive(data_dir=tmp_path)
    assert calls == [CID_A, CID_B]
    assert len(result) == 2
    assert all(contract['yes_won'] for contract in result)
    prints = [contract['trade_prints'][0] for contract in result]
    assert [p.trade_id for p in prints] == ['a', 'b']
    assert all(p.price_cents == 46 and p.volume == 3 for p in prints)
    for cid in (CID_A, CID_B):
        rows = json.loads((tmp_path / f'raw_trades_{cid}.json').read_text())
        assert all(row['conditionId'] == cid for row in rows)


def test_late_failure_preserves_all_existing_captures(tmp_path, monkeypatch):
    manifest = tmp_path / 'raw_settled_markets_manifest.json'
    manifest.write_text(json.dumps([market(), market(CID_B, 'token-b')]))
    original = tmp_path / f'raw_trades_{CID_A}.json'
    original.write_text('preserve original bytes')
    monkeypatch.setattr(harvester, 'fetch_json', lambda url: [trade('a')] if CID_A in url else None)
    with pytest.raises(RuntimeError):
        harvester.harvest_real_polymarket_archive(data_dir=tmp_path)
    assert original.read_text() == 'preserve original bytes'
    assert not (tmp_path / f'raw_trades_{CID_B}.json').exists()


def test_overlapping_market_hashes_abort_before_writes(tmp_path, monkeypatch):
    (tmp_path / 'raw_settled_markets_manifest.json').write_text(
        json.dumps([market(), market(CID_B, 'token-b')]))
    def fetch(url):
        cid = parse_qs(urlparse(url).query)['market'][0]
        return [trade('shared', cid, 'token-a' if cid == CID_A else 'token-b')]
    monkeypatch.setattr(harvester, 'fetch_json', fetch)
    with pytest.raises(ValueError, match='overlap'):
        harvester.harvest_real_polymarket_archive(data_dir=tmp_path)
    assert list(tmp_path.glob('raw_trades_*.json')) == []


@pytest.mark.parametrize('prices', ['["0", "0"]', '["1", "1"]', '["0.25", "0.75"]'])
def test_unresolved_or_inconsistent_manifest_is_not_settled_as_loss(tmp_path, monkeypatch, prices):
    row = market()
    row['outcomePrices'] = prices
    (tmp_path / 'raw_settled_markets_manifest.json').write_text(json.dumps([row]))
    def unexpected_request(url):
        pytest.fail('unresolved market must be rejected before requesting its trades')
    monkeypatch.setattr(harvester, 'fetch_json', unexpected_request)
    with pytest.raises(ValueError, match='unresolved'):
        harvester.harvest_real_polymarket_archive(data_dir=tmp_path)
