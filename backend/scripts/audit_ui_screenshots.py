#!/usr/bin/env python3
"""Playwright UI/UX Screenshot & Clutter Telemetry Auditor for all 9 PDEUE portals.

Boots an isolated fail-closed local FastAPI server (or attaches to --base-url),
captures 1440x900 above-the-fold and full-page screenshots for every portal
(plus /companion with Orientation expanded), and writes telemetry.json + SUMMARY.md
into ui_audit_output/ (or --out-dir).
"""
from __future__ import annotations

import argparse
import json
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

from playwright.sync_api import sync_playwright

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
DEFAULT_OUT_DIR = REPO_ROOT / "ui_audit_output"

PAGES: list[dict[str, str]] = [
    {"name": "companion", "route": "/companion", "file": "companion.html"},
    {"name": "dashboard", "route": "/dashboard", "file": "dashboard.html"},
    {"name": "member", "route": "/member", "file": "member.html"},
    {"name": "advisor", "route": "/advisor?role=F2-H", "file": "advisor.html"},
    {"name": "community", "route": "/community", "file": "community.html"},
    {"name": "home", "route": "/home", "file": "home.html"},
    {"name": "lineage_house", "route": "/lineage/house/1", "file": "lineage_house.html"},
    {"name": "tech", "route": "/admin/tech?tier=T3", "file": "tech.html"},
    {"name": "heritage", "route": "/community/heritage", "file": "heritage.html"},
]


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _collect_page_metrics(page: Any) -> dict[str, Any]:
    return page.evaluate(
        """() => {
            const vw = window.innerWidth;
            const vh = window.innerHeight;
            const sw = document.documentElement.scrollWidth;
            const sh = document.documentElement.scrollHeight;
            const isVisible = (el) => {
                if (!el) return false;
                const style = window.getComputedStyle(el);
                if (style.display === 'none' || style.visibility === 'hidden' || Number(style.opacity) === 0) return false;
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
            };
            const sectionNodes = Array.from(document.querySelectorAll('section, article, aside, details, .card, .panel, .card-box, .table-card, .chapter'));
            const visibleSections = sectionNodes.filter(isVisible);
            const controlNodes = Array.from(document.querySelectorAll('button, input, select, textarea'));
            const visibleControls = controlNodes.filter(isVisible);
            const aboveFoldControls = visibleControls.filter((el) => {
                const r = el.getBoundingClientRect();
                return r.bottom > 0 && r.top < vh;
            });
            const cdnTags = [];
            for (const el of document.querySelectorAll('script[src], link[href]')) {
                const raw = el.getAttribute('src') || el.getAttribute('href') || '';
                if (/^https?:\\/\\//i.test(raw)) cdnTags.push(raw);
            }
            return {
                viewport_width: vw,
                viewport_height: vh,
                scroll_width: sw,
                scroll_height: sh,
                height_ratio: Number((sh / Math.max(1, vh)).toFixed(2)),
                horizontal_overflow_px: Math.max(0, Math.round(sw - vw)),
                total_sections: sectionNodes.length,
                visible_sections: visibleSections.length,
                total_controls: controlNodes.length,
                visible_controls: visibleControls.length,
                above_fold_controls: aboveFoldControls.length,
                cdn_tags: cdnTags,
            };
        }"""
    )


def _measure_companion_orientation_and_illustration(page: Any) -> dict[str, Any]:
    return page.evaluate(
        """() => {
            const vh = window.innerHeight;
            const orient = document.getElementById('chapter-orientation');
            const illus = document.querySelector('#chapter-waterfall .waterfall');
            const toggleBtn = document.getElementById('toggleOrientationBtn');
            const rectObj = (el) => {
                if (!el) return null;
                const r = el.getBoundingClientRect();
                const cs = window.getComputedStyle(el);
                const visible = cs.display !== 'none' && cs.visibility !== 'hidden' && r.width > 0 && r.height > 0;
                return {
                    visible,
                    top: Math.round(r.top),
                    bottom: Math.round(r.bottom),
                    left: Math.round(r.left),
                    right: Math.round(r.right),
                    width: Math.round(r.width),
                    height: Math.round(r.height),
                    above_fold_fully: visible && r.top >= 0 && r.bottom <= vh,
                    above_fold_mostly: visible && r.top >= 0 && r.top < vh && (Math.min(r.bottom, vh) - Math.max(r.top, 0)) / Math.max(1, r.height) >= 0.75,
                };
            };
            const oRect = rectObj(orient);
            const iRect = rectObj(illus);
            return {
                orientation_collapsed: orient ? orient.dataset.collapsed === '1' : null,
                toggle_label: toggleBtn ? toggleBtn.textContent.trim() : null,
                orientation_rect: oRect,
                illustration_rect: iRect,
                both_visible_above_fold: Boolean(oRect && iRect && oRect.above_fold_mostly && iRect.above_fold_fully),
            };
        }"""
    )


def run_audit(base_url: str, out_dir: Path) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    base_host = urlparse(base_url).netloc
    results: dict[str, Any] = {"base_url": base_url, "viewport": "1440x900", "pages": []}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            for item in PAGES:
                name = item["name"]
                route = item["route"]
                ctx = browser.new_context(viewport={"width": 1440, "height": 900})
                console_errors: list[str] = []
                page_errors: list[str] = []
                http_errors: list[str] = []
                external_reqs: list[str] = []

                def _intercept(route_obj: Any, _ext: list[str] = external_reqs) -> None:
                    req = route_obj.request
                    parsed = urlparse(req.url)
                    if parsed.scheme in {"data", "blob", "about"} or parsed.netloc == base_host:
                        route_obj.continue_()
                        return
                    if req.resource_type == "document" and parsed.hostname == "meet.jit.si":
                        route_obj.fulfill(
                            status=200,
                            content_type="text/html",
                            body="<!doctype html><html><body>Sandboxed Jitsi offline stub</body></html>",
                        )
                        return
                    _ext.append(req.url)
                    route_obj.abort("blockedbyclient")

                ctx.route("**/*", _intercept)
                page = ctx.new_page()
                page.set_default_timeout(15000)
                page.on("console", lambda m, ce=console_errors: ce.append(m.text) if m.type == "error" else None)
                page.on("pageerror", lambda e, pe=page_errors: pe.append(str(e)))
                page.on(
                    "response",
                    lambda r, he=http_errors: he.append(f"{r.status} {r.url}") if r.status >= 400 else None,
                )

                page.goto(f"{base_url}{route}", wait_until="networkidle")
                page.wait_for_timeout(400)

                metrics = _collect_page_metrics(page)
                metrics["name"] = name
                metrics["route"] = route
                metrics["file"] = item["file"]
                metrics["console_errors"] = console_errors
                metrics["page_errors"] = page_errors
                metrics["http_errors"] = http_errors
                metrics["external_requests"] = external_reqs

                above_path = out_dir / f"{name}_above_fold.png"
                full_path = out_dir / f"{name}_full.png"
                page.screenshot(path=str(above_path), full_page=False)
                page.screenshot(path=str(full_path), full_page=True)

                if name == "companion":
                    # Check default state AND expanded Orientation state
                    default_orient = _measure_companion_orientation_and_illustration(page)
                    metrics["companion_default_orientation"] = default_orient
                    # Ensure orientation is expanded for explicit verification
                    if default_orient.get("orientation_collapsed"):
                        page.locator("#toggleOrientationBtn").click()
                        page.wait_for_timeout(200)
                    expanded_orient = _measure_companion_orientation_and_illustration(page)
                    metrics["companion_expanded_orientation"] = expanded_orient
                    page.screenshot(
                        path=str(out_dir / "companion_orientation_expanded_above_fold.png"),
                        full_page=False,
                    )

                results["pages"].append(metrics)
                ctx.close()
        finally:
            browser.close()

    (out_dir / "telemetry.json").write_text(json.dumps(results, indent=2), encoding="utf-8")

    lines = [
        "# PDEUE UI/UX Audit Summary (`1440x900`)",
        "",
        "| Page | File | Height Ratio | Scroll H | Overflow | Vis/Tot Sections | Vis/Tot Controls | Above-Fold Controls | Errors |",
        "| :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for m in results["pages"]:
        err_count = len(m["console_errors"]) + len(m["page_errors"]) + len(m["http_errors"]) + len(m["external_requests"]) + len(m["cdn_tags"])
        lines.append(
            f"| `{m['name']}` | `{m['file']}` | {m['height_ratio']:.2f}x | {m['scroll_height']}px | {m['horizontal_overflow_px']}px | "
            f"{m['visible_sections']}/{m['total_sections']} | {m['visible_controls']}/{m['total_controls']} | "
            f"{m['above_fold_controls']} | {err_count} |"
        )
    comp = next((x for x in results["pages"] if x["name"] == "companion"), None)
    if comp and "companion_expanded_orientation" in comp:
        eo = comp["companion_expanded_orientation"]
        lines.extend(
            [
                "",
                "## Companion Orientation + Illustration Above-the-Fold Check (Expanded)",
                f"- Orientation rect: `{eo.get('orientation_rect')}`",
                f"- Illustration rect: `{eo.get('illustration_rect')}`",
                f"- Both visible above fold (`1440x900`): **`{eo.get('both_visible_above_fold')}`**",
            ]
        )
    (out_dir / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture PDEUE UI audit screenshots & telemetry.")
    parser.add_argument("--base-url", default="", help="Optional running FastAPI base URL")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR), help="Output directory for screenshots & telemetry")
    args = parser.parse_args()
    out_dir = Path(args.out_dir).resolve()

    if args.base_url:
        res = run_audit(args.base_url.rstrip("/"), out_dir)
    else:
        port = _find_free_port()
        base_url = f"http://127.0.0.1:{port}"
        with tempfile.TemporaryDirectory(prefix="pdeue_ui_audit_") as tmp_dir:
            db_path = Path(tmp_dir) / "pdeue_ui_audit.db"
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
                    raise RuntimeError("FastAPI server failed to boot within 25s")
                res = run_audit(base_url, out_dir)
            finally:
                proc.terminate()
                try:
                    proc.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    proc.kill()

    print((out_dir / "SUMMARY.md").read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
