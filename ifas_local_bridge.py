#!/usr/bin/env python3
"""
IFAS Local Accounting Ingestion Bridge (Directive ADR-011 Boundary)
Pulls signed JSON-LD events from PDEUE (/api/v1/accounting/events),
verifies canonical HMAC-SHA256 signatures and ADR-008 integer-cent conservation,
posts idempotent SHA-256 reconciliation receipts (/api/v1/accounting/reconciliation-ack),
and writes an authoritative local ledger + CSV export for GnuCash/CPA ingestion.
"""
from __future__ import annotations

import csv
import hashlib
import hmac
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

DEFAULT_HMAC_SECRET = "pdeue_fge_accounting_signing_key_v1"
SYSTEM_ID = "IFAS_LOCAL_BRIDGE"
FORBIDDEN_BANKING_KEYS = frozenset({
    "account_number", "routing_number", "bank_account",
    "bank_credentials", "iban", "swift_code",
})


def canonicalize_payload(payload: Dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def payload_sha256(payload: Dict[str, Any]) -> str:
    return hashlib.sha256(canonicalize_payload(payload)).hexdigest()


def verify_envelope_signature(envelope: Dict[str, Any], secret_key: str = DEFAULT_HMAC_SECRET) -> bool:
    payload = envelope.get("payload")
    sig = envelope.get("signature_hmac_sha256")
    if not isinstance(payload, dict) or not isinstance(sig, str):
        return False
    expected = hmac.new(secret_key.encode("utf-8"), canonicalize_payload(payload), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig)


def _contains_forbidden_banking_key(obj: Any) -> bool:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if str(k).lower() in FORBIDDEN_BANKING_KEYS or _contains_forbidden_banking_key(v):
                return True
    elif isinstance(obj, list):
        return any(_contains_forbidden_banking_key(item) for item in obj)
    return False


def _validate_integer_cent_conservation(payload: Dict[str, Any]) -> Optional[Dict[str, int]]:
    amounts = payload.get("amounts_cents")
    if amounts is None:
        return None
    if not isinstance(amounts, dict):
        raise ValueError("amounts_cents must be an object")
    keys = ("gross_payout", "scma_net", "cfcp_allocation", "faep_allocation")
    parsed: Dict[str, int] = {}
    for k in keys:
        val = amounts.get(k)
        if isinstance(val, bool) or not isinstance(val, int):
            raise ValueError(f"ADR-008 violation: {k} must be an integer cent value")
        parsed[k] = val
    if parsed["scma_net"] + parsed["cfcp_allocation"] + parsed["faep_allocation"] != parsed["gross_payout"]:
        raise ValueError("ADR-008 integer-cent conservation violation")
    return parsed


def _default_get(url: str) -> Dict[str, Any]:
    req = urllib.request.Request(url, headers={"User-Agent": "IFAS-LocalBridge/2.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _default_post(url: str, body: Dict[str, Any]) -> Dict[str, Any]:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json", "User-Agent": "IFAS-LocalBridge/2.0"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def run_sync(
    node_url: str = "http://127.0.0.1:8000",
    *,
    secret_key: Optional[str] = None,
    ledger_path: Path = Path("ifas_founder_ledger.json"),
    csv_path: Path = Path("ifas_ledger_export.csv"),
    statement_path: Path = Path("ifas_statement.txt"),
    http_client: Any = None,
) -> Dict[str, Any]:
    """Synchronize signed accounting outbox events from PDEUE into the local IFAS ledger."""
    key = secret_key or os.getenv("PDEUE_ACCOUNTING_HMAC_KEY", DEFAULT_HMAC_SECRET)
    base = node_url.rstrip("/")

    if ledger_path.exists():
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    else:
        ledger = {
            "last_sequence_id": 0,
            "ingested_event_ids": [],
            "totals_cents": {"gross_payout": 0, "scma_net": 0, "cfcp_allocation": 0, "faep_allocation": 0},
            "accounts": {},
            "entries": [],
        }

    since_seq = int(ledger.get("last_sequence_id", 0))
    events_url = f"{base}/api/v1/accounting/events?since_seq={since_seq}&limit=200"
    ack_url = f"{base}/api/v1/accounting/reconciliation-ack"

    if http_client is not None:
        resp = http_client.get(events_url)
        resp.raise_for_status()
        data = resp.json()
    else:
        data = _default_get(events_url)

    events = data.get("events", [])
    ingested_count = 0
    rejected_count = 0
    seen_ids = set(ledger["ingested_event_ids"])

    for env in events:
        event_id = env.get("event_id")
        seq_id = env.get("sequence_id")
        payload = env.get("payload", {})

        if event_id in seen_ids:
            continue
        if not verify_envelope_signature(env, secret_key=key):
            rejected_count += 1
            continue
        if _contains_forbidden_banking_key(payload):
            rejected_count += 1
            continue
        try:
            amounts = _validate_integer_cent_conservation(payload)
        except ValueError:
            rejected_count += 1
            continue

        scma_id = str(payload.get("scma_id") or "MASTER")
        entry = {
            "event_id": event_id,
            "sequence_id": seq_id,
            "timestamp": env.get("timestamp"),
            "type": payload.get("@type") or payload.get("event_type") or "AccountingEvent",
            "contract_id": payload.get("contract_id", ""),
            "scma_id": scma_id,
            "gross_payout_cents": amounts["gross_payout"] if amounts else 0,
            "scma_net_cents": amounts["scma_net"] if amounts else 0,
            "cfcp_allocation_cents": amounts["cfcp_allocation"] if amounts else 0,
            "faep_allocation_cents": amounts["faep_allocation"] if amounts else 0,
            "payload_sha256": payload_sha256(payload),
        }

        ack_body = {
            "ack_id": f"IFAS-ACK-{event_id}",
            "sequence_id": int(seq_id),
            "system_id": SYSTEM_ID,
            "received_hash": entry["payload_sha256"],
        }
        if http_client is not None:
            ack_resp = http_client.post(ack_url, json=ack_body)
            ack_resp.raise_for_status()
            ack_result = ack_resp.json()
        else:
            ack_result = _default_post(ack_url, ack_body)

        if not ack_result.get("acknowledged"):
            rejected_count += 1
            continue

        if amounts:
            for k in ("gross_payout", "scma_net", "cfcp_allocation", "faep_allocation"):
                ledger["totals_cents"][k] += amounts[k]
            acct = ledger["accounts"].setdefault(scma_id, {"scma_net_cents": 0, "event_count": 0})
            acct["scma_net_cents"] += amounts["scma_net"]
            acct["event_count"] += 1

        ledger["entries"].append(entry)
        ledger["ingested_event_ids"].append(event_id)
        seen_ids.add(event_id)
        if int(seq_id) > ledger["last_sequence_id"]:
            ledger["last_sequence_id"] = int(seq_id)
        ingested_count += 1

    ledger_path.write_text(json.dumps(ledger, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    fieldnames = [
        "sequence_id", "event_id", "timestamp", "type", "contract_id", "scma_id",
        "gross_payout_cents", "scma_net_cents", "cfcp_allocation_cents", "faep_allocation_cents", "payload_sha256",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in ledger["entries"]:
            writer.writerow(row)

    totals = ledger["totals_cents"]
    statement_lines = [
        "================================================================================",
        "IFAS INDEPENDENT FINANCIAL STATEMENT (ADR-011 AIR-GAPPED GENERAL LEDGER)",
        f"Generated UTC: {datetime.now(timezone.utc).isoformat()}",
        "================================================================================",
        f"Events Reconciled: {len(ledger['entries'])} (Last Seq: {ledger['last_sequence_id']})",
        f"Gross Payouts:     ${totals['gross_payout'] / 100:,.2f} ({totals['gross_payout']} cents)",
        f"SCMA Net (87%):    ${totals['scma_net'] / 100:,.2f} ({totals['scma_net']} cents)",
        f"CFCP Pool (10%):   ${totals['cfcp_allocation'] / 100:,.2f} ({totals['cfcp_allocation']} cents)",
        f"FAEP Pool (3%):    ${totals['faep_allocation'] / 100:,.2f} ({totals['faep_allocation']} cents)",
        "",
    ]
    statement_path.write_text("\n".join(statement_lines), encoding="utf-8")

    return {
        "ingested": ingested_count,
        "rejected": rejected_count,
        "last_sequence_id": ledger["last_sequence_id"],
        "totals_cents": dict(totals),
    }


if __name__ == "__main__":
    node = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
    summary = run_sync(node)
    print(f"[IFAS SYNC COMPLETE] {json.dumps(summary)}")
