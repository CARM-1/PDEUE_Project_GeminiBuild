import json
from html.parser import HTMLParser
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.security import create_access_token
from app.main import app
from app.api.v1 import workspace_router


class BindingParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.bindings = set()
        self.external_urls = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if values.get("data-bind"):
            self.bindings.add(values["data-bind"])
        for key in ("src", "href"):
            value = values.get(key, "")
            if value.startswith(("http://", "https://")):
                self.external_urls.append(value)


def identity(subject="founder-1", role="FOUNDER"):
    return create_access_token({"sub": subject, "role": role})


def select(client, token, hat):
    return client.post(
        "/api/v1/workspace/hat-sessions/select",
        headers={"Authorization": f"Bearer {token}"},
        json={"hat": hat, "confirmed": True},
    )


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_truthful_empty_contracts_and_integer_money_when_authoritative():
    client = TestClient(app)
    selected = select(client, identity(), "CHIEF_ADMINISTRATOR")
    assert selected.status_code == 200
    token = selected.json()["access_token"]
    empty = client.get("/api/v1/workspace/capital-summary", headers=auth(token)).json()
    assert empty["schema_version"] == "rca.capital-summary.v1"
    assert empty["qualification_state"] == "QUALIFICATION_PENDING"
    assert empty["data"] is None
    assert "DRY_POWDER_POLICY_UNRESOLVED" in empty["reason_codes"]

    service = workspace_router._founder_service
    service.ledger.balance_cents = 12345
    service.ledger.central_family_pool_cents = 200
    service.ledger.founder_pool_cents = 60
    service.dry_powder_policy = {"floor_cents": 4000, "version": "accepted-test-v1", "status": "ACTIVE"}
    service.authoritative_as_of_utc = "2026-09-20T00:00:00+00:00"
    qualified = client.get("/api/v1/workspace/capital-summary", headers=auth(token)).json()
    assert qualified["qualification_state"] == "QUALIFIED"
    money = qualified["data"]
    for field in ("total_equity_cents", "unreserved_cash_cents", "dry_powder_floor_cents", "cfcp_balance_cents", "faep_balance_cents"):
        assert type(money[field]) is int
    service.dry_powder_policy = None
    service.authoritative_as_of_utc = None


def test_active_hat_switch_revokes_old_token_and_isolates_routes():
    client = TestClient(app)
    chief = select(client, identity("founder-switch"), "CHIEF_ADMINISTRATOR").json()["access_token"]
    assert client.get("/api/v1/workspace/capital-summary", headers=auth(chief)).status_code == 200
    assert client.get("/api/v1/workspace/personal-scma", headers=auth(chief)).status_code == 403

    personal_response = select(client, chief, "PERSONAL_SCMA")
    assert personal_response.status_code == 200
    personal = personal_response.json()["access_token"]
    assert client.get("/api/v1/workspace/capital-summary", headers=auth(chief)).status_code == 403
    assert client.get("/api/v1/workspace/capital-summary", headers=auth(personal)).status_code == 403
    own = client.get("/api/v1/workspace/personal-scma", headers=auth(personal))
    assert own.status_code == 200
    assert own.json()["data"] is None
    assert "FOUNDER_ACCOUNT_OWNERSHIP_MAPPING_UNAVAILABLE" in own.json()["reason_codes"]

    replay = client.get("/api/v1/workspace/personal-scma", headers=auth(chief))
    assert replay.status_code == 403


def test_t3_cannot_select_founder_hat_or_use_controls():
    client = TestClient(app)
    denied = select(client, identity("tech", "T3"), "CHIEF_ADMINISTRATOR")
    assert denied.status_code == 403
    assert client.post(
        "/api/v1/workspace/system-halt", headers=auth(identity("tech", "T3")), json={"reason": "no"}
    ).status_code == 403


def test_internal_halt_is_explicitly_external_network_free(monkeypatch):
    client = TestClient(app)
    token = select(client, identity("founder-halt"), "CHIEF_ADMINISTRATOR").json()["access_token"]
    result = client.post(
        "/api/v1/workspace/system-halt", headers=auth(token), json={"reason": "test"}
    ).json()
    assert result["status"] == "HALTED"
    assert result["workers_stopped"] is True
    assert result["external_cancellation_state"] == "NOT_AUTHORIZED_NOT_ATTEMPTED"


def test_four_domains_preserve_native_provenance_and_nulls():
    client = TestClient(app)
    token = select(client, identity("founder-scan"), "CHIEF_ADMINISTRATOR").json()["access_token"]
    result = client.get("/api/v1/workspace/scanner-summary", headers=auth(token)).json()
    assert [row["domain"] for row in result["data"]] == ["WEATHER", "CRYPTO", "MACRO", "SPORTS"]
    assert all(row["model_probability"] is None for row in result["data"])
    assert all(row["eligibility_state"] == "QUALIFICATION_PENDING" for row in result["data"])
    assert len({tuple(row["reason_codes"]) for row in result["data"]}) == 4


def test_dashboard_signal_trace_and_no_runtime_urls_or_mock_values():
    html = Path("app/api/v1/dashboard.html").read_text()
    parser = BindingParser()
    parser.feed(html)
    required = {
        "capital.data.total_equity_cents", "capital.data.dry_powder_policy_status",
        "capital.data.cfcp_balance_cents", "capital.data.faep_balance_cents",
        "governance.system_halt", "governance.pending_dual_control",
        "personal.data.principal_cents", "personal.data.unreserved_cash_cents",
    }
    assert required <= parser.bindings
    assert parser.external_urls == []
    assert "NOT AVAILABLE - QUALIFICATION PENDING" in html
    assert "$500,000" not in html and "Strategy-D" not in html


def test_acceptance_manifest_is_machine_readable():
    manifest = json.loads(Path("../docs/acceptance/rc-a-manifest.json").read_text())
    assert manifest["release_candidate"] == "RC-A"
    assert manifest["old_session_revoked_on_switch"] is True
    assert manifest["forbidden_activations"] == []
