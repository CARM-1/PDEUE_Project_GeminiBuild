"""Milestones E3-E5 Backend Contract Tests:
- E3: Exact-cent Concentric Asset Ring telemetry & responsive viewport markup
- E4: Canonical Lexicon v0.5 glossary endpoint (GET /api/v1/portal/glossary) & pure-CSS tooltips across all 5 portals
- E5: Standardized fail-closed ReadModelEnvelope[T] transitions (OK, QUALIFICATION_PENDING, TRADING_HALTED, DEGRADED_RETRYING)
- Synchronization & Hygiene: api/v1/*.html == static/*.html, zero external CDNs, zero native alert()/confirm()
"""
from __future__ import annotations

from pathlib import Path
import re

from fastapi.testclient import TestClient
from pydantic import ValidationError
import pytest

from app.domain.authority_tiers import get_directive_r04_controller
from app.domain.lexicon_v05 import LEXICON_VERSION, REQUIRED_CANONICAL_TERM_IDS
from app.main import app
from app.schemas.read_model import ReadModelEnvelope, ReadModelStatus, build_read_model_envelope


REPO_ROOT = Path(__file__).resolve().parents[2]
API_V1_DIR = REPO_ROOT / "backend" / "app" / "api" / "v1"
STATIC_DIR = REPO_ROOT / "backend" / "app" / "static"

SYNCED_HTML_FILES = (
    "dashboard.html",
    "member.html",
    "advisor.html",
    "tech.html",
    "lineage_house.html",
    "community.html",
)


@pytest.fixture(autouse=True)
def _reset_r04_and_breaker():
    from app.api.v1 import workspace_router
    from app.db.models import Base
    from app.db.session import engine as default_engine
    from app.domain.member_onboarding import get_onboarding_service

    Base.metadata.create_all(bind=default_engine)
    onboarding_svc = get_onboarding_service()
    if getattr(onboarding_svc, "_engine", None) is not None:
        Base.metadata.create_all(bind=onboarding_svc._engine)

    controller = get_directive_r04_controller()
    controller.reset_normal()
    workspace_router._service.circuit_breaker.is_tripped = False
    workspace_router._service.circuit_breaker.trip_reason = None
    yield
    controller.reset_normal()
    workspace_router._service.circuit_breaker.is_tripped = False
    workspace_router._service.circuit_breaker.trip_reason = None


def test_glossary_endpoint_returns_complete_lexicon_v05_payload():
    with TestClient(app) as client:
        resp = client.get("/api/v1/portal/glossary")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["lexicon_version"] == LEXICON_VERSION == "v0.5"
    assert payload["ratified"] is True
    assert payload["count"] == payload["total_count"] >= len(REQUIRED_CANONICAL_TERM_IDS)

    terms_by_id = payload["terms_by_id"]
    for term_id in REQUIRED_CANONICAL_TERM_IDS:
        assert term_id in terms_by_id, f"Missing canonical Lexicon v0.5 term: {term_id}"
        entry = terms_by_id[term_id]
        assert entry["term"]
        assert entry["tooltip"]
        assert entry["definition"]
        assert entry["category"]
        assert entry["authority_ref"]
        assert isinstance(entry["aliases"], list) and len(entry["aliases"]) >= 1


def test_glossary_endpoint_supports_search_and_category_filtering():
    with TestClient(app) as client:
        hwm_resp = client.get("/api/v1/portal/glossary", params={"q": "hwm"})
        assert hwm_resp.status_code == 200
        hwm_ids = {t["id"] for t in hwm_resp.json()["terms"]}
        assert "high-water-mark-adr-012" in hwm_ids

        r12_resp = client.get("/api/v1/portal/glossary", params={"q": "$****.**"})
        assert r12_resp.status_code == 200
        r12_ids = {t["id"] for t in r12_resp.json()["terms"]}
        assert "directive-r12-masking" in r12_ids

        cat_resp = client.get("/api/v1/portal/glossary", params={"category": "Capital & Pools"})
        assert cat_resp.status_code == 200
        assert cat_resp.json()["count"] >= 3
        assert all(t["category"] == "Capital & Pools" for t in cat_resp.json()["terms"])


def test_read_model_envelope_schema_enforces_fail_closed_invariants():
    with pytest.raises(ValidationError):
        ReadModelEnvelope[dict](
            status=ReadModelStatus.TRADING_HALTED,
            data={"balance_cents": 100},
            reason="Halted",
            updated_at_utc="2026-11-23T00:00:00+00:00",
            banner_headline="TRADING HALTED — EXECUTIVE OVERRIDE",
            banner_detail="Halted",
        )

    with pytest.raises(ValidationError):
        ReadModelEnvelope[dict](
            status=ReadModelStatus.DEGRADED_RETRYING,
            data={"balance_cents": 100},
            reason="Offline",
            updated_at_utc="2026-11-23T00:00:00+00:00",
            banner_headline="UNAVAILABLE — ENGINE UNREACHABLE",
            banner_detail="Offline",
        )

    env_ok = build_read_model_envelope(
        {"equity_cents": 100_000},
        surface="member",
        gate_g1_status="QUALIFIED",
    )
    assert env_ok.status == ReadModelStatus.OK
    assert env_ok.data == {"equity_cents": 100_000}
    assert env_ok.synthetic_fills_present is False


def test_read_model_envelope_state_transitions_across_portal_endpoints(monkeypatch: pytest.MonkeyPatch):
    with TestClient(app) as client:
        # 1. Default Gate G1 HOLD_OBSERVATIONS_ONLY -> QUALIFICATION_PENDING
        monkeypatch.setenv("PDEUE_GATE_G1_STATUS", "HOLD_OBSERVATIONS_ONLY")
        for surface in ("dashboard", "member", "advisor", "tech", "lineage"):
            r = client.get(f"/api/v1/portal/read-model/{surface}")
            assert r.status_code == 200
            env = r.json()
            assert env["status"] == "QUALIFICATION_PENDING"
            assert env["data"] is None
            assert env["banner_headline"] == "NOT AVAILABLE — QUALIFICATION PENDING"
            assert env["updated_at_utc"]
            assert env["synthetic_fills_present"] is False

        # Verify portal state endpoints embed read_model_envelope + exact-cent asset_rings
        ws = client.get("/api/v1/operator/workspace-state")
        assert ws.status_code == 200
        ws_json = ws.json()
        assert ws_json["read_model_envelope"]["status"] == "QUALIFICATION_PENDING"
        rings = ws_json["asset_rings"]
        assert isinstance(rings["total_equity_cents"], int)
        assert isinstance(rings["active_working_margin_cents"], int)
        assert isinstance(rings["dry_powder_floor_cents"], int)
        assert rings["dry_powder_floor_bps"] == 4000
        assert rings["waterfall_split_bps"] == {"scma": 8700, "cfcp": 1000, "faep": 300}

        mem = client.get("/api/v1/portal/member/state")
        assert mem.status_code == 200
        mem_json = mem.json()
        assert mem_json["read_model_envelope"]["status"] == "QUALIFICATION_PENDING"
        assert isinstance(mem_json["allocation"]["working_margin_cents"], int)
        assert mem_json["allocation"]["waterfall_split_bps"] == {"scma": 8700, "cfcp": 1000, "faep": 300}

        # 2. Degraded fault-injection -> DEGRADED_RETRYING (data=None)
        deg = client.get("/api/v1/portal/read-model/dashboard", params={"degraded": "true"})
        assert deg.status_code == 200
        deg_json = deg.json()
        assert deg_json["status"] == "DEGRADED_RETRYING"
        assert deg_json["data"] is None
        assert deg_json["banner_headline"] == "UNAVAILABLE — ENGINE UNREACHABLE"

        # 3. Engage Directive R-04 Emergency Halt -> TRADING_HALTED across all surfaces
        halt_resp = client.post(
            "/api/v1/operator/emergency-stop",
            headers={"X-Actor-Role": "CHIEF_ADMINISTRATOR"},
        )
        assert halt_resp.status_code == 200
        for endpoint in (
            "/api/v1/portal/read-model/dashboard",
            "/api/v1/portal/read-model/member",
            "/api/v1/portal/read-model/advisor",
            "/api/v1/portal/read-model/tech",
            "/api/v1/portal/read-model/lineage",
        ):
            hr = client.get(endpoint)
            assert hr.status_code == 200
            h_env = hr.json()
            assert h_env["status"] == "TRADING_HALTED"
            assert h_env["data"] is None
            assert h_env["banner_headline"] == "TRADING HALTED — EXECUTIVE OVERRIDE"
            assert "DIRECTIVE R-04" in h_env["reason"]

        assert client.get("/api/v1/operator/workspace-state").json()["read_model_envelope"]["status"] == "TRADING_HALTED"
        assert client.get("/api/v1/portal/member/state").json()["read_model_envelope"]["status"] == "TRADING_HALTED"
        assert client.get("/api/v1/portal/tech/telemetry?tier=T3").json()["read_model_envelope"]["status"] == "TRADING_HALTED"
        assert client.get("/api/v1/portal/advisor/household-tree?role=F2-H").json()["read_model_envelope"]["status"] == "TRADING_HALTED"
        assert client.get("/api/v1/portal/lineage/house/1/state?role=H2").json()["read_model_envelope"]["status"] == "TRADING_HALTED"

        # 4. Chief Admin Resume + QUALIFIED Gate G1 -> OK with populated data
        resume_resp = client.post(
            "/api/v1/operator/emergency-resume",
            headers={"X-Actor-Role": "CHIEF_ADMINISTRATOR"},
            json={"justification": "Unit test verification resume"},
        )
        assert resume_resp.status_code == 200
        monkeypatch.setenv("PDEUE_GATE_G1_STATUS", "QUALIFIED")
        ok_resp = client.get("/api/v1/portal/read-model/dashboard")
        assert ok_resp.status_code == 200
        ok_json = ok_resp.json()
        assert ok_json["status"] == "OK"
        assert ok_json["data"] is not None


def test_html_templates_are_synced_zero_cdn_zero_native_dialogs_and_have_lexicon_tooltips():
    cdn_re = re.compile(r"""<(?:script|link)[^>]+(?:src|href)=["']https?://""", re.IGNORECASE)
    dialog_re = re.compile(r"""\b(?:alert|confirm|prompt)\s*\(""")

    for filename in SYNCED_HTML_FILES:
        api_path = API_V1_DIR / filename
        static_path = STATIC_DIR / filename
        assert api_path.exists(), f"Missing {api_path}"
        assert static_path.exists(), f"Missing {static_path}"
        api_text = api_path.read_text(encoding="utf-8")
        static_text = static_path.read_text(encoding="utf-8")
        assert api_text == static_text, f"Template out of sync between {api_path} and {static_path}"
        assert not cdn_re.search(api_text), f"External CDN reference found in {filename}"
        assert not dialog_re.search(api_text), f"Native alert()/confirm()/prompt() found in {filename}"

    with TestClient(app) as client:
        for route in ("/dashboard", "/member", "/advisor", "/admin/tech", "/lineage/house/1", "/lineage/house/1?role=H1"):
            resp = client.get(route)
            assert resp.status_code == 200, f"{route} returned {resp.status_code}"
            body = resp.text
            assert 'class="pdeue-term"' in body, f"Missing Lexicon v0.5 <abbr class='pdeue-term'> on {route}"
            assert "data-tooltip=" in body, f"Missing data-tooltip on {route}"
            assert "ⓘ" in body, f"Missing ⓘ indicator on {route}"
            assert 'id="readModelStatusBanner"' in body, f"Missing ReadModelEnvelope banner on {route}"

        for drawer_route in ("/dashboard", "/member"):
            html = client.get(drawer_route).text
            assert 'id="openGlossaryBtn"' in html
            assert 'id="glossaryDrawer"' in html
            assert 'id="glossarySearchInput"' in html
            assert 'name="viewport"' in html
