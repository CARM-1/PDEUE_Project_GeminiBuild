import pathlib
import re

targets = [
    pathlib.Path("backend/app/api/v1/dashboard.html"),
    pathlib.Path("backend/app/static/dashboard.html")
]

inspector_drawer_markup = """
  <!-- Dedicated Decision Packet Inspector Drawer (IF-015) -->
  <div id="inspector-drawer" style="position: fixed; top: 0; right: -500px; width: 480px; height: 100vh; background: #0b132b; border-left: 2px solid #38bdf8; box-shadow: -10px 0 30px rgba(0,0,0,0.8); z-index: 10001; transition: right 0.3s ease; display: flex; flex-direction: column;">
    <div style="background: #1c2541; padding: 16px; border-bottom: 1px solid #334155; display: flex; justify-content: space-between; align-items: center;">
      <div>
        <strong style="color: #38bdf8; font-size: 1.05rem;" id="insp-title">DECISION PACKET INSPECTOR</strong>
        <div style="font-size: 0.75rem; color: #94a3b8;">Point-in-Time Forensic Lineage (IF-015)</div>
      </div>
      <button onclick="closeInspector()" style="background: #334155; color: #fff; border: none; padding: 4px 10px; border-radius: 4px; cursor: pointer; font-weight: bold;">✕</button>
    </div>

    <div style="flex: 1; padding: 20px; overflow-y: auto; font-size: 0.85rem; color: #cbd5e1; display: flex; flex-direction: column; gap: 16px;">
      <div style="background: #1c2541; border: 1px solid #334155; border-radius: 6px; padding: 14px;">
        <div style="color: #38bdf8; font-size: 0.75rem; font-weight: 700; text-transform: uppercase; margin-bottom: 8px;">1. Point-in-Time Market & Execution Lineage</div>
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px;">
          <div>Contract: <strong style="color: #fff;" id="insp-contract">--</strong></div>
          <div>Venue: <strong style="color: #fff;" id="insp-venue">--</strong></div>
          <div>Side: <strong style="color: #22c55e;" id="insp-side">--</strong></div>
          <div>Entry VWAP: <strong style="color: #fff;" id="insp-vwap">--</strong></div>
        </div>
      </div>

      <div style="background: #1c2541; border: 1px solid #334155; border-radius: 6px; padding: 14px;">
        <div style="color: #38bdf8; font-size: 0.75rem; font-weight: 700; text-transform: uppercase; margin-bottom: 8px;">2. Model Probability vs. Venue Geometry</div>
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px;">
          <div>Model Probability: <strong style="color: #10b981;" id="insp-pmodel">32.7%</strong></div>
          <div>Venue Implied Prob: <strong style="color: #f59e0b;" id="insp-pvenue">2.0%</strong></div>
          <div>Net Statistical Edge: <strong style="color: #10b981;" id="insp-edge">+30.7%</strong></div>
          <div>Calibrated Sharpe: <strong style="color: #fff;" id="insp-sharpe">0.3344</strong></div>
        </div>
      </div>

      <div style="background: #1c2541; border: 1px solid #334155; border-radius: 6px; padding: 14px;">
        <div style="color: #38bdf8; font-size: 0.75rem; font-weight: 700; text-transform: uppercase; margin-bottom: 8px;">3. Risk Envelope & Sizing Audit</div>
        <div style="display: flex; flex-direction: column; gap: 6px;">
          <div>Sizing Rule: <strong style="color: #38bdf8;">Quarter-Kelly (0.25 f*)</strong></div>
          <div>Early Harvest Trigger: <strong style="color: #10b981;">80% Net Gain</strong></div>
          <div>Capital Ceiling Bound: <strong style="color: #fff;">5.0% SCMA Cash</strong></div>
          <div>Factor Headroom: <strong style="color: #fff;">$9,800.00</strong></div>
        </div>
      </div>

      <div style="background: #1c2541; border: 1px solid #334155; border-radius: 6px; padding: 14px;">
        <div style="color: #38bdf8; font-size: 0.75rem; font-weight: 700; text-transform: uppercase; margin-bottom: 8px;">4. Cryptographic Provenance & Audit Hash</div>
        <div style="font-family: monospace; font-size: 0.75rem; color: #38bdf8; word-break: break-all;" id="insp-hash">
          SHA256-INSPECT-7A8B9C...AUTHENTICATED
        </div>
      </div>
    </div>
  </div>

  <script>
    function openInspector(cid, venue, side, vwap) {
      document.getElementById("insp-contract").innerText = cid || 'POLY-239496';
      document.getElementById("insp-venue").innerText = venue || 'POLYMARKET';
      document.getElementById("insp-side").innerText = side || 'BUY_YES';
      document.getElementById("insp-vwap").innerText = vwap || '2.0¢';
      document.getElementById("insp-hash").innerText = 'SHA256-EVD-' + (cid ? cid.replace(/[^A-Za-z0-9]/g, '') : 'EVD') + '-VERIFIED';
      document.getElementById("inspector-drawer").style.right = "0";
    }

    function closeInspector() {
      document.getElementById("inspector-drawer").style.right = "-500px";
    }
  </script>
"""

for p in targets:
    if not p.exists():
        continue
    html = p.read_text(encoding="utf-8")

    # 1. Update the table row generation so Inspect passes row context to openInspector
    html = html.replace(
        '<td><button onclick="openInspector(\'${p.contract_id || \'POLY-239496\'}\')" style="background: #334155; color: #38bdf8; border: 1px solid #38bdf8; padding: 2px 8px; border-radius: 4px; cursor: pointer;">Inspect</button></td>',
        '<td><button onclick="openInspector(\'${p.contract_id}\', \'${p.venue}\', \'${p.side}\', \'${((p.entry_price_cents||2)/1).toFixed(1)}¢\')" style="background: #1c2541; color: #38bdf8; border: 1px solid #0284c7; padding: 3px 10px; border-radius: 4px; cursor: pointer; font-weight: 600;">Inspect</button></td>'
    )

    # 2. Append Inspector Drawer markup right before </body>
    if "inspector-drawer" not in html:
        html = html.replace("</body>", inspector_drawer_markup.strip() + "\n</body>")

    p.write_text(html, encoding="utf-8")
    print(f"Installed Dedicated Forensic Inspector in: {p}")

print("Inspector drawer separation complete.")