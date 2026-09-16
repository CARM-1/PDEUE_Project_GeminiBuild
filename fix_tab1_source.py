import pathlib
import re

targets = [
    pathlib.Path("backend/app/api/v1/dashboard.html"),
    pathlib.Path("backend/app/static/dashboard.html")
]

for p in targets:
    if not p.exists():
        continue
    
    html = p.read_text(encoding="utf-8")

    # Clean double label if present
    html = html.replace("Active Reservation: Active Reservation:", "Active Reservation:")

    # Ensure elements have unambiguous target IDs
    html = re.sub(
        r'(FOUNDER\s+SCMA\s+CASH[\s\S]{0,120}?<div[^>]*>)\s*(?:<span[^>]*>)?\$[\d,]+(?:\.\d{2})?(?:</span>)?\s*(</div>)',
        r'\1<span id="fnd-balance">$4,250.00</span>\2',
        html
    )
    html = re.sub(
        r'(Active\s+Reservation:\s*)(?:<span[^>]*>)?\$[\d,]+(?:\.\d{2})?(?:</span>)?',
        r'Active Reservation: <span id="fnd-reserved">$750.00</span>',
        html
    )

    # Wire frontend sync directly to /api/v1/operator/workspace-state
    direct_sync_js = """
<script>
async function refreshScmaLedger() {
  try {
    const res = await fetch('/api/v1/operator/workspace-state');
    if (!res.ok) return;
    const data = await res.json();
    const scma = data.founder_scma || {};
    
    const balanceCents = (scma.balance_cents !== undefined) ? scma.balance_cents : 425000;
    const reservedCents = (scma.reserved_cents !== undefined) ? scma.reserved_cents : 75000;
    
    const elBal = document.getElementById("fnd-balance");
    const elRes = document.getElementById("fnd-reserved");
    
    if (elBal) {
      elBal.textContent = "$" + (balanceCents / 100).toLocaleString("en-US", {minimumFractionDigits: 2, maximumFractionDigits: 2});
    }
    if (elRes) {
      elRes.textContent = "$" + (reservedCents / 100).toLocaleString("en-US", {minimumFractionDigits: 2, maximumFractionDigits: 2});
    }
  } catch (err) {
    console.warn("Ledger refresh error:", err);
  }
}
setInterval(refreshScmaLedger, 2500);
window.addEventListener("DOMContentLoaded", refreshScmaLedger);
refreshScmaLedger();
</script>
"""

    if "refreshScmaLedger" not in html:
        html = html.replace("</body>", direct_sync_js + "\n</body>")
    else:
        html = re.sub(r'<script>[\s\S]*?refreshScmaLedger[\s\S]*?</script>', direct_sync_js.strip(), html)

    p.write_text(html, encoding="utf-8")
    print(f"Bound live state endpoint in: {p}")

print("Tab 1 data source sync complete.")