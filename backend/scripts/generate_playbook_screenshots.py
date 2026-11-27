#!/usr/bin/env python3
"""Automated Annotated UI Screenshot Generator for PDEUE University Playbooks.

Boots an isolated fail-closed local FastAPI server (or attaches to --base-url),
navigates to curated live portal views/tabs/drawers across all 5 role classes,
injects a crisp high-contrast local SVG numbered-callout overlay (1, 2, 3...)
computed from live `getBoundingClientRect()` coordinates, and saves optimized
lightweight PNGs into `backend/app/static/media/playbooks/screenshots/`.

Zero external CDNs or live network calls are used.
"""
from __future__ import annotations

import argparse
from io import BytesIO
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse
from urllib.request import urlopen

from PIL import Image
from playwright.sync_api import sync_playwright

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
DEFAULT_OUT_DIR = REPO_ROOT / "backend" / "app" / "static" / "media" / "playbooks" / "screenshots"

# Curated, repo-friendly declarative shot-list covering all 5 role classes & all 9 portals.
SHOT_LIST: List[Dict[str, Any]] = [
    {
        "id": "home_hub",
        "filename": "home_hub.png",
        "route": "/home",
        "viewport": {"width": 1280, "height": 820},
        "full_page": False,
        "actions": [],
        "callouts": [
            {"badge": 1, "selector": "#textScaleGroup", "label": "Senior Text Scale (A | A+ | A++)"},
            {"badge": 2, "selector": "#doorwayMyAccount", "label": "My Account (/member)"},
            {"badge": 3, "selector": "#doorwayFamilyHearth", "label": "Family Hearth (/community)"},
            {"badge": 4, "selector": "#doorwayHallOfArms", "label": "Hall of Arms (/community/heritage)"},
            {"badge": 5, "selector": "#doorwayUniversity", "label": "PDEUE University (/companion)"},
        ],
    },
    {
        "id": "member_orientation_engine",
        "filename": "member_orientation_engine.png",
        "route": "/member",
        "viewport": {"width": 1280, "height": 900},
        "full_page": False,
        "actions": [
            {"type": "click", "selector": "#tabBtnEngine"},
            {"type": "wait", "ms": 350},
            {"type": "scroll_to", "selector": "#riskSlider", "offset_y": -180},
        ],
        "callouts": [
            {"badge": 1, "selector": "#fundingInstructionsCard", "label": "ADR-011 Air-Gap & EXT-REF Deposit Memo"},
            {"badge": 2, "selector": "#riskSlider", "label": "Downward-Only Risk Dial"},
            {"badge": 3, "selector": "#saveRiskBtn", "label": "Save Risk Dial"},
            {"badge": 4, "selector": "#distributionBtn", "label": "Directive R-15 Distribution Request"},
            {"badge": 5, "selector": "#tutorInput", "label": "Dual-Lane AI Literacy Tutor"},
            {"badge": 6, "selector": "#clearTutorBtn", "label": "Client-Only Clear Tutor"},
        ],
    },
    {
        "id": "member_shadow_hunch",
        "filename": "member_shadow_hunch.png",
        "route": "/member",
        "viewport": {"width": 1280, "height": 860},
        "full_page": False,
        "actions": [
            {"type": "click", "selector": "#tabBtnEngine"},
            {"type": "wait", "ms": 250},
            {"type": "open_details", "selector": "#shadowHunchStudioDetails"},
            {"type": "wait", "ms": 250},
            {"type": "scroll_to", "selector": "#shadowHunchStudioDetails", "offset_y": -24},
        ],
        "callouts": [
            {"badge": 1, "selector": "#memberHunchHypothesis", "label": "Grounded Hunch Input"},
            {"badge": 2, "selector": "#memberHunchVertical", "label": "Regulated Vertical Selector"},
            {"badge": 3, "selector": "#memberLoadExampleHunchBtn", "label": "Load Example Hunch"},
            {"badge": 4, "selector": "#memberEvalHunchBtn", "label": "Run 3-Point Validation Audit"},
            {"badge": 5, "selector": "#memberRefreshHunchesBtn", "label": "Refresh Shadow Ledger"},
        ],
    },
    {
        "id": "dashboard_tab1_executive",
        "filename": "dashboard_tab1_executive.png",
        "route": "/dashboard",
        "viewport": {"width": 1280, "height": 860},
        "full_page": False,
        "actions": [
            {"type": "click", "selector": "#tab-btn-1"},
            {"type": "wait", "ms": 350},
        ],
        "callouts": [
            {"badge": 1, "selector": "#openHatSwitchBtn", "label": "Active-Hat Switcher (R-06)"},
            {"badge": 2, "selector": "#emergencyKillSwitchBtn", "label": "Directive R-04 Global Kill Switch"},
            {"badge": 3, "selector": "#custodial-lookup-input", "label": "Scoped Custodial Lookup"},
            {"badge": 4, "selector": "#tab-btn-1", "label": "4-Tab Command Navigation"},
            {"badge": 5, "selector": "#dashboard-asset-rings-card", "label": "Concentric Asset Engine Rings"},
        ],
    },
    {
        "id": "dashboard_tab2_pools_onboarding",
        "filename": "dashboard_tab2_pools_onboarding.png",
        "route": "/dashboard",
        "viewport": {"width": 1280, "height": 860},
        "full_page": False,
        "actions": [
            {"type": "click", "selector": "#tab-btn-2"},
            {"type": "wait", "ms": 350},
            {"type": "scroll_to", "selector": "#tab-panel-2", "offset_y": -20},
        ],
        "callouts": [
            {"badge": 1, "selector": "#cfcp-balance", "label": "CFCP 10% Family Pool"},
            {"badge": 2, "selector": "#faep-balance", "label": "FAEP 3% Endowment Pool"},
            {"badge": 3, "selector": "#openOnboardModalBtn", "label": "+ Onboard Member Modal"},
            {"badge": 4, "selector": "#openBatchDrawerBtn", "label": "Batch CSV/JSON Ingest"},
            {"badge": 5, "selector": "#lineage-house-tree", "label": "12-House Lineage Sub-Ledgers"},
        ],
    },
    {
        "id": "dashboard_tab3_velocity_hunch",
        "filename": "dashboard_tab3_velocity_hunch.png",
        "route": "/dashboard",
        "viewport": {"width": 1280, "height": 880},
        "full_page": False,
        "actions": [
            {"type": "click", "selector": "#tab-btn-3"},
            {"type": "wait", "ms": 350},
            {"type": "scroll_to", "selector": "#tab-panel-3", "offset_y": -20},
        ],
        "callouts": [
            {"badge": 1, "selector": "#wf-strat-d-equity", "label": "Walk-Forward Strategy D Equity"},
            {"badge": 2, "selector": "#adminHunchHypothesis", "label": "Admin Shadow Hunch Input"},
            {"badge": 3, "selector": "#adminLoadExampleHunchBtn", "label": "Load Example Hunch"},
            {"badge": 4, "selector": "#adminEvalHunchBtn", "label": "Run 3-Point Validation"},
            {"badge": 5, "selector": "#adminShadowBidBtn", "label": "Stage Shadow Paper Bid"},
        ],
    },
    {
        "id": "dashboard_tab4_governance",
        "filename": "dashboard_tab4_governance.png",
        "route": "/dashboard",
        "viewport": {"width": 1280, "height": 900},
        "full_page": False,
        "actions": [
            {"type": "click", "selector": "#tab-btn-4"},
            {"type": "wait", "ms": 350},
            {"type": "scroll_to", "selector": "#tab-panel-4", "offset_y": -16},
        ],
        "callouts": [
            {"badge": 1, "selector": "#btn-mode-executive", "label": "Stage 1: Executive Command"},
            {"badge": 2, "selector": "#btn-mode-advisory", "label": "Stage 2: Advisory Filter"},
            {"badge": 3, "selector": "#btn-mode-bicameral", "label": "Stage 3: Bicameral Veto"},
            {"badge": 4, "selector": "#btn-shtf-snapback", "label": "1-Click SHTF Snap-Back"},
            {"badge": 5, "selector": "#btn-grant-seat", "label": "Grant Enclave Voter / Veto Seat"},
        ],
    },
    {
        "id": "advisor_f2h_f3_desk",
        "filename": "advisor_f2h_f3_desk.png",
        "route": "/advisor?role=F3",
        "viewport": {"width": 1280, "height": 900},
        "full_page": False,
        "actions": [
            {"type": "wait", "ms": 350},
            {"type": "scroll_to", "selector": "#custodial-lookup-bar", "offset_y": -16},
        ],
        "callouts": [
            {"badge": 1, "selector": "#custodial-lookup-input", "label": "Scoped Fiduciary Lookup"},
            {"badge": 2, "selector": "#trigger-r04-halt-btn", "label": "CRO Directive R-04 Halt"},
            {"badge": 3, "selector": "#submit-dual-sig-btn", "label": "Dual-Signature Override"},
            {"badge": 4, "selector": "#macro-risk", "label": "12-House Macro-Risk & 99% VaR"},
            {"badge": 5, "selector": "#proposal-queue", "label": "F2-A Proposal Adjudication Queue"},
        ],
    },
    {
        "id": "admin_tech_t3_desk",
        "filename": "admin_tech_t3_desk.png",
        "route": "/admin/tech?tier=T3",
        "viewport": {"width": 1280, "height": 900},
        "full_page": False,
        "actions": [
            {"type": "wait", "ms": 350},
            {"type": "scroll_to", "selector": "#tier-scope-banner", "offset_y": -110},
        ],
        "callouts": [
            {"badge": 1, "selector": "#grant", "label": "Audited CA R-12 Override"},
            {"badge": 2, "selector": "#tier-scope-banner", "label": "Class T Tier Scope (T1/T2/T3)"},
            {"badge": 3, "selector": "#custodial-lookup-input", "label": "R-12 Masked Lookup ($****.**)"},
            {"badge": 4, "selector": "#trigger-daemon", "label": "Scan Daemon Control"},
            {"badge": 5, "selector": "#techCopilotCard", "label": "Read-Only Tech Copilot"},
        ],
    },
    {
        "id": "lineage_house1_h2_desk",
        "filename": "lineage_house1_h2_desk.png",
        "route": "/lineage/house/1?role=H2",
        "viewport": {"width": 1280, "height": 900},
        "full_page": False,
        "actions": [
            {"type": "wait", "ms": 350},
            {"type": "scroll_to", "selector": "#custodial-lookup-bar", "offset_y": -110},
        ],
        "callouts": [
            {"badge": 1, "selector": "#custodial-lookup-input", "label": "Scoped House Custodial Lookup"},
            {"badge": 2, "selector": "#desk-governance-mode", "label": "Active Constitutional Stage"},
            {"badge": 3, "selector": ".immune-badge", "label": "Founder Sovereign Immunity"},
            {"badge": 4, "selector": "button.freeze", "label": "Surgical Freeze Dial (0%)"},
            {"badge": 5, "selector": "button.cancel", "label": "Surgical Cancel Orders"},
            {"badge": 6, "selector": "#bicameral", "label": "Bicameral Ratification Chamber"},
        ],
    },
    {
        "id": "community_hearth",
        "filename": "community_hearth.png",
        "route": "/community",
        "viewport": {"width": 1280, "height": 900},
        "full_page": False,
        "actions": [
            {"type": "wait", "ms": 350},
            {"type": "click", "selector": ".tab[data-tab='academy']"},
            {"type": "wait", "ms": 300},
            {"type": "scroll_to", "selector": "#benefactorWelcomeBanner", "offset_y": -20},
        ],
        "callouts": [
            {"badge": 1, "selector": "#benefactorWelcomeBanner", "label": "Benefactor Welcome & Social Wall"},
            {"badge": 2, "selector": ".tab[data-tab='hearth']", "label": "Lineage Hearth & Board Tab"},
            {"badge": 3, "selector": ".tab[data-tab='classroom']", "label": "Sandboxed Jitsi Classroom Tab"},
            {"badge": 4, "selector": "#tutorQuery", "label": "Dual-Lane AI Tutor"},
            {"badge": 5, "selector": "#clearCommunityTutorBtn", "label": "Zero-Network Clear Tutor"},
        ],
    },
    {
        "id": "heritage_hall_of_arms",
        "filename": "heritage_hall_of_arms.png",
        "route": "/community/heritage#genealogist-desk",
        "viewport": {"width": 1280, "height": 900},
        "full_page": False,
        "actions": [
            {"type": "wait", "ms": 400},
            {"type": "open_details", "selector": "#genealogistDeskDrawer"},
            {"type": "wait", "ms": 200},
            {"type": "scroll_to", "selector": "#genealogist-desk", "offset_y": -40},
        ],
        "callouts": [
            {"badge": 1, "selector": "#editHouseId", "label": "Assigned House Selector (1-12)"},
            {"badge": 2, "selector": "#editHouseMotto", "label": "House Motto Editor"},
            {"badge": 3, "selector": "#saveHouseHistoryBtn", "label": "Save House Chronicle (403-Scoped)"},
            {"badge": 4, "selector": "#editSurnameName", "label": "Allied Surname Editor"},
            {"badge": 5, "selector": "#saveSurnameBioBtn", "label": "Save Surname Biography"},
        ],
    },
    {
        "id": "companion_university",
        "filename": "companion_university.png",
        "route": "/companion",
        "viewport": {"width": 1280, "height": 860},
        "full_page": False,
        "actions": [
            {"type": "wait", "ms": 400},
        ],
        "callouts": [
            {"badge": 1, "selector": "#tabCollegesBtn", "label": "Degree Colleges (5 Canonical Manuals)"},
            {"badge": 2, "selector": "#tabLibraryBtn", "label": "Deep-Dive & Role Playbook Library"},
            {"badge": 3, "selector": "#playOrientationBtn", "label": "30-Second Studio Orientation"},
            {"badge": 4, "selector": "#voiceSelect", "label": "Local Studio Mentor Voices (Maya/Marcus)"},
            {"badge": 5, "selector": "#profitCents", "label": "Interactive 87/10/3 + HWM Simulator"},
        ],
    },
]


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _optimize_png_bytes(raw_png: bytes) -> bytes:
    """Losslessly or cleanly palette-optimize PNG to keep repository footprint compact."""
    with Image.open(BytesIO(raw_png)) as im:
        rgb = im.convert("RGB")
        # 256-color median-cut palette preserves crisp dark-navy UI, text, and gold callouts at ~3-4x smaller size
        quantized = rgb.quantize(colors=256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
        buf = BytesIO()
        quantized.save(buf, format="PNG", optimize=True)
        optimized = buf.getvalue()
        return optimized if len(optimized) < len(raw_png) else raw_png


def _inject_svg_callouts(page: Any, callouts: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute live getBoundingClientRect() positions and inject a high-contrast local SVG overlay."""
    return page.evaluate(
        """(callouts) => {
            const old = document.getElementById('pdeue-playbook-callout-overlay');
            if (old) old.remove();

            const vw = window.innerWidth;
            const vh = window.innerHeight;
            const ns = 'http://www.w3.org/2000/svg';
            const svg = document.createElementNS(ns, 'svg');
            svg.setAttribute('id', 'pdeue-playbook-callout-overlay');
            svg.setAttribute('width', String(vw));
            svg.setAttribute('height', String(vh));
            svg.setAttribute('viewBox', `0 0 ${vw} ${vh}`);
            svg.style.position = 'fixed';
            svg.style.top = '0';
            svg.style.left = '0';
            svg.style.width = vw + 'px';
            svg.style.height = vh + 'px';
            svg.style.pointerEvents = 'none';
            svg.style.zIndex = '999999';

            const matched = [];
            const missing = [];
            const placedBadges = [];

            for (const item of callouts) {
                const el = document.querySelector(item.selector);
                if (!el) {
                    missing.push(item.selector);
                    continue;
                }
                const rect = el.getBoundingClientRect();
                if (rect.width <= 0 || rect.height <= 0) {
                    missing.push(item.selector + ' (hidden)');
                    continue;
                }

                // Clamp visible highlight frame into viewport
                const x = Math.max(4, Math.min(vw - 12, rect.left - 3));
                const y = Math.max(4, Math.min(vh - 12, rect.top - 3));
                const w = Math.max(16, Math.min(vw - x - 4, rect.width + 6));
                const h = Math.max(16, Math.min(vh - y - 4, rect.height + 6));

                // Highlight box
                const box = document.createElementNS(ns, 'rect');
                box.setAttribute('x', String(x));
                box.setAttribute('y', String(y));
                box.setAttribute('width', String(w));
                box.setAttribute('height', String(h));
                box.setAttribute('rx', '7');
                box.setAttribute('fill', 'rgba(251, 191, 36, 0.10)');
                box.setAttribute('stroke', '#FCD34D');
                box.setAttribute('stroke-width', '2.5');
                box.setAttribute('stroke-dasharray', '7,4');
                svg.appendChild(box);

                // Badge circle position (avoid overlap with previously placed badges)
                let cx = Math.max(18, Math.min(vw - 18, x + 2));
                let cy = Math.max(18, Math.min(vh - 18, y - 4));
                for (let tries = 0; tries < 6; tries++) {
                    const collides = placedBadges.some(p => Math.hypot(p.cx - cx, p.cy - cy) < 28);
                    if (!collides) break;
                    cx = Math.min(vw - 18, cx + 28);
                }
                placedBadges.push({ cx, cy });

                const halo = document.createElementNS(ns, 'circle');
                halo.setAttribute('cx', String(cx));
                halo.setAttribute('cy', String(cy));
                halo.setAttribute('r', '15');
                halo.setAttribute('fill', '#0B132B');
                svg.appendChild(halo);

                const circle = document.createElementNS(ns, 'circle');
                circle.setAttribute('cx', String(cx));
                circle.setAttribute('cy', String(cy));
                circle.setAttribute('r', '13');
                circle.setAttribute('fill', '#F59E0B');
                circle.setAttribute('stroke', '#FEF3C7');
                circle.setAttribute('stroke-width', '2');
                svg.appendChild(circle);

                const txt = document.createElementNS(ns, 'text');
                txt.setAttribute('x', String(cx));
                txt.setAttribute('y', String(cy + 4.5));
                txt.setAttribute('text-anchor', 'middle');
                txt.setAttribute('fill', '#0B132B');
                txt.setAttribute('font-family', 'system-ui, -apple-system, sans-serif');
                txt.setAttribute('font-size', '13');
                txt.setAttribute('font-weight', '900');
                txt.textContent = String(item.badge);
                svg.appendChild(txt);

                matched.push({
                    badge: item.badge,
                    selector: item.selector,
                    label: item.label,
                    rect: { x: Math.round(x), y: Math.round(y), w: Math.round(w), h: Math.round(h) },
                });
            }

            document.body.appendChild(svg);
            return { matched, missing };
        }""",
        callouts,
    )


def _apply_actions(page: Any, actions: List[Dict[str, Any]]) -> None:
    for act in actions:
        kind = act.get("type")
        if kind == "click":
            page.locator(act["selector"]).first.click()
        elif kind == "wait":
            page.wait_for_timeout(int(act.get("ms", 250)))
        elif kind == "open_details":
            page.evaluate(
                "(sel) => { const d = document.querySelector(sel); if (d) d.open = true; }",
                act["selector"],
            )
        elif kind == "scroll_to":
            offset_y = int(act.get("offset_y", -24))
            page.evaluate(
                """([sel, offsetY]) => {
                    const el = document.querySelector(sel);
                    if (!el) return;
                    const top = el.getBoundingClientRect().top + window.scrollY + offsetY;
                    window.scrollTo({ top: Math.max(0, top), behavior: 'instant' });
                }""",
                [act["selector"], offset_y],
            )
            page.wait_for_timeout(150)


def generate_playbook_screenshots(
    base_url: str,
    out_dir: Path = DEFAULT_OUT_DIR,
    only_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    base_host = urlparse(base_url).netloc
    shots = [s for s in SHOT_LIST if not only_ids or s["id"] in set(only_ids)]
    if not shots:
        raise ValueError(f"No matching shots found for {only_ids}")

    report: Dict[str, Any] = {"base_url": base_url, "out_dir": str(out_dir), "shots": []}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            for shot in shots:
                vp = shot.get("viewport", {"width": 1280, "height": 860})
                ctx = browser.new_context(viewport=vp)
                console_errors: List[str] = []
                page_errors: List[str] = []
                external_reqs: List[str] = []

                def _intercept(route_obj: Any, _ext: List[str] = external_reqs) -> None:
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

                page.goto(f"{base_url}{shot['route']}", wait_until="networkidle")
                page.wait_for_timeout(350)
                _apply_actions(page, shot.get("actions", []))

                callout_res = _inject_svg_callouts(page, shot.get("callouts", []))
                page.wait_for_timeout(120)

                raw_png = page.screenshot(full_page=bool(shot.get("full_page", False)))
                optimized_png = _optimize_png_bytes(raw_png)
                dest = out_dir / shot["filename"]
                dest.write_bytes(optimized_png)

                report["shots"].append(
                    {
                        "id": shot["id"],
                        "filename": shot["filename"],
                        "route": shot["route"],
                        "bytes": len(optimized_png),
                        "matched_callouts": len(callout_res["matched"]),
                        "missing_callouts": callout_res["missing"],
                        "console_errors": console_errors,
                        "page_errors": page_errors,
                        "external_requests": external_reqs,
                    }
                )
                ctx.close()
        finally:
            browser.close()

    return report


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Generate curated annotated UI playbook screenshots.")
    parser.add_argument("--base-url", default="", help="Optional running FastAPI base URL")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR), help="Output directory for PNG screenshots")
    parser.add_argument("--only", default="", help="Optional comma-separated shot IDs to generate")
    args = parser.parse_args(argv)

    out_dir = Path(args.out_dir).resolve()
    only_ids = [s.strip() for s in args.only.split(",") if s.strip()] or None

    if args.base_url:
        report = generate_playbook_screenshots(args.base_url.rstrip("/"), out_dir=out_dir, only_ids=only_ids)
    else:
        port = _find_free_port()
        base_url = f"http://127.0.0.1:{port}"
        with tempfile.TemporaryDirectory(prefix="pdeue_playbook_shots_") as tmp_dir:
            db_path = Path(tmp_dir) / "pdeue_playbooks.db"
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
                report = generate_playbook_screenshots(base_url, out_dir=out_dir, only_ids=only_ids)
            finally:
                proc.terminate()
                try:
                    proc.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    proc.kill()

    total_kb = sum(s["bytes"] for s in report["shots"]) / 1024.0
    print(f"[PDEUE Playbook Screenshots] generated={len(report['shots'])} total_kb={total_kb:.1f} out_dir={out_dir}")
    for s in report["shots"]:
        print(
            f"  - {s['filename']}: {s['bytes']/1024.0:.1f} KB | callouts={s['matched_callouts']} "
            f"| missing={s['missing_callouts']} | errors={len(s['console_errors'])+len(s['page_errors'])+len(s['external_requests'])}"
        )
    missing_any = [s for s in report["shots"] if s["missing_callouts"] or s["console_errors"] or s["page_errors"] or s["external_requests"]]
    if missing_any:
        print(json.dumps(missing_any, indent=2), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
