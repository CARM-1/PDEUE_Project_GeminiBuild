"""Play #14 hermetic tests for continuous dual-venue OBSERVED_L2 capture session runner."""
import httpx

from scripts.run_l2_capture_session import run_capture_session
from app.adapters.live_l2_tape_recorder import verify_tape_manifest


def _mock_session_client(fail_once_ticker: str = "") -> httpx.Client:
    state = {"failed": False}

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "kalshi.com" in url and "/events" in url:
            return httpx.Response(200, json={
                "events": [{"markets": [
                    {"ticker": "KX-WEATHER-1", "volume_24h_fp": "1200.00"},
                    {"ticker": "KX-MACRO-1", "volume_24h_fp": "800.00"},
                ]}]
            })
        if "kalshi.com" in url:
            if fail_once_ticker and fail_once_ticker in url and not state["failed"]:
                state["failed"] = True
                return httpx.Response(503)
            return httpx.Response(200, json={
                "orderbook_fp": {
                    "yes_dollars": [["0.4200", "150.00"]],
                    "no_dollars": [["0.5500", "100.00"]],
                }
            })
        if "gamma-api.polymarket.com" in url:
            return httpx.Response(200, json=[
                {"clobTokenIds": '["POLY-TOK-1"]'},
                {"clobTokenIds": '["POLY-TOK-2"]'},
            ])
        if "polymarket.com" in url:
            return httpx.Response(200, json={
                "bids": [{"price": "0.35", "size": "500"}],
                "asks": [{"price": "0.37", "size": "400"}],
            })
        return httpx.Response(404)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_capture_session_dual_venue_and_manifest_verification(tmp_path):
    summary = run_capture_session(
        tmp_path / "sess1",
        kalshi_count=2,
        poly_count=2,
        duration_seconds=0.0,
        interval_seconds=0.01,
        http_client=_mock_session_client(),
    )
    assert summary["cycles"] == 1
    assert summary["snapshot_count"] == 4
    assert summary["errors_count"] == 0
    assert len(summary["tape_manifest_sha256"]) == 64
    verified = verify_tape_manifest(tmp_path / "sess1" / "tape_manifest.json")
    assert verified["venues"] == ["KALSHI", "POLYMARKET"]


def test_capture_session_survives_transient_503_and_seals_valid_tape(tmp_path):
    summary = run_capture_session(
        tmp_path / "sess2",
        kalshi_tickers=["KX-WEATHER-1", "KX-MACRO-1"],
        poly_tokens=["POLY-TOK-1"],
        duration_seconds=0.0,
        interval_seconds=0.01,
        http_client=_mock_session_client(fail_once_ticker="KX-MACRO-1"),
    )
    assert summary["snapshot_count"] == 2
    assert summary["errors_count"] == 1
    verified = verify_tape_manifest(tmp_path / "sess2" / "tape_manifest.json")
    assert verified["snapshot_count"] == 2
