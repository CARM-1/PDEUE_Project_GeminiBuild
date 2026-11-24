"""PR #80 — Playwright E2E Verification:
- Twin heraldic crests & Founding Brand Lockup across all 7 portals
- Quiet CARM Aerotech Corporation footer colophon + fail-closed badge across all 7 portals
- Zero non-admin cross-tier jump pills on /advisor and /admin/tech (Chief Admin retains inspection)
- Compact PDEUE University (/companion) title & heading hierarchy above the fold
- Glossary Drawer plain-English default + collapsible "Technical & Governance Spec" details
- Zero console errors, zero uncaught page errors, zero external CDN tags/requests, zero HTTP >= 400, zero horizontal overflow
  across desktop (1440x900) and mobile (390x844).
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
    reason="Playwright is required for PR #80 E2E tests",
)
sync_playwright = playwright_sync.sync_playwright

pytestmark = pytest.mark.e2e

REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_DIR = REPO_ROOT / "backend"
SCREENSHOTS_DIR = REPO_ROOT / "artifacts" / "playwright_screenshots" / "pr80_branding_ux"

VIEWPORTS: dict[str, dict[str, int]] = {
    "desktop_1440x900": {"width": 1440, "height": 900},
    "mobile_390x844": {"width": 390, "height": 844},
}

SEVEN_PORTAL_PATHS = (
    "/dashboard",
    "/member",
    "/advisor?role=F2-H",
    "/admin/tech?tier=T1",
    "/lineage/house/1",
    "/community",
    "/companion",
)


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
    with tempfile.TemporaryDirectory(prefix="pdeue_pr80_e2e_") as tmp_dir:
        db_path = Path(tmp_dir) / "pdeue_pr80_e2e.db"
        mutex_path = Path(tmp_dir) / "pdeue_pr80_mutex.sqlite3"
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
        "all_requests": [],
    }

    def _intercept(route: Any) -> None:
        url = route.request.url
        parsed = urlparse(url)
        diagnostics["all_requests"].append(url)
        if parsed.scheme in {"data", "blob", "about"} or parsed.netloc == base_host:
            route.continue_()
            return
        if parsed.hostname == "meet.jit.si":
            route.fulfill(status=200, content_type="text/html", body="<html><body>Offline Jitsi Stub</body></html>")
            return
        diagnostics["external_cdn_requests"].append(url)
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


def _assert_hygiene_and_zero_overflow(page: Any, diagnostics: dict[str, list[Any]], route_label: str) -> None:
    audit = page.evaluate(
        """() => {
            const overflowPx = Math.round(document.documentElement.scrollWidth - window.innerWidth);
            const cdnTags = [];
            for (const el of document.querySelectorAll('script[src], link[href]')) {
                const raw = el.getAttribute('src') || el.getAttribute('href') || '';
                if (/^https?:\\/\\//i.test(raw)) cdnTags.push(raw);
            }
            return { overflowPx, cdnTags };
        }"""
    )
    assert audit["overflowPx"] <= 1, f"Horizontal overflow on {route_label}: {audit['overflowPx']}px"
    assert audit["cdnTags"] == [], f"External CDN tags on {route_label}: {audit['cdnTags']}"
    assert diagnostics["external_cdn_requests"] == [], f"External CDN requests on {route_label}: {diagnostics['external_cdn_requests']}"
    assert diagnostics["console_errors"] == [], f"Console errors on {route_label}: {diagnostics['console_errors']}"
    assert diagnostics["page_errors"] == [], f"Page errors on {route_label}: {diagnostics['page_errors']}"
    assert diagnostics["failed_requests"] == [], f"Failed HTTP requests on {route_label}: {diagnostics['failed_requests']}"


@pytest.mark.parametrize("vp_name,vp_size", list(VIEWPORTS.items()))
def test_pr80_twin_crests_brand_lockup_and_footer_across_all_seven_portals(
    live_server: str,
    browser: Any,
    vp_name: str,
    vp_size: dict[str, int],
) -> None:
    context, page, diagnostics = _create_monitored_page(browser, live_server, vp_size)
    try:
        for path in SEVEN_PORTAL_PATHS:
            resp = page.goto(f"{live_server}{path}", wait_until="networkidle")
            assert resp is not None and resp.status == 200
            page.wait_for_timeout(200)

            lockup = page.locator("a.brand-lockup").first
            assert lockup.is_visible(), f"Brand lockup not visible on {path} ({vp_name})"
            assert lockup.get_attribute("href") == "/community/heritage"
            assert lockup.get_attribute("data-heritage-target") == "/community/heritage"
            lockup_text = lockup.inner_text()
            assert "FUTURE · CARMICHAEL — McCORMICK" in lockup_text
            assert "Generational Love, Harmony, Resilience, and Wealth" in lockup_text

            crest_info = page.evaluate(
                """() => Array.from(document.querySelectorAll('a.brand-lockup img.brand-crest')).map(img => {
                    const r = img.getBoundingClientRect();
                    return {
                        src: img.getAttribute('src') || '',
                        complete: img.complete,
                        naturalWidth: img.naturalWidth,
                        naturalHeight: img.naturalHeight,
                        width: Math.round(r.width),
                        height: Math.round(r.height),
                    };
                })"""
            )
            assert len(crest_info) == 2, f"Expected 2 twin crest images on {path}, got {crest_info}"
            assert crest_info[0]["src"].endswith("carmichael_crest.svg")
            assert crest_info[1]["src"].endswith("mccormick_crest.svg")
            for c in crest_info:
                assert c["complete"] is True and c["naturalWidth"] > 0 and c["naturalHeight"] > 0, (
                    f"Broken crest image on {path}: {c}"
                )
                assert c["width"] == 40 and c["height"] == 46, f"Crest size mismatch on {path}: {c}"

            footer = page.locator("footer.pdeue-colophon").first
            assert footer.is_visible(), f"Footer colophon not visible on {path}"
            assert "Powered by CARM Aerotech Corporation" in footer.inner_text()
            assert page.locator("footer.pdeue-colophon .colophon-mode-badge").first.is_visible()

            _assert_hygiene_and_zero_overflow(page, diagnostics, f"{path} ({vp_name})")

        page.goto(f"{live_server}/dashboard", wait_until="networkidle")
        page.screenshot(path=str(SCREENSHOTS_DIR / f"pr80_dashboard_brand_{vp_name}.png"), full_page=True)
        page.goto(f"{live_server}/member", wait_until="networkidle")
        page.screenshot(path=str(SCREENSHOTS_DIR / f"pr80_member_brand_{vp_name}.png"), full_page=True)
    finally:
        context.close()


@pytest.mark.parametrize("vp_name,vp_size", list(VIEWPORTS.items()))
def test_pr80_non_admin_tier_hardening_and_chief_admin_inspection_e2e(
    live_server: str,
    browser: Any,
    vp_name: str,
    vp_size: dict[str, int],
) -> None:
    context, page, diagnostics = _create_monitored_page(browser, live_server, vp_size)
    try:
        # Non-admin /advisor?role=F1 -> zero cross-tier pills in DOM
        page.goto(f"{live_server}/advisor?role=F1", wait_until="networkidle")
        page.wait_for_timeout(200)
        assert page.locator("#role-switcher").count() == 0
        assert page.locator("button[data-role]").count() == 0
        assert "F1_PEER_GUIDE" in page.locator("#active-hat-text").inner_text()
        page.screenshot(path=str(SCREENSHOTS_DIR / f"pr80_advisor_f1_hardened_{vp_name}.png"), full_page=True)
        _assert_hygiene_and_zero_overflow(page, diagnostics, f"/advisor?role=F1 ({vp_name})")

        # Non-admin /admin/tech?tier=T1 -> zero cross-tier pills in DOM
        page.goto(f"{live_server}/admin/tech?tier=T1", wait_until="networkidle")
        page.wait_for_timeout(200)
        assert page.locator("#tier-switcher").count() == 0
        assert page.locator("button[data-tier]").count() == 0
        assert "T1_MONITOR" in page.locator("#active-hat").inner_text()
        page.screenshot(path=str(SCREENSHOTS_DIR / f"pr80_tech_t1_hardened_{vp_name}.png"), full_page=True)
        _assert_hygiene_and_zero_overflow(page, diagnostics, f"/admin/tech?tier=T1 ({vp_name})")

        # Chief Admin Supervisory Audit Lens retains multi-tier switcher on both portals
        page.goto(f"{live_server}/advisor?role=F1&supervisory=1&inspector=CHIEF_ADMIN", wait_until="networkidle")
        page.wait_for_timeout(200)
        assert page.locator("#role-switcher").is_visible()
        assert page.locator("button[data-role]").count() == 4
        assert page.locator("#supervisoryAuditLensBanner").is_visible()
        _assert_hygiene_and_zero_overflow(page, diagnostics, f"/advisor supervisory ({vp_name})")

        page.goto(f"{live_server}/admin/tech?tier=T1&supervisory=1&inspector=CHIEF_ADMIN", wait_until="networkidle")
        page.wait_for_timeout(200)
        assert page.locator("#tier-switcher").is_visible()
        assert page.locator("button[data-tier]").count() == 4
        assert page.locator("#supervisoryAuditLensBanner").is_visible()
        _assert_hygiene_and_zero_overflow(page, diagnostics, f"/admin/tech supervisory ({vp_name})")
    finally:
        context.close()


@pytest.mark.parametrize("vp_name,vp_size", list(VIEWPORTS.items()))
def test_pr80_companion_compact_title_hierarchy_and_glossary_two_layer_e2e(
    live_server: str,
    browser: Any,
    vp_name: str,
    vp_size: dict[str, int],
) -> None:
    context, page, diagnostics = _create_monitored_page(browser, live_server, vp_size)
    try:
        # 1. PDEUE University (/companion) compact title & heading hierarchy
        page.goto(f"{live_server}/companion", wait_until="networkidle")
        page.wait_for_timeout(250)
        metrics = page.evaluate(
            """() => {
                const h1 = document.querySelector('header h1');
                const h2 = document.querySelector('#chapter-waterfall h2');
                const h1Style = window.getComputedStyle(h1);
                const h2Style = window.getComputedStyle(h2);
                const h1Rect = h1.getBoundingClientRect();
                const h2Rect = h2.getBoundingClientRect();
                return {
                    h1FontSizePx: parseFloat(h1Style.fontSize),
                    h2FontSizePx: parseFloat(h2Style.fontSize),
                    h1Bottom: Math.round(h1Rect.bottom),
                    h2Bottom: Math.round(h2Rect.bottom),
                    viewportHeight: window.innerHeight,
                };
            }"""
        )
        assert 19.0 <= metrics["h1FontSizePx"] <= 29.0, f"Unexpected /companion H1 size ({vp_name}): {metrics}"
        assert metrics["h2FontSizePx"] < metrics["h1FontSizePx"], f"H2 must be smaller than H1: {metrics}"
        if vp_name == "desktop_1440x900":
            assert metrics["h1Bottom"] < 320, f"Hero H1 sits too low on desktop: {metrics}"
            assert metrics["h2Bottom"] <= metrics["viewportHeight"], (
                f"Chapter 1 heading should sit above the fold on desktop 1440x900: {metrics}"
            )
        page.screenshot(path=str(SCREENSHOTS_DIR / f"pr80_companion_compact_{vp_name}.png"), full_page=True)
        _assert_hygiene_and_zero_overflow(page, diagnostics, f"/companion ({vp_name})")

        # 2. Two-Layer Glossary Drawer on /member & /dashboard (plain_english default + collapsible Technical & Governance Spec)
        for route in ("/member", "/dashboard"):
            page.goto(f"{live_server}{route}", wait_until="networkidle")
            page.wait_for_timeout(250)

            page.locator("#openGlossaryBtn").click()
            drawer = page.locator("#glossaryDrawer")
            drawer.wait_for(state="visible")

            req_before = len(diagnostics["all_requests"])
            page.locator("#glossarySearchInput").fill("IFAS")
            page.wait_for_timeout(120)

            ifas_card = page.locator('.glossary-item[data-term-id="ifas"]')
            assert ifas_card.is_visible(), f"Dedicated IFAS card missing in Glossary Drawer on {route}"
            plain_p = ifas_card.locator(".glossary-plain-english")
            assert plain_p.is_visible()
            plain_text = plain_p.inner_text()
            assert "separate, dedicated banking and bookkeeping home" in plain_text.lower()
            assert "hmac-sha256" not in plain_text.lower()
            assert "json-ld" not in plain_text.lower()

            details = ifas_card.locator("details.glossary-tech-details")
            assert details.count() == 1
            assert details.get_attribute("open") is None, "Technical & Governance Spec must start collapsed"
            summary = details.locator("summary")
            assert "Technical & Governance Spec" in summary.inner_text()
            summary.click()
            page.wait_for_timeout(100)
            assert details.get_attribute("open") is not None
            tech_body = details.locator(".glossary-tech-body").inner_text()
            assert "HMAC-SHA256" in tech_body and "accounting.narratix.io" in tech_body

            glossary_net = [u for u in diagnostics["all_requests"][req_before:] if "/glossary" in u]
            assert glossary_net == [], f"Unexpected glossary network call during search: {glossary_net}"

            if vp_name == "desktop_1440x900" and route == "/member":
                page.screenshot(path=str(SCREENSHOTS_DIR / f"pr80_glossary_two_layer_{vp_name}.png"), full_page=True)
            page.locator("#closeGlossaryBtn").click()
            _assert_hygiene_and_zero_overflow(page, diagnostics, f"{route} glossary ({vp_name})")
    finally:
        context.close()
