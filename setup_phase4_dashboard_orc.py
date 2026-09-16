import pathlib
import re

for p in [pathlib.Path("backend/app/api/v1/dashboard.html"), pathlib.Path("backend/app/static/dashboard.html")]:
    if not p.exists():
        continue
    html = p.read_text(encoding="utf-8")

    orc_drawer_html = '''
    <!-- Opportunity Research Center (ORC) Slide-out Drawer -->
    <div id="orc-drawer" style="position:fixed; top:0; right:-520px; width:480px; height:100vh; background:#0f172a; border-left:2px solid #38bdf8; box-shadow:-10px 0 25px rgba(0,0,0,0.7); z-index:10000; transition:right 0.3s ease-in-out; display:flex; flex-direction:column;">
      <div style="display:flex; justify-content:space-between; align-items:center; background:#1e293b; padding:12px 16px; border-bottom:1px solid #334155;">
        <div>
          <strong style="color:#38bdf8; font-size:1rem;">&#129517; Opportunity Research Center (ORC)</strong>
          <small style="display:block; color:#94a3b8; font-size:0.7rem;">Point-in-Time Hypothesis & Edge Evaluation</small>
        </div>
        <button onclick="toggleORC(false)" style="background:#334155; color:white; border:none; padding:4px 10px; border-radius:4px; cursor:pointer;">&#10005;</button>
      </div>
      <div id="orc-body" style="padding:16px; overflow-y:auto; flex:1; font-size:0.85rem; color:#e2e8f0;">
        <p style="color:#94a3b8;">No dossier currently loaded. Launch research from AI Copilot queries.</p>
      </div>
    </div>
    '''
    if 'id="orc-drawer"' not in html:
        html = html.replace('</body>', orc_drawer_html + '\n</body>')

    js_helpers = '''
    function clearChat() {
      const log = document.getElementById("chat-log");
      if (log) log.innerHTML = '<p style="color:#94a3b8; margin-top:0;">Copilot active. State changes generate Action Cards requiring explicit operator click.</p>';
    }

    function toggleCopilot(shouldClear = false) {
      const d = document.getElementById("copilot-drawer");
      if (!d) return;
      if (d.style.right === "25px") {
        d.style.right = "-430px";
        if (shouldClear) clearChat();
      } else {
        d.style.right = "25px";
      }
    }

    function toggleORC(open = true) {
      const d = document.getElementById("orc-drawer");
      if (!d) return;
      d.style.right = open ? "0px" : "-520px";
    }

    async function launchORC(queryText) {
      toggleORC(true);
      const b = document.getElementById("orc-body");
      if (b) b.innerHTML = '<p style="color:#38bdf8;">Evaluating hypothesis against point-in-time order books...</p>';
      try {
        const res = await fetch('/api/v1/operator/orc/dossier?query=' + encodeURIComponent(queryText));
        const d = await res.json();
        renderORCDossier(d);
      } catch (e) {
        if (b) b.innerHTML = '<p style="color:#ef4444;">Error fetching ORC dossier: ' + e + '</p>';
      }
    }

    function renderORCDossier(d) {
      const b = document.getElementById("orc-body");
      if (!b) return;
      const card = d.recommended_action_card || {};
      b.innerHTML = `
        <div style="background:#1e293b; padding:12px; border-radius:6px; margin-bottom:12px; border:1px solid #334155;">
          <div style="display:flex; justify-content:space-between; align-items:center;">
            <span style="font-weight:bold; color:#f8fafc;">${d.dossier_id}</span>
            <span style="background:#0284c7; color:#fff; padding:2px 8px; border-radius:4px; font-size:0.7rem;">${d.verdict}</span>
          </div>
          <p style="margin:8px 0 0 0; color:#94a3b8;"><strong>Hypothesis:</strong> ${d.hypothesis}</p>
        </div>
        <div style="background:#1e293b; padding:12px; border-radius:6px; margin-bottom:12px; border:1px solid #334155;">
          <h4 style="margin:0 0 6px 0; color:#38bdf8;">Corroborating Evidence</h4>
          <p style="margin:0; color:#cbd5e1; font-size:0.8rem; line-height:1.4;">${d.external_corroboration}</p>
        </div>
        <div style="background:#1e293b; padding:12px; border-radius:6px; margin-bottom:12px; border:1px solid #334155;">
          <h4 style="margin:0 0 8px 0; color:#38bdf8;">Matched Opportunity Contract</h4>
          <table style="width:100%; font-size:0.8rem; border-collapse:collapse;">
            <tr><td style="color:#94a3b8; padding:3px 0;">Contract:</td><td style="color:#f8fafc; font-weight:bold;">${d.matched_contract.contract_id}</td></tr>
            <tr><td style="color:#94a3b8; padding:3px 0;">Venue / Category:</td><td style="color:#f8fafc;">${d.matched_contract.venue} (${d.category})</td></tr>
            <tr><td style="color:#94a3b8; padding:3px 0;">Venue Ask:</td><td style="color:#f8fafc;">${d.matched_contract.venue_ask_cents}¢</td></tr>
            <tr><td style="color:#94a3b8; padding:3px 0;">Modeled Probability:</td><td style="color:#f8fafc;">${(d.matched_contract.modeled_probability*100).toFixed(1)}%</td></tr>
            <tr><td style="color:#94a3b8; padding:3px 0;">Net Statistical Edge:</td><td style="color:#10b981; font-weight:bold;">+${d.matched_contract.net_edge_pct}%</td></tr>
          </table>
        </div>
        <div style="background:#0f172a; border:1px solid #10b981; border-radius:6px; padding:12px;">
          <strong style="color:#10b981;">Recommended Action Card</strong>
          <p style="margin:4px 0 8px 0; color:#cbd5e1; font-size:0.8rem;">${card.description || ''}</p>
          <button onclick="alert('Action staged: ' + '${card.action_id}')" style="background:#10b981; color:#0f172a; border:none; padding:6px 12px; border-radius:4px; font-weight:bold; cursor:pointer;">${card.title || 'Execute Staged Order'}</button>
        </div>
      `;
    }
    '''
    if 'function launchORC' not in html:
        html = html.replace('</script>', js_helpers + '\n</script>')

    old_copilot_hdr = re.search(r'<div style="display:flex; justify-content:space-between; align-items:center; background:#1e293b; padding:12px 16px; border-bottom:1px solid #334155;">.*?</div>\s*</div>', html, re.DOTALL)
    if old_copilot_hdr:
        new_copilot_hdr = '''<div style="display:flex; justify-content:space-between; align-items:center; background:#1e293b; padding:12px 16px; border-bottom:1px solid #334155;">
      <div>
        <strong style="color:#38bdf8; font-size:1rem;">&#129302; PDEUE Copilot</strong>
        <small style="display:block; color:#94a3b8; font-size:0.7rem;">AUTH-01/AUTH-04 Deterministic Governance</small>
      </div>
      <div style="display:flex; gap:6px; align-items:center;">
        <button onclick="clearChat()" style="background:#334155; color:#94a3b8; border:1px solid #475569; padding:3px 8px; border-radius:4px; font-size:0.75rem; cursor:pointer;" title="Clear Chat History">Clear</button>
        <button onclick="toggleCopilot(true)" style="background:#334155; color:white; border:none; padding:4px 10px; border-radius:4px; cursor:pointer;">&#10005;</button>
      </div>
    </div>'''
        html = html.replace(old_copilot_hdr.group(0), new_copilot_hdr, 1)

    old_card_exec = 'function executeActionCard(endpoint, method, payloadJson) {'
    new_card_exec = '''function executeActionCard(endpoint, method, payloadJson) {
      if (endpoint && endpoint.includes('/orc/dossier')) {
        let p = {};
        try { p = JSON.parse(payloadJson); } catch(e) {}
        launchORC(p.query || 'Research market opportunity');
        return;
      }'''
    if old_card_exec in html and 'launchORC(' not in html.split(old_card_exec)[1][:300]:
        html = html.replace(old_card_exec, new_card_exec, 1)

    p.write_text(html, encoding="utf-8")
    print(f"Patched ORC drawer and controls in: {p}")