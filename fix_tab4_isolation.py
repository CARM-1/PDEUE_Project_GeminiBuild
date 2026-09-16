import pathlib
import re

p = pathlib.Path("backend/app/api/v1/dashboard.html")
html = p.read_text(encoding="utf-8")

# 1. Clean the malformed duplicate attributes on button 4
html = re.sub(
    r'<button[^>]*?4\.\s*Governance\s*&\s*Dual-Control\s*</button>',
    '<button id="tab-btn-4" class="tab-btn" onclick="switchTab(4)">4. Governance & Dual-Control</button>',
    html
)

# 2. Extract Tab 4 panel and remove any nested copies
html = re.sub(r'<!--\s*TAB 4:[\s\S]*?(?=<!--\s*TAB|<div id="global-copilot|<script|$)', '', html)

# Canonical, independent Tab 4 markup
canonical_tab4 = """
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

# 3. Insert tab-panel-4 cleanly as a sibling immediately after tab-panel-3 closing tag
idx_panel3 = html.find('id="tab-panel-3"')
if idx_panel3 != -1:
    # Find the closing div of tab-panel-3
    end_p3 = html.find('</div>\n    </div>', idx_panel3)
    if end_p3 != -1:
        insert_pt = end_p3 + len('</div>\n    </div>')
        html = html[:insert_pt] + "\n" + canonical_tab4 + html[insert_pt:]
    else:
        # Fallback to appending right before the global copilot container or closing body
        idx_copilot = html.find('<div id="global-copilot')
        if idx_copilot != -1:
            html = html[:idx_copilot] + canonical_tab4 + "\n" + html[idx_copilot:]
        else:
            html = html.replace('</body>', canonical_tab4 + '\n</body>')
else:
    html = html.replace('</body>', canonical_tab4 + '\n</body>')

# 4. Enforce clean switchTab function that unhides tab-panel-4
clean_switch = """
function switchTab(idx) {
  for (let i = 1; i <= 4; i++) {
    const btn = document.getElementById("tab-btn-" + i);
    const panel = document.getElementById("tab-panel-" + i);
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
"""
html = re.sub(r'function switchTab\(idx\)[\s\S]*?\}\s*\}', clean_switch.strip(), html)

p.write_text(html, encoding="utf-8")

# Mirror cleanly to static file
static_p = pathlib.Path("backend/app/static/dashboard.html")
if static_p.exists():
    static_p.write_text(html, encoding="utf-8")

print("Tab 4 un-nested, button sanitized, and container wired cleanly.")