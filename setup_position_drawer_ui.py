import pathlib
import shutil

position_drawer_html = '''
  <!-- POSITION DETAIL & RISK ENVELOPE DRAWER -->
  <div id="position-drawer" style="position:fixed; top:0; right:-520px; width:480px; height:100vh; background:#0f172a; border-left:2px solid #0284c7; box-shadow:-10px 0 25px rgba(0,0,0,0.7); z-index:10000; transition:right 0.3s ease-in-out; display:flex; flex-direction:column;">
    <div style="display:flex; justify-content:space-between; align-items:center; background:#1e293b; padding:12px 16px; border-bottom:1px solid #334155;">
      <div>
        <strong style="color:#38bdf8; font-size:1rem;">📊 Position Detail & Risk Envelope</strong>
        <small id="pos-drawer-sub" style="display:block; color:#94a3b8; font-size:0.7rem;">Point-in-Time Sizing Telemetry</small>
      </div>
      <button onclick="togglePositionDrawer(false)" style="background:#334155; color:white; border:none; padding:4px 10px; border-radius:4px; cursor:pointer;">✕</button>
    </div>
    <div id="pos-drawer-body" style="padding:16px; overflow-y:auto; flex:1; font-size:0.85rem; color:#e2e8f0;">
      <p style="color:#94a3b8;">Loading position telemetry...</p>
    </div>
  </div>
'''

position_js_functions = '''
    // POSITION INSPECT LOGIC
    function togglePositionDrawer(open = true) {
      const d = document.getElementById("position-drawer");
      if (!d) return;
      d.style.right = open ? "0px" : "-520px";
    }

    async function inspectPosition(contractId) {
      togglePositionDrawer(true);
      const b = document.getElementById("pos-drawer-body");
      if (b) b.innerHTML = '<p style="color:#38bdf8;">Retrieving position telemetry & risk envelope...</p>';

      try {
        const res = await fetch('/api/v1/operator/positions/' + encodeURIComponent(contractId));
        const data = await res.json();
        renderPositionDetail(data);
      } catch (err) {
        if (b) b.innerHTML = '<p style="color:#ef4444;">Error loading position: ' + err + '</p>';
      }
    }

    function renderPositionDetail(data) {
      const b = document.getElementById("pos-drawer-body");
      if (!b) return;
      const risk = data.risk_envelope || {};
      const cards = data.action_cards || [];

      // Register action cards into global registry
      cards.forEach(c => { window._actionCardRegistry[c.action_id] = c; });

      let cardsHtml = cards.map(c => `
        <div style="background:#0f172a; border:1px solid #38bdf8; border-radius:6px; padding:10px; margin-top:10px;">
          <div style="display:flex; justify-content:space-between; align-items:center;">
            <strong style="color:#f8fafc; font-size:0.8rem;">${c.title}</strong>
            <span style="font-size:0.65rem; color:#94a3b8; background:#1e293b; padding:2px 6px; border-radius:3px;">${c.action_type}</span>
          </div>
          <p style="margin:4px 0 8px 0; font-size:0.75rem; color:#cbd5e1;">${c.description}</p>
          <button onclick="executeActionCard('${c.action_id}')" style="background:${c.action_type === 'ORC_INSPECT' ? '#38bdf8' : '#10b981'}; color:#0f172a; border:none; padding:5px 12px; border-radius:4px; font-weight:bold; font-size:0.75rem; cursor:pointer;">${c.action_type === 'ORC_INSPECT' ? 'Launch ORC' : 'Execute Order'}</button>
        </div>
      `).join('');

      b.innerHTML = `
        <div style="background:#1e293b; padding:12px; border-radius:6px; margin-bottom:12px; border:1px solid #334155;">
          <div style="display:flex; justify-content:space-between; align-items:center;">
            <span style="font-weight:bold; color:#38bdf8; font-size:1.05rem;">${data.contract_id}</span>
            <span style="background:#0284c7; color:#fff; padding:2px 8px; border-radius:4px; font-size:0.7rem;">${data.venue}</span>
          </div>
          <p style="margin:6px 0 0 0; color:#94a3b8; font-size:0.8rem;">Member Allocation: <strong style="color:#f8fafc;">${data.member_id}</strong></p>
        </div>

        <div style="background:#1e293b; padding:12px; border-radius:6px; margin-bottom:12px; border:1px solid #334155;">
          <h4 style="margin:0 0 8px 0; color:#38bdf8;">Execution Telemetry</h4>
          <table style="width:100%; font-size:0.8rem; border-collapse:collapse;">
            <tr><td style="color:#94a3b8; padding:3px 0;">Side / Category:</td><td style="color:#10b981; font-weight:bold;">${data.side} (${data.category})</td></tr>
            <tr><td style="color:#94a3b8; padding:3px 0;">Quantity:</td><td style="color:#f8fafc;">${Number(data.quantity).toLocaleString()} contracts</td></tr>
            <tr><td style="color:#94a3b8; padding:3px 0;">VWAP:</td><td style="color:#f8fafc;">${data.vwap_cents}¢</td></tr>
            <tr><td style="color:#94a3b8; padding:3px 0;">Cost Basis:</td><td style="color:#f8fafc;">$${(data.fill_cost_cents / 100).toFixed(2)}</td></tr>
            <tr><td style="color:#94a3b8; padding:3px 0;">Unrealized PnL:</td><td style="color:#10b981; font-weight:bold;">+$0.00</td></tr>
          </table>
        </div>

        <div style="background:#1e293b; padding:12px; border-radius:6px; margin-bottom:12px; border:1px solid #334155;">
          <h4 style="margin:0 0 8px 0; color:#38bdf8;">Risk Envelope & Strategy D Footprint</h4>
          <table style="width:100%; font-size:0.8rem; border-collapse:collapse;">
            <tr><td style="color:#94a3b8; padding:3px 0;">Sizing Standard:</td><td style="color:#f8fafc;">${risk.sizing_rule || 'Quarter-Kelly'}</td></tr>
            <tr><td style="color:#94a3b8; padding:3px 0;">Pool Allocation:</td><td style="color:#38bdf8;">${risk.capital_pool_allocation_pct}% of SCMA</td></tr>
            <tr><td style="color:#94a3b8; padding:3px 0;">Tier-1 Drawdown Headroom:</td><td style="color:#10b981;">${risk.tier1_drawdown_headroom_pct}% remaining</td></tr>
            <tr><td style="color:#94a3b8; padding:3px 0;">Maker Rebate Accrued:</td><td style="color:#f59e0b;">+${risk.maker_rebate_accrued_cents}¢</td></tr>
          </table>
        </div>

        <div style="margin-top:14px;">
          <strong style="color:#f8fafc; font-size:0.85rem;">Operational Action Cards (AUTH-01)</strong>
          ${cardsHtml}
        </div>
      `;
    }
'''

target_files = [
    pathlib.Path("backend/app/api/v1/dashboard.html"),
    pathlib.Path("backend/app/static/dashboard.html")
]

for p in target_files:
    if not p.exists():
        continue

    shutil.copy2(p, p.with_suffix(".before_inspect.bak"))
    content = p.read_text(encoding="utf-8")

    # 1. Update button from alert placeholder to inspectPosition call
    content = content.replace(
        "alert('Position inspect: ' + '${p.contract_id}')",
        "inspectPosition('${p.contract_id}')"
    )

    # 2. Add position drawer HTML before closing script/body
    if 'id="position-drawer"' not in content:
        content = content.replace('<!-- FLOATING COPILOT LAUNCHER BUTTON -->', position_drawer_html + '\n  <!-- FLOATING COPILOT LAUNCHER BUTTON -->')

    # 3. Add JS functions
    if 'function inspectPosition' not in content:
        content = content.replace('// POSITION INSPECT LOGIC', '')
        content = content.replace('</script>', position_js_functions + '\n  </script>')

    p.write_text(content, encoding="utf-8")
    print(f"Patched Inspect drawer into: {p}")

print("Inspect integration complete.")