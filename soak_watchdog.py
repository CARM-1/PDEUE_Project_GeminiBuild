# -*- coding: utf-8 -*-
"""
PDEUE Sprint 9: 24/7 Endurance Soak Telemetry Watchdog
Polls AWS Lightsail telemetry every 60 seconds, asserts invariant safety,
and persists historical health snapshots to soak_telemetry_history.json.
"""
import urllib.request
import json
import time
import pathlib
from datetime import datetime, timezone

NODE_URL = "http://13.221.153.12"
HISTORY_FILE = pathlib.Path("soak_telemetry_history.json")

def read_telemetry():
    req = urllib.request.Request(f"{NODE_URL}/api/v1/fleet/telemetry", headers={"User-Agent": "PDEUE-Watchdog/1.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))

def log_snapshot(telem):
    history = []
    if HISTORY_FILE.exists():
        try:
            history = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        except Exception:
            history = []

    summary = telem.get("summary", {})
    accounts = telem.get("accounts", [])
    founder = next((a for a in accounts if a.get("scma_id") == "SCMA-FOUNDER"), {})
    angela = next((a for a in accounts if a.get("scma_id") == "SCMA-MEM-0001"), {})

    snapshot = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "live_occupied": summary.get("live_slots_occupied", 0),
        "paper_occupied": summary.get("paper_slots_occupied", 0),
        "founder_cash_cents": founder.get("cash_cents", 0),
        "angela_cash_cents": angela.get("cash_cents", 0),
        "rack_status": [
            {
                "slot": s.get("slot_index"),
                "regime": s.get("regime"),
                "occupied": s.get("is_occupied"),
                "contract": s.get("position", {}).get("contract_ticker") if s.get("is_occupied") else None
            }
            for s in telem.get("rack", [])
        ]
    }

    # Invariant assertion checks
    assert founder.get("cash_cents", 0) >= 5300000, "CRITICAL: Founder cash dropped below safety threshold!"
    
    history.append(snapshot)
    # Retain trailing 1440 entries (24 hours of 1-minute samples)
    if len(history) > 1440:
        history = history[-1440:]

    HISTORY_FILE.write_text(json.dumps(history, indent=2), encoding="utf-8")
    return snapshot

def run_single_probe():
    telem = read_telemetry()
    return log_snapshot(telem)

if __name__ == "__main__":
    print(f"[*] Probing node at {NODE_URL}...")
    snap = run_single_probe()
    print(f"[✓] Snapshot logged at {snap['timestamp']}:")
    print(f"    • Live Slots: {snap['live_occupied']} / 4 | Paper Slots: {snap['paper_occupied']} / 4")
    print(f"    • Founder: ${snap['founder_cash_cents'] / 100:,.2f} | Angela: ${snap['angela_cash_cents'] / 100:,.2f}")
