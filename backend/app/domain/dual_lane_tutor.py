"""Dual-Lane AI Tutor (Batch 2B — Part 2).

Routes educational queries into two explicit, safe lanes with ZERO execution
authority (``unilateral_execution = False``) and ZERO imports of live trading
ledgers, risk envelopes, or banking credentials:

- LANE 1 — ``LOCAL_CANON``:
  Strictly grounded in ``LEXICON_BY_ID`` and ratified PDEUE family rules
  (87/10/3 Waterfall, High-Water Mark recovery, 100% SCMA Loss Isolation,
  Downward-Only Risk Dial, 40% Dry-Powder Floor, Quarter-Kelly sizing,
  $25,000 Active Float & IFAS Air-Gap, Three-Tier Withdrawals, Pay-it-Forward
  FSAP Phase II, Phase I vs. Phase II, Active-Hat R-06, Directive R-12
  Masking, and Shadow Paper Hunch rules). Every Lane 1 answer includes a
  concrete dollar example and a "Try this in PDEUE University" chapter pointer.

- LANE 2 — ``PUBLIC_WEB_RESEARCH``:
  Handles general market, economic, weather, energy, treasury, FX, equity-index,
  and binary-contract probability questions via the modular ``BaseLLMClient``
  adapter with read-only grounding, returning structured ``citations``
  (``[{"title": ..., "url": ..., "source": ...}]``) and the mandatory badge:
  ``"General Public Market Education — Not Financial Advice"``.

- FAIL-CLOSED REGULATORY FILTER (Nov 2026 CFTC / DEATH BETS Act):
  Blocks sports, casino-style wagers, war, terrorism, and death contracts
  before any LLM call (``lane="REGULATORY_REFUSAL"``).
"""
from __future__ import annotations

import html
import re
from typing import Any, Dict, List, Optional, Tuple

from app.domain.lexicon_v05 import LEXICON_BY_ID, LEXICON_VERSION
from app.domain.llm_client import BaseLLMClient, LLMResponse, get_llm_client
from app.domain.local_knowledge_index import get_local_knowledge_index
from app.domain.regulatory_filter import (
    PROHIBITED_CODE,
    REGULATORY_CITATION,
    check_regulatory_content,
)

LANE_LOCAL_CANON = "LOCAL_CANON"
LANE_PUBLIC_WEB_RESEARCH = "PUBLIC_WEB_RESEARCH"
LANE_REGULATORY_REFUSAL = "REGULATORY_REFUSAL"

LOCAL_CANON_BADGE = "Local PDEUE Canon"
PUBLIC_RESEARCH_DISCLAIMER_BADGE = "General Public Market Education — Not Financial Advice"
REGULATORY_REFUSAL_BADGE = "Blocked — Prohibited Event Category"

_ACADEMY_MUTATION_PHRASES: Tuple[str, ...] = (
    "buy ",
    "sell ",
    "place an order",
    "place a trade",
    "execute",
    "submit a trade",
    "make a trade",
    "cancel order",
    "transfer",
    "withdraw money",
    "withdraw $",
    "deposit $",
    "deposit money",
    "move my money",
    "wire funds",
)
_ACADEMY_BALANCE_PHRASES: Tuple[str, ...] = (
    "my balance",
    "account balance",
    "capital balance",
    "bank balance",
    "how much money",
    "check my balance",
    "show my scma balance",
    "what is my balance",
)

# Lane 1 Canonical Knowledge Entries — grounded strictly in LEXICON_BY_ID + ratified policy.
_CANON_TOPICS: Tuple[Dict[str, Any], ...] = (
    {
        "id": "SHADOW_HUNCH_RULES",
        "patterns": (
            r"\bshadow\s+paper\b",
            r"\bshadow\s+hunch",
            r"\bhunch\s+studio\b",
            r"\bhunch\s+rules?\b",
            r"\bshadow\s+bid\b",
            r"\blive\s+clearance\b",
            r"\bstewardship_l1_certified\b",
            r"\bthree-?point\s+validation\b",
        ),
        "concept": "SHADOW_HUNCH_STUDIO",
        "answer": (
            "The Shadow Paper Hunch Studio (SHADOW_PAPER mode) is a permanent, zero-risk practice lab where "
            "members and administrators test economic, weather, energy, treasury, FX, and equity-index ideas "
            "without ever touching real SCMA funds, live venue keys, or IFAS bank records. Every hunch passes "
            "a Three-Point Validation audit (external corroboration, regulated oracle mapping, and integer-cent "
            "net edge after fees). Sports, casino, war, terrorism, and death contracts are permanently blocked. "
            "Requesting live-promotion clearance requires STEWARDSHIP_L1_CERTIFIED status and an active non-frozen "
            "risk dial, followed by two-step F2-H Head of Household and F3 / Chief Admin review."
        ),
        "dollar_example": (
            "Example: Testing a $100.00 virtual Shadow Paper bid at 54¢ on a NOAA weather contract with a 62¢ "
            "modeled fair value and 2¢ fee (+6¢ net edge) tracks your shadow hit rate while keeping $0.00 of "
            "real SCMA cash at risk."
        ),
        "university_pointer": "Try this in PDEUE University: Chapter 6 — Stewardship Certification & Safety Gates (/companion?chapter=6)",
        "lexicon_ids": ["gate-g1-qualification", "quarter-kelly", "adr-008-exact-cents"],
    },
    {
        "id": "PAY_IT_FORWARD_FSAP",
        "patterns": (
            r"\bpay[\s-]it[\s-]forward\b",
            r"\bfsap\b",
            r"\blccf\b",
            r"\bsovereign\s+choice\b",
            r"\btoxic[\s-]debt\b",
            r"\bdebt[\s-]relief\b",
        ),
        "concept": "LCCF_STEWARDSHIP",
        "answer": (
            "Pay-it-Forward (FSAP — Familial Stability Advance Pool) launches in Phase II inside our separate "
            "IFAS accounting system. Stable relatives help extinguish high-interest debt directly with creditors "
            "and seed an isolated SCMA with zero shared trading risk, receiving full principal return plus a "
            "transparent share of actual realized pool income. Once repaid to $0.00, the helped relative makes "
            "The Sovereign Choice to pass the blessing forward voluntarily."
        ),
        "dollar_example": (
            "Example: If a Phase II FSAP advance pays $3,000.00 directly to clear a 24% APR credit card and "
            "seeds a separate $500.00 SCMA, the family member's trading results stay 100% isolated while "
            "repayments return the $3,000.00 principal cleanly inside IFAS."
        ),
        "university_pointer": "Try this in PDEUE University: Chapter 5 — Family Legacy & Pay-it-Forward Charter (/companion?chapter=5)",
        "lexicon_ids": ["pay-it-forward-lccf", "cfcp", "ifas"],
    },
    {
        "id": "PHASE_1_VS_PHASE_2",
        "patterns": (
            r"\bphase\s*i\b.*\bphase\s*ii\b",
            r"\bphase\s*1\b.*\bphase\s*2\b",
            r"\bphase\s*ii\b",
            r"\bphase\s*2\b",
            r"\bphase\s*i\b",
            r"\bphase\s*1\b",
            r"\bspawn\s*2\.0\b",
            r"\bproject\s+future\b",
        ),
        "concept": "PHASE_I_VS_PHASE_II",
        "answer": (
            "Phase I (Foundation & Qualification) focuses on learning, paper/observation qualification under "
            "Gate G1 (HOLD_OBSERVATIONS_ONLY), disciplined Quarter-Kelly sizing, and building each member's "
            "isolated SCMA up toward the $25,000.00 Active Float Cap. Phase II expands after qualification and "
            "float maturity: it activates the separate IFAS-backed Pay-it-Forward (FSAP) debt-relief and seeding "
            "pool, off-venue swept-cash T-bill yield, and multi-asset diversification across deeper regulated markets."
        ),
        "dollar_example": (
            "Example: In Phase I, a $1,000.00 SCMA compounds strictly inside its walled-off account under the "
            "40% cash shield. Once Phase II is active and an account exceeds the $25,000.00 active float cap, "
            "excess profits sweep safely to IFAS bank custody where voluntary FSAP participation can begin."
        ),
        "university_pointer": "Try this in PDEUE University: Chapter 1 — Founding Vision & Phase I/II Roadmap (/companion?chapter=1)",
        "lexicon_ids": ["gate-g1-qualification", "pay-it-forward-lccf", "ifas"],
    },
    {
        "id": "HIGH_WATER_MARK_AND_LOSS_ISOLATION",
        "patterns": (
            r"\bhigh[\s-]water\s*mark\b",
            r"\bhwm\b",
            r"\badr[\s-]?012\b",
            r"\brule\s+a14\b",
            r"\bloss\s+isolation\b",
            r"\bvolatility\s+tax\b",
            r"\bdrawdown\s+recovery\b",
            r"\b100%\s+scma\s+loss\b",
            r"\blosing\s+trade\b",
        ),
        "concept": "HIGH_WATER_MARK_ADR012",
        "answer": (
            "Under ADR-012 (Per-SCMA High-Water Mark) and Rule A14 (100% SCMA Loss Isolation), every member's "
            "SCMA tracks its own all-time equity peak. If your account dips on a losing trade, 100% of that loss "
            "stays strictly inside your own SCMA—CFCP, FAEP, and other relatives' accounts never absorb your loss. "
            "When your account recovers back up to its prior High-Water Mark, you keep 100% of every recovery "
            "dollar ($0.00 to CFCP and $0.00 to FAEP). The 87/10/3 split resumes only on brand-new net profit "
            "strictly above your previous peak."
        ),
        "dollar_example": (
            "Example: Suppose your SCMA peaks at $1,200.00 (your HWM), dips to $1,000.00, and then earns "
            "$300.00 back to $1,300.00. The first $200.00 of recovery is 100% yours ($0.00 split); only the "
            "$100.00 of brand-new profit above $1,200.00 splits $87.00 SCMA / $10.00 CFCP / $3.00 FAEP."
        ),
        "university_pointer": "Try this in PDEUE University: Chapter 2 — Exact-Cent Accounting & High-Water Mark (/companion?chapter=2)",
        "lexicon_ids": ["high-water-mark-adr-012", "scma", "tpw-waterfall"],
    },
    {
        "id": "WATERFALL_87_10_3",
        "patterns": (
            r"87\s*/\s*10\s*/\s*3",
            r"\bwaterfall\b",
            r"\btpw\b",
            r"\bcfcp\b",
            r"\bfaep\b",
            r"\bprofit\s+split\b",
            r"\bcompound(?:ing)?\b",
        ),
        "concept": "WATERFALL_STEWARDSHIP",
        "answer": (
            "The 87/10/3 Transaction Profit Waterfall (TPW) divides brand-new net realized profit strictly above "
            "each member's High-Water Mark (ADR-012) in exact integer cents (ADR-008): 87% stays inside your "
            "private SCMA to compound; 10% (plus any floor-truncation remainder cents) builds the CFCP Central "
            "Familial Common Pool for family resilience and Phase II FSAP; and 3% funds FAEP Platform Stewardship "
            "for servers and data feeds—so members never pay out-of-pocket software bills and nothing is skimmed "
            "during losses or recovery."
        ),
        "dollar_example": (
            "Example: On $100.00 (10,000¢) of brand-new net profit above your High-Water Mark, $87.00 (8,700¢) "
            "stays in your SCMA, $10.00 (1,000¢) strengthens CFCP, and $3.00 (300¢) funds FAEP—exact to the cent."
        ),
        "university_pointer": "Try this in PDEUE University: Chapter 2 — The 87/10/3 Waterfall & Exact-Cent Math (/companion?chapter=2)",
        "lexicon_ids": ["tpw-waterfall", "high-water-mark-adr-012", "scma", "cfcp", "faep"],
    },
    {
        "id": "QUARTER_KELLY",
        "patterns": (
            r"\bquarter[\s-]kelly\b",
            r"\b0\.25f\*?\b",
            r"\bkelly\s+(?:criterion|sizing|fraction)\b",
            r"\bposition\s+sizing\b",
        ),
        "concept": "RISK_SIZING",
        "answer": (
            "Quarter-Kelly (0.25f*) uses only one fourth of the mathematical Kelly-optimal position size. "
            "It keeps the discipline of scaling with genuine edge while adding a wide safety cushion for "
            "probability estimation error and losing streaks. In PDEUE, Quarter-Kelly is strictly an upper "
            "ceiling—never a quota—clamped even tighter by your downward-only risk dial and 40% Dry-Powder Floor."
        ),
        "dollar_example": (
            "Example: If full Kelly math suggested risking $40.00 on a $1,000.00 account, Quarter-Kelly caps "
            "maximum exposure at $10.00—leaving $990.00 untouched so one surprise outcome stays small."
        ),
        "university_pointer": "Try this in PDEUE University: Chapter 3 — Quarter-Kelly & The 40% Cash Shield (/companion?chapter=3)",
        "lexicon_ids": ["quarter-kelly", "dry-powder-floor-40", "scma"],
    },
    {
        "id": "DRY_POWDER_FLOOR_40",
        "patterns": (
            r"\bdry[\s-]powder\b",
            r"\b40%\s*(?:floor|shield|cash|reserve)\b",
            r"\b40\s+percent\b",
            r"\bcash\s+shield\b",
            r"\breserve\s+floor\b",
        ),
        "concept": "DRY_POWDER_FLOOR_40",
        "answer": (
            "The 40% Dry-Powder Floor is a permanent, non-negotiable cash shield: at least 40% of every SCMA's "
            "equity (rounded conservatively upward in integer cents under ADR-008) must remain completely "
            "uncommitted in cash at all times. Even if high-conviction opportunities appear, the engine will "
            "evict lower-edge resting orders rather than breach your 40% reserve."
        ),
        "dollar_example": (
            "Example: On a $2,500.00 SCMA balance, at least $1,000.00 stays locked as uncommitted dry-powder "
            "cash at all times, capping total active working margin at $1,500.00."
        ),
        "university_pointer": "Try this in PDEUE University: Chapter 3 — Quarter-Kelly & The 40% Cash Shield (/companion?chapter=3)",
        "lexicon_ids": ["dry-powder-floor-40", "concentric-asset-rings", "adr-008-exact-cents"],
    },
    {
        "id": "DOWNWARD_ONLY_RISK_DIAL",
        "patterns": (
            r"\bdownward[\s-]only\b",
            r"\brisk\s+dial\b",
            r"\brisk\s+governor\b",
            r"\b0\.50%\b",
        ),
        "concept": "DOWNWARD_ONLY_RISK_DIAL",
        "answer": (
            "PDEUE's Downward-Only Risk Dial lets any member turn their own risk ceiling down (for example from "
            "2.00% down to 0.50%) whenever they want extra conservatism. However, turning the dial back UP is "
            "locked by design and requires F2-H Head of Household or F3 Risk Officer review—preventing impulsive "
            "risk chasing after a hot or cold streak."
        ),
        "dollar_example": (
            "Example: On a $2,000.00 SCMA, lowering your risk dial from 2.00% ($40.00 max risk per slot) to "
            "0.50% ($10.00 max risk per slot) takes effect immediately upon your manual click, while raising it "
            "back to 2.00% requires F2-H review."
        ),
        "university_pointer": "Try this in PDEUE University: Chapter 3 — Risk Governors & Family Guardrails (/companion?chapter=3)",
        "lexicon_ids": ["quarter-kelly", "scma"],
    },
    {
        "id": "ACTIVE_FLOAT_AND_IFAS_AIRGAP",
        "patterns": (
            r"\$?25,?000\b",
            r"\b25k\b",
            r"\bactive\s+float\b",
            r"\bfloat\s+cap\b",
            r"\badr[\s-]?011\b",
            r"\bifas\b",
            r"\bair[\s-]?gap\b",
            r"\bext-ref\b",
            r"\bbanking\s+credentials?\b",
            r"\brouting\s+number",
        ),
        "concept": "ACTIVE_FLOAT_AND_IFAS_AIRGAP",
        "answer": (
            "Each SCMA caps its active on-venue trading float at $25,000.00 so no single venue holds excess "
            "family capital; net profits above $25,000.00 sweep off-venue into protected bank custody. Under "
            "ADR-011 (Zero Banking Credentials & Air-Gapped Outbox), PDEUE NEVER stores bank routing numbers, "
            "account numbers, SWIFT codes, or banking logins—only an opaque EXT-REF memo token—while signed "
            "accounting messages cross strictly to our separate IFAS portal."
        ),
        "dollar_example": (
            "Example: When an SCMA reaches $26,400.00, $25,000.00 remains as the active float cap and the "
            "$1,400.00 overflow is instructed to sweep off-venue via an opaque EXT-REF token to IFAS—with zero "
            "bank routing numbers inside PDEUE."
        ),
        "university_pointer": "Try this in PDEUE University: Chapter 4 — Banking Air-Gap (ADR-011) & IFAS (/companion?chapter=4)",
        "lexicon_ids": ["adr-011-air-gap", "ifas", "scma"],
    },
    {
        "id": "THREE_TIER_WITHDRAWALS",
        "patterns": (
            r"\bthree[\s-]tier\b",
            r"\b3[\s-]tier\b",
            r"\bgreen[\s/\-]+yellow[\s/\-]+red\b",
            r"\byellow[\s-]tier\b",
            r"\bgreen[\s-]tier\b",
            r"\bred[\s-]tier\b",
            r"\bwithdrawal\s+(?:tiers?|rules?)\b",
            r"\bdirective\s+r-15\b",
        ),
        "concept": "THREE_TIER_WITHDRAWALS",
        "answer": (
            "Directive R-15 structures personal cash requests into Three Tiers: Green-Tier draws come from "
            "swept cash above the $25,000.00 active float cap and process without slowing compounding; Yellow-Tier "
            "draws dip into active working capital and display an exact-cent 6-month compounding impact card so "
            "you can see the trade-off before confirming; Red-Tier principal or custodial minor draws engage a "
            "24-hour cooling lock and require F2-H Head of Household or Chief Administrator co-signature."
        ),
        "dollar_example": (
            "Example: Drawing $300.00 from swept cash above $25,000.00 is Green-Tier; drawing $300.00 from a "
            "$1,500.00 active SCMA triggers a Yellow-Tier Impact Card showing $1,200.00 remaining; drawing over "
            "half your principal ($800.00) triggers Red-Tier 24h cooling + F2-H co-sign."
        ),
        "university_pointer": "Try this in PDEUE University: Chapter 4 — Three-Tier Distributions & Cooling Locks (/companion?chapter=4)",
        "lexicon_ids": ["scma", "dry-powder-floor-40", "adr-008-exact-cents"],
    },
    {
        "id": "ACTIVE_HAT_R06",
        "patterns": (
            r"\bactive[\s-]hat\b",
            r"\bdirective\s+r-?06\b",
            r"\br-?06\b",
            r"\brole\s+siloing\b",
            r"\bswitch\s+hats?\b",
        ),
        "concept": "ACTIVE_HAT_R06",
        "answer": (
            "Directive R-06 (Active-Hat Context Switching) guarantees that privileges never blend. Even when a "
            "family leader holds multiple responsibilities—such as a personal Class M member account and a "
            "Class F Advisor or Chief Administrator seat—they must explicitly switch Active Hats. Non-admin "
            "portals strip cross-role navigation links and enforce server-side HTTP 403 isolation."
        ),
        "dollar_example": (
            "Example: If a House leader with a $1,500.00 personal SCMA logs in under their MEMBER_USER hat, "
            "they can only inspect their own $1,500.00 balance; admin controls remain locked (HTTP 403) until "
            "an audited hat switch occurs."
        ),
        "university_pointer": "Try this in PDEUE University: Chapter 5 — Governance Roles & Active-Hat Discipline (/companion?chapter=5)",
        "lexicon_ids": ["active-hat-r06", "directive-r12-masking"],
    },
    {
        "id": "DIRECTIVE_R12_MASKING",
        "patterns": (
            r"\bdirective\s+r-?12\b",
            r"\br-?12\b",
            r"\bmasking\b",
            r"\$\*{4}\.\*{2}",
            r"\bscma-mem-\*{4}\b",
            r"\bclass\s+t\s+privacy\b",
        ),
        "concept": "DIRECTIVE_R12_MASKING",
        "answer": (
            "Directive R-12 enforces financial privacy blinds for technical operators (Class T: T1/T2/T3) and "
            "House Secretaries (H1). Engineers can monitor server health, latency, and order pipelines while "
            "all member dollar balances display as $****.** and account IDs mask to SCMA-MEM-****—unless an "
            "explicit, time-bounded, audited Chief Administrator override is active."
        ),
        "dollar_example": (
            "Example: While your Member Desktop shows your real $2,500.00 SCMA balance, a Class T engineer "
            "checking system health sees only $****.** and SCMA-MEM-****—protecting family financial privacy."
        ),
        "university_pointer": "Try this in PDEUE University: Chapter 5 — Directive R-12 Privacy Masking (/companion?chapter=5)",
        "lexicon_ids": ["directive-r12-masking", "active-hat-r06"],
    },
    {
        "id": "CUSTODIAL_MINORS",
        "patterns": (
            r"\bcustodial\b",
            r"\bminors?\b",
            r"\bchildren\b",
            r"\bapprentice\b",
        ),
        "concept": "CUSTODIAL_ACCOUNTS",
        "answer": (
            "Children and minors may hold an isolated custodial SCMA (is_custodial: true) funded with gifted "
            "seed capital. Trades route legally through the family trust while internal sub-ledgers track the "
            "child's exact equity; the F2-H Head of Household holds mandatory co-signature control over risk "
            "bounds and every withdrawal."
        ),
        "dollar_example": (
            "Example: A minor's $500.00 gifted SCMA compounds in its own sub-ledger while any $50.00 withdrawal "
            "request automatically pauses for F2-H parental co-signature."
        ),
        "university_pointer": "Try this in PDEUE University: Chapter 5 — Custodial Stewardship & Family Protection (/companion?chapter=5)",
        "lexicon_ids": ["scma", "active-hat-r06"],
    },
)

# Explicit indicators that a question belongs to Lane 2 (Public Market Research)
_PUBLIC_MARKET_PATTERNS: Tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(?:cpi|pce|inflation|bls|nfp|payroll|unemployment|gdp|fomc|federal\s+reserve|fed\s+rate|macroeconomic)\b", re.IGNORECASE),
    re.compile(r"\b(?:treasury|treasuries|t-?bill|yield\s+curve|bond\s+yield|10-?year|2-?year|30-?year|sofr|interest\s+rates?)\b", re.IGNORECASE),
    re.compile(r"\b(?:eia|natural\s+gas|energy\s+storage|crude\s+oil|wti|brent|henry\s+hub|petroleum|bcf|opec)\b", re.IGNORECASE),
    re.compile(r"\b(?:noaa|weather\s+oracle|nws|asos|temperature\s+contract|hurricane\s+contract|degree\s+days?|ensemble\s+forecast)\b", re.IGNORECASE),
    re.compile(r"\b(?:binary\s+contract|implied\s+probability|expected\s+value|probability\s+math|brier\s+score|calibration|fee\s+friction)\b", re.IGNORECASE),
    re.compile(r"\b(?:s&p\s*500|spx|nasdaq|vix|equity\s+index|forex|fx\s+rate|eur/usd|usd/jpy|dollar\s+index|dxy|cftc)\b", re.IGNORECASE),
)


def is_academy_balance_or_trade_request(query: str) -> bool:
    """Return True if a social-plane academy query requests balances or financial transactions."""
    lowered = html.unescape(query or "").lower()
    return any(phrase in lowered for phrase in _ACADEMY_MUTATION_PHRASES + _ACADEMY_BALANCE_PHRASES)


def match_local_canon_topic(query: str) -> Optional[Dict[str, Any]]:
    """Match a query against ratified Lane 1 Local PDEUE Canon topics or exact Lexicon entries."""
    q = html.unescape(query or "").strip()
    if not q:
        return None

    for topic in _CANON_TOPICS:
        for pattern in topic["patterns"]:
            if re.search(pattern, q, re.IGNORECASE):
                lex_ids = [tid for tid in topic["lexicon_ids"] if tid in LEXICON_BY_ID]
                return {
                    "concept": topic["concept"],
                    "answer": topic["answer"],
                    "dollar_example": topic["dollar_example"],
                    "university_pointer": topic["university_pointer"],
                    "lexicon_citations": lex_ids,
                }

    # Secondary check: explicit PDEUE acronym/concept lookup in LEXICON_BY_ID
    lowered = q.lower()
    for term_id, entry in LEXICON_BY_ID.items():
        short = str(entry.get("short_label", "")).lower()
        if len(short) >= 4 and re.search(rf"\b{re.escape(short)}\b", lowered):
            return {
                "concept": term_id.upper().replace("-", "_"),
                "answer": f"{entry['term']} ({entry['authority_ref']}): {entry['plain_english']}",
                "dollar_example": (
                    "Example: Every dollar figure tied to this rule is accounted for in exact integer cents "
                    "(ADR-008)—for instance, $1,000.00 is tracked as 100,000¢ with zero floating-point rounding drift."
                ),
                "university_pointer": "Try this in PDEUE University: Chapter 1 — PDEUE Canonical Lexicon & Safety Tour (/companion?chapter=1)",
                "lexicon_citations": [term_id],
            }
    return None


def is_public_market_research_query(query: str) -> bool:
    """Return True if a query asks about general public markets, macro data, oracles, or probability math."""
    q = html.unescape(query or "").strip()
    if not q:
        return False
    return any(pat.search(q) for pat in _PUBLIC_MARKET_PATTERNS)


class DualLaneTutor:
    """Safe, modular Dual-Lane AI Tutor (Local Canon + Local Media Playbooks + Grounded Public Web Research)."""

    def __init__(self, llm_client: Optional[BaseLLMClient] = None, *, local_first: bool = True):
        self._llm_client = llm_client
        self._local_first = bool(local_first)

    def _resolve_client(self) -> BaseLLMClient:
        if self._llm_client is not None:
            return self._llm_client
        return get_llm_client(fail_closed_to_mock=True)

    def answer_academy_query(
        self,
        *,
        query: str,
        member_id: str,
    ) -> Dict[str, Any]:
        """Answer a Community Academy Tutor prompt via Lane 1 (Local Canon/Playbooks) or Lane 2 (Public Web Research).

        Note: Caller (`social_plane_router.py`) checks `is_academy_balance_or_trade_request`
        and raises HTTP 403 before invoking this method.
        """
        cleaned_query = (query or "").strip()

        # 1. Nov 2026 CFTC / DEATH BETS Act Regulatory Content Filter (FAIL-CLOSED)
        reg = check_regulatory_content(cleaned_query)
        if not reg.allowed:
            return {
                "member_id": member_id,
                "query": cleaned_query,
                "answer": reg.reason,
                "concept": PROHIBITED_CODE,
                "mode": "EDUCATIONAL_ONLY",
                "lane": LANE_REGULATORY_REFUSAL,
                "lane_badge": REGULATORY_REFUSAL_BADGE,
                "disclaimer_badge": REGULATORY_CITATION,
                "dollar_example": None,
                "university_pointer": "Try this in PDEUE University: Chapter 1 — Eligible Regulated Markets & Ethics Charter (/companion?chapter=1)",
                "lexicon_citations": [],
                "citations": [],
                "unilateral_execution": False,
                "guard_blocked": True,
                "guard_category": PROHIBITED_CODE,
                "regulatory_blocked": True,
                "prohibited_category": reg.prohibited_category,
                "provider_used": "regulatory_filter",
                "model_used": "policy-v1",
                "fallback_used": False,
                "answered_locally": True,
                "media_refs": [],
                "playbook_steps": [],
                "manual_citations": [],
            }

        # 2. Lane 1 — Local-First PDEUE Canon + Role-Scoped Playbooks/Manuals (ZERO outbound LLM calls)
        canon = match_local_canon_topic(cleaned_query)
        local_hit = (
            get_local_knowledge_index().query(cleaned_query, role="CLASS_M")
            if self._local_first
            else None
        )
        if canon is not None or (local_hit is not None and local_hit.matched):
            media_refs = list(local_hit.media_refs) if local_hit and local_hit.matched else []
            playbook_steps = list(local_hit.playbook_steps) if local_hit and local_hit.matched else []
            manual_citations = list(local_hit.manual_citations) if local_hit and local_hit.matched else []
            if canon is not None:
                lex_cites = list(canon["lexicon_citations"])
                if local_hit and local_hit.lexicon_ids:
                    for lid in local_hit.lexicon_ids:
                        if lid in LEXICON_BY_ID and lid not in lex_cites:
                            lex_cites.append(lid)
                return {
                    "member_id": member_id,
                    "query": cleaned_query,
                    "answer": canon["answer"],
                    "concept": canon["concept"],
                    "mode": "EDUCATIONAL_ONLY",
                    "lane": LANE_LOCAL_CANON,
                    "lane_badge": LOCAL_CANON_BADGE,
                    "disclaimer_badge": None,
                    "dollar_example": canon["dollar_example"],
                    "university_pointer": canon["university_pointer"],
                    "lexicon_citations": lex_cites,
                    "citations": [],
                    "unilateral_execution": False,
                    "guard_blocked": False,
                    "guard_category": None,
                    "regulatory_blocked": False,
                    "prohibited_category": None,
                    "provider_used": "local_knowledge_index",
                    "model_used": f"local-index-{LEXICON_VERSION}",
                    "fallback_used": False,
                    "answered_locally": True,
                    "media_refs": media_refs,
                    "playbook_steps": playbook_steps,
                    "manual_citations": manual_citations,
                }

            assert local_hit is not None
            return {
                "member_id": member_id,
                "query": cleaned_query,
                "answer": local_hit.answer,
                "concept": (local_hit.top_playbook_id or "LOCAL_PLAYBOOK").upper().replace("-", "_"),
                "mode": "EDUCATIONAL_ONLY",
                "lane": LANE_LOCAL_CANON,
                "lane_badge": LOCAL_CANON_BADGE,
                "disclaimer_badge": None,
                "dollar_example": (
                    "Example: Every monetary rule referenced in our local manuals uses exact integer cents "
                    "(ADR-008)—for instance, $1,000.00 is tracked as 100,000¢ with a $400.00 (40%) Dry-Powder Floor."
                ),
                "university_pointer": "Try this in PDEUE University: Role Playbooks & Illustrated Manuals (/companion)",
                "lexicon_citations": [lid for lid in local_hit.lexicon_ids if lid in LEXICON_BY_ID],
                "citations": [],
                "unilateral_execution": False,
                "guard_blocked": False,
                "guard_category": None,
                "regulatory_blocked": False,
                "prohibited_category": None,
                "provider_used": "local_knowledge_index",
                "model_used": f"local-index-{LEXICON_VERSION}",
                "fallback_used": False,
                "answered_locally": True,
                "media_refs": media_refs,
                "playbook_steps": playbook_steps,
                "manual_citations": manual_citations,
            }

        # 3. Lane 2 — Grounded Public Market Research via BaseLLMClient (strictly external/unmatched queries)
        client = self._resolve_client()
        llm_resp: LLMResponse = client.research_public_web(
            cleaned_query,
            actor_role="MEMBER",
            actor_id=member_id or "community_member",
        )
        if llm_resp.guard_triggered:
            return {
                "member_id": member_id,
                "query": cleaned_query,
                "answer": llm_resp.content,
                "concept": str(llm_resp.guard_category or "GUARDRAIL_REFUSAL"),
                "mode": "EDUCATIONAL_ONLY",
                "lane": LANE_REGULATORY_REFUSAL,
                "lane_badge": "Blocked — Constitutional Guardrail",
                "disclaimer_badge": None,
                "dollar_example": None,
                "university_pointer": None,
                "lexicon_citations": [],
                "citations": [],
                "unilateral_execution": False,
                "guard_blocked": True,
                "guard_category": llm_resp.guard_category,
                "regulatory_blocked": False,
                "prohibited_category": None,
                "provider_used": llm_resp.provider,
                "model_used": llm_resp.model,
                "fallback_used": bool(llm_resp.fallback_used),
                "answered_locally": False,
                "media_refs": [],
                "playbook_steps": [],
                "manual_citations": [],
            }

        web_citations = list(llm_resp.web_citations or [])
        if not web_citations:
            web_citations = [
                {
                    "title": "Federal Reserve Economic Data (FRED) Public Research Library",
                    "url": "https://fred.stlouisfed.org/",
                    "source": "Federal Reserve Bank of St. Louis (FRED)",
                }
            ]
        return {
            "member_id": member_id,
            "query": cleaned_query,
            "answer": llm_resp.content,
            "concept": "PUBLIC_MARKET_RESEARCH",
            "mode": "EDUCATIONAL_ONLY",
            "lane": LANE_PUBLIC_WEB_RESEARCH,
            "lane_badge": PUBLIC_RESEARCH_DISCLAIMER_BADGE,
            "disclaimer_badge": PUBLIC_RESEARCH_DISCLAIMER_BADGE,
            "dollar_example": None,
            "university_pointer": "Want to practice safely? Explore Shadow Paper Hunch Studio on your Member Desktop (/member).",
            "lexicon_citations": [],
            "citations": web_citations,
            "unilateral_execution": False,
            "guard_blocked": False,
            "guard_category": None,
            "regulatory_blocked": False,
            "prohibited_category": None,
            "provider_used": llm_resp.provider,
            "model_used": llm_resp.model,
            "fallback_used": bool(llm_resp.fallback_used),
            "answered_locally": False,
            "media_refs": [],
            "playbook_steps": [],
            "manual_citations": [],
        }

    def answer_public_market_research(
        self,
        *,
        query: str,
        actor_id: str = "member_user",
        actor_role: str = "MEMBER",
    ) -> Dict[str, Any]:
        """Execute Lane 2 Grounded Public Market Research for the Member Desktop Tutor."""
        cleaned_query = (query or "").strip()
        client = self._resolve_client()
        llm_resp: LLMResponse = client.research_public_web(
            cleaned_query,
            actor_role=actor_role,
            actor_id=actor_id,
        )
        web_citations = list(llm_resp.web_citations or [])
        if not web_citations and not llm_resp.guard_triggered:
            web_citations = [
                {
                    "title": "Federal Reserve Economic Data (FRED) Public Research Library",
                    "url": "https://fred.stlouisfed.org/",
                    "source": "Federal Reserve Bank of St. Louis (FRED)",
                }
            ]
        return {
            "content": llm_resp.content,
            "citations": web_citations,
            "provider_used": llm_resp.provider,
            "model_used": llm_resp.model,
            "fallback_used": bool(llm_resp.fallback_used),
            "requested_provider": llm_resp.requested_provider,
            "guard_blocked": bool(llm_resp.guard_triggered),
            "guard_category": llm_resp.guard_category,
            "guard_reason": llm_resp.guard_reason,
            "audit_event_id": llm_resp.audit_event_id,
            "disclaimer_badge": PUBLIC_RESEARCH_DISCLAIMER_BADGE,
            "lane": LANE_PUBLIC_WEB_RESEARCH,
            "lane_badge": PUBLIC_RESEARCH_DISCLAIMER_BADGE,
            "unilateral_execution": False,
            "answered_locally": False,
            "media_refs": [],
            "playbook_steps": [],
            "manual_citations": [],
        }


_DEFAULT_DUAL_LANE_TUTOR = DualLaneTutor()


def get_dual_lane_tutor() -> DualLaneTutor:
    return _DEFAULT_DUAL_LANE_TUTOR
