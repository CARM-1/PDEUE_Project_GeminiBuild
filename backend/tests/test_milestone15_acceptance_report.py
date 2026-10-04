"""Milestone 15 dossier and unattended-deployment contract checks."""
from __future__ import annotations

import json
import pathlib
import re

from scripts import paper_soak_runner


ROOT = pathlib.Path(__file__).resolve().parents[2]


def test_acceptance_dossier_cites_and_agrees_with_qualification_evidence():
    report_path = ROOT / "docs/acceptance/MILESTONE_15_ACCEPTANCE_REPORT.md"
    assert report_path.is_file()
    report = report_path.read_text(encoding="utf-8")
    assert "phase5_soak_report.json" in report
    assert "phase5d_testnet_report.json" in report
    assert "ADR-008" in report and "ADR-011" in report
    assert "Canonical Terminology and Replay Lexicon v0.5" in report

    soak = json.loads((report_path.parent / "phase5_soak_report.json").read_text())
    testnet = json.loads((report_path.parent / "phase5d_testnet_report.json").read_text())
    assert soak["qualification_status"] == testnet["qualification_status"] == "PASS"
    assert soak["completed_cycles"] == 250
    assert soak["max_concurrent_orders"] == 12
    assert soak["invariants"]["waterfall_87_10_3"]["residual_cents_routed_to_cfcp"] == 1
    assert testnet["completed_cycles"] == 50
    leases = testnet["dynamic_credential_leases"]
    assert leases["acquired"] == leases["revoked"] and leases["active"] == 0
    assert testnet["rate_limiter"]["ceiling_requests_per_second"] == 10


def test_systemd_unit_has_valid_sections_and_only_supported_runner_options():
    unit = (ROOT / "deploy/systemd/pdeue-paper-soak.service").read_text()
    assert re.search(r"(?m)^\[Unit\].*^\[Service\].*^\[Install\]", unit, re.DOTALL)
    exec_start = re.search(r"(?m)^ExecStart=(.+)$", unit).group(1)
    required = {"--mode", "--venue-mode", "--max-concurrent-orders", "--output"}
    assert required <= set(re.findall(r"--[a-z-]+", exec_start))
    assert "--max-concurrent-orders 12" in exec_start
    assert "--output /var/lib/pdeue-paper-soak/health_summary.json" in exec_start

    source = pathlib.Path(paper_soak_runner.__file__).read_text()
    supported = set(re.findall(r'add_argument\(\s*"(--[a-z-]+)"', source))
    assert set(re.findall(r"--[a-z-]+", exec_start)) <= supported


def test_container_packaging_is_non_root_and_probes_fastapi_health():
    dockerfile = (ROOT / "deploy/docker/Dockerfile").read_text()
    compose = (ROOT / "deploy/docker/docker-compose.yml").read_text()
    assert "FROM python:3.12-slim" in dockerfile
    assert "USER pdeue" in dockerfile
    assert "scripts.paper_soak_runner" in (
        ROOT / "deploy/docker/entrypoint.sh"
    ).read_text()
    assert "http://127.0.0.1:8000/health" in dockerfile
    assert "http://127.0.0.1:8000/health" in compose
    assert "PDEUE_CREDENTIAL_BROKER: ephemeral-memory" in compose
