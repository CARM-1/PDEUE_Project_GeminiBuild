import pathlib
import re

card_store_and_exec_js = '''
// Global Action Card in-memory registry to avoid HTML quote escaping collisions
window._actionCardRegistry = window._actionCardRegistry || {};

function executeActionCard(cardId) {
  const card = window._actionCardRegistry[cardId];
  if (!card) {
    console.error("Action card not found in registry:", cardId);
    return;
  }
  
  // Route ORC Inspections directly to the slide-out drawer
  if (card.action_type === 'ORC_INSPECT' || (card.endpoint && card.endpoint.includes('orc'))) {
    const q = (card.payload && card.payload.query) ? card.payload.query : 'Research market opportunity';
    launchORC(q);
    return;
  }
  
  // Default execution for other cards
  fetch(card.endpoint, {
    method: card.method || 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(card.payload || {})
  })
  .then(res => res.json())
  .then(data => alert('Action executed under AUTH-01:\\n' + JSON.stringify(data, null, 2)))
  .catch(err => alert('Error executing action: ' + err));
}
'''

for file_path in [pathlib.Path("backend/app/api/v1/dashboard.html"), pathlib.Path("backend/app/static/dashboard.html")]:
    if not file_path.exists():
        continue
    content = file_path.read_text(encoding="utf-8")

    # 1. Update renderCopilotResponse to register cards in window._actionCardRegistry and pass clean card.action_id
    old_card_render = re.search(
        r'if\s*\(\s*data\.action_cards.*?data\.action_cards\.forEach\(card\s*=>\s*\{.*?\}\);\s*\}',
        content,
        re.DOTALL
    )
    if old_card_render:
        new_card_render = '''if (data.action_cards && data.action_cards.length > 0) {
    data.action_cards.forEach(card => {
      // Save card in global registry using unique ID
      window._actionCardRegistry[card.action_id] = card;
      
      html += `
        <div style="background:#0f172a; border:1px solid #38bdf8; border-radius:6px; padding:10px; margin-top:8px;">
          <div style="display:flex; justify-content:space-between; align-items:center;">
            <strong style="color:#f8fafc; font-size:0.8rem;">${card.title}</strong>
            <span style="font-size:0.65rem; color:#94a3b8; background:#1e293b; padding:2px 6px; border-radius:3px;">${card.action_type}</span>
          </div>
          <p style="margin:4px 0 8px 0; font-size:0.75rem; color:#94a3b8;">${card.description || ""}</p>
          <button onclick="executeActionCard('${card.action_id}')" style="background:#38bdf8; color:#0f172a; border:none; padding:5px 10px; border-radius:4px; font-weight:bold; font-size:0.75rem; cursor:pointer;">Execute Card</button>
        </div>
      `;
    });
  }'''
        content = content.replace(old_card_render.group(0), new_card_render, 1)

    # 2. Replace any existing executeActionCard implementation with the registry-based function
    content = re.sub(
        r'function executeActionCard\(.*?\)\s*\{.*?return;\s*\}',
        '',
        content,
        flags=re.DOTALL
    )
    
    if 'window._actionCardRegistry' not in content:
        content = content.replace('</script>', card_store_and_exec_js + '\n</script>')

    file_path.write_text(content, encoding="utf-8")
    print(f"Successfully patched click handler in: {file_path}")

print("Update completed.")