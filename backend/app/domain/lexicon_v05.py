"""Canonical Lexicon v0.5 / Plain-English v0.6 Two-Layer Glossary & Tooltip Registry.

Single source of truth for two-layer PDEUE terminology served via
``GET /api/v1/portal/glossary`` and rendered as zero-CDN pure-CSS hover tooltips
(``<abbr class="pdeue-term" data-tooltip="...">`` with ``ⓘ`` indicators) across
all seven PDEUE portals.

Two-Layer Contract (PR #80 — Plain-English Lexicon v0.6):
- ``plain_english`` (DEFAULT in tooltips and Glossary Drawer): Short, warm,
  jargon-free explanation a financial novice understands in 10 seconds.
- ``technical_spec`` (COLLAPSIBLE ``<details>`` "Technical & Governance Spec"):
  Deeper ADR / Directive / cryptographic / engineering detail for Chief Admin,
  Class T, or curious members.

Grounded in:
- docs/PDEUE_Canonical_Terminology_and_Replay_Lexicon_v0.5.md
- GEMINI.md (ADR-008, ADR-011, ADR-012 / Rule A14, Directives R-04/R-06/R-12)
- DESIGN_TOKENS.md
"""
from __future__ import annotations

from html import escape
from typing import Any, Dict, List, Optional

LEXICON_VERSION = "v0.5"
PLAIN_ENGLISH_REVISION = "v0.6"
LEXICON_STATUS = "OFFICIALLY_RATIFIED_AND_BINDING"

# Engineering / cryptographic jargon that MUST stay in technical_spec, never plain_english.
BANNED_PLAIN_ENGLISH_JARGON: tuple[str, ...] = (
    "hmac-sha256",
    "json-ld",
    "monotonic",
    "outbox",
    "tenant-partitioned",
    "sub-ledger",
    "floor-truncated",
    "cross-collateralize",
    "64-bit",
    "idempotent",
    "http 403",
    "basis points",
    "readmodelenvelope",
)

LEXICON_TERMS: List[Dict[str, Any]] = [
    {
        "id": "scma",
        "term": "SCMA (Self-Contained Member Account)",
        "short_label": "SCMA",
        "category": "Capital & Pools",
        "authority_ref": "Lexicon v0.5 §2 · Directive R-07 · Rule A14",
        "plain_english": (
            "Your own private, walled-off family account. Your money grows inside your personal box, "
            "and if a trade ever loses money, that loss stays strictly inside your own account and never touches anyone else's savings."
        ),
        "technical_spec": (
            "A tenant-partitioned member sub-ledger holding discrete seed principal, signed 64-bit integer-cent "
            "available cash, reservations, inventory, realized results, and a downward-only risk profile. "
            "Under Rule A14, one SCMA must never cross-collateralize, absorb the trading loss of, or leak records from another SCMA."
        ),
        "aliases": ["member account", "segregated account", "sub-ledger", "tenant ledger", "personal account"],
    },
    {
        "id": "cfcp",
        "term": "CFCP (Central Familial Common Pool)",
        "short_label": "CFCP",
        "category": "Capital & Pools",
        "authority_ref": "Lexicon v0.5 §2 · ADR-012",
        "plain_english": (
            "The family's shared safety net and blessing fund. It receives 10% of brand-new profits above each member's "
            "personal record high to help relatives with emergencies and debt relief—and it is never risked on trades."
        ),
        "technical_spec": (
            "A non-trading familial treasury sub-ledger receiving 10% (plus floor-truncation remainder cents under ADR-008) "
            "of eligible realized net new profit strictly above each SCMA's prior High-Water Mark (ADR-012). "
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
        "plain_english": (
            "A 3% slice of brand-new profits that pays for servers, data feeds, and caring for the platform—so family "
            "members never get hit with monthly software bills or fees during a downturn."
        ),
        "technical_spec": (
            "A dedicated administrative and infrastructure endowment sub-ledger receiving 3% (floor-truncated in integer cents) "
            "of eligible realized net new profit strictly above each SCMA's prior High-Water Mark under ADR-012. "
            "Receives $0.00 during drawdowns or recovery, eliminating out-of-pocket platform bills."
        ),
        "aliases": ["founder pool", "endowment", "3% pool", "platform ops", "stewardship pool"],
    },
    {
        "id": "ifas",
        "term": "IFAS (Independent Financial Accounting System)",
        "short_label": "IFAS",
        "category": "Accounting & Air-Gap",
        "authority_ref": "ADR-011 · Directive R-13 · accounting.narratix.io",
        "plain_english": (
            "Our separate, dedicated banking and bookkeeping home where real bank accounts, deposits, withdrawals, "
            "and tax records live. Keeping it apart from the trading engine protects every family member's banking details."
        ),
        "technical_spec": (
            "Standalone fiduciary accounting and custody service hosted at accounting.narratix.io with an isolated database "
            "and JWT audience (aud='ifas'). Connects to PenFed personal rails / Delaware FBO commercial custody and communicates "
            "with PDEUE solely via monotonic HMAC-SHA256 signed JSON-LD outbox events (/api/v1/accounting/events) and reconciliation ACKs."
        ),
        "aliases": ["accounting system", "accounting.narratix.io", "bank custody", "bookkeeping", "fiduciary ledger", "ifas"],
    },
    {
        "id": "tpw-waterfall",
        "term": "87/10/3 Waterfall (TPW)",
        "short_label": "87/10/3 Waterfall",
        "category": "Capital & Pools",
        "authority_ref": "Lexicon v0.5 §2 · Directive R-08 · ADR-008 · ADR-012",
        "plain_english": (
            "How brand-new profits are shared: 87% stays in your personal account to grow, 10% builds the shared family "
            "safety net, and 3% keeps the system running. Nothing is shared until you pass your own previous peak."
        ),
        "technical_spec": (
            "Transaction Profit Waterfall (TPW): deterministic allocation of eligible realized positive profit strictly above "
            "each SCMA's prior High-Water Mark in signed 64-bit integer cents (ADR-008): 87% compounds in SCMA, 10% plus any "
            "floor-division remainder cents routes to CFCP, and 3% routes to FAEP. Component cents always sum identically to input cents."
        ),
        "aliases": ["tpw", "transaction profit waterfall", "87/10/3", "profit split", "waterfall"],
    },
    {
        "id": "quarter-kelly",
        "term": "Quarter-Kelly (0.25f*)",
        "short_label": "Quarter-Kelly",
        "category": "Risk & Sizing",
        "authority_ref": "Lexicon v0.5 §6 · B4-RSK",
        "plain_english": (
            "A cautious bet-sizing rule that uses only one-quarter of what pure math says you could wager. "
            "It gives your account a wide safety cushion against surprises so a bad streak stays small."
        ),
        "technical_spec": (
            "Canonical PDEUE position-sizing fraction set to 0.25 of the full-Kelly edge formula (0.25f*). "
            "Quarter-Kelly is an upper ceiling input, never a spending quota: final stake is clamped to the minimum of "
            "Quarter-Kelly, the member's downward-only risk dial, B4-RSK correlated-factor caps, executable book depth, and the 40% Dry-Powder Floor."
        ),
        "aliases": ["0.25f*", "kelly sizing", "position sizing", "fractional kelly", "b4-rsk"],
    },
    {
        "id": "high-water-mark-adr-012",
        "term": "High-Water Mark / ADR-012",
        "short_label": "High-Water Mark (ADR-012)",
        "category": "Accounting & Air-Gap",
        "authority_ref": "ADR-012 · Rule A14 · Lexicon v0.5 §2",
        "plain_english": (
            "Your account's personal all-time high balance. If your account dips and then climbs back up, you keep "
            "100% of every recovery dollar—profit sharing only resumes once you earn genuinely new gains above your old peak."
        ),
        "technical_spec": (
            "Architecture Decision Record 012 mandates a per-SCMA High-Water Mark watermark initialized at seed capital in exact "
            "integer cents. The 87/10/3 Transaction Profit Waterfall applies strictly to net new realized profit exceeding the prior "
            "High-Water Mark; drawdown recovery stays 100% in SCMA ($0 CFCP/FAEP skim), while Rule A14 isolates 100% of trading losses inside the executing SCMA."
        ),
        "aliases": ["hwm", "adr-012", "watermark", "volatility tax", "drawdown recovery", "rule a14"],
    },
    {
        "id": "dry-powder-floor-40",
        "term": "40% Dry-Powder Floor",
        "short_label": "40% Dry-Powder Floor",
        "category": "Risk & Sizing",
        "authority_ref": "Lexicon v0.5 §2 · Directive R-09",
        "plain_english": (
            "A permanent cash reserve rule that keeps at least 40% of your account safely on the sidelines in cash at all times, "
            "so you are never overextended and always ready for better opportunities."
        ),
        "technical_spec": (
            "Mandatory reserve invariant requiring at least 40% of applicable pre-dispatch total equity to remain uncommitted "
            "spendable cash after all existing reservations and proposed orders. Computed in integer cents rounded conservatively "
            "upward; Priority Eviction drops lower-ranked intents before the 40% shield can ever be breached."
        ),
        "aliases": ["dry powder", "40% floor", "40% shield", "cash reserve", "uncommitted capital"],
    },
    {
        "id": "active-hat-r06",
        "term": "Active-Hat / R-06",
        "short_label": "Active-Hat (R-06)",
        "category": "Governance & Roles",
        "authority_ref": "Directive R-06 · Lexicon v0.5 §3",
        "plain_english": (
            "One role at a time. Even if a family leader holds two jobs—like personal member and platform steward—they must "
            "intentionally switch hats so personal money and leadership tools never mix by accident."
        ),
        "technical_spec": (
            "Directive R-06 enforces strict Split-Hat Context Isolation. Multi-role principals must explicitly switch Active Hats "
            "via an audited gateway (/api/v1/portal/active-hat/switch), revoking the prior session authority, stripping cross-role "
            "navigation bars, and enforcing server-side HTTP 403 boundaries."
        ),
        "aliases": ["split-hat", "directive r-06", "r-06", "role isolation", "hat switch", "context switch"],
    },
    {
        "id": "directive-r12-masking",
        "term": "Directive R-12 Masking",
        "short_label": "Directive R-12",
        "category": "Security & Privacy",
        "authority_ref": "Directive R-12 · Lexicon v0.5 §4",
        "plain_english": (
            "Privacy blinds for technical helpers. Engineers and house secretaries can keep systems healthy without seeing "
            "anyone's real dollar balances or account names—those numbers appear hidden as stars."
        ),
        "technical_spec": (
            "Directive R-12 mandates server-side redaction of tenant balances ($****.**), exposure values, and SCMA identifiers "
            "(SCMA-MEM-****) on routine Class T technical consoles and H1 secretarial desks. T1, T2, and H1 cannot unmask; "
            "T3 CTO diagnostics require an explicit, time-bounded, audited Chief Administrator override grant."
        ),
        "aliases": ["r-12", "redaction", "financial masking", "$****.**", "least privilege", "ca override"],
    },
    {
        "id": "adr-011-air-gap",
        "term": "ADR-011 Air-Gap",
        "short_label": "ADR-011 Air-Gap",
        "category": "Accounting & Air-Gap",
        "authority_ref": "ADR-011 · Directive R-13 · Lexicon v0.5 §7",
        "plain_english": (
            "A strict safety wall between trading software and your bank. This platform never asks for or stores bank account "
            "numbers, routing numbers, or bank logins—it only uses a harmless reference code to coordinate with IFAS."
        ),
        "technical_spec": (
            "Architecture Decision Record 011 enforces a strict credential and ledger air-gap between PDEUE and IFAS "
            "(accounting.narratix.io). PDEUE rejects raw routing/account/SWIFT/IBAN strings, stores only opaque "
            "EXT-REF-[ENTITY]-****[LAST4] memo tokens, and transmits accounting instructions solely via monotonic HMAC-SHA256 "
            "signed JSON-LD outbox events."
        ),
        "aliases": ["adr-011", "air-gap", "outbox", "zero banking credentials", "ext-ref", "hmac-sha256"],
    },
    {
        "id": "executive-command-mode",
        "term": "Executive Command Mode",
        "short_label": "Executive Command Mode",
        "category": "Governance & Roles",
        "authority_ref": "Milestone C6 · Sovereign Settlor Doctrine",
        "plain_english": (
            "Our protective starter mode while the family learns together. House voting buttons stay safely tucked away "
            "until the Founder opens later stages—and can snap back instantly during an emergency."
        ),
        "technical_spec": (
            "Default Stage 1 governance state (EXECUTIVE_COMMAND) of the 3-Stage Dormant Bicameral Veto Engine. "
            "House voting and veto controls are stripped and fail closed (HTTP 403). Stage 2 unlocks advisory 9/12 House petitions "
            "(preserving Absolute Founder Veto), Stage 3 enables binding Bicameral Veto on eligible policy/CFCP grants, and "
            "1-click SHTF Snap-Back instantaneously restores EXECUTIVE_COMMAND."
        ),
        "aliases": ["stage 1", "sovereign settlor", "shtf snap-back", "bicameral", "founder veto", "dormant"],
    },
    {
        "id": "adr-008-exact-cents",
        "term": "ADR-008 Exact-Cent Conservation",
        "short_label": "ADR-008",
        "category": "Accounting & Air-Gap",
        "authority_ref": "ADR-008 · Lexicon v0.5 §7",
        "plain_english": (
            "Every single penny is counted as a whole cent—never rounded loosely with messy decimals—so not even one penny "
            "can ever disappear or be invented when profits are split."
        ),
        "technical_spec": (
            "Every financial ledger balance, order reservation, settlement payout, and waterfall split is stored and computed "
            "strictly in signed 64-bit integer cents (floating-point currency arithmetic is prohibited). Any floor-division "
            "remainder cents route deterministically to CFCP; dollar formatting ($X,XXX.XX) occurs exclusively at the presentation boundary."
        ),
        "aliases": ["adr-008", "integer cents", "exact cents", "no float", "cent conservation"],
    },
    {
        "id": "directive-r04-halt",
        "term": "Directive R-04 Emergency Halt",
        "short_label": "Directive R-04",
        "category": "Governance & Roles",
        "authority_ref": "Directive R-04 · Lexicon v0.5 §3",
        "plain_english": (
            "The big red emergency brake. If anything looks wrong, leadership can pause all new trades across the entire "
            "platform in one step, and only the Chief Administrator can safely turn things back on."
        ),
        "technical_spec": (
            "Executive safety circuit breaker callable by the Chief Administrator or F3 CRO that immediately halts all new "
            "financial commitments and surfaces fail-closed TRADING_HALTED ReadModelEnvelope banners across all portals. "
            "Clearing an R-04 halt is strictly reserved to the Chief Administrator (HTTP 403 for all subordinate roles)."
        ),
        "aliases": ["r-04", "emergency halt", "kill switch", "trading halted", "circuit breaker"],
    },
    {
        "id": "gate-g1-qualification",
        "term": "Gate G1 (HOLD_OBSERVATIONS_ONLY)",
        "short_label": "Gate G1",
        "category": "Risk & Sizing",
        "authority_ref": "GEMINI.md §1 · Directive R-17",
        "plain_english": (
            "Our practice-before-live safety lock. By default, the system watches real markets in paper mode without risking "
            "a single real dollar until the Founder reviews real-world evidence and formally approves going live."
        ),
        "technical_spec": (
            "Pre-pilot fail-closed release gate. Defaults to HOLD_OBSERVATIONS_ONLY and PDEUE_VENUE_MODE=paper with "
            "synthetic_fills_present=False (synthetic historical fills permanently banned). Live read-model surfaces emit "
            "ReadModelEnvelope status QUALIFICATION_PENDING until explicit Founder live qualification sign-off."
        ),
        "aliases": ["g1", "hold_observations_only", "paper mode", "qualification pending", "zero-synthetic"],
    },
    {
        "id": "concentric-asset-rings",
        "term": "Concentric Asset Engine Rings",
        "short_label": "Concentric Asset Rings",
        "category": "Capital & Pools",
        "authority_ref": "Lexicon v0.5 §8 · Milestone E3",
        "plain_english": (
            "A simple target-style ring picture of your money at a glance: the outer ring shows active working capital, "
            "the middle ring shows your 40% cash safety shield, and the inner ring shows the 87/10/3 profit-sharing split."
        ),
        "technical_spec": (
            "Ratified Lexicon v0.5 zero-CDN inline SVG HUD visualization backed by exact integer-cent ReadModel telemetry: "
            "outer ring tracks active working margin vs. $25,000 float cap, middle ring tracks the 40% Dry-Powder Floor Shield "
            "(4,000 basis points), and inner ring visualizes the 87/10/3 SCMA/CFCP/FAEP waterfall proportions with numeric legends."
        ),
        "aliases": ["asset rings", "hud rings", "concentric rings", "capital shield rings"],
    },
    {
        "id": "pay-it-forward-lccf",
        "term": "Pay-it-Forward / LCCF (Lineage Community Capital Fund)",
        "short_label": "Pay-it-Forward / LCCF",
        "category": "Capital & Pools",
        "authority_ref": "Milestone C1 · Domain D5 · FSAP / IF-038–IF-041",
        "plain_english": (
            "Our family tradition of helping loved ones get out of high-interest debt and start building wealth. "
            "As early members grow, voluntary and common-pool support helps lift the next generation—who then pass that blessing forward."
        ),
        "technical_spec": (
            "Lineage Community Capital Fund (LCCF) & Financial Stability Assistance Program (FSAP) framework (IF-038–IF-041): "
            "variable contributor participation pool paired with CFCP reserves for direct-to-creditor toxic-debt payoff and "
            "50% downstream sweep interception on assisted recovery accounts, reconciled strictly through IFAS without exposing bank credentials in PDEUE."
        ),
        "aliases": ["pay it forward", "pay-it-forward", "lccf", "fsap", "toxic debt", "debt relief", "family blessing"],
    },
]

# Populate backward-compatible tooltip & definition fields directly from plain_english
for _entry in LEXICON_TERMS:
    _entry["tooltip"] = _entry["plain_english"]
    _entry["definition"] = _entry["plain_english"]

LEXICON_BY_ID: Dict[str, Dict[str, Any]] = {entry["id"]: entry for entry in LEXICON_TERMS}

REQUIRED_CANONICAL_TERM_IDS: tuple[str, ...] = (
    "scma",
    "cfcp",
    "faep",
    "ifas",
    "tpw-waterfall",
    "quarter-kelly",
    "high-water-mark-adr-012",
    "dry-powder-floor-40",
    "active-hat-r06",
    "directive-r12-masking",
    "adr-011-air-gap",
    "executive-command-mode",
    "adr-008-exact-cents",
    "directive-r04-halt",
    "gate-g1-qualification",
    "concentric-asset-rings",
    "pay-it-forward-lccf",
)


def get_term(term_id: str) -> Dict[str, Any]:
    """Return a single canonical Lexicon term entry by ID."""
    return dict(LEXICON_BY_ID[term_id])


def get_term_tooltip(term_id: str) -> str:
    """Return the warm, jargon-free plain-English hover tooltip string for a canonical term ID."""
    return str(LEXICON_BY_ID[term_id]["plain_english"])


def render_term_abbr(term_id: str, display_text: Optional[str] = None) -> str:
    """Render a zero-CDN pure-CSS ``<abbr class="pdeue-term">`` element with ``ⓘ`` indicator."""
    entry = LEXICON_BY_ID[term_id]
    label = escape(display_text or str(entry["short_label"]))
    tooltip = escape(str(entry["plain_english"]), quote=True)
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
    """Build the canonical ``GET /api/v1/portal/glossary`` two-layer response payload."""
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
                    item["plain_english"],
                    item["technical_spec"],
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
        "plain_english_version": PLAIN_ENGLISH_REVISION,
        "two_layer_schema": True,
        "status": LEXICON_STATUS,
        "ratified": True,
        "count": len(filtered),
        "total_count": len(LEXICON_TERMS),
        "categories": categories,
        "terms": filtered,
        "terms_by_id": {item["id"]: item for item in filtered},
    }
