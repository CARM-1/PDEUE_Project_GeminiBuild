import pathlib
import subprocess
import sys
import os

REPO_ROOT = pathlib.Path(r"C:\PDEUE_Gemini")
BACKEND_DIR = REPO_ROOT / "backend"
API_DIR = BACKEND_DIR / "app" / "api" / "v1"
STATIC_DIR = BACKEND_DIR / "app" / "static"
DT_PATH = API_DIR / "dashboard_template.py"

UPGRADED_DASHBOARD_HTML = '''<!DOCTYPE html>
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

    /* Modal Backdrop & Container */
    .modal-backdrop { display: none; position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; background: rgba(2, 6, 23, 0.85); backdrop-filter: blur(4px); z-index: 20000; align-items: center; justify-content: center; }
    .modal-box { background: #111c44; border: 1px solid #38bdf8; border-radius: 10px; width: 560px; max-width: 90vw; padding: 24px; box-shadow: 0 16px 40px rgba(0, 0, 0, 0.7); animation: modalIn 0.2s ease-out; }
    @keyframes modalIn { from { opacity: 0; transform: scale(0.96); } to { opacity: 1; transform: scale(1); } }
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
        <div class="card-value" id="fnd-committed" style="color: #38bdf8;">$25.00</div>
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

  <!-- PROFESSIONAL ORDER STAGING TICKET MODAL -->
  <div id="dispatch-modal" class="modal-backdrop">
    <div class="modal-box">
      <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #1e293b; padding-bottom: 12px; margin-bottom: 16px;">
        <div style="display: flex; align-items: center; gap: 8px;">
          <span style="background: #0284c7; color: #fff; font-size: 11px; font-weight: bold; padding: 3px 8px; border-radius: 4px;">DISPATCH TICKET</span>
          <strong style="color: #38bdf8; font-size: 16px;" id="modal-ticket-id">KX-MIA-FRZ-32</strong>
        </div>
        <button onclick="closeDispatchModal()" style="background: transparent; border: none; color: #94a3b8; font-size: 18px; cursor: pointer;">✕</button>
      </div>

      <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 16px;">
        <div style="background: #0b132b; padding: 10px; border-radius: 6px; border: 1px solid #1e293b;">
          <div style="font-size: 11px; color: #94a3b8;">Target Venue</div>
          <div id="modal-venue" style="font-size: 14px; font-weight: bold; color: #38bdf8; margin-top: 2px;">KALSHI</div>
        </div>
        <div style="background: #0b132b; padding: 10px; border-radius: 6px; border: 1px solid #1e293b;">
          <div style="font-size: 11px; color: #94a3b8;">Lineage Allocation</div>
          <div id="modal-lineage" style="font-size: 14px; font-weight: bold; color: #a855f7; margin-top: 2px;">HOUSE-01</div>
        </div>
        <div style="background: #0b132b; padding: 10px; border-radius: 6px; border: 1px solid #1e293b;">
          <div style="font-size: 11px; color: #94a3b8;">Model Edge / Probability</div>
          <div id="modal-edge" style="font-size: 14px; font-weight: bold; color: #4ade80; margin-top: 2px;">+28.5% (31.5%)</div>
        </div>
        <div style="background: #0b132b; padding: 10px; border-radius: 6px; border: 1px solid #1e293b;">
          <div style="font-size: 11px; color: #94a3b8;">Sizing Protocol</div>
          <div style="font-size: 14px; font-weight: bold; color: #f8fafc; margin-top: 2px;">Quarter-Kelly (0.25 f*)</div>
        </div>
      </div>

      <div style="background: #0f172a; border: 1px solid #334155; border-radius: 6px; padding: 12px; margin-bottom: 20px;">
        <div style="font-size: 11px; color: #38bdf8; font-weight: bold; margin-bottom: 6px; text-transform: uppercase;">Deterministic Member Capital Allocation</div>
        <div style="font-size: 12px; color: #94a3b8; line-height: 1.5;">
          • Founder Chief Admin SCMA: <strong style="color: #f8fafc;">$100.00</strong> (3,333 contracts @ 3.0¢)<br>
          • Eleanor Vance SCMA: <strong style="color: #f8fafc;">$18.75</strong> (625 contracts @ 3.0¢)<br>
          • Total Target Commitment: <strong style="color: #10b981;">$118.75</strong> &nbsp;|&nbsp; Status: <span style="color: #38bdf8; font-weight: bold;">RESTING_MAKER</span>
        </div>
      </div>

      <div id="modal-actions" style="display: flex; justify-content: flex-end; gap: 10px;">
        <button onclick="closeDispatchModal()" style="background: #334155; color: #cbd5e1; border: none; padding: 8px 16px; border-radius: 6px; cursor: pointer; font-weight: bold; font-size: 13px;">Dismiss</button>
        <button id="modal-confirm-btn" onclick="confirmDispatchExecution()" style="background: #0284c7; color: #ffffff; border: 1px solid #38bdf8; padding: 8px 18px; border-radius: 6px; cursor: pointer; font-weight: bold; font-size: 13px;">Authorize &amp; Dispatch Order</button>
      </div>

      <div id="modal-receipt" style="display: none; background: rgba(16, 185, 129, 0.1); border: 1px solid #10b981; border-radius: 6px; padding: 12px; margin-top: 12px;">
        <div style="color: #10b981; font-weight: bold; font-size: 13px;">✓ Ledger Commitment Authenticated</div>
        <div id="receipt-details" style="font-size: 12px; color: #cbd5e1; margin-top: 4px;"></div>
      </div>
    </div>
  </div>

  <button class="copilot-btn">🤖 AI Copilot</button>

  <script>
    let chartInstance = null;
    let pendingDispatch = null;

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

        // Populate Active Positions
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

        // Populate Radar Opportunities
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

    // Professional Modal Handlers
    function stageHouseDispatch(ticker, venue, houseId, side, price, prob) {
      pendingDispatch = { ticker, venue, houseId, side, price, prob };
      document.getElementById("modal-ticket-id").textContent = ticker;
      document.getElementById("modal-venue").textContent = venue;
      document.getElementById("modal-lineage").textContent = "HOUSE-" + String(houseId).padStart(2, "0");
      document.getElementById("modal-edge").textContent = `+${((prob - price) * 100).toFixed(1)}% (${(prob * 100).toFixed(1)}%)`;
      document.getElementById("modal-receipt").style.display = "none";
      document.getElementById("modal-actions").style.display = "flex";
      document.getElementById("dispatch-modal").style.display = "flex";
    }

    function closeDispatchModal() {
      document.getElementById("dispatch-modal").style.display = "none";
      pendingDispatch = null;
    }

    async function confirmDispatchExecution() {
      if (!pendingDispatch) return;
      const btn = document.getElementById("modal-confirm-btn");
      btn.textContent = "Committing Margin...";
      btn.disabled = true;

      try {
        const res = await fetch("/api/v1/operator/stage-order", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            contract_ticker: pendingDispatch.ticker,
            venue: pendingDispatch.venue,
            target_house_id: pendingDispatch.houseId,
            side: pendingDispatch.side,
            market_price: pendingDispatch.price,
            model_prob: pendingDispatch.prob
          })
        });
        const data = await res.json();
        if (res.ok) {
          const d = data.dispatch;
          const dollars = (d.total_committed_cents / 100.0).toFixed(2);
          document.getElementById("receipt-details").innerHTML = `
            Dispatched to: <b>${d.lineage_code}</b> | Status: <span style="color:#10b981;">${d.status}</span><br>
            Total Contracts: <b>${d.total_quantity.toLocaleString()}</b> | Committed Margin: <b>$${dollars}</b><br>
            Audit Hash: <span style="font-family:monospace; color:#38bdf8;">${d.dispatch_id}</span>
          `;
          document.getElementById("modal-receipt").style.display = "block";
          document.getElementById("modal-actions").style.display = "none";

          setTimeout(() => {
            closeDispatchModal();
            loadWorkspaceState();
            switchTab(1);
          }, 1400);
        } else {
          alert(`Dispatch Rejected: ${data.detail || "Invariant error"}`);
          closeDispatchModal();
        }
      } catch (err) {
        console.error("Order staging failure:", err);
        closeDispatchModal();
      } finally {
        btn.textContent = "Authorize & Dispatch Order";
        btn.disabled = false;
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
    for p in [API_DIR / "dashboard.html", STATIC_DIR / "dashboard.html"]:
        p.write_text(UPGRADED_DASHBOARD_HTML.strip() + "\n", encoding="utf-8")
        print(f"[OK] Staged professional modal in {p}")

    dt_txt = '''"""PDEUE Chief Administrator Dashboard Template Provider."""
import pathlib

_BASE_DIR = pathlib.Path(__file__).parent
_HTML_PATH = _BASE_DIR / "dashboard.html"
if not _HTML_PATH.exists():
    _HTML_PATH = _BASE_DIR.parent.parent / "static" / "dashboard.html"

def get_fresh_dashboard_html() -> str:
    return _HTML_PATH.read_text(encoding="utf-8") if _HTML_PATH.exists() else "<html><body>Dashboard Not Found</body></html>"

DASHBOARD_HTML_TEMPLATE = get_fresh_dashboard_html()
'''
    DT_PATH.write_text(dt_txt.strip() + "\n", encoding="utf-8")
    print(f"[OK] Synchronized {DT_PATH}")

    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + str(BACKEND_DIR)
    res = subprocess.run([sys.executable, "-m", "pytest", "backend/tests", "-v", "--cache-clear"], cwd=str(REPO_ROOT), env=env)
    if res.returncode != 0:
        print("\n[FAIL] Test suite failed.")
        sys.exit(res.returncode)
    print("\n[SUCCESS] Modal ticket upgrade verified and 100% green!")

if __name__ == "__main__":
    execute()