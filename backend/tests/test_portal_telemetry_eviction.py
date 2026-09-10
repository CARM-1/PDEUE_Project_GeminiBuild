import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.api.v1.portal_router import _GLOBAL_EVICTION_MGR, _GLOBAL_LEDGER, _GLOBAL_WORKER

client = TestClient(app)

def test_portal_telemetry_includes_eviction_metrics():
    # Register resting order to verify telemetry visibility
    _GLOBAL_EVICTION_MGR.register_resting_order(
        order_id="REST-TEL-01",
        ticker="KX-WEATHER-HIGH",
        domain="WEATHER",
        net_edge=0.08,
        stake_cents=400
    )

    response = client.get("/api/v1/portal/telemetry")
    assert response.status_code == 200
    data = response.json()

    assert "worker_status" in data
    assert "eviction_engine" in data
    assert "capital_headroom" in data
    assert "yield_adapter" in data

    evict_data = data["eviction_engine"]
    assert evict_data["max_concurrent_orders"] == 5
    assert evict_data["active_resting_bids_count"] >= 1
    assert evict_data["preemption_alpha_threshold"] == 0.20
    assert evict_data["max_expiry_hours"] == 6.0

    # Verify dry powder headroom calculations
    headroom = data["capital_headroom"]
    assert headroom["total_equity_cents"] == 10000
    assert headroom["dry_powder_floor_cents"] == 4000
    assert headroom["dry_powder_compliant"] is True

    # Test preemption eviction recording
    _GLOBAL_EVICTION_MGR.execute_eviction("REST-TEL-01", reason="ALPHA_PREEMPTION")
    
    resp_after = client.get("/api/v1/portal/telemetry")
    data_after = resp_after.json()
    assert len(data_after["eviction_engine"]["recent_evictions"]) >= 1
    assert data_after["eviction_engine"]["recent_evictions"][-1]["order_id"] == "REST-TEL-01"
