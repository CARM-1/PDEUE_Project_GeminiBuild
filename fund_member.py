#!/usr/bin/env python3
"""
Turnkey Biweekly Member Funding Script
Usage: python3 fund_member.py <SCMA_ID> <DOLLAR_AMOUNT>
Example: python3 fund_member.py SCMA-MEM-0001 250.00
"""
import sys
import sqlite3
import hashlib
import json
from datetime import datetime, timezone

if len(sys.argv) < 3:
    print("Usage: python3 fund_member.py <SCMA_ID> <DOLLAR_AMOUNT>")
    print("Example: python3 fund_member.py SCMA-MEM-0001 250.00")
    sys.exit(1)

scma_id = sys.argv[1].strip()
try:
    amount_dollars = float(sys.argv[2])
    amount_cents = int(round(amount_dollars * 100))
except ValueError:
    print("Error: Amount must be a valid number (e.g. 250.00)")
    sys.exit(1)

if amount_cents <= 0:
    print("Error: Deposit amount must be greater than zero.")
    sys.exit(1)

DB_PATH = "pdeue.db"
now_iso = datetime.now(timezone.utc).isoformat()
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# Check account exists
cursor.execute("SELECT scma_id, cash_cents, status FROM accounts WHERE scma_id = ?;", (scma_id,))
row = cursor.fetchone()
if not row:
    print(f"Error: Account {scma_id} not found in database.")
    conn.close()
    sys.exit(1)

new_balance_cents = row[1] + amount_cents
cursor.execute("""
    UPDATE accounts 
    SET cash_cents = ?, status = 'ACTIVE', updated_at = ?
    WHERE scma_id = ?;
""", (new_balance_cents, now_iso, scma_id))

# Record to cryptographic audit chain
cursor.execute("SELECT entry_hash FROM audit_log_records ORDER BY record_id DESC LIMIT 1;")
prev_hash = cursor.fetchone()[0]

payload = {
    "scma_id": scma_id,
    "deposit_cents": amount_cents,
    "new_balance_cents": new_balance_cents,
    "status": "ACTIVE"
}
payload_str = json.dumps(payload, sort_keys=True)
entry_hash = hashlib.sha256(f"{prev_hash}|{payload_str}|{now_iso}".encode("utf-8")).hexdigest()

cursor.execute("""
    INSERT INTO audit_log_records (prev_hash, entry_hash, actor_id, action, payload_json, timestamp)
    VALUES (?, ?, 'CHIEF_ADMINISTRATOR', 'BIWEEKLY_MEMBER_DEPOSIT', ?, ?);
""", (prev_hash, entry_hash, payload_str, now_iso))

conn.commit()
conn.close()

print(f"[*] Successfully funded {scma_id} with ${amount_dollars:,.2f} ({amount_cents:,} integer cents).")
print(f"[*] Account status flipped to ACTIVE. Total Balance: ${new_balance_cents / 100:,.2f}")
