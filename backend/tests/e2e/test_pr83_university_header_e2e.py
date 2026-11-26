"""PR #83 — Playwright E2E Verification:
- PDEUE University (/companion): Guided Step-by-Step always starts on Chapter 1 (NOT Chapter 6),
  predictable chapter & paced narration beat transitions without hanging in headless browsers,
  and working Load Manual reader panel with visible content and Close Reader button.
- Community Hearth (/community): Ask-Tutor Clear button (#clearCommunityTutorBtn) resets input
  and conversation cleanly with ZERO network calls and restores focus to #tutorQuery.
- 3-Row Institutional Header alignment on /dashboard and /community/heritage (Row 1 Back to Home +
  A|A+|A++ aligned cleanly on desktop 1440x900, cohesive PDEUE University pill, full achievements
  + 11 bordure-differenced McCormick Houses in Hall of Arms), zero console/page/CDN/HTTP errors,
  and zero horizontal overflow across 1440x900 and 390x844.
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
    reason="Playwright is required for PR #83 E2E tests",
)
sync_playwright = playwright_sync.sync_playwright

pytestmark = pytest.mark.e2e

REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_DIR = REPO_ROOT / "backend"
SCREENSHOTS_DIR = REPO_ROOT / "artifacts" / "playwright_screenshots" / "pr83_polish"

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

    with tempfile.TemporaryDirectory(prefix="pdeue_pr83_e2e_") as tmp_dir:
        db_path = Path(tmp_dir) / "pdeue_pr83_e2e.db"
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
        "all_requests": [],
    }

    def _intercept(route: Any) -> None:
        req = route.request
        parsed = urlparse(req.url)
        diagnostics["all_requests"].append(req.url)
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
def test_pr83_companion_guided_starts_chapter1_narration_and_load_manual_e2e(
    live_server: str,
    browser: Any,
    vp_name: str,
    vp_size: dict[str, int],
) -> None:
    context, page, diag = _create_monitored_page(browser, live_server, vp_size)
    try:
        # 1. Even with ?scma_id=... (standard member link), /companion starts cleanly on Chapter 1 (NOT Chapter 6)
        page.goto(f"{live_server}/companion?scma_id=SCMA-ELEANOR_-B2B31C9E", wait_until="networkidle")
        assert page.locator("#chapter-waterfall").is_visible()
        assert not page.locator("#chapter-governance").is_visible()
        assert "Chapter 1 of 6" in page.locator("#activeChapterBadge").inner_text()
        assert "what this means in plain english" in page.locator("#chapter-waterfall").inner_text().lower()

        # 2. Jump to Chapter 6, then click "Guided Step-by-Step" -> MUST return cleanly to Chapter 1
        page.locator("#jumpChapter6Btn").click()
        assert page.locator("#chapter-governance").is_visible()
        assert "Chapter 6 of 6" in page.locator("#activeChapterBadge").inner_text()

        page.locator("#guidedMode").click()
        assert page.locator("#chapter-waterfall").is_visible()
        assert not page.locator("#chapter-governance").is_visible()
        assert "Chapter 1 of 6" in page.locator("#activeChapterBadge").inner_text()

        # 3. Verify Next Chapter, Previous Chapter, and Paced Narration Beat progression (headless-safe)
        page.locator("#nextChapterBtn").click()
        assert page.locator("#chapter-risk-governor").is_visible()
        assert "Chapter 2 of 6" in page.locator("#activeChapterBadge").inner_text()
        page.locator("#prevChapterBtn").click()
        assert page.locator("#chapter-waterfall").is_visible()

        initial_beat = page.locator("#narrationBeatStep").inner_text()
        assert "Beat 1 of 18" in initial_beat
        page.locator("#nextBeatBtn").click()
        assert "Beat 2 of 18" in page.locator("#narrationBeatStep").inner_text()
        page.locator("#playPause").click()
        page.wait_for_timeout(350)
        assert "Pause" in page.locator("#playPause").inner_text()
        page.locator("#playPause").click()
        assert "Play" in page.locator("#playPause").inner_text()

        page.screenshot(path=str(SCREENSHOTS_DIR / f"pr83_companion_guided_ch1_{vp_name}.png"), full_page=True)
        _assert_clean_and_no_overflow(page, diag, f"companion_guided_{vp_name}")

        # 4. Switch to Degree Colleges tab and click "Load Manual" on CLASS_F_FINANCIAL_MANUAL.md card
        page.locator("#tabCollegesBtn").click()
        page.locator('button[data-manual-load="CLASS_F_FINANCIAL_MANUAL.md"]').click()
        page.wait_for_function(
            "() => (document.getElementById('manualReaderStatus')?.textContent || '').includes('CLASS_F_FINANCIAL_MANUAL.md')"
        )
        assert page.locator("#manual-reader-panel").is_visible()
        reader_text = page.locator("#manual-reader-container").inner_text()
        assert len(reader_text.strip()) > 120, f"Expected full manual text in reader, got: {reader_text!r}"
        page.screenshot(path=str(SCREENSHOTS_DIR / f"pr83_companion_manual_reader_{vp_name}.png"), full_page=True)

        # Close Reader hides panel cleanly, clicking Load Manual reopens it
        page.locator("#closeManualReaderBtn").click()
        assert not page.locator("#manual-reader-panel").is_visible()
        page.locator('button[data-manual-load="USER_QUICKSTART.md"]').click()
        page.wait_for_function(
            "() => (document.getElementById('manualReaderStatus')?.textContent || '').includes('USER_QUICKSTART.md')"
        )
        assert page.locator("#manual-reader-panel").is_visible()
        _assert_clean_and_no_overflow(page, diag, f"companion_colleges_{vp_name}")
    finally:
        context.close()


@pytest.mark.parametrize("vp_name,vp_size", list(VIEWPORTS.items()))
def test_pr83_community_ask_tutor_clear_button_zero_network_e2e(
    live_server: str,
    browser: Any,
    vp_name: str,
    vp_size: dict[str, int],
) -> None:
    context, page, diag = _create_monitored_page(browser, live_server, vp_size)
    try:
        page.goto(f"{live_server}/community", wait_until="networkidle")
        page.locator('button.tab[data-tab="academy"]').click()
        assert page.locator("#academy").is_visible()
        assert page.locator("#clearCommunityTutorBtn").is_visible()

        # Submit a real tutor question first
        page.locator("#tutorQuery").fill("Why does Quarter-Kelly add a cushion?")
        page.locator("#askCommunityTutorBtn").click()
        page.wait_for_function(
            "() => (document.getElementById('tutorLog')?.textContent || '').includes('one fourth')"
        )
        assert "Why does Quarter-Kelly add a cushion?" in page.locator("#tutorLog").inner_text()

        # Fill a draft input, then click Clear and assert ZERO network requests + clean reset + focus restored
        page.locator("#tutorQuery").fill("Draft question to discard")
        req_count_before = len(diag["all_requests"])
        page.locator("#clearCommunityTutorBtn").click()
        page.wait_for_timeout(150)

        assert len(diag["all_requests"]) == req_count_before, (
            f"Clear triggered unexpected network calls: {diag['all_requests'][req_count_before:]}"
        )
        assert page.locator("#tutorQuery").input_value() == ""
        log_text = page.locator("#tutorLog").inner_text()
        assert "Ask me to explain a curriculum concept in plain English." in log_text
        assert "Quarter-Kelly" not in log_text
        focused_id = page.evaluate("() => document.activeElement && document.activeElement.id")
        assert focused_id == "tutorQuery", f"Expected focus on #tutorQuery after Clear, got {focused_id!r}"

        page.screenshot(path=str(SCREENSHOTS_DIR / f"pr83_community_tutor_clear_{vp_name}.png"), full_page=True)
        _assert_clean_and_no_overflow(page, diag, f"community_tutor_clear_{vp_name}")
    finally:
        context.close()


@pytest.mark.parametrize("vp_name,vp_size", list(VIEWPORTS.items()))
def test_pr83_three_row_header_alignment_and_two_scale_heraldry_e2e(
    live_server: str,
    browser: Any,
    vp_name: str,
    vp_size: dict[str, int],
) -> None:
    context, page, diag = _create_monitored_page(browser, live_server, vp_size)
    try:
        for route, slug in (("/dashboard", "dashboard"), ("/community/heritage", "heritage")):
            page.goto(f"{live_server}{route}", wait_until="networkidle")
            page.wait_for_timeout(200)

            assert page.locator(".portal-header-row1").is_visible()
            assert page.locator(".portal-header-row2").is_visible()
            assert page.locator(".portal-header-row3").is_visible()
            assert page.locator("#navCompanionLink").is_visible()

            # On desktop 1440x900, verify Brand Lockup, Back to Home, and A|A+|A++ align cleanly on Row 1
            if vp_name == "desktop_1440x900":
                row1_geom = page.evaluate(
                    """() => {
                        const lockup = document.querySelector('.portal-header-row1 .brand-lockup').getBoundingClientRect();
                        const back = document.getElementById('backToHomeBtn').getBoundingClientRect();
                        const scale = document.getElementById('textScaleGroup').getBoundingClientRect();
                        const row2 = document.querySelector('.portal-header-row2').getBoundingClientRect();
                        const uni = document.getElementById('navCompanionLink');
                        const uniStyle = window.getComputedStyle(uni);
                        return {
                            lockupTop: Math.round(lockup.top),
                            lockupBottom: Math.round(lockup.bottom),
                            backTop: Math.round(back.top),
                            backRight: Math.round(back.right),
                            scaleTop: Math.round(scale.top),
                            scaleLeft: Math.round(scale.left),
                            row2Top: Math.round(row2.top),
                            uniRadius: parseFloat(uniStyle.borderTopLeftRadius || '0'),
                            uniDecoration: uniStyle.textDecorationLine,
                        };
                    }"""
                )
                assert abs(row1_geom["backTop"] - row1_geom["scaleTop"]) <= 12, f"Row 1 controls misaligned on {route}: {row1_geom}"
                assert abs(row1_geom["backTop"] - row1_geom["lockupTop"]) <= 20, f"Row 1 wrapped below crests on {route}: {row1_geom}"
                assert row1_geom["backRight"] <= row1_geom["scaleLeft"] + 2, f"Back to Home overlaps text scale on {route}: {row1_geom}"
                assert row1_geom["row2Top"] >= row1_geom["lockupBottom"] - 2, f"Row 2 collided with Row 1 on {route}: {row1_geom}"
                assert row1_geom["uniRadius"] >= 16, f"PDEUE University must be styled as a pill button on {route}: {row1_geom}"
                assert "underline" not in row1_geom["uniDecoration"], f"PDEUE University must not be bare underlined link on {route}: {row1_geom}"

            if route == "/community/heritage":
                # Verify both full achievement crests load crisply and all 12 Houses render with bordure pills
                ach_status = page.evaluate(
                    """() => Array.from(document.querySelectorAll('#foundingAchievementsShowcase img')).map(img => ({
                        src: img.getAttribute('src') || '',
                        complete: img.complete,
                        naturalWidth: img.naturalWidth,
                    }))"""
                )
                assert len(ach_status) == 2
                assert ach_status[0]["src"].endswith("carmichael_achievement.jpg") and ach_status[0]["naturalWidth"] > 0
                assert ach_status[1]["src"].endswith("mccormick_achievement.jpg") and ach_status[1]["naturalWidth"] > 0
                page.locator("#housesGalleryGrid a.gallery-card").first.wait_for(state="visible", timeout=5000)
                assert page.locator("#housesGalleryGrid a.gallery-card").count() == 12
                assert page.locator("#housesGalleryGrid .bordure-pill").count() == 12
                house_imgs = page.evaluate(
                    """() => Array.from(document.querySelectorAll('#housesGalleryGrid img')).map(img => ({
                        src: img.getAttribute('src') || '',
                        complete: img.complete,
                        naturalWidth: img.naturalWidth,
                    }))"""
                )
                assert len(house_imgs) == 12
                for hi in house_imgs:
                    assert hi["complete"] is True and hi["naturalWidth"] > 0, f"Broken House crest SVG: {hi}"

            page.screenshot(path=str(SCREENSHOTS_DIR / f"pr83_{slug}_3row_{vp_name}.png"), full_page=True)
            _assert_clean_and_no_overflow(page, diag, f"{slug}_3row_{vp_name}")
    finally:
        context.close()
