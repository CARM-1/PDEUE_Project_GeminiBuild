from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from typing import Dict, Any, List
from app.domain.lineage_hierarchy import LineageHierarchyService

lineage_router = APIRouter()
_lineage_service = LineageHierarchyService()

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

        r = (
            f"<tr>"
            f"<td><b>{name}</b></td>"
            f"<td style='font-family: monospace; color: #38bdf8;'>{scma}</td>"
            f"<td>{cash}</td>"
            f"<td><b>{dial}</b></td>"
            f"<td>{len(orders)} resting ({orders_str})</td>"
            f"<td><span style='color: {status_color}; font-weight: bold;'>{status}</span></td>"
            f"<td><div style='display: flex; gap: 6px;'>"
            f"<button class='btn-cancel' onclick=\"cancelOrders({house_id}, '{scma}')\">Cancel Orders</button>"
            f"<button class='btn-freeze' onclick=\"freezeRisk({house_id}, '{scma}')\">Freeze Dial (0%)</button>"
            f"</div></td>"
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

    html = f"""<!DOCTYPE html>
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
    .btn-cancel {{ background: #ef4444; color: #fff; border: none; padding: 4px 8px; border-radius: 4px; cursor: pointer; font-size: 11px; font-weight: bold; }}
    .btn-freeze {{ background: #f59e0b; color: #020617; border: none; padding: 4px 8px; border-radius: 4px; cursor: pointer; font-size: 11px; font-weight: bold; }}
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

  <script>
    async function cancelOrders(houseId, scmaId) {{
      if (!confirm(`Cancel all active resting maker orders for subordinate ${{scmaId}}?`)) return;
      try {{
        const res = await fetch(`/api/v1/lineage/house/${{houseId}}/subordinate/cancel-orders`, {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{ scma_id: scmaId }})
        }});
        const data = await res.json();
        if (res.ok) {{
          alert(`[CIRCUIT BREAKER] Cancelled ${{data.cancelled_orders.length}} open orders for ${{scmaId}}.`);
          window.location.reload();
        }} else {{
          alert(`Action Failed: ${{data.detail || 'Invariant rejection'}}`);
        }}
      }} catch (err) {{
        console.error("Cancel orders error:", err);
      }}
    }}

    async function freezeRisk(houseId, scmaId) {{
      if (!confirm(`Freeze risk dial to 0.0% for subordinate ${{scmaId}}? This excludes them from future Kelly sizing cycles.`)) return;
      try {{
        const res = await fetch(`/api/v1/lineage/house/${{houseId}}/subordinate/freeze-risk`, {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{ scma_id: scmaId }})
        }});
        const data = await res.json();
        if (res.ok) {{
          alert(`[GOVERNOR CLAMP] Subordinate ${{scmaId}} risk frozen to 0.0% (${{data.member_status}}).`);
          window.location.reload();
        }} else {{
          alert(`Action Failed: ${{data.detail || 'Invariant rejection'}}`);
        }}
      }} catch (err) {{
        console.error("Freeze risk error:", err);
      }}
    }}
  </script>
</body>
</html>"""
    return HTMLResponse(content=html)
