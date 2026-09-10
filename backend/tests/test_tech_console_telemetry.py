import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_tech_console_renders_with_eviction_containers():
    response = client.get("/admin/tech")
    assert response.status_code == 200
    html = response.text

    assert "Technical Infrastructure Console" in html
    assert "dry-powder-status" in html
    assert "active-bids-count" in html
    assert "resting-orders-body" in html
    assert "eviction-history-body" in html
    assert "/api/v1/portal/telemetry" in html
