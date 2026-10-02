"""Regression coverage for the WP-6B client-only clear controls."""

import re
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)
GREETING = (
    "PDEUE Governance Copilot online. Ask a question regarding risk envelopes, "
    "settlement mechanics, or decision packets."
)
MODIFIED_SURFACES = (
    Path("app/api/v1/member.html"),
    Path("app/static/member.html"),
    Path("app/api/v1/dashboard.html"),
    Path("app/static/dashboard.html"),
    Path("app/api/v1/tech.html"),
    Path("app/static/tech_console.html"),
    Path("app/api/v1/advisor.html"),
    Path("app/static/advisor.html"),
    Path("app/static/templates/advisor.html"),
)


def _function_body(page: str, function_name: str) -> str:
    match = re.search(rf"function {function_name}\(\)\s*\{{([^}}]+)\}}", page)
    assert match, f"missing {function_name}"
    return match.group(1)


def test_member_clear_control_is_client_only_and_restores_placeholder():
    page = client.get("/member").text
    handler = _function_body(page, "clearTutorAnswer")
    assert 'id="clearTutorBtn"' in page
    assert 'type="button"' in page
    assert "Your educational answer will appear here." in handler
    assert ".value=''" in handler
    assert ".focus()" in handler
    assert "fetch(" not in handler


def test_dashboard_clear_control_preserves_governance_greeting():
    page = client.get("/dashboard").text
    handler = _function_body(page, "clearCopilotChat")
    assert 'id="clearCopilotBtn"' in page
    assert 'aria-label="Clear current conversation and reset prompt"' in page
    assert GREETING in page
    assert GREETING in handler
    assert ".focus()" in handler
    assert "fetch(" not in handler


def test_advisor_clear_control_is_client_only_and_restores_placeholder():
    page = client.get("/advisor").text
    handler = _function_body(page, "clearAdvisorCopilot")
    assert 'id="clearAdvisorCopilotBtn"' in page
    assert 'aria-label="Clear displayed guidance and input"' in page
    assert "Your educational answer will appear here." in handler
    assert ".focus()" in handler
    assert "fetch(" not in handler


def test_modified_surfaces_do_not_load_external_cdn_scripts():
    external_script = re.compile(r'<script[^>]+src=["\']https?://', re.IGNORECASE)
    for path in MODIFIED_SURFACES:
        assert not external_script.search(path.read_text(encoding="utf-8")), path
