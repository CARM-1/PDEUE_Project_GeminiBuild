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

        # PR #101 Deliverable 1: Full-width canvas, legible untruncated Founder/House names (>=280x96, >=15px),
        # plain-English generation badges on SVG nodes, and slide-over drawer starts closed
        assert not page.locator("#personDetailCard").evaluate("el => el.classList.contains('open')")
        ola_node_info = page.evaluate(
            """() => {
                const g = document.querySelector('[data-person-id="P0004"]');
                const rect = g.querySelector('rect');
                const nameEl = g.querySelector('[data-node-name]');
                const genEl = g.querySelector('[data-node-gen-label]');
                const bertha = document.querySelector('[data-person-id="P0006"]');
                const berthaGen = bertha ? bertha.querySelector('[data-node-gen-label]').textContent : '';
                return {
                    w: Number(rect.getAttribute('width')),
                    h: Number(rect.getAttribute('height')),
                    nameFontSize: Number(nameEl.getAttribute('font-size')),
                    genFontSize: Number(genEl.getAttribute('font-size')),
                    olaName: nameEl.textContent,
                    olaGen: genEl.textContent,
                    berthaGen: berthaGen,
                };
            }"""
        )
        assert ola_node_info["w"] >= 280, f"Expected node width >= 280px, got {ola_node_info['w']}"
        assert ola_node_info["h"] >= 96, f"Expected node height >= 96px, got {ola_node_info['h']}"
        assert ola_node_info["nameFontSize"] >= 15, f"Expected name font >= 15px, got {ola_node_info['nameFontSize']}"
        assert ola_node_info["genFontSize"] >= 12, f"Expected gen font >= 12px, got {ola_node_info['genFontSize']}"
        assert "Mary Viola" in ola_node_info["olaName"] and "McCormick" in ola_node_info["olaName"]
        assert "…" not in ola_node_info["olaName"] and "..." not in ola_node_info["olaName"]
        assert ola_node_info["olaGen"] == "Founding Matriarch"
        assert ola_node_info["berthaGen"] == "1st Gen · Child of Founders"

        # PR #101 Zoom unclipped check: zooming in physically increases SVG width & scrollable area
        before_zoom = page.evaluate(
            """() => {
                const vp = document.getElementById('treeViewport');
                const svg = document.getElementById('familyTreeSvg');
                return { svgW: Number(svg.getAttribute('width')), scrollW: vp.scrollWidth };
            }"""
        )
        page.click("#treeZoomInBtn")
        page.click("#treeZoomInBtn")
        page.wait_for_timeout(150)
        after_zoom = page.evaluate(
            """() => {
                const vp = document.getElementById('treeViewport');
                const svg = document.getElementById('familyTreeSvg');
                return { svgW: Number(svg.getAttribute('width')), scrollW: vp.scrollWidth };
            }"""
        )
        assert after_zoom["svgW"] > before_zoom["svgW"], f"SVG did not physically enlarge on zoom: {before_zoom} -> {after_zoom}"
        assert after_zoom["scrollW"] >= before_zoom["scrollW"], "Scrollable viewport did not expand on zoom"
        page.click("#treeZoomResetBtn")
        page.wait_for_timeout(120)

        # PR #101 Full-Screen toggle opens and closes cleanly
        page.click("#toggleFullscreenTreeBtn")
        assert page.locator("#treeWorkspaceCard").evaluate("el => el.classList.contains('tree-fullscreen-mode')")
        page.click("#toggleFullscreenTreeBtn")
        assert not page.locator("#treeWorkspaceCard").evaluate("el => el.classList.contains('tree-fullscreen-mode')")

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
        assert page.locator("#personDetailCard").evaluate("el => el.classList.contains('open')")
        detail_text = page.locator("#personDetailCard").inner_text()
        assert "William Vincent Carmichael" in detail_text
        assert "4th Gen · 2nd Great-Grandchild of Founders" in detail_text
        assert "Living — Birth year" in detail_text
        assert "Check Relationship" in detail_text

        # Close drawer cleanly with X button, reopen on deceased dated House 02 ancestor P0007
        page.click("#closePersonDrawerBtn")
        page.wait_for_timeout(150)
        assert not page.locator("#personDetailCard").evaluate("el => el.classList.contains('open')")

        page.locator('[data-person-id="P0007"]').click(force=True)
        page.wait_for_timeout(200)
        arvell_detail = page.locator("#personDetailCard").inner_text()
        assert "1895–1975" in arvell_detail
        assert "1st Gen · Child of Founders" in arvell_detail

        # Close drawer via Escape, then click Founding Matriarch P0004 -> verify Founding Matriarch badge & review flag
        page.keyboard.press("Escape")
        page.wait_for_timeout(150)
        assert not page.locator("#personDetailCard").evaluate("el => el.classList.contains('open')")

        page.locator('[data-person-id="P0004"]').click(force=True)
        page.wait_for_timeout(200)
        ola_detail = page.locator("#personDetailCard").inner_text()
        assert "Mary Viola" in ola_detail
        assert "Founding Matriarch" in ola_detail
        assert "Genealogist Review Flag" in ola_detail
        page.keyboard.press("Escape")
        page.wait_for_timeout(150)
        assert not page.locator("#personDetailCard").evaluate("el => el.classList.contains('open')")

        # PR #101 Deliverable 2: 1-Click Easy-Read Family Directory toggle + opens same slide-over drawer
        page.click("#viewModeDirectoryBtn")
        page.wait_for_selector('[data-dir-person-id="P0004"]', timeout=6000)
        dir_text = page.locator("#familyDirectoryContent").inner_text()
        assert "Founding Matriarch" in dir_text
        assert "1st Gen · Child of Founders" in dir_text
        assert "4th Gen · 2nd Great-Grandchild of Founders" in dir_text
        page.locator('[data-dir-person-id="P0028"]').click()
        page.wait_for_timeout(200)
        assert page.locator("#personDetailCard").evaluate("el => el.classList.contains('open')")
        assert "Ronnie Carmichael" in page.locator("#personDetailCard").inner_text()
        page.click("#closePersonDrawerBtn")
        page.wait_for_timeout(120)

        # Capture Easy-Read Directory screenshot on desktop
        if vp_name == "desktop_1440x900":
            page.screenshot(
                path=str(SCREENSHOTS_DIR / f"pr101_easy_read_directory_{vp_name}.png"),
                full_page=True,
            )

        # Switch back to Visual Tree Diagram
        page.click("#viewModeTreeBtn")
        page.wait_for_selector('[data-person-id="P0004"]', timeout=6000)

        # PR #101 Deliverable 4: Relationship Calculator default (Ronnie Carmichael <-> Debora Simmons),
        # single-step picker labels (no raw IDs), Plain-English Story, Lineage Trails, and zero-network Clear button
        picker_a_val = page.locator("#calcPickerA").input_value()
        picker_b_val = page.locator("#calcPickerB").input_value()
        assert "Ronnie Carmichael" in picker_a_val and "P0028" not in picker_a_val
        assert "Debora Simmons" in picker_b_val and "P0526" not in picker_b_val
        default_calc = page.locator("#calcResultCard").inner_text()
        assert "2nd Cousin once removed" in default_calc
        assert "in plain english" in default_calc.lower()
        assert "James Willie Carmichael" in default_calc
        assert "1 generation younger" in default_calc
        assert page.locator("#calcLineageTrails").is_visible()
        assert "Generation Steps:" not in default_calc

        # Verify Clear button executes purely client-side (0 network requests) and returns focus to Person A
        clear_requests: list[str] = []
        page.on("request", lambda req: clear_requests.append(req.url))
        page.click("#clearRelationshipBtn")
        page.wait_for_timeout(150)
        assert clear_requests == [], f"Clear button must make zero network calls, observed: {clear_requests}"
        assert page.locator("#calcPickerA").input_value() == ""
        assert page.locator("#calcPickerB").input_value() == ""
        assert page.evaluate("document.activeElement && document.activeElement.id") == "calcPickerA"

        # Single-step searchable picker flow: type Ronnie -> pick P0028, type Debora -> pick P0526
        page.fill("#calcPickerA", "Ronnie Carmichael")
        page.wait_for_selector('#calcSuggestionsA [data-picker-person-id="P0028"]', timeout=4000)
        page.click('#calcSuggestionsA [data-picker-person-id="P0028"]')
        page.fill("#calcPickerB", "Debora Simmons")
        page.wait_for_selector('#calcSuggestionsB [data-picker-person-id="P0526"]', timeout=4000)
        page.click('#calcSuggestionsB [data-picker-person-id="P0526"]')
        page.click("#calcRelationshipBtn")
        page.wait_for_function(
            "() => (document.getElementById('calcPrimaryLabel')?.textContent || '').includes('2nd Cousin once removed')",
            timeout=6000,
        )

        # Test Cross-House via synchronized <select> hook: P0018 <-> P0257 -> 1st Cousin once removed
        page.select_option("#calcPersonA", "P0018", force=True)
        page.select_option("#calcPersonB", "P0257", force=True)
        page.click("#calcRelationshipBtn")
        page.wait_for_function(
            "() => (document.getElementById('calcPrimaryLabel')?.textContent || '').includes('1st Cousin once removed')",
            timeout=6000,
        )
        calc_text = page.locator("#calcResultCard").inner_text()
        assert "1st Cousin once removed" in calc_text
        assert "Mary Viola" in calc_text
        assert "Plain-English Glossary" in calc_text

        # Test Cross-Branch across all 25 pages while extended toggle is OFF:
        # P0018 (House 01) vs P0706 (Ernest Linwood Thompson Jr., Sarah / Thompson lineage) -> 2nd Cousin via Roderick & Dillie Gaddy
        page.select_option("#calcPersonA", "P0018", force=True)
        page.select_option("#calcPersonB", "P0706", force=True)
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

        # Reset view to default Ronnie <-> Debora for clean PR screenshot
        page.uncheck("#toggleReferenceBranches")
        page.wait_for_timeout(300)
        page.select_option("#calcPersonA", "P0028", force=True)
        page.select_option("#calcPersonB", "P0526", force=True)
        page.click("#calcRelationshipBtn")
        page.wait_for_function(
            "() => (document.getElementById('calcPrimaryLabel')?.textContent || '').includes('2nd Cousin once removed')",
            timeout=6000,
        )
        page.screenshot(
            path=str(SCREENSHOTS_DIR / f"pr101_family_tree_{vp_name}.png"),
            full_page=True,
        )

        # Final zero-overflow & zero-error assertions
        final_overflow = page.evaluate("document.documentElement.scrollWidth - window.innerWidth")
        assert final_overflow <= 1, f"Final horizontal overflow detected on {vp_name}: {final_overflow}px"
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


@pytest.mark.parametrize("vp_name", ["desktop_1440x900", "mobile_390x844"])
def test_pr103_studio_branch_spinoff_botanical_table_and_print(
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
        page.wait_for_selector('[data-person-id="P0004"]', timeout=8000)

        # 1. Open and close the retractable Full-Screen Tree Studio overlay
        assert page.locator("#openTreeStudioBtn").is_visible()
        assert page.locator("#printTreeBtn").is_visible()
        page.click("#openTreeStudioBtn")
        page.wait_for_timeout(180)
        assert page.locator("#treeStudioModal").evaluate("el => el.classList.contains('open')")
        assert page.locator("#treeStudioModal").is_visible()

        # Verify zoom controls inside Studio (50%–200%) + Reset View + Fit to Screen
        page.click("#studioResetViewBtn")
        page.wait_for_timeout(100)
        assert page.locator("#studioZoomReadout").inner_text().strip() == "100%"
        page.click("#studioZoomInBtn")
        page.wait_for_timeout(100)
        assert page.locator("#studioZoomReadout").inner_text().strip() == "120%"
        page.click("#studioZoomOutBtn")
        page.click("#studioFitScreenBtn")
        page.wait_for_timeout(120)

        # Close Studio cleanly via Close button -> returns to host page
        page.click("#closeTreeStudioBtn")
        page.wait_for_timeout(150)
        assert not page.locator("#treeStudioModal").evaluate("el => el.classList.contains('open')")

        # 2. Spin off John Willie Carmichael (P0018) from Person Detail Drawer -> auto-opens Studio
        page.locator('[data-house-toggle="HOUSE-01"]').click()
        page.wait_for_selector('[data-person-id="P0018"]', timeout=6000)
        page.locator('[data-person-id="P0018"]').click(force=True)
        page.wait_for_selector("#drawerSpinOffBranchBtn", timeout=4000)
        assert page.locator("#drawerSpinOffBranchBtn").is_visible()
        page.click("#drawerSpinOffBranchBtn")

        # Wait for isolated sub-tree breadcrumb trail & Return to Full Tree button
        page.wait_for_selector('#resetSubtreeRootBtn', state="visible", timeout=6000)
        assert page.locator("#treeStudioModal").evaluate("el => el.classList.contains('open')")
        crumb_text = page.locator("#lineageBreadcrumbTrail").inner_text()
        assert "Full 12-House Tree" in crumb_text
        assert 'House 01: Bertha "Bert" McCormick' in crumb_text
        assert "John Willie Carmichael" in crumb_text
        summary_text = page.locator("#subtreeSummaryPill").inner_text()
        assert "66 Relatives" in summary_text
        assert page.locator('[data-person-id="P0018"]').count() == 1
        assert page.locator('[data-person-id="P0028"]').count() == 1
        assert page.locator('[data-person-id="P0007"]').count() == 0  # House 02 strictly excluded

        # 3. Switch inside Studio to Botanical Lineage Tree -> verify curved boughs & ZERO card overlaps
        page.click("#studioViewModeBotanicalBtn")
        page.wait_for_selector('#botanicalNodesLayer [data-botanical-node="true"]', timeout=6000)
        bot_metrics = page.evaluate(
            """() => {
                const paths = document.querySelectorAll('#botanicalBoughsLayer path').length;
                const nodes = Array.from(document.querySelectorAll('#botanicalNodesLayer [data-botanical-node="true"]'));
                const boxes = nodes.map(g => {
                    const r = g.querySelector('rect');
                    return {
                        id: g.getAttribute('data-person-id'),
                        x: Number(r.getAttribute('x')),
                        y: Number(r.getAttribute('y')),
                        w: Number(r.getAttribute('width')),
                        h: Number(r.getAttribute('height')),
                    };
                });
                let overlaps = 0;
                for (let i = 0; i < boxes.length; i++) {
                    for (let j = i + 1; j < boxes.length; j++) {
                        const a = boxes[i], b = boxes[j];
                        if (a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y) {
                            overlaps++;
                        }
                    }
                }
                const rootG = document.querySelector('#botanicalNodesLayer [data-person-id="P0018"]');
                return {
                    paths,
                    nodeCount: nodes.length,
                    overlaps,
                    rootName: rootG ? rootG.querySelector('[data-node-name]').textContent : '',
                    rootGen: rootG ? rootG.querySelector('[data-node-gen-label]').textContent : '',
                };
            }"""
        )
        assert bot_metrics["paths"] >= 20, f"Expected curved botanical boughs, got {bot_metrics}"
        assert bot_metrics["nodeCount"] >= 40, f"Expected botanical nodes for P0018 branch, got {bot_metrics}"
        assert bot_metrics["overlaps"] == 0, f"Detected overlapping botanical cards: {bot_metrics}"
        assert "John Willie Carmichael" in bot_metrics["rootName"]
        assert "2nd Gen · Grandchild of Founders" == bot_metrics["rootGen"]

        if vp_name == "desktop_1440x900":
            page.screenshot(
                path=str(SCREENSHOTS_DIR / f"pr103_botanical_studio_subtree_{vp_name}.png"),
                full_page=False,
            )

        # Clicking a person in Botanical view opens Person Detail Drawer on top of Studio;
        # first Escape closes Drawer while keeping Studio open
        page.locator('#botanicalNodesLayer [data-person-id="P0028"]').click(force=True)
        page.wait_for_timeout(200)
        assert page.locator("#personDetailCard").evaluate("el => el.classList.contains('open')")
        assert "Ronnie Carmichael" in page.locator("#personDetailCard").inner_text()
        page.keyboard.press("Escape")
        page.wait_for_timeout(150)
        assert not page.locator("#personDetailCard").evaluate("el => el.classList.contains('open')")
        assert page.locator("#treeStudioModal").evaluate("el => el.classList.contains('open')")

        # 4. Switch inside Studio to Structured Family Table -> verify 66 sub-tree rows, sort, filter & Privacy Guard
        page.click("#studioViewModeTableBtn")
        page.wait_for_selector('#familyTableBody tr[data-table-row-id="P0018"]', timeout=6000)
        sub_row_count = page.locator("#familyTableBody tr[data-table-row-id]").count()
        assert sub_row_count == 66, f"Expected 66 rows in John Willie Carmichael sub-tree table, got {sub_row_count}"
        ronnie_row_text = page.locator('#familyTableBody tr[data-table-row-id="P0028"]').inner_text()
        assert "Ronnie Carmichael" in ronnie_row_text
        assert "Living · Privacy Protected" in ronnie_row_text

        # Sort by Full Name & quick-filter table
        page.click("#sortColNameBtn")
        page.wait_for_timeout(100)
        assert page.locator("#sortIndName").inner_text().strip() == "▲"
        if vp_name == "desktop_1440x900":
            page.screenshot(
                path=str(SCREENSHOTS_DIR / f"pr103_structured_table_studio_{vp_name}.png"),
                full_page=False,
            )

        page.fill("#tableQuickFilterInput", "Ronnie Carmichael")
        page.wait_for_timeout(120)
        assert page.locator("#familyTableBody tr[data-table-row-id]").count() >= 1
        page.locator('[data-table-person-id="P0028"]').first.click()
        page.wait_for_timeout(180)
        assert page.locator("#personDetailCard").evaluate("el => el.classList.contains('open')")
        page.click("#closePersonDrawerBtn")
        page.fill("#tableQuickFilterInput", "")
        page.wait_for_timeout(120)

        # 5. Verify Print / Save PDF button prepares printable header sheet & invokes window.print() cleanly
        page.evaluate("() => { window.__pr103PrintCalls = 0; window.print = () => { window.__pr103PrintCalls += 1; }; }")
        page.click("#studioPrintTreeBtn")
        page.wait_for_timeout(100)
        print_state = page.evaluate(
            """() => ({
                calls: window.__pr103PrintCalls,
                title: document.getElementById('printSheetTitle')?.textContent || '',
                meta: document.getElementById('printSheetMeta')?.textContent || '',
            })"""
        )
        assert print_state["calls"] == 1
        assert "Sub-Tree: John Willie Carmichael" in print_state["title"]
        assert "Structured Family Table" in print_state["meta"]

        # Emulate print media to verify @media print displays header sheet & hides studio toolbar
        page.emulate_media(media="print")
        page.wait_for_timeout(100)
        assert page.locator("#printHeaderSheet").is_visible()
        assert not page.locator(".studio-toolbar").is_visible()
        page.emulate_media(media="screen")
        page.wait_for_timeout(100)

        # 6. Return to Full Tree via 1-click button -> full dataset restored in table
        page.click("#resetSubtreeRootBtn")
        page.wait_for_timeout(250)
        assert not page.locator("#resetSubtreeRootBtn").is_visible()
        full_row_count = page.locator("#familyTableBody tr[data-table-row-id]").count()
        assert full_row_count >= 650, f"Expected full 12-House dataset restored (>=650 rows), got {full_row_count}"

        # Close Studio via Escape key -> host page restored with zero horizontal overflow
        page.keyboard.press("Escape")
        page.wait_for_timeout(180)
        assert not page.locator("#treeStudioModal").evaluate("el => el.classList.contains('open')")

        if vp_name == "mobile_390x844":
            page.screenshot(
                path=str(SCREENSHOTS_DIR / f"pr103_family_tree_host_{vp_name}.png"),
                full_page=True,
            )

        overflow = page.evaluate("document.documentElement.scrollWidth - window.innerWidth")
        assert overflow <= 1, f"Horizontal overflow detected on {vp_name}: {overflow}px"
        assert page_errors == [], f"Uncaught JS errors on {vp_name}: {page_errors}"
        assert console_errors == [], f"Console errors on {vp_name}: {console_errors}"
        assert failed_requests == [], f"Failed HTTP requests on {vp_name}: {failed_requests}"
        assert external_cdn_requests == [], f"External CDN requests on {vp_name}: {external_cdn_requests}"
    finally:
        context.close()

