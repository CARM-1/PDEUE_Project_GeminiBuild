from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_member_page_contains_onboarding_glass_engine_and_regimes():
    response = client.get("/member")
    assert response.status_code == 200
    assert 'id="welcomeCard"' in response.text
    assert "pdeue_welcome_dismissed" in response.text
    for concept in (
        "Familial Treasury",
        "System Stewardship",
        "Personal Compounding",
        "A BETTER FINANCIAL STARTING POINT",
    ):
        assert concept in response.text
    assert response.text.count('<article class="slot" data-slot-id="') == 12
    assert response.text.count('class="regime"') == 3
    assert 'id="clearTutorBtn"' in response.text


def test_member_telemetry_has_twelve_fail_closed_integer_cent_slots():
    response = client.get("/api/v1/portal/member/SCMA-ELEANOR_-B2B31C9E")
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["concurrency_slots"]) == 12
    assert [slot["slot_id"] for slot in payload["concurrency_slots"]] == list(range(1, 13))
    assert all(isinstance(payload[key], int) for key in ("cash_cents", "reserved_cents", "lifetime_profit_cents"))
    assert any(slot["status"] == "RESTING" for slot in payload["concurrency_slots"])
    assert any(slot["status"] == "AVAILABLE" for slot in payload["concurrency_slots"])


def test_member_ai_tutor_returns_stewardship_and_custodial_guidance():
    stewardship = client.post(
        "/api/v1/portal/member/ai-tutor",
        json={"query": "Explain the 87/10/3 waterfall simply"},
    )
    assert stewardship.status_code == 200
    stewardship_answer = stewardship.json()["response"]
    assert "Platform Infrastructure & Stewardship" in stewardship_answer
    assert "never from member pockets" in stewardship_answer
    assert "never deducted on losing trades" in stewardship_answer

    custodial = client.post(
        "/api/v1/portal/member/ai-tutor",
        json={"query": "How are accounts for children and minors kept custodial?"},
    )
    assert custodial.status_code == 200
    custodial_answer = custodial.json()["response"]
    assert "is_custodial: true" in custodial_answer
    assert "family trust" in custodial_answer
    assert "co-sign all withdrawals" in custodial_answer
