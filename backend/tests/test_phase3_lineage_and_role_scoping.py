import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.domain.lineage_hierarchy import LineageHierarchyService

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

def test_house_leader_cancel_subordinate_orders():
    res = client.post(
        "/api/v1/lineage/house/1/subordinate/cancel-orders",
        json={"scma_id": "SCMA-FOUNDER_-C8575D7E"}
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "SUBORDINATE_ORDERS_CANCELLED"
    assert "KX-MIA-FRZ-32" in data["cancelled_orders"]

def test_house_leader_freeze_subordinate_risk():
    res = client.post(
        "/api/v1/lineage/house/1/subordinate/freeze-risk",
        json={"scma_id": "SCMA-FOUNDER_-C8575D7E"}
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "SUBORDINATE_RISK_FROZEN"
    assert data["new_risk_dial"] == 0.0
    assert data["member_status"] == "FROZEN_BY_HOUSE_LEADER"

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
