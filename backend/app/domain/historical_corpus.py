"""Deterministic, point-in-time corpus used by the walk-forward benchmark.

Prices are integer cents.  Decimal probability fields are model inputs rather
than money and are retained to make the fixture useful to underwriting tests.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List


def get_historical_tick_corpus() -> List[Dict[str, Any]]:
    """Return 48 normalized, chronologically ordered multi-domain decisions.

    Every observation precedes its decision time, so a consumer can enforce
    point-in-time (PIT) access without relying on the order of a dictionary.
    The outcomes are a frozen historical fixture, not a live-data forecast.
    """
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    domains = (
        ("WEATHER", ("KX-MIA-FRZ-32", "KX-ORD-FRZ-32", "KX-NYC-SNOW-6")),
        ("MACROECONOMIC", ("KX-ORD-26", "KX-FED-RATE-25", "KX-CPI-30")),
        ("SPORTS", ("NFL-POINT-SPREAD", "MLB-RUN-LINE", "NFL-MARGIN-GAUSS")),
        ("CRYPTO", ("POLY-239496", "BTC-VOL-BARRIER", "ETH-VOL-BARRIER")),
    )
    ticks: List[Dict[str, Any]] = []
    for index in range(48):
        category, names = domains[index // 12]
        cycle = index % 12
        decision = base + timedelta(hours=index + 1)
        if category == "WEATHER":
            ask_cents, peak, outcome = 15 + (cycle % 4) * 5, (82 if cycle % 2 == 0 else 45), int(cycle % 3 != 0)
        elif category == "MACROECONOMIC":
            ask_cents, peak, outcome = 40 + (cycle % 3) * 8, (88 if cycle % 3 == 0 else 55), int(cycle % 2 == 0)
        elif category == "SPORTS":
            ask_cents, peak, outcome = 45 + (cycle % 2) * 5, (94 if cycle % 2 == 1 else 60), int(cycle % 4 != 0)
        else:
            ask_cents, peak, outcome = 22 + (cycle % 4) * 6, (80 if cycle % 2 == 0 else 30), int(cycle % 3 == 1)
        bid_cents = max(1, ask_cents - 6)
        model_probability_bps = 5000
        contract_root = names[cycle % len(names)]
        ticks.append({
            "sequence": index + 1,
            "contract_id": f"{contract_root}-{cycle + 1:02d}",
            "category": category,
            "distribution": "GAUSSIAN_MARGIN" if category == "SPORTS" else "BINARY_BARRIER",
            "observed_at": (decision - timedelta(minutes=15)).isoformat(),
            "decision_at": decision.isoformat(),
            "resolved_at": (decision + timedelta(hours=8)).isoformat(),
            "yes_bid_cents": 44,
            "yes_ask_cents": 50,
            "model_probability_bps": model_probability_bps,
            "historical_outcome": outcome,
            "taker_fee_bps": 100,
            # Compatibility fields for earlier replay clients.
            "yes_bid": 0.44,
            "yes_ask": 0.50,
            "entry_ask": ask_cents / 100,
            "peak_midpoint": peak / 100,
            "p_model": 0.50,
            "final_payout": float(outcome),
            "outcome": 1,
            "fee_rate": 0.0 if category == "CRYPTO" else 0.01,
        })
    return ticks
