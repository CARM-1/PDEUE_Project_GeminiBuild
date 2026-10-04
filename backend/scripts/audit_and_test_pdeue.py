#!/usr/bin/env python3
"""Discover portal controls, verify API wires, and emit the WP-6F audit log."""

from __future__ import annotations

import argparse
import re
import sys
from html import escape
from html.parser import HTMLParser
from pathlib import Path
from time import perf_counter
from typing import Any

from fastapi.testclient import TestClient


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = BACKEND_ROOT.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.main import app  # noqa: E402
from app.domain.lineage_hierarchy import get_lineage_service  # noqa: E402


PORTAL_ROUTES = ("/member", "/dashboard", "/advisor", "/admin/tech")
REPORT_PATH = REPOSITORY_ROOT / "docs" / "PDEUE_SYSTEM_FUNCTIONALITY_AUDIT.md"
INTERACTIVE_TAGS = {"button", "a", "input", "select"}


class ControlParser(HTMLParser):
    """Small dependency-free DOM control inventory parser."""

    def __init__(self, source: str) -> None:
        super().__init__(convert_charrefs=True)
        self.source = source
        self.controls: list[dict[str, Any]] = []
        self._stack: list[tuple[str, bool, bool]] = []
        self._active: list[dict[str, Any]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key: (value or "") for key, value in attrs}
        parent_hidden = self._stack[-1][1] if self._stack else False
        parent_form = self._stack[-1][2] if self._stack else False
        hidden = parent_hidden or "hidden" in values or values.get("aria-hidden") == "true"
        in_form = parent_form or tag == "form"
        is_void = tag in {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
        if not is_void:
            self._stack.append((tag, hidden, in_form))

        classes = values.get("class", "").split()
        class_control = any(name == "btn" or "btn" in name or name == "switch-btn" for name in classes)
        role_control = values.get("role") in {"button", "tab"}
        if not hidden and (tag in INTERACTIVE_TAGS or class_control or role_control):
            control = {"tag": tag, "attrs": values, "text": [], "in_form": in_form}
            self.controls.append(control)
            if not is_void:
                self._active.append(control)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_data(self, data: str) -> None:
        for control in self._active:
            control["text"].append(data)

    def handle_endtag(self, tag: str) -> None:
        for index in range(len(self._active) - 1, -1, -1):
            if self._active[index]["tag"] == tag:
                self._active.pop(index)
                break
        for index in range(len(self._stack) - 1, -1, -1):
            if self._stack[index][0] == tag:
                del self._stack[index:]
                break


def _has_script_hook(control: dict[str, Any], source: str) -> bool:
    attrs = control["attrs"]
    if attrs.get("onclick") or attrs.get("onchange") or attrs.get("onsubmit"):
        return True
    identifier = attrs.get("id")
    if identifier:
        quoted = re.escape(identifier)
        patterns = (
            rf"getElementById\(['\"]{quoted}['\"]\)",
            rf"\$\(['\"]{quoted}['\"]\)",
            rf"\b{quoted}\.addEventListener\(",
        )
        if any(re.search(pattern, source) for pattern in patterns):
            return True
    if any(key.startswith("data-") for key in attrs):
        return True
    return False


def audit_controls(route: str, html: str) -> list[dict[str, str]]:
    parser = ControlParser(html)
    parser.feed(html)
    rows: list[dict[str, str]] = []
    blocking = bool(re.search(r"\b(?:alert|confirm)\s*\(", html))
    stub_copy = "[STUB]" in html.upper()

    for control in parser.controls:
        tag, attrs = control["tag"], control["attrs"]
        label = " ".join("".join(control["text"]).split())
        label = label or attrs.get("aria-label") or attrs.get("title") or attrs.get("placeholder") or attrs.get("id") or "(unlabelled)"
        href = attrs.get("href")
        hook = attrs.get("onclick") or attrs.get("onchange")
        if href is not None:
            target = href or "(empty href)"
        elif hook:
            target = hook
        elif attrs.get("type") == "submit" and control["in_form"]:
            target = "form submit"
        elif _has_script_hook(control, html):
            target = "JavaScript event listener"
        elif tag in {"input", "select"}:
            target = f"native {attrs.get('type', tag)} control"
        else:
            target = "—"

        dead = False
        detail = "Control has a navigable or event-driven target."
        if tag == "a" and (not href or href.strip() == "#"):
            dead, detail = True, "Link has an empty or placeholder href."
        elif tag == "button" and target == "—" and "disabled" not in attrs:
            dead, detail = True, "Button has no inline, form, or registered JavaScript hook."
        elif tag not in INTERACTIVE_TAGS and target == "—":
            dead, detail = True, "Button-styled/ARIA control has no interaction hook."
        elif "[STUB]" in label.upper() or stub_copy and "stub" in label.lower():
            dead, detail = True, "Control is associated with [STUB] placeholder copy."
        status = "FAIL" if dead else "PASS"
        blocking_hook = "alert(" in (hook or "") or "confirm(" in (hook or "")
        called_function = re.match(r"\s*([A-Za-z_$][\w$]*)\s*\(", hook or "")
        if blocking and called_function:
            definition = re.search(rf"function\s+{re.escape(called_function.group(1))}\s*\([^)]*\)", html)
            if definition and re.search(r"\b(?:alert|confirm)\s*\(", html[definition.end():definition.end() + 1500]):
                blocking_hook = True
        if not dead and blocking_hook:
            status, detail = "WARN", "Control invokes a synchronous alert/confirm dialog."
        rows.append({"route": route, "tag": tag, "label": label, "target": target, "status": status, "detail": detail})
    return rows


def _request(client: TestClient, method: str, endpoint: str, **kwargs: Any) -> dict[str, str]:
    started = perf_counter()
    response = client.request(method, endpoint, **kwargs)
    latency = (perf_counter() - started) * 1000
    return {
        "endpoint": f"{method} {endpoint}",
        "status": str(response.status_code),
        "latency": f"{latency:.2f} ms",
        "verdict": "PASS" if response.status_code in {200, 201} else "FAIL",
    }


def verify_api_wires(client: TestClient) -> list[dict[str, str]]:
    state_path = "/api/v1/portal/member/state?scma_id=SCMA-ELEANOR_-B2B31C9E"
    state = client.get(state_path)
    current_risk = state.json().get("risk_dial_pct", 0.5) if state.status_code == 200 else 0.5
    # Other tests may deliberately freeze this process-wide demo account at
    # zero. Temporarily establish the route's documented 50 bps lower bound so
    # this contract probe remains order-independent, then restore the fixture.
    service = get_lineage_service()
    member = next(
        member
        for house in service.CANONICAL_HOUSES.values()
        for member in house["members"]
        if member["scma_id"] == "SCMA-ELEANOR_-B2B31C9E"
    )
    original_risk = member["risk_dial"]
    if current_risk < 0.5:
        member["risk_dial"] = 0.005
        current_risk = 0.5
    try:
        risk_row = _request(client, "POST", "/api/v1/portal/member/risk-dial", json={"scma_id": "SCMA-ELEANOR_-B2B31C9E", "requested_risk_pct": current_risk})
    finally:
        member["risk_dial"] = original_risk
    return [
        _request(client, "GET", state_path),
        risk_row,
        _request(client, "POST", "/api/v1/portal/member/tutor", json={"question": "Explain compounding."}),
        _request(client, "GET", "/api/v1/operator/workspace-state"),
        _request(client, "GET", "/api/v1/lineage/governance/proposals"),
        _request(client, "GET", "/api/v1/operator/simulation/benchmark"),
        _request(client, "POST", "/api/v1/copilot/query", json={"prompt": "Summarize the current risk posture.", "user_id": "audit-harness", "role": "OPERATOR"}),
    ]


def run_audit(client: TestClient | None = None) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    owned_client = client is None
    client = client or TestClient(app)
    controls: list[dict[str, str]] = []
    try:
        for route in PORTAL_ROUTES:
            response = client.get(route)
            response.raise_for_status()
            controls.extend(audit_controls(route, response.text))
        api_rows = verify_api_wires(client)
    finally:
        if owned_client:
            client.close()
    return controls, api_rows


def _cell(value: str) -> str:
    return escape(str(value)).replace("|", "\\|").replace("\n", " ")


def render_report(controls: list[dict[str, str]], api_rows: list[dict[str, str]]) -> str:
    failed_controls = sum(row["status"] == "FAIL" for row in controls)
    failed_apis = sum(row["verdict"] == "FAIL" for row in api_rows)
    lines = [
        "# PDEUE System Functionality Audit",
        "",
        "> Generated by `python backend/scripts/audit_and_test_pdeue.py`. Re-run this command after portal or API wiring changes.",
        "",
        "## Summary",
        "",
        f"- Portal routes crawled: **{len(PORTAL_ROUTES)}**",
        f"- Interactive controls discovered: **{len(controls)}**",
        f"- Dead or placeholder controls: **{failed_controls}**",
        f"- API wires verified: **{len(api_rows) - failed_apis}/{len(api_rows)} passing**",
        "",
        "## Interactive Control Registry",
        "",
        "| Route | Tag | Label | Target/Hook | Status | Detail |",
        "|---|---|---|---|---|---|",
    ]
    lines.extend("| " + " | ".join(_cell(row[key]) for key in ("route", "tag", "label", "target", "status", "detail")) + " |" for row in controls)
    lines.extend(["", "## API Wire Verification", "", "| Endpoint | Status | Latency | Verdict |", "|---|---:|---:|---|"])
    lines.extend("| " + " | ".join(_cell(row[key]) for key in ("endpoint", "status", "latency", "verdict")) + " |" for row in api_rows)
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=REPORT_PATH, help="Markdown output path")
    args = parser.parse_args()
    controls, api_rows = run_audit()
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(render_report(controls, api_rows), encoding="utf-8")
    failures = [row for row in controls if row["status"] == "FAIL"] + [row for row in api_rows if row.get("verdict") == "FAIL"]
    print(f"Audited {len(controls)} controls and {len(api_rows)} API wires; report: {args.report}")
    if failures:
        print(f"Audit failed with {len(failures)} blocking finding(s).")
        return 1
    print("Audit passed with zero blocking findings.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
