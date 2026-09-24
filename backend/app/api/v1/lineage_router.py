"""
PDEUE Lineage & House Leader Desk Router (Class H)
Enforces strict Lineal branch confinement, subordinate roster controls,
institutional intervention modals with zero native alerts, and bicameral consensus.
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from typing import Dict, Any, List
from app.domain.lineage_hierarchy import get_lineage_service

lineage_router = APIRouter()
_lineage_service = get_lineage_service()

def _build_member_table_rows(members: List[Dict[str, Any]], house_id: int) -> str:
    rows = []
    for m in members:
        orders = m.get("open_orders", [])
        orders_str = ", ".join(orders) if orders else "None"
        status = m.get("status", "ACTIVE")
        status_color = "#10b981" if status == "ACTIVE" else "#ef4444"
        cash = f"${m.get('cash_cents', 0) / 100.0:,.2f}"
        dial = f"{m.get('risk_dial', 0.0) * 100:.1f}%"
        scma = m.get("scma_id", "")
        name = m.get("name", "")
        order_count = len(orders)
        if _lineage_service._is_sovereign_settlor(m):
            actions = (
                "<span style='background:#1e293b;border:1px solid #38bdf8;color:#38bdf8;"
                "padding:4px 8px;border-radius:4px;font-weight:bold;font-size:11px;'>"
                "🛡️ Sovereign Immune</span>"
            )
        else:
            actions = (
                f"<button class='btn-cancel' onclick=\"openCancelModal('{name}', '{scma}', {order_count}, '{orders_str}')\">Cancel Orders</button>"
                f"<button class='btn-freeze' onclick=\"openFreezeModal('{name}', '{scma}', '{dial}')\">Freeze Dial (0%)</button>"
            )

        r = (
            f"<tr>"
            f"<td><b><a href='/member?scma={scma}' style='color:#38bdf8;text-decoration:underline;'>{name}</a></b></td>"
            f"<td style='font-family: monospace; color: #38bdf8;'>{scma}</td>"
            f"<td>{cash}</td>"
            f"<td><b>{dial}</b></td>"
            f"<td>{order_count} resting ({orders_str})</td>"
            f"<td><span style='color: {status_color}; font-weight: bold;'>{status}</span></td>"
            f"<td><div style='display: flex; gap: 6px;'>{actions}</div></td>"
            f"</tr>"
        )
        rows.append(r)
    return "".join(rows)

@lineage_router.get("/api/v1/lineage/houses")
def get_all_houses():
    return {"houses": _lineage_service.list_all_houses()}

@lineage_router.get("/api/v1/lineage/house/{house_id}")
def get_house_detail(house_id: int):
    if house_id < 1 or house_id > 12:
        raise HTTPException(status_code=400, detail="House ID must be between 1 and 12.")
    return _lineage_service.get_house_summary(house_id)

@lineage_router.post("/api/v1/lineage/house/{house_id}/subordinate/cancel-orders")
def cancel_subordinate_orders(house_id: int, payload: Dict[str, Any]):
    scma_id = payload.get("scma_id")
    if not scma_id:
        raise HTTPException(status_code=400, detail="Missing scma_id in payload.")
    try:
        return _lineage_service.cancel_subordinate_orders(house_id=house_id, scma_id=scma_id)
    except ValueError as err:
        raise HTTPException(status_code=404, detail=str(err))

@lineage_router.post("/api/v1/lineage/house/{house_id}/subordinate/freeze-risk")
def freeze_subordinate_risk(house_id: int, payload: Dict[str, Any]):
    scma_id = payload.get("scma_id")
    if not scma_id:
        raise HTTPException(status_code=400, detail="Missing scma_id in payload.")
    try:
        return _lineage_service.freeze_subordinate_risk(house_id=house_id, scma_id=scma_id)
    except ValueError as err:
        raise HTTPException(status_code=404, detail=str(err))

@lineage_router.post("/api/v1/lineage/house/{house_id}/freeze")
def freeze_house(house_id: int):
    try:
        return _lineage_service.freeze_house(house_id)
    except ValueError as err:
        raise HTTPException(status_code=404, detail=str(err))

@lineage_router.post("/api/v1/lineage/house/{house_id}/restore")
def restore_house(house_id: int):
    try:
        return _lineage_service.restore_house(house_id)
    except ValueError as err:
        raise HTTPException(status_code=404, detail=str(err))

@lineage_router.post("/api/v1/lineage/house/{house_id}/subordinate/restore-risk")
def restore_subordinate_risk(house_id: int, payload: Dict[str, Any]):
    scma_id = payload.get("scma_id")
    target_risk_dial = payload.get("target_risk_dial")
    if not scma_id or target_risk_dial is None:
        raise HTTPException(status_code=400, detail="Missing scma_id or target_risk_dial in payload.")
    try:
        return _lineage_service.restore_subordinate_risk(
            house_id, scma_id, float(target_risk_dial)
        )
    except (TypeError, ValueError) as err:
        raise HTTPException(status_code=400, detail=str(err))

@lineage_router.post("/api/v1/lineage/governance/propose")
def evaluate_proposal(payload: Dict[str, Any]):
    votes = payload.get("affirmative_house_ids", [])
    return _lineage_service.evaluate_bicameral_proposal(votes)

@lineage_router.get("/lineage/house", response_class=HTMLResponse)
@lineage_router.get("/lineage/house/{house_id}", response_class=HTMLResponse)
def get_house_leader_portal(house_id: int = 1):
    if house_id < 1 or house_id > 12:
        house_id = 1
    house = _lineage_service.get_house_summary(house_id)
    member_rows = _build_member_table_rows(house["members"], house["house_id"])

    return HTMLResponse(content=f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>PDEUE House Leader Desk - {house['lineage_code']}</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
    body {{ background: #0b132b; color: #f8fafc; padding: 20px; }}
    .class-h-banner {{ background: #020617; border: 1px solid #334155; border-radius: 8px; padding: 10px 16px; margin-bottom: 20px; display: flex; justify-content: space-between; align-items: center; }}
    .class-badge {{ background: #1e293b; color: #a855f7; padding: 4px 10px; border-radius: 4px; font-weight: bold; font-size: 12px; border: 1px solid #a855f7; }}
    .grid-4 {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 20px; }}
    .card {{ background: #111c44; border: 1px solid #1e293b; border-radius: 8px; padding: 16px; }}
    .card-title {{ font-size: 11px; font-weight: bold; color: #94a3b8; text-transform: uppercase; margin-bottom: 6px; }}
    .card-value {{ font-size: 22px; font-weight: bold; margin-bottom: 4px; }}
    .card-sub {{ font-size: 12px; color: #94a3b8; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 12px; }}
    th {{ border-bottom: 1px solid #334155; text-align: left; padding: 10px 8px; color: #94a3b8; font-size: 12px; }}
    td {{ padding: 10px 8px; border-bottom: 1px solid #1e293b; font-size: 13px; }}
    .btn-cancel {{ background: #ef4444; color: #fff; border: 1px solid #f87171; padding: 5px 10px; border-radius: 4px; cursor: pointer; font-size: 11px; font-weight: bold; }}
    .btn-freeze {{ background: #f59e0b; color: #020617; border: 1px solid #fbbf24; padding: 5px 10px; border-radius: 4px; cursor: pointer; font-size: 11px; font-weight: bold; }}
    .modal-backdrop {{ display: none; position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; background: rgba(2, 6, 23, 0.85); backdrop-filter: blur(4px); z-index: 20000; align-items: center; justify-content: center; }}
    .modal-box {{ background: #111c44; border-radius: 10px; width: 540px; max-width: 90vw; padding: 24px; box-shadow: 0 16px 40px rgba(0, 0, 0, 0.7); animation: modalIn 0.2s ease-out; }}
    @keyframes modalIn {{ from {{ opacity: 0; transform: scale(0.96); }} to {{ opacity: 1; transform: scale(1); }} }}
  </style>
</head>
<body>

  <div class="class-h-banner">
    <div style="display: flex; align-items: center; gap: 12px;">
      <span class="class-badge">CLASS H SOVEREIGN DESK</span>
      <span style="font-weight: bold; color: #38bdf8;">{house['lineage_code']} &mdash; {house['name']}</span>
    </div>
    <span style="color: #94a3b8; font-size: 12px;">Leader: <b style="color: #f8fafc;">{house['leader_name']}</b></span>
  </div>

  <div class="grid-4">
    <div class="card">
      <div class="card-title">Aggregated House Capital</div>
      <div class="card-value" style="color: #4ade80;">{house['total_cash_formatted']}</div>
      <div class="card-sub">{house['member_count']} Subordinate Accounts</div>
    </div>
    <div class="card">
      <div class="card-title">Average Risk Dial</div>
      <div class="card-value" style="color: #38bdf8;">{house['average_risk_dial_pct']}%</div>
      <div class="card-sub">Quarter-Kelly Line Limit</div>
    </div>
    <div class="card">
      <div class="card-title">Bicameral Senate Seat</div>
      <div class="card-value" style="color: #a855f7;">Active Seat</div>
      <div class="card-sub">1 of 12 Sovereign Houses</div>
    </div>
    <div class="card">
      <div class="card-title">Oversight Status</div>
      <div class="card-value" style="color: #10b981;">COGNIZANT</div>
      <div class="card-sub">Local Branch Circuit Breaker Active</div>
    </div>
  </div>

  <div class="card">
    <div class="card-title" style="color: #38bdf8; margin-bottom: 8px;">Subordinate Member Accounts &amp; Lineal Controls</div>
    <table>
      <thead>
        <tr>
          <th>SUBORDINATE NAME</th>
          <th>SCMA IDENTIFIER</th>
          <th>CASH BALANCE</th>
          <th>RISK DIAL</th>
          <th>OPEN MAKER ORDERS</th>
          <th>STATUS</th>
          <th>LINEAL INTERVENTION ACTIONS</th>
        </tr>
      </thead>
      <tbody>
        {member_rows}
      </tbody>
    </table>
  </div>

  <!-- CANCEL ORDERS MODAL -->
  <div id="cancel-modal" class="modal-backdrop">
    <div class="modal-box" style="border: 1px solid #ef4444;">
      <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #1e293b; padding-bottom: 12px; margin-bottom: 16px;">
        <div style="display: flex; align-items: center; gap: 8px;">
          <span style="background: #ef4444; color: #fff; font-size: 11px; font-weight: bold; padding: 3px 8px; border-radius: 4px;">CIRCUIT BREAKER</span>
          <strong style="color: #f87171; font-size: 15px;">CANCEL RESTING MAKER ORDERS</strong>
        </div>
        <button onclick="closeModals()" style="background: transparent; border: none; color: #94a3b8; font-size: 18px; cursor: pointer;">✕</button>
      </div>

      <div style="background: #0b132b; border: 1px solid #1e293b; border-radius: 6px; padding: 12px; margin-bottom: 14px;">
        <div style="font-size: 12px; color: #94a3b8; margin-bottom: 4px;">Target Subordinate</div>
        <div style="font-size: 15px; font-weight: bold; color: #f8fafc;" id="cancel-subordinate-name">--</div>
        <div style="font-family: monospace; font-size: 12px; color: #38bdf8; margin-top: 2px;" id="cancel-subordinate-scma">--</div>
      </div>

      <div style="background: rgba(239, 68, 68, 0.08); border: 1px solid rgba(239, 68, 68, 0.3); border-radius: 6px; padding: 12px; margin-bottom: 16px;">
        <div style="font-size: 12px; color: #fca5a5; line-height: 1.4;">
          This action will immediately revoke all <b>resting inside-maker orders</b> (<span id="cancel-orders-detail">None</span>) on venue books for this subordinate and release committed margin back into available cash.
        </div>
      </div>

      <div id="cancel-actions" style="display: flex; justify-content: flex-end; gap: 10px;">
        <button onclick="closeModals()" style="background: #334155; color: #cbd5e1; border: none; padding: 8px 16px; border-radius: 6px; cursor: pointer; font-weight: bold; font-size: 13px;">Dismiss</button>
        <button id="cancel-confirm-btn" onclick="executeCancelOrders()" style="background: #ef4444; color: #ffffff; border: 1px solid #f87171; padding: 8px 18px; border-radius: 6px; cursor: pointer; font-weight: bold; font-size: 13px;">Confirm Order Revocation</button>
      </div>

      <div id="cancel-receipt" style="display: none; background: rgba(16, 185, 129, 0.1); border: 1px solid #10b981; border-radius: 6px; padding: 12px; margin-top: 12px;">
        <div style="color: #10b981; font-weight: bold; font-size: 13px;">✓ Orders Revoked &amp; Margin Restored</div>
        <div id="cancel-receipt-text" style="font-size: 12px; color: #cbd5e1; margin-top: 4px;"></div>
      </div>
    </div>
  </div>

  <!-- FREEZE RISK MODAL -->
  <div id="freeze-modal" class="modal-backdrop">
    <div class="modal-box" style="border: 1px solid #f59e0b;">
      <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #1e293b; padding-bottom: 12px; margin-bottom: 16px;">
        <div style="display: flex; align-items: center; gap: 8px;">
          <span style="background: #f59e0b; color: #020617; font-size: 11px; font-weight: bold; padding: 3px 8px; border-radius: 4px;">GOVERNOR CLAMP</span>
          <strong style="color: #fbbf24; font-size: 15px;">FREEZE SUBORDINATE RISK DIAL</strong>
        </div>
        <button onclick="closeModals()" style="background: transparent; border: none; color: #94a3b8; font-size: 18px; cursor: pointer;">✕</button>
      </div>

      <div style="background: #0b132b; border: 1px solid #1e293b; border-radius: 6px; padding: 12px; margin-bottom: 14px;">
        <div style="font-size: 12px; color: #94a3b8; margin-bottom: 4px;">Target Subordinate</div>
        <div style="font-size: 15px; font-weight: bold; color: #f8fafc;" id="freeze-subordinate-name">--</div>
        <div style="font-family: monospace; font-size: 12px; color: #38bdf8; margin-top: 2px;" id="freeze-subordinate-scma">--</div>
      </div>

      <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 16px;">
        <div style="background: #0f172a; padding: 10px; border-radius: 6px; border: 1px solid #334155;">
          <div style="font-size: 11px; color: #94a3b8;">Current Risk Dial</div>
          <div id="freeze-current-dial" style="font-size: 16px; font-weight: bold; color: #38bdf8; margin-top: 2px;">--</div>
        </div>
        <div style="background: #0f172a; padding: 10px; border-radius: 6px; border: 1px solid #f59e0b;">
          <div style="font-size: 11px; color: #f59e0b; font-weight: bold;">Clamped Risk Dial</div>
          <div style="font-size: 16px; font-weight: bold; color: #fbbf24; margin-top: 2px;">0.0% (Exclusion)</div>
        </div>
      </div>

      <div style="background: rgba(245, 158, 11, 0.08); border: 1px solid rgba(245, 158, 11, 0.3); border-radius: 6px; padding: 12px; margin-bottom: 16px;">
        <div style="font-size: 12px; color: #fde68a; line-height: 1.4;">
          Clamping risk to <b>0.0%</b> excludes this subordinate account from subsequent Quarter-Kelly dispatch batches until un-clamped by the House Leader.
        </div>
      </div>

      <div id="freeze-actions" style="display: flex; justify-content: flex-end; gap: 10px;">
        <button onclick="closeModals()" style="background: #334155; color: #cbd5e1; border: none; padding: 8px 16px; border-radius: 6px; cursor: pointer; font-weight: bold; font-size: 13px;">Dismiss</button>
        <button id="freeze-confirm-btn" onclick="executeFreezeRisk()" style="background: #f59e0b; color: #020617; border: 1px solid #fbbf24; padding: 8px 18px; border-radius: 6px; cursor: pointer; font-weight: bold; font-size: 13px;">Apply Governor Clamp</button>
      </div>

      <div id="freeze-receipt" style="display: none; background: rgba(16, 185, 129, 0.1); border: 1px solid #10b981; border-radius: 6px; padding: 12px; margin-top: 12px;">
        <div style="color: #10b981; font-weight: bold; font-size: 13px;">✓ Subordinate Risk Clamped to 0.0%</div>
        <div id="freeze-receipt-text" style="font-size: 12px; color: #cbd5e1; margin-top: 4px;"></div>
      </div>
    </div>
  </div>

  <script>
    const currentHouseId = {house['house_id']};
    let activeTarget = null;

    function openCancelModal(name, scma, count, ordersStr) {{
      activeTarget = {{ name, scma }};
      document.getElementById('cancel-subordinate-name').textContent = name;
      document.getElementById('cancel-subordinate-scma').textContent = scma;
      document.getElementById('cancel-orders-detail').textContent = count > 0 ? `${{count}} resting (${{ordersStr}})` : '0 resting orders';
      document.getElementById('cancel-receipt').style.display = 'none';
      document.getElementById('cancel-actions').style.display = 'flex';
      document.getElementById('cancel-modal').style.display = 'flex';
    }}

    function openFreezeModal(name, scma, dial) {{
      activeTarget = {{ name, scma }};
      document.getElementById('freeze-subordinate-name').textContent = name;
      document.getElementById('freeze-subordinate-scma').textContent = scma;
      document.getElementById('freeze-current-dial').textContent = dial;
      document.getElementById('freeze-receipt').style.display = 'none';
      document.getElementById('freeze-actions').style.display = 'flex';
      document.getElementById('freeze-modal').style.display = 'flex';
    }}

    function closeModals() {{
      document.getElementById('cancel-modal').style.display = 'none';
      document.getElementById('freeze-modal').style.display = 'none';
      activeTarget = null;
    }}

    async function executeCancelOrders() {{
      if (!activeTarget) return;
      const btn = document.getElementById('cancel-confirm-btn');
      btn.textContent = 'Revoking...';
      btn.disabled = true;

      try {{
        const res = await fetch(`/api/v1/lineage/house/${{currentHouseId}}/subordinate/cancel-orders`, {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{ scma_id: activeTarget.scma }})
        }});
        const data = await res.json();
        if (res.ok) {{
          document.getElementById('cancel-receipt-text').innerHTML = `
            Cancelled <b>${{data.cancelled_orders.length}}</b> active orders for <b>${{activeTarget.scma}}</b>.<br>
            Ledger Audit Logged: <span style="color:#38bdf8; font-family:monospace;">${{data.timestamp}}</span>
          `;
          document.getElementById('cancel-receipt').style.display = 'block';
          document.getElementById('cancel-actions').style.display = 'none';
          setTimeout(() => window.location.reload(), 1200);
        }} else {{
          document.getElementById('cancel-receipt-text').innerHTML = `<span style="color:#ef4444;">Revocation Rejected: ${{data.detail || 'Invariant error'}}</span>`;
          document.getElementById('cancel-receipt').style.display = 'block';
        }}
      }} catch (err) {{
        console.error("Cancel orders failed:", err);
      }} finally {{
        btn.textContent = 'Confirm Order Revocation';
        btn.disabled = false;
      }}
    }}

    async function executeFreezeRisk() {{
      if (!activeTarget) return;
      const btn = document.getElementById('freeze-confirm-btn');
      btn.textContent = 'Applying Clamp...';
      btn.disabled = true;

      try {{
        const res = await fetch(`/api/v1/lineage/house/${{currentHouseId}}/subordinate/freeze-risk`, {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{ scma_id: activeTarget.scma }})
        }});
        const data = await res.json();
        if (res.ok) {{
          document.getElementById('freeze-receipt-text').innerHTML = `
            Status: <b style="color:#fbbf24;">${{data.member_status}}</b> | Dial: <b>0.0%</b><br>
            Governor Lock Logged: <span style="color:#38bdf8; font-family:monospace;">${{data.timestamp}}</span>
          `;
          document.getElementById('freeze-receipt').style.display = 'block';
          document.getElementById('freeze-actions').style.display = 'none';
          setTimeout(() => window.location.reload(), 1200);
        }} else {{
          document.getElementById('freeze-receipt-text').innerHTML = `<span style="color:#ef4444;">Freeze Rejected: ${{data.detail || 'Invariant error'}}</span>`;
          document.getElementById('freeze-receipt').style.display = 'block';
        }}
      }} catch (err) {{
        console.error("Freeze risk failed:", err);
      }} finally {{
        btn.textContent = 'Apply Governor Clamp';
        btn.disabled = false;
      }}
    }}
  </script>
</body>
</html>""")


@lineage_router.get("/api/v1/lineage/governance/proposals")
def get_governance_proposals():
    return {"proposals": _lineage_service.list_proposals()}

@lineage_router.post("/api/v1/lineage/governance/petition")
def submit_petition(payload: Dict[str, Any]):
    return _lineage_service.submit_house_petition(
        title=payload.get("title", "Untitled Petition"),
        description=payload.get("description", ""),
        target_house_id=payload.get("target_house_id", 1),
        amount_cents=payload.get("amount_cents", 0),
        affirmative_house_ids=payload.get("affirmative_house_ids", [])
    )

@lineage_router.post("/api/v1/lineage/governance/adjudicate")
def adjudicate_governance_proposal(payload: Dict[str, Any]):
    proposal_id = payload.get("proposal_id")
    action = payload.get("action")
    caller_scma = payload.get("caller_scma", "SCMA-FOUNDER_-C8575D7E")
    if not proposal_id or not action:
        raise HTTPException(status_code=400, detail="Missing proposal_id or action.")
    try:
        return _lineage_service.adjudicate_proposal(proposal_id=proposal_id, action=action, caller_scma=caller_scma)
    except PermissionError as pe:
        raise HTTPException(status_code=403, detail=str(pe))
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
