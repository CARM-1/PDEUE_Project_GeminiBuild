"""HTTP and offline-integrity contracts for the PDEUE University campus."""
import re
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)
COMPANION = Path(__file__).parents[1] / "app" / "static" / "companion.html"


def test_companion_page_is_registered_html():
    response = client.get("/companion")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "PDEUE University: Sovereign Academy" in response.text


def test_companion_state_registers_all_six_chapters_and_invariants():
    response = client.get("/api/v1/portal/companion/state")
    assert response.status_code == 200
    state = response.json()
    assert [chapter["number"] for chapter in state["chapters"]] == list(range(1, 7))
    assert state["audio"]["fallback"] == "silent_timeline"
    assert {"ADR-008", "ADR-011", "risk", "offline"} == set(state["invariants"])


def test_companion_is_zero_cdn_and_exposes_required_dom_contract():
    markup = COMPANION.read_text(encoding="utf-8")
    external_assets = re.findall(
        r"<(?:script|link)\b[^>]+(?:src|href)=[\"']https?://", markup, re.IGNORECASE
    )
    assert external_assets == []
    for element_id in (
        "companion-timeline",
        "chapter-waterfall",
        "chapter-risk-governor",
        "navCompanionLink",
        "dynamic-outbox-container",
        "classification-tier-containers",
        "manual-reader-container",
    ):
        assert f'id="{element_id}"' in markup


def test_all_active_portals_link_to_the_university():
    roots = (Path(__file__).parents[1] / "app" / "api" / "v1", Path(__file__).parents[1] / "app" / "static")
    for root in roots:
        for portal in ("dashboard.html", "member.html", "advisor.html", "tech.html"):
            markup = (root / portal).read_text(encoding="utf-8")
            assert '<a href="/companion" class="nav-link campus-link" id="navCompanionLink">' in markup


def test_companion_wires_web_speech_and_deep_interactions():
    markup = COMPANION.read_text(encoding="utf-8")
    assert "window.speechSynthesis" in markup
    assert "SpeechSynthesisUtterance" in markup
    assert "scrollIntoView({ behavior: 'smooth', block: 'center' })" in markup
    assert "sha256-mock-sweep-sig-ok" in markup
    assert all(tier in markup for tier in ("tierGreen", "tierYellow", "tierRed"))


def test_manual_reader_loads_each_canonical_markdown_manual():
    manuals = (
        "USER_QUICKSTART.md",
        "CLASS_F_FINANCIAL_MANUAL.md",
        "CLASS_T_TECHNICAL_MANUAL.md",
        "CHIEF_ADMIN_RUNBOOK.md",
    )
    for manual in manuals:
        response = client.get(f"/api/v1/portal/companion/manual/{manual}")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/markdown")
        assert response.text.startswith("# ")


def test_role_navigation_is_siloed():
    api_templates = Path(__file__).parents[1] / "app" / "api" / "v1"
    member = (api_templates / "member.html").read_text(encoding="utf-8").split("</nav>", 1)[0]
    advisor = (api_templates / "advisor.html").read_text(encoding="utf-8").split("</nav>", 1)[0]
    tech = (api_templates / "tech.html").read_text(encoding="utf-8").split("</nav>", 1)[0]
    assert "Active Hat: MEMBER_USER" in member and "/dashboard" not in member and "/admin/tech" not in member
    assert "Lineal Advisory &amp; Trusts" in advisor and "/member" not in advisor and "/admin/tech" not in advisor
    assert "Technical Console (Class T)" in tech and "/advisor" not in tech and "/member" not in tech
