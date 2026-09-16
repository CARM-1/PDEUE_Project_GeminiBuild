import pathlib
import re

p = pathlib.Path("backend/app/api/v1/dashboard.html")
if not p.exists():
    print("Target file not found!")
    exit(1)

html = p.read_text(encoding="utf-8")

# 1. Print out the existing tab buttons and switching functions to understand exact wiring
print("=== TAB BUTTONS ===")
for line in html.splitlines():
    if any(k in line for k in ["tab-btn", "showTab", "switchTab", "Governance"]):
        print(" ", line.strip())

# 2. Extract Tab 4 button onclick handler
m_click = re.search(r'<button[^>]*Governance[^>]*onclick=["\']([^"\']+)["\']', html)
click_handler = m_click.group(1) if m_click else "UNKNOWN"
print("\nActive Governance Button onclick:", click_handler)

# 3. Create the canonical Tab 4 panel and ensure it satisfies both `tab4` and `tab-panel-4`
tab4_inner_content = """
  <div style="padding-top: 10px;">
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

# 4. Wrap with both possible IDs so ANY switching implementation shows it
unified_tab4 = f'''
<!-- UNIFIED TAB 4 CONTAINER -->
<div id="tab-panel-4" class="tab-panel tab-content" style="display:none;">
  <div id="tab4" class="tab-content">
    {tab4_inner_content}
  </div>
</div>
'''

# Replace existing tab4 / tab-panel-4 if found, or place right above </body>
if 'id="tab-panel-4"' in html:
    html = re.sub(r'<div\s+id="tab-panel-4"[\s\S]*?</div>\s*</div>\s*</div>\s*</div>', unified_tab4.strip(), html)
elif 'id="tab4"' in html:
    html = re.sub(r'<div\s+id="tab4"[\s\S]*?</div>\s*</div>\s*</div>', unified_tab4.strip(), html)
else:
    html = html.replace("</body>", unified_tab4.strip() + "\n</body>")

# 5. Harmonize tab-switching JS so if showTab or switchTab is invoked, both IDs are set to visible
universal_display_js = """
<script>
// Universal Tab 4 Visibility Harmonizer
(function() {
  const origSwitchTab = window.switchTab;
  window.switchTab = function(idx) {
    if (typeof origSwitchTab === 'function') origSwitchTab(idx);
    const p4 = document.getElementById("tab-panel-4");
    const t4 = document.getElementById("tab4");
    if (idx === 4) {
      if (p4) p4.style.display = "block";
      if (t4) t4.style.display = "block";
    } else {
      if (p4) p4.style.display = "none";
      if (t4) t4.style.display = "none";
    }
  };

  const origShowTab = window.showTab;
  window.showTab = function(tabId, el) {
    if (typeof origShowTab === 'function') origShowTab(tabId, el);
    const p4 = document.getElementById("tab-panel-4");
    const t4 = document.getElementById("tab4");
    if (tabId === 'tab4' || tabId === 'tab-panel-4' || tabId === 4) {
      if (p4) p4.style.display = "block";
      if (t4) t4.style.display = "block";
    } else {
      if (p4) p4.style.display = "none";
      if (t4) t4.style.display = "none";
    }
  };
})();
</script>
"""

if "Universal Tab 4 Visibility Harmonizer" not in html:
    html = html.replace("</body>", universal_display_js.strip() + "\n</body>")

p.write_text(html, encoding="utf-8")

# Mirror changes to static folder as well
static_p = pathlib.Path("backend/app/static/dashboard.html")
if static_p.exists():
    static_p.write_text(html, encoding="utf-8")

print("\nSuccessfully unified Tab 4 containers and wired universal visibility.")