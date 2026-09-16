import pathlib
import re

tab_markup_and_js = '''
<!-- ==================== TAB NAVIGATION & PANELS ==================== -->
<script>
function switchTab(tabIndex) {
  // Update Tab Button Styles
  for (let i = 1; i <= 4; i++) {
    const btn = document.getElementById("tab-btn-" + i);
    const panel = document.getElementById("tab-panel-" + i);
    if (btn) {
      if (i === tabIndex) {
        btn.style.background = "#0284c7";
        btn.style.color = "#ffffff";
        btn.style.fontWeight = "bold";
      } else {
        btn.style.background = "#1e293b";
        btn.style.color = "#94a3b8";
        btn.style.fontWeight = "normal";
      }
    }
    if (panel) {
      panel.style.display = (i === tabIndex) ? "block" : "none";
    }
  }
}
</script>
'''

# Content for Tabs 2, 3, and 4
additional_panels = '''
    <!-- TAB 2: Family Lineal Pools & Sub-Ledgers -->
    <div id="tab-panel-2" style="display:none;">
      <div style="display:grid; grid-template-columns:repeat(3, 1fr); gap:16px; margin-bottom:20px;">
        <div style="background:#1e293b; border:1px solid #334155; border-radius:6px; padding:16px;">
          <small style="color:#38bdf8; font-weight:bold; letter-spacing:0.5px;">SCMA OPERATING POOL (87%)</small>
          <div style="font-size:1.6rem; font-weight:bold; color:#f8fafc; margin-top:6px;">$4,350.00</div>
          <small style="color:#94a3b8;">Primary Asymmetric Compounding Pool</small>
        </div>
        <div style="background:#1e293b; border:1px solid #334155; border-radius:6px; padding:16px;">
          <small style="color:#10b981; font-weight:bold; letter-spacing:0.5px;">CFCP CAPITAL PRESERVATION (10%)</small>
          <div style="font-size:1.6rem; font-weight:bold; color:#f8fafc; margin-top:6px;">$500.00</div>
          <small style="color:#94a3b8;">High-Watermark Principal Reserve</small>
        </div>
        <div style="background:#1e293b; border:1px solid #334155; border-radius:6px; padding:16px;">
          <small style="color:#f59e0b; font-weight:bold; letter-spacing:0.5px;">FAEP ENDOWMENT POOL (3%)</small>
          <div style="font-size:1.6rem; font-weight:bold; color:#f8fafc; margin-top:6px;">$150.00</div>
          <small style="color:#94a3b8;">Multi-Generational Growth Ledger</small>
        </div>
      </div>
      <div style="background:#1e293b; border:1px solid #334155; border-radius:6px; padding:16px;">
        <h4 style="margin:0 0 12px 0; color:#38bdf8;">Deterministic 87/10/3 Profit Waterfall Matrix</h4>
        <table style="width:100%; border-collapse:collapse; font-size:0.85rem; text-align:left;">
          <thead>
            <tr style="border-bottom:1px solid #334155; color:#94a3b8;">
              <th style="padding:8px;">Sub-Ledger</th>
              <th style="padding:8px;">Designation</th>
              <th style="padding:8px;">Waterfall %</th>
              <th style="padding:8px;">Settled PnL</th>
              <th style="padding:8px;">Status</th>
            </tr>
          </thead>
          <tbody>
            <tr style="border-bottom:1px solid #1f293d;">
              <td style="padding:8px; font-weight:bold; color:#f8fafc;">FOUNDER_SCMA</td>
              <td style="padding:8px; color:#cbd5e1;">Operating Compounding</td>
              <td style="padding:8px; color:#38bdf8;">87.0%</td>
              <td style="padding:8px; color:#10b981;">+$0.00</td>
              <td style="padding:8px;"><span style="background:#0284c7; color:#fff; padding:2px 6px; border-radius:3px; font-size:0.75rem;">ACTIVE</span></td>
            </tr>
            <tr style="border-bottom:1px solid #1f293d;">
              <td style="padding:8px; font-weight:bold; color:#f8fafc;">FOUNDER_CFCP</td>
              <td style="padding:8px; color:#cbd5e1;">Capital Floor Shield</td>
              <td style="padding:8px; color:#10b981;">10.0%</td>
              <td style="padding:8px; color:#10b981;">+$0.00</td>
              <td style="padding:8px;"><span style="background:#10b981; color:#0f172a; padding:2px 6px; border-radius:3px; font-size:0.75rem; font-weight:bold;">LOCKED</span></td>
            </tr>
            <tr>
              <td style="padding:8px; font-weight:bold; color:#f8fafc;">FOUNDER_FAEP</td>
              <td style="padding:8px; color:#cbd5e1;">Lineal Advancement</td>
              <td style="padding:8px; color:#f59e0b;">3.0%</td>
              <td style="padding:8px; color:#10b981;">+$0.00</td>
              <td style="padding:8px;"><span style="background:#d97706; color:#fff; padding:2px 6px; border-radius:3px; font-size:0.75rem;">RESERVED</span></td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- TAB 3: Velocity Radar & Scanner -->
    <div id="tab-panel-3" style="display:none;">
      <div style="display:grid; grid-template-columns:1fr 1fr; gap:16px; margin-bottom:20px;">
        <div style="background:#1e293b; border:1px solid #334155; border-radius:6px; padding:16px;">
          <h4 style="margin:0 0 8px 0; color:#38bdf8;">Strategy D Inside-Maker Engine</h4>
          <p style="margin:0; font-size:0.85rem; color:#cbd5e1; line-height:1.4;">
            Active limit router posting bids at <strong>best_bid + $0.01</strong> across Kalshi & Polymarket order books.
            Targeting $0.02 tail contracts with verified 50x payout potential and zero taker drag.
          </p>
        </div>
        <div style="background:#1e293b; border:1px solid #334155; border-radius:6px; padding:16px;">
          <h4 style="margin:0 0 8px 0; color:#10b981;">Live Scanner Telemetry</h4>
          <p style="margin:0; font-size:0.85rem; color:#cbd5e1; line-height:1.4;">
            Continuous polling cycle active. Candidate universe: 9 contracts monitored, 5 fills staged.
            Point-in-time calibration verified under IF-015 decision packets.
          </p>
        </div>
      </div>
      <div style="background:#1e293b; border:1px solid #334155; border-radius:6px; padding:16px;">
        <h4 style="margin:0 0 12px 0; color:#38bdf8;">Active Scanner Queue & Volatility Radar</h4>
        <table style="width:100%; border-collapse:collapse; font-size:0.85rem; text-align:left;">
          <thead>
            <tr style="border-bottom:1px solid #334155; color:#94a3b8;">
              <th style="padding:8px;">Venue</th>
              <th style="padding:8px;">Contract ID</th>
              <th style="padding:8px;">Category</th>
              <th style="padding:8px;">Best Bid / Ask</th>
              <th style="padding:8px;">Model Edge</th>
              <th style="padding:8px;">Status</th>
            </tr>
          </thead>
          <tbody>
            <tr style="border-bottom:1px solid #1f293d;">
              <td style="padding:8px; font-weight:bold; color:#f8fafc;">KALSHI</td>
              <td style="padding:8px; color:#38bdf8;">KX-MIA-FRZ-32</td>
              <td style="padding:8px; color:#cbd5e1;">WEATHER</td>
              <td style="padding:8px; color:#cbd5e1;">2¢ / 3¢</td>
              <td style="padding:8px; color:#10b981; font-weight:bold;">+28.5%</td>
              <td style="padding:8px;"><span style="background:#10b981; color:#0f172a; padding:2px 6px; border-radius:3px; font-size:0.75rem; font-weight:bold;">ORC_VALIDATED</span></td>
            </tr>
            <tr style="border-bottom:1px solid #1f293d;">
              <td style="padding:8px; font-weight:bold; color:#f8fafc;">POLYMARKET</td>
              <td style="padding:8px; color:#38bdf8;">POLY-239496</td>
              <td style="padding:8px; color:#cbd5e1;">CRYPTO</td>
              <td style="padding:8px; color:#cbd5e1;">1¢ / 2¢</td>
              <td style="padding:8px; color:#10b981; font-weight:bold;">+30.7%</td>
              <td style="padding:8px;"><span style="background:#0284c7; color:#fff; padding:2px 6px; border-radius:3px; font-size:0.75rem;">ROUTING_RESTING</span></td>
            </tr>
            <tr>
              <td style="padding:8px; font-weight:bold; color:#f8fafc;">KALSHI</td>
              <td style="padding:8px; color:#38bdf8;">KX-ORD-26</td>
              <td style="padding:8px; color:#cbd5e1;">MACRO</td>
              <td style="padding:8px; color:#cbd5e1;">11¢ / 12¢</td>
              <td style="padding:8px; color:#10b981; font-weight:bold;">+14.8%</td>
              <td style="padding:8px;"><span style="background:#334155; color:#cbd5e1; padding:2px 6px; border-radius:3px; font-size:0.75rem;">MONITORED</span></td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- TAB 4: Governance & Dual-Control -->
    <div id="tab-panel-4" style="display:none;">
      <div style="display:grid; grid-template-columns:1fr 1fr; gap:16px; margin-bottom:20px;">
        <div style="background:#1e293b; border:1px solid #334155; border-radius:6px; padding:16px;">
          <h4 style="margin:0 0 8px 0; color:#38bdf8;">AUTH-01 / AUTH-02 Quorum Protocol</h4>
          <p style="margin:0 0 8px 0; font-size:0.85rem; color:#cbd5e1; line-height:1.4;">
            Unilateral AI execution prohibited. Destructive actions, kill switches, and withdrawals require two authorized signing keys.
          </p>
          <div style="font-size:0.8rem; color:#94a3b8;">
            Active Key 1: <strong style="color:#10b981;">Chief Administrator [ONLINE]</strong><br>
            Active Key 2: <strong style="color:#10b981;">Lineal Trustee [ONLINE]</strong>
          </div>
        </div>
        <div style="background:#1e293b; border:1px solid #334155; border-radius:6px; padding:16px;">
          <h4 style="margin:0 0 8px 0; color:#38bdf8;">Risk Dial & Capital Sizing</h4>
          <p style="margin:0 0 8px 0; font-size:0.85rem; color:#cbd5e1; line-height:1.4;">
            Two-Tier Risk Envelope active. Position sizing pegged to conservative Quarter-Kelly.
          </p>
          <div style="font-size:0.8rem; color:#94a3b8;">
            Max Drawdown Ceiling: <strong style="color:#38bdf8;">5.00%</strong> | Current: <strong style="color:#10b981;">-1.85%</strong><br>
            Sizing Factor: <strong style="color:#38bdf8;">Quarter-Kelly (0.25 f*)</strong>
          </div>
        </div>
      </div>
      <div style="background:#1e293b; border:1px solid #ef4444; border-radius:6px; padding:16px; display:flex; justify-content:space-between; align-items:center;">
        <div>
          <strong style="color:#ef4444;">Emergency Kill Switch / Fail-Closed Circuit Breaker</strong>
          <p style="margin:4px 0 0 0; color:#94a3b8; font-size:0.8rem;">Tripping the circuit breaker instantly aborts resting maker orders and halts daemon cycles.</p>
        </div>
        <button onclick="if(confirm('Trip Emergency Circuit Breaker under AUTH-01?')) fetch('/api/v1/operator/emergency-stop', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({actor_id:'Chief Administrator', reason:'Manual Breaker Trip'})}).then(r=>r.json()).then(d=>alert('Breaker Tripped:\\n'+JSON.stringify(d)));" style="background:#ef4444; color:white; border:none; padding:8px 16px; border-radius:4px; font-weight:bold; cursor:pointer;">TRIP BREAKER</button>
      </div>
    </div>
'''

for file_path in [pathlib.Path("backend/app/api/v1/dashboard.html"), pathlib.Path("backend/app/static/dashboard.html")]:
    if not file_path.exists():
        continue
    content = file_path.read_text(encoding="utf-8")

    # 1. Update tab navigation buttons with IDs and switchTab calls
    nav_pattern = re.search(r'<div style="display:flex;\s*gap:10px;\s*margin-bottom:20px;">(.*?)</div>', content, re.DOTALL)
    if nav_pattern:
        new_nav = '''<div style="display:flex; gap:10px; margin-bottom:20px;">
      <button id="tab-btn-1" onclick="switchTab(1)" style="background:#0284c7; color:#ffffff; font-weight:bold; border:none; padding:8px 16px; border-radius:4px; cursor:pointer; font-size:0.85rem;">1. Founder SCMA & Executive Overview</button>
      <button id="tab-btn-2" onclick="switchTab(2)" style="background:#1e293b; color:#94a3b8; border:none; padding:8px 16px; border-radius:4px; cursor:pointer; font-size:0.85rem;">2. Family Lineal Pools & Sub-Ledgers</button>
      <button id="tab-btn-3" onclick="switchTab(3)" style="background:#1e293b; color:#94a3b8; border:none; padding:8px 16px; border-radius:4px; cursor:pointer; font-size:0.85rem;">3. Velocity Radar & Scanner</button>
      <button id="tab-btn-4" onclick="switchTab(4)" style="background:#1e293b; color:#94a3b8; border:none; padding:8px 16px; border-radius:4px; cursor:pointer; font-size:0.85rem;">4. Governance & Dual-Control</button>
    </div>'''
        content = content.replace(nav_pattern.group(0), new_nav, 1)

    # 2. Wrap existing Tab 1 overview content in #tab-panel-1 if not yet wrapped
    if 'id="tab-panel-1"' not in content:
        # Match from the 4 metric cards down through the Active Portfolio Positions table
        overview_match = re.search(
            r'(<div style="display:grid; grid-template-columns:repeat\(4, 1fr\);.*?ACTIVE PORTFOLIO POSITIONS.*?</table>\s*</div>)',
            content,
            re.DOTALL
        )
        if overview_match:
            wrapped_tab1 = f'<div id="tab-panel-1">\n{overview_match.group(1)}\n</div>\n{additional_panels}'
            content = content.replace(overview_match.group(1), wrapped_tab1, 1)

    # 3. Add tab switching JavaScript if not present
    if 'function switchTab' not in content:
        content = content.replace('</body>', tab_markup_and_js + '\n</body>')

    file_path.write_text(content, encoding="utf-8")
    print(f"Tabs wired and panels injected into: {file_path}")

print("Dashboard tab setup complete.")