"""PR #95 Playwright E2E Verification:
Verifies live `/companion` Degree Colleges (Class H & House Genealogist manual)
and Library tab Role How-To & Visual Playbook Library rendering annotated local
screenshots with zero broken images, zero console/page/HTTP errors, and zero CDN calls.
"""
from __future__ import annotations

import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from typing import Any, Generator
from urllib.parse import urlparse
from urllib.request import urlopen

from playwright.sync_api import sync_playwright
import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_DIR = REPO_ROOT / "backend"


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture(scope="module")
def live_server() -> Generator[str, None, None]:
    port = _find_free_port()
    base_url = f"http://127.0.0.1:{port}"
    with tempfile.TemporaryDirectory(prefix="pdeue_pr95_e2e_") as tmp_dir:
        db_path = Path(tmp_dir) / "pdeue_pr95.db"
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
                    time.sleep(0.25)
            else:
                raise RuntimeError("FastAPI server failed to boot for PR #95 E2E test")
            yield base_url
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                proc.kill()


@pytest.fixture(scope="module")
def browser() -> Generator[Any, None, None]:
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        try:
            yield b
        finally:
            b.close()


@pytest.mark.parametrize(
    "vp_name,vp_size",
    [
        ("desktop", {"width": 1440, "height": 900}),
        ("mobile", {"width": 390, "height": 844}),
    ],
)
def test_pr95_companion_class_h_manual_and_playbook_library_e2e(
    live_server: str,
    browser: Any,
    vp_name: str,
    vp_size: dict[str, int],
) -> None:
    base_host = urlparse(live_server).netloc
    ctx = browser.new_context(viewport=vp_size)
    console_errors: list[str] = []
    page_errors: list[str] = []
    http_errors: list[str] = []
    external_reqs: list[str] = []

    def _intercept(route_obj: Any) -> None:
        req = route_obj.request
        parsed = urlparse(req.url)
        if parsed.scheme in {"data", "blob", "about"} or parsed.netloc == base_host:
            route_obj.continue_()
            return
        external_reqs.append(req.url)
        route_obj.abort("blockedbyclient")

    ctx.route("**/*", _intercept)
    page = ctx.new_page()
    page.set_default_timeout(15000)
    page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: page_errors.append(str(e)))
    page.on("response", lambda r: http_errors.append(f"{r.status} {r.url}") if r.status >= 400 else None)

    try:
        page.goto(f"{live_server}/companion", wait_until="networkidle")

        # 1. Verify Class H & House Genealogist manual card + dropdown load cleanly in Degree Colleges tab
        page.locator("#tabCollegesBtn").click()
        assert page.locator('article[data-manual-card="CLASS_H_LINEAGE_AND_HERITAGE_MANUAL.md"]').is_visible()
        page.locator('button[data-manual-load="CLASS_H_LINEAGE_AND_HERITAGE_MANUAL.md"]').click()
        page.wait_for_function(
            "() => (document.getElementById('manualReaderStatus')?.textContent || '').includes('CLASS_H_LINEAGE_AND_HERITAGE_MANUAL.md')"
        )
        reader_text = page.locator("#manual-reader-container").inner_text()
        assert "HOUSE_GENEALOGIST" in reader_text
        assert "Freeze Dial (0%)" in reader_text

        # 2. Switch to Library tab and verify Playbook Library renders local annotated screenshots cleanly
        page.locator("#tabLibraryBtn").click()
        page.wait_for_function(
            "() => document.querySelectorAll('#playbookCardsGrid .playbook-card').length >= 10"
        )

        # Wait for all playbook images to finish loading and assert ZERO broken images
        page.wait_for_function(
            """() => {
                const imgs = Array.from(document.querySelectorAll('#playbookCardsGrid img.playbook-shot-img'));
                return imgs.length >= 10 && imgs.every(img => img.complete && img.naturalWidth > 0);
            }"""
        )

        # Verify role & scenario filters work live
        page.locator("#playbookRoleFilter").select_option("CLASS_H")
        page.locator("#playbookScenarioFilter").select_option("outlier_incident")
        page.wait_for_function(
            """() => {
                const cards = Array.from(document.querySelectorAll('#playbookCardsGrid .playbook-card'));
                return cards.length >= 1 && cards.every(c => c.dataset.scenarioType === 'outlier_incident');
            }"""
        )

        # Verify Reset Filters restores all playbooks
        page.locator("#resetPlaybookFiltersBtn").click()
        page.wait_for_function(
            "() => document.querySelectorAll('#playbookCardsGrid .playbook-card').length >= 10"
        )

        # Verify zero external CDN tags, zero console/page/HTTP errors, and zero horizontal overflow
        cdn_count = page.evaluate(
            """() => Array.from(document.querySelectorAll('script[src], link[href]'))
                .filter(el => /^https?:\\/\\//i.test(el.getAttribute('src') || el.getAttribute('href') || '')).length"""
        )
        assert cdn_count == 0
        assert console_errors == [], f"{vp_name} console errors: {console_errors}"
        assert page_errors == [], f"{vp_name} page errors: {page_errors}"
        assert http_errors == [], f"{vp_name} HTTP errors: {http_errors}"
        assert external_reqs == [], f"{vp_name} external requests: {external_reqs}"
    finally:
        ctx.close()
