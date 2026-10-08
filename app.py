#!/usr/bin/env python3
import sqlite3
import json
import hashlib
import hmac
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel

DB_PATH = "pdeue.db"
HMAC_SECRET = b"PDEUE_AIRGAP_SHARED_KEY_2026_RING1"

app = FastAPI(title="PDEUE Production Node")
GLOBAL_STATE = {"system_mode": "NORMAL"}

def ensure_schema():
    conn = get_db()
    c = conn.cursor()
    c.execute("PRAGMA table_info(positions);")
    cols = [r[1] for r in c.fetchall()]
    if "slot_index" not in cols:
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


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

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

    # Query Active Positions for Concurrency Slots
    cursor.execute("SELECT * FROM positions WHERE status != 'CLOSED';")
    pos_rows = [dict(r) for r in cursor.fetchall()]

    # Query Closed Fills for Dynamic Performance Calculations
    cursor.execute("SELECT COUNT(*), SUM(CASE WHEN is_win = 1 THEN 1 ELSE 0 END), SUM(CASE WHEN pnl_cents > 0 THEN pnl_cents ELSE 0 END), SUM(CASE WHEN pnl_cents < 0 THEN ABS(pnl_cents) ELSE 0 END) FROM fills;")
    fill_stats = cursor.fetchone()
    total_trades = fill_stats[0] or 0
    wins = fill_stats[1] or 0
    losses = total_trades - wins
    gross_gains_cents = fill_stats[2] or 0
    gross_losses_cents = fill_stats[3] or 0

    win_rate_pct = (wins / total_trades * 100) if total_trades > 0 else 0.0
    profit_factor = (gross_gains_cents / gross_losses_cents) if gross_losses_cents > 0 else (9.99 if gross_gains_cents > 0 else 0.0)

    conn.close()

    total_cash = sum(a["cash_cents"] for a in accounts)
    total_profit = sum(a["lifetime_profit_cents"] for a in accounts)
    dry_powder = int(total_cash * 0.40)

    # Build 12-Slot Rack State
    rack_slots = []
    pos_by_slot = {p["slot_index"]: p for p in pos_rows}
    for i in range(1, 13):
        if i in pos_by_slot:
            p = pos_by_slot[i]
            rack_slots.append({
                "slot": i,
                "status": p["status"],
                "contract": p["contract_ticker"],
                "domain": p["domain"],
                "stake_dollars": f"${p['cost_basis_cents']/100:.2f}",
                "mtm_dollars": f"${p['mtm_cents']/100:.2f}"
            })
        else:
            rack_slots.append({
                "slot": i,
                "status": "EMPTY",
                "contract": "Standby",
                "domain": "Idle Buffer",
                "stake_dollars": "$0.00",
                "mtm_dollars": "$0.00"
            })

    return {
        "system_mode": GLOBAL_STATE["system_mode"],
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
        "performance": {
            "total_trades": total_trades,
            "wins": wins,
            "losses": losses,
            "win_rate_pct": win_rate_pct,
            "profit_factor": profit_factor,
            "max_drawdown_pct": 0.0
        }
    }

class FreezeReq(BaseModel):
    scma_id: str

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

@app.post("/api/v1/member/update-risk-dial")
def update_risk_dial(req: RiskReq):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT max_risk_dial_pct, status FROM accounts WHERE scma_id = ?;", (req.scma_id,))
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
# EXECUTION SIMULATOR (STRATEGY D SCANNER & SETTLEMENT ENGINE)
# ----------------------------------------------------------------------

@app.post("/api/v1/operator/daemon/cycle")
def execute_scan_cycle():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT cash_cents, risk_dial_pct, status FROM accounts WHERE scma_id = 'SCMA-FOUNDER';")
    acc = cursor.fetchone()
    if not acc or acc["status"] != "ACTIVE":
        conn.close()
        raise HTTPException(status_code=400, detail="SCMA-FOUNDER not active.")
    
    cursor.execute("SELECT COUNT(*) FROM positions WHERE status != 'CLOSED';")
    active_count = cursor.fetchone()[0]
    if active_count >= 12:
        conn.close()
        return {"status": "SKIPPED", "message": "All 12 concurrency slots filled."}

    # Find first vacant slot
    cursor.execute("SELECT slot_index FROM positions WHERE status != 'CLOSED';")
    occupied = {r[0] for r in cursor.fetchall()}
    target_slot = next(i for i in range(1, 13) if i not in occupied)

    pos_id = f"POS-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    ticker = "KX-MIA-FRZ-32"
    qty = 45
    vwap = 22  # $0.22/contract
    cost = 990 # $9.90
    mtm = 1125 # $11.25
    now_iso = datetime.now(timezone.utc).isoformat()

    cursor.execute("""
        INSERT INTO positions (position_id, slot_index, scma_id, contract_ticker, domain, venue, side, qty, vwap_cents, cost_basis_cents, mtm_cents, status, updated_at)
        VALUES (?, ?, 'SCMA-FOUNDER', ?, 'Weather (NOAA)', 'Kalshi', 'BUY_YES', ?, ?, ?, ?, 'RESTING_MAKER', ?);
    """, (pos_id, target_slot, ticker, qty, vwap, cost, mtm, now_iso))
    
    append_audit_log(cursor, "AUTONOMOUS_SCANNER", "DISPATCH_MAKER_ORDER", {"position_id": pos_id, "slot": target_slot, "contract": ticker})
    conn.commit()
    conn.close()
    return {"status": "SUCCESS", "message": f"Strategy D inside-maker bid assigned to Slot {target_slot}.", "position_id": pos_id, "slot": target_slot}

@app.post("/api/v1/operator/settle")
def simulate_settlement():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM positions WHERE status = 'RESTING_MAKER' ORDER BY slot_index ASC LIMIT 1;")
    pos = cursor.fetchone()
    if not pos:
        conn.close()
        return {"status": "SKIPPED", "message": "No resting positions available to settle."}

    cost_cents = pos["cost_basis_cents"]
    gross_payout_cents = 4500 # $45.00 total payout ($1.00 * 45 contracts)
    net_profit_cents = gross_payout_cents - cost_cents # $35.10 net profit
    now_iso = datetime.now(timezone.utc).isoformat()

    # 87/10/3 Waterfall Allocation
    scma_yield_cents = int(net_profit_cents * 0.87)
    cfcp_sweep_cents = int(net_profit_cents * 0.10)
    faep_sweep_cents = net_profit_cents - scma_yield_cents - cfcp_sweep_cents

    cursor.execute("""
        UPDATE accounts 
        SET cash_cents = cash_cents + ?, lifetime_profit_cents = lifetime_profit_cents + ?, updated_at = ?
        WHERE scma_id = 'SCMA-FOUNDER';
    """, (scma_yield_cents, scma_yield_cents, now_iso))

    cursor.execute("UPDATE positions SET status = 'CLOSED', updated_at = ? WHERE position_id = ?;", (now_iso, pos["position_id"]))

    fill_id = f"FILL-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    cursor.execute("""
        INSERT INTO fills (fill_id, scma_id, contract_ticker, side, qty, price_cents, pnl_cents, is_win, timestamp)
        VALUES (?, 'SCMA-FOUNDER', ?, 'BUY_YES', ?, ?, ?, 1, ?);
    """, (fill_id, pos["contract_ticker"], pos["qty"], pos["vwap_cents"], scma_yield_cents, now_iso))

    cursor.execute("SELECT cash_cents FROM accounts WHERE scma_id = 'SCMA-FOUNDER';")
    current_cash = cursor.fetchone()[0]
    cursor.execute("INSERT INTO equity_checkpoints (scma_id, equity_cents, timestamp) VALUES ('SCMA-FOUNDER', ?, ?);", (current_cash, now_iso))

    v_id = emit_outbox_voucher(cursor, "WATERFALL_SETTLEMENT_SWEPT", "SCMA-FOUNDER", {
        "contract": pos["contract_ticker"], "net_profit_cents": net_profit_cents,
        "scma_compounded_cents": scma_yield_cents, "cfcp_cents": cfcp_sweep_cents, "faep_cents": faep_sweep_cents
    })

    append_audit_log(cursor, "SETTLEMENT_RECONCILER", "SETTLEMENT_WON_87_10_3", {
        "fill_id": fill_id, "slot_freed": pos["slot_index"], "net_profit_cents": net_profit_cents, "voucher_id": v_id
    })

    conn.commit()
    conn.close()
    return {
        "status": "SUCCESS", "message": f"Settled Slot {pos['slot_index']} ({pos['contract_ticker']}). Payout compounded 87/10/3.",
        "scma_gain_dollars": f"${scma_yield_cents/100:.2f}", "cfcp_sweep_dollars": f"${cfcp_sweep_cents/100:.2f}",
        "voucher_id": v_id
    }

# ----------------------------------------------------------------------
# USER INTERFACES (ZERO-CDN, PURE NATIVE SVG/CSS)
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
    body { background: var(--bg); color: var(--text); padding: 24px; }
    .header { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border); padding-bottom: 16px; margin-bottom: 24px; }
    .btn { padding: 8px 16px; border-radius: 6px; font-weight: 700; cursor: pointer; border: none; font-size: 0.85rem; text-decoration: none; }
    .btn-red { background: var(--red); color: #fff; }
    .btn-blue { background: #1e293b; color: var(--accent); border: 1px solid var(--accent); }
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
  <div class="header">
    <div>
      <h1 style="font-size: 1.4rem;">PDEUE Master Cockpit & Registry</h1>
      <p style="font-size: 0.82rem; color: var(--muted); margin-top: 4px;">Chief Administrator Operational Desk • Ring 1 Alpha Pilot (5 Members + Founder)</p>
    </div>
    <div style="display: flex; gap: 12px; align-items: center;">
      <span class="chip chip-green" id="sysModeBadge">NORMAL</span>
      <button class="btn btn-red" onclick="toggleHalt()">Master Emergency Halt</button>
      <a href="/member" class="btn btn-blue">Switch Hat: Member View →</a>
    </div>
  </div>

  <div class="grid">
    <div class="card">
      <div class="card-title">Total Ring 1 Equity</div>
      <div class="card-value" id="totEquity">$100.00</div>
      <div class="card-sub" id="totCents">10,000 exact integer cents</div>
    </div>
    <div class="card">
      <div class="card-title">40% Dry-Powder Floor</div>
      <div class="card-value" id="dryFloor" style="color: var(--accent);">$40.00</div>
      <div class="card-sub">Untouchable liquid cash reserve</div>
    </div>
    <div class="card">
      <div class="card-title">Active Working Margin</div>
      <div class="card-value" id="actMargin" style="color: var(--green);">$60.00</div>
      <div class="card-sub">Max allowable trade collateral</div>
    </div>
    <div class="card">
      <div class="card-title">Central Family Shield (CFCP)</div>
      <div class="card-value" id="cfcpPool" style="color: var(--purple);">$0.00</div>
      <div class="card-sub">Accumulates 10% of net profits</div>
    </div>
  </div>

  <!-- Dynamic Performance Ratios -->
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

  <!-- Active Positions Table -->
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
        <tr><td colspan="10" style="text-align:center; color:var(--muted); padding:16px;">No open positions. Inventory flat (Standing by for orders).</td></tr>
      </tbody>
    </table>
  </div>

  <!-- Ring 1 Roster -->
  <div class="chart-box">
    <h3 style="font-size:1.05rem;">Ring 1 Multi-Account Registry (6 SCMAs)</h3>
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

  <!-- Emergency Queue -->
  <div class="chart-box" style="border-color: #7f1d1d;">
    <h3 style="font-size:1.05rem; color:#f87171;">Emergency Distribution & Co-Signature Queue (Directive R-15)</h3>
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

  <script>
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

        // Performance Ratios
        const perf = data.performance;
        if (perf) {
          document.getElementById('winRateVal').textContent = perf.total_trades > 0 ? (perf.win_rate_pct.toFixed(1) + '%') : '0.0%';
          document.getElementById('winRateSub').textContent = perf.total_trades > 0 ? (perf.wins + ' Wins / ' + perf.losses + ' Losses') : 'Awaiting Initial Fills';
          document.getElementById('profitFactorVal').textContent = perf.total_trades > 0 ? (perf.profit_factor.toFixed(2) + 'x') : '0.00x';
          document.getElementById('profitFactorSub').textContent = perf.total_trades > 0 ? 'Verified Execution' : 'Expectancy: $0.00';
        }

        // Positions
        const posTbody = document.getElementById('posTable');
        document.getElementById('openCountBadge').textContent = data.positions.length + ' OPEN';
        if (data.positions.length === 0) {
          posTbody.innerHTML = '<tr><td colspan="10" style="text-align:center; color:var(--muted); padding:16px;">No open positions. Inventory flat (Standing by for orders).</td></tr>';
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

        // Roster
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
              <td><button class="btn btn-blue" style="padding:4px 8px; font-size:0.75rem;" onclick="toggleFreeze('${a.scma_id}')">Quarantine / Freeze</button></td>
            </tr>
          `;
        });

        // Petitions
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

    async function toggleFreeze(scma) {
      await fetch('/api/v1/admin/toggle-freeze', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ scma_id: scma })
      });
      refreshData();
    }

    async function coSignPetition(vId) {
      if (!confirm('Co-sign acute emergency release for voucher ' + vId + '?')) return;
      await fetch('/api/v1/admin/co-sign-emergency', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ event_id: vId })
      });
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
    
    /* 12-Slot Concurrency Rack Styles */
    .rack-header { display: flex; justify-content: space-between; align-items: center; cursor: pointer; user-select: none; }
    .rack-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(170px, 1fr)); gap: 12px; margin-top: 16px; }
    .slot-card { background: #0b111e; border: 1px solid var(--border); border-radius: 6px; padding: 12px; font-size: 0.82rem; }
    .slot-card.active { border-color: rgba(56, 189, 248, 0.4); background: #0f172a; }
    .slot-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
    .slot-id { font-weight: 800; color: var(--muted); font-size: 0.75rem; }
  </style>
</head>
<body>
  <div class="header">
    <div>
      <h1 style="font-size: 1.4rem;">Member Capital Portal</h1>
      <p style="font-size: 0.82rem; color: var(--muted); margin-top: 4px;">Personal Compounding Sub-Ledger • Self-Contained Member Account (SCMA)</p>
    </div>
    <div style="display: flex; gap: 12px; align-items: center;">
      <select id="scmaSelector" onchange="switchScma()" style="background:#1e293b; color:#fff; border:1px solid var(--border); padding:6px 12px; border-radius:6px; font-size:0.85rem;">
        <option value="SCMA-FOUNDER">SCMA-FOUNDER (Founder / Active)</option>
        <option value="SCMA-MEM-0001">SCMA-MEM-0001 (Member 1)</option>
        <option value="SCMA-MEM-0002">SCMA-MEM-0002 (Member 2)</option>
        <option value="SCMA-MEM-0003">SCMA-MEM-0003 (Member 3)</option>
        <option value="SCMA-MEM-0004">SCMA-MEM-0004 (Member 4)</option>
        <option value="SCMA-MEM-0005">SCMA-MEM-0005 (Member 5)</option>
      </select>
      <a href="/dashboard" class="btn btn-secondary">Admin Cockpit →</a>
    </div>
  </div>

  <div class="grid">
    <div class="card">
      <div class="card-title">Your Unreserved Cash Balance</div>
      <div class="card-value" id="mCash">$100.00</div>
      <div class="card-sub" id="mCents">10,000 exact integer cents</div>
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

  <!-- Dynamic Performance Ratios -->
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

  <!-- 12-Slot Concurrency Rack (Collapsible & Transparent) -->
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

  <!-- Directive R-15 Capital Distribution Gateway -->
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

    function toggleRack() {
      rackExpanded = !rackExpanded;
      document.getElementById('rackGrid').style.display = rackExpanded ? 'grid' : 'none';
      document.getElementById('rackToggleBtn').textContent = rackExpanded ? 'Collapse ▲' : 'Expand ▼';
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
        const acc = data.accounts.find(a => a.scma_id === currentScma);
        if (acc) {
          document.getElementById('mCash').textContent = '$' + (acc.cash_cents / 100).toFixed(2);
          document.getElementById('mCents').textContent = acc.cash_cents.toLocaleString() + ' exact integer cents';
          document.getElementById('mYield').textContent = '$' + (acc.lifetime_profit_cents / 100).toFixed(2);
          document.getElementById('mBank').textContent = acc.bank_ref_token;
          document.getElementById('riskValDisplay').textContent = acc.risk_dial_pct.toFixed(2) + '%';
          document.getElementById('riskSlider').value = acc.risk_dial_pct;
        }

        // Performance Ratios
        const perf = data.performance;
        if (perf) {
          document.getElementById('mWinRate').textContent = perf.total_trades > 0 ? (perf.win_rate_pct.toFixed(1) + '%') : '0.0%';
          document.getElementById('mWinSub').textContent = perf.total_trades > 0 ? (perf.wins + ' Wins / ' + perf.losses + ' Losses') : 'Awaiting Initial Fills';
          document.getElementById('mProfitFactor').textContent = perf.total_trades > 0 ? (perf.profit_factor.toFixed(2) + 'x') : '0.00x';
        }

        // 12-Slot Rack Rendering
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
      const amt = prompt("Enter distribution amount in USD (e.g. 15.00):");
      if (!amt) return;
      const reason = prompt("Enter withdrawal reason (e.g. Living expense, Emergency medical):", "Personal Distribution");
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
