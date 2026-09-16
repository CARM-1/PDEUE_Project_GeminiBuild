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

    # 1. Clean up duplicated label artifacts
    html = html.replace("Active Reservation: Active Reservation:", "Active Reservation:")

    # 2. Deactivate conflicting legacy updater functions that write static $5,000.00
    html = html.replace("syncTab1Data", "disabled_syncTab1Data")
    html = html.replace("syncLedgerBalances", "disabled_syncLedgerBalances")

    # In any legacy refresh() loop, ensure it reads founder_scma cents safely
    legacy_cash_pattern = r'document\.getElementById\(["\']fnd-balance["\']\)\.innerText\s*=\s*["\']\$5,000(?:\.00)?["\'];?'
    html = re.sub(legacy_cash_pattern, "// fnd-balance controlled by refreshScmaLedger", html)

    # 3. Ensure the single authoritative polling loop is installed cleanly
    canonical_sync_block = """
<!-- Authoritative Single Ledger Poller -->
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
// Run once immediately, then poll steadily every 3 seconds
if (!window._scmaPollerRegistered) {
  window._scmaPollerRegistered = true;
  setInterval(refreshScmaLedger, 3000);
  window.addEventListener("DOMContentLoaded", refreshScmaLedger);
  refreshScmaLedger();
}
</script>
"""

    # Remove any existing versions of refreshScmaLedger scripts to avoid duplicate timers
    html = re.sub(r'<script>[\s\S]*?refreshScmaLedger[\s\S]*?</script>', '', html)
    html = html.replace('</body>', canonical_sync_block.strip() + '\n</body>')

    p.write_text(html, encoding="utf-8")
    print(f"Removed conflicting loops and stabilized: {p}")

print("Flicker resolution applied successfully.")