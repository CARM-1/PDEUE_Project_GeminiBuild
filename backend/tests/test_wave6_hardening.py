import os
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health_check_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "HEALTHY"

def test_environment_defaults():
    env = os.getenv("APP_ENV", "development")
    assert env in ["development", "staging", "production"]
