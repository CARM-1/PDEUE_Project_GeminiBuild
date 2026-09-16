import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_inspect_position_detail():
    response = client.get("/api/v1/operator/positions/POLY-239496")
    assert response.status_code == 200
    data = response.json()
    assert data["contract_id"] == "POLY-239496"
    assert "risk_envelope" in data
    assert data["risk_envelope"]["sizing_rule"] == "Quarter-Kelly (0.25 f*)"
    assert len(data["action_cards"]) == 2
