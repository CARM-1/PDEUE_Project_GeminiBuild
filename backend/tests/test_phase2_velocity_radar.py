import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_scan_worker_generates_radar_opportunities():
    res = client.get("/api/v1/operator/workspace-state")
    assert res.status_code == 200
    data = res.json()
    assert "radar_opportunities" in data
    opps = data["radar_opportunities"]
    assert len(opps) >= 2

    # Verify Kalshi & Polymarket presence
    venues = [o["venue"] for o in opps]
    assert "KALSHI" in venues
    assert "POLYMARKET" in venues

    # Verify 12-House Lineage Routing Tags
    lineage_codes = [o["lineage_code"] for o in opps]
    assert "HOUSE-01" in lineage_codes
    assert "HOUSE-02" in lineage_codes

    # Verify Net Edge barrier cleared
    for o in opps:
        assert o["net_edge"] >= 0.28
        assert o["status"] == "QUALIFIED"

def test_daemon_manual_cycle_endpoint():
    res = client.post("/api/v1/operator/daemon/cycle")
    assert res.status_code == 200
    ret = res.json()
    assert ret["cycle"] > 0
    assert ret["qualified_count"] >= 2
    assert "scanned_venues" in ret

def test_dashboard_contains_radar_table_target():
    res = client.get("/dashboard")
    assert res.status_code == 200
    assert 'id="radar-table-body"' in res.text
    assert "loadRadarOpportunities" in res.text
