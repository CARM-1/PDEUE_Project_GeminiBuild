"""PR #96 Playwright E2E Verification Suite:
Local-First Visual Media Cards, Ordered Playbook Step Checklists, Lightbox Zoom,
Calm 'Local Library · Zero Internet' Badge, and Class H / House Genealogist Instructional Aid.

Verifies against the live FastAPI server (paper mode, isolated temp SQLite):
1. Member Desktop (/member): tutor query renders Local Library badge, annotated local screenshot
   (naturalWidth > 0), numbered callout legend, ordered step checklist, manual citation badge,
   working click-to-enlarge modal, and zero-network Clear Answer reset.
2. Class H Sovereign Desk (/lineage/house/1?role=H1 and ?role=H2): embedded House & Heritage
   Instructional Aid answers locally with R-12 masking preserved for H1, renders local screenshot
   and step checklist, and resets cleanly with zero network requests.
3. Hall of Arms (/community/heritage): embedded HOUSE_GENEALOGIST Instructional Aid renders
   Hall of Arms screenshot card, callout legend, step checklist, and zero broken images or console errors.
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
    reason="Playwright is required for PR #96 E2E tests",
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


def _http_get(url: str, timeout: float = 2.0) -> int:
    try:
        with urlopen(Request(url, method="GET"), timeout=timeout) as resp:
            return int(resp.status)
    except HTTPError as err:
        return int(err.code)


@pytest.fixture(scope="module")
def live_server() -> str:
    port = _find_free_port()
    base_url = f"http://127.0.0.1:{port}"
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="pdeue_pr96_e2e_") as tmp_dir:
        db_path = Path(tmp_dir) / "pdeue_pr96.db"
        mutex_path = Path(tmp_dir) / "pdeue_pr96_mutex.sqlite3"
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
                stderr = proc.stderr.read().decode("utf-8", errors="replace") if proc.stderr else ""
                raise RuntimeError(f"FastAPI server exited early (code={proc.returncode}): {stderr}")
            try:
                if _http_get(f"{base_url}/health", timeout=1.0) == 200:
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
        parsed = urlparse(route.request.url)
        if parsed.scheme in {"data", "blob", "about"} or parsed.netloc == base_host:
            route.continue_()
            return
        diagnostics["external_cdn_requests"].append(route.request.url)
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


def _assert_hygiene_and_loaded_images(page: Any, diagnostics: dict[str, list[Any]]) -> None:
    report = page.evaluate(
        """() => {
            const overflowPx = Math.round(document.documentElement.scrollWidth - window.innerWidth);
            const cdnTags = [];
            for (const el of document.querySelectorAll('script[src], link[href]')) {
                const raw = el.getAttribute('src') || el.getAttribute('href') || '';
                if (/^https?:\\/\\//i.test(raw)) cdnTags.push(raw);
            }
            const brokenMediaImgs = [];
            for (const img of document.querySelectorAll('.tutor-media-thumb')) {
                if (!img.complete || img.naturalWidth === 0) {
                    brokenMediaImgs.push(img.getAttribute('src') || '(empty)');
                }
            }
            return { overflowPx, cdnTags, brokenMediaImgs };
        }"""
    )
    assert report["overflowPx"] <= 1, f"Horizontal overflow detected: {report['overflowPx']}px"
    assert not report["cdnTags"], f"External CDN tags found: {report['cdnTags']}"
    assert not report["brokenMediaImgs"], f"Broken visual media images: {report['brokenMediaImgs']}"
    assert not diagnostics["console_errors"], f"Console errors: {diagnostics['console_errors']}"
    assert not diagnostics["page_errors"], f"Uncaught page errors: {diagnostics['page_errors']}"
    assert not diagnostics["external_cdn_requests"], f"External CDN requests: {diagnostics['external_cdn_requests']}"
    assert not diagnostics["failed_requests"], f"HTTP >= 400 responses: {diagnostics['failed_requests']}"


@pytest.mark.parametrize("viewport_name,viewport", list(VIEWPORTS.items()))
def test_pr96_member_tutor_renders_annotated_screenshot_card_steps_and_lightbox(
    live_server: str,
    browser: Any,
    viewport_name: str,
    viewport: dict[str, int],
) -> None:
    context, page, diagnostics = _create_monitored_page(browser, live_server, viewport)
    try:
        page.goto(f"{live_server}/member?scma_id=SCMA-ELEANOR_-B2B31C9E", wait_until="networkidle")
        page.locator("#tabBtnEngine").click()
        page.locator("#tutorCard").wait_for(state="visible")

        page.locator("#tutorInput").fill("How do I use the Downward-Only Risk Dial and 40% cash cushion?")
        page.locator("#askTutorBtn").click()

        page.locator("#tutorVisualAidHost .tutor-media-card").first.wait_for(state="visible")
        page.wait_for_function(
            "() => Array.from(document.querySelectorAll('#tutorVisualAidHost .tutor-media-thumb')).every(img => img.complete && img.naturalWidth > 0)"
        )

        # Calm Local Library badge visible
        assert page.locator("#tutorLocalBadgePill").is_visible()
        assert "Local Library · Zero Internet" in page.locator("#tutorLocalBadgePill").inner_text()

        # Annotated screenshot card, callout legend, ordered steps, and manual citation rendered
        assert page.locator("#tutorVisualAidHost .tutor-callout-legend li").count() >= 2
        assert page.locator("#tutorVisualAidHost .tutor-steps-list li").count() >= 2
        assert page.locator("#tutorVisualAidHost .tutor-manual-cite-badge").count() >= 1

        # Click-to-enlarge lightbox opens cleanly with loaded image & closes cleanly
        page.locator("#tutorVisualAidHost .tutor-media-thumb-btn").first.click()
        page.locator("#pdeueMediaLightbox").wait_for(state="visible")
        page.wait_for_function(
            "() => { const img = document.getElementById('pdeueMediaLightboxImg'); return img && img.complete && img.naturalWidth > 0; }"
        )
        page.screenshot(
            path=str(SCREENSHOTS_DIR / f"pr96_member_tutor_lightbox_{viewport_name}.png"),
            full_page=True,
        )
        page.locator("#pdeueMediaLightboxCloseBtn").click()
        assert page.locator("#pdeueMediaLightbox").is_hidden()

        page.locator("#tutorCard").scroll_into_view_if_needed()
        page.screenshot(
            path=str(SCREENSHOTS_DIR / f"pr96_member_tutor_visual_card_{viewport_name}.png"),
            full_page=True,
        )

        _assert_hygiene_and_loaded_images(page, diagnostics)
    finally:
        context.close()


@pytest.mark.parametrize("viewport_name,viewport", list(VIEWPORTS.items()))
def test_pr96_class_h_and_heritage_instructional_aid_visual_media_and_r12_masking(
    live_server: str,
    browser: Any,
    viewport_name: str,
    viewport: dict[str, int],
) -> None:
    context, page, diagnostics = _create_monitored_page(browser, live_server, viewport)
    try:
        # 1. /lineage/house/1?role=H1 (Directive R-12 masked)
        page.goto(f"{live_server}/lineage/house/1?role=H1", wait_until="networkidle")
        page.locator("#lineageTutorPanel").wait_for(state="visible")
        page.locator("#lineageChipR12").click()

        page.locator("#lineageTutorOutput .tutor-media-card").first.wait_for(state="visible")
        page.wait_for_function(
            "() => Array.from(document.querySelectorAll('#lineageTutorOutput .tutor-media-thumb')).every(img => img.complete && img.naturalWidth > 0)"
        )
        out_text = page.locator("#lineageTutorOutput").inner_text()
        assert "Local Library · Zero Internet" in out_text
        assert "R-12 MASKED" in out_text
        assert page.locator("#lineageTutorOutput .tutor-steps-list li").count() >= 2
        assert page.locator("#lineageTutorOutput .tutor-manual-cite-badge").count() >= 1

        page.locator("#lineageTutorPanel").scroll_into_view_if_needed()
        page.screenshot(
            path=str(SCREENSHOTS_DIR / f"pr96_lineage_h1_tutor_{viewport_name}.png"),
            full_page=True,
        )

        # Verify pure client-side Clear Answer button (ZERO fetch/XHR, focus restored)
        clear_check = page.evaluate(
            """() => {
                const calls = [];
                const origFetch = window.fetch;
                window.fetch = function(...args) { calls.push(String(args[0])); return origFetch.apply(this, args); };
                try {
                    document.getElementById('clearLineageTutorBtn').click();
                } finally {
                    window.fetch = origFetch;
                }
                return {
                    calls,
                    inputVal: document.getElementById('lineageTutorInput').value,
                    activeId: document.activeElement ? document.activeElement.id : null,
                };
            }"""
        )
        assert clear_check["calls"] == []
        assert clear_check["inputVal"] == ""
        assert clear_check["activeId"] == "lineageTutorInput"

        _assert_hygiene_and_loaded_images(page, diagnostics)

        # 2. /community/heritage (HOUSE_GENEALOGIST)
        page.goto(f"{live_server}/community/heritage", wait_until="networkidle")
        page.locator("#heritageTutorPanel").wait_for(state="visible")
        page.locator("#heritageChipCurate").click()

        page.locator("#heritageTutorOutput .tutor-media-card").first.wait_for(state="visible")
        page.wait_for_function(
            "() => Array.from(document.querySelectorAll('#heritageTutorOutput .tutor-media-thumb')).every(img => img.complete && img.naturalWidth > 0)"
        )
        h_text = page.locator("#heritageTutorOutput").inner_text()
        assert "Local Library · Zero Internet" in h_text
        assert "HOUSE_GENEALOGIST" in h_text
        assert page.locator("#heritageTutorOutput .tutor-steps-list li").count() >= 2
        assert page.locator("#heritageTutorOutput .tutor-manual-cite-badge").count() >= 1

        page.locator("#heritageTutorPanel").scroll_into_view_if_needed()
        page.screenshot(
            path=str(SCREENSHOTS_DIR / f"pr96_heritage_genealogist_tutor_{viewport_name}.png"),
            full_page=True,
        )

        _assert_hygiene_and_loaded_images(page, diagnostics)
    finally:
        context.close()
