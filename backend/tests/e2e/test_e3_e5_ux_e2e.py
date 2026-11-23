"""Milestones E3-E5 Playwright E2E Verification Suite.

Verifies against the live FastAPI server (fail-closed paper mode, isolated temp SQLite):
- E3: Concentric Asset Rings SVG rendering, responsive compounding charts, zero horizontal
      overflow, and zero overlapping cards/tables across desktop (1440x900) and mobile (390x844).
- E4: Pure-CSS <abbr class="pdeue-term" data-tooltip="..."> hover tooltips + ⓘ indicators across
      all 5 portals (/member, /dashboard, /advisor, /admin/tech, /lineage/house/1) and
      zero-network client-side Glossary / Thesaurus Drawer search on /member & /dashboard.
- E5: Fail-closed ReadModelEnvelope UX banners & overlays for default QUALIFICATION_PENDING,
      live Directive R-04 TRADING_HALTED (+ Chief Admin resumption), and fault-injected
      DEGRADED_RETRYING offline/503 responses — proving zero fabricated placeholder numbers.
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
    reason="Playwright is required for E3-E5 E2E tests",
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
    headers: dict[str, str] | None = None,
    payload: dict[str, Any] | None = None,
    timeout: float = 5.0,
) -> tuple[int, str]:
    req_headers = dict(headers or {})
    body: bytes | None = None
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        req_headers.setdefault("Content-Type", "application/json")
    request = Request(url, data=body, headers=req_headers, method=method)
    try:
        with urlopen(request, timeout=timeout) as resp:
            return int(resp.status), resp.read().decode("utf-8", errors="replace")
    except HTTPError as err:
        return int(err.code), err.read().decode("utf-8", errors="replace")


@pytest.fixture(scope="module")
def live_server() -> str:
    port = _find_free_port()
    base_url = f"http://127.0.0.1:{port}"
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="pdeue_e3_e5_e2e_") as tmp_dir:
        db_path = Path(tmp_dir) / "pdeue_e3_e5.db"
        mutex_path = Path(tmp_dir) / "pdeue_e3_e5_mutex.sqlite3"
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
        diagnostics["external_cdn_requests"].append(req.url)
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


def _assert_layout_and_hygiene(page: Any, diagnostics: dict[str, list[Any]], *, allow_http_failures: bool = False) -> None:
    layout = page.evaluate(
        """() => {
            const docEl = document.documentElement;
            const overflowPx = Math.round(docEl.scrollWidth - window.innerWidth);
            const cdnTags = [];
            for (const el of document.querySelectorAll('script[src], link[href]')) {
                const raw = el.getAttribute('src') || el.getAttribute('href') || '';
                if (/^https?:\\/\\//i.test(raw)) cdnTags.push(raw);
            }
            const tableBoxes = [];
            for (const tc of document.querySelectorAll('.table-card, .table-wrap')) {
                const style = window.getComputedStyle(tc);
                if (tc.closest('[hidden]') || style.display === 'none' || style.visibility === 'hidden') continue;
                const r = tc.getBoundingClientRect();
                if (r.width > 0 && r.height > 0) {
                    tableBoxes.push({ top: r.top, bottom: r.bottom, left: r.left, right: r.right });
                }
            }
            const overlaps = [];
            for (let i = 0; i < tableBoxes.length; i++) {
                for (let j = i + 1; j < tableBoxes.length; j++) {
                    const a = tableBoxes[i], b = tableBoxes[j];
                    const horiz = a.left < b.right - 2 && b.left < a.right - 2;
                    const vert = a.top < b.bottom - 2 && b.top < a.bottom - 2;
                    if (horiz && vert) overlaps.push([i, j]);
                }
            }
            return { overflowPx, cdnTags, overlaps };
        }"""
    )
    assert layout["overflowPx"] <= 1, f"Horizontal overflow detected: {layout['overflowPx']}px"
    assert layout["overlaps"] == [], f"Overlapping table containers detected: {layout['overlaps']}"
    assert layout["cdnTags"] == [], f"External CDN DOM tags detected: {layout['cdnTags']}"
    assert diagnostics["external_cdn_requests"] == [], f"External CDN requests: {diagnostics['external_cdn_requests']}"
    assert diagnostics["page_errors"] == [], f"Uncaught JS errors: {diagnostics['page_errors']}"
    if not allow_http_failures:
        assert diagnostics["console_errors"] == [], f"Console errors: {diagnostics['console_errors']}"
        assert diagnostics["failed_requests"] == [], f"Failed HTTP requests: {diagnostics['failed_requests']}"


@pytest.mark.parametrize("vp_name,vp_size", list(VIEWPORTS.items()))
def test_e3_dashboard_and_member_concentric_rings_charts_and_zero_overflow(
    live_server: str,
    browser: Any,
    vp_name: str,
    vp_size: dict[str, int],
) -> None:
    """Milestone E3: Concentric Asset Rings SVG, compounding charts, zero overflow/overlap at desktop & mobile."""
    context, page, diagnostics = _create_monitored_page(browser, live_server, vp_size)
    try:
        # 1. Admin Cockpit (/dashboard)
        resp = page.goto(f"{live_server}/dashboard", wait_until="networkidle")
        assert resp is not None and resp.status == 200
        page.wait_for_timeout(350)

        rings_svg = page.locator("#dashboard-asset-rings-svg")
        assert rings_svg.is_visible()
        ring_box = rings_svg.bounding_box()
        assert ring_box is not None and ring_box["width"] >= 120 and ring_box["height"] >= 120
        assert page.locator("#dashboard-asset-rings-svg circle").count() >= 7
        assert "$" in page.locator("#dashLegendWorkingMargin").inner_text()
        assert "40%" in page.locator("#dashLegendDryPowder").inner_text()
        assert "10%/3%" in page.locator("#dashLegendWaterfall").inner_text()

        equity_svg = page.locator("#chart-equity")
        assert equity_svg.is_visible()
        eq_box = equity_svg.bounding_box()
        assert eq_box is not None and eq_box["width"] >= 200 and eq_box["height"] >= 60

        _assert_layout_and_hygiene(page, diagnostics)
        page.screenshot(path=str(SCREENSHOTS_DIR / f"e3_dashboard_tab1_{vp_name}.png"), full_page=True)

        # Verify Tabs 2, 3, 4 also have zero horizontal overflow & zero overlapping tables
        for tab_idx in (2, 3, 4):
            page.locator(f"#tab-btn-{tab_idx}").click()
            page.wait_for_timeout(350)
            _assert_layout_and_hygiene(page, diagnostics)

        # 2. Member Desktop (/member) — Orientation + Live Engine Concentric Asset Rings
        resp_m = page.goto(f"{live_server}/member", wait_until="networkidle")
        assert resp_m is not None and resp_m.status == 200
        page.wait_for_timeout(350)

        proj_svg = page.locator("#projectionCompareSvg")
        assert proj_svg.is_visible()
        proj_box = proj_svg.bounding_box()
        assert proj_box is not None and proj_box["width"] >= 200 and proj_box["height"] >= 80
        _assert_layout_and_hygiene(page, diagnostics)
        page.screenshot(path=str(SCREENSHOTS_DIR / f"e3_member_orientation_{vp_name}.png"), full_page=True)

        page.locator("#tabBtnEngine").click()
        page.wait_for_timeout(350)
        member_rings_svg = page.locator("#member-asset-rings-svg")
        assert member_rings_svg.is_visible()
        mr_box = member_rings_svg.bounding_box()
        assert mr_box is not None and mr_box["width"] >= 120 and mr_box["height"] >= 100
        assert page.locator("#member-asset-rings-svg circle").count() >= 7
        assert "40%" in page.locator("#legendDryPowder").inner_text()
        assert "87% / 10% / 3%" in page.locator("#legendWaterfall").inner_text()

        _assert_layout_and_hygiene(page, diagnostics)
        page.screenshot(path=str(SCREENSHOTS_DIR / f"e3_member_engine_{vp_name}.png"), full_page=True)
    finally:
        context.close()


def test_e4_pure_css_lexicon_tooltips_and_zero_network_glossary_drawer(
    live_server: str,
    browser: Any,
) -> None:
    """Milestone E4: Pure-CSS <abbr data-tooltip> + ⓘ across all 5 portals & zero-network Glossary Drawer search."""
    context, page, diagnostics = _create_monitored_page(browser, live_server, VIEWPORTS["desktop_1440x900"])
    try:
        # 1. Verify <abbr class="pdeue-term" data-tooltip> + ⓘ renders across all 5 portals
        for route in ("/member", "/dashboard", "/advisor", "/admin/tech", "/lineage/house/1"):
            resp = page.goto(f"{live_server}{route}", wait_until="networkidle")
            assert resp is not None and resp.status == 200
            page.wait_for_timeout(250)
            term = page.locator("abbr.pdeue-term[data-tooltip]").first
            assert term.count() == 1, f"Expected at least one visible .pdeue-term on {route}"
            assert "ⓘ" in term.inner_text()
            tooltip_attr = term.get_attribute("data-tooltip") or ""
            assert len(tooltip_attr) >= 20

            # Hover and verify pure-CSS ::after tooltip becomes visible with opacity 1
            term.hover()
            page.wait_for_timeout(200)
            pseudo = term.evaluate(
                """el => {
                    const cs = window.getComputedStyle(el, '::after');
                    return { opacity: cs.opacity, visibility: cs.visibility, content: cs.content };
                }"""
            )
            assert pseudo["visibility"] == "visible", f"Tooltip ::after not visible on hover for {route}: {pseudo}"
            assert float(pseudo["opacity"]) >= 0.9, f"Tooltip ::after opacity not active on {route}: {pseudo}"
            assert tooltip_attr[:20] in pseudo["content"]

        # 2. Verify Glossary / Thesaurus Drawer + instant zero-network client-side search on /member & /dashboard
        for route in ("/member", "/dashboard"):
            resp = page.goto(f"{live_server}{route}", wait_until="networkidle")
            assert resp is not None and resp.status == 200
            page.wait_for_timeout(300)

            page.locator("#openGlossaryBtn").click()
            drawer = page.locator("#glossaryDrawer")
            drawer.wait_for(state="visible")
            assert "Lexicon v0.5" in page.locator("#glossaryMatchCount").inner_text()

            # Snapshot request count — search & category filter MUST trigger zero network requests
            req_count_before = len(diagnostics["all_requests"])
            search_input = page.locator("#glossarySearchInput")
            search_input.fill("HWM")
            page.wait_for_timeout(120)
            assert "High-Water Mark / ADR-012" in page.locator("#glossaryResultsList").inner_text()

            search_input.fill("R-12")
            page.wait_for_timeout(120)
            assert "Directive R-12 Masking" in page.locator("#glossaryResultsList").inner_text()

            search_input.fill("")
            page.locator('#glossaryCategoryBar button[data-glossary-cat="Capital & Pools"]').click()
            page.wait_for_timeout(120)
            results_text = page.locator("#glossaryResultsList").inner_text()
            assert "SCMA" in results_text and "CFCP" in results_text and "FAEP" in results_text

            # Verify zero additional glossary fetches occurred during typing/filtering
            glossary_fetches_during_search = [
                u for u in diagnostics["all_requests"][req_count_before:] if "/glossary" in u
            ]
            assert glossary_fetches_during_search == [], (
                f"Glossary drawer search made unexpected network calls on {route}: {glossary_fetches_during_search}"
            )

            page.screenshot(path=str(SCREENSHOTS_DIR / f"e4_glossary_drawer_{route.strip('/')}.png"), full_page=True)
            page.locator("#closeGlossaryBtn").click()
            assert not drawer.is_visible()

        _assert_layout_and_hygiene(page, diagnostics)
    finally:
        context.close()


def test_e5_fail_closed_read_model_banners_halt_and_fault_injection(
    live_server: str,
    browser: Any,
) -> None:
    """Milestone E5: QUALIFICATION_PENDING default, live Directive R-04 TRADING_HALTED + CA resume, and 503 DEGRADED_RETRYING."""
    # Phase A: Default QUALIFICATION_PENDING + Live Directive R-04 TRADING_HALTED via Kill Switch modal + CA Resume
    context, page, diagnostics = _create_monitored_page(browser, live_server, VIEWPORTS["desktop_1440x900"])
    try:
        resp = page.goto(f"{live_server}/dashboard", wait_until="networkidle")
        assert resp is not None and resp.status == 200
        page.wait_for_timeout(350)

        banner = page.locator("#readModelStatusBanner")
        assert banner.is_visible()
        assert banner.get_attribute("data-rm-status") == "QUALIFICATION_PENDING"
        assert "NOT AVAILABLE — QUALIFICATION PENDING" in banner.inner_text()

        # Trigger Directive R-04 Halt using the accessible Kill Switch modal (zero native confirm/alert)
        page.locator("#emergencyKillSwitchBtn").click()
        page.locator("#kill-switch-modal").wait_for(state="visible")
        page.locator("#confirmKillSwitchExecuteBtn").click()
        page.wait_for_timeout(400)

        assert banner.get_attribute("data-rm-status") == "TRADING_HALTED"
        assert "TRADING HALTED — EXECUTIVE OVERRIDE" in banner.inner_text()
        assert page.locator("#dashboardHaltOverlay").is_visible()
        # Fail-closed: KPIs must render HALTED rather than stale/fabricated balances
        assert page.locator("#fnd-balance").inner_text().strip() == "HALTED"
        assert page.locator("#fnd-committed").inner_text().strip() == "HALTED"
        page.screenshot(path=str(SCREENSHOTS_DIR / "e5_dashboard_trading_halted.png"), full_page=True)

        # Verify /member also reflects TRADING HALTED fail-closed
        resp_m = page.goto(f"{live_server}/member", wait_until="networkidle")
        assert resp_m is not None and resp_m.status == 200
        page.wait_for_timeout(350)
        m_banner = page.locator("#readModelStatusBanner")
        assert m_banner.is_visible()
        assert m_banner.get_attribute("data-rm-status") == "TRADING_HALTED"
        assert "TRADING HALTED — EXECUTIVE OVERRIDE" in m_banner.inner_text()
        page.locator("#tabBtnEngine").click()
        page.wait_for_timeout(200)
        assert page.locator("#memberHaltOverlay").is_visible()
        assert page.locator("#totalWealth").inner_text().strip() == "HALTED"
        assert page.locator("#saveRiskBtn").is_disabled()
        page.screenshot(path=str(SCREENSHOTS_DIR / "e5_member_trading_halted.png"), full_page=True)

        # Resume as Chief Admin from /dashboard overlay so server state is restored cleanly
        page.goto(f"{live_server}/dashboard", wait_until="networkidle")
        page.wait_for_timeout(300)
        page.locator("#resumeFromHaltBtn").click()
        page.wait_for_timeout(400)
        assert page.locator("#readModelStatusBanner").get_attribute("data-rm-status") == "QUALIFICATION_PENDING"
        assert not page.locator("#dashboardHaltOverlay").is_visible()
        _assert_layout_and_hygiene(page, diagnostics)
    finally:
        # Guarantee R-04 is reset even on failure
        _http_request(
            f"{live_server}/api/v1/operator/emergency-resume",
            method="POST",
            headers={"X-Actor-Role": "CHIEF_ADMINISTRATOR"},
            payload={"justification": "E5 test teardown"},
        )
        context.close()

    # Phase B: Fault-injection (HTTP 503 on telemetry endpoints) -> DEGRADED_RETRYING with ZERO fabricated numbers
    fault_ctx, fault_page, fault_diag = _create_monitored_page(browser, live_server, VIEWPORTS["desktop_1440x900"])
    try:
        fault_page.route(
            "**/api/v1/operator/workspace-state*",
            lambda route: route.fulfill(
                status=503,
                content_type="application/json",
                body=json.dumps({"detail": "Engine telemetry unreachable (fault injection)"}),
            ),
        )
        fault_page.route(
            "**/api/v1/portal/member/state*",
            lambda route: route.fulfill(
                status=503,
                content_type="application/json",
                body=json.dumps({"detail": "Member read model unreachable (fault injection)"}),
            ),
        )

        fault_page.goto(f"{live_server}/dashboard", wait_until="networkidle")
        fault_page.wait_for_timeout(350)
        d_banner = fault_page.locator("#readModelStatusBanner")
        assert d_banner.is_visible()
        assert d_banner.get_attribute("data-rm-status") == "DEGRADED_RETRYING"
        assert "UNAVAILABLE — ENGINE UNREACHABLE" in d_banner.inner_text()
        assert fault_page.locator("#fnd-balance").inner_text().strip() == "UNAVAILABLE"
        assert "$4,250.00" not in fault_page.locator("#fnd-balance").inner_text()
        fault_page.screenshot(path=str(SCREENSHOTS_DIR / "e5_dashboard_degraded_503.png"), full_page=True)
        _assert_layout_and_hygiene(fault_page, fault_diag, allow_http_failures=True)

        fault_page.goto(f"{live_server}/member", wait_until="networkidle")
        fault_page.wait_for_timeout(350)
        m_banner = fault_page.locator("#readModelStatusBanner")
        assert m_banner.is_visible()
        assert m_banner.get_attribute("data-rm-status") == "DEGRADED_RETRYING"
        assert "UNAVAILABLE — ENGINE UNREACHABLE" in m_banner.inner_text()
        fault_page.locator("#tabBtnEngine").click()
        fault_page.wait_for_timeout(200)
        assert fault_page.locator("#totalWealth").inner_text().strip() == "UNAVAILABLE"
        fault_page.screenshot(path=str(SCREENSHOTS_DIR / "e5_member_degraded_503.png"), full_page=True)
        _assert_layout_and_hygiene(fault_page, fault_diag, allow_http_failures=True)
    finally:
        fault_ctx.close()
