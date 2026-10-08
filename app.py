#!/usr/bin/env python3
import sqlite3
import json
import hashlib
import hmac
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException, Request
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

def append_audit_log(cursor, actor_id: str, action: str, payload: dict):
    cursor.execute("SELECT entry_hash FROM audit_log_records ORDER BY record_id DESC LIMIT 1;")
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

    # Query Active Positions (Live Table)
    cursor.execute("SELECT * FROM positions WHERE status != 'CLOSED';")
    pos_rows = cursor.fetchall()
    positions = []
    for p in pos_rows:
        positions.append({
            "contract": p["contract_ticker"], "domain": p["domain"], "venue": p["venue"],
            "side": p["side"], "qty": p["qty"], "vwap": f"${p['vwap_cents']/100:.2f}",
            "cost": f"${p['cost_basis_cents']/100:.2f}", "mtm": f"${p['mtm_cents']/100:.2f}",
            "status": p["status"]
        })

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

    return {
        "system_mode": GLOBAL_STATE["system_mode"],
        "total_cash_cents": total_cash,
        "total_profit_cents": total_profit,
        "dry_powder_cents": dry_powder,
        "active_margin_cents": total_cash - dry_powder,
        "cfcp_meter_cents": int(total_profit * 0.10),
        "faep_meter_cents": int(total_profit * 0.03),
        "accounts": accounts,
        "positions": positions,
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
        raise HTTPException(status_code=400, detail="Risk dial exceeds approved administrative ceiling.")
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
        return {"status": "SUCCESS", "tier": tier, "message": f"Compounding Float Drawdown approved. Voucher: {v_id}"}
    else:
        tier = "RED"
        v_id = emit_outbox_voucher(cursor, "EMERGENCY_PETITION_STAGED", req.scma_id, {
            "tier": tier, "cents": cents, "dollars": req.amount_dollars, "reason": req.reason, "bank_ref": acc["bank_ref_token"]
        })
        cursor.execute("UPDATE accounting_outbox_events SET status = 'PENDING_CO_SIGN' WHERE event_id = ?;", (v_id,))
        append_audit_log(cursor, req.scma_id, "EMERGENCY_PETITION_LOCKED", {"cents": cents, "voucher_id": v_id, "reason": req.reason})
        conn.commit(); conn.close()
        return {"status": "PENDING_DUAL_CONTROL", "tier": tier, "voucher_id": v_id, "message": "Emergency Floor Breach: 24h Cooling Hold. Staged in Admin Queue for co-signature."}

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
# DASHBOARD TEMPLATES (PURE NATIVE SVG, ZERO EXTERNAL CDNS)
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

  <!-- Executive Capital Row -->
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

  <!-- Performance Ratio Grid -->
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
      <div class="card-value" style="color: var(--gold);">-1.85%</div>
      <div class="card-sub">5.0% Administrative Ceiling</div>
    </div>
  </div>

  <!-- Native SVG Compounding Curve -->
  <div class="chart-box">
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
      <div>
        <h3 style="font-size:1.05rem;">Lineage Equity Compounding Curve</h3>
        <p style="font-size:0.8rem; color:var(--muted);">Continuous integer-cent growth path vs. 40% capital preservation floor</p>
      </div>
      <span class="chip chip-blue">NATIVE VECTOR HUD (ZERO CDN)</span>
    </div>
    <svg viewBox="0 0 800 160" style="width:100%; height:160px; overflow:visible;">
      <defs>
        <linearGradient id="curveGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="#38bdf8" stop-opacity="0.35"/>
          <stop offset="100%" stop-color="#38bdf8" stop-opacity="0.0"/>
        </linearGradient>
      </defs>
      <!-- Grid lines -->
      <line x1="0" y1="30" x2="800" y2="30" stroke="#1f293d" stroke-dasharray="4"/>
      <line x1="0" y1="75" x2="800" y2="75" stroke="#1f293d" stroke-dasharray="4"/>
      <line x1="0" y1="120" x2="800" y2="120" stroke="#1f293d" stroke-dasharray="4"/>
      <!-- Dry powder floor line ($40.00) -->
      <line x1="0" y1="110" x2="800" y2="110" stroke="#f59e0b" stroke-width="1.5" stroke-dasharray="6"/>
      <text x="10" y="105" fill="#f59e0b" font-size="11" font-weight="700">40% DRY-POWDER FLOOR ($40.00)</text>
      <!-- Compounding curve path -->
      <path d="M 0 135 C 200 132, 400 120, 550 95 C 680 75, 750 45, 800 25 L 800 150 L 0 150 Z" fill="url(#curveGrad)"/>
      <path d="M 0 135 C 200 132, 400 120, 550 95 C 680 75, 750 45, 800 25" fill="none" stroke="#38bdf8" stroke-width="3"/>
      <!-- Milestone nodes -->
      <circle cx="0" cy="135" r="4" fill="#38bdf8"/>
      <circle cx="400" cy="120" r="4" fill="#38bdf8"/>
      <circle cx="550" cy="95" r="4" fill="#10b981"/>
      <circle cx="800" cy="25" r="5" fill="#34d399"/>
      <text x="730" y="18" fill="#34d399" font-size="12" font-weight="800">$100.00+</text>
    </svg>
  </div>

  <!-- Active Positions Table -->
  <div class="chart-box">
    <h3 style="font-size:1.05rem;">Active Portfolio Positions & Inside-Spread Resting Bids</h3>
    <table>
      <thead>
        <tr>
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
      <tbody id="posTable"></tbody>
    </table>
  </div>

  <!-- Ring 1 Roster -->
  <div class="chart-box">
    <div style="display:flex; justify-content:space-between; align-items:center;">
      <h3 style="font-size:1.05rem;">Ring 1 Multi-Account Registry (6 SCMAs)</h3>
      <span style="font-size:0.8rem; color:var(--muted);">ADR-008 Exact-Cent Math & ADR-011 Security Air-Gap</span>
    </div>
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

  <!-- Emergency Distribution Queue -->
  <div class="chart-box" style="border-color: #7f1d1d;">
    <h3 style="font-size:1.05rem; color:#f87171;">Emergency Distribution & Co-Signature Queue (Directive R-15)</h3>
    <p style="font-size:0.8rem; color:var(--muted); margin-top:2px;">Dual-control co-signature required for floor breaches.</p>
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
        
        // Dynamic Performance Cards
        const perf = data.performance;
        if (perf) {
          const wrEl = document.getElementById('winRateVal');
          if (wrEl) wrEl.textContent = perf.total_trades > 0 ? (perf.win_rate_pct.toFixed(1) + '%') : '0.0%';
          const wrSub = document.getElementById('winRateSub');
          if (wrSub) wrSub.textContent = perf.total_trades > 0 ? (perf.wins + ' Wins / ' + perf.losses + ' Losses') : 'Awaiting Initial Fills';

          const pfEl = document.getElementById('profitFactorVal');
          if (pfEl) pfEl.textContent = perf.total_trades > 0 ? (perf.profit_factor.toFixed(2) + 'x') : '0.00x';
          const pfSub = document.getElementById('profitFactorSub');
          if (pfSub) pfSub.textContent = perf.total_trades > 0 ? 'Verified Execution' : 'Expectancy: $0.00';
        }
        document.getElementById('totEquity').textContent = '$' + (data.total_cash_cents / 100).toFixed(2);
        document.getElementById('totCents').textContent = data.total_cash_cents.toLocaleString() + ' exact integer cents';
        document.getElementById('dryFloor').textContent = '$' + (data.dry_powder_cents / 100).toFixed(2);
        document.getElementById('actMargin').textContent = '$' + (data.active_margin_cents / 100).toFixed(2);
        document.getElementById('cfcpPool').textContent = '$' + (data.cfcp_meter_cents / 100).toFixed(2);

        // Positions table
        const posTbody = document.getElementById('posTable');
        posTbody.innerHTML = '';
        if (data.positions.length === 0) {
          posTbody.innerHTML = '<tr><td colspan="9" style="text-align:center; color:var(--muted); padding:20px;">No open positions. Inventory flat (Standing by for orders).</td></tr>';
        } else {
          data.positions.forEach(p => {
          posTbody.innerHTML += `
            <tr>
              <td style="font-weight:700; color:var(--accent);">${p.contract}</td>
              <td>${p.domain}</td>
              <td>${p.venue}</td>
              <td>${p.side}</td>
              <td>${p.qty}</td>
              <td>${p.vwap}</td>
              <td>${p.cost}</td>
              <td style="color:var(--green); font-weight:700;">${p.mtm}</td>
              <td><span class="chip chip-blue">${p.status}</span></td>
            </tr>
          `;
        });
        }

        // Roster table
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

        // Emergency petitions table
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
        }
      } catch (e) {
        console.error('Data refresh error:', e);
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
    .btn-tab { background: transparent; color: var(--muted); border: 1px solid var(--border); padding: 6px 14px; border-radius: 6px; cursor: pointer; }
    .btn-tab.active { background: #1e293b; color: var(--accent); border-color: var(--accent); font-weight: 700; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; margin-bottom: 20px; }
    .card { background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 18px; }
    .card-title { font-size: 0.75rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 6px; }
    .card-value { font-size: 1.8rem; font-weight: 800; color: #fff; }
    .card-sub { font-size: 0.8rem; color: var(--muted); margin-top: 4px; }
    .hud-box { background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 20px; margin-bottom: 20px; }
    .chip { padding: 3px 8px; border-radius: 4px; font-size: 0.72rem; font-weight: 700; }
    .chip-green { background: #064e3b; color: #34d399; }
    .slider { width: 100%; margin-top: 10px; accent-color: var(--accent); }
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

  <!-- Covenant Card -->
  <div class="card" style="margin-bottom: 20px; border-color: rgba(56, 189, 248, 0.3);">
    <h3 style="color: var(--accent); font-size: 1.05rem;">A Better Financial Starting Point</h3>
    <p style="font-size: 0.85rem; color: var(--muted); margin: 6px 0 12px 0; line-height: 1.5;">
      Welcome to your private generational compounding sub-ledger. You do not need to analyze charts, pick prediction contracts, or monitor markets. PDEUE's algorithmic engine evaluates real-world public data, enforces strict inside-spread bids, and compounds capital automatically.
    </p>
    <div style="display: flex; gap: 10px; flex-wrap: wrap;">
      <span class="chip chip-green">✓ 100% Isolated Capital</span>
      <span class="chip chip-green">✓ 87% Reinvestment Compounding</span>
      <span class="chip chip-green">✓ Zero Trading Losses Shared</span>
      <span class="chip chip-green">✓ Bank Air-Gap Protected</span>
    </div>
  </div>

  <!-- Member Capital Metrics -->
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
      <div class="card-value" id="mBank" style="font-size: 1.15rem; color: var(--muted); padding-top: 6px;">EXT-REF-FBO-FOUNDER-****8800</div>
      <div class="card-sub">ADR-011 Zero-Credential Air-Gap</div>
    </div>
  </div>

  <!-- 4-Card Performance Ratio Grid -->
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
      <div class="card-title">Sizing Model</div>
      <div class="card-value" style="color: #fff;">Quarter-Kelly</div>
      <div class="card-sub">Down-only Personal Governor</div>
    </div>
    <div class="card">
      <div class="card-title">Max Drawdown</div>
      <div class="card-value" style="color: var(--gold);">-1.85%</div>
      <div class="card-sub">5.0% Administrative Ceiling</div>
    </div>
  </div>

  <!-- Dynamic HUD View Switcher -->
  <div class="hud-box">
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:16px;">
      <div style="display:flex; gap:8px;">
        <button class="btn-tab active" id="btnHud1" onclick="switchHud(1)">● Compounding Horizon</button>
        <button class="btn-tab" id="btnHud2" onclick="switchHud(2)">○ Asset Engine Rings</button>
        <button class="btn-tab" id="btnHud3" onclick="switchHud(3)">○ Settlement Radar</button>
      </div>
      <span class="chip chip-green" style="background:#0c4a6e; color:var(--accent);">INTERACTIVE TELEMETRY HUD</span>
    </div>

    <!-- View 1: Compounding Horizon Area Curve -->
    <div id="hudView1">
      <p style="font-size:0.82rem; color:var(--muted); margin-bottom:12px;">Stepped compounding trajectory from micro-seed through $25,000 float ceiling and recurring bank sweeps.</p>
      <svg viewBox="0 0 800 160" style="width:100%; height:160px; overflow:visible;">
        <defs>
          <linearGradient id="memGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stop-color="#10b981" stop-opacity="0.35"/>
            <stop offset="100%" stop-color="#10b981" stop-opacity="0.0"/>
          </linearGradient>
        </defs>
        <line x1="0" y1="40" x2="800" y2="40" stroke="#1f293d" stroke-dasharray="4"/>
        <line x1="0" y1="80" x2="800" y2="80" stroke="#1f293d" stroke-dasharray="4"/>
        <line x1="0" y1="120" x2="800" y2="120" stroke="#1f293d" stroke-dasharray="4"/>
        <path d="M 0 140 C 250 138, 450 115, 600 80 C 700 50, 750 30, 800 15 L 800 155 L 0 155 Z" fill="url(#memGrad)"/>
        <path d="M 0 140 C 250 138, 450 115, 600 80 C 700 50, 750 30, 800 15" fill="none" stroke="#10b981" stroke-width="3"/>
        <circle cx="0" cy="140" r="4" fill="#38bdf8"/>
        <circle cx="450" cy="115" r="4" fill="#38bdf8"/>
        <circle cx="600" cy="80" r="4" fill="#f59e0b"/>
        <circle cx="800" cy="15" r="5" fill="#10b981"/>
        <text x="10" y="132" fill="#38bdf8" font-size="11" font-weight="700">Seed ($100)</text>
        <text x="430" y="105" fill="#38bdf8" font-size="11">100 Trades</text>
        <text x="580" y="70" fill="#f59e0b" font-size="11">$25k Float Ceiling</text>
        <text x="710" y="12" fill="#10b981" font-size="12" font-weight="800">Bank Sweeps ↗</text>
      </svg>
    </div>

    <!-- View 2: Concentric Asset Rings -->
    <div id="hudView2" style="display:none;">
      <div style="display:flex; gap:32px; align-items:center;">
        <svg viewBox="0 0 200 200" style="width:180px; height:180px;">
          <!-- Outer Ring: Active Margin -->
          <circle cx="100" cy="100" r="80" fill="none" stroke="#1e293d" stroke-width="12"/>
          <circle cx="100" cy="100" r="80" fill="none" stroke="#38bdf8" stroke-width="12" stroke-dasharray="502" stroke-dashoffset="200" stroke-linecap="round"/>
          <!-- Middle Ring: 40% Floor Shield -->
          <circle cx="100" cy="100" r="62" fill="none" stroke="#1e293d" stroke-width="12"/>
          <circle cx="100" cy="100" r="62" fill="none" stroke="#10b981" stroke-width="12" stroke-dasharray="389" stroke-dashoffset="150" stroke-linecap="round"/>
          <!-- Inner Ring: Swept Yield -->
          <circle cx="100" cy="100" r="44" fill="none" stroke="#1e293d" stroke-width="12"/>
          <circle cx="100" cy="100" r="44" fill="none" stroke="#a855f7" stroke-width="12" stroke-dasharray="276" stroke-dashoffset="210" stroke-linecap="round"/>
        </svg>
        <div style="flex:1;">
          <h4 style="margin-bottom:8px; font-size:1rem;">Asset Engine Allocation Rings</h4>
          <p style="font-size:0.82rem; color:var(--muted); margin-bottom:12px;">Three concentric safety rings protect principal and separate active margin from liquid floor cash.</p>
          <div style="display:grid; gap:8px; font-size:0.85rem;">
            <div style="display:flex; justify-content:space-between; border-bottom:1px solid var(--border); padding-bottom:4px;">
              <span style="color:#38bdf8;">● Outer Cyan Ring (Active Margin Float)</span>
              <strong>$60.00 (60%)</strong>
            </div>
            <div style="display:flex; justify-content:space-between; border-bottom:1px solid var(--border); padding-bottom:4px;">
              <span style="color:#10b981;">● Middle Emerald Ring (40% Dry-Powder Floor)</span>
              <strong>$40.00 (40%)</strong>
            </div>
            <div style="display:flex; justify-content:space-between; padding-bottom:4px;">
              <span style="color:#a855f7;">● Inner Purple Ring (Swept Yield & 4.5% APY)</span>
              <strong>$0.00</strong>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- View 3: Settlement Radar -->
    <div id="hudView3" style="display:none;">
      <h4 style="margin-bottom:8px; font-size:1rem;">Settlement Radar & 87/10/3 Waterfall Visualizer</h4>
      <p style="font-size:0.82rem; color:var(--muted); margin-bottom:14px;">Recent contract settlements with automated waterfall distribution into personal compounding and lineage treasury.</p>
      <div style="background:#090d16; border:1px solid var(--border); border-radius:6px; padding:12px; margin-bottom:10px;">
        <div style="display:flex; justify-content:space-between; align-items:center;">
          <strong style="color:var(--accent);">KX-MIA-FRZ-32 (NOAA Miami Temp)</strong>
          <span class="chip chip-green">SETTLED / WON</span>
        </div>
        <div style="font-size:0.82rem; color:var(--muted); margin:4px 0 8px 0;">Gross Payout: $4.50 • Net Profit: $3.20</div>
        <!-- Progress Bar for 87/10/3 Split -->
        <div style="display:flex; height:10px; border-radius:5px; overflow:hidden;">
          <div style="width:87%; background:#38bdf8;" title="87% Member Compounding"></div>
          <div style="width:10%; background:#10b981;" title="10% Central Family Shield"></div>
          <div style="width:3%; background:#a855f7;" title="3% Platform Stewardship"></div>
        </div>
        <div style="display:flex; justify-content:space-between; font-size:0.75rem; color:var(--muted); margin-top:4px;">
          <span>87% Personal ($2.78)</span>
          <span>10% Family Shield ($0.32)</span>
          <span>3% Ops ($0.10)</span>
        </div>
      </div>
    </div>
  </div>

  <!-- Downward-Only Risk Governor -->
  <div class="card" style="margin-bottom: 20px;">
    <div style="display: flex; justify-content: space-between; align-items: center;">
      <div>
        <h3 style="font-size: 1.05rem;">Downward-Only Personal Risk Governor</h3>
        <p style="font-size: 0.82rem; color: var(--muted); margin-top: 2px;">
          You hold sovereign discretion to reduce your risk allocation down to 0.50%. Increasing risk beyond your ratified cap (2.00%) is barred.
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

    function switchScma() {
      const sel = document.getElementById('scmaSelector');
      window.location.href = '/member?scma=' + sel.value;
    }

    function switchHud(viewIdx) {
      document.getElementById('hudView1').style.display = viewIdx === 1 ? 'block' : 'none';
      document.getElementById('hudView2').style.display = viewIdx === 2 ? 'block' : 'none';
      document.getElementById('hudView3').style.display = viewIdx === 3 ? 'block' : 'none';
      document.getElementById('btnHud1').className = viewIdx === 1 ? 'btn-tab active' : 'btn-tab';
      document.getElementById('btnHud2').className = viewIdx === 2 ? 'btn-tab active' : 'btn-tab';
      document.getElementById('btnHud3').className = viewIdx === 3 ? 'btn-tab active' : 'btn-tab';
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
