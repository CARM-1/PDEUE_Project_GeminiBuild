"""Play #9 verification: 12-category FleetCategoryRegistry & CFTC 150.4 ContractMutexRegistry wired into scan_worker."""
import pytest

from app.domain.fleet_bridge import (
    ContractCollisionError,
    FleetMutexCoordinator,
    HouseholdAffinityCollisionError,
)
from app.domain.scan_worker import AutonomousScanWorker


def test_all_12_fleet_categories_registered_and_resolvable():
    coord = FleetMutexCoordinator()
    cats = coord.list_categories()
    assert len(cats) == 12
    assert set(cats.keys()) == set(range(1, 13))
    for cid in range(1, 13):
        resolved = coord.resolve_category(cid)
        assert resolved["category_id"] == cid
        assert resolved["name"] == cats[cid]["name"]
    assert coord.resolve_category("WEATHER")["category_id"] == 1
    assert coord.resolve_category("CRYPTO")["category_id"] == 10
    with pytest.raises(ValueError, match="Unknown fleet category"):
        coord.resolve_category("NOT_A_REAL_CATEGORY")


def test_scan_worker_exposes_fleet_and_mutex_telemetry():
    worker = AutonomousScanWorker(execution_mode="PAPER")
    res = worker.run_single_cycle()
    assert res["status"] == "COMPLETED"
    assert res["fleet_categories_registered"] == 12
    assert res["active_mutex_locks"] == 4
    assert res["mutex_blocked"] == []
    assert res["gate_g1_status"] == "HOLD_OBSERVATIONS_ONLY"
    tel = worker.get_telemetry()
    assert tel["fleet_categories_registered"] == 12
    assert tel["active_mutex_locks"] == 4


def test_cross_account_contract_collision_fails_closed_in_scan_cycle():
    worker = AutonomousScanWorker(execution_mode="PAPER")
    opp_a = worker._opportunity("KX-COLLIDE-01", "KALSHI", "WEATHER", 1)
    opp_a["scma_id"] = "SCMA-FOUNDER"
    opp_b = worker._opportunity("KX-COLLIDE-01", "KALSHI", "WEATHER", 2)
    opp_b["scma_id"] = "SCMA-MEM-0002"
    worker.latest_opportunities = [opp_a, opp_b]

    res = worker.run_single_cycle()
    assert res["status"] == "COMPLETED"
    assert len(res["mutex_blocked"]) == 1
    assert "CONTRACT_COLLISION" in res["mutex_blocked"][0]["reason"]
    assert res["mutex_blocked"][0]["scma_id"] == "SCMA-MEM-0002"


def test_cftc_150_4_household_1_affinity_collision_fails_closed():
    worker = AutonomousScanWorker(execution_mode="PAPER")
    opp_founder = worker._opportunity("KX-CPI-NOV-3.0", "KALSHI", "MACRO_INFLATION_CPI", 1)
    opp_founder["scma_id"] = "SCMA-FOUNDER"
    opp_founder["series_ticker"] = "KXCPI-26NOV"

    opp_cohabitant = worker._opportunity("KX-CPI-NOV-3.2", "KALSHI", "MACRO_INFLATION_CPI", 1)
    opp_cohabitant["scma_id"] = "SCMA-MEM-0001"
    opp_cohabitant["series_ticker"] = "KXCPI-26NOV"

    worker.latest_opportunities = [opp_founder, opp_cohabitant]
    res = worker.run_single_cycle()
    assert len(res["mutex_blocked"]) == 1
    assert "HOUSEHOLD_AFFINITY_COLLISION" in res["mutex_blocked"][0]["reason"]
    assert res["mutex_blocked"][0]["scma_id"] == "SCMA-MEM-0001"


def test_observations_only_candidates_are_blocked_while_gate_g1_on_hold():
    worker = AutonomousScanWorker(execution_mode="PAPER")
    opp = worker._opportunity("KX-OBS-ONLY-1", "KALSHI", "WEATHER", 1)
    opp["data_provenance"] = "OBSERVATIONS_ONLY"
    worker.latest_opportunities = [opp]

    res = worker.run_single_cycle()
    assert len(res["mutex_blocked"]) == 1
    assert res["mutex_blocked"][0]["reason"] == "GATE_G1_OBSERVATIONS_ONLY_HOLD"
    assert res["active_mutex_locks"] == 0


def test_mutex_lock_release_and_expiry_reaping():
    coord = FleetMutexCoordinator()
    coord.acquire_contract_lock("KX-TTL-1", "KALSHI", "SCMA-FOUNDER", 1, ttl_seconds=60)
    with pytest.raises(ContractCollisionError):
        coord.acquire_contract_lock("KX-TTL-1", "KALSHI", "SCMA-MEM-0002", 1, ttl_seconds=60)
    assert coord.release_contract_lock("KX-TTL-1", "SCMA-FOUNDER") is True
    coord.acquire_contract_lock("KX-TTL-1", "KALSHI", "SCMA-MEM-0002", 1, ttl_seconds=-1)
    assert coord.reap_expired() >= 1
    assert coord.active_lock_count() == 0
