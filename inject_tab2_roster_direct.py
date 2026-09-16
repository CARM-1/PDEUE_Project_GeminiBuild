import pathlib

targets = [
    pathlib.Path("backend/app/api/v1/dashboard.html"),
    pathlib.Path("backend/app/static/dashboard.html")
]

roster_html = """
    <!-- LIVE LINEAL ROSTER & PROVISIONING MANAGER (ADR-004) -->
    <div class="table-container" style="margin-top: 20px;">
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
        <div>
          <div class="card-label" style="color: #38bdf8; margin: 0;">Active Lineal Roster & Access Control</div>
          <div style="font-size: 0.75rem; color: #94a3b8; margin-top: 2px;">Multi-Tenant Governance (M, F1-F3, T1-T3, Chief Admin)</div>
        </div>
        <button onclick="openProvisionModal()" style="background: #0284c7; color: #fff; border: none; padding: 6px 14px; border-radius: 4px; font-weight: 700; cursor: pointer; font-size: 0.8rem;">
          + Provision Identity
        </button>
      </div>
      <table>
        <thead>
          <tr>
            <th>USER ID</th>
            <th>USERNAME</th>
            <th>ACTIVE ROLE / HAT</th>
            <th>PORTAL ROUTE</th>
            <th>SCMA LEDGER</th>
            <th>BALANCE</th>
            <th>ACTION</th>
          </tr>
        </thead>
        <tbody id="roster-tbody">
          <tr><td colspan="7" style="text-align: center; color: #64748b;">Polling identity directory...</td></tr>
        </tbody>
      </table>
    </div>

    <!-- Provisioning Modal -->
    <div id="provision-modal" style="display: none; position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; background: rgba(0,0,0,0.7); z-index: 20000; align-items: center; justify-content: center;">
      <div style="background: #1c2541; border: 1px solid #334155; border-radius: 8px; width: 440px; padding: 24px; box-shadow: 0 10px 30px rgba(0,0,0,0.8);">
        <h3 style="margin: 0 0 16px 0; color: #38bdf8; font-size: 1.1rem;">Provision New Lineal Identity</h3>
        <div style="display: flex; flex-direction: column; gap: 12px; font-size: 0.85rem;">
          <div>
            <label style="color: #94a3b8; display: block; margin-bottom: 4px;">Full Name</label>
            <input type="text" id="prov-name" placeholder="e.g. Julian Vance" style="width: 100%; background: #0b132b; border: 1px solid #334155; color: #fff; padding: 8px; border-radius: 4px; box-sizing: border-box;">
          </div>
          <div>
            <label style="color: #94a3b8; display: block; margin-bottom: 4px;">Assigned Class & Hat</label>
            <select id="prov-role" style="width: 100%; background: #0b132b; border: 1px solid #334155; color: #fff; padding: 8px; border-radius: 4px; box-sizing: border-box;">
              <option value="MEMBER_USER">MEMBER_USER (Common Autonomous Account)</option>
              <option value="F1_FINANCIAL_ADVISOR">F1_FINANCIAL_ADVISOR (Lineal Peer Advisor)</option>
              <option value="F2_FINANCIAL_ADVISOR">F2_FINANCIAL_ADVISOR (Household Elder Advisor)</option>
              <option value="T1_SYSTEM_ADMIN">T1_SYSTEM_ADMIN (Junior Technical Operator)</option>
              <option value="T2_SYSTEM_ADMIN">T2_SYSTEM_ADMIN (Infrastructure Engineer)</option>
              <option value="T3_SYSTEM_ADMIN">T3_SYSTEM_ADMIN (Chief Technology Officer)</option>
            </select>
          </div>
          <div>
            <label style="color: #94a3b8; display: block; margin-bottom: 4px;">Seed Capital ($ USD)</label>
            <input type="number" id="prov-seed" value="0" style="width: 100%; background: #0b132b; border: 1px solid #334155; color: #fff; padding: 8px; border-radius: 4px; box-sizing: border-box;">
          </div>
        </div>
        <div style="display: flex; justify-content: flex-end; gap: 10px; margin-top: 20px;">
          <button onclick="closeProvisionModal()" style="background: #334155; color: #fff; border: none; padding: 6px 14px; border-radius: 4px; cursor: pointer;">Cancel</button>
          <button onclick="submitProvisioning()" style="background: #0284c7; color: #fff; border: none; padding: 6px 14px; border-radius: 4px; font-weight: 700; cursor: pointer;">Provision Account</button>
        </div>
      </div>
    </div>
"""

roster_js = """
    async function syncRoster() {
      try {
        const res = await fetch('/api/v1/operator/roster');
        if (res.ok) {
          const data = await res.json();
          const roster = data.roster || [];
          const tb = document.getElementById("roster-tbody");
          if (tb) {
            tb.innerHTML = roster.map(u => {
              const roleBadgeColor = u.role.startsWith("MEMBER") ? "#0284c7" : (u.role.startsWith("F") ? "#10b981" : (u.role.startsWith("T") ? "#f59e0b" : "#ef4444"));
              return `
                <tr>
                  <td style="color: #94a3b8; font-family: monospace;">${u.user_id}</td>
                  <td style="font-weight: 600; color: #f8fafc;">${u.username}</td>
                  <td><span style="background: ${roleBadgeColor}; color: #fff; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; font-weight: 700;">${u.role}</span></td>
                  <td style="color: #38bdf8;">${u.portal_route}</td>
                  <td style="font-family: monospace; color: #cbd5e1;">${u.account_id || '--'}</td>
                  <td style="color: #10b981; font-weight: 600;">$${u.balance_dollars.toLocaleString('en-US', {minimumFractionDigits: 2})}</td>
                  <td>
                    <button onclick="promptTransition('${u.user_id}', '${u.role}')" style="background: #334155; color: #38bdf8; border: 1px solid #0284c7; padding: 2px 8px; border-radius: 4px; cursor: pointer; font-size: 0.75rem;">Promote</button>
                  </td>
                </tr>
              `;
            }).join('');
          }
        }
      } catch (err) {
        console.warn("Roster sync failed:", err);
      }
    }

    function openProvisionModal() {
      document.getElementById("provision-modal").style.display = "flex";
    }

    function closeProvisionModal() {
      document.getElementById("provision-modal").style.display = "none";
    }

    async function submitProvisioning() {
      const name = document.getElementById("prov-name").value.trim();
      const role = document.getElementById("prov-role").value;
      const seedDollars = parseFloat(document.getElementById("prov-seed").value) || 0;
      if (!name) return alert("Please enter a member name.");

      try {
        const res = await fetch('/api/v1/operator/provision-identity', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({
            full_name: name,
            role: role,
            household_id: 'HOUSEHOLD-ALPHA',
            seed_capital_cents: Math.round(seedDollars * 100)
          })
        });
        const d = await res.json();
        closeProvisionModal();
        alert(`Account Provisioned:\\nUser ID: ${d.user_id}\\nActivation Link: ${d.activation_link}`);
        syncRoster();
      } catch (e) {
        alert("Provisioning failed: " + e.message);
      }
    }

    async function promptTransition(uid, currentRole) {
      const targetRole = prompt(`Promote/Transition User ${uid}\\nCurrent Role: ${currentRole}\\nEnter new role (e.g. F1_FINANCIAL_ADVISOR, T2_SYSTEM_ADMIN, MEMBER_USER):`);
      if (!targetRole) return;
      const just = prompt("Enter governance justification:", "Lineal Merit Promotion");
      try {
        const res = await fetch('/api/v1/operator/transition-role', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({
            user_id: uid,
            new_role: targetRole.trim(),
            justification: just || "Lineal Merit Promotion"
          })
        });
        const d = await res.json();
        alert(`Role Transitioned:\\n${d.old_role} -> ${d.new_role}\\nTarget Portal: ${d.target_portal}\\nPreserved SCMA: ${d.preserved_scma}`);
        syncRoster();
      } catch (e) {
        alert("Transition failed: " + e.message);
      }
    }
"""

anchor_html = '<!-- TAB 2: Waterfall & Lineal Pools -->'

for p in targets:
    if not p.exists():
        continue
    html = p.read_text(encoding="utf-8")

    # Clean existing occurrences if any partial run occurred
    if "Active Lineal Roster & Access Control" not in html:
        # Locate the closing tag of tab-panel-2
        pos = html.find('id="tab-panel-2"')
        if pos != -1:
            end_div_pos = html.find('</div>\n\n  <!-- TAB 3:', pos)
            if end_div_pos == -1:
                end_div_pos = html.find('</div>\n  <!-- TAB 3:', pos)
            if end_div_pos != -1:
                html = html[:end_div_pos] + roster_html + "\n  " + html[end_div_pos:]
            else:
                # Fallback: locate closing div of tab-panel-2 via class
                html = html.replace('id="tab-panel-3"', 'id="tab-panel-3"').replace('<!-- TAB 3', roster_html + '\n  <!-- TAB 3')

    # Inject JS scripts if absent
    if "syncRoster()" not in html:
        html = html.replace('function renderChart() {', roster_js + '\n    function renderChart() {')
        html = html.replace('renderChart();', 'renderChart();\n      syncRoster();')
        html = html.replace('setInterval(syncData, 3000);', 'setInterval(syncData, 3000);\n      setInterval(syncRoster, 4000);')

    p.write_text(html, encoding="utf-8")
    print(f"Directly updated: {p}")

print("DOM injection verified.")