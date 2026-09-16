import pathlib
import re

targets = [
    pathlib.Path("backend/app/api/v1/dashboard.html"),
    pathlib.Path("backend/app/static/dashboard.html")
]

# The canonical PDEUE Portal Hub navigation ribbon
portal_hub_html = """
  <div style="background: #060b19; border-bottom: 1px solid #1e293b; padding: 8px 16px; display: flex; align-items: center; gap: 16px; font-size: 0.8rem; margin: -24px -24px 20px -24px;">
    <strong style="color: #cbd5e1; letter-spacing: 0.05em;">PDEUE PORTAL HUB:</strong>
    <a href="/dashboard" style="background: #0284c7; color: #ffffff; padding: 4px 10px; border-radius: 4px; text-decoration: none; font-weight: 700;">Chief Admin Cockpit</a>
    <a href="/admin/tech" style="color: #94a3b8; padding: 4px 10px; text-decoration: none; font-weight: 600;">Technical Console (Class T)</a>
    <a href="/advisor" style="color: #94a3b8; padding: 4px 10px; text-decoration: none; font-weight: 600;">Financial Advisor Workspace (Class F)</a>
  </div>
"""

for p in targets:
    if not p.exists():
        continue
    html = p.read_text(encoding="utf-8")

    # 1. Insert the top portal ribbon if not already present
    if "PDEUE PORTAL HUB:" not in html:
        html = html.replace('<body>', '<body>\n' + portal_hub_html)

    # 2. Ensure the Chart renders immediately and positions sync without stalling on 'Loading...'
    patch_init = """
    window.addEventListener("DOMContentLoaded", () => {
      setTimeout(renderChart, 50);
      syncData();
      setInterval(syncData, 3000);
    });
    window.addEventListener("load", () => {
      renderChart();
    });
    """
    html = re.sub(r'window\.addEventListener\("DOMContentLoaded"[\s\S]*?setInterval\(syncData,\s*3000\);\s*\}\);', patch_init.strip(), html)

    p.write_text(html, encoding="utf-8")
    print(f"Added Portal Hub ribbon to: {p}")

print("Navigation ribbon applied.")