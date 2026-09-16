import pathlib
import re

targets = [
    pathlib.Path("backend/app/api/v1/dashboard.html"),
    pathlib.Path("backend/app/static/dashboard.html")
]

tab4_panel = """
    <!-- TAB 4: Governance & Dual-Control Panel -->
    <div id="tab-panel-4" style="display:none; padding-top: 10px;">
      <div style="display:grid; grid-template-columns:1fr 1fr; gap:16px; margin-bottom:20px;">
        <div style="background:#111c2e; border:1px solid #1e293b; border-radius:8px; padding:20px;">
          <div style="color:#64748b; font-size:11px; font-weight:700; text-transform:uppercase;">Signer 1 (Primary / Hat: Chief Admin)</div>
          <div style="color:#38bdf8; font-size:18px; font-weight:700; margin-top:6px;">AUTH-01-FOUNDER</div>
          <div style="color:#94a3b8; font-size:12px; margin-top:4px;">Status: <span style="color:#22c55e;">ONLINE / ACTIVE</span></div>
        </div>
        <div style="background:#111c2e; border:1px solid #1e293b; border-radius:8px; padding:20px;">
          <div style="color:#64748b; font-size:11px; font-weight:700; text-transform:uppercase;">Signer 2 (Lineal Dual-Control)</div>
          <div style="color:#38bdf8; font-size:18px; font-weight:700; margin-top:6px;">AUTH-02-TRUSTEE</div>
          <div style="color:#94a3b8; font-size:12px; margin-top:4px;">Status: <span style="color:#22c55e;">ONLINE / READY</span></div>
        </div>
      </div>

      <div style="background:#111c2e; border:1px solid #1e293b; border-radius:8px; padding:20px; margin-bottom:20px;">
        <div style="color:#38bdf8; font-size:13px; font-weight:700; text-transform:uppercase; margin-bottom:12px;">Governance Consensus Ledger</div>
        <table style="width:100%; border-collapse:collapse; font-size:12px; color:#cbd5e1;">
          <thead>
            <tr style="color:#64748b; border-bottom:1px solid #1e293b; text-align:left;">
              <th style="padding:8px;">DIRECTIVE</th>
              <th style="padding:8px;">OPERATING HAT</th>
              <th style="padding:8px;">SIGNER 1</th>
              <th style="padding:8px;">SIGNER 2</th>
              <th style="padding:8px;">CONSENSUS</th>
            </tr>
          </thead>
          <tbody>
            <tr style="border-bottom:1px solid #1e293b;">
              <td style="padding:10px 8px; color:#38bdf8;">LEDGER_RESERVE_CASH</td>
              <td style="padding:10px 8px;">OPERATOR (Class T)</td>
              <td style="padding:10px 8px; color:#22c55e;">AUTH-01 ✓</td>
              <td style="padding:10px 8px; color:#22c55e;">AUTH-02 ✓</td>
              <td style="padding:10px 8px; color:#22c55e;">ENFORCED</td>
            </tr>
            <tr>
              <td style="padding:10px 8px; color:#38bdf8;">WATERFALL_ALLOC_87_10_3</td>
              <td style="padding:10px 8px;">FIDUCIARY (Class F)</td>
              <td style="padding:10px 8px; color:#22c55e;">AUTH-01 ✓</td>
              <td style="padding:10px 8px; color:#22c55e;">AUTH-02 ✓</td>
              <td style="padding:10px 8px; color:#22c55e;">ENFORCED</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div style="background:#111c2e; border:1px solid #ef4444; border-radius:8px; padding:16px; display:flex; justify-content:space-between; align-items:center;">
        <div>
          <strong style="color:#ef4444;">Emergency Kill Switch / Circuit Breaker</strong>
          <p style="margin:4px 0 0 0; color:#94a3b8; font-size:12px;">Tripping aborts maker orders and halts daemon cycles immediately.</p>
        </div>
        <button onclick="if(confirm('Trip Emergency Circuit Breaker under AUTH-01?')) fetch('/api/v1/operator/emergency-stop', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({actor_id:'Chief Administrator', reason:'Manual Breaker Trip'})}).then(r=>r.json()).then(d=>alert('Breaker Tripped:\\n'+JSON.stringify(d)));" style="background:#ef4444; color:white; border:none; padding:8px 16px; border-radius:4px; font-weight:bold; cursor:pointer;">TRIP BREAKER</button>
      </div>
    </div>
"""

for p in targets:
    if not p.exists():
        continue
    html = p.read_text(encoding="utf-8")

    # 1. Replace or insert the tab-panel-4 container cleanly
    if 'id="tab-panel-4"' in html:
        html = re.sub(r'<div\s+id="tab-panel-4"[\s\S]*?</div>\s*</div>\s*</div>', tab4_panel.strip(), html)
    elif 'id="tab4"' in html:
        html = re.sub(r'<div\s+id="tab4"[\s\S]*?</div>\s*</div>\s*</div>', tab4_panel.replace('tab-panel-4', 'tab4').strip(), html)
    else:
        # Insert immediately before closing script or body
        html = html.replace('</body>', tab4_panel + '\n</body>')

    # 2. Wire Tab 4 button directly to switchTab(4)
    html = re.sub(
        r'<button([^>]*?)>(\s*4\.\s*Governance\s*&\s*Dual-Control\s*)</button>',
        r'<button\1 id="tab-btn-4" onclick="switchTab(4)">\2</button>',
        html
    )

    # 3. Ensure switchTab exposes panel 4 accurately
    switch_fn = """
<script>
function switchTab(idx) {
  for (let i = 1; i <= 4; i++) {
    const btn = document.getElementById("tab-btn-" + i);
    const panel = document.getElementById("tab-panel-" + i) || document.getElementById("tab" + i);
    if (btn) {
      if (i === idx) {
        btn.style.backgroundColor = "#0284c7";
        btn.style.color = "#ffffff";
        btn.style.fontWeight = "bold";
      } else {
        btn.style.backgroundColor = "#1e293b";
        btn.style.color = "#94a3b8";
        btn.style.fontWeight = "normal";
      }
    }
    if (panel) {
      panel.style.display = (i === idx) ? "block" : "none";
    }
  }
}
</script>
"""
    if "function switchTab" not in html:
        html = html.replace('</body>', switch_fn + '\n</body>')

    p.write_text(html, encoding="utf-8")
    print(f"Patched Tab 4 in: {p}")

print("Tab 4 repair ready.")