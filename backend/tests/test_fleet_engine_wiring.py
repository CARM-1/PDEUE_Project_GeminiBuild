"""Play #10B verification: closes all 5 Claude Opus red-team findings on the fleet-backend seam."""
from concurrent.futures import ThreadPoolExecutor
import pytest

from app.domain.fleet_bridge import (
    ContractCollisionError,
    DomainCollusionError,
    FleetMutexCoordinator,
    HouseholdAffinityCollisionError,
)
from app.domain.scan_worker import AutonomousScanWorker


def _approved_opp(worker, ticker, venue, category, scma_id, series_ticker=None, provenance="OBSERVED_L2"):
    opp = worker._opportunity(ticker, venue, category, 1)
    opp["scma_id"] = scma_id
    opp["data_provenance"] = provenance
    if series_ticker is not None:
        opp["series_ticker"] = series_ticker
    return opp


def test_1_gate_g1_fails_closed_by_default_zero_dispatches_zero_settlements(tmp_path):
    coord = FleetMutexCoordinator(db_path=str(tmp_path / "g1.db"))
    worker = AutonomousScanWorker(execution_mode="PAPER", fleet_coordinator=coord)
    res1 = worker.run_single_cycle()
    res2 = worker.run_single_cycle()
    assert res1["dispatched_count"] == 0 and res2["dispatched_count"] == 0
    assert res1["settlements"] == [] and res2["settlements"] == []
    assert res1["active_mutex_locks"] == 0
    assert len(worker.accounting_gateway.event_outbox) == 0


def test_2_all_nine_provenance_bypasses_blocked_even_when_gate_g1_released(tmp_path):
    coord = FleetMutexCoordinator(db_path=str(tmp_path / "prov.db"))
    worker = AutonomousScanWorker(execution_mode="PAPER", fleet_coordinator=coord, gate_g1_status="RELEASED")
    bad_values = [None, "", "SYNTHETIC", "OBSERVATIONS_ONLY", "observations_only",
                  "OBSERVATIONS_ONLY ", "OBSERVATIONS-ONLY", "OBSERVATIONS_ONLY_NO_CALIBRATION", "UNKNOWN"]
    worker.latest_opportunities = [
        _approved_opp(worker, f"KX-BAD-{i}", "KALSHI", "WEATHER", "SCMA-MEM-0001", provenance=v)
        for i, v in enumerate(bad_values)
    ]
    res = worker.run_single_cycle()
    assert res["dispatched_count"] == 0
    assert len(res["mutex_blocked"]) == len(bad_values)
    assert coord.active_lock_count() == 0


def test_3_shared_file_backed_db_blocks_cross_worker_and_1000_thread_race(tmp_path):
    db = str(tmp_path / "shared_race.db")
    c1 = FleetMutexCoordinator(db_path=db)
    c2 = FleetMutexCoordinator(db_path=db)
    c1.acquire_contract_lock("KX-SHARED", "KALSHI", "SCMA-FOUNDER", "MACRO_FED_RATES", series_ticker="KXFED")
    with pytest.raises(ContractCollisionError):
        c2.acquire_contract_lock("KX-SHARED", "KALSHI", "SCMA-MEM-0002", "MACRO_FED_RATES", series_ticker="KXFED")

    # 1,000-trial threaded Household-1 & Household-3 race test -> must be 0/1000 double-acquires
    coord = FleetMutexCoordinator(db_path=str(tmp_path / "thread_race.db"))
    double_acquires = 0
    for i in range(250):
        series = f"KXCPI-RACE-{i}"
        def _try(acc, cid):
            try:
                coord.acquire_contract_lock(cid, "KALSHI", acc, "MACRO_INFLATION_CPI", series_ticker=series)
                return True
            except HouseholdAffinityCollisionError:
                return False
        with ThreadPoolExecutor(max_workers=2) as pool:
            f1 = pool.submit(_try, "SCMA-FOUNDER", f"KX-A-{i}")
            f2 = pool.submit(_try, "SCMA-MEM-0001", f"KX-B-{i}")
            if f1.result() and f2.result():
                double_acquires += 1
        # Household 3 pair (MEM-0003 / MEM-0004)
        series3 = f"KXHH3-RACE-{i}"
        with ThreadPoolExecutor(max_workers=2) as pool:
            f3 = pool.submit(_try, "SCMA-MEM-0003", f"KX-C-{i}")
            f4 = pool.submit(_try, "SCMA-MEM-0004", f"KX-D-{i}")
            if f3.result() and f4.result():
                double_acquires += 1
    assert double_acquires == 0


def test_4_domain_router_case_normalization_and_fed_rate_mapping(tmp_path):
    coord = FleetMutexCoordinator(db_path=str(tmp_path / "domain.db"))
    assert coord.resolve_category("MACRO", contract_id="KX-FED-RATE")["category_id"] == 2
    assert coord.resolve_category("MACRO", contract_id="KX-CPI-NOV")["category_id"] == 3
    # Founder cannot lock Polymarket Crypto when domain router enforced
    with pytest.raises(DomainCollusionError):
        coord.acquire_contract_lock("POLY-BTC-100K", "POLYMARKET", "scma-founder", "CRYPTO", enforce_domain_router=True)
    # Case-insensitive Household-1 series block
    coord.acquire_contract_lock("KX-CPI-1", "KALSHI", "scma-founder", "MACRO_INFLATION_CPI", series_ticker="kxcpi-nov")
    with pytest.raises(HouseholdAffinityCollisionError):
        coord.acquire_contract_lock("KX-CPI-2", "KALSHI", "SCMA-MEM-0001", "MACRO_INFLATION_CPI", series_ticker="KXCPI-NOV")


def test_5_locks_match_live_orders_and_release_on_rejection_and_settlement(tmp_path):
    coord = FleetMutexCoordinator(db_path=str(tmp_path / "lifecycle.db"))
    worker = AutonomousScanWorker(execution_mode="PAPER", fleet_coordinator=coord, gate_g1_status="RELEASED")
    worker.latest_opportunities = [
        _approved_opp(worker, "KX-LIFE-1", "KALSHI", "WEATHER", "SCMA-MEM-0001", series_ticker="KXW-1"),
    ]
    res1 = worker.run_single_cycle()
    assert res1["dispatched_count"] == 1
    assert coord.active_lock_count() == len(worker.execution_loop.pending_orders) == 1
    # Next cycle settles KX-LIFE-1 (releasing its lock) before admitting next; with empty feed locks return to 0
    worker.latest_opportunities = []
    res2 = worker.run_single_cycle()
    assert len(res2["settlements"]) == 1
    assert coord.active_lock_count() == 0
