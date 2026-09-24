import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.domain.lineage_hierarchy import LineageHierarchyService
from app.api.v1.lineage_router import _lineage_service

client = TestClient(app)

def test_lineage_hierarchy_12_houses_initialization():
    svc = LineageHierarchyService()
    houses = svc.list_all_houses()
    assert len(houses) == 12
    assert houses[0]["lineage_code"] == "HOUSE-01"
    assert houses[11]["lineage_code"] == "HOUSE-12"

def test_house_1_founder_capital_aggregation():
    svc = LineageHierarchyService()
    h1 = svc.get_house_summary(1)
    assert h1["lineage_code"] == "HOUSE-01"
    assert h1["member_count"] == 2
    assert h1["total_cash_cents"] == 625000
    assert h1["total_cash_formatted"] == "$6,250.00"

def test_house_leader_ui_contains_institutional_modals_and_zero_native_prompts():
    """Validates that native browser alert/confirm calls are removed and institutional modals exist."""
    res = client.get("/lineage/house/1")
    assert res.status_code == 200
    html = res.text

    # 1. Assert Modal Containers Exist in DOM
    assert 'id="cancel-modal"' in html
    assert 'id="freeze-modal"' in html

    # 2. Assert Modal Triggers Exist on Buttons
    assert "openCancelModal" in html
    assert "openFreezeModal" in html

    # 3. Assert Blocking Native Prompts Are Completely Removed
    assert "confirm(" not in html
    assert "alert(" not in html

def test_sovereign_order_cancellation_is_rejected_end_to_end():
    """Proves subordinate order revocation cannot affect the Sovereign Settlor."""
    founder = _lineage_service.CANONICAL_HOUSES[1]["members"][0]
    founder["open_orders"] = ["KX-MIA-FRZ-32"]
    # 1. Execute cancel action
    res = client.post(
        "/api/v1/lineage/house/1/subordinate/cancel-orders",
        json={"scma_id": "SCMA-FOUNDER_-C8575D7E"}
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "SOVEREIGN_IMMUNE"

    # 2. Query House State to certify database/domain state is updated
    state_res = client.get("/api/v1/lineage/house/1")
    assert state_res.status_code == 200
    h1 = state_res.json()
    founder = next(m for m in h1["members"] if m["scma_id"] == "SCMA-FOUNDER_-C8575D7E")
    assert founder["open_orders"] == ["KX-MIA-FRZ-32"]

def test_sovereign_risk_freeze_is_rejected_end_to_end():
    """Proves subordinate risk clamps cannot affect the Sovereign Settlor."""
    founder = _lineage_service.CANONICAL_HOUSES[1]["members"][0]
    founder["risk_dial"] = 0.02
    founder["status"] = "ACTIVE"
    # 1. Execute freeze action
    res = client.post(
        "/api/v1/lineage/house/1/subordinate/freeze-risk",
        json={"scma_id": "SCMA-FOUNDER_-C8575D7E"}
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "SOVEREIGN_IMMUNE"
    assert data["new_risk_dial"] == 0.02

    # 2. Query House State to certify domain state
    state_res = client.get("/api/v1/lineage/house/1")
    assert state_res.status_code == 200
    h1 = state_res.json()
    founder = next(m for m in h1["members"] if m["scma_id"] == "SCMA-FOUNDER_-C8575D7E")
    assert founder["risk_dial"] == 0.02
    assert founder["status"] == "ACTIVE"

def test_bicameral_75_percent_consensus_rule():
    svc = LineageHierarchyService()
    res_8 = svc.evaluate_bicameral_proposal([1, 2, 3, 4, 5, 6, 7, 8])
    assert res_8["ratified"] is False
    assert res_8["status"] == "QUORUM_REJECTED"

    res_9 = svc.evaluate_bicameral_proposal([1, 2, 3, 4, 5, 6, 7, 8, 9])
    assert res_9["ratified"] is True
    assert res_9["status"] == "RATIFIED"

def test_house_leader_ui_is_branch_scoped_without_global_hub_ribbon():
    res = client.get("/lineage/house/1")
    assert res.status_code == 200
    assert "CLASS H SOVEREIGN DESK" in res.text
    assert "HOUSE-01" in res.text
    assert "FULL BIDIRECTIONAL NAVIGATION" not in res.text
    assert "Technical Console (Class T)" not in res.text
