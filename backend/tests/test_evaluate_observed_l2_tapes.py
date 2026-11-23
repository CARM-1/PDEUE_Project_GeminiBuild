"""Play #15B hermetic tests for zero-synthetic OBSERVED_L2 microstructure & manifest evaluator."""
import httpx

from app.adapters.live_l2_tape_recorder import ReadOnlyL2TapeRecorder
from scripts.evaluate_observed_l2_tapes import evaluate_observed_l2_root, evaluate_tape_directory


def _client() -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "kalshi.com" in url:
            return httpx.Response(200, json={
                "orderbook_fp": {
                    "yes_dollars": [["0.4800", "120.00"]],
                    "no_dollars": [["0.5000", "80.00"]],  # YES ask = 100 - 50 = 50c -> spread = 2c
                }
            })
        if "polymarket.com" in url:
            return httpx.Response(200, json={
                "bids": [{"price": "0.60", "size": "250"}],
                "asks": [{"price": "0.61", "size": "300"}],  # spread = 1c
            })
        return httpx.Response(404)
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_evaluate_tape_directory_computes_real_spreads_and_zero_synthetic_fills(tmp_path):
    sess = tmp_path / "sess_a"
    rec = ReadOnlyL2TapeRecorder(sess, http_client=_client())
    rec.capture_kalshi_snapshot("KX-TEST-1", captured_at_utc="2026-11-23T01:00:00.000000Z")
    rec.capture_polymarket_snapshot("TOK-TEST-1", captured_at_utc="2026-11-23T01:00:01.000000Z")
    rec.finalize_manifest()
    rec.close()

    res = evaluate_tape_directory(sess)
    assert res["synthetic_fills_present"] is False
    assert res["snapshot_count"] == 2
    assert res["tightest_spread_cents"] == 1
    assert res["widest_spread_cents"] == 2

    root_res = evaluate_observed_l2_root(tmp_path)
    assert root_res["sessions_verified"] == 1
    assert root_res["total_snapshots"] == 2
    assert root_res["venues_covered"] == ["KALSHI", "POLYMARKET"]
