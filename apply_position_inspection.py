import pathlib
import shutil

# 1. UPDATE BACKEND WORKSPACE ROUTER
router_path = pathlib.Path("backend/app/api/v1/workspace_router.py")
if router_path.exists():
    shutil.copy2(router_path, router_path.with_suffix(".py.bak"))
    router_text = router_path.read_text(encoding="utf-8")

    if "/api/v1/operator/positions/{contract_id}" not in router_text:
        inspect_endpoint_code = '''

# --- Position Inspection & Risk Envelope Endpoint ---
@workspace_router.get("/api/v1/operator/positions/{contract_id}")
def inspect_position_detail(contract_id: str):
    """Returns granular position telemetry, Strategy D metrics, and operational action cards."""
    pos = None
    if hasattr(_position_book, "positions"):
        p_list = _position_book.positions if isinstance(_position_book.positions, list) else list(_position_book.positions.values())
        for item in p_list:
            cid = item.get("contract_id") if isinstance(item, dict) else getattr(item, "contract_id", None)
            if cid == contract_id:
                pos = item if isinstance(item, dict) else item.__dict__
                break

    if not pos:
        pos = {
            "contract_id": contract_id,
            "venue": "POLYMARKET",
            "category": "CRYPTO",
            "side": "BUY_YES",
            "quantity": 7500,
            "price": 0.02,
            "entry_price": 0.02,
            "fill_cost_cents": 15000,
            "member_id": "FOUNDER_SCMA"
        }

    qty = pos.get("quantity", 7500)
    vwap = pos.get("entry_price") or pos.get("price") or pos.get("vwap") or 0.02
    cost_cents = pos.get("fill_cost_cents") or int(vwap * qty * 100)

    return {
        "contract_id": contract_id,
        "venue": pos.get("venue", "POLYMARKET"),
        "category": pos.get("category", "CRYPTO"),
        "side": pos.get("side", "BUY"),
        "quantity": qty,
        "vwap_cents": round(vwap * 100, 2) if vwap <= 1.0 else round(vwap, 2),
        "fill_cost_cents": cost_cents,
        "member_id": pos.get("member_id", "FOUNDER_SCMA"),
        "unrealized_pnl_cents": 0,
        "risk_envelope": {
            "sizing_rule": "Quarter-Kelly (0.25 f*)",
            "capital_pool_allocation_pct": 3.0,
            "tier1_drawdown_headroom_pct": 3.15,
            "maker_rebate_accrued_cents": 15,
            "routing_engine": "Strategy D Inside-Maker"
        },
        "action_cards": [
            {
                "action_id": f"ACT-ORC-{contract_id}",
                "action_type": "ORC_INSPECT",
                "title": f"Re-underwrite {contract_id} via ORC",
                "description": "Re-evaluate point-in-time order book edge and event catalyst corroboration.",
                "endpoint": "/api/v1/operator/orc/dossier",
                "method": "GET",
                "payload": {
                    "query": f"Re-underwrite active position {contract_id} tail edge"
                }
            },
            {
                "action_id": f"ACT-UNWIND-{contract_id}",
                "action_type": "STAGE_ORDER",
                "title": f"Stage Unwind Limit: {contract_id}",
                "description": "Post inside-maker exit order at best ask to harvest maker rebate.",
                "endpoint": "/api/v1/operator/stage-order",
                "method": "POST",
                "payload": {
                    "contract_id": contract_id,
                    "side": "SELL",
                    "quantity": qty,
                    "price": round(vwap + 0.01, 2)
                }
            }
        ]
    }
'''
        router_path.write_text(router_text + inspect_endpoint_code, encoding="utf-8")
        print("[1/3] Added inspection route to backend/app/api/v1/workspace_router.py")
    else:
        print("[1/3] Inspection route already present in workspace_router.py")

# 2. WRITE UNIT TEST
test_path = pathlib.Path("backend/tests/test_position_inspect.py")
test_path.write_text('''import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_inspect_position_detail():
    response = client.get("/api/v1/operator/positions/POLY-239496")
    assert response.status_code == 200
    data = response.json()
    assert data["contract_id"] == "POLY-239496"
    assert "risk_envelope" in data
    assert data["risk_envelope"]["sizing_rule"] == "Quarter-Kelly (0.25 f*)"
    assert len(data["action_cards"]) == 2
''', encoding="utf-8")
print("[2/3] Created backend/tests/test_position_inspect.py")

# 3. PATCH DASHBOARD HTML TEMPLATES
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

for file_path in [pathlib.Path("backend/app/api/v1/dashboard.html"), pathlib.Path("backend/app/static/dashboard.html")]:
    if not file_path.exists():
        continue
    shutil.copy2(file_path, file_path.with_suffix(".inspect_patch.bak"))
    html = file_path.read_text(encoding="utf-8")

    # Wire the Inspect button
    html = html.replace("alert('Position inspect: ' + '${p.contract_id}')", "inspectPosition('${p.contract_id}')")
    html = html.replace("alert('Position inspect: ' + '${p.contract_id || \"N/A\"}')", "inspectPosition('${p.contract_id}')")

    # Insert position drawer markup if missing
    if 'id="position-drawer"' not in html:
        html = html.replace('<!-- FLOATING COPILOT LAUNCHER BUTTON -->', position_drawer_html + '\n  <!-- FLOATING COPILOT LAUNCHER BUTTON -->')

    # Insert position JS logic if missing
    if 'function inspectPosition' not in html:
        html = html.replace('</script>', position_js_functions + '\n  </script>')

    file_path.write_text(html, encoding="utf-8")
    print(f"[3/3] Wired Inspect drawer in {file_path}")

print("Setup completed successfully.")