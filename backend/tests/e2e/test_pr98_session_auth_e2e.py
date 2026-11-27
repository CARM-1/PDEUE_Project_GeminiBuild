"""PR #98 Playwright E2E Verification Suite:
Private Family Sign-In Portal (/login) at 1440x900 & 390x844, full 6-digit email code sign-in
flow, server-side ?scma_id= tampering rejection (HTTP 403), Sign Out, Apex Passphrase + MFA
sign-in to /dashboard Tab 4 Active Sessions & Lost-Device Revocation card, and zero
console/HTTP/CDN errors or horizontal overflow."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
from typing import Any, Dict, List
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

import pytest

playwright_sync = pytest.importorskip(
    "playwright.sync_api",
    reason="Playwright is required for PR #98 E2E tests",
)
sync_playwright = playwright_sync.sync_playwright

pytestmark = pytest.mark.e2e

REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_DIR = REPO_ROOT / "backend"
SCREENSHOTS_DIR = REPO_ROOT / "artifacts" / "playwright_screenshots"

VIEWPORTS: Dict[str, Dict[str, int]] = {
    "desktop_1440x900": {"width": 1440, "height": 900},
    "mobile_390x844": {"width": 390, "height": 844},
}


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _http_get(url: str, timeout: float = 2.0) -> int:
    try:
        with urlopen(Request(url, method="GET"), timeout=timeout) as resp:
            return int(resp.status)
    except HTTPError as err:
        return int(err.code)


@pytest.fixture(scope="module")
def live_server() -> Dict[str, str]:
    port = _find_free_port()
    base_url = f"http://127.0.0.1:{port}"
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="pdeue_pr98_e2e_") as tmp_dir:
        db_path = Path(tmp_dir) / "pdeue_pr98.db"
        mutex_path = Path(tmp_dir) / "pdeue_pr98_mutex.sqlite3"
        env = os.environ.copy()
        env["DATABASE_URL"] = f"sqlite:///{db_path}"
        env["PDEUE_MUTEX_DB_PATH"] = str(mutex_path)
        env["PDEUE_VENUE_MODE"] = "paper"
        env["PDEUE_GATE_G1_STATUS"] = "HOLD_OBSERVATIONS_ONLY"
        env["AI_PROVIDER"] = "mock"
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
                err_out = proc.stderr.read().decode("utf-8", errors="ignore") if proc.stderr else ""
                raise RuntimeError(f"uvicorn exited prematurely ({proc.returncode}): {err_out}")
            try:
                if _http_get(f"{base_url}/health", timeout=1.0) == 200:
                    ready = True
                    break
            except Exception:
                pass
            time.sleep(0.2)

        if not ready:
            proc.terminate()
            raise RuntimeError("Live FastAPI server did not become ready in time")

        try:
            yield {"base_url": base_url, "db_path": str(db_path)}
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()


@pytest.fixture(scope="module")
def browser() -> Any:
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        try:
            yield b
        finally:
            b.close()


def _attach_watchers(page: Any, base_url: str) -> Dict[str, List[str]]:
    base_host = urlparse(base_url).netloc
    errors: Dict[str, List[str]] = {
        "console": [],
        "pageerror": [],
        "http": [],
        "external": [],
    }

    page.on(
        "console",
        lambda msg: errors["console"].append(f"{msg.type}: {msg.text}")
        if msg.type == "error"
        else None,
    )
    page.on("pageerror", lambda exc: errors["pageerror"].append(str(exc)))
    page.on(
        "response",
        lambda resp: errors["http"].append(f"{resp.status} {resp.url}")
        if resp.status >= 400
        else None,
    )

    def _on_request(req: Any) -> None:
        parsed = urlparse(req.url)
        if parsed.scheme in {"http", "https"} and parsed.netloc != base_host:
            errors["external"].append(req.url)

    page.on("request", _on_request)
    return errors


@pytest.mark.parametrize("vp_name", ["desktop_1440x900", "mobile_390x844"])
def test_login_portal_visual_a11y_zero_cdn_and_no_overflow(
    live_server: Dict[str, str],
    browser: Any,
    vp_name: str,
) -> None:
    base_url = live_server["base_url"]
    vp = VIEWPORTS[vp_name]
    ctx = browser.new_context(viewport=vp)
    page = ctx.new_page()
    errors = _attach_watchers(page, base_url)
    try:
        resp = page.goto(f"{base_url}/login", wait_until="networkidle")
        assert resp is not None and resp.status == 200

        # Zero horizontal overflow at desktop and mobile viewports
        overflow = page.evaluate("() => document.documentElement.scrollWidth - window.innerWidth")
        assert overflow <= 1, f"Horizontal overflow on /login ({vp_name}): {overflow}px"

        # Twin founding crests rendered cleanly
        crests = page.locator("img.brand-crest")
        assert crests.count() == 2
        for i in range(2):
            nw = crests.nth(i).evaluate("el => el.naturalWidth")
            assert nw > 0, f"Crest image {i} failed to load"

        # >= 48px tap targets on primary auth controls
        for sel in ("#loginEmailInput", "#sendCodeBtn", "#loginCodeInput", "#verifyCodeBtn"):
            box = page.locator(sel).bounding_box()
            assert box is not None and box["height"] >= 48, f"{sel} height < 48px: {box}"

        # Senior A | A+ | A++ scaling toggle works cleanly
        page.locator('#textScaleGroup button[data-scale="large"]').click()
        assert page.evaluate("() => document.documentElement.getAttribute('data-text-scale')") == "large"
        page.locator('#textScaleGroup button[data-scale="standard"]').click()

        # Collapsible How-To helper & Apex drawer expand cleanly
        page.locator("#signinHowToDrawer summary").click()
        assert page.locator("#signinHowToDrawer").evaluate("el => el.open") is True
        assert "Zero Passwords to Memorize or Leak" in page.locator("#signinHowToDrawer").inner_text()

        page.locator("#apexLoginDrawer summary").click()
        assert page.locator("#apexLoginDrawer").evaluate("el => el.open") is True

        page.screenshot(path=str(SCREENSHOTS_DIR / f"pr98_login_{vp_name}.png"), full_page=True)

        assert errors["console"] == [], f"Console errors: {errors['console']}"
        assert errors["pageerror"] == [], f"Page errors: {errors['pageerror']}"
        assert errors["http"] == [], f"HTTP errors: {errors['http']}"
        assert errors["external"] == [], f"External CDN/network calls: {errors['external']}"
    finally:
        ctx.close()


def test_full_six_digit_signin_tenant_jail_and_sign_out_e2e(
    live_server: Dict[str, str],
    browser: Any,
) -> None:
    base_url = live_server["base_url"]
    db_path = live_server["db_path"]

    ctx = browser.new_context(viewport=VIEWPORTS["desktop_1440x900"])
    page = ctx.new_page()
    errors = _attach_watchers(page, base_url)
    try:
        page.goto(f"{base_url}/login", wait_until="networkidle")

        # Step 1: Request 6-digit code via UI
        page.fill("#loginEmailInput", "julian@carmichael-family.local")
        page.click("#sendCodeBtn")
        page.locator("#codeRequestStatus.visible.ok").wait_for(timeout=5000)
        assert "family roster" in page.locator("#codeRequestStatus").inner_text().lower()

        # Set a known test 6-digit code hash on the created challenge row inside our temp E2E DB
        known_code = "654321"
        known_hash = hashlib.sha256(known_code.encode("utf-8")).hexdigest()
        conn = sqlite3.connect(db_path)
        try:
            cur = conn.execute(
                "UPDATE auth_login_challenges SET code_hash = ? WHERE user_id = ? AND consumed_at IS NULL",
                (known_hash, "USR-julian_va-A1F98B21"),
            )
            assert cur.rowcount == 1, "Expected 1 active unconsumed login challenge for Julian"
            conn.commit()
        finally:
            conn.close()

        # Step 2: Enter 6-digit code and sign in -> redirects to /member
        page.fill("#loginCodeInput", known_code)
        with page.expect_navigation(url=f"{base_url}/member", timeout=8000):
            page.click("#verifyCodeBtn")
        page.wait_for_load_state("networkidle")

        # Verify Julian's jailed SCMA loaded on /member
        page.locator("#identity").wait_for(timeout=5000)
        page.wait_for_function(
            "() => (document.getElementById('identity')?.textContent || '').includes('SCMA-JULIAN_-A1F98B21')",
            timeout=5000,
        )
        assert "SCMA-JULIAN_-A1F98B21" in page.locator("#identity").inner_text()

        # Verify zero console/HTTP/CDN errors during normal authenticated flow
        assert errors["console"] == [], f"Console errors: {errors['console']}"
        assert errors["pageerror"] == [], f"Page errors: {errors['pageerror']}"
        assert errors["http"] == [], f"HTTP errors: {errors['http']}"
        assert errors["external"] == [], f"External calls: {errors['external']}"

        # Verify server-side ?scma_id= tampering is rejected HTTP 403 via authenticated browser context
        tamper_html = ctx.request.get(f"{base_url}/member?scma_id=SCMA-ELEANOR_-B2B31C9E")
        assert tamper_html.status == 403
        tamper_api = ctx.request.get(
            f"{base_url}/api/v1/portal/member/state?scma_id=SCMA-ELEANOR_-B2B31C9E"
        )
        assert tamper_api.status == 403
        assert "TENANT_JAIL_VIOLATION" in tamper_api.json().get("error_code", "")

        # Verify unauthorized /dashboard access is blocked HTTP 403 under MEMBER_USER hat
        dash_denied = ctx.request.get(f"{base_url}/dashboard")
        assert dash_denied.status == 403

        # Click Sign Out on /member -> redirects to /login?reason=signed_out and invalidates cookie
        with page.expect_navigation(url=f"{base_url}/login?reason=signed_out", timeout=8000):
            page.click("#memberSignOutBtn")
        page.wait_for_load_state("networkidle")
        assert "safely signed out" in page.locator("#sessionReasonBanner").inner_text().lower()

        me_after_logout = ctx.request.get(f"{base_url}/api/v1/auth/me")
        assert me_after_logout.status == 401
    finally:
        ctx.close()


def test_apex_signin_dashboard_tab4_active_sessions_and_signout_e2e(
    live_server: Dict[str, str],
    browser: Any,
) -> None:
    base_url = live_server["base_url"]
    ctx = browser.new_context(viewport=VIEWPORTS["desktop_1440x900"])
    page = ctx.new_page()
    errors = _attach_watchers(page, base_url)
    try:
        page.goto(f"{base_url}/login", wait_until="networkidle")
        page.locator("#apexLoginDrawer summary").click()
        page.fill("#apexEmailInput", "founder@carmichael-family.local")
        page.fill("#apexPassphraseInput", "Carmichael-Sovereign-Stewardship-2026!")
        page.fill("#apexMfaInput", "482916")

        with page.expect_navigation(url=f"{base_url}/dashboard", timeout=8000):
            page.click("#apexLoginBtn")
        page.wait_for_load_state("networkidle")

        # Open Tab 4 and verify Active Sessions & Lost-Device Revocation card renders active session
        page.click("#tab-btn-4")
        page.locator("#active-sessions-card").wait_for(state="visible", timeout=5000)
        page.wait_for_function(
            "() => (document.getElementById('active-sessions-tbody')?.textContent || '').includes('Founder Chief Admin')",
            timeout=5000,
        )
        page.screenshot(
            path=str(SCREENSHOTS_DIR / "pr98_dashboard_tab4_sessions_1440x900.png"),
            full_page=True,
        )

        assert errors["console"] == [], f"Console errors: {errors['console']}"
        assert errors["pageerror"] == [], f"Page errors: {errors['pageerror']}"
        assert errors["http"] == [], f"HTTP errors: {errors['http']}"
        assert errors["external"] == [], f"External calls: {errors['external']}"

        # Sign Out from /dashboard header
        with page.expect_navigation(url=f"{base_url}/login?reason=signed_out", timeout=8000):
            page.click("#dashboardSignOutBtn")
        assert ctx.request.get(f"{base_url}/api/v1/auth/me").status == 401
    finally:
        ctx.close()
