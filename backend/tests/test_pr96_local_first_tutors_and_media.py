"""PR #96 Verification Suite:
1. Deterministic zero-network startup indexing of all 5 canonical manuals, registry.json, and Lexicon v0.5.
2. Local-first short-circuit across all 6 tutors/copilots (Community, Member, Class F, Class T,
   Chief Admin Chancellor Coach, and Class H / House Genealogist) returning answered_locally=True,
   provider_used="local_knowledge_index", existing local media_refs, playbook_steps, and manual_citations
   with ZERO outbound calls to BaseLLMClient / GeminiLLMClient / OpenAILLMClient even when API keys are set.
3. Strict role isolation: CLASS_M, H1, T1, F1 never receive Chief Admin or Class T3 override playbooks/manuals.
4. POST /api/v1/portal/lineage/tutor for H1, H2, and HOUSE_GENEALOGIST with R-12 masking & X-House-ID enforcement.
5. Backward-compatible LLMResponse / CopilotResponse contracts + Lane 2 preservation for external market research.
6. Zero external CDN tags & byte-for-byte parity across all 9 dual-served HTML templates.
"""
from __future__ import annotations

from pathlib import Path
import re
import sys
from unittest.mock import MagicMock

from fastapi.testclient import TestClient
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.copilot.models import CopilotResponse  # noqa: E402
from app.domain.ai_clients.base import BaseLLMClient, LLMResponse  # noqa: E402
from app.domain.ai_clients.gemini_adapter import GeminiLLMClient  # noqa: E402
from app.domain.ai_clients.openai_adapter import OpenAILLMClient  # noqa: E402
from app.domain.chancellor_coach import ChiefAdminChancellorCoach  # noqa: E402
from app.domain.dual_lane_tutor import DualLaneTutor  # noqa: E402
from app.domain.local_knowledge_index import (  # noqa: E402
    CANONICAL_MANUAL_FILES,
    LocalKnowledgeIndex,
    get_local_knowledge_index,
)
from app.domain.member_tutor import MemberLiteracyTutor  # noqa: E402
from app.domain.role_copilots import ClassFFinancialCopilot, ClassTDevOpsCopilot  # noqa: E402
from app.main import app  # noqa: E402

client = TestClient(app)

NINE_PORTAL_TEMPLATES = (
    "home.html",
    "dashboard.html",
    "member.html",
    "tech.html",
    "advisor.html",
    "lineage_house.html",
    "community.html",
    "heritage.html",
    "companion.html",
)

SEVEN_TUTOR_PORTALS = (
    "member.html",
    "community.html",
    "advisor.html",
    "tech.html",
    "dashboard.html",
    "lineage_house.html",
    "heritage.html",
)


def _assert_media_refs_exist_locally(media_refs: list[dict]) -> None:
    assert isinstance(media_refs, list) and len(media_refs) >= 1, "Expected at least one local media_ref"
    for ref in media_refs:
        path = str(ref.get("path") or "")
        assert path.startswith("/static/media/playbooks/"), f"Non-local media_ref path: {path!r}"
        assert "://" not in path and ".." not in path
        rel = path[len("/static/media/playbooks/"):].lstrip("/")
        disk_file = BACKEND_DIR / "app" / "static" / "media" / "playbooks" / rel
        assert disk_file.is_file() and disk_file.stat().st_size > 0, f"Referenced media file missing: {disk_file}"
        assert ref.get("caption"), "media_ref missing caption"
        assert isinstance(ref.get("callout_legend"), list) and len(ref["callout_legend"]) >= 1
        assert ref.get("media_type") in {"annotated_screenshot", "diagram_svg", "slide_deck", "motion_clip"}


# ---------------------------------------------------------------------------
# 1. Startup Indexing of All 5 Manuals + registry.json + Lexicon v0.5
# ---------------------------------------------------------------------------


def test_local_knowledge_index_loads_all_5_manuals_registry_and_lexicon_offline() -> None:
    idx = LocalKnowledgeIndex()
    stats = idx.stats()
    assert stats["zero_network"] is True
    assert set(stats["indexed_manuals"]) == set(CANONICAL_MANUAL_FILES)
    assert stats["manual_count"] == 5
    assert stats["manual_section_count"] >= 40
    assert stats["playbook_count"] >= 16
    assert stats["lexicon_term_count"] >= 20
    assert stats["media_asset_count"] >= 10

    # Singleton matches fresh index
    singleton = get_local_knowledge_index()
    assert singleton.stats()["manual_count"] == 5
    assert singleton.stats()["playbook_count"] == stats["playbook_count"]


def test_backward_compatible_llm_response_and_copilot_response_contracts() -> None:
    llm_resp = LLMResponse(content="Local answer")
    assert llm_resp.answered_locally is False
    assert llm_resp.media_refs == []
    assert llm_resp.playbook_steps == []
    assert llm_resp.manual_citations == []
    assert llm_resp.unilateral_execution is False

    cop_resp = CopilotResponse(answer_text="Local answer", provider_used="local_knowledge_index")
    assert cop_resp.answered_locally is False
    assert cop_resp.media_refs == []
    assert cop_resp.playbook_steps == []
    assert cop_resp.manual_citations == []
    assert cop_resp.unilateral_execution is False


# ---------------------------------------------------------------------------
# 2. Zero Outbound LLM Calls Across All 6 Tutors Even With API Keys Set
# ---------------------------------------------------------------------------


class _FailIfCalledLLMClient(BaseLLMClient):
    provider_name = "gemini"
    model_name = "gemini-spy-v1"

    def __init__(self) -> None:
        self.call_count = 0

    def generate_response(self, system_prompt, user_query, tools=None, context=None):
        self.call_count += 1
        raise AssertionError(f"External LLM must NOT be called for internal PDEUE query: {user_query!r}")


def test_local_first_short_circuit_zero_external_llm_calls_even_with_api_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Configure both hosted providers & API keys to prove zero outbound network calls happen
    monkeypatch.setenv("AI_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "fake-gemini-key-for-pr96-test")
    monkeypatch.setenv("OPENAI_API_KEY", "fake-openai-key-for-pr96-test")

    gemini_spy = MagicMock(side_effect=AssertionError("GeminiLLMClient.generate_response MUST NOT be called"))
    openai_spy = MagicMock(side_effect=AssertionError("OpenAILLMClient.generate_response MUST NOT be called"))
    monkeypatch.setattr(GeminiLLMClient, "generate_response", gemini_spy)
    monkeypatch.setattr(OpenAILLMClient, "generate_response", openai_spy)

    # 1. Community DualLaneTutor (routine + outlier)
    comm_resp = client.post(
        "/api/v1/portal/community/academy/ask-tutor",
        json={"member_id": "MEM-PR96", "query": "How do I use the Downward-Only Risk Dial and 40% dry-powder floor?"},
    )
    assert comm_resp.status_code == 200
    comm = comm_resp.json()
    assert comm["answered_locally"] is True
    assert comm["provider_used"] == "local_knowledge_index"
    assert comm["unilateral_execution"] is False
    _assert_media_refs_exist_locally(comm["media_refs"])
    assert len(comm["playbook_steps"]) >= 2
    assert len(comm["manual_citations"]) >= 1

    # 2. Member Desktop Tutor (/member/tutor and /member/ai-tutor) — outlier incident query
    for ep in ("/api/v1/portal/member/tutor", "/api/v1/portal/member/ai-tutor"):
        m_resp = client.post(
            ep,
            json={
                "question": "What should I do if I see a Directive R-04 Halt banner or Red-Tier withdrawal lock?",
                "scma_id": "SCMA-ELEANOR_-B2B31C9E",
            },
        )
        assert m_resp.status_code == 200
        mdata = m_resp.json()
        assert mdata["answered_locally"] is True
        assert mdata["provider_used"] == "local_knowledge_index"
        assert mdata["unilateral_execution"] is False
        _assert_media_refs_exist_locally(mdata["media_refs"])
        assert len(mdata["playbook_steps"]) >= 2
        assert len(mdata["manual_citations"]) >= 1

    # 3. Class F Financial Copilot (F3 CRO outlier incident)
    f_resp = client.post(
        "/api/v1/portal/advisor/copilot",
        json={
            "query": "How do I engage Directive R-04 Halt and Dual-Signature Override?",
            "role": "F3",
            "household_id": "HOUSEHOLD-ALPHA",
        },
    )
    assert f_resp.status_code == 200
    fdata = f_resp.json()
    assert fdata["answered_locally"] is True
    assert fdata["provider_used"] == "local_knowledge_index"
    assert fdata["unilateral_execution"] is False
    _assert_media_refs_exist_locally(fdata["media_refs"])
    assert len(fdata["playbook_steps"]) >= 2
    assert any(c["manual_file"] == "CLASS_F_FINANCIAL_MANUAL.md" for c in fdata["manual_citations"])

    # 4. Class T DevOps Copilot (T3 outlier incident)
    t_resp = client.post(
        "/api/v1/portal/tech/copilot",
        json={
            "query": "How do I request an Audited CA R-12 Override and settlement recovery?",
            "tier": "T3",
            "household_id": "HOUSEHOLD-ALPHA",
        },
    )
    assert t_resp.status_code == 200
    tdata = t_resp.json()
    assert tdata["answered_locally"] is True
    assert tdata["provider_used"] == "local_knowledge_index"
    assert tdata["r12_masked"] is True
    assert tdata["unilateral_execution"] is False
    _assert_media_refs_exist_locally(tdata["media_refs"])
    assert len(tdata["playbook_steps"]) >= 2
    assert any(c["manual_file"] == "CLASS_T_TECHNICAL_MANUAL.md" for c in tdata["manual_citations"])

    # 5. Chief Admin Chancellor Coach (/api/v1/copilot/query & /api/v1/operator/chancellor/query)
    c1 = client.post(
        "/api/v1/copilot/query",
        json={
            "prompt": "How do I execute Global R-04 Kill Switch and 1-Click SHTF Snap-Back?",
            "user_id": "chief-admin-pr96",
            "role": "OPERATOR",
            "context_filters": {},
        },
    )
    assert c1.status_code == 200
    c1_data = c1.json()
    assert c1_data["answered_locally"] is True
    assert c1_data["provider_used"] == "local_knowledge_index"
    assert c1_data["unilateral_execution"] is False
    assert c1_data["policy_decision_matrix"] is not None
    _assert_media_refs_exist_locally(c1_data["media_refs"])
    assert len(c1_data["playbook_steps"]) >= 2
    assert any(c["manual_file"] == "CHIEF_ADMIN_RUNBOOK.md" for c in c1_data["manual_citations"])

    c2 = client.post(
        "/api/v1/operator/chancellor/query",
        json={
            "prompt": "How do I use Tab 3 Velocity Radar and Admin Parallel Shadow Paper Hunch Studio?",
            "user_id": "chief-admin-pr96",
        },
    )
    assert c2.status_code == 200
    c2_data = c2.json()
    assert c2_data["answered_locally"] is True
    assert c2_data["provider_used"] == "local_knowledge_index"
    _assert_media_refs_exist_locally(c2_data["media_refs"])
    assert len(c2_data["playbook_steps"]) >= 2

    # 6. Class H / Genealogist Lineage Tutor
    h_resp = client.post(
        "/api/v1/portal/lineage/tutor",
        headers={"X-House-ID": "1", "X-Actor-Role": "H2"},
        json={"query": "How do I freeze a subordinate dial in an emergency?", "role": "H2", "house_id": 1},
    )
    assert h_resp.status_code == 200
    hdata = h_resp.json()
    assert hdata["answered_locally"] is True
    assert hdata["provider_used"] == "local_knowledge_index"
    _assert_media_refs_exist_locally(hdata["media_refs"])
    assert len(hdata["playbook_steps"]) >= 2
    assert any(c["manual_file"] == "CLASS_H_LINEAGE_AND_HERITAGE_MANUAL.md" for c in hdata["manual_citations"])

    # Prove ZERO outbound calls to Gemini or OpenAI across ALL 6 tutors!
    assert gemini_spy.call_count == 0
    assert openai_spy.call_count == 0


def test_direct_spy_base_llm_client_zero_calls_across_all_5_tutor_classes() -> None:
    spy = _FailIfCalledLLMClient()

    d_out = DualLaneTutor(llm_client=spy).answer_academy_query(
        query="How do I run a Shadow Paper Hunch 3-Point Validation?",
        member_id="MEM-SPY",
    )
    assert d_out["answered_locally"] is True
    assert d_out["provider_used"] == "local_knowledge_index"

    m_out = MemberLiteracyTutor(llm_client=spy).answer_member_query(
        "How do I adjust my Downward-Only Risk Dial?",
        member_state={"scma_id": "SCMA-SPY-01", "name": "Spy Member", "cash_cents": 100_000},
    )
    assert m_out["answered_locally"] is True
    assert m_out["provider_used"] == "local_knowledge_index"

    from app.api.v1 import portal_router

    f_out = ClassFFinancialCopilot(llm_client=spy).answer_advisor_query(
        "How do I review Shadow Hunch clearance and F2-H proposals?",
        role="F2-H",
        household_id="HOUSEHOLD-ALPHA",
        lineage_data=portal_router.LINEAGE_DATA,
        distribution_state={},
        advisory_proposals={},
        macro_house_exposures=[],
        directive_r04_snapshot={"status": "NORMAL"},
        dual_sig_overrides=[],
    )
    assert f_out["answered_locally"] is True
    assert f_out["provider_used"] == "local_knowledge_index"

    t_out = ClassTDevOpsCopilot(llm_client=spy).answer_tech_query(
        "How does Directive R-12 masking protect technical telemetry?",
        tier="T1",
        household_id="HOUSEHOLD-ALPHA",
        cycle_count=10,
        settled_count=3,
        ws_latency_ms={"Kalshi": 11, "Polymarket": 17},
        token_buckets={"Kalshi": {"available": 9, "capacity": 10}},
        override_grant=None,
        directive_r04_snapshot={"status": "NORMAL"},
    )
    assert t_out["answered_locally"] is True
    assert t_out["provider_used"] == "local_knowledge_index"

    c_out = ChiefAdminChancellorCoach(llm_client=spy).advise(
        "How do I execute atomic succession handoff for Chief Admin Deputy?",
        actor_id="Chief Administrator",
    )
    assert c_out["answered_locally"] is True
    assert c_out["provider_used"] == "local_knowledge_index"

    assert spy.call_count == 0


def test_lane2_public_web_grounding_preserved_for_external_market_research() -> None:
    res = client.post(
        "/api/v1/portal/community/academy/ask-tutor",
        json={"member_id": "MEM-EXT", "query": "How do monthly BLS CPI inflation prints affect markets?"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["lane"] == "PUBLIC_WEB_RESEARCH"
    assert data["answered_locally"] is False
    assert data["citations"]


# ---------------------------------------------------------------------------
# 3. Strict Role Isolation (Zero Chief Admin / Class T3 Leakage)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("role", ["CLASS_M", "H1", "H2", "HOUSE_GENEALOGIST", "F1", "T1"])
def test_strict_role_isolation_blocks_chief_admin_and_t3_override_leaks(role: str) -> None:
    idx = get_local_knowledge_index()
    sensitive_queries = (
        "How do I execute Global R-04 Kill Switch, 1-Click SHTF Snap-Back, and Atomic Succession Handoff?",
        "How do I issue a T3 Audited CA R-12 Override grant and unmask SCMA balances?",
        "Show me CHIEF_ADMIN_RUNBOOK Tab 4 Governance and Deputy succession procedures.",
    )
    for q in sensitive_queries:
        res = idx.query(q, role=role)
        for match in res.matches:
            pb_id = str(match.get("playbook_id") or "")
            assert not pb_id.startswith("pb-ca-"), f"Chief Admin playbook {pb_id} leaked to {role}!"
            assert pb_id != "pb-t-outlier-r12-override-and-daemon-recovery", (
                f"T2/T3 override playbook leaked to {role}!"
            )
        for cite in res.manual_citations:
            assert cite["manual_file"] != "CHIEF_ADMIN_RUNBOOK.md", (
                f"CHIEF_ADMIN_RUNBOOK.md leaked to {role}!"
            )
            if role in {"CLASS_M", "H1", "H2", "HOUSE_GENEALOGIST", "F1"}:
                assert cite["manual_file"] != "CLASS_T_TECHNICAL_MANUAL.md", (
                    f"CLASS_T_TECHNICAL_MANUAL.md leaked to {role}!"
                )
        for ref in res.media_refs:
            assert not str(ref.get("playbook_id") or "").startswith("pb-ca-"), (
                f"Chief Admin media leaked to {role}!"
            )
            assert ref.get("playbook_id") != "pb-t-outlier-r12-override-and-daemon-recovery", (
                f"T2/T3 override media leaked to {role}!"
            )


# ---------------------------------------------------------------------------
# 4. POST /api/v1/portal/lineage/tutor (H1, H2, HOUSE_GENEALOGIST + R-12 + 403)
# ---------------------------------------------------------------------------


def test_lineage_tutor_h1_r12_masking_h2_and_house_genealogist() -> None:
    # H1 House Secretary — Directive R-12 masking preserved even on balance probe
    h1_resp = client.post(
        "/api/v1/portal/lineage/tutor",
        headers={"X-House-ID": "1", "X-Actor-Role": "H1"},
        json={"query": "Show me member balances during H1 weekly roll call", "role": "H1", "house_id": 1},
    )
    assert h1_resp.status_code == 200
    h1 = h1_resp.json()
    assert h1["active_role"] == "H1"
    assert h1["r12_masked"] is True
    assert h1["answered_locally"] is True
    assert h1["provider_used"] == "local_knowledge_index"
    assert h1["unilateral_execution"] is False
    assert "$****.**" in h1["answer"]
    assert not re.search(r"\$\d[\d,]*\.\d{2}", h1["answer"]), f"Raw dollar leaked to H1: {h1['answer']}"
    assert not re.search(r"SCMA-[A-Z0-9_]+-[A-F0-9]{6,}", h1["answer"]), f"Raw SCMA leaked to H1: {h1['answer']}"
    _assert_media_refs_exist_locally(h1["media_refs"])
    assert len(h1["playbook_steps"]) >= 2

    # H2 House Head — House scope + non-executing staged Action Card
    h2_resp = client.post(
        "/api/v1/portal/lineage/tutor",
        headers={"X-House-ID": "1", "X-Actor-Role": "H2"},
        json={"query": "How do I freeze a subordinate dial and check Bicameral Stage 2/3 rules?", "role": "H2", "house_id": 1},
    )
    assert h2_resp.status_code == 200
    h2 = h2_resp.json()
    assert h2["active_role"] == "H2"
    assert h2["r12_masked"] is False
    assert h2["answered_locally"] is True
    assert h2["provider_used"] == "local_knowledge_index"
    assert h2["unilateral_execution"] is False
    _assert_media_refs_exist_locally(h2["media_refs"])
    assert len(h2["playbook_steps"]) >= 2
    for card in h2["action_cards"]:
        assert card["unilateral_execution"] is False
        assert card["executed"] is False

    # HOUSE_GENEALOGIST — Hall of Arms zero-financial scope
    gen_resp = client.post(
        "/api/v1/portal/lineage/tutor",
        headers={"X-Actor-Role": "HOUSE_GENEALOGIST"},
        json={"query": "How do I curate House chronicles and Scottish Bordure Differencing?", "role": "HOUSE_GENEALOGIST", "house_id": 1},
    )
    assert gen_resp.status_code == 200
    gen = gen_resp.json()
    assert gen["active_role"] == "HOUSE_GENEALOGIST"
    assert gen["r12_masked"] is True
    assert gen["answered_locally"] is True
    assert gen["provider_used"] == "local_knowledge_index"
    assert gen["unilateral_execution"] is False
    _assert_media_refs_exist_locally(gen["media_refs"])
    assert any(ref["path"].endswith("heritage_hall_of_arms.png") for ref in gen["media_refs"])

    # Cross-House X-House-ID boundary enforced (HTTP 403)
    cross_house = client.post(
        "/api/v1/portal/lineage/tutor",
        headers={"X-House-ID": "1", "X-Actor-Role": "H2"},
        json={"query": "Explain House 2 roll call", "role": "H2", "house_id": 2},
    )
    assert cross_house.status_code == 403

    # Class T technical roles blocked from Class H tutor (HTTP 403)
    class_t_blocked = client.post(
        "/api/v1/portal/lineage/tutor",
        headers={"X-Actor-Role": "T3"},
        json={"query": "Explain House governance", "role": "T3", "house_id": 1},
    )
    assert class_t_blocked.status_code == 403


# ---------------------------------------------------------------------------
# 5. Zero-CDN, Shared Visual Assets & Byte-for-Byte Parity Across All 9 Portals
# ---------------------------------------------------------------------------


def test_zero_cdn_shared_visual_assets_and_9_template_byte_parity() -> None:
    css_file = BACKEND_DIR / "app" / "static" / "css" / "tutor_media_cards.css"
    js_file = BACKEND_DIR / "app" / "static" / "js" / "tutor_media_cards.js"
    assert css_file.is_file() and css_file.stat().st_size > 1_000
    assert js_file.is_file() and js_file.stat().st_size > 1_000
    assert "http://" not in css_file.read_text(encoding="utf-8")
    assert "https://" not in css_file.read_text(encoding="utf-8")
    assert "http://" not in js_file.read_text(encoding="utf-8")
    assert "https://" not in js_file.read_text(encoding="utf-8")

    external_tag_re = re.compile(r"<(?:script|link)\b[^>]+(?:src|href)\s*=\s*['\"]https?://", re.IGNORECASE)
    for filename in NINE_PORTAL_TEMPLATES:
        api_path = BACKEND_DIR / "app" / "api" / "v1" / filename
        static_path = BACKEND_DIR / "app" / "static" / filename
        assert api_path.is_file() and static_path.is_file()
        api_bytes = api_path.read_bytes()
        static_bytes = static_path.read_bytes()
        assert api_bytes == static_bytes, f"Byte-for-byte parity drift in {filename}"
        html_text = api_bytes.decode("utf-8")
        assert external_tag_re.search(html_text) is None, f"External CDN tag in {filename}"
        if filename in SEVEN_TUTOR_PORTALS:
            assert "/static/css/tutor_media_cards.css" in html_text, f"Missing tutor_media_cards.css in {filename}"
            if filename in {"advisor.html", "tech.html"}:
                assert "<script src=" not in html_text.lower(), f"WP4 inline lock violated in {filename}"
                assert "window.PDEUEVisualTutor" in html_text, f"Missing inline PDEUEVisualTutor in {filename}"
            else:
                assert "/static/js/tutor_media_cards.js" in html_text, f"Missing tutor_media_cards.js in {filename}"
