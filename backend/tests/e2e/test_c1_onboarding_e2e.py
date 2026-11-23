"""Milestone C1 — Playwright E2E 5-Stage Member Onboarding Pipeline Verification.

Walks the complete 5-stage flow across desktop (1440x900) and mobile (390x844):
  Stage 1: Chief Admin provisions a new member via [+ Onboard Member] modal on /dashboard Tab 2
  Stage 2: Member activates the single-use 48-hour invite link
  Stage 3: /member defaults open to Platform Orientation & Lineage Covenant
  Stage 5: /member renders the [Funding Instructions] card with EXT-REF-... & accounting.narratix.io
  Stage 4: Member completes Chapter 6 Comprehension Self-Check on /companion -> ACTIVE (STEWARDSHIP_L1_CERTIFIED)
  Post-Cert: Member returns to /member and verifies ACTIVE certified state + 1-click view switcher

Asserts zero console errors, zero uncaught page errors, zero failed HTTP requests,
zero external CDN tags/requests, zero cross-role nav bleed, and captures desktop/mobile screenshots.
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
from urllib.parse import urlparse
from urllib.request import Request, urlopen

import pytest

playwright_sync = pytest.importorskip(
    "playwright.sync_api",
    reason="Playwright is required for E2E onboarding tests",
)
sync_playwright = playwright_sync.sync_playwright

pytestmark = pytest.mark.e2e

REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_DIR = REPO_ROOT / "backend"
SCREENSHOTS_DIR = REPO_ROOT / "artifacts" / "playwright_screenshots" / "c1_onboarding"

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
    timeout: float = 5.0,
) -> tuple[int, str]:
    headers: dict[str, str] = {}
    body: bytes | None = None
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = Request(url, data=body, headers=headers, method=method)
    try:
        with urlopen(req, timeout=timeout) as resp:
            return int(resp.status), resp.read().decode("utf-8", errors="replace")
    except HTTPError as err:
        return int(err.code), err.read().decode("utf-8", errors="replace")


@pytest.fixture(scope="module")
def live_server() -> str:
    port = _find_free_port()
    base_url = f"http://127.0.0.1:{port}"
    with tempfile.TemporaryDirectory(prefix="pdeue_c1_e2e_") as tmp_dir:
        db_path = Path(tmp_dir) / "pdeue_c1_e2e.db"
        mutex_path = Path(tmp_dir) / "pdeue_c1_mutex.sqlite3"
        env = os.environ.copy()
        env["DATABASE_URL"] = f"sqlite:///{db_path}"
        env["PDEUE_MUTEX_DB_PATH"] = str(mutex_path)
        env["PDEUE_VENUE_MODE"] = "paper"
        env["PYTHONUNBUFFERED"] = "1"
        env["PYTHONPATH"] = str(BACKEND_DIR)

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
        )

        deadline = time.monotonic() + 15.0
        ready = False
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                stderr = proc.stderr.read().decode("utf-8", errors="replace") if proc.stderr else ""
                raise RuntimeError(f"FastAPI server exited early (code={proc.returncode}): {stderr}")
            try:
                status, _ = _http_request(f"{base_url}/health", timeout=1.0)
                if status == 200:
                    ready = True
                    break
            except Exception:
                time.sleep(0.15)

        if not ready:
            proc.terminate()
            proc.wait(timeout=5)
            raise TimeoutError(f"FastAPI server failed to respond on {base_url}/health within 15s")

        try:
            yield base_url
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as p:
        launched = p.chromium.launch(headless=True)
        try:
            yield launched
        finally:
            launched.close()


def _assert_zero_cdn_in_dom(page: Any) -> None:
    tags = page.evaluate(
        """() => {
            const hits = [];
            for (const el of document.querySelectorAll('script[src], link[href]')) {
                const raw = el.getAttribute('src') || el.getAttribute('href') || '';
                if (/^https?:\\/\\//i.test(raw)) hits.push(raw);
            }
            return hits;
        }"""
    )
    assert tags == [], f"External CDN tags detected in DOM: {tags}"


def _assert_member_role_siloed(page: Any) -> None:
    forbidden = ("/dashboard", "/advisor", "/admin/tech", "/lineage/house")
    visible_hrefs = page.evaluate(
        """() => {
            const out = [];
            for (const a of document.querySelectorAll('a[href]')) {
                const style = window.getComputedStyle(a);
                const rect = a.getBoundingClientRect();
                if (style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0) {
                    out.push(a.getAttribute('href') || '');
                }
            }
            return out;
        }"""
    )
    for href in visible_hrefs:
        path = urlparse(href).path
        for prefix in forbidden:
            assert not (path == prefix or path.startswith(f"{prefix}/")), (
                f"Cross-role nav bleed on /member: visible link {href!r} matches forbidden {prefix!r}"
            )


@pytest.mark.parametrize("vp_name", list(VIEWPORTS.keys()))
def test_c1_full_5_stage_member_onboarding_walkthrough(
    live_server: str,
    browser: Any,
    vp_name: str,
) -> None:
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    vp_size = VIEWPORTS[vp_name]
    base_host = urlparse(live_server).netloc

    console_errors: list[str] = []
    page_errors: list[str] = []
    failed_requests: list[dict[str, Any]] = []
    external_cdn_requests: list[str] = []

    context = browser.new_context(viewport=vp_size)

    def _intercept(route: Any) -> None:
        url = route.request.url
        parsed = urlparse(url)
        if parsed.scheme in {"data", "blob", "about"} or parsed.netloc == base_host:
            route.continue_()
            return
        external_cdn_requests.append(url)
        route.abort("blockedbyclient")

    context.route("**/*", _intercept)
    page = context.new_page()
    page.set_default_timeout(15000)

    page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
    page.on("pageerror", lambda err: page_errors.append(str(err)))
    page.on(
        "response",
        lambda resp: failed_requests.append({"status": resp.status, "url": resp.url})
        if resp.status >= 400
        else None,
    )

    tag = "DESKTOP" if "desktop" in vp_name else "MOBILE"
    member_name = f"Elena Vance {tag}"
    member_id = f"MEM-C1-{tag}"
    bank_ref = "EXT-REF-PENFED-****4821"

    try:
        # ── STAGE 1: Chief Admin provisioning via [+ Onboard Member] modal on /dashboard Tab 2 ──
        resp = page.goto(f"{live_server}/dashboard", wait_until="networkidle")
        assert resp is not None and resp.status == 200
        _assert_zero_cdn_in_dom(page)

        page.locator("#tab-btn-2").click()
        page.wait_for_selector("#openOnboardModalBtn", state="visible")
        page.locator("#openOnboardModalBtn").click()
        page.wait_for_selector("#onboard-modal", state="visible")

        page.fill("#onboard-full-name", member_name)
        page.fill("#onboard-member-id", member_id)
        page.select_option("#onboard-house", "HOUSE-03")
        page.select_option("#onboard-role-tier", "MEMBER_USER")
        page.fill("#onboard-seed-cents", "100000")
        page.fill("#onboard-risk-dial", "1.50")
        page.fill("#onboard-bank-ref", bank_ref)

        # Capture Stage 1 onboarding modal screenshot (viewport-framed so modal is crisp on desktop & mobile)
        page.screenshot(path=str(SCREENSHOTS_DIR / f"stage1_onboard_modal_{vp_name}.png"), full_page=False)

        page.locator("#submitOnboardBtn").click()
        page.wait_for_selector("#onboard-receipt", state="visible")

        invite_token = page.locator("#onboard-invite-token").inner_text().strip()
        activation_link = page.locator("#onboard-invite-link").get_attribute("href") or ""
        assert invite_token.startswith("pdeue_inv_")
        assert "invite_token=" in activation_link and "scma_id=" in activation_link

        page.screenshot(path=str(SCREENSHOTS_DIR / f"stage1_onboard_receipt_{vp_name}.png"), full_page=False)

        # ── STAGE 2 & STAGE 3 & STAGE 5: Activate single-use 48h link -> /member orientation + funding card ──
        resp_member = page.goto(f"{live_server}{activation_link}", wait_until="networkidle")
        assert resp_member is not None and resp_member.status == 200
        _assert_zero_cdn_in_dom(page)
        _assert_member_role_siloed(page)

        page.wait_for_selector("#activationBanner", state="visible")
        assert "Stage 2 Invite Activated" in page.locator("#activationBanner").inner_text()
        assert "PENDING_TUTOR_CERTIFICATION" in page.locator("#onboardingStatusCard").inner_text()

        # Primary View Switcher defaults open to Platform Orientation & Lineage Covenant
        assert page.locator("#viewOrientation").is_visible()
        assert not page.locator("#viewEngine").is_visible()
        orientation_text = page.locator("#viewOrientation").inner_text()
        for expected_phrase in (
            "You do not trade",
            "ADR-012",
            "Rule A14",
            "$100.00 Starting Seed",
            "$1,000.00 Starting Seed",
            "Explicit Non-Guarantee Disclosure",
            "is_custodial: true",
            "Pay-It-Forward",
            "FSAP",
        ):
            assert expected_phrase in orientation_text, f"Missing orientation copy: {expected_phrase!r}"

        # Stage 5: Funding Instructions card displays opaque EXT-REF token, ADR-011 reassurance, IFAS host
        assert page.locator("#fundingInstructionsCard").is_visible()
        assert page.locator("#fundingBankRefToken").inner_text().strip() == bank_ref
        funding_text = page.locator("#fundingInstructionsCard").inner_text()
        assert "ADR-011" in funding_text
        assert "accounting.narratix.io" in funding_text

        page.screenshot(path=str(SCREENSHOTS_DIR / f"stage3_member_orientation_{vp_name}.png"), full_page=True)

        # Verify single-use consumption fails closed via direct HTTP replay (HTTP 410)
        replay_status, _ = _http_request(
            f"{live_server}/api/v1/onboarding/activate",
            method="POST",
            payload={"token": invite_token},
        )
        assert replay_status == 410, f"Reused invite token should fail closed with 410, got {replay_status}"

        # ── STAGE 4: PDEUE University Chapter 6 Certification Gate (/companion) ──
        page.locator("#startCertificationLink").click()
        page.wait_for_load_state("networkidle")
        _assert_zero_cdn_in_dom(page)

        page.wait_for_selector("#chapter-governance", state="visible")
        cert_scma_val = page.locator("#certScmaId").input_value()
        assert cert_scma_val.startswith("SCMA-")
        assert page.locator("#completeCertificationBtn").is_disabled()

        # Answer all 3 Chapter 6 Comprehension Self-Check questions accurately
        page.locator('#quiz button[data-answer="CFCP (ADR-008)"]').click()
        page.locator('#quiz button[data-answer="No (Downward-Only)"]').click()
        page.locator('#quiz button[data-answer="No (Dual Control)"]').click()

        assert not page.locator("#completeCertificationBtn").is_disabled()
        page.locator("#completeCertificationBtn").click()
        page.wait_for_selector("#certificationResult:not(.hidden)", state="visible")
        cert_result_text = page.locator("#certificationResult").inner_text()
        assert "STEWARDSHIP_L1_CERTIFIED" in cert_result_text
        assert "ACTIVE" in cert_result_text

        page.screenshot(path=str(SCREENSHOTS_DIR / f"stage4_companion_certified_{vp_name}.png"), full_page=True)

        # ── POST-CERTIFICATION: Return to /member and verify ACTIVE state & 1-click view switcher ──
        page.locator("#returnToMemberLink").click()
        page.wait_for_load_state("networkidle")
        _assert_zero_cdn_in_dom(page)
        _assert_member_role_siloed(page)

        page.wait_for_selector("#certifiedBanner", state="visible")
        assert "STEWARDSHIP_L1_CERTIFIED" in page.locator("#memberStatusBadge").inner_text()
        assert "Certified UTC:" in page.locator("#certifiedTimestamp").inner_text()
        assert not page.locator("#onboardingStatusCard").is_visible()
        assert page.locator("#fundingBankRefToken").inner_text().strip() == bank_ref

        # Switch to Live Trading Engine and back to Platform Orientation (1-click accessible anytime)
        page.locator("#tabBtnEngine").click()
        assert page.locator("#viewEngine").is_visible()
        page.screenshot(path=str(SCREENSHOTS_DIR / f"stage5_member_active_engine_{vp_name}.png"), full_page=True)

        page.locator("#tabBtnOrientation").click()
        assert page.locator("#viewOrientation").is_visible()
    finally:
        context.close()

    assert console_errors == [], f"console.error on {vp_name}: {console_errors}"
    assert page_errors == [], f"Uncaught pageerror on {vp_name}: {page_errors}"
    assert failed_requests == [], f"Failed HTTP requests on {vp_name}: {failed_requests}"
    assert external_cdn_requests == [], f"External CDN requests on {vp_name}: {external_cdn_requests}"
