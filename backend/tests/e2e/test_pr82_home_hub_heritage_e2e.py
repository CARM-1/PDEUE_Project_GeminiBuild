"""PR #82 — Playwright E2E Verification for Family Home Hub, Senior Accessibility (A/A+/A++),
Upgraded /community Hearth, Hall of Arms (/community/heritage), and Family Alerts Drawer.
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
from urllib.parse import urlparse
from urllib.request import urlopen

import pytest

playwright_sync = pytest.importorskip(
    "playwright.sync_api",
    reason="Playwright is required for PR #82 E2E tests",
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


@pytest.fixture(scope="module")
def live_server() -> str:
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    port = _find_free_port()
    base_url = f"http://127.0.0.1:{port}"

    with tempfile.TemporaryDirectory(prefix="pdeue_pr82_e2e_") as tmp_dir:
        db_path = Path(tmp_dir) / "pdeue_pr82_e2e.db"
        env = os.environ.copy()
        env["DATABASE_URL"] = f"sqlite:///{db_path}"
        env["PDEUE_VENUE_MODE"] = "paper"
        env["PDEUE_LIVE_TRADING_ENABLED"] = "false"
        env["PDEUE_GOVERNANCE_MODE"] = "EXECUTIVE_COMMAND"
        env["PYTHONUNBUFFERED"] = "1"

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
        try:
            deadline = time.monotonic() + 25.0
            while time.monotonic() < deadline:
                if proc.poll() is not None:
                    out, err = proc.communicate(timeout=2)
                    raise RuntimeError(
                        f"Uvicorn exited early ({proc.returncode})\n"
                        f"STDOUT: {out.decode(errors='replace')}\n"
                        f"STDERR: {err.decode(errors='replace')}"
                    )
                try:
                    with urlopen(f"{base_url}/healthz", timeout=1.5) as resp:
                        if resp.status == 200:
                            break
                except Exception:
                    time.sleep(0.2)
            else:
                raise RuntimeError(f"Timed out waiting for {base_url}/healthz")

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
        req = route.request
        parsed = urlparse(req.url)
        if parsed.scheme in {"data", "blob", "about"} or parsed.netloc == base_host:
            route.continue_()
            return
        if req.resource_type == "document" and parsed.hostname == "meet.jit.si":
            route.fulfill(
                status=200,
                content_type="text/html",
                body="<!doctype html><html><body>Sandboxed Jitsi offline stub</body></html>",
            )
            return
        diagnostics["external_cdn_requests"].append({"url": req.url, "type": req.resource_type})
        route.abort("blockedbyclient")

    context.route("**/*", _intercept)
    page = context.new_page()
    page.set_default_timeout(15000)
    page.on("console", lambda msg: diagnostics["console_errors"].append(msg.text) if msg.type == "error" else None)
    page.on("pageerror", lambda err: diagnostics["page_errors"].append(str(err)))
    page.on(
        "response",
        lambda resp: diagnostics["failed_requests"].append({"status": resp.status, "url": resp.url})
        if resp.status >= 400
        else None,
    )
    return context, page, diagnostics


def _assert_clean_and_no_overflow(page: Any, diagnostics: dict[str, list[Any]], label: str) -> None:
    audit = page.evaluate(
        """() => {
            const overflowPx = Math.max(0, Math.round(document.documentElement.scrollWidth - window.innerWidth));
            const cdnTags = [];
            for (const el of document.querySelectorAll('script[src], link[href]')) {
                const raw = el.getAttribute('src') || el.getAttribute('href') || '';
                if (/^https?:\\/\\//i.test(raw)) {
                    cdnTags.push(raw);
                }
            }
            return { overflowPx, cdnTags };
        }"""
    )
    assert audit["overflowPx"] <= 2, f"Horizontal overflow on {label}: {audit['overflowPx']}px"
    assert audit["cdnTags"] == [], f"External CDN tags on {label}: {audit['cdnTags']}"
    assert diagnostics["external_cdn_requests"] == [], f"External CDN requests on {label}: {diagnostics['external_cdn_requests']}"
    assert diagnostics["console_errors"] == [], f"Console errors on {label}: {diagnostics['console_errors']}"
    assert diagnostics["page_errors"] == [], f"Page errors on {label}: {diagnostics['page_errors']}"
    assert diagnostics["failed_requests"] == [], f"HTTP >= 400 on {label}: {diagnostics['failed_requests']}"


@pytest.mark.parametrize("vp_name,vp_size", list(VIEWPORTS.items()))
def test_pr82_home_hub_senior_text_scale_persistence_and_back_to_home(
    live_server: str,
    browser: Any,
    vp_name: str,
    vp_size: dict[str, int],
) -> None:
    context, page, diag = _create_monitored_page(browser, live_server, vp_size)
    try:
        # 1. Bare `/` redirects cleanly to `/home`
        page.goto(f"{live_server}/", wait_until="networkidle")
        assert urlparse(page.url).path == "/home"
        assert "Welcome to the Carmichael / McCormick Family Hub" in page.inner_text("h1")
        assert page.locator(".doorway-card").count() == 4
        assert page.locator("#roleDoorwayCard").count() == 0
        _assert_clean_and_no_overflow(page, diag, f"home_standard_{vp_name}")
        page.screenshot(path=str(SCREENSHOTS_DIR / f"pr82_home_hub_{vp_name}.png"), full_page=True)

        # 2. Switch text scale to A++ (xlarge) and verify zero horizontal overflow + persistence
        page.locator('#textScaleGroup button[data-scale="xlarge"]').click()
        assert page.evaluate("() => document.documentElement.getAttribute('data-text-scale')") == "xlarge"
        assert page.evaluate("() => localStorage.getItem('pdeue_text_scale')") == "xlarge"
        assert page.locator('#textScaleGroup button[data-scale="xlarge"]').get_attribute("aria-pressed") == "true"
        _assert_clean_and_no_overflow(page, diag, f"home_xlarge_{vp_name}")
        page.screenshot(path=str(SCREENSHOTS_DIR / f"pr82_home_hub_xlarge_{vp_name}.png"), full_page=True)

        # 3. Navigate via Family Hearth doorway card -> verify A++ persisted + upgraded /community controls
        page.locator("#doorwayFamilyHearth").click()
        page.wait_for_load_state("networkidle")
        assert urlparse(page.url).path == "/community"
        assert page.evaluate("() => document.documentElement.getAttribute('data-text-scale')") == "xlarge"
        assert page.locator("#benefactorWelcomeBanner").is_visible()
        assert page.locator("#backToHomeBtn").is_visible()
        _assert_clean_and_no_overflow(page, diag, f"community_xlarge_{vp_name}")

        # Open Pay-it-Forward (LCCF) Charter tab
        page.locator('button.tab[data-tab="charter"]').click()
        assert page.locator("#charter").is_visible()
        assert "Pay-it-Forward (FSAP) Sponsorship Charter" in page.locator("#charter").inner_text()

        # Open Classroom tab & switch Jitsi room preset to House 07 while keeping strict sandbox
        page.locator('button.tab[data-tab="classroom"]').click()
        page.locator("#jitsiHouseSelect").select_option("7")
        page.locator("#joinHouseRoomBtn").click()
        assert "PDEUEHouse07Gathering" in (page.locator("#jitsiVideoFrame").get_attribute("src") or "")
        assert page.locator("#jitsiVideoFrame").get_attribute("sandbox") == "allow-scripts allow-same-origin allow-forms allow-popups"

        # Open Family Alerts drawer on /community
        page.locator("#familyAlertsBtn").click()
        page.locator("#familyAlertsDrawer").wait_for(state="visible", timeout=5000)
        assert page.locator(".family-alert-item").count() >= 1
        page.screenshot(path=str(SCREENSHOTS_DIR / f"pr82_community_alerts_{vp_name}.png"), full_page=True)
        page.locator("#closeFamilyAlertsBtn").click()

        # 4. Return to /home via `← Back to Home`, then open `/member` and verify A++ persistence & IFAS handoff
        page.locator("#backToHomeBtn").click()
        page.wait_for_load_state("networkidle")
        assert urlparse(page.url).path == "/home"

        page.locator("#doorwayMyAccount").click()
        page.wait_for_load_state("networkidle")
        assert urlparse(page.url).path == "/member"
        assert page.evaluate("() => document.documentElement.getAttribute('data-text-scale')") == "xlarge"
        assert page.locator("#backToHomeBtn").is_visible()
        page.locator("#ifasHandoffBtn").click()
        assert page.locator("#ifasAirGapNotice").is_visible()
        _assert_clean_and_no_overflow(page, diag, f"member_xlarge_{vp_name}")
    finally:
        context.close()


@pytest.mark.parametrize("vp_name,vp_size", list(VIEWPORTS.items()))
def test_pr82_crest_click_to_hall_of_arms_search_and_history_pages(
    live_server: str,
    browser: Any,
    vp_name: str,
    vp_size: dict[str, int],
) -> None:
    context, page, diag = _create_monitored_page(browser, live_server, vp_size)
    try:
        # 1. Start on /member and click the founding twin-crest lockup -> lands on /community/heritage
        page.goto(f"{live_server}/member", wait_until="networkidle")
        page.locator("a.brand-lockup").first.click()
        page.wait_for_load_state("networkidle")
        assert urlparse(page.url).path == "/community/heritage"

        page.locator("#housesGalleryGrid a.gallery-card").first.wait_for(state="visible", timeout=5000)
        assert page.locator("#housesGalleryGrid a.gallery-card").count() == 12
        assert page.locator("#alliedSurnamesGrid a.gallery-card").count() >= 28
        _assert_clean_and_no_overflow(page, diag, f"hall_of_arms_{vp_name}")
        page.screenshot(path=str(SCREENSHOTS_DIR / f"pr82_hall_of_arms_{vp_name}.png"), full_page=True)

        # 2. Search for allied surname "Vance" -> filters cleanly
        page.locator("#heritageSearchInput").fill("Vance")
        page.wait_for_function(
            "() => document.querySelectorAll('#alliedSurnamesGrid a.gallery-card').length >= 1"
        )
        assert "Vance" in page.locator("#alliedSurnamesGrid").inner_text()

        # 3. Click into Vance surname history page -> verify Back to Hall of Arms + Back to Home
        page.locator('#alliedSurnamesGrid a.gallery-card[href="/community/heritage/surname/vance"]').first.click()
        page.wait_for_load_state("networkidle")
        assert urlparse(page.url).path == "/community/heritage/surname/vance"
        assert "Vance" in page.inner_text("h1")
        assert page.locator("#backToHallBtn").is_visible()
        assert page.locator("#backToHomeBtn").is_visible()
        _assert_clean_and_no_overflow(page, diag, f"surname_vance_{vp_name}")

        # 4. Visit House 01 history page and verify A++ mode has zero overflow
        page.locator("#backToHallBtn").click()
        page.wait_for_load_state("networkidle")
        page.locator('#housesGalleryGrid a.gallery-card[href="/community/heritage/house/1"]').first.click()
        page.wait_for_load_state("networkidle")
        assert urlparse(page.url).path == "/community/heritage/house/1"
        page.locator('#textScaleGroup button[data-scale="xlarge"]').click()
        _assert_clean_and_no_overflow(page, diag, f"house_01_xlarge_{vp_name}")
        page.screenshot(path=str(SCREENSHOTS_DIR / f"pr82_heritage_house1_{vp_name}.png"), full_page=True)
    finally:
        context.close()
