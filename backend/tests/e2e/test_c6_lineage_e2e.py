"""Milestone C6 — Playwright E2E Verification for 12-House Lineage Governance,
3-Stage Dormant Bicameral Veto Engine, Configurable Enclave Bodies/Seats & Open-Study Doctrine.

Verifies across desktop (1440x900) and mobile (390x844) against a live FastAPI server
in fail-closed ``paper`` mode with an isolated temporary SQLite database:
  1. Default Stage 1 EXECUTIVE_COMMAND DOM state on /lineage/house/1 (voting buttons stripped, calm badge rendered)
  2. Strict H1 vs H2 desk isolation, Directive R-12 '$****.**' masking, Founder Sovereign Immune badge, cross-house 403
  3. /dashboard Tab 4 3-Stage Governance Mode switcher + Configurable Enclave Body & Named Voter Seat Registry UI
  4. Stage 3 Bicameral Veto flow on /lineage/house/1 + 1-Click SHTF Snap-Back back to EXECUTIVE_COMMAND
  5. /companion Chapter 6 Open-Study Three-Stage Governance Lifecycle & FUTURE Enclave Charter

Asserts 0 console errors, 0 uncaught page errors, 0 failed HTTP requests, 0 external CDN
tags/requests, and 0 cross-role navigation bleed.
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
    reason="Playwright is required for E2E C6 lineage tests",
)
sync_playwright = playwright_sync.sync_playwright

pytestmark = pytest.mark.e2e

REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_DIR = REPO_ROOT / "backend"
SCREENSHOTS_DIR = REPO_ROOT / "artifacts" / "playwright_screenshots" / "c6_lineage_governance"

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
    req = Request(url, data=body, headers=req_headers, method=method)
    try:
        with urlopen(req, timeout=timeout) as resp:
            return int(resp.status), resp.read().decode("utf-8", errors="replace")
    except HTTPError as err:
        return int(err.code), err.read().decode("utf-8", errors="replace")


@pytest.fixture(scope="module")
def live_server() -> str:
    port = _find_free_port()
    base_url = f"http://127.0.0.1:{port}"
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="pdeue_c6_e2e_") as tmp_dir:
        db_path = Path(tmp_dir) / "pdeue_c6_e2e.db"
        mutex_path = Path(tmp_dir) / "pdeue_c6_mutex.sqlite3"
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


def _attach_strict_auditors(context: Any, page: Any, base_host: str) -> dict[str, list[Any]]:
    audit: dict[str, list[Any]] = {
        "console_errors": [],
        "page_errors": [],
        "failed_requests": [],
        "external_cdn": [],
    }

    def _intercept(route: Any) -> None:
        url = route.request.url
        parsed = urlparse(url)
        if parsed.scheme in {"data", "blob", "about"} or parsed.netloc == base_host:
            route.continue_()
            return
        audit["external_cdn"].append({"url": url, "type": route.request.resource_type})
        route.abort("blockedbyclient")

    context.route("**/*", _intercept)
    page.on("console", lambda m: audit["console_errors"].append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: audit["page_errors"].append(str(e)))
    page.on(
        "response",
        lambda r: audit["failed_requests"].append({"status": r.status, "url": r.url})
        if r.status >= 400
        else None,
    )
    return audit


def _assert_zero_errors_and_zero_cdn(page: Any, audit: dict[str, list[Any]], *, forbidden_prefixes: tuple[str, ...] = ()) -> None:
    dom_audit = page.evaluate(
        """() => {
            const cdn = [];
            for (const el of document.querySelectorAll('script[src], link[href]')) {
                const raw = el.getAttribute('src') || el.getAttribute('href') || '';
                if (/^https?:\\/\\//i.test(raw)) cdn.push(raw);
            }
            const visibleLinks = [];
            for (const a of document.querySelectorAll('a[href]')) {
                const st = window.getComputedStyle(a);
                const rect = a.getBoundingClientRect();
                if (!a.closest('[hidden]') && st.display !== 'none' && st.visibility !== 'hidden' && rect.width > 0 && rect.height > 0) {
                    visibleLinks.push(a.getAttribute('href') || '');
                }
            }
            return { cdn, visibleLinks };
        }"""
    )
    assert dom_audit["cdn"] == [], f"External CDN tags found in DOM: {dom_audit['cdn']}"
    assert audit["external_cdn"] == [], f"External CDN requests found: {audit['external_cdn']}"
    assert audit["console_errors"] == [], f"Console errors: {audit['console_errors']}"
    assert audit["page_errors"] == [], f"Page errors: {audit['page_errors']}"
    assert audit["failed_requests"] == [], f"Failed HTTP requests: {audit['failed_requests']}"
    for href in dom_audit["visibleLinks"]:
        path = urlparse(href).path
        for forbidden in forbidden_prefixes:
            assert not (path == forbidden or path.startswith(f"{forbidden}/")), (
                f"Cross-role nav bleed: {href!r} matches forbidden {forbidden!r}"
            )


@pytest.mark.parametrize("vp_name,vp_size", list(VIEWPORTS.items()))
def test_c6_default_executive_command_and_h1_vs_h2_isolation(
    live_server: str,
    browser: Any,
    vp_name: str,
    vp_size: dict[str, int],
) -> None:
    """Verify default Stage 1 EXECUTIVE_COMMAND strips voting buttons and H1 masks balances ($****.**)."""
    base_host = urlparse(live_server).netloc

    # 1. H2 Sovereign Desk in default EXECUTIVE_COMMAND
    ctx_h2 = browser.new_context(viewport=vp_size)
    try:
        page = ctx_h2.new_page()
        audit = _attach_strict_auditors(ctx_h2, page, base_host)
        resp = page.goto(f"{live_server}/lineage/house/1?role=H2", wait_until="networkidle", timeout=15000)
        assert resp is not None and resp.status == 200
        body_text = page.inner_text("body")
        assert "Executive Command Mode Active — Voting Dormant" in body_text
        assert "Sovereign Immune" in body_text
        assert page.locator("#vote-aye").count() == 0
        assert page.locator("#vote-nay").count() == 0
        assert page.locator("#vote-veto").count() == 0
        assert page.locator("button.freeze").count() >= 1
        page.screenshot(path=str(SCREENSHOTS_DIR / f"c6_house1_h2_executive_command_{vp_name}.png"), full_page=True)
        _assert_zero_errors_and_zero_cdn(
            page, audit, forbidden_prefixes=("/dashboard", "/member", "/advisor", "/admin/tech")
        )
    finally:
        ctx_h2.close()

    # 2. H1 Secretarial Desk: Directive R-12 masking + zero breakers/voting
    ctx_h1 = browser.new_context(viewport=vp_size)
    try:
        page = ctx_h1.new_page()
        audit = _attach_strict_auditors(ctx_h1, page, base_host)
        resp = page.goto(f"{live_server}/lineage/house/1?role=H1", wait_until="networkidle", timeout=15000)
        assert resp is not None and resp.status == 200
        body_text = page.inner_text("body")
        assert "$****.**" in body_text
        assert "$5,000.00" not in body_text
        assert "$1,250.00" not in body_text
        assert "NON-VOTING AUDIT" in body_text
        assert "Meeting Scheduler Log" in body_text
        assert page.locator("button.freeze").count() == 0
        assert page.locator("button.cancel").count() == 0
        assert page.locator("#vote-aye").count() == 0
        assert page.locator("#vote-veto").count() == 0
        page.screenshot(path=str(SCREENSHOTS_DIR / f"c6_house1_h1_r12_masked_{vp_name}.png"), full_page=True)
        _assert_zero_errors_and_zero_cdn(
            page, audit, forbidden_prefixes=("/dashboard", "/member", "/advisor", "/admin/tech")
        )
    finally:
        ctx_h1.close()

    # 3. Cross-House browser navigation returns HTTP 403
    ctx_403 = browser.new_context(viewport=vp_size)
    try:
        page = ctx_403.new_page()
        resp = page.goto(f"{live_server}/lineage/house/1?actor_house_id=2", timeout=10000)
        assert resp is not None and resp.status == 403
    finally:
        ctx_403.close()


@pytest.mark.parametrize("vp_name,vp_size", list(VIEWPORTS.items()))
def test_c6_dashboard_tab4_enclave_registry_stage3_veto_and_shtf_snapback(
    live_server: str,
    browser: Any,
    vp_name: str,
    vp_size: dict[str, int],
) -> None:
    """Verify Tab 4 mode switch, custom enclave body/named voter creation, Stage 3 veto, and 1-click SHTF snap-back."""
    base_host = urlparse(live_server).netloc
    suffix = "DESKTOP" if "desktop" in vp_name else "MOBILE"

    ctx = browser.new_context(viewport=vp_size)
    try:
        page = ctx.new_page()
        audit = _attach_strict_auditors(ctx, page, base_host)

        # 1. Open /dashboard Tab 4
        resp = page.goto(f"{live_server}/dashboard", wait_until="networkidle", timeout=15000)
        assert resp is not None and resp.status == 200
        page.locator("#tab-btn-4").click()
        page.wait_for_timeout(350)
        assert "MODE: EXECUTIVE_COMMAND" in page.locator("#gov-mode-badge").inner_text()

        # 2. Create custom communal enclave body via Tab 4 UI
        body_name = f"Council of Elders {suffix}"
        page.locator("#new-body-name").fill(body_name)
        page.locator("#new-body-quorum-num").fill("2")
        page.locator("#new-body-quorum-den").fill("3")
        page.locator("#new-body-veto-threshold").fill("2")
        page.locator("#btn-create-body").click()
        page.wait_for_timeout(450)
        assert body_name in page.locator("#enclave-bodies-tbody").inner_text()

        # 3. Grant a specific named-individual voter seat with Stage 3 veto right
        page.locator("#seat-type-select").select_option("NAMED_INDIVIDUAL")
        page.locator("#seat-user-id").fill(f"USR-ELDER-{suffix}-01")
        page.locator("#seat-display-name").fill(f"Elder Margaret {suffix}")
        page.locator("#btn-grant-seat").click()
        page.wait_for_timeout(450)
        assert f"Elder Margaret {suffix}" in page.locator("#enclave-seats-tbody").inner_text()

        # 4. Switch Governance Mode to Stage 3 (BICAMERAL_VETO_ACTIVE)
        page.locator("#gov-mode-reason").fill(f"Playwright C6 Stage 3 verification ({vp_name})")
        page.locator("#btn-mode-bicameral").click()
        page.wait_for_timeout(450)
        assert "MODE: BICAMERAL_VETO_ACTIVE" in page.locator("#gov-mode-badge").inner_text()
        page.screenshot(path=str(SCREENSHOTS_DIR / f"c6_dashboard_tab4_stage3_enclave_{vp_name}.png"), full_page=True)

        # 5. Open /lineage/house/1 (H2) in Stage 3 and cast a Bicameral Veto ballot
        resp_h2 = page.goto(f"{live_server}/lineage/house/1?role=H2", wait_until="networkidle", timeout=15000)
        assert resp_h2 is not None and resp_h2.status == 200
        assert page.locator("#vote-aye").is_visible()
        assert page.locator("#vote-nay").is_visible()
        assert page.locator("#vote-veto").is_visible()
        page.locator("#vote-veto").click()
        page.wait_for_timeout(450)
        assert "Bicameral Vetoes: 1 / 9" in page.locator("#veto-tally").inner_text()
        page.screenshot(path=str(SCREENSHOTS_DIR / f"c6_house1_h2_stage3_veto_{vp_name}.png"), full_page=True)

        # 6. Execute 1-Click SHTF Snap-Back from /dashboard Tab 4 -> EXECUTIVE_COMMAND
        resp_dash2 = page.goto(f"{live_server}/dashboard", wait_until="networkidle", timeout=15000)
        assert resp_dash2 is not None and resp_dash2.status == 200
        page.locator("#tab-btn-4").click()
        page.wait_for_timeout(350)
        page.locator("#btn-shtf-snapback").click()
        page.wait_for_timeout(450)
        assert "MODE: EXECUTIVE_COMMAND" in page.locator("#gov-mode-badge").inner_text()

        # 7. Confirm /lineage/house/1 (H2) voting buttons are stripped again after SHTF snap-back
        resp_post_shtf = page.goto(f"{live_server}/lineage/house/1?role=H2", wait_until="networkidle", timeout=15000)
        assert resp_post_shtf is not None and resp_post_shtf.status == 200
        assert "Executive Command Mode Active — Voting Dormant" in page.inner_text("body")
        assert page.locator("#vote-aye").count() == 0
        assert page.locator("#vote-veto").count() == 0

        _assert_zero_errors_and_zero_cdn(page, audit)
    finally:
        ctx.close()


@pytest.mark.parametrize("vp_name,vp_size", list(VIEWPORTS.items()))
def test_c6_companion_open_study_governance_doctrine(
    live_server: str,
    browser: Any,
    vp_name: str,
    vp_size: dict[str, int],
) -> None:
    """Verify /companion Chapter 6 renders the open-study Three-Stage Governance Lifecycle Charter."""
    base_host = urlparse(live_server).netloc
    ctx = browser.new_context(viewport=vp_size)
    try:
        page = ctx.new_page()
        audit = _attach_strict_auditors(ctx, page, base_host)
        resp = page.goto(f"{live_server}/companion", wait_until="networkidle", timeout=15000)
        assert resp is not None and resp.status == 200
        page.locator("#jumpChapter6Btn").click()
        page.wait_for_timeout(350)
        charter = page.locator("#enclaveGovernanceCharter")
        assert charter.is_visible()
        charter_text = charter.inner_text()
        assert "Three-Stage Governance Lifecycle" in charter_text
        assert "EXECUTIVE_COMMAND" in charter_text
        assert "ADVISORY_PETITION_FILTER" in charter_text
        assert "BICAMERAL_VETO_ACTIVE" in charter_text
        assert "IMMUTABLE_CORE_INVARIANT" in charter_text
        assert "SHTF" in charter_text
        page.screenshot(path=str(SCREENSHOTS_DIR / f"c6_companion_open_study_doctrine_{vp_name}.png"), full_page=True)
        _assert_zero_errors_and_zero_cdn(page, audit)
    finally:
        ctx.close()
