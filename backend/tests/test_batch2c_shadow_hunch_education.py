"""Batch 2C — Shadow Hunch How-To Education, PDEUE University Sync & Novice Alignment Tests."""
from __future__ import annotations

from pathlib import Path
import re

from fastapi.testclient import TestClient

from app.domain.lexicon_v05 import LEXICON_BY_ID
from app.main import app

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
API_V1_DIR = BACKEND_DIR / "app" / "api" / "v1"
STATIC_DIR = BACKEND_DIR / "app" / "static"
USER_QUICKSTART_PATH = REPO_ROOT / "docs" / "manuals" / "USER_QUICKSTART.md"

CDN_RE = re.compile(r"""<(?:script|link)[^>]+(?:src|href)=["']https?://""", re.IGNORECASE)
NATIVE_DIALOG_RE = re.compile(r"""\b(?:alert|confirm|prompt)\s*\(""")


def _read_synced_template(filename: str) -> str:
    api_path = API_V1_DIR / filename
    static_path = STATIC_DIR / filename
    assert api_path.exists(), f"Missing {api_path}"
    assert static_path.exists(), f"Missing {static_path}"
    api_text = api_path.read_text(encoding="utf-8")
    static_text = static_path.read_text(encoding="utf-8")
    assert api_text == static_text, f"Byte-for-byte drift between {api_path} and {static_path}"
    assert not CDN_RE.search(api_text), f"External CDN tag detected in {filename}"
    assert not NATIVE_DIALOG_RE.search(api_text), f"Native browser dialog detected in {filename}"
    return api_text


def test_part1_member_shadow_hunch_walkthrough_and_example_helper():
    html = _read_synced_template("member.html")

    # Collapsible 4-step walkthrough inside Shadow Paper Hunch Studio
    assert 'id="memberShadowHunchHowTo"' in html
    assert "📘 How to Run a Shadow Hunch — Step-by-Step" in html
    for token in (
        "Step 1 — Write a Grounded Hypothesis",
        "NOAA forecasts a 95°F heat wave in Phoenix this week, making the high-temp contract underpriced at 42¢",
        "Step 2 — Run the 3-Point Check",
        "VALIDATED",
        "VALIDATED_SHADOW_READY",
        "REJECTED_NO_EDGE",
        "PROHIBITED_EVENT_CATEGORY",
        "Step 3 — Log a Zero-Risk Shadow Paper Bid",
        "Shadow Hit-Rate",
        "Step 4 — Optional Live Clearance",
        "STEWARDSHIP_L1_CERTIFIED",
        "unilateral_execution = False",
    ):
        assert token in html, f"Missing expected walkthrough token in member.html: {token!r}"

    # Client-side 1-click Load Example Hunch helper button & handler
    assert 'id="memberLoadExampleHunchBtn"' in html
    assert "Load Example Hunch" in html
    assert "function loadExampleMemberHunch()" in html

    # Served cleanly over FastAPI route
    with TestClient(app) as client:
        resp = client.get("/member")
        assert resp.status_code == 200
        assert 'id="memberShadowHunchHowTo"' in resp.text
        assert 'id="memberLoadExampleHunchBtn"' in resp.text


def test_part1_advisor_and_dashboard_shadow_hunch_guides():
    advisor_html = _read_synced_template("advisor.html")
    assert 'id="advisorShadowHunchHowTo"' in advisor_html
    assert "📘 How to Review a Member's Hunch Proposal" in advisor_html
    for token in (
        "F1 Peer Guides &amp; F2-A Lineage Advisors (Strictly Read-Only)",
        "PENDING_F2H_CLEARANCE",
        "PENDING_F3_CLEARANCE",
        "ALLOWED",
        "DENIED",
        "RESCINDED",
        "unilateral_execution = False",
    ):
        assert token in advisor_html, f"Missing advisor guide token: {token!r}"

    dashboard_html = _read_synced_template("dashboard.html")
    assert 'id="adminShadowHunchHowTo"' in dashboard_html
    assert "📘 Admin Parallel Shadow Testing Guide" in dashboard_html
    assert 'id="adminLoadExampleHunchBtn"' in dashboard_html
    assert "function loadExampleAdminHunch()" in dashboard_html
    for token in (
        "SHADOW_PAPER",
        "shadow_hunch_dossiers",
        "VALIDATED_SHADOW_READY",
        "REJECTED_NO_EDGE",
        "PROHIBITED_EVENT_CATEGORY",
        "unilateral_execution = False",
    ):
        assert token in dashboard_html, f"Missing dashboard guide token: {token!r}"

    with TestClient(app) as client:
        adv_resp = client.get("/advisor?role=F2-H")
        assert adv_resp.status_code == 200
        assert 'id="advisorShadowHunchHowTo"' in adv_resp.text

        dash_resp = client.get("/dashboard")
        assert dash_resp.status_code == 200
        assert 'id="adminShadowHunchHowTo"' in dash_resp.text
        assert 'id="adminLoadExampleHunchBtn"' in dash_resp.text


def test_part1_worked_example_hunch_validates_live_against_api():
    """The Phoenix 95°F worked example pre-filled by Load Example Hunch must validate cleanly with +14¢ net edge."""
    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/hunch/evaluate",
            headers={"X-Actor-Role": "MEMBER_USER"},
            json={
                "hypothesis": "NOAA forecasts a 95°F heat wave in Phoenix this week, making the high-temp contract underpriced at 42¢",
                "vertical_hint": "WEATHER",
                "modeled_prob_cents": 58,
                "quoted_price_cents": 42,
                "fee_cents": 2,
                "scma_id": "SCMA-ELEANOR_-B2B31C9E",
                "actor_role": "MEMBER_USER",
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "VALIDATED_SHADOW_READY"
        assert body["mode"] == "SHADOW_PAPER"
        assert body["net_edge_cents"] == 14
        assert body["staging_eligible"] is True
        assert body["unilateral_execution"] is False


def test_part2_companion_deep_dives_live_today_and_five_beat_shadow_walkthrough():
    html = _read_synced_template("companion.html")

    assert "Paired with Batch 2B" not in html, "Batch 2B placeholder badge should be promoted to Live Today"

    # Extract dd_ai_tutor block
    ai_match = re.search(r"id:'dd_ai_tutor'[\s\S]*?id:'dd_shadow_hunch'", html)
    assert ai_match, "dd_ai_tutor block missing in companion.html"
    ai_block = ai_match.group(0)
    assert "badge:'Live Today'" in ai_block
    assert "badgeClass:'lib-badge-core'" in ai_block
    assert "/community and /member" in ai_block
    assert "Lane 1 (Local Family Canon)" in ai_block
    assert "Lane 2 (Public Market Research)" in ai_block
    assert "unilateral_execution = False" in ai_block

    # Extract dd_shadow_hunch block and verify all 5 operational beats
    hunch_match = re.search(r"id:'dd_shadow_hunch'[\s\S]*?\n\];", html)
    assert hunch_match, "dd_shadow_hunch block missing in companion.html"
    hunch_block = hunch_match.group(0)
    assert "badge:'Live Today'" in hunch_block
    assert "badgeClass:'lib-badge-core'" in hunch_block
    assert "duration:'5 min'" in hunch_block
    beat_headings = re.findall(r"\{heading:'([^']+)'", hunch_block)
    assert len(beat_headings) == 5, f"Expected 5 operational beats in dd_shadow_hunch, got {len(beat_headings)}: {beat_headings}"
    for token in (
        "95°F heat wave in Phoenix",
        "3-Point Validation",
        "VALIDATED_SHADOW_READY",
        "REJECTED_NO_EDGE",
        "PROHIBITED_EVENT_CATEGORY",
        "SHADOW_PAPER",
        "Shadow Hit-Rate",
        "STEWARDSHIP_L1_CERTIFIED",
        "F2-H",
        "F3",
        "unilateral_execution",
    ):
        assert token in hunch_block, f"Missing {token!r} in dd_shadow_hunch 5-beat walkthrough"


def test_part3_user_quickstart_novice_alignment_and_governance_locks():
    text = USER_QUICKSTART_PATH.read_text(encoding="utf-8")

    # Novice-facing headings must be clean plain English (no raw ADR-012 / Rule A14 / SHTF in Markdown headings)
    headings = re.findall(r"^#{1,6}\s+(.+)$", text, flags=re.MULTILINE)
    assert any("4. Keeping What You Earn: The 87/10/3 Profit Waterfall & High-Water Mark" in h for h in headings)
    assert any("6A. Testing Ideas Safely: How to Run the Shadow Paper Hunch Studio" in h for h in headings)
    assert any("11. Three-Stage Governance Lifecycle & Family Charter" in h for h in headings)
    for heading in headings:
        assert "ADR-012" not in heading, f"Raw ADR-012 should live in body notes, not heading: {heading}"
        assert "Rule A14" not in heading, f"Raw Rule A14 should live in body notes, not heading: {heading}"
        assert "SHTF" not in heading, f"Raw SHTF should live in body notes, not heading: {heading}"

    # Section 6 Dual-Lane AI Tutor + Section 6A Shadow Paper Hunch Studio content
    for token in (
        "Lane 1 — Local Family Canon",
        "Lane 2 — Public Market Research with Citations",
        "unilateral_execution = False",
        "Step 1 — Write a Grounded Hypothesis",
        "NOAA forecasts a 95°F heat wave in Phoenix this week, making the high-temp contract underpriced at 42¢",
        "Step 2 — Run the 3-Point Check",
        "VALIDATED_SHADOW_READY",
        "REJECTED_NO_EDGE",
        "PROHIBITED_EVENT_CATEGORY",
        "Step 3 — Log a Zero-Risk Shadow Paper Bid",
        "Step 4 — Optional Live Clearance",
        "STEWARDSHIP_L1_CERTIFIED",
        "PENDING_F2H_CLEARANCE",
        "PENDING_F3_CLEARANCE",
        "ALLOWED",
        "DENIED",
        "RESCINDED",
        "DEATH BETS Act",
    ):
        assert token in text, f"Missing {token!r} in USER_QUICKSTART.md"

    # Formal C6 governance lifecycle & ADR test locks preserved in body
    for lock in (
        "Three-Stage Governance Lifecycle",
        "EXECUTIVE_COMMAND",
        "ADVISORY_PETITION_FILTER",
        "BICAMERAL_VETO_ACTIVE",
        "SHTF",
        "IMMUTABLE_CORE_INVARIANT",
        "ADR-008",
        "ADR-011",
        "ADR-012",
        "Rule A14",
        "R-04",
        "R-12",
    ):
        assert lock in text, f"Required test lock missing from USER_QUICKSTART.md: {lock!r}"


def test_part3_member_html_novice_alignment_zero_raw_lccf_and_valid_lexicon_terms():
    html = _read_synced_template("member.html")

    # Zero raw uppercase LCCF remnants in member.html while preserving Lexicon term id
    assert "LCCF" not in html, "Raw LCCF remnant should be replaced with Pay-It-Forward & FSAP in member.html"
    assert 'data-term="pay-it-forward-lccf"' in html
    assert "Phase I Paper Mode" in html
    assert "DUAL-LANE AI LITERACY TUTOR" in html

    # Every data-term in all modified templates must be registered in LEXICON_BY_ID
    for filename in ("member.html", "advisor.html", "dashboard.html", "companion.html"):
        src = _read_synced_template(filename)
        for term_id in re.findall(r'data-term="([^"]+)"', src):
            assert term_id in LEXICON_BY_ID, f"Unregistered data-term={term_id!r} in {filename}"
