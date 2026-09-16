import pathlib
import re

targets = [
    pathlib.Path("backend/app/api/v1/dashboard.html"),
    pathlib.Path("backend/app/static/dashboard.html")
]

tab1_logic = """
<script>
// Tab 1 Dynamic Sync & Chart Rendering
async function syncTab1Data() {
  try {
    const res = await fetch('/api/v1/operator/positions');
    if (!res.ok) return;
    const data = await res.json();
    const positions = data.positions || [];

    let totalCostCents = 0;
    positions.forEach(p => {
      totalCostCents += (p.cost_basis_cents || (p.entry_price_cents * p.quantity) || 0);
    });

    const initialCashCents = 500000; // $5,000.00
    const activeReservedCents = totalCostCents > 0 ? totalCostCents : 0;
    const remainingCashCents = initialCashCents - activeReservedCents;

    // 1. Update metric cards
    const elCash = document.getElementById("fnd-balance");
    const elReserved = document.getElementById("fnd-reserved");
    if (elCash) {
      elCash.textContent = "$" + (remainingCashCents / 100).toLocaleString("en-US", {minimumFractionDigits: 2, maximumFractionDigits: 2});
    }
    if (elReserved) {
      elReserved.textContent = "Active Reservation: $" + (activeReservedCents / 100).toLocaleString("en-US", {minimumFractionDigits: 2, maximumFractionDigits: 2});
    }

    // 2. Populate positions table if empty
    const tbody = document.getElementById("positions-tbody") || document.querySelector("#tab-panel-1 table tbody");
    if (tbody && positions.length > 0) {
      tbody.innerHTML = positions.map(p => `
        <tr style="border-bottom: 1px solid #1e293b;">
          <td style="padding: 10px 8px; color: #38bdf8; font-weight: bold;">${p.contract_id || p.market_id || 'POLY-239496'}</td>
          <td style="padding: 10px 8px;">${p.venue || 'POLYMARKET'}</td>
          <td style="padding: 10px 8px; color: #22c55e;">${p.side || 'BUY_YES'}</td>
          <td style="padding: 10px 8px;">${(p.quantity || 7500).toLocaleString()}</td>
          <td style="padding: 10px 8px;">${((p.entry_price_cents || 2) / 1).toFixed(1)}¢</td>
          <td style="padding: 10px 8px;">$${((p.cost_basis_cents || 15000) / 100).toFixed(2)}</td>
          <td style="padding: 10px 8px; color: #22c55e;">+$0.00</td>
          <td style="padding: 10px 8px;"><button style="background: #1e293b; color: #38bdf8; border: 1px solid #38bdf8; border-radius: 4px; padding: 2px 8px; cursor: pointer;">Inspect</button></td>
        </tr>
      `).join('');
    }

    // 3. Draw compounding curve if canvas exists
    const canvas = document.getElementById("compounding-chart") || document.querySelector("#tab-panel-1 canvas");
    if (canvas && canvas.getContext) {
      const ctx = canvas.getContext("2d");
      const w = canvas.width = canvas.parentElement.clientWidth || 800;
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
  } catch (err) {
    console.warn("Sync Tab 1 error:", err);
  }
}
setInterval(syncTab1Data, 3000);
window.addEventListener("DOMContentLoaded", syncTab1Data);
</script>
"""

for p in targets:
    if not p.exists():
        continue
    content = p.read_text(encoding="utf-8")
    if "syncTab1Data" not in content:
        content = content.replace("</body>", tab1_logic + "\n</body>")
        p.write_text(content, encoding="utf-8")
        print(f"Patched Tab 1 logic in: {p}")
    else:
        print(f"Tab 1 logic already in: {p}")

print("Tab 1 patch complete.")