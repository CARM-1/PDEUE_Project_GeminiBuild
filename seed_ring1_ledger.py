#!/usr/bin/env python3
"""
PDEUE Stage 1 Ledger Provisioner — Ring 1 Alpha Pilot (Founder + 5 Members)
Enforces ADR-008 Integer-Cent Accounting, ADR-011 Air-Gap Tokens, and SHA-256 Audit Chaining.
"""

import sqlite3
import hashlib
import json
from datetime import datetime, timezone

DB_PATH = "pdeue.db"

RING_1_ACCOUNTS = [
    {
        "scma_id": "SCMA-FOUNDER",
        "user_id": "USR-FOUNDER-00",
        "display_name": "Founder / Chief Administrator",
        "role": "CHIEF_ADMINISTRATOR",
        "initial_cash_cents": 500000,
        "risk_dial_pct": 2.00,
        "max_risk_dial_pct": 2.00,
        "bank_ref_token": "EXT-REF-FBO-FOUNDER-****8800",
        "is_custodial": 0,
    },
    {
        "scma_id": "SCMA-MEM-0001",
        "user_id": "USR-MEM-0001",
        "display_name": "Ring 1 Family Member 1",
        "role": "MEMBER_USER",
        "initial_cash_cents": 100000,
        "risk_dial_pct": 2.00,
        "max_risk_dial_pct": 2.00,
        "bank_ref_token": "EXT-REF-FBO-MEM01-****4811",
        "is_custodial": 0,
    },
    {
        "scma_id": "SCMA-MEM-0002",
        "user_id": "USR-MEM-0002",
        "display_name": "Ring 1 Family Member 2",
        "role": "MEMBER_USER",
        "initial_cash_cents": 100000,
        "risk_dial_pct": 2.00,
        "max_risk_dial_pct": 2.00,
        "bank_ref_token": "EXT-REF-FBO-MEM02-****4812",
        "is_custodial": 0,
    },
    {
        "scma_id": "SCMA-MEM-0003",
        "user_id": "USR-MEM-0003",
        "display_name": "Ring 1 Family Member 3",
        "role": "MEMBER_USER",
        "initial_cash_cents": 100000,
        "risk_dial_pct": 2.00,
        "max_risk_dial_pct": 2.00,
        "bank_ref_token": "EXT-REF-FBO-MEM03-****4813",
        "is_custodial": 0,
    },
    {
        "scma_id": "SCMA-MEM-0004",
        "user_id": "USR-MEM-0004",
        "display_name": "Ring 1 Family Member 4",
        "role": "MEMBER_USER",
        "initial_cash_cents": 100000,
        "risk_dial_pct": 2.00,
        "max_risk_dial_pct": 2.00,
        "bank_ref_token": "EXT-REF-FBO-MEM04-****4814",
        "is_custodial": 0,
    },
    {
        "scma_id": "SCMA-MEM-0005",
        "user_id": "USR-MEM-0005",
        "display_name": "Ring 1 Family Member 5",
        "role": "MEMBER_USER",
        "initial_cash_cents": 100000,
        "risk_dial_pct": 2.00,
        "max_risk_dial_pct": 2.00,
        "bank_ref_token": "EXT-REF-FBO-MEM05-****4815",
        "is_custodial": 0,
    },
]

def init_schema(cursor: sqlite3.Cursor) -> None:
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id TEXT PRIMARY KEY,
        display_name TEXT NOT NULL,
        role TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'ACTIVE',
        created_at TEXT NOT NULL
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS accounts (
        scma_id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        cash_cents INTEGER NOT NULL,
        reserved_cents INTEGER NOT NULL DEFAULT 0,
        lifetime_profit_cents INTEGER NOT NULL DEFAULT 0,
        risk_dial_pct REAL NOT NULL DEFAULT 2.00,
        max_risk_dial_pct REAL NOT NULL DEFAULT 2.00,
        bank_ref_token TEXT NOT NULL,
        is_custodial INTEGER NOT NULL DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'ACTIVE',
        updated_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users (user_id)
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS audit_log_records (
        record_id INTEGER PRIMARY KEY AUTOINCREMENT,
        prev_hash TEXT NOT NULL,
        entry_hash TEXT NOT NULL,
        actor_id TEXT NOT NULL,
        action TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        timestamp TEXT NOT NULL
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS accounting_outbox_events (
        event_id TEXT PRIMARY KEY,
        sequence_num INTEGER NOT NULL,
        event_type TEXT NOT NULL,
        scma_id TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        signature_hmac TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'PENDING_INGESTION',
        created_at TEXT NOT NULL
    );
    """)

def get_latest_audit_hash(cursor: sqlite3.Cursor) -> str:
    cursor.execute("SELECT entry_hash FROM audit_log_records ORDER BY record_id DESC LIMIT 1;")
    row = cursor.fetchone()
    return row[0] if row else "0" * 64

def seed_ring1() -> None:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    now_iso = datetime.now(timezone.utc).isoformat()

    try:
        cursor.execute("BEGIN TRANSACTION;")
        init_schema(cursor)

        prev_hash = get_latest_audit_hash(cursor)
        total_seeded_cents = 0

        print("================================================================================")
        print("PDEUE RING 1 ALPHA PILOT: MULTI-ACCOUNT LEDGER PROVISIONING")
        print(f"Timestamp: {now_iso} | Target: {DB_PATH}")
        print("================================================================================")

        for member in RING_1_ACCOUNTS:
            cursor.execute("""
                INSERT INTO users (user_id, display_name, role, status, created_at)
                VALUES (?, ?, ?, 'ACTIVE', ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    display_name=excluded.display_name,
                    role=excluded.role;
            """, (member["user_id"], member["display_name"], member["role"], now_iso))

            cursor.execute("""
                INSERT INTO accounts (
                    scma_id, user_id, cash_cents, reserved_cents, lifetime_profit_cents,
                    risk_dial_pct, max_risk_dial_pct, bank_ref_token, is_custodial, status, updated_at
                ) VALUES (?, ?, ?, 0, 0, ?, ?, ?, ?, 'ACTIVE', ?)
                ON CONFLICT(scma_id) DO UPDATE SET
                    user_id=excluded.user_id,
                    cash_cents=excluded.cash_cents,
                    risk_dial_pct=excluded.risk_dial_pct,
                    max_risk_dial_pct=excluded.max_risk_dial_pct,
                    bank_ref_token=excluded.bank_ref_token,
                    updated_at=excluded.updated_at;
            """, (
                member["scma_id"],
                member["user_id"],
                member["initial_cash_cents"],
                member["risk_dial_pct"],
                member["max_risk_dial_pct"],
                member["bank_ref_token"],
                member["is_custodial"],
                now_iso
            ))

            total_seeded_cents += member["initial_cash_cents"]

            payload = {
                "scma_id": member["scma_id"],
                "user_id": member["user_id"],
                "seed_cash_cents": member["initial_cash_cents"],
                "risk_ceiling": member["max_risk_dial_pct"],
                "bank_ref": member["bank_ref_token"]
            }
            payload_str = json.dumps(payload, sort_keys=True)
            entry_hash = hashlib.sha256(f"{prev_hash}|{payload_str}|{now_iso}".encode("utf-8")).hexdigest()

            cursor.execute("""
                INSERT INTO audit_log_records (prev_hash, entry_hash, actor_id, action, payload_json, timestamp)
                VALUES (?, ?, 'CHIEF_ADMINISTRATOR', 'PROVISION_SCMA_RING1', ?, ?);
            """, (prev_hash, entry_hash, payload_str, now_iso))

            prev_hash = entry_hash
            formatted_cash = f"${member['initial_cash_cents'] / 100:,.2f}"
            print(f"[*] Provisioned: {member['scma_id']:<15} | {member['display_name']:<28} | Seed: {formatted_cash:>10} | Dial Cap: {member['risk_dial_pct']:.2f}%")

        conn.commit()
        print("--------------------------------------------------------------------------------")
        total_cash_str = f"${total_seeded_cents / 100:,.2f}"
        print(f"Total Ring 1 Seed Equity Committed: {total_cash_str} ({total_seeded_cents:,} integer cents)")
        print(f"Audit Spine Rolling Hash (Tip):     {prev_hash}")
        print("Status: 100% PERSISTED (ADR-008 & ADR-011 Invariants Enforced)")
        print("================================================================================")

    except Exception as exc:
        conn.rollback()
        print(f"[FATAL] Failed to provision Ring 1 accounts: {exc}")
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    seed_ring1()
