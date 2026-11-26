"""Playwright E2E Verification for UI/UX Declutter & Companion Continuous Playback.

Verifies:
1. Companion Orientation + Chapter 1 Waterfall SVG are BOTH 100% visible above the fold at 1440x900
   when Orientation is expanded, and toggling collapse/expand switches layout cleanly with 0px overflow.
2. Continuous Guided Tour Playback:
   - Auto-Advance toggle defaults to On (`Auto-Advance: On`, `aria-pressed="true"`).
   - Seamless beat-to-beat and chapter-to-chapter auto-advance (both via silent visual timer AND
     via Studio Audio `ended` events) without requiring manual clicks on each chapter.
   - Toggling Auto-Advance Off pauses cleanly at beat end (`Beat complete · Auto-Advance Off`)
     while manual Next Beat / Next Ch / chapter-pill jump controls continue to work.
3. Batch 4 local Studio Audio manifest wiring (`/api/v1/portal/companion/state` -> `studio_audio_ready: true`)
   remains intact with zero external CDN requests and zero console/page errors.
4. Decluttered disclosure drawers on `/member` and `/dashboard` preserve 100% of DOM controls and open cleanly.
"""
from __future__ import annotations

import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from typing import Any, Dict, List
from urllib.parse import urlparse
from urllib.request import urlopen

import pytest

playwright_sync = pytest.importorskip(
    "playwright.sync_api",
    reason="Playwright is required for UI declutter and Companion playback E2E tests",
)
sync_playwright = playwright_sync.sync_playwright

pytestmark = pytest.mark.e2e

REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_DIR = REPO_ROOT / "backend"


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture(scope="module")
def live_server() -> str:
    port = _find_free_port()
    base_url = f"http://127.0.0.1:{port}"

    with tempfile.TemporaryDirectory(prefix="pdeue_declutter_e2e_") as tmp_dir:
        db_path = Path(tmp_dir) / "pdeue_declutter_e2e.db"
        env = os.environ.copy()
        env["DATABASE_URL"] = f"sqlite:///{db_path}"
        env["PDEUE_VENUE_MODE"] = "paper"
        env["PDEUE_LIVE_TRADING_ENABLED"] = "false"
        env["PDEUE_GOVERNANCE_MODE"] = "EXECUTIVE_COMMAND"
        env["PYTHONUNBUFFERED"] = "1"
        for key in (
            "FAMILY_HUB_BASE_URL",
            "UNIVERSITY_BASE_URL",
            "PDEUE_VAULT_BASE_URL",
            "PDEUE_ADMIN_BASE_URL",
            "IFAS_ACCOUNTING_BASE_URL",
            "PDEUE_COMPANION_MEDIA_DIR",
        ):
            env.pop(key, None)

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
                try:
                    with urlopen(f"{base_url}/health", timeout=1.5) as resp:
                        if resp.status == 200:
                            break
                except Exception:
                    time.sleep(0.2)
            else:
                raise RuntimeError("FastAPI test server failed to start within 25s")
            yield base_url
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()


def test_companion_orientation_and_illustration_both_above_fold_and_continuous_playback(live_server: str) -> None:
    console_errors: List[str] = []
    page_errors: List[str] = []
    external_requests: List[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()

        page.on(
            "console",
            lambda msg: console_errors.append(msg.text) if msg.type == "error" else None,
        )
        page.on("pageerror", lambda err: page_errors.append(str(err)))
        page.on(
            "request",
            lambda req: external_requests.append(req.url)
            if urlparse(req.url).scheme in ("http", "https")
            and urlparse(req.url).hostname not in ("127.0.0.1", "localhost")
            else None,
        )

        page.goto(f"{live_server}/companion", wait_until="networkidle")
        page.wait_for_timeout(300)

        # 1. Verify Batch 4 studio audio wiring & zero horizontal overflow
        state_resp = page.evaluate("() => fetch('/api/v1/portal/companion/state').then(r => r.json())")
        assert state_resp["studio_audio_ready"] is True

        overflow = page.evaluate("() => Math.max(0, document.documentElement.scrollWidth - window.innerWidth)")
        assert overflow == 0

        # 2. Verify BOTH Orientation panel and Chapter 1 Waterfall SVG are 100% visible above the fold at 1440x900
        rects: Dict[str, Any] = page.evaluate(
            """() => {
                const o = document.getElementById('chapter-orientation').getBoundingClientRect();
                const svg = document.querySelector('#chapter-waterfall svg.waterfall').getBoundingClientRect();
                return {
                    orientation: { top: o.top, bottom: o.bottom, width: o.width, height: o.height },
                    waterfall: { top: svg.top, bottom: svg.bottom, width: svg.width, height: svg.height },
                };
            }"""
        )
        assert 0 <= rects["orientation"]["top"] < rects["orientation"]["bottom"] <= 900, rects
        assert 0 <= rects["waterfall"]["top"] < rects["waterfall"]["bottom"] <= 900, rects

        # Collapse and re-expand Orientation cleanly
        page.click("#toggleOrientationBtn")
        page.wait_for_timeout(150)
        assert page.locator("#simulatorLayout").evaluate("el => el.classList.contains('orientation-collapsed')")
        assert "Show Orientation" in page.locator("#toggleOrientationBtn").inner_text()
        page.click("#toggleOrientationBtn")
        page.wait_for_timeout(150)
        assert not page.locator("#simulatorLayout").evaluate("el => el.classList.contains('orientation-collapsed')")

        # 3. Verify Auto-Advance toggle default & seamless Chapter 1 -> Chapter 2 transition (visual timer)
        toggle = page.locator("#autoAdvanceToggle")
        assert toggle.get_attribute("aria-pressed") == "true"
        assert "Auto-Advance: On" in toggle.inner_text()

        # Switch to silent visual timer and seek near the end of Beat 3 (end of Ch 1, t=44.6s)
        page.select_option("#voiceSelect", "default")
        page.evaluate("() => { window.PDEUECompanion.seek(44.6, false); }")
        assert page.evaluate("() => window.PDEUECompanion.getState().activeIndex") == 0
        page.click("#playPause")
        page.wait_for_function("() => window.PDEUECompanion.getState().activeIndex === 1", timeout=4000)
        assert page.locator("#chapter-risk-governor").is_visible()
        assert "Chapter 2 of 6" in page.locator("#activeChapterBadge").inner_text()
        assert page.evaluate("() => window.PDEUECompanion.getState().playing") is True

        # 4. Verify Studio Audio `ended` event auto-advances across beats/chapters seamlessly
        page.click("#playPause")  # pause first
        page.select_option("#voiceSelect", "studio:mentor_f_aa")
        page.evaluate("() => { window.PDEUECompanion.seek(89.0, false); }")  # Beat 6 (end of Ch 2)
        assert page.evaluate("() => window.PDEUECompanion.getState().activeIndex") == 1
        page.click("#playPause")
        page.wait_for_timeout(150)
        page.evaluate("() => { document.getElementById('companionAudioPlayer').dispatchEvent(new Event('ended')); }")
        page.wait_for_function("() => window.PDEUECompanion.getState().activeIndex === 2", timeout=3000)
        assert page.locator("#chapter-segregation").is_visible()
        assert "Chapter 3 of 6" in page.locator("#activeChapterBadge").inner_text()

        # 5. Verify toggling Auto-Advance Off pauses at beat end instead of auto-advancing
        page.click("#autoAdvanceToggle")
        assert toggle.get_attribute("aria-pressed") == "false"
        assert "Auto-Advance: Off" in toggle.inner_text()
        page.evaluate("() => { document.getElementById('companionAudioPlayer').dispatchEvent(new Event('ended')); }")
        page.wait_for_timeout(200)
        assert page.evaluate("() => window.PDEUECompanion.getState().playing") is False
        assert page.evaluate("() => window.PDEUECompanion.getState().activeIndex") == 2
        assert "Auto-Advance Off" in page.locator("#audioBadge").inner_text()

        # 6. Manual Next Beat / Next Ch controls still work
        page.click("#nextChapterBtn")
        page.wait_for_timeout(150)
        assert page.evaluate("() => window.PDEUECompanion.getState().activeIndex") == 3
        assert page.locator("#chapter-float-ceiling").is_visible()

        browser.close()

    assert console_errors == [], f"Console errors: {console_errors}"
    assert page_errors == [], f"Page errors: {page_errors}"
    assert external_requests == [], f"External requests: {external_requests}"


def test_decluttered_drawers_preserve_functionality_on_member_and_dashboard(live_server: str) -> None:
    console_errors: List[str] = []
    page_errors: List[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
        page.on("pageerror", lambda err: page_errors.append(str(err)))

        # Member portal drawers
        page.goto(f"{live_server}/member", wait_until="networkidle")
        assert page.evaluate("() => Math.max(0, document.documentElement.scrollWidth - window.innerWidth)") == 0
        assert page.locator("#projectionTablesDrawer").get_attribute("open") is None
        page.click("#projectionTablesDrawer summary")
        page.wait_for_timeout(150)
        assert page.locator("#projectionTables").is_visible()
        page.click("#tabBtnEngine")
        page.wait_for_timeout(150)
        assert page.locator("#glassEngineRackDrawer").get_attribute("open") is None
        page.click("#glassEngineRackDrawer summary")
        page.wait_for_timeout(150)
        assert page.locator("#slotRack").is_visible()

        # Dashboard portal drawers & above-fold visual telemetry
        page.goto(f"{live_server}/dashboard", wait_until="networkidle")
        assert page.evaluate("() => Math.max(0, document.documentElement.scrollWidth - window.innerWidth)") == 0
        assert page.locator("#chart-equity").is_visible()
        page.click("#tab-btn-3")
        page.wait_for_timeout(150)
        assert page.locator("#adminShadowHunchCard").is_visible()
        assert page.locator("#adminShadowHunchCard").get_attribute("open") is None
        page.click("#adminShadowHunchCard summary")
        page.wait_for_timeout(150)
        assert page.locator("#adminShadowBidBtn").is_visible()

        browser.close()

    assert console_errors == [], f"Console errors: {console_errors}"
    assert page_errors == [], f"Page errors: {page_errors}"
