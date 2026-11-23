"""Milestones C2-C5 — Playwright E2E Role-Matrix, Active-Hat & Directive R-12 Verification.

Verifies across desktop (1440x900) and mobile (390x844) against a live FastAPI server
in fail-closed ``paper`` mode:
  - C2: Directive R-06 Active-Hat confirmation gateway (/dashboard <-> /member) + audit trail
  - C3: Founder Sovereign Immune badge + Supervisory Audit Lens amber banner & read-only lock
  - C4: Class T sub-tier DOM stripping (T1, T2, T2-Household, T3) + R-12 masking + CA Override & Revoke
  - C5: Class F sub-tier DOM separation (F1, F2-H, F2-A, F3) + Directive R-04 Halt & Dual-Sig modal

Asserts 0 console errors, 0 uncaught page errors, 0 failed HTTP requests, 0 external CDN
tags/requests, and 0 cross-role navigation bleed on every portal surface.
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
    reason="Playwright is required for E2E role-matrix tests",
)
sync_playwright = playwright_sync.sync_playwright

pytestmark = pytest.mark.e2e

REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_DIR = REPO_ROOT / "backend"
SCREENSHOTS_DIR = REPO_ROOT / "artifacts" / "playwright_screenshots" / "c2_c5_role_matrix"

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
    with tempfile.TemporaryDirectory(prefix="pdeue_c2_c5_e2e_") as tmp_dir:
        db_path = Path(tmp_dir) / "pdeue_c2_c5_e2e.db"
        mutex_path = Path(tmp_dir) / "pdeue_c2_c5_mutex.sqlite3"
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
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        launched = p.chromium.launch(headless=True)
        try:
            yield launched
        finally:
            launched.close()


def _create_monitored_page(browser: Any, base_url: str, viewport: dict[str, int]):
    base_host = urlparse(base_url).netloc
    diagnostics: dict[str, list[Any]] = {
        "console_errors": [],
        "page_errors": [],
        "failed_requests": [],
        "external_cdn_requests": [],
    }
    context = browser.new_context(viewport=viewport)

    def _intercept(route: Any) -> None:
        url = route.request.url
        parsed = urlparse(url)
        if parsed.scheme in {"data", "blob", "about"} or parsed.netloc == base_host:
            route.continue_()
            return
        diagnostics["external_cdn_requests"].append({"url": url, "type": route.request.resource_type})
        route.abort("blockedbyclient")

    context.route("**/*", _intercept)
    page = context.new_page()
    page.set_default_timeout(15000)

    page.on(
        "console",
        lambda msg: diagnostics["console_errors"].append(msg.text) if msg.type == "error" else None,
    )
    page.on("pageerror", lambda err: diagnostics["page_errors"].append(str(err)))
    page.on(
        "response",
        lambda resp: diagnostics["failed_requests"].append({"status": resp.status, "url": resp.url})
        if resp.status >= 400
        else None,
    )
    page.on(
        "requestfailed",
        lambda req: diagnostics["failed_requests"].append({"status": 0, "url": req.url, "failure": req.failure})
        if urlparse(req.url).netloc == base_host
        and not (req.failure and "ERR_ABORTED" in str(req.failure))
        else None,
    )
    return context, page, diagnostics


def _assert_hygiene_and_siloing(
    page: Any,
    diagnostics: dict[str, list[Any]],
    *,
    forbidden_href_prefixes: tuple[str, ...] = (),
) -> None:
    dom_audit = page.evaluate(
        """() => {
            const isVisible = (el) => {
                if (!el) return false;
                if (el.closest('[hidden]')) return false;
                const s = window.getComputedStyle(el);
                if (s.display === 'none' || s.visibility === 'hidden' || s.opacity === '0') return false;
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
            };
            const cdnTags = [];
            for (const el of document.querySelectorAll('script[src], link[href]')) {
                const raw = el.getAttribute('src') || el.getAttribute('href') || '';
                if (/^https?:\\/\\//i.test(raw)) cdnTags.push({ tag: el.tagName.toLowerCase(), url: raw });
            }
            const visibleLinks = [];
            for (const a of document.querySelectorAll('a[href]')) {
                if (isVisible(a)) visibleLinks.push({ href: a.getAttribute('href') || '', text: (a.textContent || '').trim() });
            }
            const legacyHub = document.getElementById('legacyPortalHub');
            return { cdnTags, visibleLinks, legacyHubVisible: legacyHub ? isVisible(legacyHub) : false };
        }"""
    )
    assert dom_audit["cdnTags"] == [], f"External CDN tags detected: {dom_audit['cdnTags']}"
    assert not dom_audit["legacyHubVisible"], "Hidden #legacyPortalHub must never be visible"
    for link in dom_audit["visibleLinks"]:
        path = urlparse(link["href"]).path
        for forbidden in forbidden_href_prefixes:
            assert not (path == forbidden or path.startswith(f"{forbidden}/")), (
                f"Cross-role nav bleed: visible link {link!r} matched forbidden {forbidden!r}"
            )
    assert diagnostics["console_errors"] == [], f"Console errors: {diagnostics['console_errors']}"
    assert diagnostics["page_errors"] == [], f"Page errors: {diagnostics['page_errors']}"
    assert diagnostics["failed_requests"] == [], f"Failed HTTP requests: {diagnostics['failed_requests']}"
    assert diagnostics["external_cdn_requests"] == [], f"External CDN requests: {diagnostics['external_cdn_requests']}"


@pytest.mark.parametrize("vp_name,vp_size", list(VIEWPORTS.items()))
def test_c2_c3_active_hat_switch_and_supervisory_audit_lens_e2e(
    live_server: str,
    browser: Any,
    vp_name: str,
    vp_size: dict[str, int],
) -> None:
    context, page, diagnostics = _create_monitored_page(browser, live_server, vp_size)
    try:
        # 1. Load /dashboard -> verify Active-Hat pill + Founder Sovereign Immune on Tab 2
        resp = page.goto(f"{live_server}/dashboard", wait_until="networkidle")
        assert resp is not None and resp.status == 200
        assert "Active Hat: CHIEF_ADMIN" in page.locator("#activeHatBadge").inner_text()
        page.locator("#tab-btn-2").click()
        page.wait_for_timeout(300)
        assert "Sovereign Immune" in page.locator("#lineage-house-tree").inner_text()

        # 2. C2: Click Switch Active Hat -> confirm gateway -> lands on /member with audited hat switch
        page.locator("#openHatSwitchBtn").click()
        page.locator("#hat-switch-modal").wait_for(state="visible")
        page.screenshot(path=str(SCREENSHOTS_DIR / f"c2_hat_switch_modal_{vp_name}.png"), full_page=True)
        with page.expect_navigation(wait_until="networkidle"):
            page.locator("#confirmHatSwitchBtn").click()
        page.wait_for_timeout(300)
        assert "/member" in page.url and "hat_switch=AUD-" in page.url
        assert page.locator("#memberSwitchHatBtn").is_visible()
        _assert_hygiene_and_siloing(
            page,
            diagnostics,
            forbidden_href_prefixes=("/dashboard", "/advisor", "/admin/tech", "/lineage/house"),
        )

        # 3. C2: Switch back intentionally to CHIEF_ADMINISTRATOR via confirmation modal
        page.locator("#memberSwitchHatBtn").click()
        page.locator("#member-hat-switch-modal").wait_for(state="visible")
        with page.expect_navigation(wait_until="networkidle"):
            page.locator("#confirmMemberHatSwitchBtn").click()
        page.wait_for_timeout(250)
        assert "/dashboard" in page.url

        # Verify audit events recorded server-side
        status, body = _http_request(f"{live_server}/api/v1/portal/active-hat/audit")
        assert status == 200
        events = json.loads(body)["events"]
        assert len(events) >= 2

        # 4. C3: Supervisory Audit Lens on subordinate /member view
        resp = page.goto(
            f"{live_server}/member?scma_id=SCMA-ELEANOR_-B2B31C9E&supervisory=1&inspector=CHIEF_ADMIN",
            wait_until="networkidle",
        )
        assert resp is not None and resp.status == 200
        page.wait_for_timeout(300)
        banner = page.locator("#supervisoryAuditLensBanner")
        assert banner.is_visible()
        assert "SUPERVISORY AUDIT LENS — READ-ONLY INSPECTION" in banner.inner_text()
        page.locator("#tabBtnEngine").click()
        page.wait_for_timeout(200)
        assert page.locator("#riskSlider").is_disabled()
        assert page.locator("#saveRiskBtn").is_disabled()
        assert page.locator("#distributionBtn").is_disabled()
        page.screenshot(path=str(SCREENSHOTS_DIR / f"c3_supervisory_audit_lens_{vp_name}.png"), full_page=True)
        _assert_hygiene_and_siloing(
            page,
            diagnostics,
            forbidden_href_prefixes=("/dashboard", "/advisor", "/admin/tech", "/lineage/house"),
        )
    finally:
        context.close()


@pytest.mark.parametrize("vp_name,vp_size", list(VIEWPORTS.items()))
def test_c4_class_t_role_matrix_and_r12_masking_e2e(
    live_server: str,
    browser: Any,
    vp_name: str,
    vp_size: dict[str, int],
) -> None:
    context, page, diagnostics = _create_monitored_page(browser, live_server, vp_size)
    forbidden = ("/dashboard", "/member", "/advisor", "/lineage/house")
    try:
        # T1: Read-only; daemon triggers & CA override hidden; R-12 masked
        resp = page.goto(f"{live_server}/admin/tech?tier=T1", wait_until="networkidle")
        assert resp is not None and resp.status == 200
        page.wait_for_timeout(250)
        assert "T1_MONITOR" in page.locator("#active-hat").inner_text()
        assert not page.locator("#trigger-daemon").is_visible()
        assert not page.locator("#trigger-settlement").is_visible()
        assert not page.locator("#grant").is_visible()
        orders_t1 = page.locator("#resting-orders-body").inner_text()
        assert "SCMA-MEM-****" in orders_t1 and "$****.**" in orders_t1
        assert "SCMA-ELEANOR" not in orders_t1
        _assert_hygiene_and_siloing(page, diagnostics, forbidden_href_prefixes=forbidden)

        # T2: Daemon triggers visible; CA override hidden; R-12 masked
        page.locator('button[data-tier="T2"]').click()
        page.wait_for_timeout(250)
        assert "T2_ENGINEER" in page.locator("#active-hat").inner_text()
        assert page.locator("#trigger-daemon").is_visible()
        assert page.locator("#trigger-settlement").is_visible()
        assert not page.locator("#grant").is_visible()
        orders_t2 = page.locator("#resting-orders-body").inner_text()
        assert "SCMA-MEM-****" in orders_t2 and "$****.**" in orders_t2

        # T2-Household: Household scope card visible; global triggers & CA override hidden; R-12 masked
        page.locator('button[data-tier="T2-HOUSEHOLD"]').click()
        page.wait_for_timeout(250)
        assert "T2_HOUSEHOLD_SCOPED" in page.locator("#active-hat").inner_text()
        assert page.locator("#household-scope-card").is_visible()
        assert "HOUSEHOLD-ALPHA" in page.locator("#household-scope-card").inner_text()
        assert not page.locator("#trigger-daemon").is_visible()
        assert not page.locator("#trigger-settlement").is_visible()
        assert not page.locator("#grant").is_visible()
        orders_t2h = page.locator("#resting-orders-body").inner_text()
        assert "SCMA-MEM-****" in orders_t2h and "$****.**" in orders_t2h
        page.screenshot(path=str(SCREENSHOTS_DIR / f"c4_tech_t2_household_{vp_name}.png"), full_page=True)

        # T3: Full tech triggers + CA Override modal + time-bounded unmask + revoke remasks
        page.locator('button[data-tier="T3"]').click()
        page.wait_for_timeout(250)
        assert "T3_CTO" in page.locator("#active-hat").inner_text()
        assert page.locator("#trigger-daemon").is_visible()
        assert page.locator("#grant").is_visible()
        assert page.locator("#zero-fin-badge").is_visible()
        assert "SCMA-MEM-****" in page.locator("#resting-orders-body").inner_text()

        page.locator("#grant").click()
        page.locator("#override-modal").wait_for(state="visible")
        page.locator("#override-token").fill("CA-OVERRIDE-SECRET-DEV")
        page.locator('#override-form button[type="submit"]').click()
        page.wait_for_timeout(300)
        assert page.locator("#grant-badge").is_visible()
        unmasked_text = page.locator("#resting-orders-body").inner_text()
        assert "SCMA-ELEANOR_-B2B31C9E" in unmasked_text and "$25.00" in unmasked_text
        page.screenshot(path=str(SCREENSHOTS_DIR / f"c4_tech_t3_unmasked_{vp_name}.png"), full_page=True)

        page.locator("#revoke").click()
        page.wait_for_timeout(300)
        remasked_text = page.locator("#resting-orders-body").inner_text()
        assert "SCMA-MEM-****" in remasked_text and "$****.**" in remasked_text
        _assert_hygiene_and_siloing(page, diagnostics, forbidden_href_prefixes=forbidden)
    finally:
        context.close()


@pytest.mark.parametrize("vp_name,vp_size", list(VIEWPORTS.items()))
def test_c5_class_f_role_matrix_and_dual_control_e2e(
    live_server: str,
    browser: Any,
    vp_name: str,
    vp_size: dict[str, int],
) -> None:
    context, page, diagnostics = _create_monitored_page(browser, live_server, vp_size)
    forbidden = ("/dashboard", "/member", "/admin/tech", "/lineage/house")
    try:
        # F1: Mentee guidance only; equity redacted; co-sign queue absent
        resp = page.goto(f"{live_server}/advisor?role=F1", wait_until="networkidle")
        assert resp is not None and resp.status == 200
        page.wait_for_timeout(300)
        assert "F1_PEER_GUIDE" in page.locator("#active-hat-text").inner_text()
        assert "EQUITY REDACTED ($****.**)" in page.locator("#equity").inner_text()
        assert page.locator("#distribution-card").count() == 0
        assert not page.locator("#cro-emergency-controls").is_visible()
        _assert_hygiene_and_siloing(page, diagnostics, forbidden_href_prefixes=forbidden)

        # F2-H: Domestic equity visible; custodial minor risk locks; Co-Sign button visible
        page.locator('button[data-role="F2-H"]').click()
        page.wait_for_timeout(300)
        assert "F2-H_HOUSEHOLD_HEAD" in page.locator("#active-hat-text").inner_text()
        assert "$5,850.00" in page.locator("#equity").inner_text()
        roster_text = page.locator("#roster").inner_text()
        assert "CUSTODIAL APPRENTICE" in roster_text
        assert "Risk dial locked — F2 co-sign required" in roster_text
        assert page.locator("[data-cosign]").count() >= 1
        assert not page.locator("#cro-emergency-controls").is_visible()
        page.screenshot(path=str(SCREENSHOTS_DIR / f"c5_advisor_f2h_{vp_name}.png"), full_page=True)

        # F2-A: Read-only audit queue; no Co-Sign buttons; household selector visible
        page.locator('button[data-role="F2-A"]').click()
        page.wait_for_timeout(300)
        assert "F2-A_LINEAGE_ADVISOR" in page.locator("#active-hat-text").inner_text()
        assert page.locator("#household-selector").is_visible()
        assert page.locator("[data-cosign]").count() == 0
        assert "READ-ONLY AUDIT: F2-H SIGNATURE REQUIRED" in page.locator("#distribution-slot").inner_text()
        assert not page.locator("#cro-emergency-controls").is_visible()

        # F3: Platform risk analytics + Directive R-04 Emergency Halt + Dual-Sig Override (CA-only resume)
        page.locator('button[data-role="F3"]').click()
        page.wait_for_timeout(350)
        assert "F3_CRO_RISK" in page.locator("#active-hat-text").inner_text()
        assert not page.locator("#metrics").is_visible()
        assert page.locator("#macro-risk").is_visible()
        assert page.locator("#cro-emergency-controls").is_visible()
        assert "CHIEF_ADMINISTRATOR_ONLY" in page.locator("#macro-risk").inner_text()

        # Engage Directive R-04 Halt from F3 CRO modal
        page.locator("#trigger-r04-halt-btn").click()
        page.locator("#r04-halt-modal").wait_for(state="visible")
        page.locator('#r04-halt-form button[type="submit"]').click()
        page.wait_for_timeout(350)
        assert "SYSTEM STATUS: HALTED" in page.locator("#macro-risk").inner_text()

        # Submit Dual-Signature Override from F3 CRO modal
        page.locator("#submit-dual-sig-btn").click()
        page.locator("#dual-sig-modal").wait_for(state="visible")
        page.locator('#dual-sig-form button[type="submit"]').click()
        page.wait_for_timeout(350)
        assert "PENDING_CHIEF_ADMIN_COUNTERSIGN" in page.locator("#dual-sig-list").inner_text()
        page.screenshot(path=str(SCREENSHOTS_DIR / f"c5_advisor_f3_cro_{vp_name}.png"), full_page=True)

        # Reset Directive R-04 back to NORMAL as Chief Admin via API so server stays clean
        status, _ = _http_request(
            f"{live_server}/api/v1/portal/advisor/emergency-resume?role=CHIEF_ADMINISTRATOR",
            method="POST",
            payload={"justification": "E2E teardown reset"},
        )
        assert status == 200
        _assert_hygiene_and_siloing(page, diagnostics, forbidden_href_prefixes=forbidden)
    finally:
        context.close()
