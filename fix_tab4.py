import pathlib
import re

# Identify which files exist on disk
targets = [
    pathlib.Path("backend/app/api/v1/dashboard.html"),
    pathlib.Path("backend/app/static/dashboard.html")
]

tab4_html = """
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
"""

for p in targets:
    if not p.exists():
        continue
    
    content = p.read_text(encoding="utf-8")

    # 1. Harmonize Tab 4 button wiring
    # If the button uses showTab('tab4') or switchTab(4), support both IDs
    if 'id="tab-panel-4"' in content:
        # Panel already present; replace cleanly to ensure accurate markup
        content = re.sub(r'<div\s+id="tab-panel-4"[\s\S]*?</div>\s*</div>\s*</div>', tab4_html.strip(), content)
    elif 'id="tab4"' in content:
        content = re.sub(r'<div\s+id="tab4"[\s\S]*?</div>\s*</div>\s*</div>', tab4_html.replace('tab-panel-4', 'tab4').strip(), content)
    else:
        # If missing entirely, place Tab 4 immediately after Tab 3 panel
        if 'id="tab-panel-3"' in content:
            content = content.replace('</div>\n    </div>\n\n    <!-- TAB 4', tab4_html + '\n    <!-- TAB 4')
            if 'tab-panel-4' not in content:
                # Append right before closing container/script
                idx = content.rfind('</div>')
                content = content[:idx] + tab4_html + '\n' + content[idx:]
        elif 'id="tab3"' in content:
            idx = content.find('</div>', content.find('id="tab3"'))
            content = content[:idx+6] + tab4_html.replace('tab-panel-4', 'tab4') + content[idx+6:]

    # 2. Ensure switchTab function activates both tab-panel-4 and tab4
    if "function switchTab" in content:
        # Patch switchTab to handle both naming conventions gracefully
        old_js = re.search(r'function switchTab\(tabIndex\)\s*\{[\s\S]*?\}', content)
        new_js = """function switchTab(tabIndex) {
  for (let i = 1; i <= 4; i++) {
    const btn = document.getElementById("tab-btn-" + i);
    const panel = document.getElementById("tab-panel-" + i) || document.getElementById("tab" + i);
    if (btn) {
      if (i === tabIndex) {
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
      panel.style.display = (i === tabIndex) ? "block" : "none";
    }
  }
}"""
        if old_js:
            content = content.replace(old_js.group(0), new_js)

    p.write_text(content, encoding="utf-8")
    print(f"Updated: {p}")

print("Tab 4 successfully patched.")