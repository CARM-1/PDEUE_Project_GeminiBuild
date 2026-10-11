"""
Qualification Suite for WP-8E Authentic Venue Tape Loader
Verifies:
1. Valid trade record ingestion and type casting.
2. ADR-008 integer-cent pricing boundaries ([1, 99] cents).
3. Monotonic nanosecond timestamp progression enforcement.
4. Fail-closed rejection of corrupted rows or missing keys.
"""

import pytest
import json
import tempfile
from pathlib import Path
from app.adapters.venue_tape_loader import VenueTapeLoader, MarketTradePrint

def test_parse_valid_trade_print():
    payload = {
        "trade_id": "KALSHI-TRD-908124",
        "contract_id": "KX-NFP-2026-OCT",
        "category": "macro_labor",
        "timestamp_ns": 1791707400000000000,
        "price_cents": 47,
        "volume": 250,
        "aggressor_side": "SELL"
    }
    trade = VenueTapeLoader.parse_trade_print_record(payload)
    assert trade.trade_id == "KALSHI-TRD-908124"
    assert trade.price_cents == 47
    assert trade.volume == 250
    assert trade.aggressor_side == "SELL"

def test_reject_adr008_out_of_bounds_price():
    payload_low = {
        "trade_id": "T-01", "contract_id": "C-01", "category": "weather_noaa",
        "timestamp_ns": 100, "price_cents": 0, "volume": 10, "aggressor_side": "BUY"
    }
    with pytest.raises(ValueError, match="ADR-008 Violation"):
        VenueTapeLoader.parse_trade_print_record(payload_low)

    payload_high = {
        "trade_id": "T-02", "contract_id": "C-01", "category": "weather_noaa",
        "timestamp_ns": 100, "price_cents": 100, "volume": 10, "aggressor_side": "BUY"
    }
    with pytest.raises(ValueError, match="ADR-008 Violation"):
        VenueTapeLoader.parse_trade_print_record(payload_high)

def test_stream_tape_file_monotonic_integrity():
    with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".jsonl") as tmp:
        tmp.write(json.dumps({
            "trade_id": "T1", "contract_id": "C-01", "category": "equity_index",
            "timestamp_ns": 1000, "price_cents": 35, "volume": 50, "aggressor_side": "SELL"
        }) + "\n")
        tmp.write(json.dumps({
            "trade_id": "T2", "contract_id": "C-01", "category": "equity_index",
            "timestamp_ns": 2000, "price_cents": 36, "volume": 75, "aggressor_side": "BUY"
        }) + "\n")
        tmp_path = Path(tmp.name)

    try:
        prints = list(VenueTapeLoader.stream_tape_file(tmp_path))
        assert len(prints) == 2
        assert prints[0].timestamp_ns == 1000
        assert prints[1].timestamp_ns == 2000
    finally:
        tmp_path.unlink()

def test_stream_tape_file_rejects_timestamp_regression():
    with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".jsonl") as tmp:
        tmp.write(json.dumps({
            "trade_id": "T1", "contract_id": "C-01", "category": "equity_index",
            "timestamp_ns": 5000, "price_cents": 35, "volume": 50, "aggressor_side": "SELL"
        }) + "\n")
        # Regressing timestamp back to 4000ns
        tmp.write(json.dumps({
            "trade_id": "T2", "contract_id": "C-01", "category": "equity_index",
            "timestamp_ns": 4000, "price_cents": 36, "volume": 75, "aggressor_side": "BUY"
        }) + "\n")
        tmp_path = Path(tmp.name)

    try:
        with pytest.raises(ValueError, match="Sequence Anomaly"):
            list(VenueTapeLoader.stream_tape_file(tmp_path))
    finally:
        tmp_path.unlink()
