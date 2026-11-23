"""Milestone B2-PREP verification tests for hardened fail-closed Lightsail paper/observation deployment."""
from __future__ import annotations

import json
import os
import pathlib
import re
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import httpx
import pytest
from fastapi.testclient import TestClient

from app.adapters.live_l2_tape_recorder import (
    discover_liquid_polymarket_tokens,
    extract_polymarket_clob_token_ids,
    verify_tape_manifest,
)
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


def test_b2_collector_compose_healthcheck_verifies_heartbeat_not_port_8000(tmp_path: pathlib.Path):
    compose = COMPOSE_PAPER_PATH.read_text(encoding="utf-8")
    api_block, sep, collector_block = compose.partition("\n  pdeue-l2-collector:\n")
    assert sep, "deploy/docker-compose.paper.yml must define pdeue-l2-collector service"

    # pdeue-api keeps its HTTP /health check
    assert "http://127.0.0.1:8000/health" in api_block

    # pdeue-l2-collector overrides inherited Dockerfile healthcheck with heartbeat check (not port 8000)
    assert "\n    healthcheck:\n" in collector_block
    hc_section = collector_block.split("\n    healthcheck:\n", 1)[1].split("\n    logging:\n", 1)[0]
    assert "8000" not in hc_section, "Collector healthcheck must not probe HTTP port 8000"
    assert "/health" not in hc_section, "Collector healthcheck must not probe HTTP /health"
    assert "python3" in hc_section
    assert "/var/lib/pdeue/tapes/collector_heartbeat.json" in hc_section
    assert "timestamp_utc" in hc_section
    assert "180" in hc_section
    assert "consecutive_errors" in hc_section

    match = re.search(r'test:\s*\["CMD",\s*"python3",\s*"-c",\s*"([^"]+)"\]', hc_section)
    assert match, "Collector healthcheck must use a concise python3 -c one-liner"
    one_liner = match.group(1)

    hb_file = tmp_path / "collector_heartbeat.json"
    probe_code = one_liner.replace("/var/lib/pdeue/tapes/collector_heartbeat.json", str(hb_file))

    def _run_probe() -> int:
        return subprocess.run(
            [sys.executable, "-c", probe_code],
            capture_output=True,
            text=True,
            timeout=10,
        ).returncode

    # 1. Missing heartbeat file -> unhealthy
    assert _run_probe() != 0

    # 2. Invalid JSON -> unhealthy
    hb_file.write_text("{not valid json", encoding="utf-8")
    assert _run_probe() != 0

    # 3. Fresh valid heartbeat with consecutive_errors < 5 -> healthy
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    hb_file.write_text(
        json.dumps({"timestamp_utc": now_iso, "consecutive_errors": 0, "status": "HEALTHY"}),
        encoding="utf-8",
    )
    assert _run_probe() == 0

    # 4. Stale heartbeat (> 180s old) -> unhealthy
    stale_iso = (datetime.now(timezone.utc) - timedelta(seconds=240)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    hb_file.write_text(
        json.dumps({"timestamp_utc": stale_iso, "consecutive_errors": 0, "status": "HEALTHY"}),
        encoding="utf-8",
    )
    assert _run_probe() != 0

    # 5. Fresh heartbeat with consecutive_errors >= 5 -> unhealthy
    hb_file.write_text(
        json.dumps({"timestamp_utc": now_iso, "consecutive_errors": 5, "status": "WAITING_ON_VENUE"}),
        encoding="utf-8",
    )
    assert _run_probe() != 0


def test_b2_polymarket_discovery_preserves_uint256_and_recovers_from_404(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("PDEUE_VENUE_MODE", "observation")
    monkeypatch.setenv("PDEUE_LIVE_TRADING_ENABLED", "false")

    dead_404_tok = "10639244265485390123456789012345678901234567890123456789012345678901234567890"
    resolved_midrun_tok = "20987654321098765432109876543210987654321098765432109876543210987654321098765"
    live_tok_a = "31111111111111111111111111111111111111111111111111111111111111111111111111111"
    live_tok_b = "42222222222222222222222222222222222222222222222222222222222222222222222222222"
    disabled_book_tok = "53333333333333333333333333333333333333333333333333333333333333333333333333333"

    # Full uint256 string parsing without truncation
    assert extract_polymarket_clob_token_ids(json.dumps([dead_404_tok, live_tok_a])) == [dead_404_tok, live_tok_a]
    assert len(extract_polymarket_clob_token_ids([live_tok_a])[0]) == 77

    state = {"resolved_midrun": False}
    gamma_queries: List[Dict[str, str]] = []
    queried_poly_book_tokens: List[str] = []
    seen_auth_headers: List[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        for hdr in ("authorization", "x-api-key", "kalshi-access-key", "poly-api-key"):
            if hdr in request.headers:
                seen_auth_headers.append(hdr)
        url = str(request.url)
        if "kalshi.com" in url and "/events" in url:
            return httpx.Response(
                200,
                json={"events": [{"markets": [{"ticker": "KX-B2-LIVE", "volume_24h_fp": "2500.00"}]}]},
            )
        if "kalshi.com" in url:
            return httpx.Response(
                200,
                json={"orderbook_fp": {"yes_dollars": [["0.4600", "250.00"]], "no_dollars": [["0.5100", "180.00"]]}},
            )
        if "gamma-api.polymarket.com" in url:
            gamma_queries.append(dict(request.url.params))
            return httpx.Response(
                200,
                json=[
                    {"active": True, "closed": False, "enableOrderBook": False, "clobTokenIds": json.dumps([disabled_book_tok])},
                    {"active": True, "closed": False, "enableOrderBook": True, "clobTokenIds": json.dumps([dead_404_tok])},
                    {"active": True, "closed": False, "enableOrderBook": True, "clobTokenIds": json.dumps([resolved_midrun_tok])},
                    {"active": True, "closed": False, "enableOrderBook": True, "clobTokenIds": json.dumps([live_tok_a])},
                    {"active": True, "closed": False, "enableOrderBook": True, "clobTokenIds": json.dumps([live_tok_b])},
                ],
            )
        if "clob.polymarket.com" in url and "/book" in url:
            tok = request.url.params.get("token_id", "")
            queried_poly_book_tokens.append(tok)
            if tok == dead_404_tok or (tok == resolved_midrun_tok and state["resolved_midrun"]):
                return httpx.Response(404, json={"error": "No orderbook exists for the requested token id"}, request=request)
            if tok in {resolved_midrun_tok, live_tok_a, live_tok_b}:
                return httpx.Response(
                    200,
                    json={"bids": [{"price": "0.42", "size": "500"}], "asks": [{"price": "0.45", "size": "450"}]},
                    request=request,
                )
            return httpx.Response(404, request=request)
        return httpx.Response(404, request=request)

    collector = ObservedL2Collector(
        tmp_path / "tapes",
        kalshi_count=1,
        poly_count=2,
        interval_seconds=0.0,
        rediscover_every_cycles=30,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        log_fn=lambda _msg: None,
        session_id="session_b2_poly_404_recovery",
    )

    try:
        # Cycle 1: Discovery filters out disabled book & initial HTTP 404 token, locks in full uint256 tokens
        hb1 = collector.collect_once()
        assert hb1["status"] == "HEALTHY"
        assert hb1["cycle_errors_count"] == 0
        assert hb1["cycle_snapshots"] == 3
        assert collector.poly_tokens == [resolved_midrun_tok, live_tok_a]
        assert gamma_queries[0]["active"] == "true"
        assert gamma_queries[0]["closed"] == "false"
        assert gamma_queries[0]["enableOrderBook"] == "true"
        assert disabled_book_tok not in queried_poly_book_tokens
        assert all(len(tok) == 77 for tok in queried_poly_book_tokens)

        # Cycle 2: Market resolves -> resolved_midrun_tok starts returning HTTP 404
        state["resolved_midrun"] = True
        hb2 = collector.collect_once()
        assert hb2["status"] == "DEGRADED"
        assert hb2["cycle_errors_count"] == 1
        assert hb2["cycle_snapshots"] == 2
        assert hb2["consecutive_errors"] == 0
        assert resolved_midrun_tok not in collector.poly_tokens

        # Cycle 3: Collector automatically refreshes discovery on next cycle (does NOT wait 30 cycles)
        hb3 = collector.collect_once()
        assert hb3["status"] == "HEALTHY"
        assert hb3["cycle_errors_count"] == 0
        assert hb3["cycle_snapshots"] == 3
        assert collector.poly_tokens == [live_tok_a, live_tok_b]

        # Cycle 4: Remains HEALTHY and never re-polls resolved 404 token
        before_c4 = len(queried_poly_book_tokens)
        hb4 = collector.collect_once()
        assert hb4["status"] == "HEALTHY"
        assert hb4["cycle_errors_count"] == 0
        assert resolved_midrun_tok not in queried_poly_book_tokens[before_c4:]
    finally:
        collector.close()

    assert seen_auth_headers == []
    manifest = verify_tape_manifest(collector.session_dir / "tape_manifest.json", require_non_empty_book=True)
    assert manifest["synthetic_fills_present"] is False
    assert manifest["venues"] == ["KALSHI", "POLYMARKET"]
    assert live_tok_a in manifest["tickers"]
    assert live_tok_b in manifest["tickers"]


def test_b2_polymarket_discovery_falls_back_to_clob_sampling_markets():
    sampling_tok = "98765432109876543210987654321098765432109876543210987654321098765432109876543"

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "gamma-api.polymarket.com" in url:
            return httpx.Response(200, json=[{"active": True, "closed": False, "enableOrderBook": True, "clobTokenIds": '["STALE-404"]'}])
        if "clob.polymarket.com/sampling-markets" in url:
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "active": True,
                            "closed": False,
                            "enable_order_book": True,
                            "accepting_orders": True,
                            "tokens": [{"token_id": sampling_tok, "outcome": "Yes"}],
                        }
                    ]
                },
            )
        if "clob.polymarket.com/book" in url:
            if request.url.params.get("token_id") == sampling_tok:
                return httpx.Response(
                    200,
                    json={"bids": [{"price": "0.51", "size": "120"}], "asks": [{"price": "0.54", "size": "140"}]},
                )
            return httpx.Response(404, request=request)
        return httpx.Response(404, request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        discovered = discover_liquid_polymarket_tokens(http_client=client, limit=1)
    assert discovered == [sampling_tok]

