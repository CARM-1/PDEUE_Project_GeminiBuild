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
    ):
        assert f'id="{element_id}"' in markup


def test_all_active_portals_link_to_the_university():
    roots = (Path(__file__).parents[1] / "app" / "api" / "v1", Path(__file__).parents[1] / "app" / "static")
    for root in roots:
        for portal in ("dashboard.html", "member.html", "advisor.html", "tech.html"):
            markup = (root / portal).read_text(encoding="utf-8")
            assert '<a href="/companion" class="nav-link campus-link" id="navCompanionLink">' in markup
