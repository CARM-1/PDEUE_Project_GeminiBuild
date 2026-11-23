"""Strictly read-only live L2 order-book tape recorder & SHA-256 manifest verifier (Gate G1 evidence)."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import httpx

KALSHI_PUBLIC_BASE = "https://api.elections.kalshi.com/trade-api/v2"
POLYMARKET_PUBLIC_BASE = "https://clob.polymarket.com"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _to_price_cents(raw_price: Any, *, venue: str) -> int:
    if isinstance(raw_price, bool):
        raise ValueError("Boolean price rejected")
    if venue == "KALSHI" and isinstance(raw_price, int):
        cents = raw_price
    else:
        try:
            d = Decimal(str(raw_price))
        except InvalidOperation as exc:
            raise ValueError(f"Invalid price: {raw_price}") from exc
        cents_dec = d * Decimal("100") if d <= Decimal("1") else d
        if cents_dec != cents_dec.to_integral_value():
            raise ValueError(f"Non-integer cent price rejected: {raw_price}")
        cents = int(cents_dec)
    if not (1 <= cents <= 99):
        raise ValueError(f"Price cents out of binary range 1..99: {cents}")
    return cents


def _to_int_size(raw_size: Any) -> int:
    if isinstance(raw_size, bool):
        raise ValueError("Boolean size rejected")
    try:
        d = Decimal(str(raw_size))
    except InvalidOperation as exc:
        raise ValueError(f"Invalid size: {raw_size}") from exc
    qty = int(d.to_integral_value())
    if qty < 0:
        raise ValueError(f"Negative depth rejected: {qty}")
    return qty


def normalize_kalshi_l2(ticker: str, payload: Dict[str, Any], source_url: str, captured_at_utc: Optional[str] = None) -> Dict[str, Any]:
    ob = payload.get("orderbook", payload)
    yes_raw = ob.get("yes") or []
    no_raw = ob.get("no") or []
    bids = [[_to_price_cents(p, venue="KALSHI"), _to_int_size(q)] for p, q in yes_raw if _to_int_size(q) > 0]
    # Kalshi NO bids at price p correspond to YES asks at 100 - p
    asks = [[100 - _to_price_cents(p, venue="KALSHI"), _to_int_size(q)] for p, q in no_raw if _to_int_size(q) > 0]
    bids.sort(key=lambda x: x[0], reverse=True)
    asks.sort(key=lambda x: x[0])
    return {
        "venue": "KALSHI",
        "contract_ticker": ticker.strip(),
        "captured_at_utc": captured_at_utc or _utc_now_iso(),
        "source_url": source_url,
        "data_provenance": "OBSERVED_L2",
        "bids": bids,
        "asks": asks,
    }


def normalize_polymarket_l2(token_id: str, payload: Dict[str, Any], source_url: str, captured_at_utc: Optional[str] = None) -> Dict[str, Any]:
    bids_raw = payload.get("bids") or []
    asks_raw = payload.get("asks") or []
    bids = [[_to_price_cents(lv["price"], venue="POLYMARKET"), _to_int_size(lv["size"])] for lv in bids_raw if _to_int_size(lv["size"]) > 0]
    asks = [[_to_price_cents(lv["price"], venue="POLYMARKET"), _to_int_size(lv["size"])] for lv in asks_raw if _to_int_size(lv["size"]) > 0]
    bids.sort(key=lambda x: x[0], reverse=True)
    asks.sort(key=lambda x: x[0])
    return {
        "venue": "POLYMARKET",
        "contract_ticker": token_id.strip(),
        "captured_at_utc": captured_at_utc or _utc_now_iso(),
        "source_url": source_url,
        "data_provenance": "OBSERVED_L2",
        "bids": bids,
        "asks": asks,
    }


class ReadOnlyL2TapeRecorder:
    """Polls public venue L2 order books (GET only, zero auth/order capability) and seals a SHA-256 manifest."""

    def __init__(self, output_dir: Path, http_client: Optional[httpx.Client] = None) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._owns_client = http_client is None
        self.client = http_client or httpx.Client(timeout=10.0)
        self.tape_path = self.output_dir / "tape.jsonl"
        self.manifest_path = self.output_dir / "tape_manifest.json"
        self._records: List[Dict[str, Any]] = []

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def capture_kalshi_snapshot(self, ticker: str, *, captured_at_utc: Optional[str] = None) -> Dict[str, Any]:
        url = f"{KALSHI_PUBLIC_BASE}/markets/{ticker}/orderbook"
        resp = self.client.get(url)
        resp.raise_for_status()
        snap = normalize_kalshi_l2(ticker, resp.json(), source_url=url, captured_at_utc=captured_at_utc)
        self._append(snap)
        return snap

    def capture_polymarket_snapshot(self, token_id: str, *, captured_at_utc: Optional[str] = None) -> Dict[str, Any]:
        url = f"{POLYMARKET_PUBLIC_BASE}/book"
        resp = self.client.get(url, params={"token_id": token_id})
        resp.raise_for_status()
        snap = normalize_polymarket_l2(token_id, resp.json(), source_url=f"{url}?token_id={token_id}", captured_at_utc=captured_at_utc)
        self._append(snap)
        return snap

    def _append(self, snapshot: Dict[str, Any]) -> None:
        line = json.dumps(snapshot, sort_keys=True, separators=(",", ":")) + "\n"
        with self.tape_path.open("a", encoding="utf-8") as fh:
            fh.write(line)
        self._records.append(snapshot)

    def finalize_manifest(self) -> Dict[str, Any]:
        if not self.tape_path.exists() or not self._records:
            raise ValueError("Cannot finalize manifest: zero L2 snapshots captured")
        raw_bytes = self.tape_path.read_bytes()
        digest = hashlib.sha256(raw_bytes).hexdigest()
        manifest = {
            "schema_version": "1.1.0-certified-candidate",
            "data_provenance": "OBSERVED_L2",
            "tape_file": self.tape_path.name,
            "tape_manifest_sha256": digest,
            "snapshot_count": len(self._records),
            "venues": sorted({r["venue"] for r in self._records}),
            "tickers": sorted({r["contract_ticker"] for r in self._records}),
            "first_captured_at_utc": self._records[0]["captured_at_utc"],
            "last_captured_at_utc": self._records[-1]["captured_at_utc"],
            "read_only_capture": True,
            "synthetic_fills_present": False,
        }
        self.manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return manifest


def verify_tape_manifest(manifest_path: Path) -> Dict[str, Any]:
    """Fail-closed verifier for OBSERVED_L2 tape manifests: validates SHA-256, integer cents, and monotonic UTC."""
    mpath = Path(manifest_path)
    manifest = json.loads(mpath.read_text(encoding="utf-8"))
    if manifest.get("data_provenance") != "OBSERVED_L2":
        raise ValueError("Manifest provenance must be OBSERVED_L2")
    if manifest.get("synthetic_fills_present") is not False:
        raise ValueError("Manifest failed zero-synthetic check")
    tape_path = mpath.parent / manifest["tape_file"]
    raw_bytes = tape_path.read_bytes()
    actual_sha = hashlib.sha256(raw_bytes).hexdigest()
    if actual_sha != manifest.get("tape_manifest_sha256"):
        raise ValueError("SHA-256 tamper mismatch between tape_manifest.json and tape.jsonl")

    lines = [ln for ln in raw_bytes.decode("utf-8").splitlines() if ln.strip()]
    if len(lines) != manifest.get("snapshot_count"):
        raise ValueError("Snapshot count mismatch")

    prev_ts: Optional[datetime] = None
    for idx, line in enumerate(lines):
        def _no_float(val: str) -> Any:
            raise ValueError(f"Float rejected in tape line {idx}: {val}")
        rec = json.loads(line, parse_float=_no_float)
        if rec.get("data_provenance") != "OBSERVED_L2":
            raise ValueError(f"Line {idx} is not OBSERVED_L2")
        ts_str = rec["captured_at_utc"]
        ts = datetime.fromisoformat(ts_str[:-1] + "+00:00")
        if prev_ts is not None and ts < prev_ts:
            raise ValueError(f"Non-monotonic timestamp at line {idx}")
        prev_ts = ts
        for side in ("bids", "asks"):
            for price, qty in rec[side]:
                if not (isinstance(price, int) and 1 <= price <= 99 and isinstance(qty, int) and qty > 0):
                    raise ValueError(f"Invalid integer L2 level at line {idx}")
    return manifest
