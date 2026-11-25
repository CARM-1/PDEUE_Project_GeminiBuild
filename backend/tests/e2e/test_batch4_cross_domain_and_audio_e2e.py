"""Batch 4 Playwright E2E Verification:
1. Cross-domain header doorway hydration across /dashboard, /companion, /advisor, /member,
   and /admin/tech in BOTH `relative_single_host` and `multi_domain_air_gapped` modes
   (preserving query strings like `?supervisory=1&inspector=CHIEF_ADMIN`, `?role=F2-A`,
   `?role=F3`, `?scma_id=...`).
2. PDEUE University (/companion) local static Studio Audio (.mp3) + WebVTT (.vtt) playback
   wired via `GET /api/v1/portal/companion/state` with ZERO runtime TTS API calls, ZERO
   external CDN requests, and ZERO console/network errors.
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
from typing import Any, Dict, List
from urllib.parse import urlparse
from urllib.request import urlopen

import pytest

playwright_sync = pytest.importorskip(
    "playwright.sync_api",
    reason="Playwright is required for Batch 4 E2E tests",
)
sync_playwright = playwright_sync.sync_playwright

pytestmark = pytest.mark.e2e

REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_DIR = REPO_ROOT / "backend"
SCREENSHOTS_DIR = REPO_ROOT / "artifacts" / "playwright_screenshots" / "batch4"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from scripts import build_companion_audio as audio_builder  # noqa: E402

MULTI_DOMAIN_PLANES_PAYLOAD: Dict[str, Any] = {
    "routing_mode": "multi_domain_air_gapped",
    "air_gapped_social_plane": True,
    "prohibited_corporate_domains_untouched": ["carm-aerotech.com", "narratixai.com"],
    "planes": {},
    "doorways": {
        "home": "https://narratixai.org/home",
        "community": "https://narratixai.org/community",
        "heritage": "https://narratixai.org/community/heritage",
        "genealogist_desk": "https://narratixai.org/community/heritage#genealogist-desk",
        "companion": "https://narratixai.info/companion",
        "member": "https://vault.narratixai.io/member",
        "advisor": "https://vault.narratixai.io/advisor",
        "lineage_house_template": "https://vault.narratixai.io/lineage/house/{house_id}",
        "dashboard": "https://admin.narratixai.io/dashboard",
        "tech": "https://admin.narratixai.io/admin/tech",
        "admin_tech": "https://admin.narratixai.io/admin/tech",
        "ifas": "https://narratixai.net",
        "ifas_configured": True,
        "ifas_production_target": "https://narratixai.net",
    },
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

    with tempfile.TemporaryDirectory(prefix="pdeue_batch4_e2e_") as tmp_dir:
        db_path = Path(tmp_dir) / "pdeue_batch4_e2e.db"
        env = os.environ.copy()
        env["DATABASE_URL"] = f"sqlite:///{db_path}"
        env["PDEUE_VENUE_MODE"] = "paper"
        env["PDEUE_LIVE_TRADING_ENABLED"] = "false"
        env["PDEUE_GOVERNANCE_MODE"] = "EXECUTIVE_COMMAND"
        env["PYTHONUNBUFFERED"] = "1"
        for k in (
            "FAMILY_HUB_BASE_URL",
            "UNIVERSITY_BASE_URL",
            "PDEUE_VAULT_BASE_URL",
            "PDEUE_ADMIN_BASE_URL",
            "IFAS_ACCOUNTING_BASE_URL",
            "PDEUE_COMPANION_MEDIA_DIR",
        ):
            env.pop(k, None)

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
                raise RuntimeError("FastAPI live server failed to boot within 25s")
            yield base_url
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                proc.kill()


def test_cross_domain_doorway_hydration_preserves_queries_across_all_portals(live_server: str):
    console_errors: List[str] = []
    page_errors: List[str] = []
    external_requests: List[str] = []
    http_errors: List[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            # 1. Default relative_single_host check on /dashboard (must remain relative!)
            rel_ctx = browser.new_context(viewport={"width": 1440, "height": 900})
            rel_page = rel_ctx.new_page()
            rel_page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
            rel_page.on("pageerror", lambda e: page_errors.append(str(e)))
            rel_page.goto(f"{live_server}/dashboard", wait_until="networkidle")
            rel_page.wait_for_function("() => Boolean(window.PDEUEPlaneConfig)")

            assert rel_page.locator('a[data-plane-doorway="advisor"]').first.get_attribute("href") == "/advisor?supervisory=1&inspector=CHIEF_ADMIN"
            assert rel_page.locator('a[data-plane-doorway="admin_tech"]').first.get_attribute("href") == "/admin/tech?supervisory=1&inspector=CHIEF_ADMIN"
            assert rel_page.locator('a[data-plane-doorway="companion"]').first.get_attribute("href") == "/companion"
            assert rel_page.locator('a[data-plane-doorway="home"]').first.get_attribute("href") == "/home"
            rel_ctx.close()

            # 2. multi_domain_air_gapped hydration across /dashboard, /companion, /advisor, /member, /admin/tech
            ctx = browser.new_context(viewport={"width": 1440, "height": 900})
            page = ctx.new_page()
            page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
            page.on("pageerror", lambda e: page_errors.append(str(e)))

            def _track_req(req: Any) -> None:
                parsed = urlparse(req.url)
                if parsed.hostname not in (None, "127.0.0.1", "localhost"):
                    external_requests.append(req.url)

            page.on("request", _track_req)
            page.on("response", lambda r: http_errors.append(f"{r.status} {r.url}") if r.status >= 400 else None)

            page.route(
                "**/api/v1/portal/planes",
                lambda route: route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps(MULTI_DOMAIN_PLANES_PAYLOAD),
                ),
            )

            # /dashboard
            page.goto(f"{live_server}/dashboard", wait_until="networkidle")
            page.wait_for_function("() => window.PDEUEPlaneConfig && window.PDEUEPlaneConfig.routing_mode === 'multi_domain_air_gapped'")
            assert page.locator('a[data-plane-doorway="home"]').first.get_attribute("href") == "https://narratixai.org/home"
            assert page.locator('a[data-plane-doorway="heritage"]').first.get_attribute("href") == "https://narratixai.org/community/heritage"
            assert page.locator('a[data-plane-doorway="dashboard"]').first.get_attribute("href") == "https://admin.narratixai.io/dashboard"
            assert page.locator('a[data-plane-doorway="admin_tech"]').first.get_attribute("href") == "https://admin.narratixai.io/admin/tech?supervisory=1&inspector=CHIEF_ADMIN"
            assert page.locator('a[data-plane-doorway="advisor"]').first.get_attribute("href") == "https://vault.narratixai.io/advisor?supervisory=1&inspector=CHIEF_ADMIN"
            assert page.locator('a[data-plane-doorway="member"]').first.get_attribute("href") == "https://vault.narratixai.io/member"
            assert page.locator('a[data-plane-doorway="companion"]').first.get_attribute("href") == "https://narratixai.info/companion"
            page.screenshot(path=str(SCREENSHOTS_DIR / "dashboard_cross_domain_hydrated.png"))

            # Verify arbitrary ?role=F2-A query string preservation helper directly in browser
            preserved = page.evaluate(
                "() => window.PDEUESeniorA11y.resolveDoorwayUrl('advisor', '/advisor?role=F2-A')"
            )
            assert preserved == "https://vault.narratixai.io/advisor?role=F2-A"
            preserved_f3 = page.evaluate(
                "() => window.PDEUESeniorA11y.resolveDoorwayUrl('advisor', '/advisor?role=F3')"
            )
            assert preserved_f3 == "https://vault.narratixai.io/advisor?role=F3"

            # /companion (with ?scma_id=... query string preserved on Member header link)
            page.goto(f"{live_server}/companion?scma_id=SCMA-ELEANOR_-B2B31C9E", wait_until="networkidle")
            page.wait_for_function("() => window.PDEUEPlaneConfig && window.PDEUEPlaneConfig.routing_mode === 'multi_domain_air_gapped'")
            assert page.locator('a[data-plane-doorway="home"]').first.get_attribute("href") == "https://narratixai.org/home"
            assert page.locator('a[data-plane-doorway="dashboard"]').first.get_attribute("href") == "https://admin.narratixai.io/dashboard"
            assert page.locator('a[data-plane-doorway="member"]').first.get_attribute("href") == "https://vault.narratixai.io/member?scma_id=SCMA-ELEANOR_-B2B31C9E"
            assert page.locator('a[data-plane-doorway="companion"]').first.get_attribute("href") == "https://narratixai.info/companion"

            # /advisor, /member, /admin/tech
            for path in ("/advisor?role=F2-H", "/member", "/admin/tech?tier=T3"):
                page.goto(f"{live_server}{path}", wait_until="networkidle")
                page.wait_for_function("() => window.PDEUEPlaneConfig && window.PDEUEPlaneConfig.routing_mode === 'multi_domain_air_gapped'")
                assert page.locator('a[data-plane-doorway="home"]').first.get_attribute("href") == "https://narratixai.org/home"
                assert page.locator('a[data-plane-doorway="heritage"]').first.get_attribute("href") == "https://narratixai.org/community/heritage"
                comp_href = page.locator('a[data-plane-doorway="companion"]').first.get_attribute("href")
                if path == "/member":
                    assert comp_href is not None and comp_href.startswith("https://narratixai.info/companion?scma_id="), (
                        f"Expected /member companion link to preserve scma_id on narratixai.info, got {comp_href!r}"
                    )
                else:
                    assert comp_href == "https://narratixai.info/companion"

            ctx.close()
        finally:
            browser.close()

    assert console_errors == [], f"Console errors: {console_errors}"
    assert page_errors == [], f"Page errors: {page_errors}"
    assert external_requests == [], f"Unexpected external CDN/API requests: {external_requests}"
    assert http_errors == [], f"HTTP errors: {http_errors}"


def test_companion_plays_local_static_studio_audio_and_webvtt_with_zero_runtime_api_calls(
    live_server: str,
    tmp_path: Path,
):
    # Generate real valid MPEG-1 Layer 3 mock .mp3 + WebVTT .vtt tracks via Batch 4 builder
    build_res = audio_builder.build_companion_audio(
        provider=audio_builder.MockTTSProvider(),
        output_dir=tmp_path,
        only_beat_ids=["ch0_orientation", "ch1_b1"],
    )
    manifest = build_res["manifest"]

    console_errors: List[str] = []
    page_errors: List[str] = []
    external_requests: List[str] = []
    http_errors: List[str] = []
    served_media_urls: List[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            ctx = browser.new_context(viewport={"width": 1440, "height": 900})
            page = ctx.new_page()
            page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
            page.on("pageerror", lambda e: page_errors.append(str(e)))
            page.on(
                "request",
                lambda req: external_requests.append(req.url)
                if urlparse(req.url).hostname not in (None, "127.0.0.1", "localhost")
                else None,
            )
            page.on("response", lambda r: http_errors.append(f"{r.status} {r.url}") if r.status >= 400 else None)

            # Intercept /api/v1/portal/companion/state to serve the freshly generated manifest
            def _serve_state(route: Any) -> None:
                resp = route.fetch()
                payload = resp.json()
                payload["media_manifest"] = manifest
                payload["studio_audio_ready"] = True
                payload["zero_runtime_tts_api"] = True
                route.fulfill(status=200, content_type="application/json", body=json.dumps(payload))

            # Serve generated local .mp3 and .vtt files under /static/media/companion/*
            def _serve_media(route: Any) -> None:
                rel = urlparse(route.request.url).path.removeprefix("/static/media/companion/")
                local_file = (tmp_path / rel).resolve()
                if local_file.is_file():
                    served_media_urls.append(urlparse(route.request.url).path)
                    ctype = "audio/mpeg" if local_file.suffix == ".mp3" else "text/vtt; charset=utf-8"
                    route.fulfill(status=200, content_type=ctype, body=local_file.read_bytes())
                else:
                    route.continue_()

            page.route("**/api/v1/portal/companion/state", _serve_state)
            page.route("**/static/media/companion/**", _serve_media)

            page.goto(f"{live_server}/companion", wait_until="networkidle")
            page.wait_for_function("() => Boolean(window.PDEUECompanionMedia && window.PDEUECompanionMedia.manifest)")

            assert "Studio Audio Ready" in page.locator("#audioBadge").inner_text()

            # Trigger Chapter 0 Orientation narration (Studio Mentor Maya)
            page.locator("#playOrientationBtn").click()
            page.wait_for_function(
                "() => document.getElementById('companionAudioPlayer').dataset.studioActive === 'true'"
            )

            audio_state = page.evaluate(
                """() => {
                  const a = document.getElementById('companionAudioPlayer');
                  const src = a.querySelector('source');
                  const tr = a.querySelector('track');
                  return {
                    studioActive: a.dataset.studioActive,
                    studioTrack: a.dataset.studioTrack,
                    sourceSrc: src ? src.getAttribute('src') : null,
                    sourceType: src ? src.getAttribute('type') : null,
                    trackKind: tr ? tr.getAttribute('kind') : null,
                    trackSrc: tr ? tr.getAttribute('src') : null,
                    badge: document.getElementById('audioBadge').textContent,
                  };
                }"""
            )
            assert audio_state["studioActive"] == "true"
            assert audio_state["studioTrack"] == "ch0_orientation"
            assert audio_state["sourceSrc"] == "/static/media/companion/mentor_f_aa/ch0_orientation.mp3"
            assert audio_state["sourceType"] == "audio/mpeg"
            assert audio_state["trackKind"] == "captions"
            assert audio_state["trackSrc"] == "/static/media/companion/mentor_f_aa/ch0_orientation.vtt"
            assert audio_state["badge"] == "Studio Mentor Audio + Synced Captions"

            # Switch to Studio Mentor Marcus and play Chapter 1 Beat 1
            page.locator("#voiceSelect").select_option("studio:mentor_m_aa")
            page.locator("#playPause").click()
            page.wait_for_function(
                "() => document.getElementById('companionAudioPlayer').dataset.studioTrack === 'ch1_b1'"
            )
            marcus_src = page.locator("#companionAudioPlayer source").get_attribute("src")
            marcus_vtt = page.locator("#companionAudioPlayer track").get_attribute("src")
            assert marcus_src == "/static/media/companion/mentor_m_aa/ch1_b1.mp3"
            assert marcus_vtt == "/static/media/companion/mentor_m_aa/ch1_b1.vtt"

            page.screenshot(path=str(SCREENSHOTS_DIR / "companion_studio_audio_webvtt.png"))
            ctx.close()
        finally:
            browser.close()

    assert console_errors == [], f"Console errors: {console_errors}"
    assert page_errors == [], f"Page errors: {page_errors}"
    assert external_requests == [], f"Runtime external TTS/CDN calls detected: {external_requests}"
    assert http_errors == [], f"HTTP errors: {http_errors}"
    assert any(u.endswith(".mp3") for u in served_media_urls), f"Expected local .mp3 fetch, got {served_media_urls}"
