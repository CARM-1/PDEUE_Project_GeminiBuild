from fastapi.testclient import TestClient
from app.main import app
import pathlib

def test_healthz_endpoint_healthy():
    client = TestClient(app)
    res = client.get('/healthz')
    assert res.status_code == 200
    data = res.json()
    assert data['status'] == 'HEALTHY'
    assert data['circuit_breaker_tripped'] is False

def test_dockerfile_compliance():
    df_path = pathlib.Path('Dockerfile')
    assert df_path.exists(), 'Dockerfile missing'
    content = df_path.read_text(encoding='utf-8')
    assert 'USER pdeue' in content, 'Root user must not run container'
    assert 'HEALTHCHECK' in content, 'Healthcheck missing from Dockerfile'
    assert 'python:3.12-slim' in content, 'Must use slim base'

def test_compose_compliance():
    dc_path = pathlib.Path('docker-compose.yml')
    assert dc_path.exists(), 'docker-compose.yml missing'
    content = dc_path.read_text(encoding='utf-8')
    assert 'pdeue-engine' in content
    assert '8000:8000' in content
