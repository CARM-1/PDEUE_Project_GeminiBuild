from fastapi.testclient import TestClient
from app.main import app
import pathlib

def get_repo_root() -> pathlib.Path:
    here = pathlib.Path(__file__).resolve()
    return here.parents[2] if (here.parents[2] / 'Dockerfile').exists() else pathlib.Path.cwd()

def test_healthz_endpoint_healthy():
    client = TestClient(app)
    res = client.get('/healthz')
    assert res.status_code == 200
    data = res.json()
    assert data['status'] == 'HEALTHY'
    assert data['circuit_breaker_tripped'] is False

def test_dockerfile_compliance():
    root = get_repo_root()
    df_path = root / 'Dockerfile'
    assert df_path.exists(), f'Dockerfile missing at {df_path}'
    content = df_path.read_text(encoding='utf-8')
    assert 'USER pdeue' in content, 'Root user must not run container'
    assert 'HEALTHCHECK' in content, 'Healthcheck missing from Dockerfile'
    assert 'python:3.12-slim' in content, 'Must use slim base'

def test_compose_compliance():
    root = get_repo_root()
    dc_path = root / 'docker-compose.yml'
    assert dc_path.exists(), f'docker-compose.yml missing at {dc_path}'
    content = dc_path.read_text(encoding='utf-8')
    assert 'pdeue-engine' in content
    assert '8000:8000' in content
