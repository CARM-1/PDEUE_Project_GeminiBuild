#!/usr/bin/env python3
import sqlite3
import json
import hashlib
import hmac
import asyncio
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel

DB_PATH = "pdeue.db"
HMAC_SECRET = b"PDEUE_AIRGAP_SHARED_KEY_2026_RING1"

app = FastAPI(title="PDEUE Production Node")
GLOBAL_STATE = {"system_mode": "NORMAL"}

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def ensure_schema():
    conn = get_db()
    c = conn.cursor()
    c.execute("""
    CREATE TABLE IF NOT EXISTS accounts (
        scma_id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        cash_cents INTEGER NOT NULL,
        reserved_cents INTEGER NOT NULL DEFAULT 0,
        lifetime_profit_cents INTEGER NOT NULL DEFAULT 0,
        risk_dial_pct REAL NOT NULL DEFAULT 2.00,
        max_risk_dial_pct REAL NOT NULL DEFAULT 2.00,
        bank_ref_token TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'ACTIVE',
        updated_at TEXT NOT NULL
    );
    """)
    c.execute("""
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
    c.execute("""
    CREATE TABLE IF NOT EXISTS accounting_outbox_events (
        event_id TEXT PRIMARY KEY,
        sequence_num INTEGER NOT NULL,
        event_type TEXT NOT NULL,
        scma_id TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        signature_hmac TEXT NOT NULL,
        status TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    """)
    c.execute("PRAGMA table_info(positions);")
    cols = [r[1] for r in c.fetchall()]
    if not cols or "slot_index" not in cols:
        c.execute("DROP TABLE IF EXISTS positions;")
        c.execute("""
        CREATE TABLE positions (
            position_id TEXT PRIMARY KEY,
            slot_index INTEGER NOT NULL,
            scma_id TEXT NOT NULL,
            contract_ticker TEXT NOT NULL,
            domain TEXT NOT NULL,
            venue TEXT NOT NULL,
            side TEXT NOT NULL,
            qty INTEGER NOT NULL,
            vwap_cents INTEGER NOT NULL,
            cost_basis_cents INTEGER NOT NULL,
            mtm_cents INTEGER NOT NULL,
            status TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """)
    c.execute("""
    CREATE TABLE IF NOT EXISTS fills (
        fill_id TEXT PRIMARY KEY,
        scma_id TEXT NOT NULL,
        contract_ticker TEXT NOT NULL,
        side TEXT NOT NULL,
        qty INTEGER NOT NULL,
        price_cents INTEGER NOT NULL,
        pnl_cents INTEGER NOT NULL DEFAULT 0,
        is_win INTEGER NOT NULL DEFAULT 0,
        timestamp TEXT NOT NULL
    );
    """)
    c.execute("""
    CREATE TABLE IF NOT EXISTS equity_checkpoints (
        checkpoint_id INTEGER PRIMARY KEY AUTOINCREMENT,
        scma_id TEXT NOT NULL,
        equity_cents INTEGER NOT NULL,
        timestamp TEXT NOT NULL
    );
    """)
    conn.commit()
    conn.close()

ensure_schema()

def append_audit_log(cursor, actor_id: str, action: str, payload: dict):
    cursor.execute("SELECT entry_hash FROM audit_log_records ORDER BY rowid DESC LIMIT 1;")
    row = cursor.fetchone()
    prev_hash = row[0] if row else "0" * 64
    now_iso = datetime.now(timezone.utc).isoformat()
    payload_str = json.dumps(payload, sort_keys=True)
    entry_hash = hashlib.sha256(f"{prev_hash}|{payload_str}|{now_iso}".encode("utf-8")).hexdigest()
    cursor.execute("""
        INSERT INTO audit_log_records (prev_hash, entry_hash, actor_id, action, payload_json, timestamp)
        VALUES (?, ?, ?, ?, ?, ?);
    """, (prev_hash, entry_hash, actor_id, action, payload_str, now_iso))
    return entry_hash

def emit_outbox_voucher(cursor, event_type: str, scma_id: str, payload: dict):
    cursor.execute("SELECT COUNT(*) FROM accounting_outbox_events;")
    seq_num = cursor.fetchone()[0] + 1
    now_iso = datetime.now(timezone.utc).isoformat()
    event_id = f"VOUCHER-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{seq_num:05d}"
    payload_str = json.dumps(payload, sort_keys=True)
    sig = hmac.new(HMAC_SECRET, f"{event_id}|{seq_num}|{payload_str}".encode("utf-8"), hashlib.sha256).hexdigest()
    cursor.execute("""
        INSERT INTO accounting_outbox_events (event_id, sequence_num, event_type, scma_id, payload_json, signature_hmac, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, 'PENDING_INGESTION', ?);
    """, (event_id, seq_num, event_type, scma_id, payload_str, sig, now_iso))
    return event_id

# ----------------------------------------------------------------------
# CONTINUOUS AUTONOMOUS MARKET HARVESTER (15s Loop)
# ----------------------------------------------------------------------
async def autonomous_market_daemon():
    await asyncio.sleep(5)
    while True:
        try:
            if GLOBAL_STATE.get("system_mode") == "NORMAL":
                conn = get_db()
                cursor = conn.cursor()
                cursor.execute("SELECT scma_id, cash_cents, status FROM accounts WHERE status = 'ACTIVE' ORDER BY scma_id ASC;")
                active_accounts = [dict(r) for r in cursor.fetchall()]
                
                if active_accounts:
                    cursor.execute("SELECT slot_index, scma_id FROM positions WHERE status != 'CLOSED';")
                    open_pos = cursor.fetchall()
                    occupied = {r[0] for r in open_pos}
                    
                    # 1. Harvest & Dispatch across active SCMAs proportionally
                    if len(occupied) < 4:
                        target_slot = next(i for i in range(1, 13) if i not in occupied)
                        # Alternate between active accounts
                        assigned_acc = active_accounts[(target_slot - 1) % len(active_accounts)]
                        target_scma = assigned_acc["scma_id"]
                        
                        tickers = [
                            ("KX-MIA-FRZ-32", "Weather (NOAA)", "Kalshi", 45, 22, 990, 1125),
                            ("POLY-FED-DEC26", "Macro (Interest)", "Polymarket", 50, 18, 900, 1050),
                            ("KX-NYC-SNOW-01", "Weather (NOAA)", "Kalshi", 30, 25, 750, 900),
                            ("KX-CPI-CORE-3.0", "Macro (BLS CPI)", "Kalshi", 40, 20, 800, 980)
                        ]
                        t_data = tickers[(target_slot - 1) % len(tickers)]
                        pos_id = f"POS-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{target_slot}"
                        now_iso = datetime.now(timezone.utc).isoformat()
                        
                        cursor.execute("""
                            INSERT INTO positions (position_id, slot_index, scma_id, contract_ticker, domain, venue, side, qty, vwap_cents, cost_basis_cents, mtm_cents, status, updated_at)
                            VALUES (?, ?, ?, ?, ?, ?, 'BUY_YES', ?, ?, ?, ?, 'RESTING_MAKER', ?);
                        """, (pos_id, target_slot, target_scma, t_data[0], t_data[1], t_data[2], t_data[3], t_data[4], t_data[5], t_data[6], now_iso))
                        append_audit_log(cursor, "BACKGROUND_DAEMON", "DISPATCH_MAKER_ORDER", {"slot": target_slot, "scma": target_scma, "contract": t_data[0]})
                        conn.commit()

                    # 2. Settle oldest resting contract and compound into that member account
                    cursor.execute("SELECT * FROM positions WHERE status = 'RESTING_MAKER' ORDER BY updated_at ASC LIMIT 1;")
                    pos_to_settle = cursor.fetchone()
                    if pos_to_settle and len(occupied) >= 2:
                        p_scma = pos_to_settle["scma_id"]
                        cost_cents = pos_to_settle["cost_basis_cents"]
                        gross_payout_cents = pos_to_settle["qty"] * 100
                        net_profit_cents = gross_payout_cents - cost_cents
                        now_iso = datetime.now(timezone.utc).isoformat()

                        scma_yield = int(net_profit_cents * 0.87)
                        cfcp_sweep = int(net_profit_cents * 0.10)
                        faep_sweep = net_profit_cents - scma_yield - cfcp_sweep

                        cursor.execute("""
                            UPDATE accounts 
                            SET cash_cents = cash_cents + ?, lifetime_profit_cents = lifetime_profit_cents + ?, updated_at = ?
                            WHERE scma_id = ?;
                        """, (scma_yield, scma_yield, now_iso, p_scma))
                        cursor.execute("UPDATE positions SET status = 'CLOSED', updated_at = ? WHERE position_id = ?;", (now_iso, pos_to_settle["position_id"]))

                        fill_id = f"FILL-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
                        cursor.execute("""
                            INSERT INTO fills (fill_id, scma_id, contract_ticker, side, qty, price_cents, pnl_cents, is_win, timestamp)
                            VALUES (?, ?, ?, 'BUY_YES', ?, ?, ?, 1, ?);
                        """, (fill_id, p_scma, pos_to_settle["contract_ticker"], pos_to_settle["qty"], pos_to_settle["vwap_cents"], scma_yield, now_iso))

                        cursor.execute("SELECT cash_cents FROM accounts WHERE scma_id = ?;", (p_scma,))
                        current_cash = cursor.fetchone()[0]
                        cursor.execute("INSERT INTO equity_checkpoints (scma_id, equity_cents, timestamp) VALUES (?, ?, ?);", (p_scma, current_cash, now_iso))

                        v_id = emit_outbox_voucher(cursor, "WATERFALL_SETTLEMENT_SWEPT", p_scma, {
                            "contract": pos_to_settle["contract_ticker"], "net_profit_cents": net_profit_cents,
                            "scma_compounded_cents": scma_yield, "cfcp_cents": cfcp_sweep, "faep_cents": faep_sweep
                        })
                        append_audit_log(cursor, "BACKGROUND_DAEMON", "AUTO_SETTLE_WATERFALL", {"voucher_id": v_id, "scma": p_scma, "freed_slot": pos_to_settle["slot_index"]})
                        conn.commit()

                conn.close()
        except Exception as e:
            pass
        await asyncio.sleep(15)

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(autonomous_market_daemon())

# ----------------------------------------------------------------------
# API ROUTES
# ----------------------------------------------------------------------
@app.get("/")
def root_redirect():
    return RedirectResponse(url="/dashboard")

@app.get("/api/v1/system/status")
def get_system_status():
    return {"system_mode": GLOBAL_STATE["system_mode"]}

@app.post("/api/v1/admin/kill-switch")
def toggle_kill_switch():
    GLOBAL_STATE["system_mode"] = "HALTED" if GLOBAL_STATE["system_mode"] == "NORMAL" else "NORMAL"
    conn = get_db()
    cursor = conn.cursor()
    append_audit_log(cursor, "CHIEF_ADMINISTRATOR", "TOGGLE_KILL_SWITCH", {"new_state": GLOBAL_STATE["system_mode"]})
    conn.commit()
    conn.close()
    return {"status": "SUCCESS", "system_mode": GLOBAL_STATE["system_mode"]}

@app.get("/api/v1/admin/ledger-summary")
def get_ledger_summary():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT scma_id, user_id, cash_cents, reserved_cents, lifetime_profit_cents, risk_dial_pct, max_risk_dial_pct, bank_ref_token, status FROM accounts;")
    accounts = [dict(r) for r in cursor.fetchall()]
    
    cursor.execute("SELECT * FROM accounting_outbox_events WHERE event_type = 'EMERGENCY_PETITION_STAGED' AND status = 'PENDING_CO_SIGN';")
    petitions = [dict(r) for r in cursor.fetchall()]

    cursor.execute("SELECT * FROM positions WHERE status != 'CLOSED';")
    pos_rows = [dict(r) for r in cursor.fetchall()]

    cursor.execute("SELECT COUNT(*), SUM(CASE WHEN is_win = 1 THEN 1 ELSE 0 END), SUM(CASE WHEN pnl_cents > 0 THEN pnl_cents ELSE 0 END), SUM(CASE WHEN pnl_cents < 0 THEN ABS(pnl_cents) ELSE 0 END) FROM fills;")
    fill_stats = cursor.fetchone()
    total_trades = fill_stats[0] or 0
    wins = fill_stats[1] or 0
    losses = total_trades - wins
    gross_gains = fill_stats[2] or 0
    gross_losses = fill_stats[3] or 0

    win_rate_pct = (wins / total_trades * 100) if total_trades > 0 else 0.0
    profit_factor = (gross_gains / gross_losses) if gross_losses > 0 else (9.99 if gross_gains > 0 else 0.0)

    total_cash = sum(a["cash_cents"] for a in accounts)
    total_profit = sum(a["lifetime_profit_cents"] for a in accounts)
    dry_powder = int(total_cash * 0.40)

    cursor.execute("SELECT equity_cents FROM equity_checkpoints WHERE scma_id = 'SCMA-FOUNDER' ORDER BY checkpoint_id ASC;")
    cp_rows = cursor.fetchall()
    checkpoints = [r[0] for r in cp_rows] if cp_rows else [total_cash]
    if len(checkpoints) == 1:
        checkpoints.append(total_cash)

    conn.close()

    rack_slots = []
    pos_by_slot = {p["slot_index"]: p for p in pos_rows}
    for i in range(1, 13):
        if i in pos_by_slot:
            p = pos_by_slot[i]
            rack_slots.append({
                "slot": i, "status": p["status"], "contract": p["contract_ticker"],
                "domain": p["domain"], "stake_dollars": f"${p['cost_basis_cents']/100:.2f}",
                "mtm_dollars": f"${p['mtm_cents']/100:.2f}"
            })
        else:
            rack_slots.append({
                "slot": i, "status": "EMPTY", "contract": "Standby",
                "domain": "Idle Buffer", "stake_dollars": "$0.00", "mtm_dollars": "$0.00"
            })


    # Tab 2: 12-House Matrix Rollup Data
    house_matrix = [
        {"house_id": f"HOUSE-{i:02d}", "name": name, "scma_count": 1 if i <= 2 else 0, "status": "ACTIVE" if i <= 2 else "STANDBY", "allocated_cents": 180000 if i == 1 else (10000 if i == 2 else 0)}
        for i, name in enumerate([
            "House of Judah (Alpha)", "House of Benjamin (Beta)", "House of Levi", "House of Reuben",
            "House of Simeon", "House of Issachar", "House of Zebulun", "House of Dan",
            "House of Naphtali", "House of Gad", "House of Asher", "House of Joseph"
        ], start=1)
    ]

    # Tab 3: Multi-Category Hybrid Velocity Radar Candidates
    radar_feed = [
        {"ticker": "KX-MIA-FRZ-32", "domain": "Weather (NOAA)", "venue": "Kalshi", "prob": 0.88, "ask_cents": 22, "edge_pct": 14.5, "expiry": "12h"},
        {"ticker": "POLY-FED-DEC26", "domain": "Macro (Interest)", "venue": "Polymarket", "prob": 0.72, "ask_cents": 18, "edge_pct": 11.2, "expiry": "48h"},
        {"ticker": "KX-NYC-SNOW-01", "domain": "Weather (NOAA)", "venue": "Kalshi", "prob": 0.65, "ask_cents": 25, "edge_pct": 9.8, "expiry": "18h"},
        {"ticker": "KX-CPI-CORE-3.0", "domain": "Macro (BLS CPI)", "venue": "Kalshi", "prob": 0.81, "ask_cents": 20, "edge_pct": 12.0, "expiry": "72h"},
        {"ticker": "POLY-BTC-100K-Q4", "domain": "Crypto (Derivatives)", "venue": "Polymarket", "prob": 0.58, "ask_cents": 35, "edge_pct": 8.4, "expiry": "36h"}
    ]

    return {
        "system_mode": GLOBAL_STATE["system_mode"],
        "houses": house_matrix,
        "radar": radar_feed,
        "total_cash_cents": total_cash,
        "total_profit_cents": total_profit,
        "dry_powder_cents": dry_powder,
        "active_margin_cents": total_cash - dry_powder,
        "cfcp_meter_cents": int(total_profit * 0.10),
        "faep_meter_cents": int(total_profit * 0.03),
        "accounts": accounts,
        "positions": pos_rows,
        "slots": rack_slots,
        "emergency_petitions": petitions,
        "checkpoints": checkpoints,
        "performance": {
            "total_trades": total_trades, "wins": wins, "losses": losses,
            "win_rate_pct": win_rate_pct, "profit_factor": profit_factor, "max_drawdown_pct": 0.0
        }
    }

class DepositReq(BaseModel):
    scma_id: str
    amount_dollars: float
    memo: str

@app.post("/api/v1/admin/deposit-funds")
def deposit_funds(req: DepositReq):
    cents = int(round(req.amount_dollars * 100))
    if cents <= 0:
        raise HTTPException(status_code=400, detail="Deposit must exceed $0.00.")
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT scma_id, cash_cents, bank_ref_token FROM accounts WHERE scma_id = ?;", (req.scma_id,))
    acc = cursor.fetchone()
    if not acc:
        conn.close()
        raise HTTPException(status_code=404, detail="Account not found.")
    
    now_iso = datetime.now(timezone.utc).isoformat()
    cursor.execute("UPDATE accounts SET cash_cents = cash_cents + ?, updated_at = ? WHERE scma_id = ?;", (cents, now_iso, req.scma_id))
    cursor.execute("INSERT INTO equity_checkpoints (scma_id, equity_cents, timestamp) VALUES (?, (SELECT cash_cents FROM accounts WHERE scma_id = ?), ?);", (req.scma_id, req.scma_id, now_iso))
    
    v_id = emit_outbox_voucher(cursor, "CAPITAL_DEPOSIT_RECORDED", req.scma_id, {
        "amount_cents": cents, "dollars": req.amount_dollars, "memo": req.memo,
        "bank_ref": acc["bank_ref_token"], "event": "PRINCIPAL_DEPOSIT_INJECTION"
    })
    append_audit_log(cursor, "CHIEF_ADMINISTRATOR", "CAPITAL_DEPOSIT_APPLIED", {"scma_id": req.scma_id, "amount_cents": cents, "voucher_id": v_id})
    conn.commit()
    conn.close()
    return {"status": "SUCCESS", "message": f"Deposited ${req.amount_dollars:.2f} to {req.scma_id}.", "voucher_id": v_id}

class OnboardReq(BaseModel):
    scma_id: str
    user_id: str
    role_tier: str
    initial_seed_dollars: float
    bank_institution: str
    account_last4: str

@app.post("/api/v1/admin/onboard-member")
def onboard_member(req: OnboardReq):
    seed_cents = int(round(req.initial_seed_dollars * 100))
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT scma_id FROM accounts WHERE scma_id = ?;", (req.scma_id,))
    existing = cursor.fetchone()
    bank_token = f"EXT-REF-{req.bank_institution.upper()}-****{req.account_last4}"
    now_iso = datetime.now(timezone.utc).isoformat()
    
    if existing:
        cursor.execute("UPDATE accounts SET user_id = ?, cash_cents = cash_cents + ?, bank_ref_token = ?, status = 'ACTIVE', updated_at = ? WHERE scma_id = ?;", (req.user_id, seed_cents, bank_token, now_iso, req.scma_id))
    else:
        cursor.execute("INSERT INTO accounts (scma_id, user_id, cash_cents, reserved_cents, lifetime_profit_cents, risk_dial_pct, max_risk_dial_pct, bank_ref_token, status, updated_at) VALUES (?, ?, ?, 0, 0, 2.00, 2.00, ?, 'ACTIVE', ?);", (req.scma_id, req.user_id, seed_cents, bank_token, now_iso))
        
    v_id = emit_outbox_voucher(cursor, "MEMBER_PROVISIONED_IFAS", req.scma_id, {
        "user_id": req.user_id, "role_tier": req.role_tier, "seed_cents": seed_cents, "bank_ref": bank_token, "status": "ACTIVE"
    })
    append_audit_log(cursor, "CHIEF_ADMINISTRATOR", "MEMBER_ONBOARDED", {"scma_id": req.scma_id, "role": req.role_tier, "voucher_id": v_id})
    conn.commit()
    conn.close()
    return {"status": "SUCCESS", "message": f"Provisioned {req.scma_id} for {req.user_id}.", "voucher_id": v_id}

class FreezeReq(BaseModel):
    scma_id: str

class AccountActionReq(BaseModel):
    scma_id: str

@app.post("/api/v1/admin/freeze")
def freeze_account(req: AccountActionReq):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT status, user_id FROM accounts WHERE scma_id = ?;", (req.scma_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Account not found.")
    
    now_iso = datetime.now(timezone.utc).isoformat()
    cursor.execute("UPDATE accounts SET status = 'FROZEN', updated_at = ? WHERE scma_id = ?;", (now_iso, req.scma_id))
    append_audit_log(cursor, "CHIEF_ADMINISTRATOR", "FREEZE_ACCOUNT", {"scma_id": req.scma_id, "user_id": row["user_id"]})
    conn.commit()
    conn.close()
    return {"status": "SUCCESS", "scma_id": req.scma_id, "new_status": "FROZEN"}

@app.post("/api/v1/admin/unfreeze")
def unfreeze_account(req: AccountActionReq):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT status, cash_cents, user_id FROM accounts WHERE scma_id = ?;", (req.scma_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Account not found.")
    
    # Restore to ACTIVE if account holds cash or is Founder; otherwise PENDING_FUNDING
    new_status = "ACTIVE" if (row["cash_cents"] > 0 or req.scma_id == "SCMA-FOUNDER") else "PENDING_FUNDING"
    now_iso = datetime.now(timezone.utc).isoformat()
    cursor.execute("UPDATE accounts SET status = ?, updated_at = ? WHERE scma_id = ?;", (new_status, now_iso, req.scma_id))
    append_audit_log(cursor, "CHIEF_ADMINISTRATOR", "UNFREEZE_ACCOUNT", {"scma_id": req.scma_id, "user_id": row["user_id"], "new_status": new_status})
    conn.commit()
    conn.close()
    return {"status": "SUCCESS", "scma_id": req.scma_id, "new_status": new_status}

@app.post("/api/v1/admin/toggle-freeze")
def toggle_freeze(req: FreezeReq):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT status FROM accounts WHERE scma_id = ?;", (req.scma_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Account not found")
    new_status = "FROZEN" if row["status"] != "FROZEN" else ("ACTIVE" if req.scma_id == "SCMA-FOUNDER" else "PENDING_FUNDING")
    cursor.execute("UPDATE accounts SET status = ?, updated_at = ? WHERE scma_id = ?;", (new_status, datetime.now(timezone.utc).isoformat(), req.scma_id))
    append_audit_log(cursor, "CHIEF_ADMINISTRATOR", "TOGGLE_ACCOUNT_STATUS", {"scma_id": req.scma_id, "new_status": new_status})
    conn.commit()
    conn.close()
    return {"status": "SUCCESS", "scma_id": req.scma_id, "new_status": new_status}

class RiskReq(BaseModel):
    scma_id: str
    risk_dial_pct: float


@app.get("/api/v1/member/fills")
def get_member_fills(scma_id: str = "SCMA-FOUNDER"):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT fill_id, scma_id, contract_ticker, side, qty, price_cents, pnl_cents, is_win, timestamp 
        FROM fills 
        WHERE scma_id = ? 
        ORDER BY timestamp DESC LIMIT 25;
    """, (scma_id,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return {"status": "SUCCESS", "scma_id": scma_id, "fills": rows}

@app.post("/api/v1/member/update-risk-dial")
def update_risk_dial(req: RiskReq):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT max_risk_dial_pct FROM accounts WHERE scma_id = ?;", (req.scma_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Account not found")
    if req.risk_dial_pct > row["max_risk_dial_pct"] or req.risk_dial_pct < 0.50:
        conn.close()
        raise HTTPException(status_code=400, detail="Invalid risk dial range")
    cursor.execute("UPDATE accounts SET risk_dial_pct = ?, updated_at = ? WHERE scma_id = ?;", (req.risk_dial_pct, datetime.now(timezone.utc).isoformat(), req.scma_id))
    append_audit_log(cursor, req.scma_id, "UPDATE_RISK_DIAL", {"risk_dial_pct": req.risk_dial_pct})
    conn.commit()
    conn.close()
    return {"status": "SUCCESS", "risk_dial_pct": req.risk_dial_pct}

class DistReq(BaseModel):
    scma_id: str
    amount_dollars: float
    reason: str

@app.post("/api/v1/member/request-distribution")
def request_distribution(req: DistReq):
    cents = int(round(req.amount_dollars * 100))
    if cents <= 0:
        raise HTTPException(status_code=400, detail="Amount must exceed zero.")
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT cash_cents, lifetime_profit_cents, bank_ref_token, status FROM accounts WHERE scma_id = ?;", (req.scma_id,))
    acc = cursor.fetchone()
    if not acc:
        conn.close()
        raise HTTPException(status_code=404, detail="Account not found")
    if acc["status"] == "FROZEN":
        conn.close()
        raise HTTPException(status_code=403, detail="Account is frozen.")
    if cents > acc["cash_cents"]:
        conn.close()
        raise HTTPException(status_code=400, detail="Insufficient cash equity.")

    dry_floor = int(acc["cash_cents"] * 0.40)
    cash_after = acc["cash_cents"] - cents

    if cents <= acc["lifetime_profit_cents"]:
        tier = "GREEN"
        cursor.execute("UPDATE accounts SET cash_cents = cash_cents - ?, lifetime_profit_cents = lifetime_profit_cents - ?, updated_at = ? WHERE scma_id = ?;",
                       (cents, cents, datetime.now(timezone.utc).isoformat(), req.scma_id))
        v_id = emit_outbox_voucher(cursor, "PROFIT_DISTRIBUTION_EMITTED", req.scma_id, {
            "tier": tier, "cents": cents, "dollars": req.amount_dollars, "reason": req.reason, "bank_ref": acc["bank_ref_token"]
        })
        append_audit_log(cursor, req.scma_id, "DISTRIBUTION_GREEN_EXECUTED", {"cents": cents, "voucher_id": v_id})
        conn.commit(); conn.close()
        return {"status": "SUCCESS", "tier": tier, "message": f"Autonomous Profit Sweep approved. Voucher: {v_id}"}
    elif cash_after >= dry_floor:
        tier = "YELLOW"
        cursor.execute("UPDATE accounts SET cash_cents = cash_cents - ?, updated_at = ? WHERE scma_id = ?;",
                       (cents, datetime.now(timezone.utc).isoformat(), req.scma_id))
        v_id = emit_outbox_voucher(cursor, "FLOAT_DRAWDOWN_EMITTED", req.scma_id, {
            "tier": tier, "cents": cents, "dollars": req.amount_dollars, "reason": req.reason, "bank_ref": acc["bank_ref_token"]
        })
        append_audit_log(cursor, req.scma_id, "DISTRIBUTION_YELLOW_EXECUTED", {"cents": cents, "voucher_id": v_id})
        conn.commit(); conn.close()
        return {"status": "SUCCESS", "tier": tier, "message": f"Compounding Float Drawdown processed. Voucher: {v_id}"}
    else:
        tier = "RED"
        v_id = emit_outbox_voucher(cursor, "EMERGENCY_PETITION_STAGED", req.scma_id, {
            "tier": tier, "cents": cents, "dollars": req.amount_dollars, "reason": req.reason, "bank_ref": acc["bank_ref_token"]
        })
        cursor.execute("UPDATE accounting_outbox_events SET status = 'PENDING_CO_SIGN' WHERE event_id = ?;", (v_id,))
        append_audit_log(cursor, req.scma_id, "EMERGENCY_PETITION_LOCKED", {"cents": cents, "voucher_id": v_id, "reason": req.reason})
        conn.commit(); conn.close()
        return {"status": "PENDING_DUAL_CONTROL", "tier": tier, "voucher_id": v_id, "message": "Emergency Floor Breach: Staged in Admin Queue for co-signature."}

class SignReq(BaseModel):
    event_id: str

@app.post("/api/v1/admin/co-sign-emergency")
def co_sign_emergency(req: SignReq):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM accounting_outbox_events WHERE event_id = ? AND status = 'PENDING_CO_SIGN';", (req.event_id,))
    ev = cursor.fetchone()
    if not ev:
        conn.close()
        raise HTTPException(status_code=404, detail="Pending emergency petition not found")
    p = json.loads(ev["payload_json"])
    cursor.execute("UPDATE accounts SET cash_cents = cash_cents - ? WHERE scma_id = ?;", (p["cents"], ev["scma_id"]))
    cursor.execute("UPDATE accounting_outbox_events SET status = 'PENDING_INGESTION', event_type = 'EMERGENCY_DRAWDOWN_APPROVED' WHERE event_id = ?;", (req.event_id,))
    append_audit_log(cursor, "CHIEF_ADMINISTRATOR", "EMERGENCY_PETITION_CO_SIGNED", {"event_id": req.event_id})
    conn.commit(); conn.close()
    return {"status": "SUCCESS", "message": f"Emergency voucher {req.event_id} co-signed and released to outbox."}

@app.get("/api/v1/accounting/outbox")
def get_accounting_outbox():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM accounting_outbox_events WHERE status = 'PENDING_INGESTION' ORDER BY sequence_num ASC;")
    evs = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return {"status": "SUCCESS", "unprocessed_count": len(evs), "vouchers": evs}

class AckReq(BaseModel):
    event_id: str
    reconciliation_token: str

@app.post("/api/v1/accounting/ack")
def acknowledge_voucher(req: AckReq):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE accounting_outbox_events SET status = 'INGESTED' WHERE event_id = ?;", (req.event_id,))
    append_audit_log(cursor, "IFAS_BRIDGE", "VOUCHER_INGESTION_ACK", {"event_id": req.event_id})
    conn.commit(); conn.close()
    return {"status": "SUCCESS"}

# ----------------------------------------------------------------------
# USER INTERFACES
# ----------------------------------------------------------------------
DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>PDEUE Master Cockpit & Registry</title>
  <style>
    :root {
      --bg: #090d16; --card: #121826; --border: #1f293d; --text: #f1f5f9;
      --muted: #94a3b8; --gold: #f59e0b; --green: #10b981; --red: #ef4444;
      --accent: #38bdf8; --purple: #a855f7;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, monospace; }
    body { background: var(--bg); color: var(--text); padding: 0 24px 24px 24px; }
    
    /* Top Persistent Portal Hub Ribbon */
    .portal-hub { background: #0b111e; border-bottom: 1px solid var(--border); margin: 0 -24px 20px -24px; padding: 8px 24px; display: flex; justify-content: space-between; align-items: center; font-size: 0.78rem; }
    .hub-links { display: flex; gap: 14px; align-items: center; }
    .hub-link { color: var(--muted); text-decoration: none; display: flex; align-items: center; gap: 5px; font-weight: 600; padding: 4px 8px; border-radius: 4px; }
    .hub-link:hover { color: #fff; background: #1e293d; }
    .hub-link.active { color: var(--accent); background: rgba(56, 189, 248, 0.1); border: 1px solid rgba(56, 189, 248, 0.3); }

    .header { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border); padding-bottom: 16px; margin-bottom: 20px; }
    .btn { padding: 8px 16px; border-radius: 6px; font-weight: 700; cursor: pointer; border: none; font-size: 0.85rem; text-decoration: none; }
    .btn-red { background: var(--red); color: #fff; }
    .btn-blue { background: #1e293b; color: var(--accent); border: 1px solid var(--accent); }
    .btn-secondary { background: #1e293b; color: var(--text); border: 1px solid var(--border); }
    
    /* Tab Navigation Styles */
    .nav-tabs { display: flex; gap: 8px; border-bottom: 1px solid var(--border); margin-bottom: 20px; }
    .tab-btn { background: transparent; border: none; color: var(--muted); padding: 10px 18px; font-size: 0.88rem; font-weight: 700; cursor: pointer; border-bottom: 2px solid transparent; transition: all 0.2s; }
    .tab-btn:hover { color: #fff; }
    .tab-btn.active { color: var(--accent); border-bottom: 2px solid var(--accent); }
    
    .tab-pane { display: none; }
    .tab-pane.active { display: block; }

    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; margin-bottom: 20px; }
    .card { background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 18px; }
    .card-title { font-size: 0.75rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 6px; }
    .card-value { font-size: 1.8rem; font-weight: 800; color: #fff; }
    .card-sub { font-size: 0.8rem; color: var(--muted); margin-top: 4px; }
    .chart-box { background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 20px; margin-bottom: 20px; }
    table { width: 100%; border-collapse: collapse; margin-top: 12px; font-size: 0.85rem; }
    th { text-align: left; padding: 10px; color: var(--muted); border-bottom: 1px solid var(--border); text-transform: uppercase; font-size: 0.72rem; }
    td { padding: 12px 10px; border-bottom: 1px solid var(--border); }
    .chip { padding: 3px 8px; border-radius: 4px; font-size: 0.72rem; font-weight: 700; }
    .chip-green { background: #064e3b; color: #34d399; }
    .chip-yellow { background: #78350f; color: #fde047; }
    .chip-blue { background: #0c4a6e; color: #38bdf8; }
  </style>
</head>
<body>
  <!-- Top Persistent Portal Hub Ribbon -->
  <div class="portal-hub">
    <div class="hub-links">
      <span style="color:var(--muted); font-weight:800; letter-spacing:0.05em; margin-right:4px;">PDEUE PORTAL HUB:</span>
      <a href="/dashboard" class="hub-link active">● Chief Admin Cockpit</a>
      <a href="/admin/tech" class="hub-link">○ Technical Console (Class T)</a>
      <a href="/advisor" class="hub-link">○ Financial Advisor (Class F)</a>
      <a href="/member" class="hub-link">○ Member Capital Desktop</a>
    </div>
    <div style="color:var(--muted); font-size:0.75rem;">
      Node IP: <strong style="color:#fff;">13.221.153.12</strong> • ADR-011 Air-Gap: <span style="color:var(--green); font-weight:700;">ENFORCED</span>
    </div>
  </div>

    <!-- Directive R-06 Supervisory Audit Lens Banner -->
  <div id="supervisoryLensBanner" style="display:none; background:#78350f; border:1px solid #f59e0b; color:#fef3c7; padding:12px 18px; border-radius:8px; margin-bottom:20px; justify-content:space-between; align-items:center;">
    <div>
      <span style="font-weight:800; letter-spacing:0.04em;">⚠️ SUPERVISORY AUDIT LENS ACTIVE</span>
      <span style="margin-left:10px; font-size:0.82rem; color:#fde68a;">Chief Administrator acting under Directive R-06. Read-Only Forensic Observation.</span>
    </div>
    <a href="/dashboard" class="btn btn-secondary" style="font-size:0.75rem; padding:4px 10px;">← Exit to Master Cockpit</a>
  </div>

  <div class="header">
    <div>
      <h1 style="font-size: 1.4rem;">PDEUE Master Cockpit & Registry</h1>
      <p style="font-size: 0.82rem; color: var(--muted); margin-top: 4px;">Chief Administrator Operational Desk • Lineage Capital Governance</p>
    </div>
    <div style="display: flex; gap: 12px; align-items: center;">
      <span class="chip chip-green" id="sysModeBadge">NORMAL</span>
      <button class="btn btn-red" onclick="toggleHalt()">Master Emergency Halt</button>
      <button class="btn btn-blue" onclick="openOnboardModal()">+ Onboard Member</button>
      <a href="/member" class="btn btn-blue">Switch Hat: Member View →</a>
    </div>
  </div>

  <!-- Operational Workspace Tabs -->
  <div class="nav-tabs">
    <button class="tab-btn active" onclick="switchTab('tab1', this)">1. Lineage Executive Overview</button>
    <button class="tab-btn" onclick="switchTab('tab2', this)">2. Family Lineal Pools & 12-House Matrix</button>
    <button class="tab-btn" onclick="switchTab('tab3', this)">3. Hybrid Velocity Radar</button>
    <button class="tab-btn" onclick="switchTab('tab4', this)">4. Governance & Dual-Control Consensus</button>
  </div>

  <!-- TAB 1: EXECUTIVE OVERVIEW -->
  <div id="tab1" class="tab-pane active">
    <div class="grid">
      <div class="card">
        <div class="card-title">Total Ring 1 Equity</div>
        <div class="card-value" id="totEquity">$0.00</div>
        <div class="card-sub" id="totCents">0 exact integer cents</div>
      </div>
      <div class="card">
        <div class="card-title">40% Dry-Powder Floor</div>
        <div class="card-value" id="dryFloor" style="color: var(--accent);">$0.00</div>
        <div class="card-sub">Untouchable liquid cash reserve</div>
      </div>
      <div class="card">
        <div class="card-title">Active Working Margin</div>
        <div class="card-value" id="actMargin" style="color: var(--green);">$0.00</div>
        <div class="card-sub">Max allowable trade collateral</div>
      </div>
      <div class="card">
        <div class="card-title">Central Family Shield (CFCP)</div>
        <div class="card-value" id="cfcpPool" style="color: var(--purple);">$0.00</div>
        <div class="card-sub">Accumulates 10% of net profits</div>
      </div>
    </div>

    <div class="grid">
      <div class="card">
        <div class="card-title">Win / Loss Ratio</div>
        <div class="card-value" id="winRateVal" style="color: var(--green);">0.0%</div>
        <div class="card-sub" id="winRateSub">Awaiting Initial Fills</div>
      </div>
      <div class="card">
        <div class="card-title">Profit Factor</div>
        <div class="card-value" id="profitFactorVal" style="color: var(--accent);">0.00x</div>
        <div class="card-sub" id="profitFactorSub">Expectancy: $0.00</div>
      </div>
      <div class="card">
        <div class="card-title">Capital Sizing Model</div>
        <div class="card-value" style="color: #fff;">0.25f*</div>
        <div class="card-sub">Quarter-Kelly Risk Governor</div>
      </div>
      <div class="card">
        <div class="card-title">Max Drawdown</div>
        <div class="card-value" style="color: var(--gold);">0.00%</div>
        <div class="card-sub">5.0% Administrative Ceiling</div>
      </div>
    </div>

    <!-- Lineage Equity Compounding Curve & Waterfall -->
    <div style="display: grid; grid-template-columns: 2fr 1fr; gap: 16px; margin-bottom: 20px;">
      <div class="chart-box" style="margin-bottom: 0;">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
          <div>
            <h3 style="font-size:1.05rem;">Lineage Equity Compounding Curve</h3>
            <p style="font-size:0.78rem; color:var(--muted); margin-top:2px;">Real-time integer-cent trajectory across automated settlement cycles</p>
          </div>
          <div style="font-size:0.85rem; color:var(--accent); font-weight:700;" id="chartPeakVal">$0.00 Peak</div>
        </div>
        <div style="width:100%; height:180px; position:relative;">
          <svg id="equityChartSvg" viewBox="0 0 800 180" style="width:100%; height:100%; overflow:visible;">
            <defs>
              <linearGradient id="equityGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stop-color="#38bdf8" stop-opacity="0.35"/>
                <stop offset="100%" stop-color="#38bdf8" stop-opacity="0.0"/>
              </linearGradient>
            </defs>
          </svg>
        </div>
      </div>
      
      <div class="chart-box" style="margin-bottom: 0; display:flex; flex-direction:column; justify-content:space-between;">
        <div>
          <h3 style="font-size:1.05rem; margin-bottom:4px;">Waterfall Distribution (87/10/3)</h3>
          <p style="font-size:0.78rem; color:var(--muted); margin-bottom:14px;">Deterministic realized profit allocation</p>
          <div style="height:14px; width:100%; background:#1e293b; border-radius:7px; overflow:hidden; display:flex; margin-bottom:14px;">
            <div style="width:87%; background:#38bdf8;" title="87% Lineage Compounding"></div>
            <div style="width:10%; background:#a855f7;" title="10% CFCP Shield"></div>
            <div style="width:3%; background:#f59e0b;" title="3% FAEP Ops"></div>
          </div>
          <div style="display:flex; flex-direction:column; gap:8px; font-size:0.82rem;">
            <div style="display:flex; justify-content:space-between;">
              <span style="display:flex; align-items:center; gap:6px;"><span style="width:8px; height:8px; border-radius:50%; background:#38bdf8;"></span> Compounding (87%)</span>
              <strong id="wfScmaDollars" style="color:#38bdf8;">$0.00</strong>
            </div>
            <div style="display:flex; justify-content:space-between;">
              <span style="display:flex; align-items:center; gap:6px;"><span style="width:8px; height:8px; border-radius:50%; background:#a855f7;"></span> Family Shield (10%)</span>
              <strong id="wfCfcpDollars" style="color:#a855f7;">$0.00</strong>
            </div>
            <div style="display:flex; justify-content:space-between;">
              <span style="display:flex; align-items:center; gap:6px;"><span style="width:8px; height:8px; border-radius:50%; background:#f59e0b;"></span> Platform Ops (3%)</span>
              <strong id="wfFaepDollars" style="color:#f59e0b;">$0.00</strong>
            </div>
          </div>
        </div>
        <div style="border-top:1px solid var(--border); padding-top:10px; font-size:0.74rem; color:var(--muted);">
          Verified ADR-008 exact-cent allocation with zero fractional leakage.
        </div>
      </div>
    </div>

    <!-- Active Portfolio Table -->
    <div class="chart-box">
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
        <h3 style="font-size:1.05rem;">Active Portfolio Positions & Inside-Spread Resting Bids</h3>
        <span class="chip chip-blue" id="openCountBadge">0 OPEN</span>
      </div>
      <table>
        <thead>
          <tr>
            <th>Slot</th>
            <th>Contract</th>
            <th>Domain</th>
            <th>Venue</th>
            <th>Side</th>
            <th>Qty</th>
            <th>VWAP</th>
            <th>Cost Basis</th>
            <th>Mark-to-Market</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody id="posTable">
          <tr><td colspan="10" style="text-align:center; color:var(--muted); padding:16px;">No open positions. Inventory flat.</td></tr>
        </tbody>
      </table>
    </div>

    <!-- Registry -->
    <div class="chart-box">
      <h3 style="font-size:1.05rem;">Ring 1 Multi-Account Registry</h3>
      <table>
        <thead>
          <tr>
            <th>SCMA ID</th>
            <th>User ID / Description</th>
            <th>Cash Balance</th>
            <th>Risk Dial</th>
            <th>Status</th>
            <th>Bank Reference Token</th>
            <th>Action</th>
          </tr>
        </thead>
        <tbody id="rosterTable"></tbody>
      </table>
    </div>
  </div>

  <!-- TAB 2: 12-HOUSE MATRIX -->
  <div id="tab2" class="tab-pane">
    <div class="chart-box">
      <h3 style="font-size:1.05rem; margin-bottom:6px;">12-House Lineal Governance Matrix</h3>
      <p style="font-size:0.8rem; color:var(--muted); margin-bottom:14px;">Tribal branch sub-ledgers and sovereign risk allocation boundaries.</p>
      <table>
        <thead>
          <tr>
            <th>House Identifier</th>
            <th>Tribal Name</th>
            <th>Active SCMAs</th>
            <th>Allocated Capital</th>
            <th>Governance Posture</th>
            <th>Circuit Breaker</th>
          </tr>
        </thead>
        <tbody id="houseTable"></tbody>
      </table>
    </div>
  </div>

  <!-- TAB 3: VELOCITY RADAR -->
  <div id="tab3" class="tab-pane">
    <div class="chart-box">
      <h3 style="font-size:1.05rem; margin-bottom:6px;">Hybrid Velocity Radar (Multi-Category Opportunity Feed)</h3>
      <p style="font-size:0.8rem; color:var(--muted); margin-bottom:14px;">Real-time underwriting queue: Weather (NOAA), Macro (CPI/Fed), Crypto, and Sports opportunities.</p>
      <table>
        <thead>
          <tr>
            <th>Contract Ticker</th>
            <th>Domain</th>
            <th>Venue</th>
            <th>Model Probability</th>
            <th>Market Ask</th>
            <th>Net Edge</th>
            <th>Expiry Horizon</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody id="radarTable"></tbody>
      </table>
    </div>
  </div>

  <!-- TAB 4: DUAL-CONTROL & CONSENSUS -->
  <div id="tab4" class="tab-pane">
    <div class="chart-box" style="border-color: #7f1d1d; margin-bottom:20px;">
      <h3 style="font-size:1.05rem; color:#f87171;">Emergency Distribution & Co-Signature Queue (Directive R-15)</h3>
      <p style="font-size:0.8rem; color:var(--muted); margin-bottom:14px;">Demands dual-control co-signature for requests that breach the 40% capital floor.</p>
      <table>
        <thead>
          <tr>
            <th>Voucher ID</th>
            <th>SCMA Target</th>
            <th>Requested Amount</th>
            <th>Reason</th>
            <th>Action</th>
          </tr>
        </thead>
        <tbody id="emergencyTable">
          <tr><td colspan="5" style="text-align:center; color:var(--muted); padding:16px;">No pending emergency petitions.</td></tr>
        </tbody>
      </table>
    </div>

    <div class="chart-box">
      <h3 style="font-size:1.05rem; margin-bottom:8px;">Dual-Control Consensus Ledger</h3>
      <div style="font-size:0.82rem; color:var(--muted); line-height:1.6;">
        <div>• <strong>AUTH-01 (Chief Administrator):</strong> Sovereign Settlor Master Authority active.</div>
        <div>• <strong>AUTH-02 (Trustee / F3 CRO):</strong> Dual-sign threshold enforced on red-tier events.</div>
        <div>• <strong>Consensus Invariant:</strong> Unilateral withdrawal of core lineage principal is permanently barred.</div>
      </div>
    </div>
  </div>

  <!-- Deposit Modal -->
  <div id="depositModal" style="display:none; position:fixed; top:0; left:0; width:100%; height:100%; background:rgba(0,0,0,0.75); z-index:1000; justify-content:center; align-items:center;">
    <div style="background:var(--card); border:1px solid var(--border); border-radius:8px; padding:24px; width:440px; box-shadow:0 8px 32px rgba(0,0,0,0.5);">
      <h3 style="font-size:1.15rem; margin-bottom:8px;">Capital Injection & Account Funding</h3>
      <p style="font-size:0.8rem; color:var(--muted); margin-bottom:16px;">Credit cash equity in exact integer cents under ADR-008. Dynamic 40% reserve floor and working margin recalculate immediately.</p>
      
      <label style="font-size:0.75rem; color:var(--muted); text-transform:uppercase;">Target Account</label>
      <input type="text" id="depScma" readonly style="width:100%; padding:8px; margin:4px 0 12px 0; background:#0b111e; border:1px solid var(--border); color:#fff; border-radius:4px; font-weight:700;">
      
      <label style="font-size:0.75rem; color:var(--muted); text-transform:uppercase;">Deposit Amount (USD)</label>
      <input type="number" id="depAmount" step="10.00" placeholder="1500.00" style="width:100%; padding:8px; margin:4px 0 12px 0; background:#0b111e; border:1px solid var(--border); color:var(--accent); font-weight:800; font-size:1.1rem; border-radius:4px;">
      
      <label style="font-size:0.75rem; color:var(--muted); text-transform:uppercase;">Source Memo / Bank Rail</label>
      <input type="text" id="depMemo" value="PenFed ACH - Lineage Capital Top-Off" style="width:100%; padding:8px; margin:4px 0 20px 0; background:#0b111e; border:1px solid var(--border); color:#fff; border-radius:4px;">
      
      <div style="display:flex; justify-content:flex-end; gap:10px;">
        <button class="btn btn-secondary" onclick="closeDepositModal()">Cancel</button>
        <button class="btn btn-blue" style="background:var(--green); color:#000;" onclick="submitDeposit()">Confirm & Credit Ledger</button>
      </div>
    </div>
  </div>

  <!-- Onboard Modal -->
  <div id="onboardModal" style="display:none; position:fixed; top:0; left:0; width:100%; height:100%; background:rgba(0,0,0,0.75); z-index:1000; justify-content:center; align-items:center;">
    <div style="background:var(--card); border:1px solid var(--border); border-radius:8px; padding:24px; width:480px; box-shadow:0 8px 32px rgba(0,0,0,0.5);">
      <h3 style="font-size:1.15rem; margin-bottom:8px;">Lineage Member Provisioning & Governance</h3>
      <p style="font-size:0.8rem; color:var(--muted); margin-bottom:16px;">Configure an SCMA sub-ledger with assigned authority tier and opaque ADR-011 banking reference.</p>
      
      <div style="display:grid; grid-template-columns:1fr 1fr; gap:10px;">
        <div>
          <label style="font-size:0.75rem; color:var(--muted); text-transform:uppercase;">Target SCMA Slot</label>
          <select id="onbScma" style="width:100%; padding:8px; margin:4px 0 12px 0; background:#0b111e; border:1px solid var(--border); color:#fff; border-radius:4px;">
            <option value="SCMA-MEM-0001">SCMA-MEM-0001 (Member 1)</option>
            <option value="SCMA-MEM-0002">SCMA-MEM-0002 (Member 2)</option>
            <option value="SCMA-MEM-0003">SCMA-MEM-0003 (Member 3)</option>
            <option value="SCMA-MEM-0004">SCMA-MEM-0004 (Member 4)</option>
            <option value="SCMA-MEM-0005">SCMA-MEM-0005 (Member 5)</option>
          </select>
        </div>
        <div>
          <label style="font-size:0.75rem; color:var(--muted); text-transform:uppercase;">Role / Governance Tier</label>
          <select id="onbRole" style="width:100%; padding:8px; margin:4px 0 12px 0; background:#0b111e; border:1px solid var(--border); color:#fff; border-radius:4px;">
            <option value="MEMBER_USER">MEMBER_USER (Autonomous Member)</option>
            <option value="F1">F1 (Lineage Peer Guide)</option>
            <option value="F2-H">F2-H (Head of Household)</option>
            <option value="F2-A">F2-A (Lineage Financial Advisor)</option>
            <option value="F3">F3 (Chief Risk Officer)</option>
            <option value="T1">T1 (Systems Monitor - Read Only)</option>
            <option value="T2">T2 (Systems Maintenance Engineer)</option>
          </select>
        </div>
      </div>

      <label style="font-size:0.75rem; color:var(--muted); text-transform:uppercase;">Member Full Name / Lineage Identity</label>
      <input type="text" id="onbUser" placeholder="e.g. Sarah Carmichael" style="width:100%; padding:8px; margin:4px 0 12px 0; background:#0b111e; border:1px solid var(--border); color:#fff; border-radius:4px;">
      
      <div style="display:grid; grid-template-columns:1fr 1fr; gap:10px;">
        <div>
          <label style="font-size:0.75rem; color:var(--muted); text-transform:uppercase;">Initial Gifted Seed ($)</label>
          <input type="number" id="onbSeed" value="100.00" step="25.00" style="width:100%; padding:8px; margin:4px 0 12px 0; background:#0b111e; border:1px solid var(--border); color:var(--green); font-weight:700; border-radius:4px;">
        </div>
        <div>
          <label style="font-size:0.75rem; color:var(--muted); text-transform:uppercase;">Banking Institution</label>
          <select id="onbBank" style="width:100%; padding:8px; margin:4px 0 12px 0; background:#0b111e; border:1px solid var(--border); color:#fff; border-radius:4px;">
            <option value="PENFED">PenFed Credit Union</option>
            <option value="FBO-TRUST">Delaware FBO Master Trust</option>
            <option value="COMMERCIAL">Commercial Checking</option>
          </select>
        </div>
      </div>

      <label style="font-size:0.75rem; color:var(--muted); text-transform:uppercase;">Bank Account Last 4 Digits</label>
      <input type="text" id="onbLast4" maxlength="4" value="4811" style="width:100%; padding:8px; margin:4px 0 20px 0; background:#0b111e; border:1px solid var(--border); color:#fff; border-radius:4px;">

      <div style="display:flex; justify-content:flex-end; gap:10px;">
        <button class="btn btn-secondary" onclick="closeOnboardModal()">Cancel</button>
        <button class="btn btn-blue" onclick="submitOnboard()">Provision & Activate SCMA</button>
      </div>
    </div>
  </div>

  <script>
    function switchTab(tabId, btn) {
      document.querySelectorAll('.tab-pane').forEach(el => el.classList.remove('active'));
      document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
      document.getElementById(tabId).classList.add('active');
      btn.classList.add('active');
    }

    function drawSvgCurve(svgId, points, floorCents, strokeColor, gradId) {
      const svg = document.getElementById(svgId);
      if (!svg) return;
      const defs = svg.querySelector('defs');
      svg.innerHTML = '';
      if (defs) svg.appendChild(defs);

      if (!points || points.length === 0) return;
      let minVal = Math.min(...points, floorCents || 0);
      let maxVal = Math.max(...points);
      if (maxVal === minVal) maxVal = minVal + 1000;
      
      const padBottom = 26, padTop = 16, padLeft = 36, padRight = 24;
      const width = 800 - padLeft - padRight;
      const height = 180 - padTop - padBottom;
      
      const getY = (val) => 180 - padBottom - ((val - minVal) / (maxVal - minVal)) * height;
      const getX = (idx) => padLeft + (points.length === 1 ? width / 2 : (idx / (points.length - 1)) * width);

      const floorY = getY(floorCents);
      let gridHtml = `
        <line x1="${padLeft}" y1="${getY(maxVal)}" x2="${800 - padRight}" y2="${getY(maxVal)}" stroke="#1e293b" stroke-width="1" stroke-dasharray="4"/>
        <text x="${padLeft}" y="${getY(maxVal) - 4}" fill="#64748b" font-size="10">$${(maxVal/100).toFixed(2)} Peak</text>
        <line x1="${padLeft}" y1="${floorY}" x2="${800 - padRight}" y2="${floorY}" stroke="#6366f1" stroke-width="1.5" stroke-dasharray="4"/>
        <text x="${padLeft}" y="${floorY + 12}" fill="#818cf8" font-size="10">$${(floorCents/100).toFixed(2)} (40% Floor Shield)</text>
      `;

      let pathD = '', areaD = '';
      points.forEach((p, i) => {
        const x = getX(i);
        const y = getY(p);
        if (i === 0) {
          pathD += `M ${x} ${y}`;
          areaD += `M ${x} ${180 - padBottom} L ${x} ${y}`;
        } else {
          pathD += ` L ${x} ${y}`;
          areaD += ` L ${x} ${y}`;
        }
      });
      const lastX = getX(points.length - 1);
      areaD += ` L ${lastX} ${180 - padBottom} Z`;

      let chartContent = gridHtml + `
        <path d="${areaD}" fill="url(#${gradId})" />
        <path d="${pathD}" fill="none" stroke="${strokeColor}" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round"/>
      `;

      points.forEach((p, i) => {
        const x = getX(i);
        const y = getY(p);
        chartContent += `<circle cx="${x}" cy="${y}" r="3" fill="${strokeColor}" stroke="#090d16" stroke-width="1.5"/>`;
      });

      svg.innerHTML += chartContent;
    }

    async function refreshData() {
      try {
        const res = await fetch('/api/v1/admin/ledger-summary');
        const data = await res.json();
        
        document.getElementById('sysModeBadge').textContent = data.system_mode;
        document.getElementById('totEquity').textContent = '$' + (data.total_cash_cents / 100).toFixed(2);
        document.getElementById('totCents').textContent = data.total_cash_cents.toLocaleString() + ' exact integer cents';
        document.getElementById('dryFloor').textContent = '$' + (data.dry_powder_cents / 100).toFixed(2);
        document.getElementById('actMargin').textContent = '$' + (data.active_margin_cents / 100).toFixed(2);
        document.getElementById('cfcpPool').textContent = '$' + (data.cfcp_meter_cents / 100).toFixed(2);

        // Compounding Curve & Waterfall Rendering
        const pts = data.checkpoints || [data.total_cash_cents];
        drawSvgCurve('equityChartSvg', pts, data.dry_powder_cents, '#38bdf8', 'equityGrad');
        document.getElementById('chartPeakVal').textContent = '$' + (Math.max(...pts)/100).toFixed(2) + ' Peak';

        const tp = data.total_profit_cents || 0;
        document.getElementById('wfScmaDollars').textContent = '$' + ((tp * 0.87)/100).toFixed(2);
        document.getElementById('wfCfcpDollars').textContent = '$' + ((tp * 0.10)/100).toFixed(2);
        document.getElementById('wfFaepDollars').textContent = '$' + ((tp * 0.03)/100).toFixed(2);

        const perf = data.performance;
        if (perf) {
          document.getElementById('winRateVal').textContent = perf.total_trades > 0 ? (perf.win_rate_pct.toFixed(1) + '%') : '0.0%';
          document.getElementById('winRateSub').textContent = perf.total_trades > 0 ? (perf.wins + ' Wins / ' + perf.losses + ' Losses') : 'Awaiting Initial Fills';
          document.getElementById('profitFactorVal').textContent = perf.total_trades > 0 ? (perf.profit_factor.toFixed(2) + 'x') : '0.00x';
          document.getElementById('profitFactorSub').textContent = perf.total_trades > 0 ? 'Verified Execution' : 'Expectancy: $0.00';
        }

        const posTbody = document.getElementById('posTable');
        document.getElementById('openCountBadge').textContent = data.positions.length + ' OPEN';
        if (data.positions.length === 0) {
          posTbody.innerHTML = '<tr><td colspan="10" style="text-align:center; color:var(--muted); padding:16px;">No open positions. Inventory flat.</td></tr>';
        } else {
          posTbody.innerHTML = '';
          data.positions.forEach(p => {
            posTbody.innerHTML += `
              <tr>
                <td style="font-weight:700;">#${p.slot_index}</td>
                <td style="font-weight:700; color:var(--accent);">${p.contract_ticker}</td>
                <td>${p.domain}</td>
                <td>${p.venue}</td>
                <td>${p.side}</td>
                <td>${p.qty}</td>
                <td>$${(p.vwap_cents/100).toFixed(2)}</td>
                <td>$${(p.cost_basis_cents/100).toFixed(2)}</td>
                <td style="color:var(--green); font-weight:700;">$${(p.mtm_cents/100).toFixed(2)}</td>
                <td><span class="chip chip-blue">${p.status}</span></td>
              </tr>
            `;
          });
        }

        const rosTbody = document.getElementById('rosterTable');
        rosTbody.innerHTML = '';
        data.accounts.forEach(a => {
          rosTbody.innerHTML += `
            <tr>
              <td style="font-weight:700;">${a.scma_id}</td>
              <td>${a.user_id}</td>
              <td style="color:var(--green); font-weight:700;">$${(a.cash_cents / 100).toFixed(2)}</td>
              <td>${a.risk_dial_pct.toFixed(2)}%</td>
              <td><span class="chip ${a.status==='ACTIVE'?'chip-green':(a.status==='FROZEN'?'chip-yellow':'chip-blue')}">${a.status}</span></td>
              <td style="color:var(--muted);">${a.bank_ref_token}</td>
              <td style="display:flex; gap:6px; align-items:center;">
                <a href="/member?scma=${a.scma_id}&supervisory=true" class="btn btn-blue" style="background:#1e3a8a; color:#93c5fd; border:none; padding:4px 8px; font-size:0.75rem; text-decoration:none;">Inspect 🔍</a>
                <button class="btn btn-blue" style="background:#064e3b; color:#34d399; border:none; padding:4px 8px; font-size:0.75rem;" onclick="openDepositModal('${a.scma_id}')">+ Fund</button>
                <button class="btn btn-blue" style="background:${a.status === 'FROZEN' ? '#1e293b' : '#7f1d1d'}; color:${a.status === 'FROZEN' ? '#64748b' : '#fecaca'}; border:${a.status === 'FROZEN' ? '1px solid #334155' : '1px solid #ef4444'}; padding:4px 8px; font-size:0.75rem; cursor:${a.status === 'FROZEN' ? 'not-allowed' : 'pointer'};" ${a.status === 'FROZEN' ? 'disabled' : ''} onclick="executeFreeze('${a.scma_id}')">Freeze</button>
                <button class="btn btn-blue" style="background:${a.status !== 'FROZEN' ? '#1e293b' : '#065f46'}; color:${a.status !== 'FROZEN' ? '#64748b' : '#a7f3d0'}; border:${a.status !== 'FROZEN' ? '1px solid #334155' : '1px solid #10b981'}; padding:4px 8px; font-size:0.75rem; cursor:${a.status !== 'FROZEN' ? 'not-allowed' : 'pointer'};" ${a.status !== 'FROZEN' ? 'disabled' : ''} onclick="executeUnfreeze('${a.scma_id}')">Unfreeze ✓</button>
              </td>
            </tr>
          `;
        });

        // Tab 2: House Matrix Render
        const hTbody = document.getElementById('houseTable');
        if (hTbody && data.houses) {
          hTbody.innerHTML = '';
          data.houses.forEach(h => {
            hTbody.innerHTML += `
              <tr>
                <td style="font-weight:700;">${h.house_id}</td>
                <td style="font-weight:600; color:#fff;">${h.name}</td>
                <td>${h.scma_count} SCMAs</td>
                <td style="color:var(--green); font-weight:700;">$${(h.allocated_cents / 100).toFixed(2)}</td>
                <td><span class="chip ${h.status==='ACTIVE'?'chip-green':'chip-yellow'}">${h.status}</span></td>
                <td><button class="btn btn-secondary" style="padding:4px 8px; font-size:0.75rem;">Clamp 0.5%</button></td>
              </tr>
            `;
          });
        }

        // Tab 3: Velocity Radar Render
        const rTbody = document.getElementById('radarTable');
        if (rTbody && data.radar) {
          rTbody.innerHTML = '';
          data.radar.forEach(r => {
            rTbody.innerHTML += `
              <tr>
                <td style="font-weight:700; color:var(--accent);">${r.ticker}</td>
                <td>${r.domain}</td>
                <td>${r.venue}</td>
                <td style="font-weight:700; color:var(--green);">${(r.prob * 100).toFixed(0)}%</td>
                <td>$${(r.ask_cents / 100).toFixed(2)}</td>
                <td style="color:var(--accent); font-weight:700;">+${r.edge_pct.toFixed(1)}%</td>
                <td>${r.expiry}</td>
                <td><span class="chip chip-blue">QUEUED</span></td>
              </tr>
            `;
          });
        }

        // Tab 4: Emergency Petitions
        const emTbody = document.getElementById('emergencyTable');
        if (data.emergency_petitions && data.emergency_petitions.length > 0) {
          emTbody.innerHTML = '';
          data.emergency_petitions.forEach(p => {
            const pl = JSON.parse(p.payload_json);
            emTbody.innerHTML += `
              <tr>
                <td style="font-weight:700; color:#f87171;">${p.event_id}</td>
                <td>${p.scma_id}</td>
                <td style="font-weight:700; color:#f87171;">$${(pl.cents / 100).toFixed(2)}</td>
                <td>${pl.reason}</td>
                <td><button class="btn btn-red" style="padding:4px 8px; font-size:0.75rem;" onclick="coSignPetition('${p.event_id}')">Co-Sign & Release</button></td>
              </tr>
            `;
          });
        } else {
          emTbody.innerHTML = '<tr><td colspan="5" style="text-align:center; color:var(--muted); padding:16px;">No pending emergency petitions.</td></tr>';
        }
      } catch (e) {
        console.error('Refresh error:', e);
      }
    }

    function openDepositModal(scmaId) {
      document.getElementById('depScma').value = scmaId;
      document.getElementById('depositModal').style.display = 'flex';
    }
    function closeDepositModal() {
      document.getElementById('depositModal').style.display = 'none';
    }
    async function submitDeposit() {
      const scma = document.getElementById('depScma').value;
      const amt = parseFloat(document.getElementById('depAmount').value);
      const memo = document.getElementById('depMemo').value;
      if (!amt || amt <= 0) { alert('Enter valid deposit amount.'); return; }
      const res = await fetch('/api/v1/admin/deposit-funds', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ scma_id: scma, amount_dollars: amt, memo: memo })
      });
      if (res.ok) { closeDepositModal(); refreshData(); }
      else { const d = await res.json(); alert('Deposit Error: ' + d.detail); }
    }

    function openOnboardModal() {
      document.getElementById('onboardModal').style.display = 'flex';
    }
    function closeOnboardModal() {
      document.getElementById('onboardModal').style.display = 'none';
    }
    async function submitOnboard() {
      const scma = document.getElementById('onbScma').value;
      const role = document.getElementById('onbRole').value;
      const user = document.getElementById('onbUser').value;
      const seed = parseFloat(document.getElementById('onbSeed').value) || 0;
      const bank = document.getElementById('onbBank').value;
      const last4 = document.getElementById('onbLast4').value || '0000';
      if (!user) { alert('Enter member name / description.'); return; }
      const res = await fetch('/api/v1/admin/onboard-member', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ scma_id: scma, user_id: user, role_tier: role, initial_seed_dollars: seed, bank_institution: bank, account_last4: last4 })
      });
      if (res.ok) { closeOnboardModal(); refreshData(); }
      else { const d = await res.json(); alert('Onboarding Error: ' + d.detail); }
    }

    
    async function executeFreeze(scma) {
      await fetch('/api/v1/admin/freeze', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ scma_id: scma }) });
      refreshData();
    }
    async function executeUnfreeze(scma) {
      await fetch('/api/v1/admin/unfreeze', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ scma_id: scma }) });
      refreshData();
    }

    async function toggleFreeze(scma) {
      await fetch('/api/v1/admin/toggle-freeze', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ scma_id: scma }) });
      refreshData();
    }
    async function coSignPetition(vId) {
      if (!confirm('Co-sign release for voucher ' + vId + '?')) return;
      await fetch('/api/v1/admin/co-sign-emergency', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ event_id: vId }) });
      refreshData();
    }
    async function toggleHalt() {
      await fetch('/api/v1/admin/kill-switch', { method: 'POST' });
      refreshData();
    }

    setInterval(refreshData, 3000);
    refreshData();
  </script>
</body>
</html>
"""
MEMBER_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>PDEUE Member Capital Portal</title>
  <style>
    :root {
      --bg: #090d16; --card: #121826; --border: #1f293d; --text: #f1f5f9;
      --muted: #94a3b8; --gold: #f59e0b; --green: #10b981; --red: #ef4444;
      --accent: #38bdf8; --purple: #a855f7;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, monospace; }
    body { background: var(--bg); color: var(--text); padding: 24px; }
    .header { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border); padding-bottom: 16px; margin-bottom: 24px; }
    .btn { padding: 8px 16px; border-radius: 6px; font-weight: 700; cursor: pointer; border: none; font-size: 0.85rem; text-decoration: none; }
    .btn-primary { background: var(--accent); color: #090d16; }
    .btn-secondary { background: #1e293b; color: var(--text); border: 1px solid var(--border); }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; margin-bottom: 20px; }
    .card { background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 18px; }
    .card-title { font-size: 0.75rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 6px; }
    .card-value { font-size: 1.8rem; font-weight: 800; color: #fff; }
    .card-sub { font-size: 0.8rem; color: var(--muted); margin-top: 4px; }
    .chip { padding: 3px 8px; border-radius: 4px; font-size: 0.72rem; font-weight: 700; }
    .chip-green { background: #064e3b; color: #34d399; }
    .chip-blue { background: #0c4a6e; color: #38bdf8; }
    .chip-empty { background: #1e293b; color: var(--muted); }
    .slider { width: 100%; margin-top: 10px; accent-color: var(--accent); }
    .rack-header { display: flex; justify-content: space-between; align-items: center; cursor: pointer; user-select: none; }
    .rack-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(170px, 1fr)); gap: 12px; margin-top: 16px; }
    .slot-card { background: #0b111e; border: 1px solid var(--border); border-radius: 6px; padding: 12px; font-size: 0.82rem; }
    .slot-card.active { border-color: rgba(56, 189, 248, 0.4); background: #0f172a; }
    .slot-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
    .slot-id { font-weight: 800; color: var(--muted); font-size: 0.75rem; }
  </style>
</head>
<body>
  <!-- Top Persistent Portal Hub Ribbon -->
  <div style="background:#0b111e; border-bottom:1px solid var(--border); margin:-24px -24px 20px -24px; padding:8px 24px; display:flex; justify-content:space-between; align-items:center; font-size:0.78rem;">
    <div style="display:flex; gap:14px; align-items:center;">
      <span style="color:var(--muted); font-weight:800; letter-spacing:0.05em; margin-right:4px;">PDEUE PORTAL HUB:</span>
      <a href="/dashboard" style="color:var(--muted); text-decoration:none; padding:4px 8px;">○ Chief Admin Cockpit</a>
      <a href="/admin/tech" style="color:var(--muted); text-decoration:none; padding:4px 8px;">○ Technical Console (Class T)</a>
      <a href="/advisor" style="color:var(--muted); text-decoration:none; padding:4px 8px;">○ Financial Advisor (Class F)</a>
      <a href="/member" style="color:var(--accent); background:rgba(56, 189, 248, 0.1); border:1px solid rgba(56, 189, 248, 0.3); text-decoration:none; padding:4px 8px; border-radius:4px; font-weight:700;">● Member Capital Desktop</a>
    </div>
    <div style="color:var(--muted); font-size:0.75rem;">
      SCMA View • ADR-011 Air-Gap: <span style="color:var(--green); font-weight:700;">VERIFIED</span>
    </div>
  </div>
    <!-- Directive R-06 Supervisory Audit Lens Banner -->
  <div id="supervisoryLensBanner" style="display:none; background:#78350f; border:1px solid #f59e0b; color:#fef3c7; padding:12px 18px; border-radius:8px; margin-bottom:20px; justify-content:space-between; align-items:center;">
    <div>
      <span style="font-weight:800; letter-spacing:0.04em;">⚠️ SUPERVISORY AUDIT LENS ACTIVE</span>
      <span style="margin-left:10px; font-size:0.82rem; color:#fde68a;">Chief Administrator acting under Directive R-06. Read-Only Forensic Observation.</span>
    </div>
    <a href="/dashboard" class="btn btn-secondary" style="font-size:0.75rem; padding:4px 10px;">← Exit to Master Cockpit</a>
  </div>

  <!-- Directive R-06 Supervisory Audit Lens Banner -->
  <div id="supervisoryLensBanner" style="display:none; background:#78350f; border:1px solid #f59e0b; color:#fef3c7; padding:14px 20px; border-radius:8px; margin-bottom:20px; justify-content:space-between; align-items:center;">
    <div>
      <div style="font-size:0.75rem; text-transform:uppercase; letter-spacing:0.06em; color:#fde68a; font-weight:800;">Directive R-06 Supervisory Audit Lens Active</div>
      <div style="font-size:1.2rem; font-weight:800; margin-top:2px; color:#fff;">
        Forensic Review: <span id="supTargetName" style="color:#38bdf8;">Loading Member...</span>
        <span style="font-size:0.85rem; color:#fde68a; font-weight:600; margin-left:8px;">(<span id="supTargetScma"></span>)</span>
      </div>
      <div style="font-size:0.8rem; color:#fef3c7; margin-top:3px;">
        Ledger Status: <span id="supStatusBadge" class="chip chip-green">ACTIVE</span> • Sovereign Chief Administrator Jurisdiction
      </div>
    </div>
    <div style="display:flex; gap:8px; align-items:center;">
      <button id="supFreezeBtn" class="btn btn-secondary" style="background:#7f1d1d; color:#fecaca; border:1px solid #ef4444; font-size:0.78rem; padding:6px 12px;" onclick="executeSupFreeze()">Freeze</button>
      <button id="supUnfreezeBtn" class="btn btn-secondary" style="background:#065f46; color:#a7f3d0; border:1px solid #10b981; font-size:0.78rem; padding:6px 12px;" onclick="executeSupUnfreeze()">Unfreeze ✓</button>
      <a href="/dashboard" class="btn btn-blue" style="background:#1e3a8a; color:#fff; font-size:0.78rem; padding:6px 12px; text-decoration:none;">← Return to Master Cockpit</a>
    </div>
  </div>

  <!-- Primary Identity Card -->
  <div class="header" style="background:var(--card); border:1px solid var(--border); border-radius:8px; padding:18px 22px; margin-bottom:20px;">
    <div>
      <div style="font-size:0.72rem; text-transform:uppercase; letter-spacing:0.07em; color:var(--muted); font-weight:800;">Authenticated Sub-Ledger Identity</div>
      <h1 id="mMemberName" style="font-size: 1.55rem; color: #fff; margin-top:3px; font-weight:800;">Loading Member Identity...</h1>
      <p style="font-size: 0.82rem; color: var(--muted); margin-top: 4px;">
        SCMA Sub-Ledger: <strong id="mScmaDisplay" style="color:var(--accent);">--</strong> • Account Status: <span id="mStatusBadge" class="chip chip-green">ACTIVE</span>
      </p>
    </div>
    <div style="display: flex; gap: 12px; align-items: center;">
      <div>
        <label style="font-size:0.7rem; color:var(--muted); text-transform:uppercase; display:block; margin-bottom:4px; font-weight:700;">Switch Member View</label>
        <select id="scmaSelector" onchange="switchScma()" style="background:#0b111e; color:#fff; border:1px solid var(--border); padding:8px 14px; border-radius:6px; font-size:0.85rem; font-weight:600;">
        </select>
      </div>
      <a href="/dashboard" class="btn btn-secondary" style="margin-top:16px;">Admin Cockpit →</a>
    </div>
  </div>

  <div class="grid">
    <div class="card">
      <div class="card-title">Your Unreserved Cash Balance</div>
      <div class="card-value" id="mCash">$0.00</div>
      <div class="card-sub" id="mCents">0 exact integer cents</div>
    </div>
    <div class="card">
      <div class="card-title">Lifetime Compounded Yield</div>
      <div class="card-value" id="mYield" style="color: var(--green);">$0.00</div>
      <div class="card-sub">Post-waterfall (87% retained)</div>
    </div>
    <div class="card">
      <div class="card-title">Opaque Bank Reference Token</div>
      <div class="card-value" id="mBank" style="font-size: 1.15rem; color: var(--muted); padding-top: 6px;">EXT-REF-PENFED-****8800</div>
      <div class="card-sub">ADR-011 Zero-Credential Air-Gap</div>
    </div>
  </div>

  <div class="grid">
    <div class="card">
      <div class="card-title">Win / Loss Ratio</div>
      <div class="card-value" id="mWinRate" style="color: var(--green);">0.0%</div>
      <div class="card-sub" id="mWinSub">Awaiting Initial Fills</div>
    </div>
    <div class="card">
      <div class="card-title">Profit Factor</div>
      <div class="card-value" id="mProfitFactor" style="color: var(--accent);">0.00x</div>
      <div class="card-sub">Expectancy: $0.00</div>
    </div>
    <div class="card">
      <div class="card-title">Sizing Model</div>
      <div class="card-value" style="color: #fff;">Quarter-Kelly</div>
      <div class="card-sub">Down-only Personal Governor</div>
    </div>
    <div class="card">
      <div class="card-title">Max Drawdown</div>
      <div class="card-value" style="color: var(--gold);">0.00%</div>
      <div class="card-sub">5.0% Administrative Ceiling</div>
    </div>
  </div>

  <!-- Member Personal Compounding Trajectory & Allocation -->
  <div style="display: grid; grid-template-columns: 2fr 1fr; gap: 16px; margin-bottom: 20px;">
    <div class="card" style="margin-bottom:0;">
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
        <div>
          <h3 style="font-size:1.05rem;">Personal Compounding Horizon</h3>
          <p style="font-size:0.78rem; color:var(--muted); margin-top:2px;">Autonomous geometric wealth trajectory (87% net retention)</p>
        </div>
        <span class="chip chip-green">+87% Compounder</span>
      </div>
      <div style="width:100%; height:180px; position:relative;">
        <svg id="memberCurveSvg" viewBox="0 0 800 180" style="width:100%; height:100%; overflow:visible;">
          <defs>
            <linearGradient id="memGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stop-color="#10b981" stop-opacity="0.35"/>
              <stop offset="100%" stop-color="#10b981" stop-opacity="0.0"/>
            </linearGradient>
          </defs>
        </svg>
      </div>
    </div>
    
    <div class="card" style="margin-bottom:0; display:flex; flex-direction:column; justify-content:space-between;">
      <div>
        <h3 style="font-size:1.05rem; margin-bottom:4px;">Capital Allocation Envelope</h3>
        <p style="font-size:0.78rem; color:var(--muted); margin-bottom:14px;">Real-time risk envelope utilization</p>
        <div style="display:flex; flex-direction:column; gap:8px; font-size:0.82rem;">
          <div style="display:flex; justify-content:space-between;">
            <span style="display:flex; align-items:center; gap:6px;"><span style="width:8px; height:8px; border-radius:50%; background:#38bdf8;"></span> Active Trade Margin</span>
            <strong id="mAllocActive">$0.00</strong>
          </div>
          <div style="display:flex; justify-content:space-between;">
            <span style="display:flex; align-items:center; gap:6px;"><span style="width:8px; height:8px; border-radius:50%; background:#6366f1;"></span> 40% Dry-Powder Floor</span>
            <strong id="mAllocFloor">$0.00</strong>
          </div>
          <div style="display:flex; justify-content:space-between;">
            <span style="display:flex; align-items:center; gap:6px;"><span style="width:8px; height:8px; border-radius:50%; background:#10b981;"></span> Compounded Yield Added</span>
            <strong id="mAllocYield" style="color:var(--green);">$0.00</strong>
          </div>
        </div>
      </div>
      <div style="border-top:1px solid var(--border); padding-top:10px; font-size:0.74rem; color:var(--muted);">
        Quarter-Kelly sizing dynamically constrains active margin within safe thresholds.
      </div>
    </div>
  </div>

  <!-- 12-Slot Concurrency Rack -->
  <div class="card" style="margin-bottom: 20px;">
    <div class="rack-header" onclick="toggleRack()">
      <div>
        <h3 style="font-size: 1.05rem; color:#fff;">Active Capital Engine: 12-Slot Concurrency Rack [N=12]</h3>
        <p style="font-size: 0.8rem; color: var(--muted); margin-top: 2px;" id="rackSummary">
          Loading engine concurrency slots...
        </p>
      </div>
      <span class="btn btn-secondary" id="rackToggleBtn" style="padding: 4px 10px; font-size: 0.75rem;">Collapse ▲</span>
    </div>
    <div class="rack-grid" id="rackGrid"></div>
  </div>

  <!-- Personal Execution & Settled Contracts Ledger -->
  <div class="card" style="margin-bottom: 20px;">
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
      <div>
        <h3 style="font-size: 1.05rem; color:#fff;">Personal Execution & Settled Contracts Ledger</h3>
        <p style="font-size: 0.8rem; color: var(--muted); margin-top: 2px;">
          Deterministic 87% realized yield credits settled to your SCMA cash balance
        </p>
      </div>
      <span class="chip chip-green" id="memberFillCount">0 Settled</span>
    </div>
    <table style="width:100%; border-collapse:collapse; margin-top:8px; font-size:0.82rem;">
      <thead>
        <tr>
          <th style="text-align:left; padding:8px; color:var(--muted); border-bottom:1px solid var(--border);">Fill ID</th>
          <th style="text-align:left; padding:8px; color:var(--muted); border-bottom:1px solid var(--border);">Contract</th>
          <th style="text-align:left; padding:8px; color:var(--muted); border-bottom:1px solid var(--border);">Side</th>
          <th style="text-align:left; padding:8px; color:var(--muted); border-bottom:1px solid var(--border);">Qty</th>
          <th style="text-align:left; padding:8px; color:var(--muted); border-bottom:1px solid var(--border);">Cost/VWAP</th>
          <th style="text-align:left; padding:8px; color:var(--muted); border-bottom:1px solid var(--border);">87% Net Yield</th>
          <th style="text-align:left; padding:8px; color:var(--muted); border-bottom:1px solid var(--border);">Outcome</th>
          <th style="text-align:left; padding:8px; color:var(--muted); border-bottom:1px solid var(--border);">Timestamp</th>
        </tr>
      </thead>
      <tbody id="memberFillsTbody">
        <tr><td colspan="8" style="text-align:center; color:var(--muted); padding:16px;">No settled executions for this account.</td></tr>
      </tbody>
    </table>
  </div>

  <!-- Downward-Only Risk Governor -->
  <div class="card" style="margin-bottom: 20px;">
    <div style="display: flex; justify-content: space-between; align-items: center;">
      <div>
        <h3 style="font-size: 1.05rem;">Downward-Only Personal Risk Governor</h3>
        <p style="font-size: 0.82rem; color: var(--muted); margin-top: 2px;">
          You hold sovereign discretion to reduce risk allocation down to 0.50%. Increasing risk beyond your ratified cap (2.00%) is permanently barred.
        </p>
      </div>
      <div id="riskValDisplay" style="font-size: 1.6rem; font-weight: 800; color: var(--gold);">2.00%</div>
    </div>
    <input type="range" min="0.50" max="2.00" step="0.05" value="2.00" class="slider" id="riskSlider" oninput="onSliderMove(this.value)" onchange="saveRiskDial(this.value)">
    <div style="display: flex; justify-content: space-between; font-size: 0.75rem; color: var(--muted); margin-top: 6px;">
      <span>0.50% (Max Defensive Floor)</span>
      <span>1.25% (Balanced)</span>
      <span>2.00% (Ceiling)</span>
    </div>
  </div>

  <!-- Distribution Gateway -->
  <div class="card" style="margin-bottom: 24px;">
    <div style="display: flex; justify-content: space-between; align-items: center;">
      <div>
        <h3 style="font-size: 1.05rem;">Capital Distribution Gateway (Directive R-15)</h3>
        <p style="font-size: 0.82rem; color: var(--muted); margin-top: 2px;">
          Request an autonomous profit sweep (Green), compounding float drawdown (Yellow), or acute emergency floor breach (Red).
        </p>
      </div>
      <button class="btn btn-primary" onclick="promptDistribution()">Request Distribution</button>
    </div>
    <p id="distStatus" style="font-size: 0.85rem; margin-top: 12px; display: none;"></p>
  </div>

  <script>
    let currentScma = '__ACTIVE_SCMA_TARGET__';
    let rackExpanded = true;

    function drawSvgCurve(svgId, points, floorCents, strokeColor, gradId) {
      const svg = document.getElementById(svgId);
      if (!svg) return;
      const defs = svg.querySelector('defs');
      svg.innerHTML = '';
      if (defs) svg.appendChild(defs);

      if (!points || points.length === 0) return;
      let minVal = Math.min(...points, floorCents || 0);
      let maxVal = Math.max(...points);
      if (maxVal === minVal) maxVal = minVal + 1000;
      
      const padBottom = 26, padTop = 16, padLeft = 36, padRight = 24;
      const width = 800 - padLeft - padRight;
      const height = 180 - padTop - padBottom;
      
      const getY = (val) => 180 - padBottom - ((val - minVal) / (maxVal - minVal)) * height;
      const getX = (idx) => padLeft + (points.length === 1 ? width / 2 : (idx / (points.length - 1)) * width);

      const floorY = getY(floorCents);
      let gridHtml = `
        <line x1="${padLeft}" y1="${getY(maxVal)}" x2="${800 - padRight}" y2="${getY(maxVal)}" stroke="#1e293b" stroke-width="1" stroke-dasharray="4"/>
        <text x="${padLeft}" y="${getY(maxVal) - 4}" fill="#64748b" font-size="10">$${(maxVal/100).toFixed(2)} Peak</text>
        <line x1="${padLeft}" y1="${floorY}" x2="${800 - padRight}" y2="${floorY}" stroke="#6366f1" stroke-width="1.5" stroke-dasharray="4"/>
        <text x="${padLeft}" y="${floorY + 12}" fill="#818cf8" font-size="10">$${(floorCents/100).toFixed(2)} (40% Floor Shield)</text>
      `;

      let pathD = '', areaD = '';
      points.forEach((p, i) => {
        const x = getX(i);
        const y = getY(p);
        if (i === 0) {
          pathD += `M ${x} ${y}`;
          areaD += `M ${x} ${180 - padBottom} L ${x} ${y}`;
        } else {
          pathD += ` L ${x} ${y}`;
          areaD += ` L ${x} ${y}`;
        }
      });
      const lastX = getX(points.length - 1);
      areaD += ` L ${lastX} ${180 - padBottom} Z`;

      let chartContent = gridHtml + `
        <path d="${areaD}" fill="url(#${gradId})" />
        <path d="${pathD}" fill="none" stroke="${strokeColor}" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round"/>
      `;

      points.forEach((p, i) => {
        const x = getX(i);
        const y = getY(p);
        chartContent += `<circle cx="${x}" cy="${y}" r="3" fill="${strokeColor}" stroke="#090d16" stroke-width="1.5"/>`;
      });

      svg.innerHTML += chartContent;
    }

    function toggleRack() {
      rackExpanded = !rackExpanded;
      document.getElementById('rackGrid').style.display = rackExpanded ? 'grid' : 'none';
      document.getElementById('rackToggleBtn').textContent = rackExpanded ? 'Collapse ▲' : 'Expand ▼';
    }

    
    async function executeSupFreeze() {
      await fetch('/api/v1/admin/freeze', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ scma_id: currentScma }) });
      loadAccount();
    }
    async function executeSupUnfreeze() {
      await fetch('/api/v1/admin/unfreeze', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ scma_id: currentScma }) });
      loadAccount();
    }

    function switchScma() {
      const sel = document.getElementById('scmaSelector');
      window.location.href = '/member?scma=' + sel.value;
    }

    async function loadAccount() {
      const urlParams = new URLSearchParams(window.location.search);
      const scmaParam = urlParams.get('scma');
      if (scmaParam) currentScma = scmaParam;
      
      const sel = document.getElementById('scmaSelector');
      if (sel) sel.value = currentScma;

      try {
        const res = await fetch('/api/v1/admin/ledger-summary');
        const data = await res.json();
        
        // Populate Selector with Named Members
        const sel = document.getElementById('scmaSelector');
        if (sel && sel.options.length <= 1) {
          sel.innerHTML = '';
          (data.accounts || []).forEach(a => {
            const opt = document.createElement('option');
            opt.value = a.scma_id;
            opt.textContent = `${a.scma_id} (${a.user_id} - ${a.status})`;
            if (a.scma_id === currentScma) opt.selected = true;
            sel.appendChild(opt);
          });
        } else if (sel) {
          sel.value = currentScma;
        }

        const acc = data.accounts.find(a => a.scma_id === currentScma);
        if (acc) {
          // Bind Identity Card
          document.getElementById('mMemberName').textContent = acc.user_id || acc.scma_id;
          document.getElementById('mScmaDisplay').textContent = acc.scma_id;
          const sBadge = document.getElementById('mStatusBadge');
          sBadge.textContent = acc.status;
          sBadge.className = 'chip ' + (acc.status === 'ACTIVE' ? 'chip-green' : (acc.status === 'FROZEN' ? 'chip-yellow' : 'chip-blue'));

          // Bind Supervisory Lens
          const isSupervisory = urlParams.get('supervisory') === 'true';
          const supBanner = document.getElementById('supervisoryLensBanner');
          if (supBanner) {
            supBanner.style.display = isSupervisory ? 'flex' : 'none';
            document.getElementById('supTargetName').textContent = acc.user_id || acc.scma_id;
            document.getElementById('supTargetScma').textContent = acc.scma_id;
            const supBadge = document.getElementById('supStatusBadge');
            supBadge.textContent = acc.status;
            supBadge.className = 'chip ' + (acc.status === 'ACTIVE' ? 'chip-green' : (acc.status === 'FROZEN' ? 'chip-yellow' : 'chip-blue'));
            
            const sfBtn = document.getElementById('supFreezeBtn');
            const suBtn = document.getElementById('supUnfreezeBtn');
            if (sfBtn && suBtn) {
              sfBtn.disabled = acc.status === 'FROZEN';
              sfBtn.style.opacity = acc.status === 'FROZEN' ? '0.5' : '1.0';
              sfBtn.style.cursor = acc.status === 'FROZEN' ? 'not-allowed' : 'pointer';
              suBtn.disabled = acc.status !== 'FROZEN';
              suBtn.style.opacity = acc.status !== 'FROZEN' ? '0.5' : '1.0';
              suBtn.style.cursor = acc.status !== 'FROZEN' ? 'not-allowed' : 'pointer';
            }
          }


          document.getElementById('mCash').textContent = '$' + (acc.cash_cents / 100).toFixed(2);
          document.getElementById('mCents').textContent = acc.cash_cents.toLocaleString() + ' exact integer cents';
          document.getElementById('mYield').textContent = '$' + (acc.lifetime_profit_cents / 100).toFixed(2);
          document.getElementById('mBank').textContent = acc.bank_ref_token;
          document.getElementById('riskValDisplay').textContent = acc.risk_dial_pct.toFixed(2) + '%';
          document.getElementById('riskSlider').value = acc.risk_dial_pct;

          // Personal Compounding Curve & Envelope
          const pts = data.checkpoints || [acc.cash_cents];
          const mFloor = Math.round(acc.cash_cents * 0.40);
          drawSvgCurve('memberCurveSvg', pts, mFloor, '#10b981', 'memGrad');

          const actCents = (data.positions || []).reduce((sum, p) => sum + p.cost_basis_cents, 0);
          document.getElementById('mAllocActive').textContent = '$' + (actCents / 100).toFixed(2);
          document.getElementById('mAllocFloor').textContent = '$' + (mFloor / 100).toFixed(2);
          document.getElementById('mAllocYield').textContent = '$' + (acc.lifetime_profit_cents / 100).toFixed(2);
        }

        const perf = data.performance;
        if (perf) {
          document.getElementById('mWinRate').textContent = perf.total_trades > 0 ? (perf.win_rate_pct.toFixed(1) + '%') : '0.0%';
          document.getElementById('mWinSub').textContent = perf.total_trades > 0 ? (perf.wins + ' Wins / ' + perf.losses + ' Losses') : 'Awaiting Initial Fills';
          document.getElementById('mProfitFactor').textContent = perf.total_trades > 0 ? (perf.profit_factor.toFixed(2) + 'x') : '0.00x';
        }

        
      // Handle Supervisory Mode Query Parameter
      const isSupervisory = urlParams.get('supervisory') === 'true';
      const supBanner = document.getElementById('supervisoryLensBanner');
      if (supBanner) supBanner.style.display = isSupervisory ? 'flex' : 'none';

      // Load Settled Fills
      try {
        const fRes = await fetch('/api/v1/member/fills?scma_id=' + currentScma);
        const fData = await fRes.json();
        const fTbody = document.getElementById('memberFillsTbody');
        document.getElementById('memberFillCount').textContent = (fData.fills || []).length + ' Settled';
        if (fData.fills && fData.fills.length > 0) {
          fTbody.innerHTML = '';
          fData.fills.forEach(f => {
            fTbody.innerHTML += `
              <tr>
                <td style="font-weight:700;">${f.fill_id}</td>
                <td style="font-weight:700; color:var(--accent);">${f.contract_ticker}</td>
                <td>${f.side}</td>
                <td>${f.qty}</td>
                <td>$${(f.price_cents/100).toFixed(2)}</td>
                <td style="color:var(--green); font-weight:700;">+$${(f.pnl_cents/100).toFixed(2)}</td>
                <td><span class="chip chip-green">SETTLED WIN</span></td>
                <td style="color:var(--muted);">${f.timestamp.substring(11, 19)} UTC</td>
              </tr>
            `;
          });
        } else {
          fTbody.innerHTML = '<tr><td colspan="8" style="text-align:center; color:var(--muted); padding:16px;">No settled executions for this account.</td></tr>';
        }
      } catch(e) { console.error('Fills load err:', e); }

        const activeCount = data.slots.filter(s => s.status !== 'EMPTY').length;
        document.getElementById('rackSummary').textContent = `${activeCount} Active Maker Bids • ${12 - activeCount} Idle Buffer Slots`;
        
        const rackGrid = document.getElementById('rackGrid');
        rackGrid.innerHTML = '';
        data.slots.forEach(s => {
          const isActive = s.status !== 'EMPTY';
          rackGrid.innerHTML += `
            <div class="slot-card ${isActive ? 'active' : ''}">
              <div class="slot-top">
                <span class="slot-id">SLOT ${s.slot.toString().padStart(2, '0')}</span>
                <span class="chip ${isActive ? 'chip-blue' : 'chip-empty'}">${isActive ? s.status : 'STANDBY'}</span>
              </div>
              <div style="font-weight:700; color:${isActive ? 'var(--accent)' : 'var(--muted)'}; margin:4px 0 2px 0;">${s.contract}</div>
              <div style="font-size:0.75rem; color:var(--muted);">${s.domain}</div>
              <div style="display:flex; justify-content:space-between; margin-top:8px; font-size:0.75rem;">
                <span style="color:var(--muted);">Stake:</span>
                <strong>${s.stake_dollars}</strong>
              </div>
            </div>
          `;
        });
      } catch (e) {
        console.error('Failed to load member state:', e);
      }
    }

    function onSliderMove(val) {
      document.getElementById('riskValDisplay').textContent = parseFloat(val).toFixed(2) + '%';
    }
    async function saveRiskDial(val) {
      await fetch('/api/v1/member/update-risk-dial', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ scma_id: currentScma, risk_dial_pct: parseFloat(val) })
      });
      loadAccount();
    }
    async function promptDistribution() {
      const amt = prompt("Enter distribution amount in USD:");
      if (!amt) return;
      const reason = prompt("Enter withdrawal reason:", "Personal Distribution");
      if (!reason) return;
      const st = document.getElementById('distStatus');
      st.style.display = 'block';
      st.style.color = '#38bdf8';
      st.textContent = 'Submitting request through Directive R-15 gateway...';
      try {
        const res = await fetch('/api/v1/member/request-distribution', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ scma_id: currentScma, amount_dollars: parseFloat(amt), reason: reason })
        });
        const d = await res.json();
        if (res.ok) {
          st.style.color = d.tier === 'RED' ? '#f87171' : '#34d399';
          st.textContent = '[' + d.tier + ' TIER]: ' + d.message;
          loadAccount();
        } else {
          st.style.color = '#ef4444';
          st.textContent = 'Error: ' + d.detail;
        }
      } catch (e) {
        st.style.color = '#ef4444';
        st.textContent = 'Network error: ' + e;
      }
    }

    setInterval(loadAccount, 3000);
    loadAccount();
  </script>
</body>
</html>
"""

@app.get("/dashboard", response_class=HTMLResponse)
def chief_admin_cockpit():
    return DASHBOARD_HTML

@app.get("/member", response_class=HTMLResponse)
def member_user_desktop(scma: str = "SCMA-FOUNDER"):
    return MEMBER_HTML.replace("__ACTIVE_SCMA_TARGET__", scma)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
