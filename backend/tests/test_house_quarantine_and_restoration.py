"""Iteration 3 acceptance coverage for branch-scoped quarantine controls."""
from fastapi.testclient import TestClient

from app.main import app
from app.domain.lineage_hierarchy import get_lineage_service
from app.domain.quarter_kelly_dispatcher import QuarterKellyDispatcher

client = TestClient(app)
HOUSE_2_SCMA = "SCMA-JULIAN_-A1F98B21"


def setup_function():
    service = get_lineage_service()
    service.restore_house(1)
    service.restore_house(2)
    # Ensure the order-revocation assertion starts with an open House 2 order.
    service.CANONICAL_HOUSES[2]["members"][0]["open_orders"] = ["POLY-239496"]


def teardown_function():
    get_lineage_service().restore_house(2)


def test_house_2_quarantine_is_surgically_isolated():
    house_1_before = client.get("/api/v1/lineage/house/1").json()

    response = client.post("/api/v1/lineage/house/2/freeze")

    assert response.status_code == 200
    house_2 = client.get("/api/v1/lineage/house/2").json()
    house_1 = client.get("/api/v1/lineage/house/1").json()
    assert house_2["status"] == "QUARANTINED"
    assert all(member["risk_dial"] == 0.0 for member in house_2["members"])
    assert all(member["open_orders"] == [] for member in house_2["members"])
    assert house_1["status"] == "ACTIVE"
    assert [m["risk_dial"] for m in house_1["members"]] == [
        m["risk_dial"] for m in house_1_before["members"]
    ]


def test_subordinate_restore_risk_does_not_lift_house_quarantine():
    client.post("/api/v1/lineage/house/2/freeze")

    response = client.post(
        "/api/v1/lineage/house/2/subordinate/restore-risk",
        json={"scma_id": HOUSE_2_SCMA, "target_risk_dial": 0.015},
    )

    assert response.status_code == 200
    assert response.json()["new_risk_dial"] == 0.015
    house_2 = client.get("/api/v1/lineage/house/2").json()
    assert house_2["status"] == "QUARANTINED"
    assert house_2["members"][0]["risk_dial"] == 0.015


def test_restore_house_2_clears_quarantine_and_restores_baseline():
    client.post("/api/v1/lineage/house/2/freeze")

    response = client.post("/api/v1/lineage/house/2/restore")

    assert response.status_code == 200
    house_2 = client.get("/api/v1/lineage/house/2").json()
    assert house_2["status"] == "ACTIVE"
    assert house_2["members"][0]["risk_dial"] > 0.0


def test_dispatcher_skips_only_quarantined_house():
    client.post("/api/v1/lineage/house/2/freeze")
    dispatcher = QuarterKellyDispatcher()
    args = dict(contract_ticker="TEST", venue="KALSHI", side="BUY_YES", market_price=.03, model_prob=.315)

    quarantined = dispatcher.dispatch_opportunity(target_house_id=2, **args)
    compliant = dispatcher.dispatch_opportunity(target_house_id=1, **args)

    assert quarantined["status"] == "SKIPPED_HOUSE_QUARANTINED"
    assert quarantined["total_quantity"] == 0
    assert compliant["status"] == "RESTING_MAKER"
    assert compliant["total_quantity"] > 0
