#!/usr/bin/env python3
"""
IFAS Local Accounting Ingestion Bridge (Directive ADR-011 Boundary)
Downloads signed vouchers from PDEUE, verifies cryptographic HMAC signatures,
and writes the authoritative local general ledger statement.
"""
import urllib.request
import json
import hmac
import hashlib
import sys
from datetime import datetime, timezone

HMAC_SECRET = b"PDEUE_AIRGAP_SHARED_KEY_2026_RING1"
LOCAL_LEDGER_FILE = "ifas_founder_ledger.json"
STATEMENT_FILE = "ifas_statement.txt"

def verify_voucher(voucher):
    msg = f"{voucher['event_id']}|{voucher['sequence_num']}|{voucher['payload_json']}".encode('utf-8')
    expected_sig = hmac.new(HMAC_SECRET, msg, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected_sig, voucher['signature_hmac'])

def run_sync(node_url="http://127.0.0.1:8000"):
    print(f"[*] Connecting to PDEUE Node at: {node_url}")
    outbox_url = f"{node_url}/api/v1/accounting/outbox"
    try:
        req = urllib.request.Request(outbox_url, headers={"User-Agent": "IFAS-LocalBridge/1.0"})
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode('utf-8'))
    except Exception as e:
        print(f"[!] Connection failed: {e}")
        return

    vouchers = data.get("vouchers", [])
    print(f"[*] Discovered {len(vouchers)} pending signed vouchers.")
    if not vouchers:
        print("[*] Local IFAS ledger is completely up-to-date.")
        return

    try:
        with open(LOCAL_LEDGER_FILE, "r") as f:
            ledger = json.load(f)
    except FileNotFoundError:
        ledger = {"ingested_events": [], "bank_accounts": {}}

    ack_url = f"{node_url}/api/v1/accounting/ack"

    for v in vouchers:
        if not verify_voucher(v):
            print(f"[ALERT] HMAC signature mismatch on {v['event_id']}! Rejecting voucher.")
            continue
        
        payload = json.loads(v["payload_json"])
        cents = payload.get("cents", 0)
        bank_ref = payload.get("bank_ref", "EXT-UNKNOWN")

        if bank_ref not in ledger["bank_accounts"]:
            ledger["bank_accounts"][bank_ref] = {"total_disbursed_cents": 0, "transactions": []}

        ledger["bank_accounts"][bank_ref]["total_disbursed_cents"] += cents
        ledger["bank_accounts"][bank_ref]["transactions"].append({
            "event_id": v["event_id"],
            "type": v["event_type"],
            "tier": payload.get("tier"),
            "cents": cents,
            "dollars": f"${cents/100:,.2f}",
            "reason": payload.get("reason"),
            "timestamp": v["created_at"]
        })
        ledger["ingested_events"].append(v["event_id"])

        ack_payload = json.dumps({"event_id": v["event_id"], "reconciliation_token": "IFAS-ACK-" + v["signature_hmac"][:16]}).encode('utf-8')
        ack_req = urllib.request.Request(ack_url, data=ack_payload, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(ack_req) as ack_resp:
            pass
        
        print(f"  [+] Ingested & Acknowledged: {v['event_id']} | Type: {v['event_type']} | Amount: ${cents/100:,.2f}")

    with open(LOCAL_LEDGER_FILE, "w") as f:
        json.dump(ledger, f, indent=2)

    with open(STATEMENT_FILE, "w") as f:
        f.write("================================================================================\n")
        f.write("IFAS INDEPENDENT FINANCIAL STATEMENT — DELAWARE CUSTODY / FOUNDER BANK RECON\n")
        f.write(f"Generated: {datetime.now(timezone.utc).isoformat()}\n")
        f.write("================================================================================\n\n")
        for acct, info in ledger["bank_accounts"].items():
            f.write(f"Account Token: {acct}\n")
            f.write(f"Total Net Payouts Disbursed: ${info['total_disbursed_cents']/100:,.2f}\n")
            f.write("Transaction Details:\n")
            for t in info["transactions"]:
                f.write(f"  - [{t['timestamp'][:19]}] {t['event_id']} | Tier: {t['tier']} | Amount: {t['dollars']} | Reason: {t['reason']}\n")
            f.write("\n")

    print(f"[*] Authoritative statement written to: {STATEMENT_FILE}")

if __name__ == "__main__":
    node = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
    run_sync(node)
