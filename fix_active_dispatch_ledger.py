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
    
    # Defend get_summary calculations against missing dictionary keys
    txt = re.sub(
        r"p\['total_cost_cents'\]",
        "p.get('total_cost_cents', 0)",
        txt
    )
    txt = re.sub(
        r"p\['unrealized_pnl_cents'\]",
        "p.get('unrealized_pnl_cents', 0)",
        txt
    )
    txt = re.sub(
        r"p\['realized_pnl_cents'\]",
        "p.get('realized_pnl_cents', 0)",
        txt
    )
    POSITION_BOOK_PATH.write_text(txt, encoding="utf-8")
    print(f"[OK] Fortified defensive ledger calculations in {POSITION_BOOK_PATH}")

def patch_workspace_router():
    txt = WORKSPACE_ROUTER_PATH.read_text(encoding="utf-8")

    # Ensure pos_record supplies both UI and domain ledger keys
    old_record = '''    pos_record = {
        "contract": ticker,
        "venue": venue,
        "side": side,
        "qty": dispatch["total_quantity"],
        "vwap": f"{int(round(price * 100))}¢",
        "cost": f"${dispatch['total_committed_cents'] / 100.0:.2f}",
        "mtm": "+$0.00",
        "status": "RESTING_MAKER",
        "lineage_code": dispatch["lineage_code"]
    }'''

    new_record = '''    pos_record = {
        "contract": ticker,
        "venue": venue,
        "side": side,
        "qty": dispatch["total_quantity"],
        "vwap": f"{int(round(price * 100))}¢",
        "cost": f"${dispatch['total_committed_cents'] / 100.0:.2f}",
        "mtm": "+$0.00",
        "status": "RESTING_MAKER",
        "lineage_code": dispatch["lineage_code"],
        "total_cost_cents": dispatch["total_committed_cents"],
        "unrealized_pnl_cents": 0,
        "realized_pnl_cents": 0
    }'''

    if old_record in txt:
        txt = txt.replace(old_record, new_record)
    else:
        # Generic regex replacement if spacing differs
        txt = re.sub(
            r'pos_record\s*=\s*\{[^}]*"lineage_code":\s*dispatch\["lineage_code"\]\s*\}',
            new_record.strip(),
            txt
        )

    WORKSPACE_ROUTER_PATH.write_text(txt, encoding="utf-8")
    print(f"[OK] Synchronized integer ledger keys in {WORKSPACE_ROUTER_PATH}")

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