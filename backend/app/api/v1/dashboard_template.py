  <div class="topbar">
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
    <button class="tab-btn active" onclick="showTab('tab1', this)">1. Founder SCMA & Executive Overview</button>
    <button class="tab-btn" onclick="showTab('tab2', this)">2. Family Lineal Pools & Sub-Ledgers</button>
    <button class="tab-btn" onclick="showTab('tab3', this)">3. Velocity Radar & Scanner</button>
    <button class="tab-btn" onclick="showTab('tab4', this)">4. Governance & Dual-Control</button>
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
          <button class="tf-btn" onclick="fetchTf('1H', this)">1H</button>
          <button class="tf-btn active" onclick="fetchTf('24H', this)">24H</button>
          <button class="tf-btn" onclick="fetchTf('7D', this)">7D</button>
          <button class="tf-btn" onclick="fetchTf('1MO', this)">1MO</button>
          <button class="tf-btn" onclick="fetchTf('1Y', this)">1Y</button>
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
  <div id="tab2" class="tab-content">
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
