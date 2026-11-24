"""Milestone PR #81 — Playwright E2E Verification:
- Root `/` HTTP 302 redirect lands directly on `/community`
- Scoped Custodial Lookup bars across `/dashboard`, `/advisor`, `/lineage/house/1`, and `/admin/tech`
  (confirming Directive R-12 `$****.**` and `SCMA-MEM-****` masking on `/admin/tech` and `/lineage/house/1?role=H1`)
- Role provisioning, Anti-Tribalism Custody toggle (`CROSS_HOUSE_ANTI_TRIBAL`), and Delegated Onboarding
  scope & Genealogical Board toggles on `/dashboard` Tab 4
- Zero console errors, zero uncaught page errors, zero external CDN requests, zero HTTP >= 400,
  and zero horizontal overflow at desktop (`1440x900`) and mobile (`390x844`).
"""
from __future__ import annotations

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
    reason="Playwright is required for PR #81 E2E tests",
)
sync_playwright = playwright_sync.sync_playwright

pytestmark = pytest.mark.e2e

REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_DIR = REPO_ROOT / "backend"
SCREENSHOTS_DIR = REPO_ROOT / "artifacts" / "playwright_screenshots" / "pr81_custody_onboarding"

VIEWPORTS: dict[str, dict[str, int]] = {
    "desktop_1440x900": {"width": 1440, "height": 900},
    "mobile_390x844": {"width": 390, "height": 844},
}


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _http_get(url: str, timeout: float = 5.0) -> tuple[int, str]:
    req = Request(url, method="GET")
    try:
        with urlopen(req, timeout=timeout) as resp:
            return int(resp.status), resp.read().decode("utf-8", errors="replace")
    except HTTPError as err:
        return int(err.code), err.read().decode("utf-8", errors="replace")


@pytest.fixture(scope="module")
def live_server() -> str:
    port = _find_free_port()
    base_url = f"http://127.0.0.1:{port}"
    with tempfile.TemporaryDirectory(prefix="pdeue_pr81_e2e_") as tmp_dir:
        db_path = Path(tmp_dir) / "pdeue_pr81_e2e.db"
        mutex_path = Path(tmp_dir) / "pdeue_pr81_mutex.sqlite3"
        env = os.environ.copy()
        env["DATABASE_URL"] = f"sqlite:///{db_path}"
        env["PDEUE_MUTEX_DB_PATH"] = str(mutex_path)
        env["PDEUE_VENUE_MODE"] = "paper"
        env["PDEUE_GATE_G1_STATUS"] = "HOLD_OBSERVATIONS_ONLY"
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
                status, _ = _http_get(f"{base_url}/health", timeout=1.0)
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
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        launched = p.chromium.launch(headless=True)
        try:
            yield launched
        finally:
            launched.close()


def _create_monitored_page(browser: Any, base_url: str, viewport: dict[str, int]):
    base_host = urlparse(base_url).netloc
    context = browser.new_context(viewport=viewport)
    diagnostics: dict[str, list[Any]] = {
        "console_errors": [],
        "page_errors": [],
        "failed_requests": [],
        "external_cdn_requests": [],
    }

    def _intercept(route: Any) -> None:
        url = route.request.url
        parsed = urlparse(url)
        if parsed.scheme in {"data", "blob", "about"} or parsed.netloc == base_host:
            route.continue_()
        elif parsed.netloc == "meet.jit.si":
            route.fulfill(
                status=200,
                content_type="text/html",
                body="<!doctype html><html><body>Sandboxed Jitsi Classroom Offline Stub</body></html>",
            )
        else:
            diagnostics["external_cdn_requests"].append(url)
            route.abort()

    context.route("**/*", _intercept)
    page = context.new_page()
    page.on("console", lambda msg: diagnostics["console_errors"].append(msg.text) if msg.type == "error" else None)
    page.on("pageerror", lambda err: diagnostics["page_errors"].append(str(err)))
    page.on(
        "response",
        lambda resp: diagnostics["failed_requests"].append((resp.status, resp.url))
        if resp.status >= 400
        else None,
    )
    return context, page, diagnostics


def _assert_clean_page(page: Any, diagnostics: dict[str, list[Any]], label: str) -> None:
    assert diagnostics["console_errors"] == [], f"{label} console errors: {diagnostics['console_errors']}"
    assert diagnostics["page_errors"] == [], f"{label} page errors: {diagnostics['page_errors']}"
    assert diagnostics["failed_requests"] == [], f"{label} HTTP >= 400: {diagnostics['failed_requests']}"
    assert diagnostics["external_cdn_requests"] == [], f"{label} external CDN requests: {diagnostics['external_cdn_requests']}"
    overflow = page.evaluate("() => document.documentElement.scrollWidth - window.innerWidth")
    assert overflow <= 2, f"{label} horizontal overflow detected ({overflow}px)"


@pytest.mark.parametrize("vp_name", ("desktop_1440x900", "mobile_390x844"))
def test_root_redirect_and_scoped_lookup_bars_across_all_custodial_portals(
    live_server: str, browser: Any, vp_name: str
):
    viewport = VIEWPORTS[vp_name]

    # 1. Root URL `/` redirects cleanly to `/home` (PR #82 Central Family Home Hub)
    ctx, page, diag = _create_monitored_page(browser, live_server, viewport)
    try:
        page.goto(f"{live_server}/", wait_until="networkidle")
        assert urlparse(page.url).path == "/home"
        _assert_clean_page(page, diag, f"root_redirect_{vp_name}")
    finally:
        ctx.close()

    # 2. `/dashboard` Enclave-Wide Scoped Custodial Lookup + Tab 4 Role/Custody/Delegation Controls
    ctx, page, diag = _create_monitored_page(browser, live_server, viewport)
    try:
        page.goto(f"{live_server}/dashboard", wait_until="networkidle")
        page.locator("#custodial-lookup-input").fill("Eleanor")
        page.locator("#custodial-lookup-btn").click()
        drawer = page.locator("#custodial-lookup-drawer")
        drawer.locator(".custodial-lookup-item").first.wait_for(state="visible", timeout=5000)
        assert "Eleanor Vance" in drawer.inner_text()
        assert "SCMA-ELEANOR_-B2B31C9E" in drawer.inner_text()

        # Switch to Tab 4 and verify role provisioning, anti-tribalism toggle, and delegation controls
        page.locator("#tab-btn-4").click()
        page.locator("#role-custody-governance-card").wait_for(state="visible", timeout=5000)
        assert "INTRA_HOUSE" in page.locator("#custody-mode-badge").inner_text()

        # Toggle Anti-Tribalism Custody -> CROSS_HOUSE_ANTI_TRIBAL and back to INTRA_HOUSE
        page.locator("#btn-custody-cross").click()
        page.wait_for_function(
            "() => document.getElementById('custody-mode-badge').textContent.includes('CROSS_HOUSE_ANTI_TRIBAL')",
            timeout=5000,
        )
        # Toggle Delegated Onboarding scope -> PER_HOUSE + Board ON
        page.locator("#delegation-scope-select").select_option("PER_HOUSE")
        page.locator("#house-delegation-enabled-check").check()
        page.locator("#genealogical-board-toggle").check()
        page.locator("#btn-save-delegation-config").click()
        page.wait_for_function(
            "() => document.getElementById('delegation-scope-badge').textContent.includes('PER_HOUSE')",
            timeout=5000,
        )

        # Reset back to default fail-closed states
        page.locator("#btn-custody-intra").click()
        page.wait_for_function(
            "() => document.getElementById('custody-mode-badge').textContent.includes('INTRA_HOUSE')",
            timeout=5000,
        )
        page.locator("#delegation-scope-select").select_option("ADMIN_ONLY")
        page.locator("#genealogical-board-toggle").uncheck()
        page.locator("#btn-save-delegation-config").click()
        page.wait_for_function(
            "() => document.getElementById('delegation-scope-badge').textContent.includes('ADMIN_ONLY')",
            timeout=5000,
        )

        page.screenshot(path=str(SCREENSHOTS_DIR / f"dashboard_tab4_{vp_name}.png"), full_page=True)
        _assert_clean_page(page, diag, f"dashboard_{vp_name}")
    finally:
        ctx.close()

    # 3. `/advisor?role=F2-H` Scoped Custodial Lookup (zero cross-tier links)
    ctx, page, diag = _create_monitored_page(browser, live_server, viewport)
    try:
        page.goto(f"{live_server}/advisor?role=F2-H", wait_until="networkidle")
        page.locator("#custodial-lookup-input").fill("Julian")
        page.locator("#custodial-lookup-btn").click()
        drawer = page.locator("#custodial-lookup-drawer")
        drawer.locator(".custodial-lookup-item").first.wait_for(state="visible", timeout=5000)
        assert "Julian Vance" in drawer.inner_text()
        assert page.locator("#role-switcher").count() == 0
        page.screenshot(path=str(SCREENSHOTS_DIR / f"advisor_lookup_{vp_name}.png"), full_page=True)
        _assert_clean_page(page, diag, f"advisor_{vp_name}")
    finally:
        ctx.close()

    # 4. `/lineage/house/1` & `/lineage/house/1?role=H1` Scoped House Lookup
    ctx, page, diag = _create_monitored_page(browser, live_server, viewport)
    try:
        page.goto(f"{live_server}/lineage/house/1", wait_until="networkidle")
        page.locator("#custodial-lookup-input").fill("Eleanor")
        page.locator("#custodial-lookup-btn").click()
        drawer = page.locator("#custodial-lookup-drawer")
        drawer.locator(".custodial-lookup-item").first.wait_for(state="visible", timeout=5000)
        assert "Eleanor Vance" in drawer.inner_text()
        page.screenshot(path=str(SCREENSHOTS_DIR / f"lineage_house1_lookup_{vp_name}.png"), full_page=True)
        _assert_clean_page(page, diag, f"lineage_h2_{vp_name}")

        page.goto(f"{live_server}/lineage/house/1?role=H1", wait_until="networkidle")
        page.locator("#custodial-lookup-input").fill("Eleanor")
        page.locator("#custodial-lookup-btn").click()
        drawer = page.locator("#custodial-lookup-drawer")
        drawer.locator(".custodial-lookup-item").first.wait_for(state="visible", timeout=5000)
        assert "$****.**" in drawer.inner_text()
        _assert_clean_page(page, diag, f"lineage_h1_{vp_name}")
    finally:
        ctx.close()

    # 5. `/admin/tech?tier=T1` Technical Node/Relay Lookup — STRICT Directive R-12 masking
    ctx, page, diag = _create_monitored_page(browser, live_server, viewport)
    try:
        page.goto(f"{live_server}/admin/tech?tier=T1", wait_until="networkidle")
        page.locator("#custodial-lookup-input").fill("HOUSE-01")
        page.locator("#custodial-lookup-btn").click()
        drawer = page.locator("#custodial-lookup-drawer")
        drawer.locator(".custodial-lookup-item").first.wait_for(state="visible", timeout=5000)
        text = drawer.inner_text()
        assert "SCMA-MEM-****" in text
        assert "$****.**" in text
        assert "Eleanor" not in text
        assert "$5,000.00" not in text
        assert page.locator("#tier-switcher").count() == 0
        page.screenshot(path=str(SCREENSHOTS_DIR / f"tech_r12_lookup_{vp_name}.png"), full_page=True)
        _assert_clean_page(page, diag, f"tech_t1_{vp_name}")
    finally:
        ctx.close()
