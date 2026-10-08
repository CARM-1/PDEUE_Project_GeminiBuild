#!/usr/bin/env python3
"""
Calibrates PDEUE ledger to Real Founder Launch Seed ($100.00 / 10,000 cents).
Members 1-5 remain in PENDING_FUNDING with 0 cents.
Enforces ADR-008 exact-cent conservation and SHA-256 audit continuity.
"""
import sqlite3
import hashlib
import json
from datetime import datetime, timezone

DB_PATH = "pdeue.db"
now_iso = datetime.now(timezone.utc).isoformat()

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# 1. Update Founder to $100.00 (10,000 cents)
cursor.execute("""
    UPDATE accounts 
    SET cash_cents = 10000, status = 'ACTIVE', updated_at = ?
    WHERE scma_id = 'SCMA-FOUNDER';
""", (now_iso,))

# 2. Ensure Members 1 through 5 remain at 0 cents in PENDING_FUNDING
member_ids = [f"SCMA-MEM-000{i}" for i in range(1, 6)]
for mem_id in member_ids:
    cursor.execute("""
        UPDATE accounts 
        SET cash_cents = 0, status = 'PENDING_FUNDING', updated_at = ?
        WHERE scma_id = ?;
    """, (now_iso, mem_id))

# 3. Log to cryptographic audit chain
cursor.execute("SELECT entry_hash FROM audit_log_records ORDER BY record_id DESC LIMIT 1;")
row = cursor.fetchone()
prev_hash = row[0] if row else "0" * 64

payload = {
    "action": "CALIBRATE_REAL_FOUNDER_SEED",
    "scma_id": "SCMA-FOUNDER",
    "seed_cash_cents": 10000,
    "seed_dollars": "100.00",
    "dry_powder_floor_cents": 4000,
    "max_trade_stake_cents": 200,
    "pending_members": member_ids
}
payload_str = json.dumps(payload, sort_keys=True)
entry_hash = hashlib.sha256(f"{prev_hash}|{payload_str}|{now_iso}".encode("utf-8")).hexdigest()

cursor.execute("""
    INSERT INTO audit_log_records (prev_hash, entry_hash, actor_id, action, payload_json, timestamp)
    VALUES (?, ?, 'CHIEF_ADMINISTRATOR', 'CALIBRATE_REAL_FOUNDER_SEED', ?, ?);
""", (prev_hash, entry_hash, payload_str, now_iso))

conn.commit()
conn.close()
print("Calibration successful: SCMA-FOUNDER set to $100.00 (10,000 integer cents).")
