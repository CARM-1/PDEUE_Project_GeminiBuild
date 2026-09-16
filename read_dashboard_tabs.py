import pathlib
import re

p = pathlib.Path("backend/app/api/v1/dashboard.html")
if not p.exists():
    p = pathlib.Path("backend/app/static/dashboard.html")

html = p.read_text(encoding="utf-8")

print(f"--- ACTIVE FILE: {p} ---")

# 1. Print all tab buttons
print("\n[TAB BUTTONS]")
for line in html.splitlines():
    if "tab-btn" in line or "Governance" in line or "Founder SCMA" in line:
        print("  ", line.strip())

# 2. Print all tab container div declarations
print("\n[TAB CONTAINERS]")
for m in re.finditer(r'<div[^>]+id=[\"\'](tab[^\"]*)[\"\'][^>]*>', html):
    print("  ", m.group(0))

# 3. Print the tab switching functions
print("\n[JAVASCRIPT FUNCTIONS]")
for fn in ["showTab", "switchTab"]:
    m_fn = re.search(r'function\s+' + fn + r'[\s\S]*?\{[\s\S]*?\n\}', html)
    if m_fn:
        print(f"--- {fn} ---")
        print(m_fn.group(0))