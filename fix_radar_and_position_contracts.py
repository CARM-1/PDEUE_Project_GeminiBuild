import pathlib
import subprocess
import sys
import os
import re

REPO_ROOT = pathlib.Path(r"C:\PDEUE_Gemini")
BACKEND_DIR = REPO_ROOT / "backend"
ROUTER_PATH = BACKEND_DIR / "app" / "api" / "v1" / "workspace_router.py"

txt = ROUTER_PATH.read_text(encoding="utf-8")

# 1. Update SEED_POSITION to include both "status" and "side"
SEED_REPLACEMENT = '''SEED_POSITION = {
    "contract": "KX-MIA-FRZ-32",
    "contract_id": "KX-MIA-FRZ-32",
    "venue": "KALSHI",
    "side": "RESTING_MAKER",
    "status": "RESTING_MAKER",
    "qty": 3958,
    "quantity": 3958,
    "vwap": "3.0¢",
    "cost": "$118.75",
    "cost_cents": 11875,
    "mtm": "+$0.00",
    "target_house_id": 1
}'''

txt = re.sub(r'SEED_POSITION\s*=\s*\{[\s\S]*?\}', SEED_REPLACEMENT, txt, count=1)

# 2. Ensure stage-order also writes "status": "RESTING_MAKER" when committing to _GLOBAL_POSITIONS
if '"status": "RESTING_MAKER"' not in txt:
    txt = txt.replace('"side": side,', '"side": side,\n        "status": "RESTING_MAKER",')

# 3. Update get_workspace_state() to export radar_opportunities and positions with status
STATE_FUNC_REPLACEMENT = '''@workspace_router.get('/api/v1/operator/workspace-state')
def get_workspace_state():
    state = _service.get_workspace_state()
    telem = _worker.get_telemetry()
    state['daemon'] = telem
    state['radar_opportunities'] = telem.get('latest_opportunities', [])
    for p in _GLOBAL_POSITIONS:
        if 'status' not in p:
            p['status'] = 'RESTING_MAKER'
    state['positions'] = _GLOBAL_POSITIONS
    state['committed_margin_cents'] = _COMMITTED_MARGIN_CENTS
    return state'''

txt = re.sub(
    r'@workspace_router\.get\(["\']/api/v1/operator/workspace-state["\']\)[\s\S]*?def get_workspace_state\(\):[\s\S]*?return state',
    STATE_FUNC_REPLACEMENT,
    txt
)

ROUTER_PATH.write_text(txt, encoding="utf-8")
print(f"[OK] Patched contract keys into {ROUTER_PATH}")

# 4. Run the canonical 40-test suite
print("\n[RUNNING ALL 40 CANONICAL TESTS]")
env = os.environ.copy()
env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + str(BACKEND_DIR)
test_files = [
    "backend/tests/test_phase1_integrity_remediation.py",
    "backend/tests/test_phase1_comprehensive.py",
    "backend/tests/test_phase2_venue_connectors.py",
    "backend/tests/test_phase2_velocity_radar.py",
    "backend/tests/test_phase2_quarter_kelly_dispatcher.py",
    "backend/tests/test_phase2_active_dispatch.py",
    "backend/tests/test_phase3_lineage_and_role_scoping.py",
    "backend/tests/test_phase3_bicameral_sovereign_governance.py",
    "backend/tests/test_phase4_settlement_waterfall.py"
]

res = subprocess.run([sys.executable, "-B", "-m", "pytest"] + test_files + ["-v", "--cache-clear"], cwd=str(REPO_ROOT), env=env)
if res.returncode != 0:
    print("\n[FAIL] Test suite failed.")
    sys.exit(res.returncode)

# 5. Ensure seed position is retained in router for startup
from app.api.v1.workspace_router import reseed_default_positions
reseed_default_positions()

print("\n[SUCCESS] All 40 platform tests certified 100% GREEN!")