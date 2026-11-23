"""Milestone B2-PREP verification tests for hardened fail-closed Lightsail paper/observation deployment."""
from __future__ import annotations

import json
import os
import pathlib
import re
import sqlite3
import subprocess
import sys
from typing import Any, Dict, List

import httpx
import pytest
from fastapi.testclient import TestClient

from app.adapters.live_l2_tape_recorder import verify_tape_manifest
from app.main import app
from scripts.observed_l2_collector import ObservedL2Collector, assert_fail_closed_paper_mode

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
DOCKERFILE_PATH = BACKEND_DIR / "Dockerfile"
RUNTIME_REQS_PATH = BACKEND_DIR / "requirements.runtime.txt"
ENTRYPOINT_PATH = REPO_ROOT / "deploy" / "entrypoint_paper.sh"
COMPOSE_PAPER_PATH = REPO_ROOT / "deploy" / "docker-compose.paper.yml"

SECRET_PATTERNS = (
    re.compile(r"(?i)(?:api_key|api_secret|private_key|secret_key|password|token)\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{12,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
)


def _assert_no_hardcoded_secrets(content: str, label: str) -> None:
    for pattern in SECRET_PATTERNS:
        assert not pattern.search(content), f"Potential hardcoded secret detected in {label}"


def test_b2_dockerfile_hardened_non_root_fail_closed_and_no_baked_db():
    assert DOCKERFILE_PATH.is_file(), "backend/Dockerfile must exist"
    assert RUNTIME_REQS_PATH.is_file(), "backend/requirements.runtime.txt must exist"

    df = DOCKERFILE_PATH.read_text(encoding="utf-8")
    req_lines = [
        line.strip().lower()
        for line in RUNTIME_REQS_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    reqs = "\n".join(req_lines)

    # Base image & Python runtime hygiene
    assert "FROM python:3.12-slim" in df
    assert "PYTHONDONTWRITEBYTECODE=1" in df
    assert "PYTHONUNBUFFERED=1" in df

    # Runtime-only deps (zero Playwright/Chromium/pytest bloat for 512 MB Lightsail)
    assert "requirements.runtime.txt" in df
    assert req_lines, "requirements.runtime.txt must declare runtime dependencies"
    for forbidden_pkg in ("playwright", "chromium", "pytest"):
        assert forbidden_pkg not in reqs, f"Dev dependency {forbidden_pkg!r} must not be in runtime requirements"

    # Fail-closed paper/observation ENV defaults
    assert "PDEUE_VENUE_MODE=paper" in df
    assert "PDEUE_LIVE_TRADING_ENABLED=false" in df
    assert "PDEUE_GOVERNANCE_MODE=EXECUTIVE_COMMAND" in df
    assert "DATABASE_URL=sqlite:////var/lib/pdeue/data/pdeue.db" in df

    # Non-root user & persistent host-volume mount directories
    assert "USER pdeue" in df
    assert "/var/lib/pdeue/data" in df
    assert "/var/lib/pdeue/tapes" in df

    # NEVER bake a static pdeue.db into the container image
    assert not re.search(r"(?im)^\s*(?:COPY|ADD)\b.*pdeue\.db", df), "Must never COPY/ADD pdeue.db into image"

    # Container healthcheck and entrypoint wiring
    assert "HEALTHCHECK" in df
    assert "http://127.0.0.1:8000/health" in df
    assert "entrypoint_paper.sh" in df
    _assert_no_hardcoded_secrets(df, "backend/Dockerfile")


def test_b2_entrypoint_script_contract_and_fail_closed_guards(tmp_path: pathlib.Path):
    assert ENTRYPOINT_PATH.is_file(), "deploy/entrypoint_paper.sh must exist"
    assert os.access(ENTRYPOINT_PATH, os.X_OK), "deploy/entrypoint_paper.sh must be executable"

    script = ENTRYPOINT_PATH.read_text(encoding="utf-8")
    assert "alembic upgrade head" in script
    assert "uvicorn app.main:app" in script
    assert "--workers 1" in script
    assert "PDEUE_VENUE_MODE" in script
    assert "PDEUE_LIVE_TRADING_ENABLED" in script
    _assert_no_hardcoded_secrets(script, "deploy/entrypoint_paper.sh")

    # Verify POSIX shell syntax
    syntax_res = subprocess.run(["sh", "-n", str(ENTRYPOINT_PATH)], capture_output=True, text=True, timeout=10)
    assert syntax_res.returncode == 0, syntax_res.stderr

    # 1. Fail-closed refusal when live venue mode is requested
    env_live_mode = os.environ.copy()
    env_live_mode.update({"PDEUE_VENUE_MODE": "live", "PDEUE_LIVE_TRADING_ENABLED": "false"})
    res_live = subprocess.run([str(ENTRYPOINT_PATH)], env=env_live_mode, capture_output=True, text=True, timeout=10)
    assert res_live.returncode != 0
    assert "FAIL-CLOSED" in res_live.stderr

    # 2. Fail-closed refusal when live trading flag is enabled
    env_live_flag = os.environ.copy()
    env_live_flag.update({"PDEUE_VENUE_MODE": "paper", "PDEUE_LIVE_TRADING_ENABLED": "true"})
    res_flag = subprocess.run([str(ENTRYPOINT_PATH)], env=env_live_flag, capture_output=True, text=True, timeout=10)
    assert res_flag.returncode != 0
    assert "FAIL-CLOSED" in res_flag.stderr

    # 3. Clean idempotent Alembic migration execution in paper mode against a fresh persistent SQLite path
    db_file = tmp_path / "data" / "pdeue.db"
    env_paper = os.environ.copy()
    env_paper.update(
        {
            "PDEUE_VENUE_MODE": "paper",
            "PDEUE_LIVE_TRADING_ENABLED": "false",
            "PDEUE_GOVERNANCE_MODE": "EXECUTIVE_COMMAND",
            "DATABASE_URL": f"sqlite:///{db_file}",
            "PDEUE_BACKEND_DIR": str(BACKEND_DIR),
            "PDEUE_ENTRYPOINT_MIGRATE_ONLY": "true",
            "PATH": f"{pathlib.Path(sys.executable).parent}:{os.environ.get('PATH', '')}",
        }
    )
    for _ in range(2):
        res_ok = subprocess.run([str(ENTRYPOINT_PATH)], env=env_paper, capture_output=True, text=True, timeout=30)
        assert res_ok.returncode == 0, f"stdout={res_ok.stdout}\nstderr={res_ok.stderr}"
    assert db_file.is_file(), "Alembic upgrade head must initialize persistent SQLite DB"

    with sqlite3.connect(db_file) as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"alembic_version", "accounting_outbox_events", "onboarding_members", "lineage_houses", "governance_config"} <= tables


def test_b2_docker_compose_paper_lightsail_tuning_and_fail_closed_defaults():
    assert COMPOSE_PAPER_PATH.is_file(), "deploy/docker-compose.paper.yml must exist"
    compose = COMPOSE_PAPER_PATH.read_text(encoding="utf-8")

    assert "dockerfile: backend/Dockerfile" in compose
    assert "restart: unless-stopped" in compose
    assert "read_only: true" in compose
    assert "no-new-privileges:true" in compose
    assert "mem_limit:" in compose
    assert "memswap_limit:" in compose
    assert "/var/lib/pdeue/data" in compose
    assert "/var/lib/pdeue/tapes" in compose
    assert "PDEUE_VENUE_MODE: paper" in compose
    assert 'PDEUE_LIVE_TRADING_ENABLED: "false"' in compose
    assert "PDEUE_GOVERNANCE_MODE: EXECUTIVE_COMMAND" in compose
    assert "DATABASE_URL: sqlite:////var/lib/pdeue/data/pdeue.db" in compose
    assert "pdeue-l2-collector:" in compose
    assert "http://127.0.0.1:8000/health" in compose
    _assert_no_hardcoded_secrets(compose, "deploy/docker-compose.paper.yml")


def test_b2_health_and_healthz_return_200_with_paper_mode_metadata(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PDEUE_VENUE_MODE", "paper")
    monkeypatch.setenv("PDEUE_LIVE_TRADING_ENABLED", "false")
    monkeypatch.setenv("PDEUE_GOVERNANCE_MODE", "EXECUTIVE_COMMAND")
    monkeypatch.setenv("PDEUE_GATE_G1_STATUS", "HOLD_OBSERVATIONS_ONLY")

    client = TestClient(app)

    for path in ("/health", "/healthz"):
        res = client.get(path)
        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "HEALTHY"
        assert body["healthy"] is True
        assert body["venue_mode"] == "paper"
        assert body["paper_mode"] is True
        assert body["live_trading_enabled"] is False
        assert body["governance_mode"] == "EXECUTIVE_COMMAND"
        assert body["gate_g1_status"] == "HOLD_OBSERVATIONS_ONLY"
        assert body["synthetic_fills_present"] is False

    assert client.get("/healthz").json()["circuit_breaker_tripped"] is False


def test_b2_observed_l2_collector_refuses_live_mode():
    assert assert_fail_closed_paper_mode({"PDEUE_VENUE_MODE": "paper", "PDEUE_LIVE_TRADING_ENABLED": "false"}) == "paper"
    assert assert_fail_closed_paper_mode({"PDEUE_VENUE_MODE": "observation", "PDEUE_LIVE_TRADING_ENABLED": "false"}) == "observation"

    with pytest.raises(RuntimeError, match="FAIL-CLOSED"):
        assert_fail_closed_paper_mode({"PDEUE_VENUE_MODE": "live", "PDEUE_LIVE_TRADING_ENABLED": "false"})

    with pytest.raises(RuntimeError, match="FAIL-CLOSED"):
        assert_fail_closed_paper_mode({"PDEUE_VENUE_MODE": "paper", "PDEUE_LIVE_TRADING_ENABLED": "true"})


def test_b2_observed_l2_collector_writes_verified_jsonl_and_survives_timeouts_and_429(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("PDEUE_VENUE_MODE", "observation")
    monkeypatch.setenv("PDEUE_LIVE_TRADING_ENABLED", "false")

    calls: Dict[str, int] = {"kalshi": 0, "poly": 0}
    seen_auth_headers: List[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        for hdr in ("authorization", "x-api-key", "kalshi-access-key", "poly-api-key"):
            if hdr in request.headers:
                seen_auth_headers.append(hdr)
        url = str(request.url)
        if "kalshi.com" in url and "/events" in url:
            return httpx.Response(
                200,
                json={"events": [{"markets": [{"ticker": "KX-B2-TEST", "volume_24h_fp": "1500.00"}]}]},
            )
        if "gamma-api.polymarket.com" in url:
            return httpx.Response(200, json=[{"clobTokenIds": '["POLY-B2-TOK"]'}])
        if "kalshi.com" in url:
            calls["kalshi"] += 1
            if calls["kalshi"] == 1:
                raise httpx.ReadTimeout("Simulated transient venue read timeout", request=request)
            return httpx.Response(
                200,
                json={"orderbook_fp": {"yes_dollars": [["0.4400", "200.00"]], "no_dollars": [["0.5300", "150.00"]]}},
            )
        if "clob.polymarket.com" in url:
            calls["poly"] += 1
            if calls["poly"] == 1:
                return httpx.Response(429, json={"error": "rate limited"}, request=request)
            return httpx.Response(
                200,
                json={"bids": [{"price": "0.38", "size": "320"}], "asks": [{"price": "0.41", "size": "280"}]},
            )
        return httpx.Response(404, request=request)

    sleeps: List[float] = []
    heartbeats_logged: List[str] = []
    mock_client = httpx.Client(transport=httpx.MockTransport(handler))

    collector = ObservedL2Collector(
        tmp_path / "tapes",
        kalshi_count=1,
        poly_count=1,
        interval_seconds=10.0,
        max_backoff_seconds=60.0,
        http_client=mock_client,
        sleep_fn=sleeps.append,
        log_fn=heartbeats_logged.append,
        session_id="session_b2_unit",
    )

    # Cycle 1: both venues experience transient timeout / 429 -> collector must NOT crash
    hb1 = collector.collect_once()
    assert hb1["status"] == "WAITING_ON_VENUE"
    assert hb1["cycle_snapshots"] == 0
    assert hb1["cycle_errors_count"] == 2
    assert hb1["rate_limited"] is True
    assert hb1["consecutive_errors"] == 1
    assert hb1["synthetic_fills_present"] is False

    # Cycle 2 (via run): both venues recover -> writes verified OBSERVED_L2 JSONL + SHA-256 manifest
    hb2 = collector.run(max_cycles=2)
    assert hb2["status"] == "HEALTHY"
    assert hb2["cycle"] == 2
    assert hb2["cycle_snapshots"] == 2
    assert hb2["snapshots_total"] == 2
    assert hb2["consecutive_errors"] == 0
    assert hb2["data_provenance"] == "OBSERVED_L2"
    assert hb2["synthetic_fills_present"] is False
    assert len(hb2["tape_manifest_sha256"]) == 64

    # Zero private API credentials sent
    assert seen_auth_headers == []

    # Heartbeat file persisted on disk and valid JSON
    hb_disk = json.loads((tmp_path / "tapes" / "collector_heartbeat.json").read_text(encoding="utf-8"))
    assert hb_disk["snapshots_total"] == 2
    assert len(heartbeats_logged) == 2

    # Sealed tape passes strict SHA-256 + integer-cent + zero-synthetic verification
    manifest = verify_tape_manifest(collector.session_dir / "tape_manifest.json", require_non_empty_book=True)
    assert manifest["snapshot_count"] == 2
    assert manifest["venues"] == ["KALSHI", "POLYMARKET"]
    assert manifest["synthetic_fills_present"] is False

    tape_lines = [
        json.loads(line)
        for line in (collector.session_dir / "tape.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(tape_lines) == 2
    for snap in tape_lines:
        assert snap["data_provenance"] == "OBSERVED_L2"
        assert snap["bids"] and snap["asks"]
