DASHBOARD_HTML_TEMPLATE = '<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>PDEUE Chief Administrator Workspace</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 20px; }
    .topbar { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #334155; padding-bottom: 15px; margin-bottom: 20px; }
    .tabs { display: flex; gap: 8px; margin-bottom: 20px; border-bottom: 1px solid #334155; }
    .tab-btn { background: #1e293b; color: #94a3b8; border: none; padding: 12px 20px; font-weight: 600; cursor: pointer; border-radius: 6px 6px 0 0; }
    .tab-btn.active { background: #38bdf8; color: #0f172a; }
    .tab-content { display: none; }
    .tab-content.active { display: block; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 20px; margin-bottom: 25px; }
    .card { background: #1e293b; border: 1px solid #334155; border-radius: 8px; padding: 18px; }
    .card h3 { margin-top: 0; color: #38bdf8; font-size: 0.95rem; text-transform: uppercase; }
    .val { font-size: 1.8rem; font-weight: 700; margin: 10px 0; }
    table { width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 0.85rem; }
    th, td { padding: 10px; text-align: left; border-bottom: 1px solid #334155; }
    th { background: #090d16; color: #94a3b8; }
    .btn-kill { background: #ef4444; color: white; border: none; padding: 10px 20px; font-weight: bold; border-radius: 6px; cursor: pointer; }
    .btn-action { background: #38bdf8; color: #0f172a; border: none; padding: 6px 12px; font-weight: bold; border-radius: 4px; cursor: pointer; }
    abbr[data-tooltip] { text-decoration: underline dotted #38bdf8; cursor: help; position: relative; }
    abbr[data-tooltip]:hover::after { content: attr(data-tooltip); position: absolute; bottom: 125%; left: 50%; transform: translateX(-50%); background: #020617; color: #f8fafc; border: 1px solid #475569; padding: 4px 8px; font-size: 0.75rem; border-radius: 4px; white-space: nowrap; z-index: 100; }
    #drawer { position: fixed; right: -450px; top: 0; width: 420px; height: 100%; background: #090d16; border-left: 2px solid #38bdf8; box-shadow: -5px 0 25px rgba(0,0,0,0.7); padding: 25px; box-sizing: border-box; transition: right 0.3s ease; z-index: 200; overflow-y: auto; }
    #drawer.open { right: 0; }
    .close-btn { background: #334155; color: white; border: none; padding: 5px 10px; border-radius: 4px; cursor: pointer; float: right; }
    .tf-btn { background: #1e293b; color: #94a3b8; border: 1px solid #334155; padding: 4px 10px; border-radius: 4px; cursor: pointer; font-size: 0.75rem; }
    .tf-btn.active { background: #38bdf8; color: #0f172a; font-weight: bold; }
  </style>
</head>
<body>
'
DASHBOARD_HTML_TEMPLATE += '  <div class="topbar">
    <div>
      <h1 style="margin:0; font-size: 1.4rem;">PDEUE Chief Administrator Workspace</h1>
      <small style="color: #94a3b8;">Binding Lexicon v0.4 | Dual-Control Active</small>
    </div>
    <div style="display:flex; gap:15px; align-items:center;">
      <span id="sys-mode" style="background:#22c55e; color:#0f172a; padding:6px 14px; font-weight:bold; border-radius:20px;">MODE: PAPER</span>
      <button class="btn-kill" onclick="triggerKillSwitch()">EMERGENCY KILL SWITCH</button>
    </div>
  </div>
  <div class="tabs">
    <button class="tab-btn active" onclick="showTab(&apos;tab1&apos;, this)">1. Founder SCMA & Executive Overview</button>
    <button class="tab-btn" onclick="showTab(&apos;tab2&apos;, this)">2. Family Lineal Pools & Sub-Ledgers</button>
    <button class="tab-btn" onclick="showTab(&apos;tab3&apos;, this)">3. Velocity Radar & Scanner</button>
    <button class="tab-btn" onclick="showTab(&apos;tab4&apos;, this)">4. Governance & Dual-Control</button>
  </div>
  <div id="tab1" class="tab-content active">
    <div class="grid">
      <div class="card">
        <h3><abbr data-tooltip="Self-Contained Member Account: Isolated founder sub-ledger">Founder SCMA Cash</abbr></h3>
        <div class="val" id="fnd-balance">$5,000.00</div>
        <small style="color:#94a3b8;">Active Reservation: <span id="fnd-reserved">$0.00</span></small>
      </div>
      <div class="card">
        <h3><abbr data-tooltip="Founder/Chief Administrator Endowment Pool: 3% carry on winning trades">Founder FAEP Pool (3%)</abbr></h3>
        <div class="val" id="fnd-faep" style="color:#38bdf8;">$0.00</div>
        <small style="color:#94a3b8;">Lifetime PnL: <span id="fnd-pnl">$0.00</span></small>
      </div>
      <div class="card">
        <h3><abbr data-tooltip="Total Gross Win Cents / Total Gross Loss Cents">Profit Factor</abbr></h3>
        <div class="val" id="metric-pf" style="color:#22c55e;">2.84x</div>
        <small id="metric-wr">Win Rate: 75.0%</small>
      </div>
      <div class="card">
        <h3><abbr data-tooltip="Peak-to-trough historical drawdown bound">Max Drawdown</abbr></h3>
        <div class="val" id="metric-mdd" style="color:#f59e0b;">-1.85%</div>
        <small style="color:#94a3b8;">Tier-1 Ceiling: 5.0%</small>
      </div>
    </div>
    <div class="card" style="margin-bottom:20px;">
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
        <h3>Equity Compounding Curve (Cents)</h3>
        <div style="display:flex; gap:6px;">
          <button class="tf-btn" onclick="fetchTf(&apos;1H&apos;, this)">1H</button>
          <button class="tf-btn active" onclick="fetchTf(&apos;24H&apos;, this)">24H</button>
          <button class="tf-btn" onclick="fetchTf(&apos;7D&apos;, this)">7D</button>
          <button class="tf-btn" onclick="fetchTf(&apos;1MO&apos;, this)">1MO</button>
          <button class="tf-btn" onclick="fetchTf(&apos;1Y&apos;, this)">1Y</button>
        </div>
      </div>
      <canvas id="chart-equity" height="70"></canvas>
    </div>
    <div class="card">
      <h3>Active Portfolio Positions</h3>
      <table>
        <thead><tr><th>Contract</th><th>Venue</th><th>Side</th><th>Qty</th><th><abbr data-tooltip="Volume-Weighted Average Price">VWAP</abbr></th><th>Cost</th><th><abbr data-tooltip="Mark-to-Market Valuation">MTM</abbr></th><th>Action</th></tr></thead>
        <tbody id="pos-tbody"><tr><td colspan="8" style="text-align:center; color:#94a3b8;">No open positions</td></tr></tbody>
      </table>
    </div>
  </div>
'
DASHBOARD_HTML_TEMPLATE += '  <div id="tab2" class="tab-content">
    <div class="grid">
      <div class="card">
        <h3><abbr data-tooltip="Central Familial Common Pool: 10% Lineage Treasury">CFCP Family Pool (10%)</abbr></h3>
        <div class="val" id="pool-cfcp" style="color:#22c55e;">$0.00</div>
        <small style="color:#94a3b8;">Automated Lineage Compounding</small>
      </div>
      <div class="card">
        <h3><abbr data-tooltip="Transaction Profit Waterfall">Waterfall Distribution</abbr></h3>
        <canvas id="chart-waterfall" height="120"></canvas>
      </div>
    </div>
    <div class="card">
      <h3>Registered Family Member Sub-Ledgers</h3>
      <table>
        <thead><tr><th>Member ID</th><th>Balance</th><th>Reserved</th><th>Risk Dial</th><th>Lifetime Profit</th></tr></thead>
        <tbody id="members-tbody"></tbody>
      </table>
    </div>
  </div>
  <div id="tab3" class="tab-content">
    <div class="card" style="margin-bottom:20px;">
      <h3>Hybrid Velocity Radar & Scanner</h3>
      <table>
        <thead><tr><th>Contract</th><th>Category</th><th>Venue</th><th>Ask</th><th><abbr data-tooltip="Model Exceedance Probability">P(Model)</abbr></th><th>Net Edge</th><th>Expiry</th><th>Inspect</th></tr></thead>
        <tbody id="scanner-tbody"></tbody>
      </table>
    </div>
  </div>
  <div id="tab4" class="tab-content">
    <div class="grid">
      <div class="card">
        <h3>Simulated Dual-Control Queue</h3>
        <div id="dc-queue-list"><small style="color:#94a3b8;">No pending co-approvals.</small></div>
      </div>
      <div class="card">
        <h3>Active Hat Operating Context</h3>
        <select id="hat-select" style="width:100%; padding:10px; background:#0f172a; color:white; border:1px solid #334155; border-radius:4px;">
          <option>Chief Administrator (Governance Plane)</option>
          <option>System Administrator T3 (Infrastructure Plane)</option>
          <option>Financial Advisor F3 (Risk Review)</option>
          <option>Member User (Founder SCMA View)</option>
        </select>
      </div>
    </div>
  </div>
  <div id="drawer">
    <button class="close-btn" onclick="closeDrawer()">X</button>
    <h2 id="drw-title" style="margin-top:0; color:#38bdf8; font-size:1.2rem;">Contract Detail</h2>
    <hr style="border-color:#334155;">
    <div id="drw-body" style="font-size:0.85rem; line-height:1.6;"></div>
  </div>
'
DASHBOARD_HTML_TEMPLATE += '  <script>
    let eqChart = null, wfChart = null;
    function showTab(id, btn) {
      document.querySelectorAll(".tab-content").forEach(el => el.classList.remove("active"));
      document.querySelectorAll(".tab-btn").forEach(el => el.classList.remove("active"));
      document.getElementById(id).classList.add("active");
      btn.classList.add("active");
    }
    function closeDrawer() { document.getElementById("drawer").classList.remove("open"); }
    function inspect(cid) {
      fetch("/api/v1/operator/contract/" + cid).then(r => r.json()).then(d => {
        document.getElementById("drw-title").innerText = d.contract_id;
        document.getElementById("drw-body").innerHTML = "<p><strong>Venue:</strong> " + d.venue + " | <strong>Domain:</strong> " + d.category + "</p><p><strong>P(Model):</strong> " + (d.model_probability*100).toFixed(1) + "% | <strong>Ask:</strong> $" + d.venue_implied_prob.toFixed(2) + "</p><p><strong>Net Edge:</strong> +" + (d.net_edge*100).toFixed(1) + "%</p><p><strong>Early Harvest:</strong> " + (d.profit_capture_ratio*100).toFixed(1) + "% / 80%</p><p><strong>Audit Hash:</strong> <br><code style=\"color:#38bdf8; font-size:0.75rem;\">" + d.audit_hash + "</code></p>";
        document.getElementById("drawer").classList.add("open");
      });
    }
    function initCharts() {
      const ctxEq = document.getElementById("chart-equity").getContext("2d");
      eqChart = new Chart(ctxEq, { type: "line", data: { labels: ["T-6h","T-5h","T-4h","T-3h","T-2h","T-1h","Now"], datasets: [{ label: "Equity (Cents)", data: [500000, 502000, 504500, 503800, 506200, 508000, 510000], borderColor: "#38bdf8", tension: 0.3 }] }, options: { responsive: true, plugins: { legend: { display: false } } } });
      const ctxWf = document.getElementById("chart-waterfall").getContext("2d");
      wfChart = new Chart(ctxWf, { type: "doughnut", data: { labels: ["SCMA (87%)", "CFCP (10%)", "FAEP (3%)"], datasets: [{ data: [87, 10, 3], backgroundColor: ["#38bdf8", "#22c55e", "#a855f7"] }] }, options: { responsive: true } });
    }
    function fetchTf(tf, btn) {
      document.querySelectorAll(".tf-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      fetch("/api/v1/operator/analytics/pnl-series?timeframe=" + tf).then(r => r.json()).then(d => {
        eqChart.data.labels = d.labels;
        eqChart.data.datasets[0].data = d.equity_curve_cents;
        eqChart.update();
      });
    }
    function triggerKillSwitch() {
      if (confirm("Trip Emergency Circuit Breaker?")) {
        fetch("/api/v1/operator/emergency-stop", { method: "POST" }).then(() => refresh());
      }
    }
    function refresh() {
      fetch("/api/v1/operator/workspace-state").then(r => r.json()).then(d => {
        document.getElementById("fnd-balance").innerText = "$" + (d.founder_scma.balance_cents / 100).toFixed(2);
        document.getElementById("fnd-reserved").innerText = "$" + (d.founder_scma.reserved_cents / 100).toFixed(2);
        document.getElementById("fnd-faep").innerText = "$" + (d.faep_cents / 100).toFixed(2);
        document.getElementById("pool-cfcp").innerText = "$" + (d.cfcp_cents / 100).toFixed(2);
        document.getElementById("metric-pf").innerText = d.metrics.profit_factor + "x";
        document.getElementById("metric-wr").innerText = "Win Rate: " + d.metrics.win_rate_pct + "%";
        const tbodyPos = document.getElementById("pos-tbody");
        if (d.portfolio.positions && d.portfolio.positions.length > 0) {
          tbodyPos.innerHTML = d.portfolio.positions.map(p => "<tr><td><a href=\"#\" onclick=\"inspect('" + p.contract_id + "')\" style=\"color:#38bdf8;\">" + p.contract_id + "</a></td><td>" + p.venue + "</td><td>" + p.side + "</td><td>" + p.quantity + "</td><td>$" + p.vwap_price.toFixed(2) + "</td><td>$" + (p.total_cost_cents/100).toFixed(2) + "</td><td>$" + (p.mtm_value_cents/100).toFixed(2) + "</td><td><button class=\"btn-action\" onclick=\"inspect('" + p.contract_id + "')\">Inspect</button></td></tr>").join("");
        }
        const tbodyMem = document.getElementById("members-tbody");
        if (d.family_members) {
          tbodyMem.innerHTML = d.family_members.map(m => "<tr><td>" + m.member_id + "</td><td>$" + (m.balance_cents/100).toFixed(2) + "</td><td>$" + (m.reserved_cents/100).toFixed(2) + "</td><td>" + (m.max_risk_pct*100).toFixed(1) + "%</td><td>$" + (m.lifetime_profit_cents/100).toFixed(2) + "</td></tr>").join("");
        }
        const tbodySc = document.getElementById("scanner-tbody");
        if (d.screened_opportunities) {
          tbodySc.innerHTML = d.screened_opportunities.map(o => "<tr><td>" + o.contract_id + "</td><td>" + o.category + "</td><td>" + o.venue + "</td><td>$" + o.entry_price.toFixed(2) + "</td><td>" + ((o.model_probability||0.5)*100).toFixed(1) + "%</td><td>+" + (o.net_edge*100).toFixed(1) + "%</td><td>" + o.hours_to_expiry + "h</td><td><button class=\"btn-action\" onclick=\"inspect('" + o.contract_id + "')\">View</button></td></tr>").join("");
        }
      });
    }
    window.onload = () => { initCharts(); refresh(); setInterval(refresh, 5000); };
  </script>
</body>
</html>'
