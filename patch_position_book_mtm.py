import pathlib
import re
import subprocess
import sys
import os

REPO_ROOT = pathlib.Path(r"C:\PDEUE_Gemini")
BACKEND_DIR = REPO_ROOT / "backend"
POSITION_BOOK_PATH = BACKEND_DIR / "app" / "domain" / "position_book.py"
WORKSPACE_ROUTER_PATH = BACKEND_DIR / "app" / "api" / "v1" / "workspace_router.py"
TEST_PATH = BACKEND_DIR / "tests" / "test_phase2_active_dispatch.py"

def patch_position_book():
    if not POSITION_BOOK_PATH.exists():
        print(f"[SKIP] {POSITION_BOOK_PATH} not found")
        return
    txt = POSITION_BOOK_PATH.read_text(encoding="utf-8")
    
    # Safely replace all direct dictionary lookups in get_summary
    txt = re.sub(r"p\['total_cost_cents'\]", "p.get('total_cost_cents', 0)", txt)
    txt = re.sub(r"p\['mtm_value_cents'\]", "p.get('mtm_value_cents', p.get('total_cost_cents', 0))", txt)
    txt = re.sub(r"p\['unrealized_pnl_cents'\]", "p.get('unrealized_pnl_cents', 0)", txt)
    txt = re.sub(r"p\['realized_pnl_cents'\]", "p.get('realized_pnl_cents', 0)", txt)

    POSITION_BOOK_PATH.write_text(txt, encoding="utf-8")
    print(f"[OK] Patched defensive lookups in {POSITION_BOOK_PATH}")

def patch_workspace_router():
    txt = WORKSPACE_ROUTER_PATH.read_text(encoding="utf-8")

    # Add mtm_value_cents explicitly to pos_record
    if '"mtm_value_cents"' not in txt:
        txt = txt.replace(
            '"total_cost_cents": dispatch["total_committed_cents"],',
            '"total_cost_cents": dispatch["total_committed_cents"],\n        "mtm_value_cents": dispatch["total_committed_cents"],'
        )

    WORKSPACE_ROUTER_PATH.write_text(txt, encoding="utf-8")
    print(f"[OK] Added mtm_value_cents to {WORKSPACE_ROUTER_PATH}")

def run_verification():
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + str(BACKEND_DIR)
    res = subprocess.run([sys.executable, "-m", "pytest", str(TEST_PATH), "-v", "--cache-clear"], cwd=str(REPO_ROOT), env=env)
    if res.returncode != 0:
        print("\n[FAIL] Test suite failed.")
        sys.exit(res.returncode)
    print("\n[SUCCESS] test_phase2_active_dispatch passed 100% green!")

if __name__ == "__main__":
    patch_position_book()
    patch_workspace_router()
    run_verification()