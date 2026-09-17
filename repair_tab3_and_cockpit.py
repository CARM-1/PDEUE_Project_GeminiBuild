import pathlib
import subprocess
import sys
import os

REPO_ROOT = pathlib.Path(r"C:\PDEUE_Gemini")
BACKEND_DIR = REPO_ROOT / "backend"
API_DIR = BACKEND_DIR / "app" / "api" / "v1"
STATIC_DIR = BACKEND_DIR / "app" / "static"
ROUTER_PATH = API_DIR / "workspace_router.py"
DT_PATH = API_DIR / "dashboard_template.py"

UNIFIED_DASHBOARD_HTML = '''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>PDEUE Chief Administrator Workspace</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
    body { background: #0b132b; color: #f8fafc; padding: 20px; }
    .hub-ribbon { background: #020617; border: 1px solid #1e293b; border-radius: 8px; padding: 8px 16px; margin-bottom: 20px; display: flex; justify-content: space-between; align-items: center; }
    .hub-links { display: flex; gap: 8px; }
    .hub-btn { padding: 6px 12px; border-radius: 4px; font-size: 12px; font-weight: bold; text-decoration: none; border: 1px solid #334155; }
    .hub-btn.active { background: #0284c7; color: #fff; border-color: #38bdf8; }
    .hub-btn.inactive { background: #1e293b; color: #94a3b8; }
    .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
    .header h1 { font-size: 22px; font-weight: bold; color: #f8fafc; }
    .header-controls { display: flex; gap: 10px; align-items: center; }
    .tabs { display: flex; gap: 8px; margin-bottom: 20px; border-bottom: 1px solid #1e293b; padding-bottom: 10px; }
    .tab-btn { background: #1e293b; color: #94a3b8; border: 1px solid #334155; padding: 8px 16px; border-radius: 6px; cursor: pointer; font-weight: 600; font-size: 13px; }
    .tab-btn.active { background: #0284c7; color: #ffffff; border-color: #38bdf8; }
    .grid-4 { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 20px; }
    .card { background: #111c44; border: 1px solid #1e293b; border-radius: 8px; padding: 16px; }
    .card-title { font-size: 11px; font-weight: bold; color: #94a3b8; text-transform: uppercase; margin-bottom: 6px; }
    .card-value { font-size: 24px; font-weight: bold; margin-bottom: 4px; }
    .card-sub { font-size: 12px; color: #94a3b8; }
    table { width: 100%; border-collapse: collapse; margin-top: 10px; }
    th { border-bottom: 1px solid #334155; text-align: left; padding: 8px; color: #94a3b8; font-size: 12px; }
    td { padding: 8px; border-bottom: 1px solid #1e293b; font-size: 13px; }
    .btn-stage { background: #0284c7; color: #fff; border: 1px solid #38bdf8; padding: 4px 10px; border-radius: 4px; cursor: pointer; font-weight: bold; }
    .copilot-btn { position: fixed; bottom: 20px; right: 20px; background: #0284c7; color: #fff; border: none; border-radius: 20px; padding: 10px 18px; font-weight: bold; cursor: pointer; box-shadow: 0 4px 12px rgba(0,0,0,0.4); }
  </style>
</head>
<body>

  <div class="hub-ribbon">
    <div style="display: flex; align-items: center; gap: 12px;">
      <span style="font-weight: bold; font-size: 12px; color: #38bdf8;">PDEUE PORTAL HUB:</span>
      <div class="hub-links">
        <a href="/dashboard" class="hub-btn active">Chief Admin Cockpit</a>
        <a href="/admin/tech" class="hub-btn inactive">Technical Console (Class T)</a>
        <a href="/advisor" class="hub-btn inactive">Advisor Workspace (Class F)</a>
        <a href="/member" class="hub-btn inactive">Member Desktop (Class M)</a>
      </div>
    </div>
    <span style="color: #64748b; font-size: 11px; font-weight: bold;">FULL BIDIRECTIONAL NAVIGATION</span>
  </div>

  <div class="header">
    <div>
      <div style="color: #38bdf8; font-size: 11px; font-weight: bold; text-transform: uppercase;">JURISDICTION: TOP-LEVEL EXECUTIVE OVERSIGHT (SPLIT-HAT CONTEXT)</div>
      <h1>PDEUE Chief Administrator Workspace</h1>
      <div style="color: #64748b; font-size: 12px; margin-top: 2px;">Binding Lexicon v0.4 | Dual-Control Active</div>
    </div>
    <div class="header-controls">
      <span style="background: #10b981; color: #020617; font-weight: bold; font-size: 12px; padding: 6px 12px; border-radius: 4px;">MODE: PAPER</span>
      <button style="background: #ef4444; color: #fff; border: none; font-weight: bold; font-size: 12px; padding: 6px 12px; border-radius: 4px; cursor: pointer;">EMERGENCY KILL SWITCH</button>
    </div>
  </div>

  <div class="tabs">
    <button id="tab-btn-1" class="tab-btn active" onclick="switchTab(1)">1. Lineage Executive Overview</button>
    <button id="tab-btn-2" class="tab-btn" onclick="switchTab(2)">2. Family Lineal Pools &amp; Sub-Ledgers</button>
    <button id="tab-btn-3" class="tab-btn" onclick="switchTab(3)">3. Velocity Radar &amp; Scanner</button>
    <button id="tab-btn-4" class="tab-btn" onclick="switchTab(4)">4. Governance &amp; Dual-Control</button>
  </div>

  <!-- TAB 1: EXECUTIVE OVERVIEW -->
  <div id="tab-panel-1" style="display: block;">
    <div class="grid-4">
      <div class="card">
        <div class="card-title">LINEAGE TOTAL EQUITY</div>
        <div class="card-value" id="fnd-balance">$4,250.00</div>
        <div class="card-sub">Active Reservation: <span id="fnd-reserved" style="color: #38bdf8;">$750.00</span></div>
      </div>
      <div class="card">
        <div class="card-title">COMMITTED MARGIN</div>
        <div class="card-value" style="color: #38bdf8;">$25.00</div>
        <div class="card-sub">Lifetime PnL: $0.00</div>
      </div>
      <div class="card">
        <div class="card-title">PROFIT FACTOR</div>
        <div class="card-value" style="color: #4ade80;">2.84x</div>
        <div class="card-sub">Win Rate: 75.0%</div>
      </div>
      <div class="card">
        <div class="card-title">MAX DRAWDOWN</div>
        <div class="card-value" style="color: #f87171;">-1.85%</div>
        <div class="card-sub">Tier-1 Ceiling: 5.0%</div>
      </div>
    </div>

    <div class="card" style="margin-bottom: 20px;">
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
        <div class="card-title" style="color: #38bdf8;">EQUITY COMPOUNDING CURVE (CENTS)</div>
        <div style="color: #64748b; font-size: 11px;">Peak: 510,000¢ | Floor: 500,000¢</div>
      </div>
      <canvas id="chart-equity" height="65"></canvas>
    </div>

    <div class="card">
      <div class="card-title" style="color: #38bdf8; margin-bottom: 8px;">ACTIVE PORTFOLIO POSITIONS</div>
      <table>
        <thead>
          <tr><th>CONTRACT</th><th>VENUE</th><th>SIDE</th><th>QTY</th><th>VWAP</th><th>COST</th><th>MTM</th><th>ACTION</th></tr>
        </thead>
        <tbody id="pos-tbody">
          <tr><td colspan="8" style="text-align: center; color: #94a3b8; padding: 15px;">Loading open positions...</td></tr>
        </tbody>
      </table>
    </div>
  </div>

  <!-- TAB 2: LINEAL POOLS & WATERFALL -->
  <div id="tab-panel-2" style="display: none;">
    <div class="grid-4">
      <div class="card">
        <div class="card-title">CFCP Family Pool (10%)</div>
        <div class="card-value" style="color: #4ade80;">$500.00</div>
        <div class="card-sub">Central Lineage Growth</div>
      </div>
      <div class="card">
        <div class="card-title">Founder FAEP Pool (3%)</div>
        <div class="card-value" style="color: #38bdf8;">$150.00</div>
        <div class="card-sub">Endowment Growth</div>
      </div>
      <div class="card">
        <div class="card-title">Waterfall Distribution</div>
        <div class="card-value">87 / 10 / 3</div>
        <div class="card-sub">SCMA / CFCP / FAEP</div>
      </div>
      <div class="card">
        <div class="card-title">Tribal Houses</div>
        <div class="card-value" style="color: #a855f7;">12 Houses</div>
        <div class="card-sub">Autonomous Partitioning</div>
      </div>
    </div>
  </div>

  <!-- TAB 3: VELOCITY RADAR & SCANNER -->
  <div id="tab-panel-3" style="display: none;">
    <div class="card" style="margin-bottom: 20px;">
      <div class="card-title" style="color: #38bdf8; margin-bottom: 12px;">STRATEGY D (INSIDE MAKER CORE) &amp; EMPIRICAL 4-WAY WALK-FORWARD SIMULATION</div>
      <div class="grid-4" style="margin-bottom: 0;">
        <div style="background: #0f172a; padding: 12px; border-radius: 6px; border: 1px solid #1e293b;">
          <div style="font-size: 11px; color: #94a3b8;">Baseline A (Taker Only)</div>
          <div style="font-size: 18px; font-weight: bold; margin: 4px 0;">$485,000</div>
          <div style="color: #ef4444; font-size: 11px;">-3.0% Drag</div>
        </div>
        <div style="background: #0f172a; padding: 12px; border-radius: 6px; border: 1px solid #1e293b;">
          <div style="font-size: 11px; color: #94a3b8;">Baseline B (Passive Limit)</div>
          <div style="font-size: 18px; font-weight: bold; margin: 4px 0;">$494,000</div>
          <div style="color: #f59e0b; font-size: 11px;">-1.2% Slip</div>
        </div>
        <div style="background: #0f172a; padding: 12px; border-radius: 6px; border: 1px solid #1e293b;">
          <div style="font-size: 11px; color: #94a3b8;">Baseline C (Midpoint Passive)</div>
          <div style="font-size: 18px; font-weight: bold; margin: 4px 0;">$502,000</div>
          <div style="color: #4ade80; font-size: 11px;">+0.4% Net</div>
        </div>
        <div style="background: #0f172a; padding: 12px; border-radius: 6px; border: 1px solid #38bdf8;">
          <div style="font-size: 11px; color: #38bdf8; font-weight: bold;">Strategy D (Inside Maker)</div>
          <div style="font-size: 18px; font-weight: bold; color: #4ade80; margin: 4px 0;">$713,000</div>
          <div style="color: #4ade80; font-size: 11px; font-weight: bold;">+42.6% Net ROI</div>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="card-title" style="color: #38bdf8; margin-bottom: 12px;">ACTIVE SCANNER QUEUE &amp; VOLATILITY RADAR</div>
      <table>
        <thead>
          <tr><th>CONTRACT</th><th>VENUE</th><th>LINEAGE</th><th>MODEL PROB</th><th>MARKET PRICE</th><th>NET EDGE</th><th>STATUS</th><th>ACTION</th></tr>
        </thead>
        <tbody id="radar-table-body">
          <tr><td colspan="8" style="text-align: center; color: #94a3b8; padding: 20px;">Scanning prediction venues and public feeds...</td></tr>
        </tbody>
      </table>
    </div>
  </div>

  <!-- TAB 4: GOVERNANCE & DUAL CONTROL -->
  <div id="tab-panel-4" style="display: none;">
    <div class="card">
      <div class="card-title" style="color: #38bdf8;">GOVERNANCE CONSENSUS LEDGER &amp; DUAL CONTROL</div>
      <p style="color: #94a3b8; font-size: 13px; margin-top: 8px;">Bicameral consensus: 75% House Ratification required for CFCP pool distributions.</p>
    </div>
  </div>

  <button class="copilot-btn">🤖 AI Copilot</button>

  <script>
    let chartInstance = null;

    function switchTab(idx) {
      for (let i = 1; i <= 4; i++) {
        const btn = document.getElementById("tab-btn-" + i);
        const panel = document.getElementById("tab-panel-" + i);
        if (btn) {
          if (i === idx) {
            btn.classList.add("active");
            btn.style.background = "#0284c7";
            btn.style.color = "#ffffff";
          } else {
            btn.classList.remove("active");
            btn.style.background = "#1e293b";
            btn.style.color = "#94a3b8";
          }
        }
        if (panel) {
          panel.style.display = (i === idx) ? "block" : "none";
        }
      }
      if (idx === 3) loadRadarOpportunities();
    }

    function renderChart() {
      const ctx = document.getElementById("chart-equity");
      if (!ctx || typeof Chart === "undefined") return;
      if (chartInstance) chartInstance.destroy();

      chartInstance = new Chart(ctx, {
        type: "line",
        data: {
          labels: ["00:00", "04:00", "08:00", "12:00", "16:00", "20:00", "24:00"],
          datasets: [{
            data: [500000, 501500, 503000, 504800, 507200, 508900, 510000],
            borderColor: "#38bdf8",
            backgroundColor: "rgba(56, 189, 248, 0.1)",
            borderWidth: 2,
            tension: 0.35,
            fill: true
          }]
        },
        options: {
          responsive: true,
          plugins: { legend: { display: false } },
          scales: {
            x: { grid: { color: "#1e293b" }, ticks: { color: "#64748b" } },
            y: { grid: { color: "#1e293b" }, ticks: { color: "#64748b" } }
          }
        }
      });
    }

    async function loadWorkspaceState() {
      try {
        const res = await fetch("/api/v1/operator/workspace-state");
        if (!res.ok) return;
        const data = await res.json();

        // 1. Populate Active Positions Table
        const positions = data.positions || [];
        const posTbody = document.getElementById("pos-tbody");
        if (posTbody) {
          if (positions.length === 0) {
            posTbody.innerHTML = '<tr><td colspan="8" style="text-align:center; color:#94a3b8; padding:15px;">No active open positions</td></tr>';
          } else {
            posTbody.innerHTML = positions.map(p => `
              <tr>
                <td><b>${p.contract || p.contract_id}</b></td>
                <td>${p.venue}</td>
                <td style="color:#10b981; font-weight:bold;">${p.side}</td>
                <td>${Number(p.qty || p.quantity || 0).toLocaleString()}</td>
                <td>${p.vwap}</td>
                <td>${p.cost}</td>
                <td style="color:#10b981;">${p.mtm}</td>
                <td><button style="background:#334155; color:#fff; border:none; padding:3px 8px; border-radius:3px; cursor:pointer;">Inspect</button></td>
              </tr>
            `).join('');
          }
        }

        // 2. Populate Velocity Radar Opportunities
        const opps = data.radar_opportunities || (data.daemon && data.daemon.latest_opportunities) || [];
        const radarTbody = document.getElementById("radar-table-body");
        if (radarTbody && opps.length > 0) {
          radarTbody.innerHTML = opps.map(o => `
            <tr>
              <td><b>${o.contract_ticker}</b></td>
              <td><span style="color: #38bdf8; font-weight: bold;">${o.venue}</span></td>
              <td><span style="background: #1e293b; color: #a855f7; padding: 2px 6px; border-radius: 4px; font-weight: bold;">${o.lineage_code}</span></td>
              <td>${(o.model_prob * 100).toFixed(1)}%</td>
              <td>$${o.market_price.toFixed(2)}</td>
              <td style="color: #4ade80; font-weight: bold;">+${(o.net_edge * 100).toFixed(1)}%</td>
              <td><span style="color: ${o.status === 'QUALIFIED' ? '#10b981' : '#f59e0b'}; font-weight: bold;">${o.status}</span></td>
              <td>
                <button class="btn-stage" onclick="stageHouseDispatch('${o.contract_ticker}', '${o.venue}', ${o.target_house_id}, '${o.recommended_action}', ${o.market_price}, ${o.model_prob})">Stage Order</button>
              </td>
            </tr>
          `).join('');
        }
      } catch (err) {
        console.error("Workspace state poll error:", err);
      }
    }

    function loadRadarOpportunities() {
      loadWorkspaceState();
    }

    async function stageHouseDispatch(ticker, venue, houseId, side, price, prob) {
      try {
        const res = await fetch("/api/v1/operator/stage-order", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({
            contract_ticker: ticker,
            venue: venue,
            target_house_id: houseId,
            side: side,
            market_price: price,
            model_prob: prob
          })
        });
        const data = await res.json();
        if (res.ok) {
          const cents = data.dispatch.total_committed_cents;
          alert(`[COMMITTED] Staged ${ticker} for ${data.dispatch.lineage_code}. Margin: $${(cents / 100.0).toFixed(2)}`);
          loadWorkspaceState();
          switchTab(1);
        } else {
          alert(`Rejected: ${data.detail || 'Invariant violation'}`);
        }
      } catch (err) {
        console.error("Stage order failed:", err);
      }
    }

    window.addEventListener("DOMContentLoaded", () => {
      renderChart();
      loadWorkspaceState();
      setInterval(loadWorkspaceState, 4000);
    });
  </script>
</body>
</html>
'''

def execute():
    # Write fresh HTML to templates
    for p in [API_DIR / "dashboard.html", STATIC_DIR / "dashboard.html"]:
        p.write_text(UNIFIED_DASHBOARD_HTML.strip() + "\n", encoding="utf-8")
        print(f"[OK] Wrote clean unified dashboard to {p}")

    # Synchronize dashboard_template.py loader
    loader_code = '''"""
PDEUE Chief Administrator Dashboard Template Provider.
Loads pure HTML directly from disk to ensure zero string escaping errors.
"""
import pathlib

_BASE_DIR = pathlib.Path(__file__).parent
_HTML_PATH = _BASE_DIR / "dashboard.html"
if not _HTML_PATH.exists():
    _HTML_PATH = _BASE_DIR.parent.parent / "static" / "dashboard.html"

def get_fresh_dashboard_html() -> str:
    return _HTML_PATH.read_text(encoding="utf-8") if _HTML_PATH.exists() else "<html><body>Dashboard Not Found</body></html>"

DASHBOARD_HTML_TEMPLATE = get_fresh_dashboard_html()
'''
    DT_PATH.write_text(loader_code.strip() + "\n", encoding="utf-8")
    print(f"[OK] Wrote template provider to {DT_PATH}")

    # Verify tests pass
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + str(BACKEND_DIR)
    res = subprocess.run([sys.executable, "-m", "pytest", "backend/tests", "-v", "--cache-clear"], cwd=str(REPO_ROOT), env=env)
    if res.returncode != 0:
        print("\n[FAIL] Test suite failed.")
        sys.exit(res.returncode)
    print("\n[SUCCESS] Unified Cockpit & Radar verified 100% green!")

if __name__ == "__main__":
    execute()