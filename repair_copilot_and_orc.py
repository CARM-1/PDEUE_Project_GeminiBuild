import pathlib
import re

# ==========================================
# 1. FIX WORKSPACE_ROUTER ROUTE PATH
# ==========================================
wr_path = pathlib.Path("backend/app/api/v1/workspace_router.py")
wr_text = wr_path.read_text(encoding="utf-8")

# Ensure canonical /api/v1/operator/orc/dossier is registered
if "/api/v1/operator/orc/dossier" not in wr_text:
    wr_text = re.sub(
        r'@workspace_router\.get\(["\'](/orc/dossier|/operator/orc/dossier)["\']\)',
        '@workspace_router.get("/api/v1/operator/orc/dossier")\n@workspace_router.get("/orc/dossier")',
        wr_text
    )
    if "/api/v1/operator/orc/dossier" not in wr_text:
        wr_text += '''

# --- Opportunity Research Center (ORC) API ---
from app.domain.orc_engine import OpportunityResearchCenter
_orc_engine = OpportunityResearchCenter()

@workspace_router.get("/api/v1/operator/orc/dossier")
@workspace_router.get("/orc/dossier")
def get_orc_dossier(query: str = "Research market opportunity"):
    return _orc_engine.evaluate_hypothesis(hypothesis=query)
'''
    wr_path.write_text(wr_text, encoding="utf-8")
    print("[1/3] Registered canonical /api/v1/operator/orc/dossier in workspace_router.py")
else:
    print("[1/3] Route /api/v1/operator/orc/dossier already present.")

# ==========================================
# 2. RESTORE COPILOT DRAWER & ORC IN HTML
# ==========================================
full_copilot_markup = '''
    <!-- Floating Copilot Launcher Button (when drawer is closed) -->
    <button id="copilot-toggle-btn" onclick="toggleCopilot()" style="position:fixed; bottom:25px; right:25px; background:#0284c7; color:white; border:none; border-radius:50%; width:50px; height:50px; font-size:1.5rem; cursor:pointer; box-shadow:0 4px 15px rgba(0,0,0,0.5); z-index:9998; display:none; align-items:center; justify-content:center;">🤖</button>

    <!-- PDEUE Copilot Drawer -->
    <div id="copilot-drawer" style="position:fixed; bottom:25px; right:25px; width:400px; height:520px; background:#0f172a; border:2px solid #38bdf8; border-radius:8px; box-shadow:0 10px 25px rgba(0,0,0,0.6); z-index:9999; display:flex; flex-direction:column; overflow:hidden;">
      <div style="display:flex; justify-content:space-between; align-items:center; background:#1e293b; padding:12px 16px; border-bottom:1px solid #334155;">
        <div>
          <strong style="color:#38bdf8; font-size:1rem;">🤖 PDEUE Copilot</strong>
          <small style="display:block; color:#94a3b8; font-size:0.7rem;">AUTH-01/AUTH-04 Deterministic Governance</small>
        </div>
        <div style="display:flex; gap:6px; align-items:center;">
          <button onclick="clearChat()" style="background:#334155; color:#94a3b8; border:1px solid #475569; padding:3px 8px; border-radius:4px; font-size:0.75rem; cursor:pointer;" title="Clear Chat History">Clear</button>
          <button onclick="toggleCopilot(true)" style="background:#334155; color:white; border:none; padding:4px 10px; border-radius:4px; cursor:pointer;">✕</button>
        </div>
      </div>
      <div id="chat-log" style="flex:1; padding:16px; overflow-y:auto; font-size:0.85rem; display:flex; flex-direction:column; gap:12px;">
        <div style="background:#1e293b; padding:10px 12px; border-radius:6px; border-left:3px solid #38bdf8; color:#cbd5e1;">
          <p style="margin:0 0 4px 0; font-weight:600; color:#38bdf8; font-size:0.75rem;">PDEUE COPILOT</p>
          <p style="margin:0; font-size:0.85rem; line-height:1.4;">Copilot active. Ask about point-in-time underwriting, Strategy D inside-maker limits, the 87/10/3 waterfall, or Opportunity Research Center (ORC) hypotheses.</p>
        </div>
      </div>
      <div style="padding:12px 16px; background:#1e293b; border-top:1px solid #334155; display:flex; gap:8px;">
        <input id="copilot-input" type="text" placeholder="Ask Copilot or propose a hypothesis..." onkeydown="if(event.key==='Enter') sendCopilotQuery()" style="flex:1; background:#0f172a; border:1px solid #334155; border-radius:4px; padding:8px 12px; color:#f8fafc; font-size:0.85rem; outline:none;" />
        <button onclick="sendCopilotQuery()" style="background:#38bdf8; color:#0f172a; font-weight:bold; border:none; border-radius:4px; padding:8px 14px; cursor:pointer; font-size:0.85rem;">Send</button>
      </div>
    </div>

    <!-- Opportunity Research Center (ORC) Slide-out Drawer -->
    <div id="orc-drawer" style="position:fixed; top:0; right:-520px; width:480px; height:100vh; background:#0f172a; border-left:2px solid #38bdf8; box-shadow:-10px 0 25px rgba(0,0,0,0.7); z-index:10000; transition:right 0.3s ease-in-out; display:flex; flex-direction:column;">
      <div style="display:flex; justify-content:space-between; align-items:center; background:#1e293b; padding:12px 16px; border-bottom:1px solid #334155;">
        <div>
          <strong style="color:#38bdf8; font-size:1rem;">🧪 Opportunity Research Center (ORC)</strong>
          <small style="display:block; color:#94a3b8; font-size:0.7rem;">Point-in-Time Hypothesis & Edge Evaluation</small>
        </div>
        <button onclick="toggleORC(false)" style="background:#334155; color:white; border:none; padding:4px 10px; border-radius:4px; cursor:pointer;">✕</button>
      </div>
      <div id="orc-body" style="padding:16px; overflow-y:auto; flex:1; font-size:0.85rem; color:#e2e8f0;">
        <p style="color:#94a3b8;">No dossier loaded. Submit a hypothesis in Copilot to evaluate.</p>
      </div>
    </div>
'''

js_runtime = '''
<script>
function clearChat() {
  const log = document.getElementById("chat-log");
  if (log) {
    log.innerHTML = `
      <div style="background:#1e293b; padding:10px 12px; border-radius:6px; border-left:3px solid #38bdf8; color:#cbd5e1;">
        <p style="margin:0 0 4px 0; font-weight:600; color:#38bdf8; font-size:0.75rem;">PDEUE COPILOT</p>
        <p style="margin:0; font-size:0.85rem; line-height:1.4;">Copilot active. Ask about point-in-time underwriting, Strategy D inside-maker limits, the 87/10/3 waterfall, or Opportunity Research Center (ORC) hypotheses.</p>
      </div>`;
  }
}

function toggleCopilot(shouldClear = false) {
  const d = document.getElementById("copilot-drawer");
  const btn = document.getElementById("copilot-toggle-btn");
  if (!d) return;
  if (d.style.display === "none") {
    d.style.display = "flex";
    if (btn) btn.style.display = "none";
  } else {
    d.style.display = "none";
    if (btn) btn.style.display = "flex";
    if (shouldClear) clearChat();
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
      <button onclick="alert('Action staged under AUTH-01: ' + '${card.action_id}')" style="background:#10b981; color:#0f172a; border:none; padding:6px 12px; border-radius:4px; font-weight:bold; cursor:pointer;">${card.title || 'Execute Staged Order'}</button>
    </div>
  `;
}

async function sendCopilotQuery() {
  const input = document.getElementById("copilot-input");
  const query = input ? input.value.trim() : "";
  if (!query) return;
  input.value = "";

  const log = document.getElementById("chat-log");
  if (log) {
    const userMsg = document.createElement("div");
    userMsg.style.cssText = "background:#0284c7; color:#ffffff; padding:8px 12px; border-radius:6px; align-self:flex-end; max-width:85%; font-size:0.85rem; word-break:break-word;";
    userMsg.innerText = query;
    log.appendChild(userMsg);
    log.scrollTop = log.scrollHeight;
  }

  try {
    const res = await fetch("/api/v1/operator/ai-chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query: query, actor_hat: "Chief Administrator" })
    });
    const data = await res.json();
    renderCopilotResponse(data);
  } catch (err) {
    if (log) {
      const errBox = document.createElement("div");
      errBox.style.cssText = "background:#ef4444; color:#fff; padding:8px 12px; border-radius:6px; font-size:0.85rem;";
      errBox.innerText = "Error: " + err;
      log.appendChild(errBox);
    }
  }
}

function renderCopilotResponse(data) {
  const log = document.getElementById("chat-log");
  if (!log) return;

  const botMsg = document.createElement("div");
  botMsg.style.cssText = "background:#1e293b; padding:10px 12px; border-radius:6px; border-left:3px solid #38bdf8; color:#cbd5e1; align-self:flex-start; max-width:90%; font-size:0.85rem;";
  
  let html = `<p style="margin:0 0 6px 0; font-weight:600; color:#38bdf8; font-size:0.75rem;">PDEUE COPILOT</p>`;
  html += `<p style="margin:0 0 8px 0; line-height:1.4;">${data.response_text || ""}</p>`;

  if (data.action_cards && data.action_cards.length > 0) {
    data.action_cards.forEach(card => {
      const payloadStr = JSON.stringify(card.payload || {}).replace(/"/g, '&quot;');
      html += `
        <div style="background:#0f172a; border:1px solid #38bdf8; border-radius:6px; padding:10px; margin-top:8px;">
          <div style="display:flex; justify-content:space-between; align-items:center;">
            <strong style="color:#f8fafc; font-size:0.8rem;">${card.title}</strong>
            <span style="font-size:0.65rem; color:#94a3b8; background:#1e293b; padding:2px 6px; border-radius:3px;">${card.action_type}</span>
          </div>
          <p style="margin:4px 0 8px 0; font-size:0.75rem; color:#94a3b8;">${card.description || ""}</p>
          <button onclick='executeActionCard("${card.endpoint}", "${card.method}", "${payloadStr}")' style="background:#38bdf8; color:#0f172a; border:none; padding:5px 10px; border-radius:4px; font-weight:bold; font-size:0.75rem; cursor:pointer;">Execute Card</button>
        </div>
      `;
    });
  }

  botMsg.innerHTML = html;
  log.appendChild(botMsg);
  log.scrollTop = log.scrollHeight;
}

function executeActionCard(endpoint, method, payloadJson) {
  if (endpoint && (endpoint.includes('/orc/dossier') || endpoint.includes('orc'))) {
    let p = {};
    try { p = typeof payloadJson === 'string' ? JSON.parse(payloadJson) : payloadJson; } catch(e) {}
    launchORC(p.query || 'Research market opportunity');
    return;
  }
  alert('Action executed under AUTH-01: ' + endpoint);
}
</script>
'''

for file_path in [pathlib.Path("backend/app/api/v1/dashboard.html"), pathlib.Path("backend/app/static/dashboard.html")]:
    if not file_path.exists():
        continue
    html = file_path.read_text(encoding="utf-8")
    
    # Strip any corrupted existing drawers
    html = re.sub(r'<!-- Floating Copilot Launcher.*?</div>\s*</div>', '', html, flags=re.DOTALL)
    html = re.sub(r'<div id="copilot-drawer".*?</div>\s*</div>\s*(?=<!-- Opportunity|<script|</body>)', '', html, flags=re.DOTALL)
    html = re.sub(r'<!-- Opportunity Research Center.*?</div>\s*</div>', '', html, flags=re.DOTALL)
    
    # Insert restored markup cleanly right before </body>
    if 'id="copilot-drawer"' not in html:
        html = html.replace('</body>', full_copilot_markup + '\n' + js_runtime + '\n</body>')
    
    file_path.write_text(html, encoding="utf-8")
    print(f"[2/3] Restored complete Copilot & ORC drawer interface in: {file_path}")

print("\n[3/3] Repair completed successfully.")