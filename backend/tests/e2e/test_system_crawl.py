"""Milestone E2 — Automated Offline-Safe Playwright Full-System & Role Crawler.

Boots the live FastAPI server on 127.0.0.1 against an isolated temporary SQLite
database in fail-closed ``paper`` mode, discovers every registered HTML portal
route from ``/openapi.json``, audits each portal and role/tier view across
desktop (1440x900) and mobile (390x844) viewports, verifies role-siloing and
HTTP 403 boundaries, captures full-page screenshots, and writes a structured
JSON crawl inventory report.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile
import time
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

import pytest

playwright_sync = pytest.importorskip(
    "playwright.sync_api",
    reason="Playwright is required for E2E system crawl tests",
)
sync_playwright = playwright_sync.sync_playwright

pytestmark = pytest.mark.e2e

REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_DIR = REPO_ROOT / "backend"
ARTIFACTS_DIR = REPO_ROOT / "artifacts"
SCREENSHOTS_DIR = ARTIFACTS_DIR / "playwright_screenshots"
REPORT_PATH = ARTIFACTS_DIR / "playwright_crawl_report.json"

VIEWPORTS: dict[str, dict[str, int]] = {
    "desktop_1440x900": {"width": 1440, "height": 900},
    "mobile_390x844": {"width": 390, "height": 844},
}

EXPECTED_HTML_ROUTES = {
    "/home",
    "/dashboard",
    "/member",
    "/advisor",
    "/admin/tech",
    "/login",
    "/companion",
    "/lineage/house/{house_id}",
    "/lineage/house",
    "/community",
    "/community/heritage",
    "/community/heritage/tree",
    "/community/heritage/house/{house_id}",
    "/community/heritage/surname/{slug}",
}

# Explicitly allowed sandboxed iframe host on /community (Milestone G3 / Wave 2C).
# Intercepted locally offline so the crawler never makes outbound internet requests.
ALLOWED_SANDBOXED_IFRAME_HOSTS: dict[str, set[str]] = {
    "/community": {"meet.jit.si"},
}


@dataclass(frozen=True)
class CrawlTarget:
    """Concrete URL + role/security audit expectations for a portal view."""

    slug: str
    path: str
    route_template: str
    role_scope: str
    forbidden_visible_href_prefixes: tuple[str, ...] = ()
    check_nav_only: bool = False
    desktop_tab_selectors: tuple[tuple[str, str], ...] = ()
    expect_r12_masked: bool = False


CRAWL_TARGETS: tuple[CrawlTarget, ...] = (
    CrawlTarget(
        slug="dashboard_admin",
        path="/dashboard",
        route_template="/dashboard",
        role_scope="CHIEF_ADMINISTRATOR",
        desktop_tab_selectors=(
            ("tab2_lineage", "#tab-btn-2"),
            ("tab3_radar", "#tab-btn-3"),
            ("tab4_governance", "#tab-btn-4"),
        ),
    ),
    CrawlTarget(
        slug="member_desktop",
        path="/member",
        route_template="/member",
        role_scope="CLASS_M_MEMBER",
        forbidden_visible_href_prefixes=("/dashboard", "/advisor", "/admin/tech", "/lineage/house"),
        desktop_tab_selectors=(("engine_view", "#tabBtnEngine"),),
    ),
    CrawlTarget(
        slug="advisor_f2h",
        path="/advisor",
        route_template="/advisor",
        role_scope="CLASS_F_F2H",
        forbidden_visible_href_prefixes=("/dashboard", "/member", "/admin/tech", "/lineage/house"),
    ),
    CrawlTarget(
        slug="advisor_f1",
        path="/advisor?role=F1",
        route_template="/advisor",
        role_scope="CLASS_F_F1",
        forbidden_visible_href_prefixes=("/dashboard", "/member", "/admin/tech", "/lineage/house"),
    ),
    CrawlTarget(
        slug="advisor_f2a",
        path="/advisor?role=F2-A",
        route_template="/advisor",
        role_scope="CLASS_F_F2A",
        forbidden_visible_href_prefixes=("/dashboard", "/member", "/admin/tech", "/lineage/house"),
    ),
    CrawlTarget(
        slug="advisor_f3",
        path="/advisor?role=F3",
        route_template="/advisor",
        role_scope="CLASS_F_F3",
        forbidden_visible_href_prefixes=("/dashboard", "/member", "/admin/tech", "/lineage/house"),
    ),
    CrawlTarget(
        slug="tech_t3",
        path="/admin/tech",
        route_template="/admin/tech",
        role_scope="CLASS_T_T3",
        forbidden_visible_href_prefixes=("/dashboard", "/member", "/advisor", "/lineage/house"),
        expect_r12_masked=True,
    ),
    CrawlTarget(
        slug="tech_t1",
        path="/admin/tech?tier=T1",
        route_template="/admin/tech",
        role_scope="CLASS_T_T1",
        forbidden_visible_href_prefixes=("/dashboard", "/member", "/advisor", "/lineage/house"),
        expect_r12_masked=True,
    ),
    CrawlTarget(
        slug="tech_t2",
        path="/admin/tech?tier=T2",
        route_template="/admin/tech",
        role_scope="CLASS_T_T2",
        forbidden_visible_href_prefixes=("/dashboard", "/member", "/advisor", "/lineage/house"),
        expect_r12_masked=True,
    ),
    CrawlTarget(
        slug="companion_university",
        path="/companion",
        route_template="/companion",
        role_scope="SHARED_UNIVERSITY",
        desktop_tab_selectors=(("colleges_manuals", 'button.tab[data-panel="colleges"]'),),
    ),
    CrawlTarget(
        slug="lineage_house_1_h2",
        path="/lineage/house/1",
        route_template="/lineage/house/{house_id}",
        role_scope="CLASS_H_H2",
        forbidden_visible_href_prefixes=("/dashboard", "/member", "/advisor", "/admin/tech"),
    ),
    CrawlTarget(
        slug="lineage_house_1_h1",
        path="/lineage/house/1?role=H1",
        route_template="/lineage/house/{house_id}",
        role_scope="CLASS_H_H1",
        forbidden_visible_href_prefixes=("/dashboard", "/member", "/advisor", "/admin/tech"),
        expect_r12_masked=True,
    ),
    CrawlTarget(
        slug="lineage_house_legacy",
        path="/lineage/house?house_id=1",
        route_template="/lineage/house",
        role_scope="CLASS_H_LEGACY",
        forbidden_visible_href_prefixes=("/dashboard", "/advisor", "/admin/tech"),
        check_nav_only=False,
    ),
    CrawlTarget(
        slug="community_hearth",
        path="/community",
        route_template="/community",
        role_scope="CLASS_C_COMMUNITY",
        forbidden_visible_href_prefixes=("/dashboard", "/member", "/advisor", "/admin/tech", "/lineage/house"),
        desktop_tab_selectors=(
            ("charter", 'button.tab[data-tab="charter"]'),
            ("classroom", 'button.tab[data-tab="classroom"]'),
            ("academy", 'button.tab[data-tab="academy"]'),
        ),
    ),
    CrawlTarget(
        slug="family_home_hub",
        path="/home",
        route_template="/home",
        role_scope="CLASS_M_HOME_HUB",
        forbidden_visible_href_prefixes=("/dashboard", "/advisor", "/admin/tech", "/lineage/house"),
    ),
    CrawlTarget(
        slug="hall_of_arms_heritage",
        path="/community/heritage",
        route_template="/community/heritage",
        role_scope="CLASS_C_HERITAGE",
        forbidden_visible_href_prefixes=("/dashboard", "/member", "/advisor", "/admin/tech", "/lineage/house"),
    ),
    CrawlTarget(
        slug="interactive_family_tree",
        path="/community/heritage/tree",
        route_template="/community/heritage/tree",
        role_scope="CLASS_C_HERITAGE_TREE",
        forbidden_visible_href_prefixes=("/dashboard", "/member", "/advisor", "/admin/tech", "/lineage/house"),
    ),
    CrawlTarget(
        slug="heritage_house_01_history",
        path="/community/heritage/house/1",
        route_template="/community/heritage/house/{house_id}",
        role_scope="CLASS_C_HERITAGE_HOUSE",
        forbidden_visible_href_prefixes=("/dashboard", "/member", "/advisor", "/admin/tech", "/lineage/house"),
    ),
    CrawlTarget(
        slug="heritage_surname_carmichael",
        path="/community/heritage/surname/carmichael",
        route_template="/community/heritage/surname/{slug}",
        role_scope="CLASS_C_HERITAGE_SURNAME",
        forbidden_visible_href_prefixes=("/dashboard", "/member", "/advisor", "/admin/tech", "/lineage/house"),
    ),
    CrawlTarget(
        slug="private_family_login",
        path="/login",
        route_template="/login",
        role_scope="PRIVATE_LOGIN_ALLOWLIST",
        forbidden_visible_href_prefixes=("/dashboard", "/member", "/advisor", "/admin/tech", "/lineage/house"),
    ),
)


@dataclass
class _CrawlState:
    discovered_html_routes: list[str] = field(default_factory=list)
    route_reports: dict[str, dict[str, Any]] = field(default_factory=dict)
    unauthorized_checks: list[dict[str, Any]] = field(default_factory=list)


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


def _discover_html_routes(base_url: str) -> list[str]:
    status, body = _http_request(f"{base_url}/openapi.json", timeout=5.0)
    assert status == 200, f"Failed to fetch /openapi.json (HTTP {status})"
    spec = json.loads(body)
    html_routes: list[str] = []
    for path, methods in spec.get("paths", {}).items():
        get_op = methods.get("get")
        if not isinstance(get_op, dict):
            continue
        ok_content = get_op.get("responses", {}).get("200", {}).get("content", {})
        if "text/html" in ok_content:
            html_routes.append(path)
    return sorted(html_routes)


def _extract_page_audit(page: Any) -> dict[str, Any]:
    """Collect links, assets, interactive controls, and dead/stub candidates from live DOM."""
    return page.evaluate(
        """() => {
            const isVisible = (el) => {
                if (!el) return false;
                if (el.closest('[hidden]')) return false;
                const style = window.getComputedStyle(el);
                if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') {
                    return false;
                }
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            };

            const externalCdnTags = [];
            for (const el of document.querySelectorAll('script[src], link[href]')) {
                const raw = el.getAttribute('src') || el.getAttribute('href') || '';
                if (/^https?:\\/\\//i.test(raw)) {
                    externalCdnTags.push({ tag: el.tagName.toLowerCase(), url: raw });
                }
            }

            const internalLinks = [];
            const visibleLinks = [];
            for (const a of document.querySelectorAll('a[href]')) {
                const href = (a.getAttribute('href') || '').trim();
                const visible = isVisible(a);
                const text = (a.textContent || '').replace(/\\s+/g, ' ').trim();
                if (visible) {
                    visibleLinks.push({ href, text, id: a.id || '' });
                }
                if (href && !href.startsWith('#') && !href.startsWith('mailto:') && !href.startsWith('javascript:')) {
                    internalLinks.push({ href, text, visible });
                }
            }

            const internalAssets = [];
            for (const el of document.querySelectorAll('img[src], script[src], link[rel="stylesheet"][href]')) {
                const attr = el.tagName === 'LINK' ? 'href' : 'src';
                const val = (el.getAttribute(attr) || '').trim();
                if (val && !val.startsWith('data:') && !val.startsWith('blob:')) {
                    internalAssets.push({
                        tag: el.tagName.toLowerCase(),
                        url: val,
                        brokenImage: el.tagName === 'IMG' ? (isVisible(el) && el.naturalWidth === 0) : false,
                    });
                }
            }

            const deferredMediaSources = [];
            for (const source of document.querySelectorAll('audio source[src], video source[src], audio[src], video[src]')) {
                const mediaEl = source.tagName === 'SOURCE' ? source.parentElement : source;
                deferredMediaSources.push({
                    tag: mediaEl ? mediaEl.tagName.toLowerCase() : 'media',
                    src: source.getAttribute('src') || '',
                    preload: mediaEl ? (mediaEl.getAttribute('preload') || '') : '',
                });
            }

            const legacyHub = document.getElementById('legacyPortalHub');
            const legacyHubVisible = legacyHub ? isVisible(legacyHub) : false;

            const controls = [];
            const deadOrStub = [];
            const selector = 'button, a[href], input, select, textarea, [role="button"], [role="tab"]';
            const stubPattern = /\\b(todo|tbd|coming soon|\\[stub\\])\\b/i;

            for (const el of document.querySelectorAll(selector)) {
                const tag = el.tagName.toLowerCase();
                const visible = isVisible(el);
                const id = el.id || '';
                const role = el.getAttribute('role') || '';
                const type = el.getAttribute('type') || '';
                const href = tag === 'a' ? (el.getAttribute('href') || '').trim() : '';
                const onclick = el.getAttribute('onclick') || '';
                const text = (el.textContent || '').replace(/\\s+/g, ' ').trim();
                const label = (
                    el.getAttribute('aria-label')
                    || el.getAttribute('title')
                    || el.getAttribute('placeholder')
                    || text
                    || id
                ).slice(0, 120);

                let reason = null;
                if (tag === 'a' && visible) {
                    if (href === '' || href === '#' || /^javascript:/i.test(href)) {
                        if (!onclick) reason = `dead_href:${href || 'empty'}`;
                    }
                }
                if (onclick && (/^\\s*$/.test(onclick) || /^\\s*return\\s+false;?\\s*$/i.test(onclick))) {
                    reason = 'empty_or_noop_onclick';
                }
                if (tag === 'button' && visible) {
                    if (!label) {
                        reason = 'unlabeled_visible_button';
                    } else if (stubPattern.test(label)) {
                        reason = 'stub_label';
                    }
                }

                const entry = {
                    tag,
                    id,
                    type,
                    role,
                    label,
                    href,
                    visible,
                    disabled: Boolean(el.disabled),
                    has_inline_handler: Boolean(onclick),
                    inside_form: Boolean(el.closest('form')),
                };
                if (reason) {
                    entry.dead_or_stub_reason = reason;
                    deadOrStub.push(entry);
                }
                controls.push(entry);
            }

            const iframes = [];
            for (const iframe of document.querySelectorAll('iframe')) {
                iframes.push({
                    src: iframe.getAttribute('src') || '',
                    sandbox: iframe.getAttribute('sandbox') || '',
                    title: iframe.getAttribute('title') || '',
                });
            }

            return {
                title: document.title,
                bodyTextSample: (document.body.innerText || '').slice(0, 4000),
                externalCdnTags,
                internalLinks,
                visibleLinks,
                internalAssets,
                deferredMediaSources,
                legacyHubVisible,
                controls,
                deadOrStub,
                iframes,
            };
        }"""
    )


def _write_report(state: _CrawlState) -> None:
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    routes_list = list(state.route_reports.values())
    total_controls = sum(len(item.get("controls", [])) for item in routes_list)
    total_dead = sum(len(item.get("dead_or_stub_elements", [])) for item in routes_list)
    total_console_errors = sum(len(item.get("console_errors", [])) for item in routes_list)
    total_page_errors = sum(len(item.get("page_errors", [])) for item in routes_list)
    total_failed_requests = sum(len(item.get("failed_requests", [])) for item in routes_list)
    total_external_cdn = sum(
        len(item.get("external_cdn_requests", [])) + len(item.get("dom_external_cdn_tags", []))
        for item in routes_list
    )
    total_broken_links = sum(len(item.get("broken_internal_links", [])) for item in routes_list)
    total_screenshots = sum(len(item.get("screenshots", [])) for item in routes_list)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "venue_mode": "paper",
        "database_mode": "isolated_temp_sqlite",
        "viewports": VIEWPORTS,
        "discovered_html_routes": state.discovered_html_routes,
        "summary": {
            "routes_audited": len(routes_list),
            "screenshots_captured": total_screenshots,
            "interactive_controls_inventoried": total_controls,
            "dead_or_stubbed_elements": total_dead,
            "console_errors": total_console_errors,
            "page_errors": total_page_errors,
            "failed_requests": total_failed_requests,
            "broken_internal_links_or_assets": total_broken_links,
            "external_cdn_violations": total_external_cdn,
            "unauthorized_403_checks": len(state.unauthorized_checks),
            "unauthorized_403_passed": sum(1 for c in state.unauthorized_checks if c["passed"]),
        },
        "routes": routes_list,
        "unauthorized_access_checks": state.unauthorized_checks,
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")


@pytest.fixture(scope="module")
def crawl_state() -> _CrawlState:
    state = _CrawlState()
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    yield state
    _write_report(state)


@pytest.fixture(scope="module")
def live_server() -> str:
    """Start the real FastAPI app on 127.0.0.1 with an isolated temp SQLite DB in paper mode."""
    port = _find_free_port()
    base_url = f"http://127.0.0.1:{port}"

    with tempfile.TemporaryDirectory(prefix="pdeue_playwright_e2e_") as tmp_dir:
        db_path = Path(tmp_dir) / "pdeue_e2e.db"
        mutex_path = Path(tmp_dir) / "pdeue_e2e_mutex.sqlite3"
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


def test_discover_all_registered_html_routes(live_server: str, crawl_state: _CrawlState) -> None:
    """Every registered HTML route from /openapi.json must be accounted for in the crawl matrix."""
    discovered = _discover_html_routes(live_server)
    crawl_state.discovered_html_routes = discovered

    missing_expected = EXPECTED_HTML_ROUTES - set(discovered)
    assert not missing_expected, f"Expected portal routes missing from OpenAPI: {sorted(missing_expected)}"

    covered_templates = {target.route_template for target in CRAWL_TARGETS}
    uncovered = set(discovered) - covered_templates
    assert not uncovered, f"Discovered HTML routes not covered by CRAWL_TARGETS: {sorted(uncovered)}"


@pytest.mark.parametrize("target", CRAWL_TARGETS, ids=lambda t: t.slug)
def test_crawl_portal_route_desktop_and_mobile(
    live_server: str,
    browser: Any,
    crawl_state: _CrawlState,
    target: CrawlTarget,
) -> None:
    """Audit HTTP status, JS errors, console errors, links/assets, zero-CDN, role-siloing, and screenshots."""
    base_host = urlparse(live_server).netloc
    route_entry: dict[str, Any] = {
        "slug": target.slug,
        "path": target.path,
        "route_template": target.route_template,
        "role_scope": target.role_scope,
        "status_by_viewport": {},
        "screenshots": [],
        "tabs_exercised": [],
        "console_errors": [],
        "page_errors": [],
        "failed_requests": [],
        "external_cdn_requests": [],
        "dom_external_cdn_tags": [],
        "sandboxed_iframes_intercepted": [],
        "broken_internal_links": [],
        "internal_links_checked": [],
        "deferred_media_sources": [],
        "visible_links": [],
        "controls": [],
        "dead_or_stub_elements": [],
    }
    crawl_state.route_reports[target.slug] = route_entry

    checked_internal_urls: dict[str, int] = {}

    for vp_name, vp_size in VIEWPORTS.items():
        context = browser.new_context(viewport=vp_size)
        allowed_iframe_hosts = ALLOWED_SANDBOXED_IFRAME_HOSTS.get(target.route_template, set())

        def _intercept(route: Any) -> None:
            req = route.request
            url = req.url
            parsed = urlparse(url)
            if parsed.scheme in {"data", "blob", "about"} or parsed.netloc == base_host:
                route.continue_()
                return
            if req.resource_type == "document" and parsed.hostname in allowed_iframe_hosts:
                route_entry["sandboxed_iframes_intercepted"].append(
                    {"viewport": vp_name, "url": url, "resource_type": req.resource_type}
                )
                route.fulfill(
                    status=200,
                    content_type="text/html",
                    body="<!doctype html><html><body>Sandboxed classroom offline stub</body></html>",
                )
                return
            route_entry["external_cdn_requests"].append(
                {"viewport": vp_name, "url": url, "resource_type": req.resource_type}
            )
            route.abort("blockedbyclient")

        context.route("**/*", _intercept)
        page = context.new_page()
        page.set_default_timeout(15000)

        page.on(
            "console",
            lambda msg, vp=vp_name: route_entry["console_errors"].append(
                {"viewport": vp, "text": msg.text}
            )
            if msg.type == "error"
            else None,
        )
        page.on(
            "pageerror",
            lambda err, vp=vp_name: route_entry["page_errors"].append(
                {"viewport": vp, "error": str(err)}
            ),
        )
        page.on(
            "response",
            lambda resp, vp=vp_name: route_entry["failed_requests"].append(
                {"viewport": vp, "status": resp.status, "url": resp.url}
            )
            if resp.status >= 400
            else None,
        )
        page.on(
            "requestfailed",
            lambda req, vp=vp_name: route_entry["failed_requests"].append(
                {
                    "viewport": vp,
                    "status": 0,
                    "url": req.url,
                    "failure": req.failure,
                }
            )
            if urlparse(req.url).netloc == base_host
            and not (req.failure and "ERR_ABORTED" in str(req.failure))
            else None,
        )

        try:
            response = page.goto(f"{live_server}{target.path}", wait_until="networkidle", timeout=15000)
            assert response is not None, f"Navigation returned no response for {target.path}"
            route_entry["status_by_viewport"][vp_name] = response.status
            page.wait_for_timeout(350)

            screenshot_file = SCREENSHOTS_DIR / f"{target.slug}_{vp_name}.png"
            page.screenshot(path=str(screenshot_file), full_page=True)
            route_entry["screenshots"].append(str(screenshot_file.relative_to(REPO_ROOT)))

            audit = _extract_page_audit(page)
            for tag_hit in audit["externalCdnTags"]:
                route_entry["dom_external_cdn_tags"].append({"viewport": vp_name, **tag_hit})

            # Non-admin role siloing check on every viewport
            assert not audit["legacyHubVisible"], f"{target.path} ({vp_name}) exposed hidden #legacyPortalHub"
            for link in audit["visibleLinks"]:
                href_path = urlparse(link["href"]).path
                for forbidden in target.forbidden_visible_href_prefixes:
                    assert not (href_path == forbidden or href_path.startswith(f"{forbidden}/")), (
                        f"Cross-role nav bleed on {target.path} ({vp_name}): "
                        f"visible link {link['href']!r} ({link['text']!r}) matches forbidden {forbidden!r}"
                    )

            # Directive R-12 redaction check on masked portals
            if target.expect_r12_masked:
                assert "$****.**" in audit["bodyTextSample"], (
                    f"Expected Directive R-12 '$****.**' mask on {target.path} ({vp_name})"
                )
                if target.route_template == "/admin/tech":
                    assert "SCMA-MEM-****" in audit["bodyTextSample"], (
                        f"Expected masked SCMA-MEM-**** on {target.path} ({vp_name})"
                    )
                    assert "SCMA-ELEANOR_-B2B31C9E" not in audit["bodyTextSample"], (
                        f"Unredacted SCMA leaked on {target.path} ({vp_name}) without CA override"
                    )

            # Collect full control & link inventory once on desktop viewport
            if vp_name == "desktop_1440x900":
                route_entry["title"] = audit["title"]
                route_entry["visible_links"] = audit["visibleLinks"]
                route_entry["deferred_media_sources"] = audit["deferredMediaSources"]
                route_entry["controls"] = audit["controls"]
                route_entry["dead_or_stub_elements"] = audit["deadOrStub"]
                route_entry["iframes"] = audit["iframes"]

                # Verify sandbox attribute on any iframe present
                for iframe in audit["iframes"]:
                    assert iframe["sandbox"], f"Unsandboxed iframe found on {target.path}: {iframe}"

                # Verify every internal link and asset returns HTTP 200
                urls_to_check: list[str] = []
                for link in audit["internalLinks"]:
                    full = urljoin(f"{live_server}{target.path}", link["href"])
                    if urlparse(full).netloc == base_host:
                        urls_to_check.append(full)
                for asset in audit["internalAssets"]:
                    assert not asset["brokenImage"], f"Broken <img> on {target.path}: {asset}"
                    full = urljoin(f"{live_server}{target.path}", asset["url"])
                    if urlparse(full).netloc == base_host:
                        urls_to_check.append(full)

                for full_url in sorted(set(urls_to_check)):
                    if full_url not in checked_internal_urls:
                        code, _ = _http_request(full_url, timeout=5.0)
                        checked_internal_urls[full_url] = code
                    code = checked_internal_urls[full_url]
                    rel_url = full_url.removeprefix(live_server)
                    route_entry["internal_links_checked"].append({"url": rel_url, "status": code})
                    if code >= 400:
                        route_entry["broken_internal_links"].append({"url": rel_url, "status": code})

                # Exercise multi-tab portals on desktop to catch lazy-loaded tab JS/API errors
                for tab_slug, selector in target.desktop_tab_selectors:
                    locator = page.locator(selector).first
                    locator.click()
                    page.wait_for_timeout(450)
                    tab_shot = SCREENSHOTS_DIR / f"{target.slug}_{tab_slug}_desktop_1440x900.png"
                    page.screenshot(path=str(tab_shot), full_page=True)
                    route_entry["screenshots"].append(str(tab_shot.relative_to(REPO_ROOT)))
                    route_entry["tabs_exercised"].append(tab_slug)
        finally:
            context.close()

    # Final hard assertions for this route across all viewports and tabs
    for vp_name, status_code in route_entry["status_by_viewport"].items():
        assert status_code == 200, f"{target.path} ({vp_name}) returned HTTP {status_code}"
    assert route_entry["page_errors"] == [], f"Uncaught JS errors on {target.path}: {route_entry['page_errors']}"
    assert route_entry["console_errors"] == [], f"console.error on {target.path}: {route_entry['console_errors']}"
    assert route_entry["failed_requests"] == [], f"Failed HTTP requests on {target.path}: {route_entry['failed_requests']}"
    assert route_entry["external_cdn_requests"] == [], (
        f"Disallowed external/CDN network requests on {target.path}: {route_entry['external_cdn_requests']}"
    )
    assert route_entry["dom_external_cdn_tags"] == [], (
        f"External <script>/<link> tags in DOM on {target.path}: {route_entry['dom_external_cdn_tags']}"
    )
    assert route_entry["broken_internal_links"] == [], (
        f"Broken internal links/assets on {target.path}: {route_entry['broken_internal_links']}"
    )
    assert route_entry["dead_or_stub_elements"] == [], (
        f"Dead/stubbed interactive elements found on {target.path}: {route_entry['dead_or_stub_elements']}"
    )


def test_unauthorized_role_and_cross_house_403_isolation(
    live_server: str,
    browser: Any,
    crawl_state: _CrawlState,
) -> None:
    """Verify server-side HTTP 403 enforcement on unauthorized role and cross-house paths."""
    # 1. Browser-level navigation to cross-house HTML route must return HTTP 403
    context = browser.new_context(viewport=VIEWPORTS["desktop_1440x900"])
    try:
        page = context.new_page()
        resp = page.goto(f"{live_server}/lineage/house/1?actor_house_id=2", timeout=10000)
        assert resp is not None
        crawl_state.unauthorized_checks.append(
            {
                "name": "browser_cross_house_query_403",
                "method": "GET",
                "path": "/lineage/house/1?actor_house_id=2",
                "expected_status": 403,
                "actual_status": resp.status,
                "passed": resp.status == 403,
            }
        )
        assert resp.status == 403, f"Expected 403 for cross-house HTML request, got {resp.status}"
    finally:
        context.close()

    # 2. Header-scoped & role-scoped HTTP 403 checks across Class H, Class F, and Class T boundaries
    checks = [
        (
            "header_cross_house_html_403",
            "GET",
            "/lineage/house/2",
            {"X-House-ID": "1"},
            None,
        ),
        (
            "lineage_h1_vote_403",
            "POST",
            "/api/v1/portal/lineage/house/1/vote?role=H1",
            {"X-House-ID": "1"},
            {"proposal_id": "CFCP-2026-02", "vote": "AYE"},
        ),
        (
            "lineage_h1_circuit_breaker_403",
            "POST",
            "/api/v1/portal/lineage/house/1/circuit-breaker?role=H1",
            {"X-House-ID": "1"},
            {"scma_id": "SCMA-ELEANOR_-B2B31C9E", "action": "FREEZE_DIAL"},
        ),
        (
            "advisor_cross_household_403",
            "GET",
            "/api/v1/portal/advisor/household-tree?household_id=HOUSEHOLD-BETA&role=F2-H",
            {"X-Household-ID": "HOUSEHOLD-ALPHA"},
            None,
        ),
        (
            "advisor_f1_macro_risk_403",
            "GET",
            "/api/v1/portal/advisor/macro-risk?role=F1",
            {},
            None,
        ),
        (
            "tech_t1_trigger_daemon_403",
            "POST",
            "/api/v1/portal/tech/trigger-daemon?tier=T1",
            {},
            None,
        ),
    ]

    for name, method, path, headers, payload in checks:
        status, body = _http_request(
            f"{live_server}{path}",
            method=method,
            headers=headers,
            payload=payload,
            timeout=5.0,
        )
        passed = status == 403
        crawl_state.unauthorized_checks.append(
            {
                "name": name,
                "method": method,
                "path": path,
                "expected_status": 403,
                "actual_status": status,
                "passed": passed,
            }
        )
        assert passed, f"{name} ({method} {path}) expected HTTP 403, got {status}: {body}"
