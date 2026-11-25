"""Milestone PR #85 verification tests: 4-domain Caddy HTTPS reverse proxy,
host-level plane isolation, IFAS static ADR-011 air-gap page, Lightsail Compose
overlay (`docker-compose.domains.yml`), and `plane_routing.py` cutover."""
from __future__ import annotations

import json
import pathlib
import re
import shutil
import subprocess
from typing import Dict

import pytest
import yaml
from fastapi.testclient import TestClient

from app.domain.plane_routing import (
    PROHIBITED_DOMAINS,
    get_plane_config,
    resolve_lineage_house_url,
)
from app.main import app

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
CADDYFILE_PATH = REPO_ROOT / "deploy" / "caddy" / "Caddyfile"
IFAS_INDEX_PATH = REPO_ROOT / "deploy" / "caddy" / "ifas_airgap" / "index.html"
COMPOSE_PAPER_PATH = REPO_ROOT / "deploy" / "docker-compose.paper.yml"
COMPOSE_DOMAINS_PATH = REPO_ROOT / "docker-compose.domains.yml"
RUNBOOK_PATH = REPO_ROOT / "docs" / "DEPLOYMENT_4_DOMAINS_LIGHTSAIL.md"

EXPECTED_PLANE_ENV: Dict[str, str] = {
    "FAMILY_HUB_BASE_URL": "https://narratixai.org",
    "UNIVERSITY_BASE_URL": "https://narratixai.info",
    "PDEUE_VAULT_BASE_URL": "https://vault.narratixai.io",
    "PDEUE_ADMIN_BASE_URL": "https://admin.narratixai.io",
    "IFAS_ACCOUNTING_BASE_URL": "https://narratixai.net",
}


def _extract_caddy_site_block(caddyfile_text: str, host: str) -> str:
    """Extract the top-level brace-balanced site block for a given Caddy hostname."""
    pattern = re.compile(rf"(?m)^{re.escape(host)}\s*\{{")
    match = pattern.search(caddyfile_text)
    assert match is not None, f"Missing top-level Caddy site block for {host}"
    start = match.start()
    depth = 0
    for idx in range(match.end() - 1, len(caddyfile_text)):
        ch = caddyfile_text[idx]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return caddyfile_text[start : idx + 1]
    raise AssertionError(f"Unbalanced braces in Caddyfile site block for {host}")


def test_pr85_caddyfile_exists_defines_all_domains_security_headers_and_zero_prohibited_domains():
    assert CADDYFILE_PATH.is_file(), "deploy/caddy/Caddyfile must exist"
    text = CADDYFILE_PATH.read_text(encoding="utf-8")

    # All required host blocks exist
    for host in (
        "www.narratixai.org",
        "narratixai.org",
        "narratixai.info",
        "vault.narratixai.io",
        "admin.narratixai.io",
        "narratixai.net",
    ):
        block = _extract_caddy_site_block(text, host)
        assert block, f"Empty site block for {host}"

    # Required security headers declared
    for header_token in (
        "Strict-Transport-Security",
        "X-Content-Type-Options",
        "nosniff",
        "Referrer-Policy",
        "strict-origin-when-cross-origin",
        "Permissions-Policy",
    ):
        assert header_token in text, f"Missing security header token {header_token!r} in Caddyfile"

    # ZERO prohibited corporate domains across all PR #85 artifacts
    for artifact in (CADDYFILE_PATH, IFAS_INDEX_PATH, COMPOSE_DOMAINS_PATH, RUNBOOK_PATH):
        assert artifact.is_file(), f"Expected PR #85 artifact missing: {artifact}"
        content_lower = artifact.read_text(encoding="utf-8").lower()
        for forbidden in PROHIBITED_DOMAINS:
            assert forbidden not in content_lower, (
                f"Prohibited corporate domain {forbidden!r} must never appear in {artifact.name}"
            )


def test_pr85_caddyfile_enforces_strict_host_plane_isolation_and_redirects():
    text = CADDYFILE_PATH.read_text(encoding="utf-8")

    # 1. www.narratixai.org -> 301 canonical redirect to https://narratixai.org{uri}
    www_block = _extract_caddy_site_block(text, "www.narratixai.org")
    assert "redir https://narratixai.org{uri} 301" in www_block

    # 2. narratixai.org (Family Social & Heritage Plane)
    org_block = _extract_caddy_site_block(text, "narratixai.org")
    assert "reverse_proxy pdeue-paper-api:8000" in org_block
    assert "import security_headers_social_jitsi" in org_block
    assert "https://meet.jit.si" in text, "Jitsi Meet compatibility must be preserved for /community"
    for allowed in ("/home", "/community", "/community/*", "/static/*", "/api/v1/portal/planes", "/api/v1/portal/community/*", "/health"):
        assert allowed in org_block, f"narratixai.org must allow {allowed}"
    for blocked in ("/member", "/advisor", "/dashboard", "/admin", "/lineage", "/api/v1/ledger", "/api/v1/governance", "/api/v1/operator"):
        assert blocked in org_block, f"narratixai.org must explicitly block {blocked}"
    assert "403" in org_block

    # 3. narratixai.info (PDEUE University Plane)
    info_block = _extract_caddy_site_block(text, "narratixai.info")
    assert "redir /companion 302" in info_block
    assert "reverse_proxy pdeue-paper-api:8000" in info_block
    for allowed in ("/companion", "/static/*", "/api/v1/portal/planes", "/api/v1/portal/companion", "/api/v1/manuals", "/api/v1/lexicon", "/health"):
        assert allowed in info_block, f"narratixai.info must allow {allowed}"
    for blocked in ("/member", "/advisor", "/dashboard", "/admin", "/lineage", "/api/v1/ledger", "/api/v1/governance", "/api/v1/operator"):
        assert blocked in info_block, f"narratixai.info must explicitly block {blocked}"
    assert "403" in info_block

    # 4. vault.narratixai.io (Personal Account & Custodial Vault Plane)
    vault_block = _extract_caddy_site_block(text, "vault.narratixai.io")
    assert "redir /member 302" in vault_block
    assert "reverse_proxy pdeue-paper-api:8000" in vault_block
    for allowed in (
        "/member",
        "/advisor",
        "/lineage/*",
        "/static/*",
        "/api/v1/portal/*",
        "/api/v1/member/*",
        "/api/v1/advisor/*",
        "/api/v1/lineage/*",
        "/api/v1/lexicon",
        "/api/v1/onboarding/*",
        "/health",
    ):
        assert allowed in vault_block, f"vault.narratixai.io must allow {allowed}"
    assert "/dashboard" in vault_block and "/admin" in vault_block
    assert "403" in vault_block

    # 5. admin.narratixai.io (Executive & Technical Operations Plane)
    admin_block = _extract_caddy_site_block(text, "admin.narratixai.io")
    assert "redir /dashboard 302" in admin_block
    assert "reverse_proxy pdeue-paper-api:8000" in admin_block
    for allowed in ("/dashboard", "/admin/*", "/static/*", "/api/v1/*", "/health"):
        assert allowed in admin_block, f"admin.narratixai.io must allow {allowed}"

    # 6. narratixai.net (Standalone IFAS Air-Gap — ZERO PDEUE proxying)
    net_block = _extract_caddy_site_block(text, "narratixai.net")
    assert "reverse_proxy" not in net_block, "narratixai.net MUST NOT reverse_proxy any PDEUE route"
    assert "pdeue-paper-api" not in net_block
    assert "root * /srv/ifas" in net_block
    assert "file_server" in net_block
    assert "403" in net_block


def test_pr85_ifas_static_airgap_page_zero_cdn_and_adr011_notice():
    assert IFAS_INDEX_PATH.is_file(), "deploy/caddy/ifas_airgap/index.html must exist"
    markup = IFAS_INDEX_PATH.read_text(encoding="utf-8")

    # Zero external CDN scripts, stylesheets, or font links
    external_asset_pattern = re.compile(
        r"""<(?:script|link)\b[^>]*(?:src|href)=["']https?://""",
        re.IGNORECASE,
    )
    assert not external_asset_pattern.search(markup), "IFAS static air-gap page must contain ZERO external CDN tags"
    for cdn_token in ("cdn.", "jsdelivr", "unpkg", "cdnjs", "fonts.googleapis", "bootstrapcdn", "tailwind"):
        assert cdn_token not in markup.lower(), f"Forbidden CDN reference {cdn_token!r} found in IFAS page"

    # Institutional branding & ADR-011 air-gap notice
    assert "ADR-011" in markup
    assert "Independent Financial Accounting System" in markup
    assert "IFAS" in markup
    assert "CARMICHAEL" in markup and "McCORMICK" in markup
    assert "#0B132B" in markup and "#1C2541" in markup

    # Clean return links to Family Home Hub and Personal Account Vault
    assert 'href="https://narratixai.org/home"' in markup
    assert 'href="https://vault.narratixai.io/member"' in markup


def test_pr85_compose_domains_overlay_valid_yaml_env_injection_and_gate_g1_preserved():
    assert COMPOSE_PAPER_PATH.is_file(), "deploy/docker-compose.paper.yml must exist"
    assert COMPOSE_DOMAINS_PATH.is_file(), "docker-compose.domains.yml must exist"

    paper_doc = yaml.safe_load(COMPOSE_PAPER_PATH.read_text(encoding="utf-8"))
    overlay_doc = yaml.safe_load(COMPOSE_DOMAINS_PATH.read_text(encoding="utf-8"))

    assert isinstance(overlay_doc, dict) and "services" in overlay_doc
    overlay_services = overlay_doc["services"]

    # Overlay MUST NOT touch pdeue-l2-collector
    assert "pdeue-l2-collector" not in overlay_services, (
        "docker-compose.domains.yml must NOT alter or interrupt pdeue-l2-collector"
    )

    # Overlay targets the existing API service (`pdeue-api`, container_name `pdeue-paper-api`)
    assert paper_doc["services"]["pdeue-api"]["container_name"] == "pdeue-paper-api"
    assert "pdeue-api" in overlay_services
    api_overlay = overlay_services["pdeue-api"]
    api_env = api_overlay.get("environment", {})
    assert isinstance(api_env, dict), "pdeue-api environment overlay must be a mapping"

    for env_key, expected_url in EXPECTED_PLANE_ENV.items():
        assert api_env.get(env_key) == expected_url, f"Expected {env_key}={expected_url}"

    # Overlay MUST NOT weaken Gate G1 fail-closed defaults or data/tape mounts
    for protected_env in (
        "PDEUE_VENUE_MODE",
        "PDEUE_LIVE_TRADING_ENABLED",
        "PDEUE_GATE_G1_STATUS",
        "PDEUE_GOVERNANCE_MODE",
        "DATABASE_URL",
        "PDEUE_TAPE_DIR",
    ):
        assert protected_env not in api_env, f"Overlay must not override protected Gate G1 env {protected_env}"
    assert "volumes" not in api_overlay, "Overlay must not alter /var/lib/pdeue/data or /var/lib/pdeue/tapes mounts"

    # Verify DNS alias ensures `pdeue-paper-api:8000` always resolves on Compose network
    aliases = api_overlay.get("networks", {}).get("default", {}).get("aliases", [])
    assert "pdeue-paper-api" in aliases

    # Verify pdeue-caddy service definition
    assert "pdeue-caddy" in overlay_services
    caddy_svc = overlay_services["pdeue-caddy"]
    assert caddy_svc["image"] == "caddy:2-alpine"
    assert caddy_svc["restart"] == "unless-stopped"
    assert str(caddy_svc["mem_limit"]).lower() == "128m"
    assert "80:80" in caddy_svc["ports"]
    assert "443:443" in caddy_svc["ports"]

    volumes = caddy_svc["volumes"]
    assert any(v.endswith("deploy/caddy/Caddyfile:/etc/caddy/Caddyfile:ro") for v in volumes)
    assert any(v.endswith("deploy/caddy/ifas_airgap:/srv/ifas:ro") for v in volumes)
    assert "/var/lib/pdeue/caddy/data:/data" in volumes
    assert "/var/lib/pdeue/caddy/config:/config" in volumes

    # If Docker Compose CLI is installed, verify full merged config & real host mount paths
    if shutil.which("docker"):
        res = subprocess.run(
            [
                "docker",
                "compose",
                "-f",
                str(COMPOSE_PAPER_PATH),
                "-f",
                str(COMPOSE_DOMAINS_PATH),
                "config",
                "--format",
                "json",
            ],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=15,
        )
        if res.returncode == 0:
            merged = json.loads(res.stdout)
            merged_api = merged["services"]["pdeue-api"]
            merged_env = merged_api["environment"]
            assert merged_env["PDEUE_VENUE_MODE"] == "paper"
            assert merged_env["PDEUE_LIVE_TRADING_ENABLED"] == "false"
            assert merged_env["PDEUE_GATE_G1_STATUS"] == "HOLD_OBSERVATIONS_ONLY"
            assert merged_env["PDEUE_GOVERNANCE_MODE"] == "EXECUTIVE_COMMAND"
            for env_key, expected_url in EXPECTED_PLANE_ENV.items():
                assert merged_env[env_key] == expected_url

            # Resolved Caddy bind mounts must point to actual existing repo files
            merged_caddy_vols = {v["target"]: v["source"] for v in merged["services"]["pdeue-caddy"]["volumes"]}
            assert pathlib.Path(merged_caddy_vols["/etc/caddy/Caddyfile"]).resolve() == CADDYFILE_PATH.resolve()
            assert pathlib.Path(merged_caddy_vols["/srv/ifas"]).resolve() == IFAS_INDEX_PATH.parent.resolve()
            assert merged_caddy_vols["/data"] == "/var/lib/pdeue/caddy/data"
            assert merged_caddy_vols["/config"] == "/var/lib/pdeue/caddy/config"

            # Collector remains intact in observation fail-closed mode
            merged_collector = merged["services"]["pdeue-l2-collector"]
            assert merged_collector["environment"]["PDEUE_VENUE_MODE"] == "observation"
            assert merged_collector["environment"]["PDEUE_LIVE_TRADING_ENABLED"] == "false"


def test_pr85_plane_routing_resolves_all_five_production_urls_from_compose_env(
    monkeypatch: pytest.MonkeyPatch,
):
    overlay_doc = yaml.safe_load(COMPOSE_DOMAINS_PATH.read_text(encoding="utf-8"))
    api_env = overlay_doc["services"]["pdeue-api"]["environment"]

    for key, value in api_env.items():
        monkeypatch.setenv(key, value)

    cfg = get_plane_config()
    assert cfg["routing_mode"] == "multi_domain_air_gapped"
    assert cfg["air_gapped_social_plane"] is True

    doorways = cfg["doorways"]
    assert doorways["home"] == "https://narratixai.org/home"
    assert doorways["community"] == "https://narratixai.org/community"
    assert doorways["heritage"] == "https://narratixai.org/community/heritage"
    assert doorways["companion"] == "https://narratixai.info/companion"
    assert doorways["member"] == "https://vault.narratixai.io/member"
    assert doorways["advisor"] == "https://vault.narratixai.io/advisor"
    assert doorways["lineage_house_template"] == "https://vault.narratixai.io/lineage/house/{house_id}"
    assert doorways["dashboard"] == "https://admin.narratixai.io/dashboard"
    assert doorways["tech"] == "https://admin.narratixai.io/admin/tech"
    assert doorways["ifas"] == "https://narratixai.net"
    assert doorways["ifas_configured"] is True

    assert resolve_lineage_house_url(1) == "https://vault.narratixai.io/lineage/house/1"
    assert resolve_lineage_house_url(12) == "https://vault.narratixai.io/lineage/house/12"

    # Also verify live FastAPI /api/v1/portal/planes endpoint reflects the exact 5 URLs
    client = TestClient(app)
    resp = client.get("/api/v1/portal/planes")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["routing_mode"] == "multi_domain_air_gapped"
    assert payload["doorways"]["home"] == "https://narratixai.org/home"
    assert payload["doorways"]["companion"] == "https://narratixai.info/companion"
    assert payload["doorways"]["member"] == "https://vault.narratixai.io/member"
    assert payload["doorways"]["dashboard"] == "https://admin.narratixai.io/dashboard"
    assert payload["doorways"]["ifas"] == "https://narratixai.net"


def test_pr85_lightsail_deployment_runbook_covers_ports_dns_launch_and_verification():
    assert RUNBOOK_PATH.is_file(), "docs/DEPLOYMENT_4_DOMAINS_LIGHTSAIL.md must exist"
    doc = RUNBOOK_PATH.read_text(encoding="utf-8")

    for required_token in (
        "pdeue-ring1-paper",
        "44.200.6.195",
        "443",
        "80",
        "Route 53",
        "narratixai.org",
        "www.narratixai.org",
        "narratixai.info",
        "vault.narratixai.io",
        "admin.narratixai.io",
        "narratixai.net",
        "docker compose -f deploy/docker-compose.paper.yml -f docker-compose.domains.yml",
        "pdeue-l2-collector",
        "/var/lib/pdeue/tapes",
        "curl -I",
    ):
        assert required_token in doc, f"Runbook missing required deployment detail: {required_token!r}"
