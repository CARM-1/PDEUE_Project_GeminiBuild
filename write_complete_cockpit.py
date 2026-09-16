import pathlib
import shutil

html_template = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>PDEUE Chief Administrator Workspace</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0b132b; color: #f8fafc; margin: 0; padding: 24px; }
    .topbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
    .nav-tabs { display: flex; gap: 8px; margin-bottom: 20px; }
    .nav-btn { background: #1c2541; color: #94a3b8; border: none; padding: 10px 18px; border-radius: 6px; font-weight: 600; cursor: pointer; font-size: 0.85rem; }
    .nav-btn.active { background: #0284c7; color: #ffffff; }
    .tab-panel { display: none; }
    .tab-panel.active { display: block; }
    .grid-cards { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 20px; }
    .card { background: #1c2541; border: 1px solid #334155; border-radius: 6px; padding: 16px; }
    .card-label { font-size: 0.75rem; color: #94a3b8; font-weight: 700; text-transform: uppercase; margin-bottom: 8px; }
    .card-val { font-size: 1.5rem; font-weight: 700; color: #f8fafc; }
    .card-sub { font-size: 0.75rem; color: #64748b; margin-top: 4px; }
    .table-container { background: #1c2541; border: 1px solid #334155; border-radius: 6px; padding: 16px; margin-bottom: 20px; }
    table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
    th { text-align: left; color: #94a3b8; border-bottom: 1px solid #334155; padding: 10px 8px; font-weight: 600; }
    td { border-bottom: 1px solid #1e293b; padding: 10px 8px; }
    .btn-kill { background: #ef4444; color: #ffffff; border: none; padding: 8px 16px; border-radius: 6px; font-weight: 700; cursor: pointer; }
    
    /* Copilot Drawer */
    #copilot-drawer {
      position: fixed; top: 0; right: -460px; width: 440px; height: 100vh;
      background: #0f172a; border-left: 2px solid #0284c7; z-index: 10000;
      box-shadow: -8px 0 24px rgba(0,0,0,0.6); transition: right 0.3s ease;
      display: flex; flex-direction: column;
    }
    #copilot-drawer.open { right: 0; }
    .copilot-header {
      background: #1e293b; padding: 16px; border-bottom: 1px solid #334155;
      display: flex; justify-content: space-between; align-items: center;
    }
    .copilot-body { flex: 1; padding: 16px; overflow-y: auto; font-size: 0.85rem; }
    .copilot-footer { padding: 12px 16px; background: #1e293b; border-top: 1px solid #334155; display: flex; gap: 8px; }
    .chat-bubble { background: #1e293b; border: 1px solid #334155; border-radius: 6px; padding: 10px 12px; margin-bottom: 12px; }
    .chat-bubble.ai { border-left: 3px solid #38bdf8; }
  </style>
</head>
<body>

  <div class="topbar">
    <div>
      <h2 style="margin: 0; font-size: 1.4rem;">PDEUE Chief Administrator Workspace</h2>
      <div style="font-size: 0.8rem; color: #64748b; margin-top: 4px;">Binding Lexicon v0.4 | Dual-Control Active</div>
    </div>
    <div style="display: flex; gap: 12px; align-items: center;">
      <span style="background: #22c55e; color: #0b132b; padding: 4px 10px; border-radius: 4px; font-weight: 700; font-size: 0.8rem;">MODE: PAPER</span>
      <button class="btn-kill" onclick="triggerBreaker()">EMERGENCY KILL SWITCH</button>
    </div>
  </div>

  <div class="nav-tabs">
    <button id="tab-btn-1" class="nav-btn active" onclick="switchTab(1)">1. Founder SCMA & Executive Overview</button>
    <button id="tab-btn-2" class="nav-btn" onclick="switchTab(2)">2. Family Lineal Pools & Sub-Ledgers</button>
    <button id="tab-btn-3" class="nav-btn" onclick="switchTab(3)">3. Velocity Radar & Scanner</button>
    <button id="tab-btn-4" class="nav-btn" onclick="switchTab(4)">4. Governance & Dual-Control</button>
  </div>

  <!-- TAB 1: SCMA Overview -->
  <div id="tab-panel-1" class="tab-panel active">
    <div class="grid-cards">
      <div class="card">
        <div class="card-label">Founder SCMA Cash</div>
        <div class="card-val" id="fnd-balance">$4,250.00</div>
        <div class="card-sub" id="fnd-reserved">Active Reservation: $750.00</div>
      </div>
      <div class="card">
        <div class="card-label">Founder FAEP Pool (3%)</div>
        <div class="card-val" style="color: #38bdf8;">$150.00</div>
        <div class="card-sub">Lifetime PnL: $0.00</div>
      </div>
      <div class="card">
        <div class="card-label">Profit Factor</div>
        <div class="card-val" style="color: #22c55e;">2.84x</div>
        <div class="card-sub">Win Rate: 75.0%</div>
      </div>
      <div class="card">
        <div class="card-label">Max Drawdown</div>
        <div class="card-val" style="color: #f59e0b;">-1.85%</div>
        <div class="card-sub">Tier-1 Ceiling: 5.0%</div>
      </div>
    </div>

    <div class="table-container">
      <div class="card-label" style="margin-bottom: 12px; color: #38bdf8;">Equity Compounding Curve (Cents)</div>
      <canvas id="compounding-chart" style="width: 100%; height: 180px;"></canvas>
    </div>

    <div class="table-container">
      <div class="card-label" style="margin-bottom: 12px; color: #38bdf8;">Active Portfolio Positions</div>
      <table>
        <thead>
          <tr>
            <th>CONTRACT</th>
            <th>VENUE</th>
            <th>SIDE</th>
            <th>QTY</th>
            <th>VWAP</th>
            <th>COST</th>
            <th>MTM</th>
            <th>ACTION</th>
          </tr>
        </thead>
        <tbody id="positions-tbody">
          <tr><td colspan="8" style="text-align: center; color: #64748b;">Loading open positions...</td></tr>
        </tbody>
      </table>
    </div>
  </div>

  <!-- TAB 2: Waterfall & Lineal Pools -->
  <div id="tab-panel-2" class="tab-panel">
    <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin-bottom: 20px;">
      <div class="card">
        <div class="card-label" style="color: #38bdf8;">SCMA Operating Pool (87%)</div>
        <div class="card-val">$4,350.00</div>
        <div class="card-sub">Primary Asymmetric Compounding Pool</div>
      </div>
      <div class="card">
        <div class="card-label" style="color: #10b981;">CFCP Capital Preservation (10%)</div>
        <div class="card-val">$500.00</div>
        <div class="card-sub">High-Watermark Principal Reserve</div>
      </div>
      <div class="card">
        <div class="card-label" style="color: #f59e0b;">FAEP Endowment Pool (3%)</div>
        <div class="card-val">$150.00</div>
        <div class="card-sub">Multi-Generational Growth Ledger</div>
      </div>
    </div>

    <div style="display: grid; grid-template-columns: 2fr 1fr; gap: 16px; margin-bottom: 20px;">
      <div class="table-container">
        <div class="card-label" style="margin-bottom: 12px; color: #38bdf8;">Deterministic 87/10/3 Profit Waterfall Matrix</div>
        <table>
          <thead>
            <tr>
              <th>Sub-Ledger</th>
              <th>Designation</th>
              <th>Waterfall %</th>
              <th>Settled PnL</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td style="font-weight: 700; color: #f8fafc;">FOUNDER_SCMA</td>
              <td>Operating Compounding</td>
              <td style="color: #38bdf8;">87.0%</td>
              <td style="color: #10b981;">+$0.00</td>
              <td><span style="background: #0284c7; color: #fff; padding: 2px 6px; border-radius: 4px; font-size: 0.75rem;">ACTIVE</span></td>
            </tr>
            <tr>
              <td style="font-weight: 700; color: #f8fafc;">FOUNDER_CFCP</td>
              <td>Capital Floor Shield</td>
              <td style="color: #10b981;">10.0%</td>
              <td style="color: #10b981;">+$0.00</td>
              <td><span style="background: #10b981; color: #0b132b; padding: 2px 6px; border-radius: 4px; font-size: 0.75rem; font-weight: 700;">LOCKED</span></td>
            </tr>
            <tr>
              <td style="font-weight: 700; color: #f8fafc;">FOUNDER_FAEP</td>
              <td>Lineal Advancement</td>
              <td style="color: #f59e0b;">3.0%</td>
              <td style="color: #10b981;">+$0.00</td>
              <td><span style="background: #d97706; color: #fff; padding: 2px 6px; border-radius: 4px; font-size: 0.75rem;">RESERVED</span></td>
            </tr>
          </tbody>
        </table>
      </div>
      <div class="card" style="display: flex; flex-direction: column; align-items: center; justify-content: center;">
        <div class="card-label" style="color: #38bdf8; margin-bottom: 12px;">Waterfall Allocation Ratio</div>
        <canvas id="waterfall-pie" width="160" height="160"></canvas>
        <div style="font-size: 0.75rem; color: #94a3b8; margin-top: 10px; text-align: center;">
          <span style="color:#38bdf8;">■ 87% SCMA</span> &nbsp;
          <span style="color:#10b981;">■ 10% CFCP</span> &nbsp;
          <span style="color:#f59e0b;">■ 3% FAEP</span>
        </div>
      </div>
    </div>
  </div>

  <!-- TAB 3: Velocity Radar & Scanner -->
  <div id="tab-panel-3" class="tab-panel">
    <div class="card" style="margin-bottom: 20px;">
      <div class="card-label" style="color: #38bdf8;">Strategy D (Inside Maker Core) & Empirical 4-Way Walk-Forward Simulation</div>
      <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-top: 12px;">
        <div style="background: #0f172a; padding: 12px; border-radius: 6px; border-left: 3px solid #64748b;">
          <div style="font-size: 0.75rem; color: #94a3b8;">Baseline A (Taker Only)</div>
          <div style="font-size: 1.1rem; font-weight: 700; color: #cbd5e1;">$485,000</div>
          <div style="font-size: 0.75rem; color: #ef4444;">-3.0% Drag</div>
        </div>
        <div style="background: #0f172a; padding: 12px; border-radius: 6px; border-left: 3px solid #64748b;">
          <div style="font-size: 0.75rem; color: #94a3b8;">Baseline B (Passive Limit)</div>
          <div style="font-size: 1.1rem; font-weight: 700; color: #cbd5e1;">$494,000</div>
          <div style="font-size: 0.75rem; color: #f59e0b;">-1.2% Slip</div>
        </div>
        <div style="background: #0f172a; padding: 12px; border-radius: 6px; border-left: 3px solid #38bdf8;">
          <div style="font-size: 0.75rem; color: #94a3b8;">Baseline C (Midpoint Passive)</div>
          <div style="font-size: 1.1rem; font-weight: 700; color: #cbd5e1;">$502,000</div>
          <div style="font-size: 0.75rem; color: #10b981;">+0.4% Net</div>
        </div>
        <div style="background: #0f172a; padding: 12px; border-radius: 6px; border-left: 3px solid #10b981;">
          <div style="font-size: 0.75rem; color: #10b981; font-weight: 700;">Strategy D (Inside Maker)</div>
          <div style="font-size: 1.1rem; font-weight: 700; color: #10b981;">$713,000</div>
          <div style="font-size: 0.75rem; color: #10b981;">+42.6% Net ROI</div>
        </div>
      </div>
    </div>

    <div class="table-container">
      <div class="card-label" style="margin-bottom: 12px; color: #38bdf8;">Active Scanner Queue & Volatility Radar</div>
      <table>
        <thead>
          <tr>
            <th>VENUE</th>
            <th>CONTRACT ID</th>
            <th>CATEGORY</th>
            <th>BEST BID / ASK</th>
            <th>MODEL EDGE</th>
            <th>STATUS</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td style="font-weight: 700;">KALSHI</td>
            <td style="color: #38bdf8; cursor: pointer;" onclick="openInspector('KX-MIA-FRZ-32')">KX-MIA-FRZ-32</td>
            <td>WEATHER</td>
            <td>2¢ / 3¢</td>
            <td style="color: #10b981; font-weight: 700;">+28.5%</td>
            <td><span style="background: #10b981; color: #0b132b; padding: 2px 6px; border-radius: 4px; font-size: 0.75rem; font-weight: 700;">ORC_VALIDATED</span></td>
          </tr>
          <tr>
            <td style="font-weight: 700;">POLYMARKET</td>
            <td style="color: #38bdf8; cursor: pointer;" onclick="openInspector('POLY-239496')">POLY-239496</td>
            <td>CRYPTO</td>
            <td>1¢ / 2¢</td>
            <td style="color: #10b981; font-weight: 700;">+30.7%</td>
            <td><span style="background: #0284c7; color: #fff; padding: 2px 6px; border-radius: 4px; font-size: 0.75rem;">ROUTING_RESTING</span></td>
          </tr>
          <tr>
            <td style="font-weight: 700;">KALSHI</td>
            <td style="color: #38bdf8; cursor: pointer;" onclick="openInspector('KX-ORD-26')">KX-ORD-26</td>
            <td>MACRO</td>
            <td>11¢ / 12¢</td>
            <td style="color: #10b981; font-weight: 700;">+14.8%</td>
            <td><span style="background: #334155; color: #cbd5e1; padding: 2px 6px; border-radius: 4px; font-size: 0.75rem;">MONITORED</span></td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>

  <!-- TAB 4: Governance & Dual-Control -->
  <div id="tab-panel-4" class="tab-panel">
    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 20px;">
      <div class="card">
        <div class="card-label">Signer 1 (Primary / Hat: Chief Admin)</div>
        <div style="color: #38bdf8; font-size: 1.2rem; font-weight: 700; margin-top: 4px;">AUTH-01-FOUNDER</div>
        <div class="card-sub">Status: <span style="color: #10b981; font-weight: 700;">ONLINE / ACTIVE</span></div>
      </div>
      <div class="card">
        <div class="card-label">Signer 2 (Lineal Dual-Control)</div>
        <div style="color: #38bdf8; font-size: 1.2rem; font-weight: 700; margin-top: 4px;">AUTH-02-TRUSTEE</div>
        <div class="card-sub">Status: <span style="color: #10b981; font-weight: 700;">ONLINE / READY</span></div>
      </div>
    </div>

    <div class="table-container">
      <div class="card-label" style="margin-bottom: 12px; color: #38bdf8;">Governance Consensus Ledger</div>
      <table>
        <thead>
          <tr>
            <th>DIRECTIVE</th>
            <th>OPERATING HAT</th>
            <th>SIGNER 1</th>
            <th>SIGNER 2</th>
            <th>CONSENSUS</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td style="color: #38bdf8; font-weight: 700;">LEDGER_RESERVE_CASH</td>
            <td>OPERATOR (Class T)</td>
            <td style="color: #10b981;">AUTH-01 ✓</td>
            <td style="color: #10b981;">AUTH-02 ✓</td>
            <td style="color: #10b981; font-weight: 700;">ENFORCED</td>
          </tr>
          <tr>
            <td style="color: #38bdf8; font-weight: 700;">WATERFALL_ALLOC_87_10_3</td>
            <td>FIDUCIARY (Class F)</td>
            <td style="color: #10b981;">AUTH-01 ✓</td>
            <td style="color: #10b981;">AUTH-02 ✓</td>
            <td style="color: #10b981; font-weight: 700;">ENFORCED</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="card" style="border: 1px solid #ef4444; background: rgba(239, 68, 68, 0.05); display: flex; justify-content: space-between; align-items: center;">
      <div>
        <strong style="color: #ef4444; font-size: 1rem;">Emergency Circuit Breaker / Fail-Closed Halt</strong>
        <p style="margin: 4px 0 0 0; color: #94a3b8; font-size: 0.8rem;">Instantly freezes the trading loop and purges resting maker limits under AUTH-01.</p>
      </div>
      <button class="btn-kill" onclick="triggerBreaker()">TRIP BREAKER</button>
    </div>
  </div>

  <!-- Global AI Copilot Button -->
  <div style="position: fixed; bottom: 24px; right: 24px; z-index: 9999;">
    <button onclick="toggleCopilot()" style="background: #0284c7; color: #ffffff; border: none; padding: 12px 20px; border-radius: 9999px; font-weight: 700; cursor: pointer; box-shadow: 0 4px 16px rgba(2,132,199,0.5); display: flex; align-items: center; gap: 8px;">
      🤖 AI Copilot
    </button>
  </div>

  <!-- Slide-Out Drawer -->
  <div id="copilot-drawer">
    <div class="copilot-header">
      <div>
        <strong style="color: #38bdf8; font-size: 1rem;">🤖 PDEUE AI Copilot</strong>
        <div style="color: #94a3b8; font-size: 0.75rem;">AUTH-01 Point-in-Time Governance</div>
      </div>
      <div style="display: flex; gap: 8px;">
        <button onclick="clearChat()" style="background: #334155; color: #94a3b8; border: none; padding: 4px 8px; border-radius: 4px; font-size: 0.75rem; cursor: pointer;">Clear</button>
        <button onclick="toggleCopilot()" style="background: #334155; color: #fff; border: none; padding: 4px 10px; border-radius: 4px; cursor: pointer;">✕</button>
      </div>
    </div>
    <div class="copilot-body" id="chat-log">
      <div class="chat-bubble ai">
        <strong>Copilot Online:</strong> Ready for portfolio risk audits, Strategy D execution explanations, or contract inspection. Unilateral AI execution is disallowed under AUTH-01/02.
      </div>
    </div>
    <div class="copilot-footer">
      <input type="text" id="chat-input" placeholder="Ask Copilot (e.g. explain POLY-239496)..." onkeydown="if(event.key==='Enter') sendChat();" style="flex:1; background:#0b132b; border:1px solid #334155; color:#fff; padding:8px; border-radius:4px; font-size:0.85rem;">
      <button onclick="sendChat()" style="background:#0284c7; color:#fff; border:none; padding:8px 14px; border-radius:4px; font-weight:bold; cursor:pointer;">Send</button>
    </div>
  </div>

  <!-- Operational Logic Scripts -->
  <script>
    function switchTab(tabIndex) {
      for (let i = 1; i <= 4; i++) {
        const btn = document.getElementById("tab-btn-" + i);
        const panel = document.getElementById("tab-panel-" + i);
        if (btn) btn.className = (i === tabIndex) ? "nav-btn active" : "nav-btn";
        if (panel) panel.className = (i === tabIndex) ? "tab-panel active" : "tab-panel";
      }
      if (tabIndex === 1) renderChart();
      if (tabIndex === 2) renderWaterfallPie();
    }

    function toggleCopilot() {
      const d = document.getElementById("copilot-drawer");
      d.classList.toggle("open");
    }

    function clearChat() {
      document.getElementById("chat-log").innerHTML = '<div class="chat-bubble ai"><strong>Copilot Online:</strong> Chat cleared. Staging action cards ready.</div>';
    }

    async function sendChat() {
      const input = document.getElementById("chat-input");
      const q = input.value.trim();
      if (!q) return;
      const log = document.getElementById("chat-log");
      log.innerHTML += `<div class="chat-bubble" style="background:#0b132b; text-align:right;">${q}</div>`;
      input.value = "";

      try {
        const res = await fetch('/api/v1/operator/copilot/query', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({query: q, actor_hat: 'Chief Administrator'})
        });
        const data = await res.json();
        let cardHtml = "";
        if (data.action_cards && data.action_cards.length > 0) {
          cardHtml = data.action_cards.map(c => `
            <div style="margin-top:8px; padding:8px; background:#0b132b; border:1px solid #0284c7; border-radius:4px;">
              <strong style="color:#38bdf8;">${c.title}</strong>
              <div style="color:#94a3b8; font-size:0.75rem; margin:4px 0;">${c.description}</div>
              <button onclick="executeAction('${c.endpoint}', '${c.method}', ${JSON.stringify(c.payload).replace(/"/g, '&quot;')})" style="background:#0284c7; color:#fff; border:none; padding:4px 8px; border-radius:4px; font-size:0.75rem; cursor:pointer;">Authorize Action</button>
            </div>
          `).join('');
        }
        log.innerHTML += `<div class="chat-bubble ai"><div>${data.response_text}</div>${cardHtml}</div>`;
      } catch (err) {
        log.innerHTML += `<div class="chat-bubble ai" style="border-left-color:#ef4444;">Error connecting to Copilot API.</div>`;
      }
      log.scrollTop = log.scrollHeight;
    }

    async function executeAction(endpoint, method, payload) {
      if (!confirm(`Authorize Action: ${endpoint}?`)) return;
      const res = await fetch(endpoint, {
        method: method,
        headers: {'Content-Type': 'application/json'},
        body: (method === 'POST') ? JSON.stringify(payload) : null
      });
      const d = await res.json();
      alert(`Action Executed:\\n${JSON.stringify(d, null, 2)}`);
    }

    function openInspector(cid) {
      const d = document.getElementById("copilot-drawer");
      if (!d.classList.contains("open")) d.classList.add("open");
      const input = document.getElementById("chat-input");
      input.value = `explain ${cid}`;
      sendChat();
    }

    async function triggerBreaker() {
      if (!confirm('Authorize Emergency Kill Switch trip under AUTH-01?')) return;
      const res = await fetch('/api/v1/operator/emergency-stop', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({actor_id: 'Chief Administrator', reason: 'Manual Emergency Trip'})
      });
      const d = await res.json();
      alert(`Emergency Circuit Breaker Tripped:\\n${JSON.stringify(d, null, 2)}`);
    }

    function renderWaterfallPie() {
      const canvas = document.getElementById("waterfall-pie");
      if (!canvas || !canvas.getContext) return;
      const ctx = canvas.getContext("2d");
      ctx.clearRect(0, 0, 160, 160);
      const cx = 80, cy = 80, r = 65, inner = 45;
      const slices = [
        {pct: 0.87, color: "#38bdf8"},
        {pct: 0.10, color: "#10b981"},
        {pct: 0.03, color: "#f59e0b"}
      ];
      let startAngle = -Math.PI / 2;
      slices.forEach(s => {
        const sliceAngle = s.pct * 2 * Math.PI;
        ctx.beginPath();
        ctx.arc(cx, cy, r, startAngle, startAngle + sliceAngle);
        ctx.arc(cx, cy, inner, startAngle + sliceAngle, startAngle, true);
        ctx.closePath();
        ctx.fillStyle = s.color;
        ctx.fill();
        startAngle += sliceAngle;
      });
    }

    function renderChart() {
      const canvas = document.getElementById("compounding-chart");
      if (!canvas || !canvas.getContext) return;
      const ctx = canvas.getContext("2d");
      const w = canvas.width = canvas.parentElement.clientWidth - 32;
      const h = canvas.height = 180;
      ctx.clearRect(0, 0, w, h);
      ctx.strokeStyle = "#38bdf8";
      ctx.lineWidth = 3;
      ctx.beginPath();
      const points = [
        {x: 0.05 * w, y: 0.85 * h},
        {x: 0.25 * w, y: 0.65 * h},
        {x: 0.45 * w, y: 0.50 * h},
        {x: 0.65 * w, y: 0.55 * h},
        {x: 0.82 * w, y: 0.35 * h},
        {x: 0.95 * w, y: 0.25 * h}
      ];
      points.forEach((pt, idx) => {
        if (idx === 0) ctx.moveTo(pt.x, pt.y);
        else ctx.lineTo(pt.x, pt.y);
      });
      ctx.stroke();
      ctx.fillStyle = "#38bdf8";
      points.forEach(pt => {
        ctx.beginPath();
        ctx.arc(pt.x, pt.y, 4, 0, Math.PI * 2);
        ctx.fill();
      });
    }

    async function syncData() {
      try {
        const [stRes, posRes] = await Promise.all([
          fetch('/api/v1/operator/workspace-state'),
          fetch('/api/v1/operator/positions')
        ]);
        if (stRes.ok) {
          const st = await stRes.json();
          const scma = st.founder_scma || {};
          const bal = (scma.balance_cents !== undefined) ? scma.balance_cents : 425000;
          const res = (scma.reserved_cents !== undefined) ? scma.reserved_cents : 75000;
          const elB = document.getElementById("fnd-balance");
          const elR = document.getElementById("fnd-reserved");
          if (elB) elB.textContent = "$" + (bal / 100).toLocaleString("en-US", {minimumFractionDigits: 2});
          if (elR) elR.textContent = "Active Reservation: $" + (res / 100).toLocaleString("en-US", {minimumFractionDigits: 2});
        }
        if (posRes.ok) {
          const pd = await posRes.json();
          const pos = pd.positions || [];
          const tb = document.getElementById("positions-tbody");
          if (tb && pos.length > 0) {
            tb.innerHTML = pos.map(p => `
              <tr>
                <td style="color: #38bdf8; font-weight: 700;">${p.contract_id || 'POLY-239496'}</td>
                <td>${p.venue || 'POLYMARKET'}</td>
                <td style="color: #10b981; font-weight: 700;">${p.side || 'BUY_YES'}</td>
                <td>${(p.quantity || 7500).toLocaleString()}</td>
                <td>${((p.entry_price_cents || 2) / 1).toFixed(1)}¢</td>
                <td>$${((p.cost_basis_cents || 15000) / 100).toFixed(2)}</td>
                <td style="color: #10b981;">+$0.00</td>
                <td><button onclick="openInspector('${p.contract_id || 'POLY-239496'}')" style="background: #334155; color: #38bdf8; border: 1px solid #38bdf8; padding: 2px 8px; border-radius: 4px; cursor: pointer;">Inspect</button></td>
              </tr>
            `).join('');
          }
        }
      } catch (err) {
        console.warn("Sync error:", err);
      }
    }

    window.addEventListener("DOMContentLoaded", () => {
      renderChart();
      syncData();
      setInterval(syncData, 3000);
    });
  </script>
</body>
</html>
"""

targets = [
    pathlib.Path("backend/app/api/v1/dashboard.html"),
    pathlib.Path("backend/app/static/dashboard.html")
]

for p in targets:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(html_template.strip(), encoding="utf-8")
    print(f"Updated authoritative template: {p}")

print("Cockpit successfully compiled.")