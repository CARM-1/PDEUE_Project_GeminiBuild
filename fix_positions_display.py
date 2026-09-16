import pathlib
import re

resilient_tbody_mapping = '''        tbody.innerHTML = positions.map(p => {
          // Robust property resolution across schemas
          const rawPrice = (p.vwap !== undefined) ? p.vwap : ((p.entry_price !== undefined) ? p.entry_price : (p.price !== undefined ? p.price : 0.02));
          const priceCents = rawPrice <= 1.0 ? (rawPrice * 100).toFixed(1) : Number(rawPrice).toFixed(1);
          
          let costDollars = "0.00";
          if (p.fill_cost_cents !== undefined) {
            costDollars = (p.fill_cost_cents / 100).toFixed(2);
          } else if (p.cost_basis_cents !== undefined) {
            costDollars = (p.cost_basis_cents / 100).toFixed(2);
          } else if (p.cost_cents !== undefined) {
            costDollars = (p.cost_cents / 100).toFixed(2);
          } else {
            costDollars = (Number(rawPrice) * Number(p.quantity || 0)).toFixed(2);
          }

          const sideColor = (p.side && p.side.includes("BUY")) ? "#10b981" : "#ef4444";

          return `
            <tr>
              <td style="font-weight:bold; color:#38bdf8;">${p.contract_id || "N/A"}</td>
              <td>${p.venue || "POLYMARKET"}</td>
              <td style="color:${sideColor}; font-weight:bold;">${p.side || "BUY"}</td>
              <td>${Number(p.quantity || 0).toLocaleString()}</td>
              <td>${priceCents}¢</td>
              <td>$${costDollars}</td>
              <td style="color:#10b981;">+$0.00</td>
              <td><button onclick="alert('Position inspect: ' + '${p.contract_id}')" style="background:#334155; color:#f8fafc; border:none; padding:3px 8px; border-radius:3px; font-size:0.75rem; cursor:pointer;">Inspect</button></td>
            </tr>
          `;
        }).join('');'''

files = [
    pathlib.Path("backend/app/api/v1/dashboard.html"),
    pathlib.Path("backend/app/static/dashboard.html")
]

for p in files:
    if not p.exists():
        continue
    content = p.read_text(encoding="utf-8")
    
    # Replace the existing tbody.innerHTML mapping block
    pattern = re.compile(r'tbody\.innerHTML\s*=\s*positions\.map\(p\s*=>\s*`.*?`\)\.join\([\'"]{2}\);', re.DOTALL)
    if pattern.search(content):
        content = pattern.sub(resilient_tbody_mapping, content)
        p.write_text(content, encoding="utf-8")
        print(f"Patched position formatter in: {p}")
    else:
        print(f"Target pattern not found in: {p}")

print("Update complete.")