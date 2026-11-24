"""Canonical Lexicon v0.5 Glossary & Tooltip Registry (Milestone E4).

Single source of truth for plain-English PDEUE Lexicon v0.5 terminology served via
``GET /api/v1/portal/glossary`` and rendered as zero-CDN pure-CSS hover tooltips
(``<abbr class="pdeue-term" data-tooltip="...">`` with ``ⓘ`` indicators) across
all PDEUE portals.

Grounded in:
- docs/PDEUE_Canonical_Terminology_and_Replay_Lexicon_v0.5.md
- GEMINI.md (ADR-008, ADR-011, ADR-012 / Rule A14, Directives R-04/R-06/R-12)
- DESIGN_TOKENS.md
"""
from __future__ import annotations

from html import escape
from typing import Any, Dict, List, Optional

LEXICON_VERSION = "v0.5"
LEXICON_STATUS = "OFFICIALLY_RATIFIED_AND_BINDING"

LEXICON_TERMS: List[Dict[str, Any]] = [
    {
        "id": "scma",
        "term": "SCMA (Self-Contained Member Account)",
        "short_label": "SCMA",
        "category": "Capital & Pools",
        "authority_ref": "Lexicon v0.5 §2 · Directive R-07 · Rule A14",
        "tooltip": (
            "Self-Contained Member Account: tenant-partitioned member sub-ledger in exact integer cents. "
            "Losses remain 100% isolated inside the executing SCMA and never cross-collateralize sibling accounts."
        ),
        "definition": (
            "A tenant-partitioned member sub-ledger holding discrete seed principal, integer-cent available cash, "
            "reservations, inventory, realized results, and a downward-only risk profile. One SCMA must never "
            "cross-collateralize, absorb the trading loss of, or leak records from another SCMA."
        ),
        "aliases": ["member account", "segregated account", "sub-ledger", "tenant ledger", "personal account"],
    },
    {
        "id": "cfcp",
        "term": "CFCP (Central Familial Common Pool)",
        "short_label": "CFCP",
        "category": "Capital & Pools",
        "authority_ref": "Lexicon v0.5 §2 · ADR-012",
        "tooltip": (
            "Central Familial Common Pool: non-trading familial reserve receiving 10% (plus remainder cents) "
            "of eligible net new profit above High-Water Mark. Never absorbs individual trading losses."
        ),
        "definition": (
            "A non-trading familial treasury sub-ledger that receives 10% (plus floor-truncation remainder cents "
            "under ADR-008) of eligible realized net new profit above each SCMA's prior High-Water Mark. "
            "Funds lineage resilience and FSAP debt-relief programs; never acts as spare member margin and never absorbs individual trading losses."
        ),
        "aliases": ["family pool", "familial shield", "10% pool", "lineage reserve", "common pool"],
    },
    {
        "id": "faep",
        "term": "FAEP (Founder/Chief Administrator Endowment Pool)",
        "short_label": "FAEP",
        "category": "Capital & Pools",
        "authority_ref": "Lexicon v0.5 §2 · ADR-012",
        "tooltip": (
            "Founder/Chief Administrator Endowment Pool: receives 3% of eligible net new profit above High-Water Mark "
            "for platform stewardship and infrastructure. $0 skim on loss or drawdown recovery."
        ),
        "definition": (
            "A dedicated administrative and infrastructure endowment sub-ledger receiving 3% of eligible realized "
            "net new profit strictly above each SCMA's prior High-Water Mark. Receives $0 during drawdowns or recovery, "
            "eliminating out-of-pocket platform bills."
        ),
        "aliases": ["founder pool", "endowment", "3% pool", "platform ops", "stewardship pool"],
    },
    {
        "id": "quarter-kelly",
        "term": "Quarter-Kelly (0.25f*)",
        "short_label": "Quarter-Kelly",
        "category": "Risk & Sizing",
        "authority_ref": "Lexicon v0.5 §6 · B4-RSK",
        "tooltip": (
            "Canonical sizing ceiling at 0.25 of full-Kelly. Final stake is the minimum of Quarter-Kelly, "
            "member risk dial, Tier-1 ceilings, liquidity, and the 40% Dry-Powder Floor."
        ),
        "definition": (
            "The canonical PDEUE position-sizing fraction set to 0.25 of the full-Kelly edge formula. "
            "Quarter-Kelly is an upper ceiling input, never a spending quota: final stake is clamped to the minimum "
            "allowed by Quarter-Kelly, the member's downward-only risk dial, correlated-factor caps, executable book depth, "
            "and the mandatory 40% Dry-Powder Floor."
        ),
        "aliases": ["0.25f*", "kelly sizing", "position sizing", "fractional kelly", "b4-rsk"],
    },
    {
        "id": "high-water-mark-adr-012",
        "term": "High-Water Mark / ADR-012",
        "short_label": "High-Water Mark (ADR-012)",
        "category": "Accounting & Air-Gap",
        "authority_ref": "ADR-012 · Rule A14 · Lexicon v0.5 §2",
        "tooltip": (
            "Per-SCMA High-Water Mark (ADR-012): the 87/10/3 waterfall applies strictly to net new profit above "
            "prior peak equity. Drawdown recovery stays 100% in SCMA ($0 CFCP/FAEP skim)."
        ),
        "definition": (
            "Architecture Decision Record 012 mandates a per-SCMA High-Water Mark watermark initialized at seed capital. "
            "The 87% SCMA / 10% CFCP / 3% FAEP Transaction Profit Waterfall applies strictly to net new realized profit "
            "exceeding the prior High-Water Mark. Gains earned while recovering from a drawdown remain 100% in the SCMA, "
            "eliminating volatility tax while Rule A14 keeps 100% of losses contained in the executing SCMA."
        ),
        "aliases": ["hwm", "adr-012", "watermark", "volatility tax", "drawdown recovery", "rule a14"],
    },
    {
        "id": "dry-powder-floor-40",
        "term": "40% Dry-Powder Floor",
        "short_label": "40% Dry-Powder Floor",
        "category": "Risk & Sizing",
        "authority_ref": "Lexicon v0.5 §2 · Directive R-09",
        "tooltip": (
            "Uncommitted cash shield: every dispatch batch must leave at least 40% of pre-dispatch total equity "
            "uncommitted (integer-cent ceiling). Priority eviction drops weaker intents rather than breaching it."
        ),
        "definition": (
            "The mandatory reserve invariant requiring at least 40% of applicable pre-dispatch total equity to remain "
            "uncommitted spendable cash after all existing reservations and proposed orders. Computed in integer cents "
            "rounded conservatively upward; lower-priority intents are evicted before the 40% shield can ever be breached."
        ),
        "aliases": ["dry powder", "40% floor", "40% shield", "cash reserve", "uncommitted capital"],
    },
    {
        "id": "active-hat-r06",
        "term": "Active-Hat / R-06",
        "short_label": "Active-Hat (R-06)",
        "category": "Governance & Roles",
        "authority_ref": "Directive R-06 · Lexicon v0.5 §3",
        "tooltip": (
            "Directive R-06 Split-Hat Role Mapping: multi-role operators explicitly switch between isolated role contexts "
            "(Chief Admin, Class F, Class T, Class H, Class M). Privileges never blend across workspaces."
        ),
        "definition": (
            "Directive R-06 enforces strict Split-Hat Context Isolation. A person holding multiple appointments must "
            "explicitly switch Active Hats via an audited gateway. Switching hats revokes the prior workspace authority "
            "for that session, strips cross-role navigation bars, and enforces server-side HTTP 403 boundaries."
        ),
        "aliases": ["split-hat", "directive r-06", "r-06", "role isolation", "hat switch", "context switch"],
    },
    {
        "id": "directive-r12-masking",
        "term": "Directive R-12 Masking",
        "short_label": "Directive R-12",
        "category": "Security & Privacy",
        "authority_ref": "Directive R-12 · Lexicon v0.5 §4",
        "tooltip": (
            "Least-Privilege Financial Masking (R-12): Class T and H1 desks redact balances ($****.**) and SCMA IDs "
            "(SCMA-MEM-****) server-side. Only a time-bounded, audited T3 Chief Admin override may temporarily unmask."
        ),
        "definition": (
            "Directive R-12 mandates server-side redaction of tenant balances ($****.**), exposure values, and SCMA "
            "identifiers (SCMA-MEM-****) on routine Class T technical consoles and H1 secretarial desks. T1, T2, and H1 "
            "cannot unmask; T3 CTO diagnostics require an explicit, time-bounded, logged Chief Administrator override grant."
        ),
        "aliases": ["r-12", "redaction", "financial masking", "$****.**", "least privilege", "ca override"],
    },
    {
        "id": "adr-011-air-gap",
        "term": "ADR-011 Air-Gap",
        "short_label": "ADR-011 Air-Gap",
        "category": "Accounting & Air-Gap",
        "authority_ref": "ADR-011 · Directive R-13 · Lexicon v0.5 §7",
        "tooltip": (
            "Zero Banking Credentials & Signed Outbox (ADR-011): PDEUE never stores bank routing, account, SWIFT, or "
            "login credentials. External accounts use opaque EXT-REF tokens and HMAC-SHA256 signed events to IFAS."
        ),
        "definition": (
            "Architecture Decision Record 011 enforces a strict credential and ledger air-gap between PDEUE and the "
            "Independent Financial Accounting System (IFAS at accounting.narratix.io). PDEUE rejects raw routing/account "
            "numbers, stores only opaque EXT-REF-[ENTITY]-****[LAST4] memo tokens, and transmits accounting instructions "
            "solely via monotonic HMAC-SHA256 signed JSON-LD outbox events."
        ),
        "aliases": ["adr-011", "ifas", "outbox", "zero banking credentials", "ext-ref", "hmac-sha256"],
    },
    {
        "id": "executive-command-mode",
        "term": "Executive Command Mode",
        "short_label": "Executive Command Mode",
        "category": "Governance & Roles",
        "authority_ref": "Milestone C6 · Sovereign Settlor Doctrine",
        "tooltip": (
            "Stage 1 fail-closed governance mode: House voting and bicameral veto controls remain dormant (HTTP 403) "
            "until promoted by the Chief Administrator, with instant 1-click SHTF snap-back and Absolute Founder Veto."
        ),
        "definition": (
            "The default Stage 1 governance state of the 3-Stage Dormant Bicameral Veto Engine. House voting and veto "
            "controls are stripped and fail closed (HTTP 403) while Executive Command is active. Stage 2 unlocks advisory "
            "9/12 House petitions (preserving Absolute Founder Veto), Stage 3 enables binding Bicameral Veto on eligible "
            "policy/CFCP grants, and 1-click SHTF Snap-Back instantaneously restores Executive Command."
        ),
        "aliases": ["stage 1", "sovereign settlor", "shtf snap-back", "bicameral", "founder veto", "dormant"],
    },
    {
        "id": "tpw-waterfall",
        "term": "87/10/3 Waterfall (TPW)",
        "short_label": "87/10/3 Waterfall",
        "category": "Capital & Pools",
        "authority_ref": "Lexicon v0.5 §2 · Directive R-08 · ADR-008",
        "tooltip": (
            "Transaction Profit Waterfall: eligible realized net new profit above HWM splits 87% SCMA, 10% CFCP "
            "(+ floor remainder cents), and 3% FAEP with exact-cent conservation."
        ),
        "definition": (
            "The deterministic allocation of eligible realized positive profit strictly above each SCMA's prior High-Water "
            "Mark: 87% compounds inside the executing SCMA, 10% plus any floor-division remainder cents flows to CFCP, "
            "and 3% flows to FAEP. Sum of component cents always equals input cents exactly."
        ),
        "aliases": ["tpw", "transaction profit waterfall", "87/10/3", "profit split", "waterfall"],
    },
    {
        "id": "adr-008-exact-cents",
        "term": "ADR-008 Exact-Cent Conservation",
        "short_label": "ADR-008",
        "category": "Accounting & Air-Gap",
        "authority_ref": "ADR-008 · Lexicon v0.5 §7",
        "tooltip": (
            "Exact-Cent Integer Accounting (ADR-008): all balances, order sizes, reservations, and waterfall splits "
            "use 64-bit integer cents. Floating-point currency math is strictly prohibited."
        ),
        "definition": (
            "Every financial ledger balance, order reservation, settlement payout, and waterfall split is stored and "
            "computed strictly in signed 64-bit integer cents. Dollar formatting ($X,XXX.XX) occurs exclusively at the "
            "presentation boundary."
        ),
        "aliases": ["adr-008", "integer cents", "exact cents", "no float", "cent conservation"],
    },
    {
        "id": "directive-r04-halt",
        "term": "Directive R-04 Emergency Halt",
        "short_label": "Directive R-04",
        "category": "Governance & Roles",
        "authority_ref": "Directive R-04 · Lexicon v0.5 §3",
        "tooltip": (
            "Emergency Financial Halt (R-04): immediately stops new financial commitments and surfaces a fail-closed "
            "TRADING HALTED banner across portals. Resumption is strictly reserved to the Chief Administrator."
        ),
        "definition": (
            "An executive safety circuit breaker callable by the Chief Administrator or F3 CRO that halts all new "
            "financial commitments and unsafe settlement releases when ledger integrity, venue truth, or risk bounds are "
            "in doubt. Clearing an R-04 halt is strictly reserved to the Chief Administrator (HTTP 403 for all other roles)."
        ),
        "aliases": ["r-04", "emergency halt", "kill switch", "trading halted", "circuit breaker"],
    },
    {
        "id": "gate-g1-qualification",
        "term": "Gate G1 (HOLD_OBSERVATIONS_ONLY)",
        "short_label": "Gate G1",
        "category": "Risk & Sizing",
        "authority_ref": "GEMINI.md §1 · Directive R-17",
        "tooltip": (
            "Fail-closed Gate G1 qualification state: execution defaults to paper/observation mode with zero synthetic "
            "fills until explicit Founder live qualification sign-off."
        ),
        "definition": (
            "The pre-pilot fail-closed release gate. While Gate G1 remains in HOLD_OBSERVATIONS_ONLY and paper mode, "
            "no live capital is risked, synthetic historical fills are banned (synthetic_fills_present: False), and "
            "live read-model surfaces clearly announce QUALIFICATION PENDING."
        ),
        "aliases": ["g1", "hold_observations_only", "paper mode", "qualification pending", "zero-synthetic"],
    },
    {
        "id": "concentric-asset-rings",
        "term": "Concentric Asset Engine Rings",
        "short_label": "Concentric Asset Rings",
        "category": "Capital & Pools",
        "authority_ref": "Lexicon v0.5 §8 · Milestone E3",
        "tooltip": (
            "Canonical PDEUE HUD visualization showing nested rings for Active Working Margin, the 40% Dry-Powder "
            "Floor Shield, and the 87/10/3 SCMA/CFCP/FAEP waterfall split with accessible numeric legends."
        ),
        "definition": (
            "The ratified Lexicon v0.5 visual HUD metaphor displaying nested capital allocation and safety boundaries: "
            "outer ring for active working margin vs. float cap, middle ring for the 40% Dry-Powder Floor Shield, "
            "and inner ring for the 87/10/3 SCMA/CFCP/FAEP waterfall proportions—always paired with exact text labels."
        ),
        "aliases": ["asset rings", "hud rings", "concentric rings", "capital shield rings"],
    },
]

LEXICON_BY_ID: Dict[str, Dict[str, Any]] = {entry["id"]: entry for entry in LEXICON_TERMS}

REQUIRED_CANONICAL_TERM_IDS: tuple[str, ...] = (
    "scma",
    "cfcp",
    "faep",
    "quarter-kelly",
    "high-water-mark-adr-012",
    "dry-powder-floor-40",
    "active-hat-r06",
    "directive-r12-masking",
    "adr-011-air-gap",
    "executive-command-mode",
)


def get_term(term_id: str) -> Dict[str, Any]:
    """Return a single canonical Lexicon v0.5 term entry by ID."""
    return dict(LEXICON_BY_ID[term_id])


def get_term_tooltip(term_id: str) -> str:
    """Return the plain-English hover tooltip string for a canonical term ID."""
    return str(LEXICON_BY_ID[term_id]["tooltip"])


def render_term_abbr(term_id: str, display_text: Optional[str] = None) -> str:
    """Render a zero-CDN pure-CSS ``<abbr class="pdeue-term">`` element with ``ⓘ`` indicator."""
    entry = LEXICON_BY_ID[term_id]
    label = escape(display_text or str(entry["short_label"]))
    tooltip = escape(str(entry["tooltip"]), quote=True)
    safe_id = escape(str(entry["id"]), quote=True)
    return (
        f'<abbr class="pdeue-term" tabindex="0" data-term="{safe_id}" data-tooltip="{tooltip}">'
        f'{label}<span class="pdeue-term-info" aria-hidden="true">ⓘ</span></abbr>'
    )


def get_lexicon_payload(
    *,
    q: Optional[str] = None,
    category: Optional[str] = None,
) -> Dict[str, Any]:
    """Build the canonical ``GET /api/v1/portal/glossary`` response payload."""
    needle = (q or "").strip().lower()
    cat_filter = (category or "").strip().lower()

    filtered: List[Dict[str, Any]] = []
    for item in LEXICON_TERMS:
        if cat_filter and cat_filter != "all" and item["category"].lower() != cat_filter:
            continue
        if needle:
            haystack = " ".join(
                [
                    item["id"],
                    item["term"],
                    item["short_label"],
                    item["category"],
                    item["authority_ref"],
                    item["tooltip"],
                    item["definition"],
                    " ".join(item.get("aliases", [])),
                ]
            ).lower()
            if needle not in haystack:
                continue
        filtered.append(dict(item))

    categories = sorted({item["category"] for item in LEXICON_TERMS})
    return {
        "lexicon_version": LEXICON_VERSION,
        "status": LEXICON_STATUS,
        "ratified": True,
        "count": len(filtered),
        "total_count": len(LEXICON_TERMS),
        "categories": categories,
        "terms": filtered,
        "terms_by_id": {item["id"]: item for item in filtered},
    }
