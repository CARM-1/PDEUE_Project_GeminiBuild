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

    # 1. Give explicit IDs to the SCMA Cash balance and Active Reservation labels if they lack them
    # Match the $5,000.00 element under FOUNDER SCMA CASH
    html = re.sub(
        r'(FOUNDER\s+SCMA\s+CASH[\s\S]{0,100}?<div[^>]*>)\s*\$5,000(?:\.00)?\s*(</div>)',
        r'\1<span id="fnd-balance">$5,000.00</span>\2',
        html,
        count=1
    )
    # Match the Active Reservation: $0.00 element
    html = re.sub(
        r'(Active\s+Reservation:\s*)\$0(?:\.00)?',
        r'Active Reservation: <span id="fnd-reserved">$0.00</span>',
        html,
        count=1
    )

    # 2. Inject high-precision card update script into syncTab1Data
    card_update_js = """
    // Direct DOM binding for Cash & Reservation
    const reservedSum = positions.reduce((acc, p) => acc + (p.cost_basis_cents || 15000), 0) / 100;
    const initialCash = 5000.00;
    const cashRemaining = initialCash - reservedSum;

    const cashSpan = document.getElementById("fnd-balance");
    const reservedSpan = document.getElementById("fnd-reserved");

    if (cashSpan) {
      cashSpan.textContent = "$" + cashRemaining.toLocaleString("en-US", {minimumFractionDigits: 2, maximumFractionDigits: 2});
    }
    if (reservedSpan) {
      reservedSpan.textContent = "$" + reservedSum.toLocaleString("en-US", {minimumFractionDigits: 2, maximumFractionDigits: 2});
    }
"""

    if "Direct DOM binding for Cash & Reservation" not in html:
        # Place directly inside the syncTab1Data try block
        html = html.replace(
            "const initialCashCents = 500000;",
            card_update_js + "\n    const initialCashCents = 500000;"
        )

    p.write_text(html, encoding="utf-8")
    print(f"Patched card IDs and live math in: {p}")

print("Tab 1 card patch applied.")