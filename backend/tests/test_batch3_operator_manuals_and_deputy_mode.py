"""Batch 3 verification suite:
- Operator Manuals Alignment (CLASS_F, CLASS_T, CHIEF_ADMIN) + C6/ADR test lock preservation
- CHIEF_ADMIN_DEPUTY Read-Only Shadow Succession Mode (/dashboard, /api/v1/portal/dashboard/state, HTTP 403 locks)
- Operator Portal Consistency (zero stale visible LCCF copy, F2-A vs. F3 separation, /companion Succession Annex)
- 9/9 Portal template byte-for-byte parity between api/v1/ and static/
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.portal_discovery import PORTALS

REPO_ROOT = Path(__file__).resolve().parents[2]
MANUALS_DIR = REPO_ROOT / "docs" / "manuals"
API_V1_DIR = REPO_ROOT / "backend" / "app" / "api" / "v1"
STATIC_DIR = REPO_ROOT / "backend" / "app" / "static"

CLIENT = TestClient(app)


def _strip_html_tags_and_attrs(html: str) -> str:
    """Extract visible text outside script/style tags and HTML attributes."""
    cleaned = re.sub(r"<(script|style)\b[^>]*>[\s\S]*?</\1>", " ", html, flags=re.I)
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    return cleaned


# =============================================================================
# 1. OPERATOR MANUALS ALIGNMENT & PRESERVED LOCKS
# =============================================================================


def test_class_f_manual_aligned_with_four_tier_hierarchy_and_batch2_capabilities():
    text = (MANUALS_DIR / "CLASS_F_FINANCIAL_MANUAL.md").read_text(encoding="utf-8")
    for required in (
        "School of Fiduciary Stewardship",
        "F1",
        "F2-H",
        "F2-A",
        "F3",
        "Peer Guide",
        "Head of Household",
        "Lineage Advisor",
        "Chief Risk Officer",
        "PENDING",
        "ALLOWED",
        "DENIED",
        "RESCINDED",
        "PENDING_F2H_CLEARANCE",
        "PENDING_F3_CLEARANCE",
        "ADR-008",
        "ADR-011",
        "ADR-012",
        "Rule A14",
        "High-Water Mark",
        "Directive R-04",
        "Directive R-12",
        "Directive R-15",
        "Phase I Paper Mode",
        "Phase II",
        "IFAS",
        "FSAP (Phase II)",
        "Dual-Lane AI Tutor",
        "Shadow Paper Hunch Studio",
        "Nov 2026 CFTC",
        "DEATH BETS Act",
        "unilateral_execution = False",
    ):
        assert required in text, f"CLASS_F_FINANCIAL_MANUAL.md missing '{required}'"
    assert re.search(r"\bLCCF\b", text) is None, "Stale visible LCCF reference found in CLASS_F_FINANCIAL_MANUAL.md"


def test_class_t_manual_aligned_with_infrastructure_and_r12_boundaries():
    text = (MANUALS_DIR / "CLASS_T_TECHNICAL_MANUAL.md").read_text(encoding="utf-8")
    for required in (
        "Institute of Systems Engineering",
        "T1",
        "T2",
        "T2-Household",
        "T3",
        "Directive R-12",
        "$****.**",
        "SCMA-MEM-****",
        "SQLite WAL",
        "PRAGMA journal_mode=WAL",
        "N=12",
        "pdeue-l2-collector",
        "OBSERVED_L2",
        "Gate G1",
        "HOLD_OBSERVATIONS_ONLY",
        "synthetic_fills_present: False",
        "pdeue_shadow_hunch.db",
        "BaseLLMClient",
        "MockLLMClient",
        "GeminiLLMClient",
        "OpenAILLMClient",
        "narratixai.org",
        "narratixai.info",
        "vault.narratixai.io",
        "admin.narratixai.io",
        "narratixai.net",
        "Zero-CDN",
        "Play #16B",
        "ADR-008",
        "ADR-011",
        "ADR-012",
        "Rule A14",
        "Directive R-04",
        "FSAP (Phase II)",
    ):
        assert required in text, f"CLASS_T_TECHNICAL_MANUAL.md missing '{required}'"
    assert re.search(r"\bLCCF\b", text) is None, "Stale visible LCCF reference found in CLASS_T_TECHNICAL_MANUAL.md"


def test_chief_admin_runbook_aligned_with_deputy_succession_and_preserves_c6_locks():
    text = (MANUALS_DIR / "CHIEF_ADMIN_RUNBOOK.md").read_text(encoding="utf-8")
    for required in (
        # Preserved C6 governance locks
        "Three-Stage Governance Lifecycle",
        "EXECUTIVE_COMMAND",
        "ADVISORY_PETITION_FILTER",
        "BICAMERAL_VETO_ACTIVE",
        "SHTF",
        "IMMUTABLE_CORE_INVARIANT",
        # 4-tab checklists
        "Tab 1",
        "Tab 2",
        "Tab 3",
        "Tab 4",
        "Admin Parallel Shadow Paper Hunch Studio",
        # Surgical vs Global freeze contrast
        "Surgical Single-SCMA / Single-House Freeze",
        "Global Emergency Kill Switch",
        "Directive R-04",
        # Succession & Deputy Protocol
        "Succession & Deputy Administrator Protocol",
        "CHIEF_ADMIN_DEPUTY",
        "DEPUTY_READ_ONLY_OBSERVER",
        "observation window",
        "Liquidity Shock",
        "Runaway Domestic Node",
        "$25k",
        "Sweep Audit",
        # Core governance & Phase I/II alignment
        "ADR-008",
        "ADR-011",
        "ADR-012",
        "Rule A14",
        "R-12",
        "FSAP (Phase II)",
        "Nov 2026 CFTC",
        "DEATH BETS Act",
        "unilateral_execution = False",
    ):
        assert required in text, f"CHIEF_ADMIN_RUNBOOK.md missing '{required}'"
    assert re.search(r"\bLCCF\b", text) is None, "Stale visible LCCF reference found in CHIEF_ADMIN_RUNBOOK.md"


# =============================================================================
# 2. CHIEF_ADMIN_DEPUTY READ-ONLY SHADOW SUCCESSION MODE
# =============================================================================


def test_dashboard_deputy_query_and_header_render_observer_banner_and_locked_controls():
    # Default CHIEF_ADMIN dashboard remains unlocked and banner stays hidden
    default_resp = CLIENT.get("/dashboard")
    assert default_resp.status_code == 200
    assert 'id="deputyObserverBanner" class="deputy-observer-banner" hidden' in default_resp.text
    assert 'data-deputy-observer="true"' not in default_resp.text
    assert 'id="emergencyKillSwitchBtn" disabled' not in default_resp.text

    # Query param (?role=CHIEF_ADMIN_DEPUTY) renders visible banner & locked buttons
    deputy_resp = CLIENT.get("/dashboard?role=CHIEF_ADMIN_DEPUTY")
    assert deputy_resp.status_code == 200
    html = deputy_resp.text
    assert 'data-deputy-observer="true"' in html
    assert 'id="deputyObserverBanner" class="deputy-observer-banner" role="region"' in html
    assert "DEPUTY OBSERVER MODE (CHIEF_ADMIN_DEPUTY) — READ-ONLY SUCCESSION SHADOW." in html
    assert "Active Hat: CHIEF_ADMIN_DEPUTY (READ-ONLY)" in html
    for locked_id in (
        "emergencyKillSwitchBtn",
        "btn-mode-advisory",
        "btn-shtf-snapback",
        "btn-assign-role",
        "openOnboardModalBtn",
        "adminEvalHunchBtn",
    ):
        assert f'id="{locked_id}" disabled aria-disabled="true" data-deputy-locked="true"' in html

    # Header (X-PDEUE-Role: CHIEF_ADMIN_DEPUTY) also activates Read-Only Shadow Mode
    header_resp = CLIENT.get("/dashboard", headers={"X-PDEUE-Role": "CHIEF_ADMIN_DEPUTY"})
    assert header_resp.status_code == 200
    assert 'data-deputy-observer="true"' in header_resp.text
    assert 'id="deputyObserverBanner" class="deputy-observer-banner" role="region"' in header_resp.text


def test_portal_dashboard_state_and_read_endpoints_expose_deputy_observer_status():
    # Normal Chief Admin state
    ca_state = CLIENT.get("/api/v1/portal/dashboard/state")
    assert ca_state.status_code == 200
    ca_body = ca_state.json()
    assert ca_body["active_role"] == "CHIEF_ADMIN"
    assert ca_body["deputy_observer_mode"] is False
    assert ca_body["read_only"] is False
    assert ca_body["mutations_locked"] is False

    # Deputy via query param
    dep_q = CLIENT.get("/api/v1/portal/dashboard/state?role=CHIEF_ADMIN_DEPUTY")
    assert dep_q.status_code == 200
    body_q = dep_q.json()
    assert body_q["active_role"] == "CHIEF_ADMIN_DEPUTY"
    assert body_q["deputy_observer_mode"] is True
    assert body_q["read_only"] is True
    assert body_q["mutations_locked"] is True
    assert body_q["mutation_error_code"] == "DEPUTY_READ_ONLY_OBSERVER"
    assert "DEPUTY OBSERVER MODE (CHIEF_ADMIN_DEPUTY)" in body_q["observer_banner"]

    # Deputy via X-PDEUE-Role header
    dep_hdr = CLIENT.get("/api/v1/portal/dashboard/state", headers={"X-PDEUE-Role": "CHIEF_ADMIN_DEPUTY"})
    assert dep_hdr.status_code == 200
    assert dep_hdr.json()["deputy_observer_mode"] is True

    # Workspace state + read-only operator endpoints succeed with HTTP 200 for Deputy
    ws = CLIENT.get("/api/v1/operator/workspace-state", headers={"X-PDEUE-Role": "CHIEF_ADMIN_DEPUTY"})
    assert ws.status_code == 200
    assert ws.json()["deputy_observer_mode"] is True
    assert len(ws.json()["houses"]) == 12

    lookup = CLIENT.get(
        "/api/v1/portal/custodial/lookup?q=HOUSE-01",
        headers={"X-PDEUE-Role": "CHIEF_ADMIN_DEPUTY"},
    )
    assert lookup.status_code == 200
    assert lookup.json()["scope"] == "ENCLAVE_WIDE_READ_ONLY"
    assert lookup.json()["read_only"] is True

    hunch_list = CLIENT.get(
        "/api/v1/hunch/dossiers",
        headers={"X-PDEUE-Role": "CHIEF_ADMIN_DEPUTY"},
    )
    assert hunch_list.status_code == 200
    assert hunch_list.json()["viewer_role"] == "CHIEF_ADMIN_DEPUTY"

    gov_state = CLIENT.get(
        "/api/v1/governance/state",
        headers={"X-PDEUE-Role": "CHIEF_ADMIN_DEPUTY"},
    )
    assert gov_state.status_code == 200


@pytest.mark.parametrize(
    "method,path,payload",
    [
        ("POST", "/api/v1/operator/emergency-stop", {"reason": "Deputy should be blocked"}),
        ("POST", "/api/v1/operator/emergency-resume", {"justification": "Deputy should be blocked"}),
        ("POST", "/api/v1/governance/mode", {"governance_mode": "ADVISORY_PETITION_FILTER", "reason": "Blocked"}),
        ("POST", "/api/v1/governance/shtf-snapback", {"reason": "Blocked"}),
        ("POST", "/api/v1/governance/roles/assign", {"member_id": "MEM-TEST-1", "role_token": "F1", "house_id": 1}),
        ("POST", "/api/v1/governance/roles/promote", {"member_id": "MEM-TEST-1", "to_role": "F2-A", "house_id": 1}),
        ("POST", "/api/v1/governance/custody-mode", {"custody_assignment_mode": "CROSS_HOUSE_ANTI_TRIBAL"}),
        (
            "POST",
            "/api/v1/onboarding/provision",
            {
                "full_name": "Deputy Test",
                "lineage_house": "HOUSE-01",
                "role_tier": "MEMBER_USER",
                "seed_cents": 10000,
                "risk_dial_pct": 1.0,
                "is_custodial": False,
                "bank_ref_token": "EXT-REF-PENFED-****1234",
            },
        ),
        ("POST", "/api/v1/onboarding/delegation-config", {"delegated_onboarding_scope": "ENCLAVE_WIDE"}),
        ("POST", "/api/v1/lineage/house/1/freeze", {}),
        ("POST", "/api/v1/operator/stage-order", {"contract_ticker": "KX-MIA-FRZ-32", "target_house_id": 1}),
        ("POST", "/api/v1/hunch/evaluate", {"hypothesis": "NOAA heat wave in Phoenix at 42c", "modeled_prob_cents": 58, "quoted_price_cents": 42, "fee_cents": 2}),
        ("POST", "/api/v1/hunch/HUNCH-TEST-001/review", {"decision": "ALLOWED", "notes": "Blocked"}),
    ],
)
def test_chief_admin_mutations_fail_closed_403_for_deputy_role(method: str, path: str, payload: dict):
    resp = CLIENT.request(
        method,
        path,
        headers={"X-PDEUE-Role": "CHIEF_ADMIN_DEPUTY"},
        json=payload,
    )
    assert resp.status_code == 403, f"Expected 403 on {method} {path}, got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert "DEPUTY_READ_ONLY_OBSERVER" in str(body.get("detail", ""))
    assert body.get("error_code") == "DEPUTY_READ_ONLY_OBSERVER"
    assert body.get("read_only") is True


# =============================================================================
# 3. F2-A VS. F3 SEPARATION, COMPANION SUCCESSION ANNEX & PORTAL CONSISTENCY
# =============================================================================


def test_f2a_vs_f3_separation_remains_unmistakable_and_enforced():
    f2a_html = CLIENT.get("/advisor?role=F2-A").text
    assert "F2-A Lineage Advisor · Multi-Branch Advisory Scope" in f2a_html
    assert "F2-A STAGES PENDING PROPOSALS ONLY · F3 CRO ADJUDICATES" in f2a_html
    assert "Stage Advisory Proposal" in f2a_html

    f3_html = CLIENT.get("/advisor?role=F3").text
    assert "F3 Chief Risk Officer (CRO) · Platform-Wide 12-House Macro-Risk" in f3_html
    assert "12-House Exposure Table" in f3_html
    assert "Fiduciary Supervisory Queue (F3 CRO Adjudication of F2-A Proposals)" in f3_html

    # Backend enforcement: F2-A can stage a proposal, cannot adjudicate or co-sign; F3 can adjudicate, cannot co-sign
    staged = CLIENT.post(
        "/api/v1/portal/advisor/proposals?role=F2-A",
        json={
            "target_scma": "SCMA-JULIAN_-A1F98B21",
            "proposed_dial": 1.15,
            "justification": "Batch 3 F2-A separation verification",
        },
    )
    assert staged.status_code == 201
    prop_id = staged.json()["proposal_id"]
    assert staged.json()["status"] == "PENDING"

    assert (
        CLIENT.post(
            f"/api/v1/portal/advisor/proposals/{prop_id}/adjudicate?role=F2-A",
            json={"decision": "ALLOW"},
        ).status_code
        == 403
    )
    assert (
        CLIENT.post(
            "/api/v1/portal/advisor/co-sign",
            json={"request_id": "DIST-105", "actor_role": "F2-A"},
        ).status_code
        == 403
    )
    assert (
        CLIENT.post(
            "/api/v1/portal/advisor/co-sign",
            json={"request_id": "DIST-105", "actor_role": "F3"},
        ).status_code
        == 403
    )

    f3_adj = CLIENT.post(
        f"/api/v1/portal/advisor/proposals/{prop_id}/adjudicate?role=F3",
        json={"decision": "DENY"},
    )
    assert f3_adj.status_code == 200
    assert f3_adj.json()["status"] == "DENIED"


def test_companion_renders_executive_chancellor_succession_annex_card():
    resp = CLIENT.get("/companion")
    assert resp.status_code == 200
    html = resp.text
    assert 'id="executiveSuccessionAnnexCard"' in html
    assert "Executive Chancellor Succession Annex" in html
    assert "CHIEF_ADMIN_DEPUTY" in html
    assert "Surgical vs. Global Freeze Discipline" in html
    assert "Liquidity Shock" in html
    assert "Runaway Domestic Node" in html
    assert "$25k Sweep Audit" in html
    assert 'id="openSuccessionRunbookBtn"' in html
    assert "loadManualByName('CHIEF_ADMIN_RUNBOOK.md')" in html


def test_all_nine_portals_zero_visible_stale_lccf_and_byte_for_byte_static_parity():
    for route, rel_path in PORTALS.items():
        filename = Path(rel_path).name
        api_file = API_V1_DIR / filename
        static_file = STATIC_DIR / filename
        assert api_file.is_file() and static_file.is_file(), f"Missing portal template pair for {route}"
        api_bytes = api_file.read_bytes()
        static_bytes = static_file.read_bytes()
        assert api_bytes == static_bytes, f"Template parity mismatch between api/v1/{filename} and static/{filename}"

        visible_text = _strip_html_tags_and_attrs(api_bytes.decode("utf-8"))
        assert re.search(r"\bLCCF\b", visible_text) is None, (
            f"Stale visible LCCF copy detected on {route} ({filename}); use FSAP (Phase II)."
        )
