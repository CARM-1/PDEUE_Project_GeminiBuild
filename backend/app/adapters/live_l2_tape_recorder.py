"""Strictly read-only live L2 order-book tape recorder & SHA-256 manifest verifier (Gate G1 evidence)."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

KALSHI_PUBLIC_BASE = "https://api.elections.kalshi.com/trade-api/v2"
POLYMARKET_PUBLIC_BASE = "https://clob.polymarket.com"
POLYMARKET_GAMMA_BASE = "https://gamma-api.polymarket.com"


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


def _to_float_metric(val: Any) -> float:
    try:
        return float(val) if val is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def normalize_kalshi_l2(
    ticker: str,
    payload: Dict[str, Any],
    source_url: str,
    captured_at_utc: Optional[str] = None,
) -> Dict[str, Any]:
    """Normalize both Kalshi live orderbook_fp (yes_dollars/no_dollars) and legacy orderbook (yes/no)."""
    if "orderbook_fp" in payload and isinstance(payload["orderbook_fp"], dict):
        ob_fp = payload["orderbook_fp"]
        yes_raw = ob_fp.get("yes_dollars") or []
        no_raw = ob_fp.get("no_dollars") or []
    else:
        ob = payload.get("orderbook", payload)
        yes_raw = ob.get("yes") or ob.get("yes_dollars") or []
        no_raw = ob.get("no") or ob.get("no_dollars") or []

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


def normalize_polymarket_l2(
    token_id: str,
    payload: Dict[str, Any],
    source_url: str,
    captured_at_utc: Optional[str] = None,
) -> Dict[str, Any]:
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


def discover_liquid_kalshi_tickers(
    http_client: Optional[httpx.Client] = None,
    limit: int = 5,
    events_limit: int = 50,
) -> List[str]:
    """Discover active, non-combo Kalshi single-event tickers ranked by live volume_24h_fp & open_interest_fp."""
    owns = http_client is None
    client = http_client or httpx.Client(timeout=15.0)
    try:
        resp = client.get(
            f"{KALSHI_PUBLIC_BASE}/events",
            params={"status": "open", "with_nested_markets": "true", "limit": events_limit},
        )
        resp.raise_for_status()
        events = resp.json().get("events", [])
        markets = [
            m for ev in events for m in ev.get("markets", [])
            if m.get("ticker") and not str(m["ticker"]).startswith("KXMVE")
        ]
        markets.sort(
            key=lambda m: (
                _to_float_metric(m.get("volume_24h_fp", m.get("volume_24h"))),
                _to_float_metric(m.get("open_interest_fp", m.get("open_interest"))),
                _to_float_metric(m.get("volume_fp", m.get("volume"))),
            ),
            reverse=True,
        )
        return [str(m["ticker"]) for m in markets[:limit]]
    finally:
        if owns:
            client.close()


def extract_polymarket_clob_token_ids(raw: Any) -> List[str]:
    """Extract full-precision Polymarket CLOB token ID strings without truncation."""
    if raw is None:
        return []
    parsed: Any = raw
    if isinstance(raw, str):
        stripped = raw.strip()
        if not stripped:
            return []
        if stripped.startswith("["):
            try:
                parsed = json.loads(stripped)
            except (ValueError, json.JSONDecodeError):
                return []
        elif stripped.startswith("{"):
            return []
        else:
            parsed = [part.strip() for part in stripped.split(",") if part.strip()]
    if not isinstance(parsed, (list, tuple)):
        return []

    tokens: List[str] = []
    seen: set[str] = set()
    for item in parsed:
        if item is None or isinstance(item, (bool, float, dict, list)):
            continue
        tok = str(item).strip()
        if tok and tok not in seen:
            seen.add(tok)
            tokens.append(tok)
    return tokens


def _verify_polymarket_orderbook(
    client: httpx.Client,
    token_id: str,
    *,
    require_non_empty_book: bool = True,
) -> bool:
    """Verify a Polymarket CLOB token returns HTTP 200 with a valid ADR-008 integer-cent book."""
    url = f"{POLYMARKET_PUBLIC_BASE}/book"
    try:
        resp = client.get(url, params={"token_id": token_id})
    except (httpx.TimeoutException, httpx.RequestError):
        return False
    if resp.status_code == 429:
        resp.raise_for_status()
    if resp.status_code != 200:
        return False
    try:
        payload = resp.json()
    except ValueError:
        return False
    if not isinstance(payload, dict):
        return False
    try:
        snap = normalize_polymarket_l2(token_id, payload, source_url=f"{url}?token_id={token_id}")
    except (ValueError, KeyError, TypeError):
        return False
    if require_non_empty_book and not snap["bids"] and not snap["asks"]:
        return False
    return True


def _extract_sampling_market_token_groups(payload: Any) -> List[List[str]]:
    """Extract active order-book-enabled token ID groups from CLOB /sampling-markets payload."""
    rows = payload.get("data", []) if isinstance(payload, dict) else (payload if isinstance(payload, list) else [])
    groups: List[List[str]] = []
    for market in rows:
        if not isinstance(market, dict):
            continue
        if (
            market.get("closed") is True
            or market.get("archived") is True
            or market.get("active") is False
            or market.get("enable_order_book") is False
            or market.get("accepting_orders") is False
        ):
            continue
        raw_tokens = market.get("tokens") or []
        if not isinstance(raw_tokens, list):
            continue
        group: List[str] = []
        seen: set[str] = set()
        for entry in raw_tokens:
            if not isinstance(entry, dict):
                continue
            raw_id = entry.get("token_id")
            if raw_id is None or isinstance(raw_id, (bool, float, dict, list)):
                continue
            tok = str(raw_id).strip()
            if tok and tok not in seen:
                seen.add(tok)
                group.append(tok)
        if group:
            groups.append(group)
    return groups


def discover_liquid_polymarket_tokens(
    http_client: Optional[httpx.Client] = None,
    limit: int = 5,
    *,
    verify_orderbook: bool = True,
    require_non_empty_book: bool = True,
    exclude_tokens: Optional[set[str]] = None,
) -> List[str]:
    """Discover active, order-book-enabled Polymarket CLOB token IDs verified against /book."""
    target_limit = max(0, int(limit))
    if target_limit == 0:
        return []

    excluded = {str(t).strip() for t in (exclude_tokens or set()) if str(t).strip()}
    owns = http_client is None
    client = http_client or httpx.Client(timeout=15.0)
    try:
        tokens: List[str] = []
        checked: set[str] = set()
        gamma_error: Optional[Exception] = None

        def _collect_from_groups(groups: List[List[str]]) -> None:
            for candidate_group in groups:
                for tok in candidate_group:
                    if tok in excluded or tok in checked or tok in tokens:
                        continue
                    checked.add(tok)
                    if not verify_orderbook or _verify_polymarket_orderbook(
                        client,
                        tok,
                        require_non_empty_book=require_non_empty_book,
                    ):
                        tokens.append(tok)
                        break  # At most one verified outcome token per market for diversity
                if len(tokens) >= target_limit:
                    break

        try:
            resp = client.get(
                f"{POLYMARKET_GAMMA_BASE}/markets",
                params={
                    "active": "true",
                    "closed": "false",
                    "archived": "false",
                    "enableOrderBook": "true",
                    "limit": max(target_limit * 10, 25),
                    "order": "volume24hr",
                    "ascending": "false",
                },
            )
            resp.raise_for_status()
            markets = resp.json()
            gamma_groups: List[List[str]] = []
            if isinstance(markets, list):
                for m in markets:
                    if not isinstance(m, dict):
                        continue
                    if (
                        m.get("closed") is True
                        or m.get("archived") is True
                        or m.get("active") is False
                        or m.get("enableOrderBook") is False
                        or m.get("acceptingOrders") is False
                    ):
                        continue
                    group = extract_polymarket_clob_token_ids(m.get("clobTokenIds"))
                    if group:
                        gamma_groups.append(group)
            _collect_from_groups(gamma_groups)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429:
                raise
            gamma_error = exc
        except (httpx.TimeoutException, httpx.RequestError, ValueError) as exc:
            gamma_error = exc

        if len(tokens) < target_limit:
            try:
                sampling_resp = client.get(f"{POLYMARKET_PUBLIC_BASE}/sampling-markets")
                if sampling_resp.status_code == 429:
                    sampling_resp.raise_for_status()
                if sampling_resp.status_code == 200:
                    _collect_from_groups(_extract_sampling_market_token_groups(sampling_resp.json()))
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 429:
                    raise
            except (httpx.TimeoutException, httpx.RequestError, ValueError):
                pass

        if not tokens and gamma_error is not None:
            raise gamma_error
        return tokens
    finally:
        if owns:
            client.close()


class ReadOnlyL2TapeRecorder:
    """Polls public venue L2 order books (GET only, zero auth/order capability) and seals a SHA-256 manifest."""

    def __init__(
        self,
        output_dir: Path,
        http_client: Optional[httpx.Client] = None,
        require_non_empty_book: bool = True,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._owns_client = http_client is None
        self.client = http_client or httpx.Client(timeout=10.0)
        self.require_non_empty_book = bool(require_non_empty_book)
        self.tape_path = self.output_dir / "tape.jsonl"
        self.manifest_path = self.output_dir / "tape_manifest.json"
        self._records: List[Dict[str, Any]] = []

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def _enforce_depth(self, snap: Dict[str, Any]) -> None:
        if self.require_non_empty_book and not snap["bids"] and not snap["asks"]:
            raise ValueError(f"Empty L2 order book rejected for {snap['venue']}:{snap['contract_ticker']}")

    def capture_kalshi_snapshot(self, ticker: str, *, captured_at_utc: Optional[str] = None) -> Dict[str, Any]:
        url = f"{KALSHI_PUBLIC_BASE}/markets/{ticker}/orderbook"
        resp = self.client.get(url)
        resp.raise_for_status()
        snap = normalize_kalshi_l2(ticker, resp.json(), source_url=url, captured_at_utc=captured_at_utc)
        self._enforce_depth(snap)
        self._append(snap)
        return snap

    def capture_polymarket_snapshot(self, token_id: str, *, captured_at_utc: Optional[str] = None) -> Dict[str, Any]:
        url = f"{POLYMARKET_PUBLIC_BASE}/book"
        resp = self.client.get(url, params={"token_id": token_id})
        resp.raise_for_status()
        snap = normalize_polymarket_l2(token_id, resp.json(), source_url=f"{url}?token_id={token_id}", captured_at_utc=captured_at_utc)
        self._enforce_depth(snap)
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


def verify_tape_manifest(manifest_path: Path, *, require_non_empty_book: bool = True) -> Dict[str, Any]:
    """Fail-closed verifier for OBSERVED_L2 tape manifests: validates SHA-256, integer cents, depth, and monotonic UTC."""
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
        if require_non_empty_book and not rec["bids"] and not rec["asks"]:
            raise ValueError(f"Empty L2 order book at line {idx}")
        for side in ("bids", "asks"):
            for price, qty in rec[side]:
                if not (isinstance(price, int) and 1 <= price <= 99 and isinstance(qty, int) and qty > 0):
                    raise ValueError(f"Invalid integer L2 level at line {idx}")
    return manifest
