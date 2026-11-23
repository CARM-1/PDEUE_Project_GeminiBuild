"""Milestone A2 — ADR-012 Per-SCMA High-Water Mark & Rule A14 (100% SCMA Loss Isolation) tests."""
from pathlib import Path
import sqlite3

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import create_engine, inspect

from app.adapters.platform_yield_adapter import PlatformYieldAdapter
from app.db.models import AccountModel
from app.domain.capital_ledger import CapitalLedger
from app.domain.maker_rebate_adapter import MakerRebateLedgerAdapter
from app.domain.settlement_engine import SettlementEngine, calculate_hwm_waterfall_cents
from app.domain.walk_forward_simulation import WalkForwardBenchmark

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"


def test_a_win_from_hwm_splits_87_10_3_with_remainder_to_cfcp():
    ledger = CapitalLedger()
    ledger.register_member_account("SCMA-A", seed_capital_cents=100_000)

    # 10,001 cents: scma=8,700, faep=300, cfcp=1,001 (1 residual cent -> CFCP)
    wf = ledger.settle_member_trade("SCMA-A", 10_001)
    assert wf["waterfall_eligible_cents"] == 10_001
    assert wf["recovery_cents"] == 0
    assert wf["scma_cents"] == 8_700
    assert wf["cfcp_cents"] == 1_001
    assert wf["faep_cents"] == 300
    assert wf["residual_cents"] == 1
    assert wf["scma_cents"] + wf["cfcp_cents"] + wf["faep_cents"] == 10_001
    assert ledger.members["SCMA-A"]["balance_cents"] == 108_700
    assert ledger.members["SCMA-A"]["high_water_mark_cents"] == 108_700
    assert ledger.central_family_pool_cents == 1_001
    assert ledger.founder_pool_cents == 300

    # Exhaustive conservation check across 1..500 cents at HWM
    for profit in range(1, 501):
        res = calculate_hwm_waterfall_cents(profit, 50_000, 50_000)
        assert res["scma_cents"] == (profit * 87) // 100
        assert res["faep_cents"] == (profit * 3) // 100
        assert res["cfcp_cents"] == profit - res["scma_cents"] - res["faep_cents"]
        assert res["residual_cents"] in (0, 1, 2)
        assert res["scma_cents"] + res["cfcp_cents"] + res["faep_cents"] == profit
        assert res["high_water_mark_after_cents"] == 50_000 + res["scma_cents"]


def test_b_realized_loss_is_100_percent_contained_inside_executing_scma():
    ledger = CapitalLedger()
    ledger.register_member_account("SCMA-LOSS", seed_capital_cents=100_000)
    ledger.register_member_account("SCMA-SIBLING", seed_capital_cents=50_000)

    # Seed prior CFCP/FAEP balances via a win on SCMA-SIBLING
    ledger.settle_member_trade("SCMA-SIBLING", 10_000)
    cfcp_before = ledger.central_family_pool_cents
    faep_before = ledger.founder_pool_cents
    sibling_before = ledger.members["SCMA-SIBLING"]["balance_cents"]
    assert cfcp_before == 1_000 and faep_before == 300

    # Realized loss on SCMA-LOSS must NEVER touch sibling SCMA, CFCP, or FAEP
    wf = ledger.settle_member_trade("SCMA-LOSS", -25_000)
    assert wf["scma_cents"] == -25_000
    assert wf["cfcp_cents"] == 0
    assert wf["faep_cents"] == 0
    assert wf["waterfall_eligible_cents"] == 0
    assert wf["high_water_mark_after_cents"] == 100_000
    assert ledger.members["SCMA-LOSS"]["balance_cents"] == 75_000
    assert ledger.members["SCMA-LOSS"]["high_water_mark_cents"] == 100_000
    assert ledger.central_family_pool_cents == cfcp_before
    assert ledger.founder_pool_cents == faep_before
    assert ledger.members["SCMA-SIBLING"]["balance_cents"] == sibling_before


def test_c_partial_and_full_drawdown_recovery_below_hwm_pays_zero_to_cfcp_and_faep():
    ledger = CapitalLedger()
    ledger.register_member_account("SCMA-REC", seed_capital_cents=100_000)

    # Drawdown of -$200.00 -> equity = 80,000, HWM = 100,000
    ledger.settle_member_trade("SCMA-REC", -20_000)
    assert ledger.members["SCMA-REC"]["balance_cents"] == 80_000
    assert ledger.members["SCMA-REC"]["high_water_mark_cents"] == 100_000

    # Partial recovery +$120.00 -> equity = 92,000 <= 100,000 (0% skim)
    partial = ledger.settle_member_trade("SCMA-REC", 12_000)
    assert partial["recovery_cents"] == 12_000
    assert partial["waterfall_eligible_cents"] == 0
    assert partial["scma_cents"] == 12_000
    assert partial["cfcp_cents"] == 0
    assert partial["faep_cents"] == 0
    assert partial["high_water_mark_after_cents"] == 100_000
    assert ledger.members["SCMA-REC"]["balance_cents"] == 92_000
    assert ledger.central_family_pool_cents == 0
    assert ledger.founder_pool_cents == 0

    # Exact full recovery +$80.00 -> equity = 100,000 == HWM (still 0% skim)
    full = ledger.settle_member_trade("SCMA-REC", 8_000)
    assert full["recovery_cents"] == 8_000
    assert full["waterfall_eligible_cents"] == 0
    assert full["scma_cents"] == 8_000
    assert full["cfcp_cents"] == 0
    assert full["faep_cents"] == 0
    assert full["high_water_mark_after_cents"] == 100_000
    assert ledger.members["SCMA-REC"]["balance_cents"] == 100_000
    assert ledger.central_family_pool_cents == 0
    assert ledger.founder_pool_cents == 0


def test_d_recovery_crossing_above_hwm_splits_only_net_excess_and_advances_hwm():
    ledger = CapitalLedger()
    ledger.register_member_account("SCMA-CROSS", seed_capital_cents=10_000)

    # Lose 40 cents -> equity = 9,960, HWM = 10,000
    ledger.settle_member_trade("SCMA-CROSS", -40)
    assert ledger.members["SCMA-CROSS"]["balance_cents"] == 9_960
    assert ledger.members["SCMA-CROSS"]["high_water_mark_cents"] == 10_000

    # Win 100 cents -> 40 recovery (0% skim) + 60 eligible (scma=52, faep=1, cfcp=7 [1 residual])
    cross = ledger.settle_member_trade("SCMA-CROSS", 100)
    assert cross["recovery_cents"] == 40
    assert cross["waterfall_eligible_cents"] == 60
    assert cross["scma_cents"] == 92
    assert cross["cfcp_cents"] == 7
    assert cross["faep_cents"] == 1
    assert cross["residual_cents"] == 1
    assert cross["scma_cents"] + cross["cfcp_cents"] + cross["faep_cents"] == 100
    assert cross["high_water_mark_after_cents"] == 10_052
    assert ledger.members["SCMA-CROSS"]["balance_cents"] == 10_052
    assert ledger.members["SCMA-CROSS"]["high_water_mark_cents"] == 10_052
    assert ledger.central_family_pool_cents == 7
    assert ledger.founder_pool_cents == 1


def test_e_alternating_win_loss_chop_netting_flat_imposes_zero_volatility_tax():
    ledger = CapitalLedger()
    ledger.register_member_account("SCMA-CHOP", seed_capital_cents=100_000)

    # 25 consecutive -500 / +500 flat cycles (gross chop = $250, net PnL = $0)
    for _ in range(25):
        ledger.settle_member_trade("SCMA-CHOP", -500)
        ledger.settle_member_trade("SCMA-CHOP", 500)

    assert ledger.members["SCMA-CHOP"]["balance_cents"] == 100_000
    assert ledger.members["SCMA-CHOP"]["high_water_mark_cents"] == 100_000
    assert ledger.central_family_pool_cents == 0
    assert ledger.founder_pool_cents == 0

    # Also verify chop after establishing a higher HWM: win +10,000 then chop 10x
    ledger.settle_member_trade("SCMA-CHOP", 10_000)
    hwm_peak = ledger.members["SCMA-CHOP"]["high_water_mark_cents"]
    assert hwm_peak == 108_700
    cfcp_at_peak = ledger.central_family_pool_cents
    faep_at_peak = ledger.founder_pool_cents

    for _ in range(10):
        ledger.settle_member_trade("SCMA-CHOP", -2_000)
        ledger.settle_member_trade("SCMA-CHOP", 2_000)

    assert ledger.members["SCMA-CHOP"]["balance_cents"] == hwm_peak
    assert ledger.members["SCMA-CHOP"]["high_water_mark_cents"] == hwm_peak
    assert ledger.central_family_pool_cents == cfcp_at_peak
    assert ledger.founder_pool_cents == faep_at_peak


def test_f_deposit_and_withdrawal_hwm_adjustments_behave_cleanly():
    ledger = CapitalLedger()
    ledger.register_member_account("SCMA-FLOW", seed_capital_cents=100_000)

    # 1. Deposit at HWM raises HWM dollar-for-dollar (principal is not profit)
    dep = ledger.deposit_member_capital("SCMA-FLOW", 50_000)
    assert dep["balance_cents"] == 150_000
    assert dep["high_water_mark_after_cents"] == 150_000
    assert ledger.central_family_pool_cents == 0
    assert ledger.founder_pool_cents == 0

    # 2. Withdrawal at HWM reduces HWM dollar-for-dollar so account is NOT trapped below HWM
    wd = ledger.withdraw_member_capital("SCMA-FLOW", 50_000)
    assert wd["balance_cents"] == 100_000
    assert wd["high_water_mark_after_cents"] == 100_000

    # Next $10 win is immediately eligible for 87/10/3 split (not trapped)
    win = ledger.settle_member_trade("SCMA-FLOW", 1_000)
    assert win["waterfall_eligible_cents"] == 1_000
    assert win["scma_cents"] == 870 and win["cfcp_cents"] == 100 and win["faep_cents"] == 30
    assert ledger.members["SCMA-FLOW"]["high_water_mark_cents"] == 100_870

    # 3. Deposit during drawdown preserves exact dollar loss deficit
    ledger.register_member_account("SCMA-DD", seed_capital_cents=100_000)
    ledger.settle_member_trade("SCMA-DD", -20_000)  # equity=80,000, HWM=100,000 (deficit=20,000)
    ledger.deposit_member_capital("SCMA-DD", 20_000)  # equity=100,000, HWM=120,000 (deficit still 20,000)
    assert ledger.members["SCMA-DD"]["balance_cents"] == 100_000
    assert ledger.members["SCMA-DD"]["high_water_mark_cents"] == 120_000
    rec = ledger.settle_member_trade("SCMA-DD", 20_000)
    assert rec["waterfall_eligible_cents"] == 0
    assert rec["cfcp_cents"] == 0 and rec["faep_cents"] == 0

    # 4. Underwater withdrawal scales HWM proportionally (preserving drawdown ratio, never trapping)
    ledger.register_member_account("SCMA-UW", seed_capital_cents=100_000)
    ledger.settle_member_trade("SCMA-UW", -20_000)  # equity=80,000, HWM=100,000 (needs +25% to recover)
    wd_uw = ledger.withdraw_member_capital("SCMA-UW", 40_000)  # withdraws 50% -> equity=40,000, HWM=50,000
    assert wd_uw["balance_cents"] == 40_000
    assert wd_uw["high_water_mark_after_cents"] == 50_000

    # 5. Full withdrawal cleanly resets equity and HWM to 0
    wd_all = ledger.withdraw_member_capital("SCMA-UW", 40_000)
    assert wd_all["balance_cents"] == 0
    assert wd_all["high_water_mark_after_cents"] == 0


def test_settlement_engine_tracks_hwm_across_sequential_resolutions():
    ledger = CapitalLedger()
    ledger.register_member_account("SCMA-SEQ", seed_capital_cents=100_000)
    engine = SettlementEngine(ledger=ledger)

    # Loss: 100 contracts @ 50c cost = 5,000c, outcome NO -> -5,000c
    r1 = engine.resolve_contract("KX-TEST-1", "NO", quantity=100, cost_cents=5_000, member_scma="SCMA-SEQ")
    assert r1["net_pnl_cents"] == -5_000
    assert r1["waterfall"]["cfcp_shield_cents"] == 0
    assert r1["waterfall"]["faep_endowment_cents"] == 0
    assert r1["waterfall"]["high_water_mark_after_cents"] == 100_000

    # Partial recovery win: 40 contracts @ 25c cost = 1,000c, outcome YES -> +3,000c (still below HWM)
    r2 = engine.resolve_contract("KX-TEST-2", "YES", quantity=40, cost_cents=1_000, member_scma="SCMA-SEQ")
    assert r2["net_pnl_cents"] == 3_000
    assert r2["waterfall"]["recovery_cents"] == 3_000
    assert r2["waterfall"]["waterfall_eligible_cents"] == 0
    assert r2["waterfall"]["scma_reinvest_cents"] == 3_000
    assert r2["waterfall"]["cfcp_shield_cents"] == 0
    assert r2["waterfall"]["faep_endowment_cents"] == 0

    # Cross HWM: 50 contracts @ 20c cost = 1,000c, outcome YES -> +4,000c (2,000 recovery + 2,000 eligible)
    r3 = engine.resolve_contract("KX-TEST-3", "YES", quantity=50, cost_cents=1_000, member_scma="SCMA-SEQ")
    assert r3["net_pnl_cents"] == 4_000
    assert r3["waterfall"]["recovery_cents"] == 2_000
    assert r3["waterfall"]["waterfall_eligible_cents"] == 2_000
    assert r3["waterfall"]["scma_reinvest_cents"] == 2_000 + 1_740
    assert r3["waterfall"]["cfcp_shield_cents"] == 200
    assert r3["waterfall"]["faep_endowment_cents"] == 60
    assert r3["waterfall"]["high_water_mark_after_cents"] == 101_740


def test_yield_and_rebate_adapters_honor_adr012_drawdown_protection():
    ledger = CapitalLedger()
    ledger.register_member_account("SCMA-ADAPT", seed_capital_cents=1_000_000)
    # Put account in a -$100.00 drawdown
    ledger.settle_member_trade("SCMA-ADAPT", -10_000)

    # Maker rebate during drawdown stays 100% in SCMA
    rebate_adapter = MakerRebateLedgerAdapter(ledger=ledger)
    reb = rebate_adapter.process_maker_rebate("SCMA-ADAPT", 500, "KALSHI", "KX-1", "ORD-1")
    assert reb["waterfall_split"]["member_rebate_cents"] == 500
    assert reb["waterfall_split"]["central_family_pool_cents"] == 0
    assert reb["waterfall_split"]["founder_pool_cents"] == 0

    # Escrow yield during drawdown stays 100% in SCMA
    yield_adapter = PlatformYieldAdapter(ledger=ledger)
    yld = yield_adapter.accrue_broker_escrow_yield("SCMA-ADAPT", annual_yield_bps=500, elapsed_days=7.0)
    assert yld["gross_yield_cents"] > 0
    assert yld["scma_net_cents"] == yld["gross_yield_cents"]
    assert yld["cfcp_cents"] == 0
    assert yld["faep_cents"] == 0


def test_walk_forward_benchmark_honors_adr012_drawdown_recovery():
    sim = WalkForwardBenchmark(initial_capital_cents=10_000)
    # Loss tick followed by smaller recovery win tick
    ticks = [
        {"contract_id": "L1", "p_model": 0.70, "yes_ask": 0.50, "yes_bid": 0.44, "outcome": 0, "resting_bid": 0.40},
        {"contract_id": "W1", "p_model": 0.70, "yes_ask": 0.50, "yes_bid": 0.44, "outcome": 1, "resting_bid": 0.40},
    ]
    res = sim.run_simulation(ticks)
    wf = res["waterfall"]
    assert wf["member_scma_cents"] + wf["cfcp_cents"] + wf["faep_cents"] == wf["realized_profit_cents"]


def test_adr008_rejects_floats_and_booleans():
    with pytest.raises(TypeError, match="ADR-008"):
        calculate_hwm_waterfall_cents(100.0, 10_000, 10_000)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="ADR-008"):
        calculate_hwm_waterfall_cents(True, 10_000, 10_000)  # type: ignore[arg-type]


def test_account_model_and_alembic_002_migration_backfill_and_downgrade(tmp_path):
    acc = AccountModel(account_id="SCMA-ORM-1", user_id="U-1", balance_cents=250_000)
    assert acc.high_water_mark_cents == 250_000

    # Simulate an existing pre-ADR-012 SQLite DB with accounts lacking high_water_mark_cents
    db_file = tmp_path / "pre_adr012.db"
    conn = sqlite3.connect(db_file)
    conn.execute(
        "CREATE TABLE accounts (account_id VARCHAR PRIMARY KEY, user_id VARCHAR NOT NULL, balance_cents INTEGER DEFAULT 0)"
    )
    conn.execute("INSERT INTO accounts VALUES ('SCMA-OLD-1', 'U-1', 75000)")
    conn.commit()
    conn.close()

    db_url = f"sqlite:///{db_file.as_posix()}"
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", db_url)

    command.upgrade(cfg, "head")
    engine = create_engine(db_url)
    try:
        cols = {c["name"] for c in inspect(engine).get_columns("accounts")}
        assert "high_water_mark_cents" in cols
        with engine.connect() as c:
            row = c.exec_driver_sql("SELECT high_water_mark_cents FROM accounts WHERE account_id = 'SCMA-OLD-1'").fetchone()
            assert row == (75_000,)

        command.downgrade(cfg, "001_initial_schema")
        cols_down = {c["name"] for c in inspect(engine).get_columns("accounts")}
        assert "high_water_mark_cents" not in cols_down
    finally:
        engine.dispose()


def test_companion_and_manuals_reconciled_to_adr012_and_rule_a14():
    companion = (BACKEND_DIR / "app" / "static" / "companion.html").read_text(encoding="utf-8")
    assert "ADR-012" in companion
    assert "Rule A14" in companion
    assert "volatility tax" in companion
    assert 'id="drawdownCents"' in companion

    for manual_name in (
        "USER_QUICKSTART.md",
        "CLASS_F_FINANCIAL_MANUAL.md",
        "CLASS_T_TECHNICAL_MANUAL.md",
        "CHIEF_ADMIN_RUNBOOK.md",
    ):
        text = (REPO_ROOT / "docs" / "manuals" / manual_name).read_text(encoding="utf-8")
        assert "ADR-012" in text, f"{manual_name} missing ADR-012"
        assert "Rule A14" in text, f"{manual_name} missing Rule A14"
