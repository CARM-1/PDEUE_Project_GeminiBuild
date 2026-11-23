"""Play #11B + #13B hermetic tests for read-only live L2 tape capture & SHA-256 manifest verification."""
import httpx
import pytest

from app.adapters.live_l2_tape_recorder import (
    ReadOnlyL2TapeRecorder,
    discover_liquid_kalshi_tickers,
    discover_liquid_polymarket_tokens,
    verify_tape_manifest,
)
from app.domain.gate_g2_validator import validate_trade_candidate


def _mock_client(kalshi_payload=None, poly_payload=None) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "kalshi.com" in url and "/events" in url:
            return httpx.Response(200, json={
                "events": [{
                    "markets": [
                        {"ticker": "KXMVE-COMBO-1", "volume_24h_fp": "99999.00"},
                        {"ticker": "KXLOW", "volume_24h_fp": "10.00", "open_interest_fp": "50.00"},
                        {"ticker": "KXHIGHMIA-26NOV22-T80", "volume_24h_fp": "5400.00", "open_interest_fp": "12000.00"},
                    ]
                }]
            })
        if "kalshi.com" in url:
            return httpx.Response(200, json=kalshi_payload if kalshi_payload is not None else {
                "orderbook_fp": {
                    "yes_dollars": [["0.4800", "120.50"], ["0.4500", "50.00"]],
                    "no_dollars": [["0.5000", "80.00"], ["0.4700", "40.00"]],
                }
            })
        if "gamma-api.polymarket.com" in url:
            return httpx.Response(200, json=[{"clobTokenIds": '["TOKEN-TOP-1", "TOKEN-TOP-2"]'}])
        if "polymarket.com" in url:
            return httpx.Response(200, json=poly_payload if poly_payload is not None else {
                "bids": [{"price": "0.49", "size": "200"}],
                "asks": [{"price": "0.52", "size": "150"}],
            })
        return httpx.Response(404)
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_kalshi_fp_and_polymarket_capture_produces_verified_observed_l2_manifest(tmp_path):
    rec = ReadOnlyL2TapeRecorder(tmp_path, http_client=_mock_client())
    s1 = rec.capture_kalshi_snapshot("KXHIGHMIA-26NOV22-T80", captured_at_utc="2026-11-22T20:00:00.000000Z")
    s2 = rec.capture_polymarket_snapshot("TOKEN-12345", captured_at_utc="2026-11-22T20:00:01.000000Z")
    manifest = rec.finalize_manifest()
    verified = verify_tape_manifest(rec.manifest_path)

    assert s1["bids"] == [[48, 120], [45, 50]]
    assert s1["asks"] == [[50, 80], [53, 40]]
    assert s2["bids"] == [[49, 200]] and s2["asks"] == [[52, 150]]
    assert verified["data_provenance"] == "OBSERVED_L2"
    assert verified["snapshot_count"] == 2
    assert len(verified["tape_manifest_sha256"]) == 64

    validate_trade_candidate({
        "schema_version": "1.1.0-certified-candidate",
        "candidate_id": "cand-l2-001", "scma_id": "SCMA-MEM-0001",
        "category": "WEATHER_TEMPERATURE", "venue": "KALSHI",
        "contract_ticker": "KXHIGHMIA-26NOV22-T80", "side": "YES", "quantity": 5,
        "evidence_max_ts_utc": "2026-11-22T20:00:00Z", "pit_cutoff_utc": "2026-11-22T20:00:05Z",
        "event_blackout_utc": "2026-11-22T23:00:00Z", "model_prob_bps": 7000,
        "fill_conditioned_win_bps": 6500, "limit_price_cents": 49, "effective_fee_cents": 0,
        "expected_payoff_if_filled_cents": 65, "conditional_ev_cents": 16,
        "data_provenance": "OBSERVED_L2", "tape_manifest_sha256": manifest["tape_manifest_sha256"],
    })


def test_empty_book_rejected_fail_closed(tmp_path):
    rec = ReadOnlyL2TapeRecorder(tmp_path, http_client=_mock_client(kalshi_payload={"orderbook_fp": {}}))
    with pytest.raises(ValueError, match="Empty L2 order book"):
        rec.capture_kalshi_snapshot("KX-EMPTY")


def test_liquid_discovery_filters_combo_markets_and_ranks_by_volume():
    client = _mock_client()
    assert discover_liquid_kalshi_tickers(http_client=client, limit=2) == ["KXHIGHMIA-26NOV22-T80", "KXLOW"]
    assert discover_liquid_polymarket_tokens(http_client=client, limit=1) == ["TOKEN-TOP-1"]


def test_verify_manifest_fails_closed_on_single_byte_tamper(tmp_path):
    rec = ReadOnlyL2TapeRecorder(tmp_path, http_client=_mock_client())
    rec.capture_kalshi_snapshot("KX-TAMP", captured_at_utc="2026-11-22T20:00:00.000000Z")
    rec.finalize_manifest()
    rec.tape_path.write_text(rec.tape_path.read_text(encoding="utf-8").replace("120", "121"), encoding="utf-8")
    with pytest.raises(ValueError, match="SHA-256 tamper mismatch"):
        verify_tape_manifest(rec.manifest_path)


def test_verify_manifest_rejects_non_monotonic_timestamps(tmp_path):
    rec = ReadOnlyL2TapeRecorder(tmp_path, http_client=_mock_client())
    rec.capture_kalshi_snapshot("KX-MONO", captured_at_utc="2026-11-22T20:00:05.000000Z")
    rec.capture_kalshi_snapshot("KX-MONO", captured_at_utc="2026-11-22T20:00:01.000000Z")
    rec.finalize_manifest()
    with pytest.raises(ValueError, match="Non-monotonic timestamp"):
        verify_tape_manifest(rec.manifest_path)


def test_recorder_rejects_non_integer_cent_prices(tmp_path):
    bad_poly = {"bids": [{"price": "0.495", "size": "100"}], "asks": []}
    rec = ReadOnlyL2TapeRecorder(tmp_path, http_client=_mock_client(poly_payload=bad_poly))
    with pytest.raises(ValueError, match="Non-integer cent"):
        rec.capture_polymarket_snapshot("TOKEN-BAD")
