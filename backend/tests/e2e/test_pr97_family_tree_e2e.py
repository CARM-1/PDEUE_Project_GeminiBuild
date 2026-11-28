"""PR #97 Playwright E2E Verification Suite:
Interactive Zero-CDN Family Tree (/community/heritage/tree), Live Relationship Calculator,
Living-Member Privacy Guard display, Person Detail Card, Reference Branch toggle,
and Scoped Genealogist Curation Drawer across desktop (1440x900) and mobile (390x844)."""
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
    reason="Playwright is required for PR #97 E2E tests",
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

    with tempfile.TemporaryDirectory(prefix="pdeue_pr97_e2e_") as tmp_dir:
        db_path = Path(tmp_dir) / "pdeue_pr97.db"
        mutex_path = Path(tmp_dir) / "pdeue_pr97_mutex.sqlite3"
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
            yield base_url
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


@pytest.mark.parametrize("vp_name", ["desktop_1440x900", "mobile_390x844"])
def test_pr97_family_tree_portal_renders_filters_calculates_and_has_zero_overflow(
    live_server: str,
    browser: Any,
    vp_name: str,
) -> None:
    vp = VIEWPORTS[vp_name]
    base_host = urlparse(live_server).netloc
    context = browser.new_context(viewport=vp)
    page_errors: list[str] = []
    console_errors: list[str] = []
    failed_requests: list[str] = []
    external_cdn_requests: list[str] = []

    try:
        page = context.new_page()
        page.on("pageerror", lambda err: page_errors.append(str(err)))
        page.on(
            "console",
            lambda msg: console_errors.append(msg.text) if msg.type == "error" else None,
        )
        page.on(
            "response",
            lambda resp: failed_requests.append(f"{resp.status} {resp.url}")
            if resp.status >= 400
            else None,
        )

        def _guard_external(route: Any) -> None:
            url = route.request.url
            parsed = urlparse(url)
            if parsed.scheme in {"http", "https"} and parsed.netloc != base_host:
                external_cdn_requests.append(url)
                route.abort()
            else:
                route.continue_()

        page.route("**/*", _guard_external)

        resp = page.goto(f"{live_server}/community/heritage/tree", wait_until="networkidle", timeout=15000)
        assert resp is not None and resp.status == 200

        # Wait for SVG tree nodes to hydrate (fast render at scale)
        page.wait_for_selector('[data-person-id="P0004"]', timeout=8000)
        page.wait_for_selector('#calcPrimaryLabel', timeout=8000)

        # Standard member view: read-only notice visible, curation drawer stripped
        assert page.locator("#treeReadOnlyBanner").count() == 1
        assert page.locator("#genealogistTreeDrawer").count() == 0

        # Calm scale-safe default: Houses collapsed to Gen 1 roots + Founders (< 45 SVG nodes),
        # and Extended Roderick & Dillie Gaddy branch OFF by default (P0001 not rendered)
        initial_node_count = page.locator("#treeNodesLayer [data-person-id]").count()
        assert 14 <= initial_node_count <= 45, f"Expected calm collapsed default view, got {initial_node_count} nodes"
        assert page.locator('[data-person-id="P0001"]').count() == 0
        assert page.locator('[data-person-id="P0058"]').count() == 0  # Gen 4 hidden until House 01 expanded

        # Zero horizontal overflow check
        overflow = page.evaluate("document.documentElement.scrollWidth - window.innerWidth")
        assert overflow <= 1, f"Horizontal overflow detected on {vp_name}: {overflow}px"

        # Zero external CDN tags in DOM
        cdn_tags = page.evaluate(
            """() => Array.from(document.querySelectorAll('script[src], link[href]'))
                .map(el => el.getAttribute('src') || el.getAttribute('href') || '')
                .filter(u => /^https?:\\/\\//i.test(u))"""
        )
        assert cdn_tags == [], f"External CDN tags detected: {cdn_tags}"

        # 1-click expand House 01 -> reveals living descendant P0058 (William Vincent Carmichael, deduplicated)
        page.locator('[data-house-toggle="HOUSE-01"]').click()
        page.wait_for_selector('[data-person-id="P0058"]', timeout=6000)
        assert page.locator('[data-person-id="P0058"]').count() == 1
        page.locator('[data-person-id="P0058"]').click(force=True)
        page.wait_for_timeout(200)
        detail_text = page.locator("#personDetailCard").inner_text()
        assert "William Vincent Carmichael" in detail_text
        assert "Living — Birth year" in detail_text

        # Click deceased dated House 02 ancestor P0007 (Arvell "Son" McCormick) -> verify 1895–1975
        page.locator('[data-person-id="P0007"]').click(force=True)
        page.wait_for_timeout(200)
        arvell_detail = page.locator("#personDetailCard").inner_text()
        assert "1895–1975" in arvell_detail

        # Click Founding Matriarch P0004 (Mary Viola "Ola" McCormick) -> verify Child I. review flag
        page.locator('[data-person-id="P0004"]').click(force=True)
        page.wait_for_timeout(200)
        ola_detail = page.locator("#personDetailCard").inner_text()
        assert "Mary Viola" in ola_detail
        assert "Genealogist Review Flag" in ola_detail

        # Test Live Relationship Calculator (Cross-House):
        # P0018 (John Willie Carmichael, House 01) vs P0257 (William "Cookie Boy" McCormick, House 03)
        page.select_option("#calcPersonA", "P0018")
        page.select_option("#calcPersonB", "P0257")
        page.click("#calcRelationshipBtn")
        page.wait_for_function(
            "() => (document.getElementById('calcPrimaryLabel')?.textContent || '').includes('1st Cousin once removed')",
            timeout=6000,
        )
        calc_text = page.locator("#calcResultCard").inner_text()
        assert "1st Cousin once removed" in calc_text
        assert "Mary Viola" in calc_text
        assert "Plain-English Glossary" in calc_text

        # Test Live Relationship Calculator (Cross-Branch across all 25 pages while extended toggle is OFF):
        # P0018 (House 01) vs P0706 (Ernest Linwood Thompson Jr., Sarah / Thompson lineage) -> 2nd Cousin via Roderick & Dillie Gaddy
        page.select_option("#calcPersonA", "P0018")
        page.select_option("#calcPersonB", "P0706")
        page.click("#calcRelationshipBtn")
        page.wait_for_function(
            "() => (document.getElementById('calcPrimaryLabel')?.textContent || '').includes('2nd Cousin')",
            timeout=6000,
        )
        cross_calc_text = page.locator("#calcResultCard").inner_text()
        assert "2nd Cousin" in cross_calc_text
        assert "Roderick McCormick" in cross_calc_text

        # Test House Filter + Search
        page.select_option("#treeHouseFilter", "HOUSE-01")
        page.wait_for_timeout(350)
        assert page.locator('[data-person-id="P0058"]').count() == 1
        assert page.locator('[data-person-id="P0008"]').count() == 0

        page.click("#treeResetFiltersBtn")
        page.wait_for_timeout(350)
        page.fill("#treeSearchInput", "Whitehead")
        page.wait_for_timeout(350)
        assert page.locator('[data-person-id="P0032"]').count() == 1

        # Test Extended Roderick & Dillie Gaddy Lineage toggle reveals P0001 & P0002
        page.click("#treeResetFiltersBtn")
        page.wait_for_timeout(350)
        page.check("#toggleReferenceBranches")
        page.wait_for_selector('[data-person-id="P0001"]', timeout=6000)
        assert page.locator('[data-person-id="P0001"]').count() == 1
        assert page.locator('[data-person-id="P0002"]').count() == 1

        # Reset view & capture screenshot
        page.uncheck("#toggleReferenceBranches")
        page.wait_for_timeout(350)
        page.screenshot(
            path=str(SCREENSHOTS_DIR / f"pr100_family_tree_{vp_name}.png"),
            full_page=True,
        )

        # Final zero-error assertions
        assert page_errors == [], f"Uncaught JS errors on {vp_name}: {page_errors}"
        assert console_errors == [], f"Console errors on {vp_name}: {console_errors}"
        assert failed_requests == [], f"Failed HTTP requests on {vp_name}: {failed_requests}"
        assert external_cdn_requests == [], f"External CDN requests on {vp_name}: {external_cdn_requests}"
    finally:
        context.close()


def test_pr97_genealogist_drawer_and_heritage_community_ctas(
    live_server: str,
    browser: Any,
) -> None:
    context = browser.new_context(viewport=VIEWPORTS["desktop_1440x900"])
    try:
        page = context.new_page()

        # 1. Verify CTA on /community/heritage navigates to /community/heritage/tree
        page.goto(f"{live_server}/community/heritage", wait_until="networkidle", timeout=15000)
        assert page.locator("#exploreFamilyTreeBtn").is_visible()
        page.click("#exploreFamilyTreeBtn")
        page.wait_for_url("**/community/heritage/tree", timeout=8000)
        page.wait_for_selector('[data-person-id="P0004"]', timeout=8000)

        # 2. Verify CTA on /community navigates to /community/heritage/tree
        page.goto(f"{live_server}/community", wait_until="networkidle", timeout=15000)
        assert page.locator("#communityExploreFamilyTreeBtn").is_visible()

        # 3. Verify HOUSE_GENEALOGIST view enables collapsible Curation Drawer
        page.goto(
            f"{live_server}/community/heritage/tree?role=HOUSE_GENEALOGIST&house_id=HOUSE-03",
            wait_until="networkidle",
            timeout=15000,
        )
        assert page.locator("#genealogistTreeDrawer").count() == 1
        page.locator("#genealogistTreeDrawer summary").click()
        assert page.locator("#addPersonForm").is_visible()
        page.screenshot(
            path=str(SCREENSHOTS_DIR / "pr97_family_tree_genealogist_desktop_1440x900.png"),
            full_page=True,
        )
    finally:
        context.close()
