#!/usr/bin/env python3
"""
PDEUE Stage 2 Core Desktops Server (Calibrated for $100 Real Seed Baseline)
- / (Automatic Redirect to /dashboard)
- /dashboard (Chief Administrator Cockpit)
- /member (Member User Desktop)
Zero external CDNs, ADR-008 integer cents, and SHA-256 audit chaining.
"""

import sqlite3
import json
import hashlib
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel

DB_PATH = "pdeue.db"
app = FastAPI(title="PDEUE Ring 1 Core Desktops")

GLOBAL_STATE = {
    "system_mode": "NORMAL"  # NORMAL or HALTED
}

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

# ----------------------------------------------------------------------
# API ENDPOINTS
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
    accounts = [dict(row) for row in cursor.fetchall()]
    conn.close()

    total_cash_cents = sum(acc["cash_cents"] for acc in accounts)
    total_profit_cents = sum(acc["lifetime_profit_cents"] for acc in accounts)
    dry_powder_cents = int(total_cash_cents * 0.40)

    return {
        "system_mode": GLOBAL_STATE["system_mode"],
        "total_cash_cents": total_cash_cents,
        "total_profit_cents": total_profit_cents,
        "dry_powder_cents": dry_powder_cents,
        "active_margin_cents": total_cash_cents - dry_powder_cents,
        "cfcp_meter_cents": int(total_profit_cents * 0.10),
        "faep_meter_cents": int(total_profit_cents * 0.03),
        "accounts": accounts
    }

class FreezeRequest(BaseModel):
    scma_id: str

@app.post("/api/v1/admin/toggle-freeze")
def toggle_freeze(req: FreezeRequest):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT status FROM accounts WHERE scma_id = ?;", (req.scma_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Account not found")
    
    current_status = row["status"]
    new_status = "FROZEN" if current_status != "FROZEN" else ("ACTIVE" if row["scma_id"] == "SCMA-FOUNDER" else "PENDING_FUNDING")
    now_iso = datetime.now(timezone.utc).isoformat()

    cursor.execute("UPDATE accounts SET status = ?, updated_at = ? WHERE scma_id = ?;", (new_status, now_iso, req.scma_id))
    append_audit_log(cursor, "CHIEF_ADMINISTRATOR", "TOGGLE_ACCOUNT_STATUS", {"scma_id": req.scma_id, "new_status": new_status})
    conn.commit()
    conn.close()
    return {"status": "SUCCESS", "scma_id": req.scma_id, "new_status": new_status}

class RiskDialRequest(BaseModel):
    scma_id: str
    risk_dial_pct: float

@app.post("/api/v1/member/update-risk-dial")
def update_risk_dial(req: RiskDialRequest):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT max_risk_dial_pct, status FROM accounts WHERE scma_id = ?;", (req.scma_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Account not found")
    
    if row["status"] == "FROZEN":
        conn.close()
        raise HTTPException(status_code=403, detail="Account is frozen. Risk updates barred.")

    max_cap = row["max_risk_dial_pct"]
    if req.risk_dial_pct > max_cap:
        conn.close()
        raise HTTPException(status_code=400, detail=f"Risk cannot exceed ratified ceiling of {max_cap:.2f}%")
    if req.risk_dial_pct < 0.50:
        conn.close()
        raise HTTPException(status_code=400, detail="Minimum defensive risk floor is 0.50%")

    now_iso = datetime.now(timezone.utc).isoformat()
    cursor.execute("UPDATE accounts SET risk_dial_pct = ?, updated_at = ? WHERE scma_id = ?;", (req.risk_dial_pct, now_iso, req.scma_id))
    append_audit_log(cursor, req.scma_id, "UPDATE_RISK_DIAL", {"scma_id": req.scma_id, "risk_dial_pct": req.risk_dial_pct})
    conn.commit()
    conn.close()
    return {"status": "SUCCESS", "scma_id": req.scma_id, "risk_dial_pct": req.risk_dial_pct}

# ----------------------------------------------------------------------
# HTML TEMPLATES (Pure Raw Strings — No Python f-string Collisions)
# ----------------------------------------------------------------------

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>PDEUE Chief Administrator Cockpit</title>
<style>
:root {
  --bg: #090d16; --card: #121826; --border: #1f293d; --text: #f1f5f9;
  --muted: #94a3b8; --gold: #f59e0b; --green: #10b981; --red: #ef4444;
  --accent: #3b82f6; --font: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, monospace;
}
* { box-sizing: border-box; margin: 0; padding: 0; font-family: var(--font); }
body { background: var(--bg); color: var(--text); padding: 24px; }
.header { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border); padding-bottom: 16px; margin-bottom: 24px; }
.title-block h1 { font-size: 1.5rem; color: #fff; letter-spacing: -0.5px; }
.title-block p { font-size: 0.85rem; color: var(--muted); margin-top: 4px; }
.header-actions { display: flex; gap: 12px; align-items: center; }
.btn { padding: 8px 16px; border-radius: 6px; font-weight: 600; font-size: 0.85rem; cursor: pointer; border: 1px solid transparent; transition: all 0.15s; }
.btn-danger { background: #7f1d1d; color: #fecaca; border-color: var(--red); }
.btn-danger:hover { background: var(--red); color: #fff; }
.btn-primary { background: var(--accent); color: #fff; }
.btn-outline { background: transparent; border-color: var(--border); color: var(--text); text-decoration: none; display: inline-flex; align-items: center; }
.btn-outline:hover { background: var(--card); }
.status-pill { padding: 4px 10px; border-radius: 999px; font-size: 0.75rem; font-weight: 700; text-transform: uppercase; }
.status-normal { background: #064e3b; color: #6ee7b7; border: 1px solid var(--green); }
.status-halted { background: #7f1d1d; color: #fca5a5; border: 1px solid var(--red); }
.grid-4 { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; margin-bottom: 24px; }
.card { background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 18px; }
.card-label { font-size: 0.75rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.5px; }
.card-val { font-size: 1.6rem; font-weight: 700; margin: 8px 0; }
.card-sub { font-size: 0.8rem; color: var(--muted); }
.table-card { background: var(--card); border: 1px solid var(--border); border-radius: 8px; overflow: hidden; }
.table-header { padding: 16px 20px; border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center; }
.table-header h2 { font-size: 1.1rem; }
table { width: 100%; border-collapse: collapse; text-align: left; font-size: 0.85rem; }
th { background: #0c121e; color: var(--muted); padding: 12px 20px; font-weight: 600; text-transform: uppercase; font-size: 0.7rem; border-bottom: 1px solid var(--border); }
td { padding: 14px 20px; border-bottom: 1px solid #162032; }
tr:hover td { background: #151e30; }
.badge { display: inline-block; padding: 3px 8px; border-radius: 4px; font-size: 0.75rem; font-weight: 600; }
.badge-active { background: #064e3b; color: #34d399; }
.badge-pending { background: #78350f; color: #fde68a; }
.badge-frozen { background: #7f1d1d; color: #f87171; }
.token-span { font-family: monospace; font-size: 0.75rem; color: #94a3b8; }
</style>
</head>
<body>

<div class="header">
  <div class="title-block">
    <h1>PDEUE Master Cockpit & Registry</h1>
    <p>Chief Administrator Operational Desk • Ring 1 Alpha Pilot (5 Members + Founder)</p>
  </div>
  <div class="header-actions">
    <span id="systemPill" class="status-pill status-normal">NORMAL</span>
    <button id="killBtn" class="btn btn-danger" onclick="toggleKillSwitch()">Master Emergency Halt</button>
    <a href="/member" class="btn btn-outline">Switch Hat: Member View →</a>
  </div>
</div>

<div class="grid-4">
  <div class="card">
    <div class="card-label">Total Ring 1 Equity</div>
    <div class="card-val" id="totalEquity">$100.00</div>
    <div class="card-sub" id="centsSub">10,000 exact integer cents</div>
  </div>
  <div class="card">
    <div class="card-label">40% Dry-Powder Floor</div>
    <div class="card-val" id="dryPowder">$40.00</div>
    <div class="card-sub">Untouchable liquid cash reserve</div>
  </div>
  <div class="card">
    <div class="card-label">Active Working Margin</div>
    <div class="card-val" id="activeMargin" style="color:var(--accent);">$60.00</div>
    <div class="card-sub">Maximum allowable trade collateral</div>
  </div>
  <div class="card">
    <div class="card-label">Central Family Shield (CFCP)</div>
    <div class="card-val" id="cfcpMeter">$0.00</div>
    <div class="card-sub">Accumulates 10% of net profits</div>
  </div>
</div>

<div class="table-card">
  <div class="table-header">
    <h2>Ring 1 Multi-Account Registry (6 SCMAs)</h2>
    <span style="font-size:0.8rem; color:var(--muted);">Enforcing ADR-008 Integer Math & ADR-011 Security Air-Gap</span>
  </div>
  <table>
    <thead>
      <tr>
        <th>SCMA ID</th>
        <th>User ID / Description</th>
        <th>Cash Balance</th>
        <th>Risk Dial</th>
        <th>Lifecycle Status</th>
        <th>Bank Token (Air-Gap)</th>
        <th>Administrative Action</th>
      </tr>
    </thead>
    <tbody id="accountTable">
      <tr><td colspan="7" style="text-align:center; padding:30px;">Loading persistent ledger...</td></tr>
    </tbody>
  </table>
</div>

<script>
async function refreshDashboard() {
  const res = await fetch('/api/v1/admin/ledger-summary');
  const data = await res.json();
  
  document.getElementById('totalEquity').textContent = '$' + (data.total_cash_cents / 100).toLocaleString('en-US', {minimumFractionDigits: 2});
  document.getElementById('centsSub').textContent = data.total_cash_cents.toLocaleString() + ' exact integer cents';
  document.getElementById('dryPowder').textContent = '$' + (data.dry_powder_cents / 100).toLocaleString('en-US', {minimumFractionDigits: 2});
  document.getElementById('activeMargin').textContent = '$' + (data.active_margin_cents / 100).toLocaleString('en-US', {minimumFractionDigits: 2});
  document.getElementById('cfcpMeter').textContent = '$' + (data.cfcp_meter_cents / 100).toLocaleString('en-US', {minimumFractionDigits: 2});

  const pill = document.getElementById('systemPill');
  const killBtn = document.getElementById('killBtn');
  if (data.system_mode === 'HALTED') {
    pill.className = 'status-pill status-halted';
    pill.textContent = 'SYSTEM HALTED';
    killBtn.textContent = 'Resume System (NORMAL)';
    killBtn.className = 'btn btn-primary';
  } else {
    pill.className = 'status-pill status-normal';
    pill.textContent = 'NORMAL';
    killBtn.textContent = 'Master Emergency Halt';
    killBtn.className = 'btn btn-danger';
  }

  const tbody = document.getElementById('accountTable');
  tbody.innerHTML = '';
  data.accounts.forEach(acc => {
    const tr = document.createElement('tr');
    let badgeClass = 'badge-active';
    if (acc.status === 'PENDING_FUNDING') badgeClass = 'badge-pending';
    if (acc.status === 'FROZEN') badgeClass = 'badge-frozen';

    const isFrozen = acc.status === 'FROZEN';
    tr.innerHTML = `
      <td style="font-weight:700; color:#fff;">${acc.scma_id}</td>
      <td>${acc.user_id}</td>
      <td style="font-weight:600; color:#34d399;">$${(acc.cash_cents / 100).toLocaleString('en-US', {minimumFractionDigits: 2})}</td>
      <td>${acc.risk_dial_pct.toFixed(2)}% (Max ${acc.max_risk_dial_pct.toFixed(2)}%)</td>
      <td><span class="badge ${badgeClass}">${acc.status}</span></td>
      <td><span class="token-span">${acc.bank_ref_token}</span></td>
      <td>
        <button class="btn btn-outline" style="padding:4px 10px; font-size:0.75rem;" onclick="toggleFreeze('${acc.scma_id}')">
          ${isFrozen ? 'Unfreeze' : 'Quarantine / Freeze'}
        </button>
      </td>
    `;
    tbody.appendChild(tr);
  });
}

async function toggleKillSwitch() {
  await fetch('/api/v1/admin/kill-switch', {method: 'POST'});
  refreshDashboard();
}

async function toggleFreeze(scmaId) {
  await fetch('/api/v1/admin/toggle-freeze', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({scma_id: scmaId})
  });
  refreshDashboard();
}

refreshDashboard();
setInterval(refreshDashboard, 5000);
</script>
</body>
</html>
"""

MEMBER_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>PDEUE Member Desktop</title>
<style>
:root {
  --bg: #0b0f19; --card: #131b2e; --border: #1e293b; --text: #f8fafc;
  --muted: #94a3b8; --green: #10b981; --accent: #3b82f6; --gold: #f59e0b;
  --font: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
}
* { box-sizing: border-box; margin: 0; padding: 0; font-family: var(--font); }
body { background: var(--bg); color: var(--text); padding: 24px; max-width: 1050px; margin: 0 auto; }
.header { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border); padding-bottom: 16px; margin-bottom: 24px; }
.title-block h1 { font-size: 1.4rem; color: #fff; }
.title-block p { font-size: 0.85rem; color: var(--muted); margin-top: 4px; }
.account-selector { display: flex; align-items: center; gap: 8px; font-size: 0.85rem; }
select { background: var(--card); color: var(--text); border: 1px solid var(--border); padding: 6px 12px; border-radius: 6px; font-size: 0.85rem; outline: none; }
.welcome-card { background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%); border: 1px solid #334155; border-radius: 10px; padding: 24px; margin-bottom: 24px; }
.welcome-card h2 { color: #38bdf8; font-size: 1.25rem; margin-bottom: 8px; }
.welcome-card p { color: #cbd5e1; font-size: 0.92rem; line-height: 1.5; margin-bottom: 12px; }
.highlight-pill { display: inline-flex; align-items: center; gap: 6px; background: rgba(56, 189, 248, 0.1); border: 1px solid rgba(56, 189, 248, 0.3); color: #7dd3fc; padding: 4px 10px; border-radius: 999px; font-size: 0.8rem; font-weight: 600; }
.grid-3 { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 16px; margin-bottom: 24px; }
.card { background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 20px; }
.card-label { font-size: 0.75rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.5px; }
.card-val { font-size: 1.8rem; font-weight: 700; color: #fff; margin: 8px 0; }
.card-sub { font-size: 0.82rem; color: var(--muted); }
.risk-card { background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 24px; margin-bottom: 24px; }
.risk-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.risk-slider-container { margin: 20px 0; }
input[type="range"] { width: 100%; accent-color: var(--accent); cursor: pointer; }
.slider-bounds { display: flex; justify-content: space-between; font-size: 0.75rem; color: var(--muted); }
.status-banner { padding: 12px 16px; border-radius: 6px; margin-bottom: 20px; font-size: 0.85rem; display: none; }
.status-banner-pending { background: rgba(245, 158, 11, 0.15); border: 1px solid var(--gold); color: #fde68a; display: block; }
.btn { padding: 8px 16px; border-radius: 6px; font-weight: 600; font-size: 0.85rem; cursor: pointer; border: 1px solid transparent; }
.btn-outline { background: transparent; border-color: var(--border); color: var(--text); text-decoration: none; }
.btn-outline:hover { background: #1e293b; }
</style>
</head>
<body>

<div class="header">
  <div class="title-block">
    <h1>Member Capital Portal</h1>
    <p>Personal Compounding Sub-Ledger • Self-Contained Member Account (SCMA)</p>
  </div>
  <div class="account-selector">
    <label for="scmaSelect">Select View:</label>
    <select id="scmaSelect" onchange="switchAccount(this.value)">
      <option value="SCMA-FOUNDER">SCMA-FOUNDER (Founder / Active)</option>
      <option value="SCMA-MEM-0001">SCMA-MEM-0001 (Member 1)</option>
      <option value="SCMA-MEM-0002">SCMA-MEM-0002 (Member 2)</option>
      <option value="SCMA-MEM-0003">SCMA-MEM-0003 (Member 3)</option>
      <option value="SCMA-MEM-0004">SCMA-MEM-0004 (Member 4)</option>
      <option value="SCMA-MEM-0005">SCMA-MEM-0005 (Member 5)</option>
    </select>
    <a href="/dashboard" class="btn btn-outline" style="margin-left:12px;">Admin Cockpit →</a>
  </div>
</div>

<div id="pendingBanner" class="status-banner status-banner-pending" style="display:none;">
  <strong>Notice:</strong> This account is currently in <code>PENDING_FUNDING</code> status awaiting its biweekly onboarding deposit. The automated trading engine is safely idle.
</div>

<div class="welcome-card">
  <h2>A Better Financial Starting Point</h2>
  <p>
    Welcome to your private generational compounding sub-ledger. You do not need to analyze charts, pick prediction contracts, or monitor markets.
    PDEUE's algorithmic engine evaluates real-world public data, enforces strict inside-spread bids, and compounds capital automatically.
  </p>
  <div style="display:flex; gap:10px; flex-wrap:wrap;">
    <div class="highlight-pill">✓ 100% Isolated Capital</div>
    <div class="highlight-pill">✓ 87% Reinvestment Compounding</div>
    <div class="highlight-pill">✓ Zero Trading Losses Shared</div>
    <div class="highlight-pill">✓ Bank Air-Gap Protected</div>
  </div>
</div>

<div class="grid-3">
  <div class="card">
    <div class="card-label">Your Unreserved Cash Balance</div>
    <div class="card-val" id="memberCash">$100.00</div>
    <div class="card-sub" id="cashCentsSub">10,000 integer cents</div>
  </div>
  <div class="card">
    <div class="card-label">Lifetime Compounded Yield</div>
    <div class="card-val" style="color:var(--green);" id="lifetimeProfit">$0.00</div>
    <div class="card-sub">Post-waterfall (87% retained)</div>
  </div>
  <div class="card">
    <div class="card-label">Opaque Bank Reference Token</div>
    <div class="card-val" style="font-size:1.05rem; font-family:monospace; margin-top:14px;" id="bankToken">Loading...</div>
    <div class="card-sub">ADR-011 Zero-Credential Air-Gap</div>
  </div>
</div>

<div class="risk-card">
  <div class="risk-header">
    <div>
      <h3 style="font-size:1.1rem; color:#fff;">Downward-Only Personal Risk Governor</h3>
      <p style="font-size:0.82rem; color:var(--muted); margin-top:2px;">
        You hold sovereign discretion to reduce your risk allocation down to 0.50%. Increasing risk beyond your ratified cap (2.00%) is permanently barred.
      </p>
    </div>
    <div style="font-size:1.5rem; font-weight:700; color:var(--gold);" id="dialValText">2.00%</div>
  </div>
  
  <div class="risk-slider-container">
    <input type="range" id="riskSlider" min="0.50" max="2.00" step="0.05" value="2.00" oninput="updateDialPreview(this.value)" onchange="commitRiskDial(this.value)">
    <div class="slider-bounds">
      <span>0.50% (Max Defensive Floor)</span>
      <span>1.25% (Balanced)</span>
      <span id="maxCapLabel">2.00% (Ceiling)</span>
    </div>
  </div>
  <p id="riskMsg" style="font-size:0.8rem; color:#38bdf8;"></p>
</div>

<script>
let currentScma = "__ACTIVE_SCMA_TARGET__";
document.getElementById('scmaSelect').value = currentScma;

function switchAccount(val) {
  window.location.href = '/member?scma=' + val;
}

function updateDialPreview(val) {
  document.getElementById('dialValText').textContent = parseFloat(val).toFixed(2) + '%';
}

async function loadAccountData() {
  const res = await fetch('/api/v1/admin/ledger-summary');
  const data = await res.json();
  const acc = data.accounts.find(a => a.scma_id === currentScma);
  if (!acc) return;

  document.getElementById('memberCash').textContent = '$' + (acc.cash_cents / 100).toLocaleString('en-US', {minimumFractionDigits: 2});
  document.getElementById('cashCentsSub').textContent = acc.cash_cents.toLocaleString() + ' exact integer cents';
  document.getElementById('lifetimeProfit').textContent = '$' + (acc.lifetime_profit_cents / 100).toLocaleString('en-US', {minimumFractionDigits: 2});
  document.getElementById('bankToken').textContent = acc.bank_ref_token;

  const slider = document.getElementById('riskSlider');
  slider.max = acc.max_risk_dial_pct;
  slider.value = acc.risk_dial_pct;
  document.getElementById('maxCapLabel').textContent = acc.max_risk_dial_pct.toFixed(2) + '% (Ceiling)';
  document.getElementById('dialValText').textContent = acc.risk_dial_pct.toFixed(2) + '%';

  const pendingBanner = document.getElementById('pendingBanner');
  if (acc.status === 'PENDING_FUNDING') {
    pendingBanner.style.display = 'block';
  } else {
    pendingBanner.style.display = 'none';
  }

  if (acc.status === 'FROZEN') {
    slider.disabled = true;
    document.getElementById('riskMsg').textContent = 'Account is currently quarantined/frozen by Administrator.';
    document.getElementById('riskMsg').style.color = '#ef4444';
  } else {
    slider.disabled = false;
    document.getElementById('riskMsg').textContent = 'Dial adjustments save automatically and log to the cryptographic audit chain.';
    document.getElementById('riskMsg').style.color = '#38bdf8';
  }
}

async function commitRiskDial(val) {
  try {
    const res = await fetch('/api/v1/member/update-risk-dial', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({scma_id: currentScma, risk_dial_pct: parseFloat(val)})
    });
    const result = await res.json();
    if (res.ok) {
      document.getElementById('riskMsg').textContent = 'Risk governor updated to ' + result.risk_dial_pct.toFixed(2) + '% at ' + new Date().toLocaleTimeString();
    } else {
      document.getElementById('riskMsg').textContent = 'Error: ' + result.detail;
      document.getElementById('riskMsg').style.color = '#ef4444';
      loadAccountData();
    }
  } catch (err) {
    console.error(err);
  }
}

loadAccountData();
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
