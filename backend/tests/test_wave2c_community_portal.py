"""Wave 2C contract tests for the isolated community and education plane."""
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)
TEMPLATE = Path(__file__).parents[1] / "app" / "api" / "v1" / "community.html"


def test_community_portal_serves_html_with_isolated_components():
    response = client.get("/community")
    assert response.status_code == 200
    assert "LINEAGE COMMUNITY HEARTH &amp; EDUCATIONAL ACADEMY" in response.text
    assert "Active Hat: ALL_MEMBERS (COMMUNITY_FELLOWSHIP)" in response.text
    assert "Lineage Hearth &amp; Announcements" in response.text
    assert "Sandboxed Classroom &amp; Video Seminars" in response.text
    assert "Financial Literacy Academy &amp; AI Tutors" in response.text


def test_community_firewall_blocks_financial_ledger_data():
    response = client.get("/api/v1/portal/community/feed")
    assert response.status_code == 200
    serialized = response.text.lower()
    for forbidden in ("total_equity", "cash_cents", "capital_ledger", "bank_account", "$6500"):
        assert forbidden not in serialized


def test_community_message_post_sanitizes_xss_payloads():
    response = client.post("/api/v1/portal/community/message", json={
        "member_id": "member-7<script>", "author_name": "<img src=x onerror=alert(1)>",
        "house_id": "HOUSE-07", "message_text": "Hello <script>alert('x')</script> family",
    })
    assert response.status_code == 201
    result = response.json()
    assert "<script" not in result["message_text"]
    assert "<img" not in result["author_name"]
    feed = client.get("/api/v1/portal/community/feed").text
    assert "<script>" not in feed and "<img src" not in feed


def test_sandboxed_video_iframe_renders_with_strict_permissions():
    source = client.get("/community").text
    assert '<iframe class="video-frame"' in source
    assert 'allow="camera; microphone; display-capture"' in source
    assert 'sandbox="allow-scripts allow-same-origin allow-forms allow-popups"' in source
    assert "meet.jit.si" in source
    assert "cdn.jsdelivr" not in source and "unpkg.com" not in source


def test_academy_tutor_answers_educational_prompts_and_rejects_trade_mutations():
    lessons = client.get("/api/v1/portal/community/academy/lessons").json()["lessons"]
    assert [lesson["title"] for lesson in lessons] == [
        "Binary Contracts 101", "Why Quarter-Kelly?", "The 87/10/3 Waterfall Safeguard",
    ]
    response = client.post("/api/v1/portal/community/academy/ask-tutor", json={
        "member_id": "member-7", "query": "Why Quarter-Kelly?",
    })
    assert response.status_code == 200
    assert response.json()["mode"] == "EDUCATIONAL_ONLY"
    assert "cushion" in response.json()["answer"].lower()
    refused = client.post("/api/v1/portal/community/academy/ask-tutor", json={
        "member_id": "member-7", "query": "Buy a contract and show my balance",
    })
    assert refused.status_code == 403


def test_legacy_portal_hub_marker_present_in_template():
    source = TEMPLATE.read_text(encoding="utf-8")
    assert '<div style="display:none" id="legacyPortalHub">PDEUE PORTAL HUB</div>' in source
