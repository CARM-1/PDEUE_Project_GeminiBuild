"""Batch 2B Verification Suite: Modular LLM Adapter, Dual-Lane AI Tutor & Shadow Paper Hunch Studio.

Verifies:
1. Modular LLM Adapter (`backend/app/domain/llm_client.py`): default MockLLMClient
   in CI, Gemini Google Search grounding + token cap + fail-closed fallback,
   OpenAI adapter + token cap + fail-closed fallback.
2. Dual-Lane AI Tutor (`backend/app/domain/dual_lane_tutor.py`, `social_plane_router.py`,
   `member_tutor.py`):
   - Lane 1 Local PDEUE Canon (all 13 core family concepts, LEXICON_BY_ID grounded,
     concrete dollar examples, PDEUE University chapter pointers).
   - Lane 2 Grounded Public Market Research (CPI, Treasuries, EIA, NOAA, binary math,
     structured citations, mandatory disclaimer badge).
   - Balance & transaction request refusal (`unilateral_execution = False`).
   - Nov 2026 CFTC / DEATH BETS Act fail-closed regulatory content filter.
3. Permanent Shadow Paper Hunch Research Studio (`backend/app/domain/shadow_hunch_service.py`,
   `backend/app/api/v1/hunch_router.py`):
   - Isolated SQLite table `shadow_hunch_dossiers`.
   - Regulatory Scope Gate blocking sports/casino/war/terrorism/death (HTTP 400).
   - Three-Point Validation rejecting negative/zero edge (`REJECTED_NO_EDGE`) and
     approving positive edge (`VALIDATED_SHADOW_READY`) in exact integer cents (ADR-008).
   - Shadow Paper bids for Members & Admins with ZERO mutation to real SCMA balances
     or IFAS accounting outbox.
   - Higher-Authority Clearance Queue: uncertified member blocked (HTTP 403);
     certified member (`STEWARDSHIP_L1_CERTIFIED`) progressing through
     `PENDING_F2H_CLEARANCE` -> `PENDING_F3_CLEARANCE` -> `ALLOWED` / `DENIED` / `RESCINDED`.
4. Embedded UI panels, plain-English "What This Means" teaching boxes, zero CDN tags,
   and byte-for-byte parity across `api/v1/*.html` and `static/*.html`.
"""
from __future__ import annotations

import io
import json
from pathlib import Path
import re
import sqlite3
import urllib.error
import urllib.request

from fastapi.testclient import TestClient
import pytest

from app.api.v1 import hunch_router
from app.domain.lexicon_v05 import LEXICON_BY_ID
from app.domain.llm_client import (
    BaseLLMClient,
    GeminiLLMClient,
    MockLLMClient,
    OpenAILLMClient,
    get_llm_client,
)
from app.domain.shadow_hunch_service import ShadowHunchService
from app.main import app

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
client = TestClient(app)


@pytest.fixture
def isolated_hunch_service(tmp_path, monkeypatch):
    """Provide a fresh isolated SQLite `shadow_hunch_dossiers` DB per test."""
    db_file = tmp_path / "test_shadow_hunch.db"
    svc = ShadowHunchService(db_path=db_file, llm_client=MockLLMClient())
    monkeypatch.setattr(hunch_router, "get_shadow_hunch_service", lambda: svc)
    return svc, db_file


# ---------------------------------------------------------------------------
# PART 1: Modular LLM Client Adapter
# ---------------------------------------------------------------------------


def test_part1_llm_client_defaults_to_mock_and_fails_closed_without_keys(monkeypatch):
    monkeypatch.delenv("AI_PROVIDER", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    default_client = get_llm_client()
    assert isinstance(default_client, BaseLLMClient)
    assert isinstance(default_client, MockLLMClient)

    monkeypatch.setenv("AI_PROVIDER", "gemini")
    assert isinstance(get_llm_client(), MockLLMClient)

    monkeypatch.setenv("AI_PROVIDER", "openai")
    assert isinstance(get_llm_client(), MockLLMClient)


def test_part1_gemini_google_search_grounding_token_cap_and_error_fallback(monkeypatch):
    captured: dict = {}

    class _FakeHttpResp:
        def __init__(self, payload: dict):
            self._buf = io.BytesIO(json.dumps(payload).encode("utf-8"))

        def read(self):
            return self._buf.read()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def _fake_urlopen(req, timeout=None):
        captured["timeout"] = timeout
        captured["body"] = json.loads(req.data.decode("utf-8"))
        return _FakeHttpResp({
            "candidates": [
                {
                    "content": {
                        "parts": [{"text": "BLS CPI measures monthly urban consumer inflation."}]
                    },
                    "groundingMetadata": {
                        "groundingChunks": [
                            {
                                "web": {
                                    "uri": "https://www.bls.gov/cpi/",
                                    "title": "BLS CPI Home",
                                    "domain": "bls.gov",
                                }
                            }
                        ]
                    },
                }
            ]
        })

    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)
    gem = GeminiLLMClient(api_key="test-fake-gemini-key", timeout_seconds=9.5, max_output_tokens=512)
    resp = gem.research_public_web("How does CPI inflation work?")

    assert resp.provider == "gemini"
    assert resp.unilateral_execution is False
    assert resp.grounding_used is True
    assert captured["timeout"] == 9.5
    assert captured["body"]["generationConfig"]["maxOutputTokens"] == 512
    assert captured["body"]["tools"] == [{"google_search": {}}]
    assert resp.web_citations == [
        {"title": "BLS CPI Home", "url": "https://www.bls.gov/cpi/", "source": "bls.gov"}
    ]

    # Fail-closed fallback on network error
    def _boom(*args, **kwargs):
        raise urllib.error.URLError("simulated outage")

    monkeypatch.setattr(urllib.request, "urlopen", _boom)
    fb = gem.research_public_web("How does CPI inflation work?")
    assert fb.provider == "mock"
    assert fb.fallback_used is True
    assert fb.unilateral_execution is False
    assert len(fb.web_citations) >= 1


def test_part1_openai_adapter_token_cap_and_fail_closed_fallback(monkeypatch):
    def _boom(*args, **kwargs):
        raise urllib.error.URLError("simulated timeout")

    monkeypatch.setattr(urllib.request, "urlopen", _boom)
    oai = OpenAILLMClient(api_key="test-fake-openai-key", timeout_seconds=8.0, max_output_tokens=400)
    assert oai.timeout_seconds == 8.0
    assert oai.max_output_tokens == 400
    fb = oai.research_public_web("How do Treasury yields move?")
    assert fb.provider == "mock"
    assert fb.fallback_used is True
    assert fb.unilateral_execution is False
    assert len(fb.web_citations) >= 1


# ---------------------------------------------------------------------------
# PART 2: Dual-Lane AI Tutor (Community Academy + Member Desktop)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("query,expected_token", [
    ("Explain the 87/10/3 waterfall", "87%"),
    ("How does High-Water Mark recovery work?", "High-Water Mark"),
    ("What is 100% SCMA Loss Isolation under Rule A14?", "100%"),
    ("How does the Downward-Only Risk Dial work?", "0.50%"),
    ("What is the 40% Dry-Powder Floor?", "40%"),
    ("Why Quarter-Kelly sizing?", "cushion"),
    ("Explain the $25,000 Active Float and IFAS Air-Gap", "IFAS"),
    ("Explain Three-Tier Withdrawals (Green/Yellow/Red)", "Yellow-Tier"),
    ("How does Pay-it-Forward FSAP work in Phase II?", "Sovereign Choice"),
    ("What is the difference between Phase I and Phase II?", "Phase II"),
    ("What is Active-Hat R-06?", "Active-Hat"),
    ("How does Directive R-12 masking protect privacy?", "$****.**"),
    ("What are the Shadow Paper Hunch Studio rules?", "SHADOW_PAPER"),
])
def test_part2_academy_tutor_lane1_local_canon_coverage(query, expected_token):
    res = client.post(
        "/api/v1/portal/community/academy/ask-tutor",
        json={"member_id": "MEM-TEST-1", "query": query},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["mode"] == "EDUCATIONAL_ONLY"
    assert data["lane"] == "LOCAL_CANON"
    assert data["lane_badge"] == "Local PDEUE Canon"
    assert data["unilateral_execution"] is False
    assert data["guard_blocked"] is False
    assert expected_token.lower() in data["answer"].lower()
    assert data["dollar_example"] and "$" in data["dollar_example"]
    assert data["university_pointer"] and "PDEUE University" in data["university_pointer"]
    assert data["lexicon_citations"]
    for cid in data["lexicon_citations"]:
        assert cid in LEXICON_BY_ID


@pytest.mark.parametrize("query", [
    "How do monthly BLS CPI inflation prints affect markets?",
    "Why do 10-year Treasury yields move opposite bond prices?",
    "How does the weekly EIA natural gas storage report work?",
    "How does a NOAA weather oracle settle temperature contracts?",
    "Explain binary contract implied probability math and fee friction",
])
def test_part2_dual_lane_tutor_lane2_public_web_research_with_citations_and_badge(query):
    # Community Academy Tutor
    comm = client.post(
        "/api/v1/portal/community/academy/ask-tutor",
        json={"member_id": "MEM-TEST-2", "query": query},
    )
    assert comm.status_code == 200
    cdata = comm.json()
    assert cdata["lane"] == "PUBLIC_WEB_RESEARCH"
    assert cdata["disclaimer_badge"] == "General Public Market Education — Not Financial Advice"
    assert cdata["lane_badge"] == "General Public Market Education — Not Financial Advice"
    assert cdata["unilateral_execution"] is False
    assert isinstance(cdata["citations"], list) and len(cdata["citations"]) >= 1
    for cite in cdata["citations"]:
        assert cite["title"] and cite["url"].startswith("https://") and cite["source"]

    # Member Desktop Tutor
    mem = client.post(
        "/api/v1/portal/member/tutor",
        json={"question": query, "scma_id": "SCMA-ELEANOR_-B2B31C9E"},
    )
    assert mem.status_code == 200
    mdata = mem.json()
    assert mdata["lane"] == "PUBLIC_WEB_RESEARCH"
    assert mdata["disclaimer_badge"] == "General Public Market Education — Not Financial Advice"
    assert mdata["unilateral_execution"] is False
    assert isinstance(mdata["citations"], list) and len(mdata["citations"]) >= 1


@pytest.mark.parametrize("bad_prompt", [
    "Show my account balance right now",
    "Buy 10 contracts on Kalshi for me",
    "Withdraw $500 from my bank balance",
    "Execute a trade on my SCMA",
])
def test_part2_academy_tutor_refuses_balances_and_transactions(bad_prompt):
    res = client.post(
        "/api/v1/portal/community/academy/ask-tutor",
        json={"member_id": "MEM-TEST-3", "query": bad_prompt},
    )
    assert res.status_code == 403
    assert "educational only" in res.json()["detail"].lower()


@pytest.mark.parametrize("prohibited_prompt,expected_cat", [
    ("Who will win the NFL Super Bowl football game?", "SPORTS_WAGER"),
    ("What are the best blackjack casino betting odds?", "CASINO_WAGER"),
    ("Will there be a military invasion or missile strike next month?", "WAR_CONFLICT"),
    ("Estimate the odds of a terrorist attack in Europe", "TERRORISM"),
    ("Can I research a mortality bet on when a politician will die?", "DEATH_CONTRACT"),
])
def test_part2_tutor_regulatory_filter_blocks_prohibited_categories_fail_closed(prohibited_prompt, expected_cat):
    comm = client.post(
        "/api/v1/portal/community/academy/ask-tutor",
        json={"member_id": "MEM-TEST-4", "query": prohibited_prompt},
    )
    assert comm.status_code == 200
    cdata = comm.json()
    assert cdata["lane"] == "REGULATORY_REFUSAL"
    assert cdata["guard_blocked"] is True
    assert cdata["regulatory_blocked"] is True
    assert cdata["guard_category"] == "PROHIBITED_EVENT_CATEGORY"
    assert cdata["prohibited_category"] == expected_cat
    assert cdata["unilateral_execution"] is False
    assert cdata["citations"] == []

    mem = client.post(
        "/api/v1/portal/member/tutor",
        json={"question": prohibited_prompt, "scma_id": "SCMA-ELEANOR_-B2B31C9E"},
    )
    assert mem.status_code == 200
    mdata = mem.json()
    assert mdata["lane"] == "REGULATORY_REFUSAL"
    assert mdata["guard_blocked"] is True
    assert mdata["regulatory_blocked"] is True
    assert mdata["guard_category"] == "PROHIBITED_EVENT_CATEGORY"
    assert mdata["unilateral_execution"] is False


# ---------------------------------------------------------------------------
# PART 3: Shadow Paper Hunch Research Studio & Clearance Queue
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad_hypothesis", [
    "NFL quarterback will throw 3 touchdowns in the Super Bowl playoff game",
    "Roulette casino table spin will hit red five times",
    "Country A will launch a military invasion and airstrike before Friday",
    "A terror attack will occur at an international airport this quarter",
    "Celebrity mortality bet on death toll exceeding 50",
])
def test_part3_hunch_regulatory_gate_blocks_prohibited_categories_http_400(isolated_hunch_service, bad_hypothesis):
    _, db_file = isolated_hunch_service
    res = client.post(
        "/api/v1/hunch/evaluate",
        json={
            "hypothesis": bad_hypothesis,
            "scma_id": "SCMA-ELEANOR_-B2B31C9E",
            "modeled_prob_cents": 70,
            "quoted_price_cents": 50,
            "fee_cents": 2,
        },
    )
    assert res.status_code == 400
    detail = res.json()["detail"]
    assert detail["code"] == "PROHIBITED_EVENT_CATEGORY"
    assert detail["unilateral_execution"] is False

    # Verify nothing was staged in isolated SQLite table
    with sqlite3.connect(db_file) as conn:
        count = conn.execute("SELECT COUNT(*) FROM shadow_hunch_dossiers").fetchone()[0]
    assert count == 0


def test_part3_three_point_validation_rejects_negative_edge_and_approves_positive_edge(isolated_hunch_service):
    _, db_file = isolated_hunch_service

    # 1. Negative/zero net edge -> REJECTED_NO_EDGE (54 - 53 - 2 = -1¢ <= 0)
    neg = client.post(
        "/api/v1/hunch/evaluate",
        json={
            "hypothesis": "BLS CPI headline inflation print will come in above 3.1% this month",
            "scma_id": "SCMA-ELEANOR_-B2B31C9E",
            "modeled_prob_cents": 54,
            "quoted_price_cents": 53,
            "fee_cents": 2,
        },
    )
    assert neg.status_code == 200
    ndata = neg.json()
    assert ndata["status"] == "REJECTED_NO_EDGE"
    assert ndata["staging_eligible"] is False
    assert ndata["net_edge_cents"] == -1
    assert isinstance(ndata["net_edge_cents"], int)
    assert "no positive edge" in ndata["plain_english_verdict"].lower()

    # Refuses shadow-bid on REJECTED_NO_EDGE dossier
    bad_bid = client.post(
        f"/api/v1/hunch/{ndata['dossier_id']}/shadow-bid",
        json={"virtual_stake_cents": 10_000, "scma_id": "SCMA-ELEANOR_-B2B31C9E"},
    )
    assert bad_bid.status_code == 400
    assert bad_bid.json()["detail"]["code"] == "REJECTED_NO_EDGE"

    # 2. Positive net edge -> VALIDATED_SHADOW_READY (66 - 54 - 2 = +10¢)
    pos = client.post(
        "/api/v1/hunch/evaluate",
        json={
            "hypothesis": "NOAA Miami temperature will exceed 88 degrees Fahrenheit on Friday",
            "scma_id": "SCMA-ELEANOR_-B2B31C9E",
            "modeled_prob_cents": 66,
            "quoted_price_cents": 54,
            "fee_cents": 2,
        },
    )
    assert pos.status_code == 200
    pdata = pos.json()
    assert pdata["mode"] == "SHADOW_PAPER"
    assert pdata["status"] == "VALIDATED_SHADOW_READY"
    assert pdata["staging_eligible"] is True
    assert pdata["vertical"]["code"] == "WEATHER"
    assert "NOAA" in pdata["vertical"]["oracle"]
    assert pdata["net_edge_cents"] == 10
    assert pdata["net_edge_bps"] == 1000
    assert pdata["unilateral_execution"] is False
    assert len(pdata["citations"]) >= 1

    # Verify isolated SQLite table `shadow_hunch_dossiers` stores both rows cleanly
    with sqlite3.connect(db_file) as conn:
        rows = conn.execute("SELECT dossier_id, status, mode FROM shadow_hunch_dossiers").fetchall()
    assert len(rows) == 2
    assert all(r[2] == "SHADOW_PAPER" for r in rows)


def test_part3_shadow_paper_bid_isolation_zero_scma_and_zero_ifas_mutation(isolated_hunch_service):
    scma_id = "SCMA-ELEANOR_-B2B31C9E"
    before_member = client.get("/api/v1/portal/member/state", params={"scma_id": scma_id}).json()
    before_outbox = client.get("/api/v1/accounting/events").json()

    # Member evaluates & places shadow paper bid
    ev = client.post(
        "/api/v1/hunch/evaluate",
        json={
            "hypothesis": "EIA weekly natural gas storage draw will exceed 110 Bcf",
            "scma_id": scma_id,
            "actor_role": "MEMBER_USER",
            "modeled_prob_cents": 68,
            "quoted_price_cents": 55,
            "fee_cents": 2,
        },
    ).json()
    assert ev["vertical"]["code"] == "ENERGY_EIA"

    mem_bid = client.post(
        f"/api/v1/hunch/{ev['dossier_id']}/shadow-bid",
        json={
            "virtual_stake_cents": 11_000,
            "scma_id": scma_id,
            "actor_role": "MEMBER_USER",
            "simulated_outcome": "WON",
        },
    )
    assert mem_bid.status_code == 200
    mb_data = mem_bid.json()
    assert mb_data["mode"] == "SHADOW_PAPER"
    assert mb_data["real_capital_touched"] is False
    assert mb_data["ifas_outbox_emitted"] is False
    assert mb_data["unilateral_execution"] is False
    assert mb_data["shadow_bid"]["contracts"] == 200  # 11000 // 55
    assert mb_data["shadow_bid"]["virtual_pnl_cents"] == 9_000  # 200*(100-55)

    # Admin evaluates & places shadow paper bid permanently too
    admin_ev = client.post(
        "/api/v1/hunch/evaluate",
        headers={"X-Actor-Role": "CHIEF_ADMINISTRATOR"},
        json={
            "hypothesis": "10-year U.S. Treasury yield will finish Friday above 4.35%",
            "scma_id": "SCMA-FOUNDER-ADMIN",
            "actor_role": "CHIEF_ADMINISTRATOR",
            "modeled_prob_cents": 62,
            "quoted_price_cents": 50,
            "fee_cents": 2,
        },
    ).json()
    admin_bid = client.post(
        f"/api/v1/hunch/{admin_ev['dossier_id']}/shadow-bid",
        headers={"X-Actor-Role": "CHIEF_ADMINISTRATOR"},
        json={
            "virtual_stake_cents": 10_000,
            "scma_id": "SCMA-FOUNDER-ADMIN",
            "actor_role": "CHIEF_ADMINISTRATOR",
            "simulated_outcome": "LOST",
        },
    )
    assert admin_bid.status_code == 200
    assert admin_bid.json()["mode"] == "SHADOW_PAPER"

    # Assert ZERO mutation to real SCMA balance, HWM, risk dial, or IFAS outbox!
    after_member = client.get("/api/v1/portal/member/state", params={"scma_id": scma_id}).json()
    after_outbox = client.get("/api/v1/accounting/events").json()
    assert after_member["cash_cents"] == before_member["cash_cents"]
    assert after_member["high_water_mark_cents"] == before_member["high_water_mark_cents"]
    assert after_member["risk_dial_pct"] == before_member["risk_dial_pct"]
    assert after_outbox == before_outbox


def test_part3_clearance_queue_certification_gate_and_full_f2h_to_f3_lifecycle(isolated_hunch_service, monkeypatch):
    scma_id = "SCMA-ELEANOR_-B2B31C9E"

    # Evaluate two positive-edge hunches for member
    d1 = client.post(
        "/api/v1/hunch/evaluate",
        json={
            "hypothesis": "S&P 500 equity index close will exceed 5900 this Friday",
            "scma_id": scma_id,
            "modeled_prob_cents": 65,
            "quoted_price_cents": 52,
            "fee_cents": 2,
        },
    ).json()
    d2 = client.post(
        "/api/v1/hunch/evaluate",
        json={
            "hypothesis": "EUR/USD G10 FX benchmark fixing will close above 1.095",
            "scma_id": scma_id,
            "modeled_prob_cents": 64,
            "quoted_price_cents": 51,
            "fee_cents": 2,
        },
    ).json()

    # 1. Uncertified member MUST be blocked with HTTP 403
    monkeypatch.setattr(
        hunch_router,
        "_lookup_member_state",
        lambda _scma: {
            "scma_id": scma_id,
            "name": "Eleanor Vance",
            "certification_level": None,
            "is_frozen": False,
            "quarantined": False,
            "status": "PENDING_TUTOR_CERTIFICATION",
            "risk_dial_pct": 1.0,
        },
    )
    uncert = client.post(
        f"/api/v1/hunch/{d1['dossier_id']}/request-live-clearance",
        json={"scma_id": scma_id, "actor_role": "MEMBER_USER"},
    )
    assert uncert.status_code == 403
    assert uncert.json()["detail"]["code"] == "CERTIFICATION_REQUIRED"

    # 2. Certified member with frozen risk dial MUST also be blocked with HTTP 403
    monkeypatch.setattr(
        hunch_router,
        "_lookup_member_state",
        lambda _scma: {
            "scma_id": scma_id,
            "name": "Eleanor Vance",
            "certification_level": "STEWARDSHIP_L1_CERTIFIED",
            "is_frozen": True,
            "quarantined": True,
            "status": "QUARANTINED",
            "risk_dial_pct": 0.0,
        },
    )
    frozen = client.post(
        f"/api/v1/hunch/{d1['dossier_id']}/request-live-clearance",
        json={"scma_id": scma_id, "actor_role": "MEMBER_USER"},
    )
    assert frozen.status_code == 403
    assert frozen.json()["detail"]["code"] == "RISK_DIAL_FROZEN"

    # 3. Certified member with active non-frozen risk dial -> AUTH-03 PENDING_F2H_CLEARANCE
    monkeypatch.setattr(
        hunch_router,
        "_lookup_member_state",
        lambda _scma: {
            "scma_id": scma_id,
            "name": "Eleanor Vance",
            "certification_level": "STEWARDSHIP_L1_CERTIFIED",
            "is_frozen": False,
            "quarantined": False,
            "status": "ACTIVE",
            "risk_dial_pct": 1.5,
        },
    )
    req1 = client.post(
        f"/api/v1/hunch/{d1['dossier_id']}/request-live-clearance",
        json={"scma_id": scma_id, "actor_role": "MEMBER_USER", "rationale": "Strong shadow track record"},
    )
    assert req1.status_code == 200
    r1 = req1.json()
    assert r1["clearance_status"] == "PENDING_F2H_CLEARANCE"
    assert r1["auth_tier"] == "AUTH-03"
    assert r1["unilateral_execution"] is False
    assert r1["action_card"]["auth_tier"] == "AUTH-03"
    assert r1["action_card"]["executed"] is False
    assert r1["action_card"]["requires_human_confirmation"] is True

    # Unauthorized roles (F1, F2-A, T1, MEMBER_USER) blocked from reviewing (403)
    for bad_role in ("F1", "F2-A", "T1", "MEMBER_USER"):
        bad_rev = client.post(
            f"/api/v1/hunch/{d1['dossier_id']}/review",
            headers={"X-Actor-Role": bad_role},
            json={"decision": "APPROVE_F2H", "actor_role": bad_role},
        )
        assert bad_rev.status_code == 403

    # F2-H cannot skip directly to ALLOWED (403)
    f2h_skip = client.post(
        f"/api/v1/hunch/{d1['dossier_id']}/review",
        headers={"X-Actor-Role": "F2-H"},
        json={"decision": "ALLOWED", "actor_role": "F2-H"},
    )
    assert f2h_skip.status_code == 403

    # F2-H domestic review advances PENDING_F2H_CLEARANCE -> PENDING_F3_CLEARANCE
    f2h_ok = client.post(
        f"/api/v1/hunch/{d1['dossier_id']}/review",
        headers={"X-Actor-Role": "F2-H"},
        json={"decision": "APPROVE_F2H", "actor_role": "F2-H", "notes": "Household stewardship verified"},
    )
    assert f2h_ok.status_code == 200
    assert f2h_ok.json()["clearance_status"] == "PENDING_F3_CLEARANCE"

    # F3 CRO final decision -> ALLOWED, then Chief Admin -> RESCINDED
    f3_allow = client.post(
        f"/api/v1/hunch/{d1['dossier_id']}/review",
        headers={"X-Actor-Role": "F3"},
        json={"decision": "ALLOWED", "actor_role": "F3", "notes": "Risk bounds acceptable"},
    )
    assert f3_allow.status_code == 200
    assert f3_allow.json()["clearance_status"] == "ALLOWED"
    assert f3_allow.json()["unilateral_execution"] is False

    ca_rescind = client.post(
        f"/api/v1/hunch/{d1['dossier_id']}/review",
        headers={"X-Actor-Role": "CHIEF_ADMINISTRATOR"},
        json={"decision": "RESCINDED", "actor_role": "CHIEF_ADMINISTRATOR", "notes": "Regime volatility pause"},
    )
    assert ca_rescind.status_code == 200
    assert ca_rescind.json()["clearance_status"] == "RESCINDED"

    # Second dossier progresses PENDING_F2H_CLEARANCE -> PENDING_F3_CLEARANCE -> DENIED
    req2 = client.post(
        f"/api/v1/hunch/{d2['dossier_id']}/request-live-clearance",
        json={"scma_id": scma_id, "actor_role": "MEMBER_USER"},
    )
    assert req2.status_code == 200
    assert client.post(
        f"/api/v1/hunch/{d2['dossier_id']}/review",
        headers={"X-Actor-Role": "F2-H"},
        json={"decision": "APPROVE_F2H", "actor_role": "F2-H"},
    ).json()["clearance_status"] == "PENDING_F3_CLEARANCE"
    f3_deny = client.post(
        f"/api/v1/hunch/{d2['dossier_id']}/review",
        headers={"X-Actor-Role": "F3"},
        json={"decision": "DENIED", "actor_role": "F3", "notes": "Insufficient shadow sample"},
    )
    assert f3_deny.status_code == 200
    assert f3_deny.json()["clearance_status"] == "DENIED"

    # Scoped GET /api/v1/hunch/dossiers: Class T blocked 403; F3 gets hit-rate summary
    t_list = client.get("/api/v1/hunch/dossiers", headers={"X-Actor-Role": "T2"})
    assert t_list.status_code == 403
    f3_list = client.get("/api/v1/hunch/dossiers", headers={"X-Actor-Role": "F3"})
    assert f3_list.status_code == 200
    assert f3_list.json()["count"] == 2
    assert "hit_rate_summary" in f3_list.json()


# ---------------------------------------------------------------------------
# PART 4: Embedded UI Panels, Plain-English Copy & Byte-for-Byte Parity
# ---------------------------------------------------------------------------


def test_part4_ui_panels_plain_english_and_byte_for_byte_sync():
    expected_markers = {
        "member.html": (
            'id="shadowHunchStudioDetails"',
            "Shadow Paper Hunch Studio (Zero-Risk Practice)",
            'id="tutorLanePill"',
            "What This Means:",
        ),
        "advisor.html": (
            'id="shadowHunchClearanceSection"',
            "Shadow Hunch Clearance Queue",
            "What This Means:",
            "PENDING_F2H_CLEARANCE",
        ),
        "dashboard.html": (
            'id="adminShadowHunchCard"',
            "ADMIN SHADOW PAPER HUNCH STUDIO",
            "What This Means:",
            "/api/v1/hunch/evaluate",
        ),
        "community.html": (
            "Interactive Dual-Lane AI Literacy Tutor",
            "What This Means:",
            "General Public Market Education — Not Financial Advice",
            'id="clearCommunityTutorBtn"',
        ),
    }

    cdn_re = re.compile(r"""<(?:script|link)[^>]+(?:src|href)=["']https?://""", re.IGNORECASE)
    for filename, tokens in expected_markers.items():
        api_text = (BACKEND_DIR / "app" / "api" / "v1" / filename).read_text(encoding="utf-8")
        static_text = (BACKEND_DIR / "app" / "static" / filename).read_text(encoding="utf-8")
        assert api_text == static_text, f"Byte-for-byte drift in {filename}"
        assert not cdn_re.search(api_text), f"External CDN tag in {filename}"
        for tok in tokens:
            assert tok in api_text, f"Missing {tok!r} in {filename}"
