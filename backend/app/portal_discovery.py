"""Static portal component discovery, API wiring inventory, and UI-to-Lexicon-to-Curriculum parity auditor."""
from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
import re
from typing import Any

from app.domain.lexicon_v05 import (
    BANNED_PLAIN_ENGLISH_JARGON,
    LEXICON_BY_ID,
    LEXICON_TERMS,
    REQUIRED_CANONICAL_TERM_IDS,
)

PORTALS = {
    "/home": "app/api/v1/home.html",
    "/dashboard": "app/api/v1/dashboard.html",
    "/member": "app/api/v1/member.html",
    "/admin/tech": "app/api/v1/tech.html",
    "/advisor": "app/api/v1/advisor.html",
    "/lineage/house/1": "app/api/v1/lineage_house.html",
    "/community": "app/api/v1/community.html",
    "/community/heritage": "app/api/v1/heritage.html",
    "/companion": "app/api/v1/companion.html",
}

PILLARS = (
    "Governance", "Identity & Access", "Capital Ledger", "Risk Controls",
    "Market Intelligence", "Order Execution", "Settlement", "Waterfall Accounting",
    "Lineage & Household", "Fiduciary Oversight", "Education", "Copilot Intelligence",
    "Infrastructure", "Observability", "Security & Privacy", "Audit & Compliance",
)

# Canonical acronyms & governance concepts cross-checked across all 9 portals,
# Lexicon (plain_english + technical_spec), and PDEUE University (/companion).
CANONICAL_CONCEPT_PATTERNS: dict[str, tuple[str, ...]] = {
    "scma": (r"\bSCMA\b",),
    "cfcp": (r"\bCFCP\b",),
    "faep": (r"\bFAEP\b",),
    "ifas": (r"\bIFAS\b",),
    "tpw-waterfall": (r"\bTPW\b", r"87\s*/\s*10\s*/\s*3", r"Transaction Profit Waterfall"),
    "quarter-kelly": (r"Quarter-Kelly", r"0\.25f\*"),
    "high-water-mark-adr-012": (r"High-Water Mark", r"\bHWM\b", r"\bADR-012\b"),
    "dry-powder-floor-40": (r"40%\s+Dry-Powder", r"Dry-Powder Floor", r"40%\s+SHIELD"),
    "active-hat-r06": (r"Active[\s-]Hat", r"\bR-06\b"),
    "directive-r12-masking": (r"Directive\s+R-12", r"\bR-12\b"),
    "adr-011-air-gap": (r"\bADR-011\b",),
    "executive-command-mode": (r"Executive Command", r"\bEXECUTIVE_COMMAND\b"),
    "adr-008-exact-cents": (r"\bADR-008\b",),
    "directive-r04-halt": (r"Directive\s+R-04", r"\bR-04\b"),
    "gate-g1-qualification": (r"\bGate\s+G1\b", r"HOLD_OBSERVATIONS_ONLY"),
    "concentric-asset-rings": (r"Concentric Asset", r"Asset Engine Rings"),
    "pay-it-forward-lccf": (r"Pay-[Ii]t-Forward", r"\bLCCF\b"),
    "house-genealogist": (r"House Genealogist", r"\bHOUSE_GENEALOGIST\b"),
    "anti-tribalism-custody": (r"Anti-Tribalism Custody", r"CROSS_HOUSE_ANTI_TRIBAL"),
    "delegated-onboarding": (r"Delegated Onboarding", r"PENDING_RATIFICATION"),
    "genealogical-ratification": (r"Genealogical Ratification", r"Genealogical Admissions Board"),
    "family-home-hub": (r"Family Home Hub",),
    "hall-of-arms": (r"Hall of Arms",),
    "lineage-hearth": (r"Lineage Hearth", r"Lineage Community Hearth"),
    "bordure-differencing": (r"Bordure Differencing", r"bordure differencing"),
    "guided-tour": (r"Guided Tour", r"Guided Step-by-Step"),
}


class ComponentParser(HTMLParser):
    """Collect interactive elements, headings, labels, tooltips, and visible text without third-party packages."""

    def __init__(self) -> None:
        super().__init__()
        self.components: list[dict[str, str]] = []
        self.headings: list[dict[str, str]] = []
        self.labels: list[str] = []
        self.abbr_terms: list[dict[str, str]] = []
        self._text_chunks: list[str] = []
        self._button: dict[str, str] | None = None
        self._heading: dict[str, str] | None = None
        self._in_label: bool = False
        self._label_buf: list[str] = []
        self._skip_depth: int = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key: value or "" for key, value in attrs}
        if tag in {"script", "style"}:
            self._skip_depth += 1
            return
        if self._skip_depth > 0:
            return
        if tag == "button":
            self._button = {
                "kind": "button",
                "id": values.get("id", ""),
                "label": "",
                "onclick": values.get("onclick", ""),
            }
        elif tag == "input":
            self.components.append({
                "kind": "slider" if values.get("type") == "range" else "input",
                "id": values.get("id", ""),
                "label": values.get("aria-label") or values.get("placeholder", ""),
                "onclick": values.get("onchange", ""),
            })
        elif tag in {"h1", "h2", "h3", "h4"}:
            self._heading = {"level": tag, "text": ""}
        elif tag == "label":
            self._in_label = True
            self._label_buf = []
        elif tag == "abbr" and "pdeue-term" in values.get("class", "").split():
            self.abbr_terms.append({
                "term_id": values.get("data-term", ""),
                "tooltip": values.get("data-tooltip", ""),
            })

    def handle_data(self, data: str) -> None:
        if self._skip_depth > 0:
            return
        cleaned = data.strip()
        if cleaned:
            self._text_chunks.append(cleaned)
        if self._button is not None:
            self._button["label"] += (" " if self._button["label"] and cleaned else "") + cleaned
        if self._heading is not None and cleaned:
            self._heading["text"] += (" " if self._heading["text"] else "") + cleaned
        if self._in_label and cleaned:
            self._label_buf.append(cleaned)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"}:
            self._skip_depth = max(0, self._skip_depth - 1)
            return
        if self._skip_depth > 0:
            return
        if tag == "button" and self._button is not None:
            self._button["label"] = re.sub(r"\s+", " ", self._button["label"]).strip()
            self.components.append(self._button)
            self._button = None
        elif tag in {"h1", "h2", "h3", "h4"} and self._heading is not None:
            text = re.sub(r"\s+", " ", self._heading["text"]).strip()
            if text:
                self.headings.append({"level": self._heading["level"], "text": text})
            self._heading = None
        elif tag == "label" and self._in_label:
            text = re.sub(r"\s+", " ", " ".join(self._label_buf)).strip()
            if text:
                self.labels.append(text)
            self._in_label = False
            self._label_buf = []

    @property
    def visible_text(self) -> str:
        return " ".join(self._text_chunks)


def _target(source: str, component: dict[str, str]) -> str:
    marker = component["id"] or component["label"]
    nearby = re.search(rf"{re.escape(marker)}[\s\S]{{0,700}}?fetch\(['\"]([^'\"]+)", source)
    if not nearby and component["id"]:
        nearby = re.search(rf"fetch\(['\"]([^'\"]+)[\s\S]{{0,700}}?{re.escape(component['id'])}", source)
    return nearby.group(1).split("?")[0] if nearby else "DOM state / navigation"


def _pillar(route: str, label: str) -> str:
    text = label.lower()
    if "copilot" in text or "diagnostic" in text:
        return "Copilot Intelligence"
    if "override" in text or "grant" in text or "revoke" in text:
        return "Security & Privacy"
    if "sign" in text or route == "/advisor":
        return "Fiduciary Oversight"
    if "risk" in text or "slider" in text:
        return "Risk Controls"
    if route == "/admin/tech":
        return "Infrastructure / Observability"
    if route == "/member":
        return "Education / Capital Ledger"
    if route.startswith("/lineage/"):
        return "Lineage & Household / Fiduciary Oversight"
    if route == "/home":
        return "Lineage & Household / Identity & Access"
    if route == "/community/heritage":
        return "Lineage & Household / Education"
    if route == "/community":
        return "Education / Lineage & Household"
    if route == "/companion":
        return "Education / Governance"
    return "Governance / Order Execution"


def _matches_any(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pat, text, re.IGNORECASE) for pat in patterns)


def audit_ui_lexicon_curriculum_parity(repo_root: Path) -> dict[str, Any]:
    """Cross-check all served portal controls, acronyms, Lexicon two-layer entries, and PDEUE University coverage."""
    undocumented_controls: list[dict[str, str]] = []
    dangling_data_terms: list[dict[str, str]] = []
    jargon_violations: list[dict[str, str]] = []
    portal_catalog: dict[str, dict[str, Any]] = {}
    term_portals: dict[str, list[str]] = {term_id: [] for term_id in CANONICAL_CONCEPT_PATTERNS}

    companion_visible_text = ""

    for route, relative in PORTALS.items():
        source = (repo_root / "backend" / relative).read_text(encoding="utf-8")
        parser = ComponentParser()
        parser.feed(source)

        for component in parser.components:
            identity = component["id"] or re.sub(r"\s+", " ", component["label"]).strip() or component["kind"]
            handler = component["onclick"] or ("addEventListener / delegated listener" if identity in source else "native form/navigation")
            is_stub = not handler or "alert(" in handler or handler.strip() in {"", "return false"}
            is_empty_button = component["kind"] == "button" and not component["label"]
            if is_stub or is_empty_button:
                undocumented_controls.append({"route": route, "identity": identity, "reason": "stub_or_empty_label"})

        for abbr in parser.abbr_terms:
            term_id = abbr["term_id"]
            tooltip = abbr["tooltip"]
            if term_id not in LEXICON_BY_ID:
                dangling_data_terms.append({"route": route, "term_id": term_id})
            lowered_tip = tooltip.lower()
            for banned in BANNED_PLAIN_ENGLISH_JARGON:
                if banned in lowered_tip:
                    jargon_violations.append({"source": f"{route}:abbr[{term_id}]", "banned_token": banned})

        visible = parser.visible_text
        if route == "/companion":
            companion_visible_text = visible

        detected_terms: list[str] = []
        for term_id, patterns in CANONICAL_CONCEPT_PATTERNS.items():
            if _matches_any(visible, patterns):
                detected_terms.append(term_id)
                term_portals[term_id].append(route)

        portal_catalog[route] = {
            "source_file": relative,
            "control_count": len(parser.components),
            "heading_count": len(parser.headings),
            "headings": [f"{h['level'].upper()}: {h['text']}" for h in parser.headings],
            "label_count": len(parser.labels),
            "abbr_tooltip_count": len(parser.abbr_terms),
            "detected_canonical_terms": detected_terms,
        }

    # Verify every Lexicon term's plain_english is jargon-free and has non-empty plain_english + technical_spec
    for entry in LEXICON_TERMS:
        pe = str(entry.get("plain_english") or "").strip().lower()
        for banned in BANNED_PLAIN_ENGLISH_JARGON:
            if banned in pe:
                jargon_violations.append({"source": f"lexicon_v05:{entry['id']}", "banned_token": banned})

    uncovered_lexicon_terms: list[str] = []
    uncovered_curriculum_terms: list[str] = []
    parity_matrix: list[dict[str, Any]] = []

    all_canonical_ids = list(dict.fromkeys([*REQUIRED_CANONICAL_TERM_IDS, *CANONICAL_CONCEPT_PATTERNS.keys()]))
    for term_id in all_canonical_ids:
        entry = LEXICON_BY_ID.get(term_id)
        plain_ok = bool(entry and str(entry.get("plain_english") or "").strip())
        tech_ok = bool(entry and str(entry.get("technical_spec") or "").strip())
        if not (plain_ok and tech_ok):
            uncovered_lexicon_terms.append(term_id)

        patterns = CANONICAL_CONCEPT_PATTERNS.get(term_id, (re.escape(term_id),))
        uni_ok = _matches_any(companion_visible_text, patterns)
        if not uni_ok:
            uncovered_curriculum_terms.append(term_id)

        parity_matrix.append({
            "term_id": term_id,
            "short_label": entry["short_label"] if entry else term_id,
            "portals_using": term_portals.get(term_id, []),
            "lexicon_plain_english_ok": plain_ok,
            "lexicon_technical_spec_ok": tech_ok,
            "university_covered": uni_ok,
            "status": "PASS" if (plain_ok and tech_ok and uni_ok) else "FAIL",
        })

    passed = (
        not undocumented_controls
        and not dangling_data_terms
        and not jargon_violations
        and not uncovered_lexicon_terms
        and not uncovered_curriculum_terms
    )

    return {
        "portals_scanned": list(PORTALS.keys()),
        "undocumented_controls": undocumented_controls,
        "dangling_data_terms": dangling_data_terms,
        "jargon_violations": jargon_violations,
        "uncovered_lexicon_terms": uncovered_lexicon_terms,
        "uncovered_curriculum_terms": uncovered_curriculum_terms,
        "portal_catalog": portal_catalog,
        "parity_matrix": parity_matrix,
        "passed": passed,
    }


def generate_inventory(repo_root: Path) -> str:
    rows: list[str] = []
    for route, relative in PORTALS.items():
        source = (repo_root / "backend" / relative).read_text(encoding="utf-8")
        parser = ComponentParser()
        parser.feed(source)
        for component in parser.components:
            identity = component["id"] or re.sub(r"\s+", " ", component["label"]).strip() or component["kind"]
            target = _target(source, component)
            handler = component["onclick"] or ("addEventListener / delegated listener" if identity in source else "native form/navigation")
            stub = not handler or "alert(" in handler or handler.strip() in {"", "return false"}
            status = "[STUB]" if stub else "[COMPLETE]"
            rows.append(f"| {route} | `{identity}` | {handler} | `{target}` | {status} | {_pillar(route, identity)} |")

    parity = audit_ui_lexicon_curriculum_parity(repo_root)

    header = """# Portal Component Inventory

Generated by `backend/app/portal_discovery.py`. The catalog covers all nine registered portal surfaces (`/home`, `/dashboard`, `/member`, `/admin/tech`, `/advisor`, `/lineage/house/1`, `/community`, `/community/heritage`, `/companion`), maps controls to the ratified 16-pillar ecosystem taxonomy, and enforces automated UI-to-Lexicon-to-Curriculum parity.

## Ratified taxonomy

""" + ", ".join(f"**{i + 1}. {name}**" for i, name in enumerate(PILLARS))

    table = "\n\n## Interactive component wiring\n\n| Portal Route | Element ID / Label | Event Handler | Target API | Status | System Pillar Map |\n|---|---|---|---|---|---|\n"

    portal_summary_rows = [
        f"| {route} | `{info['source_file']}` | {info['heading_count']} | {info['label_count']} | {info['control_count']} | {info['abbr_tooltip_count']} | {len(info['detected_canonical_terms'])} |"
        for route, info in parity["portal_catalog"].items()
    ]
    portal_summary = (
        "\n\n## Portal surface catalog (headings, labels, controls & tooltips)\n\n"
        "| Portal Route | Template Source | Headings | Labels | Interactive Controls | Pure-CSS Tooltips | Canonical Terms Detected |\n"
        "|---|---|---:|---:|---:|---:|---:|\n"
        + "\n".join(portal_summary_rows)
    )

    matrix_rows = [
        f"| `{row['term_id']}` | {row['short_label']} | {', '.join(row['portals_using']) or '—'} | "
        f"{'PASS' if row['lexicon_plain_english_ok'] else 'FAIL'} | "
        f"{'PASS' if row['lexicon_technical_spec_ok'] else 'FAIL'} | "
        f"{'PASS' if row['university_covered'] else 'FAIL'} | "
        f"**{row['status']}** |"
        for row in parity["parity_matrix"]
    ]
    scanned_list = ", ".join(f"`{r}`" for r in parity["portals_scanned"])
    parity_section = (
        "\n\n## UI-to-Lexicon-to-Curriculum Parity Audit\n\n"
        f"- **Portals audited:** {len(parity['portals_scanned'])} ({scanned_list})\n"
        f"- **Undocumented controls:** {len(parity['undocumented_controls'])}\n"
        f"- **Uncovered canonical acronyms/concepts (Lexicon):** {len(parity['uncovered_lexicon_terms'])}\n"
        f"- **Uncovered canonical acronyms/concepts (PDEUE University):** {len(parity['uncovered_curriculum_terms'])}\n"
        f"- **Dangling `data-term` tooltips:** {len(parity['dangling_data_terms'])}\n"
        f"- **Plain-English jargon violations:** {len(parity['jargon_violations'])}\n"
        f"- **Automated Parity Gate:** **{'PASS' if parity['passed'] else 'FAIL'}**\n\n"
        "| Term ID | Canonical Label | Portal Surfaces | Lexicon `plain_english` | Lexicon `technical_spec` | PDEUE University (`/companion`) | Parity |\n"
        "|---|---|---|---|---|---|---|\n"
        + "\n".join(matrix_rows)
    )

    return header + table + "\n".join(rows) + portal_summary + parity_section + "\n"


def write_inventory(repo_root: Path) -> Path:
    output = repo_root / "docs" / "PORTAL_COMPONENT_INVENTORY.md"
    output.write_text(generate_inventory(repo_root), encoding="utf-8")
    return output


if __name__ == "__main__":
    write_inventory(Path(__file__).resolve().parents[2])
