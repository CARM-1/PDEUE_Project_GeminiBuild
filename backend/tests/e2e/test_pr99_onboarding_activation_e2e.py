"""PR #99 Playwright E2E Suite — Invite Activation Portal (/activate) at 1440x900 & 390x844,
Expired/Already-Used Token Calm Error Card (HTTP 410), Allowlist Provisioning, and
House Delegated Intake / F2-H Co-Sign / Dashboard Tab 4 UI Verification.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

playwright_sync = pytest.importorskip(
    "playwright.sync_api",
    reason="Playwright is required for PR #99 E2E tests",
)
sync_playwright = playwright_sync.sync_playwright

pytestmark = pytest.mark.e2e

REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_DIR = REPO_ROOT / "backend"
SCREENSHOTS_DIR = REPO_ROOT / "artifacts" / "playwright_screenshots"

VIEWPORTS: dict[str, dict[str, int]] = {
    "desktop_1440x900": {"width": 1440, "height": 900},
    "mobile_390x844": {"width": 390, "height": 844},
}


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _http_request(
    url: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 5.0,
) -> tuple[int, str]:
    req_headers = dict(headers or {})
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        req_headers.setdefault("Content-Type", "application/json")
    req = Request(url, data=data, headers=req_headers, method=method)
    try:
        with urlopen(req, timeout=timeout) as resp:
            return int(resp.status), resp.read().decode("utf-8", errors="replace")
    except HTTPError as err:
        return int(err.code), err.read().decode("utf-8", errors="replace")


@pytest.fixture(scope="module")
def live_server() -> str:
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    port = _find_free_port()
    base_url = f"http://127.0.0.1:{port}"
    tmp_dir = tempfile.TemporaryDirectory(prefix="pdeue_pr99_e2e_")
    db_path = Path(tmp_dir.name) / "pdeue_pr99_e2e.db"

    env = os.environ.copy()
    env.update(
        {
            "DATABASE_URL": f"sqlite:///{db_path.as_posix()}",
            "PDEUE_VENUE_MODE": "paper",
            "PDEUE_LIVE_TRADING_ENABLED": "false",
            "PDEUE_GOVERNANCE_MODE": "EXECUTIVE_COMMAND",
            "PDEUE_GATE_G1_STATUS": "HOLD_OBSERVATIONS_ONLY",
            "PDEUE_LLM_PROVIDER": "mock",
            "PDEUE_ENFORCE_SESSION_AUTH": "false",
            "PYTHONUNBUFFERED": "1",
        }
    )

    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        cwd=str(BACKEND_DIR),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    deadline = time.time() + 30.0
    healthy = False
    while time.time() < deadline:
        if proc.poll() is not None:
            out, err = proc.communicate(timeout=3)
            tmp_dir.cleanup()
            raise RuntimeError(f"Server exited early ({proc.returncode}).\nSTDOUT:\n{out}\nSTDERR:\n{err}")
        try:
            st, _ = _http_request(f"{base_url}/health", timeout=1.5)
            if st == 200:
                healthy = True
                break
        except Exception:
            time.sleep(0.25)

    if not healthy:
        proc.terminate()
        proc.wait(timeout=5)
        tmp_dir.cleanup()
        raise RuntimeError(f"Server did not become healthy at {base_url}/health")

    try:
        yield base_url
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
        tmp_dir.cleanup()


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        try:
            yield b
        finally:
            b.close()


def _assert_zero_cdn_and_no_overflow(page: Any, vp_name: str) -> None:
    ext = page.evaluate(
        """() => [...document.querySelectorAll('script[src], link[href]')]
            .map(el => el.getAttribute('src') || el.getAttribute('href') || '')
            .filter(u => /^https?:\\/\\//i.test(u))"""
    )
    assert ext == [], f"External CDN tags detected on {vp_name}: {ext}"

    overflow = page.evaluate(
        """() => document.documentElement.scrollWidth - document.documentElement.clientWidth"""
    )
    assert overflow <= 2, f"Horizontal overflow detected on {vp_name}: {overflow}px"


@pytest.mark.parametrize("vp_name", ["desktop_1440x900", "mobile_390x844"])
def test_pr99_invite_activation_portal_valid_and_expired_flow(
    live_server: str,
    browser: Any,
    vp_name: str,
) -> None:
    vp = VIEWPORTS[vp_name]
    tag = "DESKTOP" if "desktop" in vp_name else "MOBILE"

    # Provision a real family member to obtain a valid 48h single-use invite token
    st, raw = _http_request(
        f"{live_server}/api/v1/onboarding/provision",
        method="POST",
        payload={
            "full_name": f"Evelyn McCormick {tag}",
            "member_id": f"MEM-PR99-{tag}",
            "email": f"evelyn.{tag.lower()}@carmichael-family.local",
            "lineage_house": "HOUSE-03",
            "role_tier": "MEMBER_USER",
            "seed_cents": 100_000,
            "risk_dial_pct": 1.25,
            "bank_ref_token": "EXT-REF-PENFED-****4821",
        },
    )
    assert st == 201, raw
    prov = json.loads(raw)
    invite_token = prov["invite"]["token"]
    scma_id = prov["member"]["scma_id"]

    console_errors: list[str] = []
    page_errors: list[str] = []
    failed_requests: list[dict[str, Any]] = []
    external_cdn_requests: list[str] = []

    context = browser.new_context(viewport=vp)

    def _intercept(route: Any) -> None:
        url = route.request.url
        if url.startswith(live_server) or url.startswith("data:") or url.startswith("blob:"):
            route.continue_()
        else:
            external_cdn_requests.append(url)
            route.abort()

    context.route("**/*", _intercept)
    page = context.new_page()
    page.set_default_timeout(15000)
    page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: page_errors.append(str(e)))
    page.on(
        "response",
        lambda r: failed_requests.append({"status": r.status, "url": r.url})
        if r.status >= 400 and "/api/v1/onboarding/invite-preview" not in r.url
        else None,
    )

    try:
        # 1. Valid invite activation flow at /activate?token=...
        resp = page.goto(f"{live_server}/activate?token={invite_token}", wait_until="networkidle")
        assert resp is not None and resp.status == 200
        _assert_zero_cdn_and_no_overflow(page, vp_name)

        # Wait for Step 1–3 wizard to populate from read-only preview
        page.wait_for_selector("#activationStepsFlow:not([hidden])", state="visible")
        assert f"Evelyn McCormick {tag}" in page.locator("#previewFullName").inner_text()
        assert "HOUSE-03" in page.locator("#previewHouseCode").inner_text()
        assert page.locator("#activateEmailInput").input_value() == f"evelyn.{tag.lower()}@carmichael-family.local"

        # Verify >= 48px senior tap targets on primary button & email input
        btn_box = page.locator("#activateAccountBtn").bounding_box()
        assert btn_box is not None and btn_box["height"] >= 48
        email_box = page.locator("#activateEmailInput").bounding_box()
        assert email_box is not None and email_box["height"] >= 48

        # Step 2: Covenant acknowledgment gates Step 3 button
        assert page.locator("#activateAccountBtn").is_disabled()
        page.screenshot(path=str(SCREENSHOTS_DIR / f"pr99_activate_steps_{vp_name}.png"), full_page=True)
        page.locator("#covenantAckCheckbox").check()
        assert not page.locator("#activateAccountBtn").is_disabled()

        # Step 3: Activate Private Account -> allowlist provisioned + next-step buttons visible
        page.locator("#activateAccountBtn").click()
        page.wait_for_selector("#activationSuccessCard:not([hidden])", state="visible")
        _assert_zero_cdn_and_no_overflow(page, vp_name)

        success_text = page.locator("#activationSuccessCard").inner_text()
        assert f"evelyn.{tag.lower()}@carmichael-family.local" in success_text
        assert scma_id in success_text
        assert page.locator("#nextStepUniversityBtn").is_visible()
        assert page.locator("#nextStepAccountBtn").is_visible()
        assert "/companion" in (page.locator("#nextStepUniversityBtn").get_attribute("href") or "")
        assert "/member" in (page.locator("#nextStepAccountBtn").get_attribute("href") or "")
        page.screenshot(path=str(SCREENSHOTS_DIR / f"pr99_activate_success_{vp_name}.png"), full_page=True)

        # Verify Open My Account loads member portal cleanly under the newly issued session cookie
        page.locator("#nextStepAccountBtn").click()
        page.wait_for_load_state("networkidle")
        assert "/member" in page.url

        # Zero console errors, zero page errors, zero failed HTTP requests across the full valid activation flow
        assert console_errors == [], f"console.error during valid flow on {vp_name}: {console_errors}"
        assert page_errors == [], f"Uncaught pageerror during valid flow on {vp_name}: {page_errors}"
        assert failed_requests == [], f"Failed HTTP requests during valid flow on {vp_name}: {failed_requests}"

        # 2. Re-opening the consumed single-use invite token intentionally triggers HTTP 410 and renders the calm error card
        resp_used = page.goto(f"{live_server}/activate?token={invite_token}", wait_until="networkidle")
        assert resp_used is not None and resp_used.status == 200
        page.wait_for_selector("#inviteErrorCard:not([hidden])", state="visible")
        _assert_zero_cdn_and_no_overflow(page, vp_name)
        err_text = page.locator("#inviteErrorCard").inner_text()
        assert "Already Activated" in err_text or "Expired" in err_text
        assert page.locator("#errorSignInLink").is_visible()
        page.screenshot(path=str(SCREENSHOTS_DIR / f"pr99_activate_expired_card_{vp_name}.png"), full_page=True)
    finally:
        context.close()

    unexpected_console = [msg for msg in console_errors if "410 (Gone)" not in msg]
    assert unexpected_console == [], f"Unexpected console.error on {vp_name}: {unexpected_console}"
    assert page_errors == [], f"Uncaught pageerror on {vp_name}: {page_errors}"
    assert failed_requests == [], f"Unexpected failed HTTP requests on {vp_name}: {failed_requests}"
    assert external_cdn_requests == [], f"External CDN requests on {vp_name}: {external_cdn_requests}"


def test_pr99_dashboard_tab4_house_intake_and_advisor_cosign_ui_desktop(
    live_server: str,
    browser: Any,
) -> None:
    context = browser.new_context(viewport=VIEWPORTS["desktop_1440x900"])
    page = context.new_page()
    page.set_default_timeout(15000)
    console_errors: list[str] = []
    page_errors: list[str] = []
    page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: page_errors.append(str(e)))

    try:
        # 1. /dashboard Tab 4 shows Admission Authority Mode selector defaulting to CHIEF_ADMIN_SOLO
        page.goto(f"{live_server}/dashboard", wait_until="networkidle")
        page.locator("#tab-btn-4").click()
        page.wait_for_selector("#admission-authority-mode-select", state="visible")
        assert page.locator("#admission-authority-mode-select").input_value() == "CHIEF_ADMIN_SOLO"
        assert "CHIEF_ADMIN_SOLO" in page.locator("#admission-authority-badge").inner_text()
        page.screenshot(path=str(SCREENSHOTS_DIR / "pr99_dashboard_tab4_admission_mode.png"), full_page=False)

        # 2. /lineage/house/1?role=H2 renders collapsible House Delegated Onboarding Intake panel with ADMIN_ONLY calm notice
        page.goto(f"{live_server}/lineage/house/1?role=H2", wait_until="networkidle")
        page.wait_for_selector("#houseDelegatedOnboardingDrawer", state="visible")
        page.locator("#houseDelegatedOnboardingDrawer summary").click()
        page.wait_for_selector("#houseDelegationModeNotice", state="visible")
        assert "ADMIN_ONLY" in page.locator("#houseDelegationModeNotice").inner_text()
        page.screenshot(path=str(SCREENSHOTS_DIR / "pr99_lineage_house_delegated_intake.png"), full_page=False)

        # H1 strictly stripped
        page.goto(f"{live_server}/lineage/house/1?role=H1", wait_until="networkidle")
        assert page.locator("#houseDelegatedOnboardingPanel").count() == 0

        # 3. /advisor?role=F2-H shows Pending Member Admission Co-Signs; F1 strips it
        page.goto(f"{live_server}/advisor?role=F2-H", wait_until="networkidle")
        page.wait_for_selector("#f2hAdmissionCosignSection", state="visible")
        assert "Pending Member Admission Co-Signs" in page.locator("#f2hAdmissionCosignSection").inner_text()
        page.screenshot(path=str(SCREENSHOTS_DIR / "pr99_advisor_f2h_admission_cosign.png"), full_page=False)

        page.goto(f"{live_server}/advisor?role=F1", wait_until="networkidle")
        assert page.locator("#f2hAdmissionCosignSection").count() == 0
    finally:
        context.close()

    assert console_errors == [], f"console.error: {console_errors}"
    assert page_errors == [], f"pageerror: {page_errors}"
