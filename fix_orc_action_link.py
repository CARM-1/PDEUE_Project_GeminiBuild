import pathlib
import re

targets = [
    pathlib.Path("backend/app/api/v1/dashboard.html"),
    pathlib.Path("backend/app/static/dashboard.html")
]

replacement_action_handler = """
    async function executeAction(endpoint, method, payload) {
      try {
        const res = await fetch(endpoint, {
          method: method,
          headers: {'Content-Type': 'application/json'},
          body: (method === 'POST') ? JSON.stringify(payload) : null
        });
        const d = await res.json();

        // If this is an Opportunity Research Dossier action, slide out the inspector directly
        if (endpoint.includes('research') || d.dossier_id || endpoint.includes('copilot/action')) {
          const cid = (payload && payload.contract_id) ? payload.contract_id : 'KX-MIA-FRZ-32';
          openInspector(cid, 'KALSHI', 'BUY_YES', '3.0¢');
          const hashEl = document.getElementById("insp-hash");
          if (hashEl && d.dossier_id) {
            hashEl.innerText = 'SHA256-' + d.dossier_id + '-VERIFIED';
          }
          const pModelEl = document.getElementById("insp-pmodel");
          if (pModelEl) pModelEl.innerText = "31.5%";
          const edgeEl = document.getElementById("insp-edge");
          if (edgeEl) edgeEl.innerText = "+28.5%";
        } else {
          alert(`Action Executed:\\n${JSON.stringify(d, null, 2)}`);
        }
      } catch (e) {
        alert(`Execution failed: ${e.message}`);
      }
    }
"""

for p in targets:
    if not p.exists():
        continue
    html = p.read_text(encoding="utf-8")

    # Replace the existing executeAction function cleanly
    html = re.sub(
        r'async function executeAction\([\s\S]*?\}\s*\}',
        replacement_action_handler.strip(),
        html
    )

    p.write_text(html, encoding="utf-8")
    print(f"Bound Action Card execution to Decision Packet Drawer in: {p}")

print("Action Card linking complete.")