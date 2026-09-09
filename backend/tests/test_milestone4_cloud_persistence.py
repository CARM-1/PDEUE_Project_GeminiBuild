import json
import pathlib
import pytest
from app.db.models import AccountModel, TenantModel
from fastapi.testclient import TestClient
from app.main import app

def test_milestone4_container_and_ecs_manifest_integrity():
    """Validates Dockerfile non-root security context and ECS Fargate task definitions."""
    root = pathlib.Path(__file__).resolve().parents[2]
    
    # 1. AWS ECS Fargate task definition conformance
    task_def_path = root / "deploy" / "ecs" / "task-definition.json"
    assert task_def_path.exists(), "ECS task definition must exist"
    task_def = json.loads(task_def_path.read_text(encoding="utf-8"))
    assert "containerDefinitions" in task_def
    container = task_def["containerDefinitions"][0]
    assert container["name"] in ["pdeue-core-engine", "pdeue-engine"]
    assert "image" in container
    assert "secrets" in container or "environment" in container

    # 2. Dockerfile production packaging conformance
    dockerfile_path = root / "Dockerfile"
    assert dockerfile_path.exists(), "Dockerfile must exist"
    dockerfile_content = dockerfile_path.read_text(encoding="utf-8")
    assert "USER pdeue" in dockerfile_content
    assert "python:3.12-slim" in dockerfile_content

    # 3. Docker compose service conformance
    compose_path = root / "docker-compose.yml"
    assert compose_path.exists(), "docker-compose.yml must exist"
    compose_content = compose_path.read_text(encoding="utf-8")
    assert "pdeue-engine" in compose_content

def test_milestone4_fail_closed_health_endpoint():
    """Validates container health probe endpoint (/healthz)."""
    client = TestClient(app)
    res = client.get("/healthz")
    assert res.status_code == 200
    data = res.json()
    assert data.get("status") in ["HEALTHY", "healthy", "OK", "ok"]

def test_milestone4_persistence_models_and_alembic_spine():
    """Validates relational ORM models and Alembic migration directory layout."""
    root = pathlib.Path(__file__).resolve().parents[2]
    alembic_ini = root / "backend" / "alembic.ini"
    alembic_dir = root / "backend" / "alembic"
    assert alembic_ini.exists(), "alembic.ini must exist"
    assert alembic_dir.exists(), "Alembic migration directory must exist"

    # AccountModel mapping verification
    acc = AccountModel(
        account_id="ACC-M4-01",
        user_id="USR-M4-01",
        account_name="Cloud Persistence Test Account",
        balance_cents=5000000
    )
    assert acc.account_id == "ACC-M4-01"
    assert acc.balance_cents == 5000000

    # TenantModel mapping verification using introspection
    col_names = [c.name for c in TenantModel.__table__.columns]
    tenant_kwargs = {"tenant_id": "TENANT-M4-01"}
    if "name" in col_names:
        tenant_kwargs["name"] = "Alpha Cloud Tenant"
    elif "tenant_name" in col_names:
        tenant_kwargs["tenant_name"] = "Alpha Cloud Tenant"
    if "jurisdiction" in col_names:
        tenant_kwargs["jurisdiction"] = "USA"

    tenant = TenantModel(**tenant_kwargs)
    assert tenant.tenant_id == "TENANT-M4-01"
