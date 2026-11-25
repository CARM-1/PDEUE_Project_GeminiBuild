"""Class M Member AI Literacy Tutor (Milestone F2).

Wires the `/member` AI Literacy Tutor through the pluggable ``BaseLLMClient``
adapter pipeline (Milestone F1) with:
- Strict single-member SCMA context isolation (zero cross-member or admin leakage).
- Novice-friendly plain-English explanations & analogies grounded in ``lexicon_v05.py``.
- Exact 64-bit integer-cent Yellow-Tier Impact Cards (ADR-008; zero float currency math).
- Constitutional ``unilateral_execution = False`` invariant with deterministic
  non-executing ``AUTH-01``–``AUTH-04`` Action Cards.
- Prompt-injection, role-escalation, and Directive R-12 exfiltration refusal logging.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple
import uuid

from app.domain.ai_clients import (
    BaseLLMClient,
    LLMResponse,
    get_llm_client,
    inspect_user_input,
)
from app.domain.dual_lane_tutor import (
    LANE_LOCAL_CANON,
    LANE_PUBLIC_WEB_RESEARCH,
    LANE_REGULATORY_REFUSAL,
    LOCAL_CANON_BADGE,
    PUBLIC_RESEARCH_DISCLAIMER_BADGE,
    REGULATORY_REFUSAL_BADGE,
    is_public_market_research_query,
    match_local_canon_topic,
)
from app.domain.lexicon_v05 import LEXICON_BY_ID, LEXICON_VERSION, get_lexicon_payload
from app.domain.regulatory_filter import PROHIBITED_CODE, check_regulatory_content

MEMBER_TUTOR_SYSTEM_PROMPT = (
    "You are the PDEUE Class M Member AI Literacy Tutor. "
    "Explain concepts in warm, novice-friendly plain English using everyday analogies "
    "grounded strictly in PDEUE Lexicon v0.5, ADR-008 (exact integer cents), "
    "ADR-011 (zero banking credentials / IFAS outbox air-gap), and ADR-012 / Rule A14 "
    "(per-SCMA High-Water Mark and 100% SCMA loss isolation). "
    "CONSTITUTIONAL RULES: unilateral_execution = False ALWAYS. Never execute trades, "
    "withdrawals, risk-dial mutations, or governance actions. Never disclose another member's "
    "SCMA data, admin telemetry, or credentials."
)

_ACTIVE_FLOAT_CAP_CENTS = 2_500_000  # $25,000.00 hard active float cap
_CONSERVATIVE_MONTHLY_FACTOR_BPS = 11_000  # +10.00% illustrative conservative monthly factor
_STEADY_MONTHLY_SWEEP_CENTS = 280_000  # $2,800.00 conservative post-cap monthly sweep

_DOLLAR_AMOUNT_RE = re.compile(
    r"(?:\$\s*(\d[\d,]*)(?:\.(\d{1,2}))?|\b(\d[\d,]*)(?:\.(\d{1,2}))?\s*(?:dollars?|usd|bucks?)\b)",
    re.IGNORECASE,
)
_BARE_WITHDRAW_AMOUNT_RE = re.compile(
    r"\b(?:withdraw|take\s+out|pull\s+out|reduce(?:\s+my)?\s+seed\s+by|distribution\s+of|cash\s+out)\s+\$?\s*(\d[\d,]*)(?:\.(\d{1,2}))?\b",
    re.IGNORECASE,
)
_RISK_PCT_RE = re.compile(r"\b(\d+(?:\.\d{1,2})?)\s*%", re.IGNORECASE)


def format_exact_cents(cents: int) -> str:
    """Format integer cents into USD display string strictly via integer arithmetic (ADR-008)."""
    whole_cents = int(cents)
    sign = "-" if whole_cents < 0 else ""
    abs_cents = abs(whole_cents)
    return f"{sign}${abs_cents // 100:,}.{abs_cents % 100:02d}"


def parse_dollar_amount_cents(query: str) -> Optional[int]:
    """Parse a dollar amount from free text into exact integer cents (zero float currency math)."""
    text = query or ""
    for pattern in (_DOLLAR_AMOUNT_RE, _BARE_WITHDRAW_AMOUNT_RE):
        match = pattern.search(text)
        if not match:
            continue
        groups = [g for g in match.groups() if g is not None]
        if not groups:
            continue
        # Extract whole dollars and optional cents from the matched alternative.
        if pattern is _DOLLAR_AMOUNT_RE:
            whole_str = match.group(1) if match.group(1) is not None else match.group(3)
            frac_str = match.group(2) if match.group(1) is not None else match.group(4)
        else:
            whole_str = match.group(1)
            frac_str = match.group(2)
        if not whole_str:
            continue
        dollars = int(whole_str.replace(",", ""))
        cents_part = int(frac_str.ljust(2, "0")[:2]) if frac_str else 0
        total = dollars * 100 + cents_part
        if total > 0:
            return total
    return None


def _project_6m_exact_cents(starting_cents: int, months: int = 6) -> int:
    """Pure integer-cent illustrative 6-month compounding simulation (ADR-008)."""
    start = max(0, int(starting_cents))
    active = min(start, _ACTIVE_FLOAT_CAP_CENTS)
    swept = max(0, start - active)
    for _ in range(months):
        if active < _ACTIVE_FLOAT_CAP_CENTS:
            grown = (active * _CONSERVATIVE_MONTHLY_FACTOR_BPS) // 10_000
            if grown > _ACTIVE_FLOAT_CAP_CENTS:
                swept += grown - _ACTIVE_FLOAT_CAP_CENTS
                active = _ACTIVE_FLOAT_CAP_CENTS
            else:
                active = grown
        else:
            swept += _STEADY_MONTHLY_SWEEP_CENTS
    return active + swept


def build_member_tutor_context(member_state: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Project ONLY the requesting member's own SCMA fields (strict tenant isolation)."""
    st = dict(member_state or {})
    cash_cents = int(st.get("cash_cents", 25_000))
    hwm_cents = int(st.get("high_water_mark_cents", cash_cents))
    active_float_cents = int(st.get("active_float_cents", min(cash_cents, _ACTIVE_FLOAT_CAP_CENTS)))
    swept_cash_cents = int(st.get("swept_cash_cents", max(0, cash_cents - active_float_cents)))
    passive_yield_cents = int(st.get("passive_yield_cents", (cash_cents * 450) // 10_000))
    reserve_floor_cents = (cash_cents * 40 + 99) // 100
    bank_ref_token = str(st.get("bank_ref_token") or "EXT-REF-IFAS-****0000")
    if not bank_ref_token.startswith("EXT-REF-"):
        bank_ref_token = "EXT-REF-IFAS-****0000"

    return {
        "actor_role": "MEMBER",
        "scma_id": str(st.get("scma_id") or "SCMA-MEMBER-SELF"),
        "allowed_scma_id": str(st.get("scma_id") or "SCMA-MEMBER-SELF"),
        "member_name": str(st.get("name") or "Member"),
        "lineage_code": str(st.get("lineage_code") or "HOUSE-01"),
        "status": str(st.get("status") or "ACTIVE"),
        "is_custodial": bool(st.get("is_custodial", False)),
        "cash_cents": cash_cents,
        "high_water_mark_cents": hwm_cents,
        "active_float_cents": active_float_cents,
        "swept_cash_cents": swept_cash_cents,
        "passive_yield_cents": passive_yield_cents,
        "reserve_floor_cents": reserve_floor_cents,
        "risk_dial_pct": float(st.get("risk_dial_pct", 1.0)),
        "risk_ceiling_pct": float(st.get("risk_ceiling_pct", 2.0)),
        "bank_ref_token": bank_ref_token,
        "ifas_portal_host": str(st.get("ifas_portal_host") or "accounting.narratix.io"),
    }


def compute_yellow_tier_impact_card(
    member_ctx: Dict[str, Any],
    requested_cents: Optional[int] = None,
) -> Dict[str, Any]:
    """Compute a structured Yellow-Tier Compounding Impact Card in exact 64-bit integer cents."""
    current_balance_cents = max(0, int(member_ctx.get("cash_cents", 0)))
    hwm_cents = max(0, int(member_ctx.get("high_water_mark_cents", current_balance_cents)))
    swept_cash_cents = max(0, int(member_ctx.get("swept_cash_cents", 0)))
    is_custodial = bool(member_ctx.get("is_custodial", False))

    if requested_cents is None or requested_cents <= 0:
        # Default educational scenario: 25% of current SCMA balance (at least $100 if funded).
        default_req = max(current_balance_cents // 4, 10_000)
        requested_withdrawal_cents = min(default_req, current_balance_cents) if current_balance_cents > 0 else 10_000
    else:
        requested_withdrawal_cents = int(requested_cents)

    exceeds_balance = requested_withdrawal_cents > current_balance_cents
    effective_withdrawal_cents = min(requested_withdrawal_cents, current_balance_cents)
    post_withdrawal_balance_cents = max(0, current_balance_cents - effective_withdrawal_cents)

    # Mandatory 40% Dry-Powder Floor (rounded conservatively upward in integer cents).
    dry_powder_before_cents = (current_balance_cents * 40 + 99) // 100
    dry_powder_after_cents = (post_withdrawal_balance_cents * 40 + 99) // 100
    working_capital_before_cents = max(0, current_balance_cents - dry_powder_before_cents)
    working_capital_after_cents = max(0, post_withdrawal_balance_cents - dry_powder_after_cents)

    # Illustrative 6-month conservative compounding friction (strictly integer cents).
    projected_6m_baseline_cents = _project_6m_exact_cents(current_balance_cents, months=6)
    projected_6m_after_cents = _project_6m_exact_cents(post_withdrawal_balance_cents, months=6)
    compounding_friction_6m_cents = max(0, projected_6m_baseline_cents - projected_6m_after_cents)
    velocity_reduction_bps = (
        (compounding_friction_6m_cents * 10_000) // projected_6m_baseline_cents
        if projected_6m_baseline_cents > 0
        else 0
    )

    # Gentler partial alternative (50% floor-truncated integer cents).
    recommended_partial_cents = effective_withdrawal_cents // 2

    if is_custodial or exceeds_balance or (current_balance_cents > 0 and effective_withdrawal_cents * 2 > current_balance_cents):
        tier = "RED_TIER"
        auth_tier = "AUTH-03"
        tier_label = "Red-Tier Principal Lock (24h Cooling + F2-H / Chief Admin Co-Sign)"
    elif swept_cash_cents >= effective_withdrawal_cents and effective_withdrawal_cents > 0:
        tier = "GREEN_TIER"
        auth_tier = "AUTH-02"
        tier_label = "Green-Tier Swept Cash Eligible (Active Float Untouched)"
    else:
        tier = "YELLOW_TIER"
        auth_tier = "AUTH-02"
        tier_label = "Yellow-Tier Educational Friction (Active Compounding Float Impact)"

    return {
        "card_type": "YELLOW_TIER_IMPACT_CARD",
        "tier": tier,
        "tier_label": tier_label,
        "auth_tier": auth_tier,
        "scma_id": member_ctx["scma_id"],
        "currency_standard": "ADR-008_EXACT_INTEGER_CENTS",
        "current_balance_cents": current_balance_cents,
        "high_water_mark_cents": hwm_cents,
        "requested_withdrawal_cents": requested_withdrawal_cents,
        "effective_withdrawal_cents": effective_withdrawal_cents,
        "exceeds_balance": exceeds_balance,
        "post_withdrawal_balance_cents": post_withdrawal_balance_cents,
        "dry_powder_floor_before_cents": dry_powder_before_cents,
        "dry_powder_floor_after_cents": dry_powder_after_cents,
        "working_capital_before_cents": working_capital_before_cents,
        "working_capital_after_cents": working_capital_after_cents,
        "projected_6m_baseline_cents": projected_6m_baseline_cents,
        "projected_6m_after_withdrawal_cents": projected_6m_after_cents,
        "compounding_friction_6m_cents": compounding_friction_6m_cents,
        "velocity_reduction_bps": velocity_reduction_bps,
        "recommended_partial_cents": recommended_partial_cents,
        "display": {
            "current_balance": format_exact_cents(current_balance_cents),
            "requested_withdrawal": format_exact_cents(requested_withdrawal_cents),
            "post_withdrawal_balance": format_exact_cents(post_withdrawal_balance_cents),
            "dry_powder_floor_before": format_exact_cents(dry_powder_before_cents),
            "dry_powder_floor_after": format_exact_cents(dry_powder_after_cents),
            "projected_6m_baseline": format_exact_cents(projected_6m_baseline_cents),
            "projected_6m_after_withdrawal": format_exact_cents(projected_6m_after_cents),
            "compounding_friction_6m": format_exact_cents(compounding_friction_6m_cents),
            "velocity_reduction_pct": f"{velocity_reduction_bps // 100}.{velocity_reduction_bps % 100:02d}%",
            "recommended_partial": format_exact_cents(recommended_partial_cents),
        },
        "mutated": False,
        "unilateral_execution": False,
        "illustrative_only": True,
        "non_guarantee_notice": (
            "Illustrative exact-cent compounding simulation only — not a guarantee of future returns. "
            "No balance has been modified and no withdrawal has been submitted."
        ),
    }


def _make_action_card(
    *,
    action_type: str,
    auth_tier: str,
    title: str,
    description: str,
    ui_target: str,
    payload: Optional[Dict[str, Any]] = None,
    confirmation_notice: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "action_id": f"ACT-MEM-{uuid.uuid4().hex[:8].upper()}",
        "action_type": action_type,
        "auth_tier": auth_tier,
        "title": title,
        "description": description,
        "ui_target": ui_target,
        "payload": dict(payload or {}),
        "requires_human_confirmation": True,
        "unilateral_execution": False,
        "executed": False,
        "confirmation_notice": confirmation_notice
        or f"Non-executing {auth_tier} proposal: review and confirm manually inside your Member Desktop controls.",
    }


def _build_deterministic_tutor_draft(
    query: str,
    member_ctx: Dict[str, Any],
) -> Dict[str, Any]:
    """Compose a Lexicon v0.5 grounded, novice-friendly educational response + cards."""
    q = (query or "").lower().strip()
    scma_id = member_ctx["scma_id"]
    bal_str = format_exact_cents(member_ctx["cash_cents"])
    hwm_str = format_exact_cents(member_ctx["high_water_mark_cents"])
    floor_str = format_exact_cents(member_ctx["reserve_floor_cents"])
    risk_pct = float(member_ctx["risk_dial_pct"])
    bank_token = member_ctx["bank_ref_token"]
    ifas_host = member_ctx["ifas_portal_host"]

    # 1. Withdrawal / Seed Reduction / Distribution requests -> Yellow-Tier Impact Card + AUTH-02/03 card (ZERO mutation!)
    if any(
        marker in q
        for marker in (
            "withdraw",
            "withdrawal",
            "distribution",
            "take out",
            "pull out",
            "cash out",
            "reduce my seed",
            "reduce seed",
            "seed reduction",
            "yellow-tier",
            "yellow tier",
        )
    ):
        parsed_cents = parse_dollar_amount_cents(query)
        impact_card = compute_yellow_tier_impact_card(member_ctx, parsed_cents)
        disp = impact_card["display"]
        tier = impact_card["tier"]
        auth_tier = impact_card["auth_tier"]

        if impact_card["exceeds_balance"]:
            summary_note = (
                f"Your requested amount ({disp['requested_withdrawal']}) exceeds your current SCMA balance "
                f"({disp['current_balance']}), so a full withdrawal would leave $0.00 working capital and "
                "requires Red-Tier fiduciary review."
            )
        else:
            summary_note = (
                f"Removing {disp['requested_withdrawal']} from your {disp['current_balance']} SCMA leaves "
                f"{disp['post_withdrawal_balance']} to compound (with a {disp['dry_powder_floor_after']} mandatory "
                f"40% Dry-Powder Floor), creating an illustrative 6-month compounding drag of "
                f"{disp['compounding_friction_6m']} ({disp['velocity_reduction_pct']} slower velocity). "
                f"A gentler partial distribution of {disp['recommended_partial']} keeps more seed working."
            )

        content = (
            f"No funds have been moved (`unilateral_execution = False`). "
            f"Here is your {tier.replace('_', '-').title()} Compounding Impact Preview for {scma_id}: "
            f"{summary_note} "
            "Green-Tier draws come from swept cash above the $25,000 float cap; Yellow-Tier draws pause for "
            "compounding-friction education; Red-Tier principal or custodial draws require a 24-hour cooling lock "
            "and F2-H Head of Household / Chief Administrator co-sign."
        )
        analogy = (
            "Think of your active SCMA seed like a young fruit tree: picking apples from the overflow basket "
            "(Green-Tier swept cash above $25,000) doesn't slow next season's harvest, whereas trimming active "
            "branches early (Yellow-Tier) shrinks how much fruit the tree can grow over the next six months."
        )
        action_cards = [
            _make_action_card(
                action_type="STAGE_DISTRIBUTION_REVIEW",
                auth_tier=auth_tier,
                title=f"Review {disp['requested_withdrawal']} Distribution in Drawer",
                description=(
                    f"Pre-fill the 3-Tier Distribution Request Drawer with {disp['requested_withdrawal']} "
                    f"({impact_card['requested_withdrawal_cents']} cents) for manual review. No funds move automatically."
                ),
                ui_target="distribution_drawer",
                payload={
                    "scma_id": scma_id,
                    "amount_cents": impact_card["requested_withdrawal_cents"],
                    "recommended_partial_cents": impact_card["recommended_partial_cents"],
                    "tier": tier,
                },
                confirmation_notice=(
                    f"Staged under {auth_tier} (unilateral_execution = False): review your Yellow-Tier Impact Card "
                    "and submit explicitly via the Distribution Drawer if you choose to proceed."
                ),
            )
        ]
        return {
            "content": content,
            "analogy": analogy,
            "auth_tier": auth_tier,
            "impact_card": impact_card,
            "action_cards": action_cards,
            "citations": ["scma", "dry-powder-floor-40", "adr-008-exact-cents"],
        }

    # 2. Risk Dial / Downward-Only Governor (e.g., "set my risk to 2%", "how does the risk dial work?")
    if any(
        marker in q
        for marker in (
            "risk dial",
            "set my risk",
            "change my risk",
            "raise my risk",
            "increase my risk",
            "lower my risk",
            "reduce my risk",
            "downward-only",
            "risk governor",
        )
    ):
        pct_match = _RISK_PCT_RE.search(q)
        requested_pct = float(pct_match.group(1)) if pct_match else None
        if requested_pct is not None and requested_pct > risk_pct:
            auth_tier = "AUTH-03"
            action_type = "REQUEST_F2H_RISK_RESTORATION"
            card_title = f"Review F2-H Restoration Request ({requested_pct:.2f}%)"
            card_desc = (
                f"Your current dial is {risk_pct:.2f}%. Because the Risk Governor is downward-only, "
                f"raising exposure to {requested_pct:.2f}% requires F2-H Head of Household / F3 CRO review."
            )
            specific_line = (
                f"I have NOT changed your risk dial (`unilateral_execution = False`). "
                f"Your SCMA is currently at {risk_pct:.2f}%, and requesting {requested_pct:.2f}% is an upward change—"
                "which is locked to your F2-H Head of Household under PDEUE's Downward-Only Risk Governor."
            )
        else:
            auth_tier = "AUTH-02"
            action_type = "REVIEW_RISK_GOVERNOR"
            card_title = "Open Downward-Only Risk Governor"
            card_desc = (
                f"Review your current {risk_pct:.2f}% risk dial in the Member Desktop governor "
                "(downward reductions to 0.50% require manual confirmation)."
            )
            specific_line = (
                f"No setting has been changed (`unilateral_execution = False`). "
                f"Your SCMA risk dial is currently {risk_pct:.2f}% (ceiling {member_ctx['risk_ceiling_pct']:.2f}%). "
                "A risk dial is a safety ceiling on how much capital may be exposed to an opportunity. "
                "Members may turn the dial down toward 0.50% to be more conservative, while restoring it upward "
                "requires F2-H Head of Household or fiduciary review."
            )
        analogy = (
            "Think of the Downward-Only Risk Governor like a speed limiter on a family car: you can always "
            "lower the maximum speed yourself in rough weather, but raising the limit back up requires a "
            "family steward (F2-H) to turn the key with you."
        )
        return {
            "content": specific_line,
            "analogy": analogy,
            "auth_tier": auth_tier,
            "impact_card": None,
            "action_cards": [
                _make_action_card(
                    action_type=action_type,
                    auth_tier=auth_tier,
                    title=card_title,
                    description=card_desc,
                    ui_target="risk_governor",
                    payload={
                        "scma_id": scma_id,
                        "current_risk_pct": risk_pct,
                        "requested_risk_pct": requested_pct,
                    },
                )
            ],
            "citations": ["quarter-kelly", "scma"],
        }

    # 3. Direct manual trade / order execution command -> explain autonomous maker + AUTH-01–AUTH-04 (ZERO mutation)
    if any(
        marker in q
        for marker in (
            "buy ",
            "sell ",
            "place a trade",
            "place an order",
            "execute a trade",
            "trade for me",
            "bet on",
        )
    ):
        content = (
            "I cannot place trades or dispatch orders (`unilateral_execution = False` under AUTH-01–AUTH-04). "
            "In PDEUE, members never trade manually: qualified inside-maker orders are evaluated autonomously "
            "by the engine under Quarter-Kelly sizing and the 40% Dry-Powder Floor, and live execution remains "
            "fail-closed in Gate G1 (`HOLD_OBSERVATIONS_ONLY` / paper mode) until explicit Founder sign-off."
        )
        analogy = (
            "Think of yourself as a passenger in a certified commercial aircraft with a transparent cockpit window "
            "(the Glass Engine): you can inspect every instrument and safety reserve, but the Tutor is a flight "
            "educator—not a pilot grabbing the controls."
        )
        return {
            "content": content,
            "analogy": analogy,
            "auth_tier": "AUTH-01",
            "impact_card": None,
            "action_cards": [
                _make_action_card(
                    action_type="INSPECT_GLASS_ENGINE",
                    auth_tier="AUTH-01",
                    title="Inspect Glass Engine Concurrency Rack",
                    description="View your read-only 12-slot concurrency transparency rack and active safety rings.",
                    ui_target="glass_engine",
                    payload={"scma_id": scma_id},
                )
            ],
            "citations": ["gate-g1-qualification", "quarter-kelly", "dry-powder-floor-40"],
        }

    # 4. High-Water Mark / ADR-012 / Rule A14 / Loss Isolation
    if any(
        marker in q
        for marker in (
            "high-water",
            "high water",
            "hwm",
            "adr-012",
            "adr 012",
            "rule a14",
            "drawdown",
            "volatility tax",
            "loss isolation",
            "losing trade",
        )
    ):
        content = (
            f"Under ADR-012 (Per-SCMA High-Water Mark), your SCMA ({scma_id}) tracks its highest prior net equity "
            f"peak (currently {hwm_str}). The 87% SCMA / 10% CFCP / 3% FAEP Transaction Profit Waterfall applies "
            "strictly to net new realized profit above that High-Water Mark—floor-truncated in exact integer cents "
            "(ADR-008) with remainder cents routed to CFCP. Any gains earned while recovering from a drawdown stay "
            "100% inside your SCMA ($0 to CFCP, $0 to FAEP), eliminating volatility tax. Under Rule A14, 100% of "
            "any trading loss remains isolated inside the executing SCMA; CFCP, FAEP, and sibling accounts never "
            "absorb another member's loss."
        )
        analogy = (
            "Picture climbing a mountain and planting a flag at your highest elevation (your High-Water Mark). "
            "If you step down into a valley (a drawdown) and climb back up to your old flag, you keep 100% of "
            "that recovery climb—the 87/10/3 split only starts once you break fresh ground above the flag."
        )
        return {
            "content": content,
            "analogy": analogy,
            "auth_tier": "AUTH-01",
            "impact_card": None,
            "action_cards": [
                _make_action_card(
                    action_type="OPEN_LEXICON_TERM",
                    auth_tier="AUTH-01",
                    title="Open ADR-012 High-Water Mark in Lexicon v0.5",
                    description="Inspect the ratified Lexicon v0.5 entry for High-Water Mark / ADR-012.",
                    ui_target="glossary_drawer",
                    payload={"term_id": "high-water-mark-adr-012", "search": "ADR-012"},
                )
            ],
            "citations": ["high-water-mark-adr-012", "tpw-waterfall", "scma"],
        }

    # 5. 40% Dry-Powder Floor
    if any(
        marker in q
        for marker in (
            "dry-powder",
            "dry powder",
            "40%",
            "40 percent",
            "cash shield",
            "reserve floor",
            "uncommitted cash",
        )
    ):
        content = (
            f"The 40% Dry-Powder Floor is a mandatory uncommitted-cash shield: on your current {bal_str} balance, "
            f"at least {floor_str} must always remain uncommitted spendable cash after all active reservations "
            "(computed conservatively upward in exact integer cents under ADR-008). If a new opportunity would "
            "dip into that 40% shield, PDEUE's priority eviction engine drops lower-edge intents before the floor "
            "can ever be breached."
        )
        analogy = (
            "Imagine crossing a desert with ten canteens of water: you seal four canteens (40%) behind a steel "
            "latch as your survival reserve. No matter how promising a detour looks, you never drink from the "
            "sealed four—so an unexpected dry spell can never knock you out of the journey."
        )
        return {
            "content": content,
            "analogy": analogy,
            "auth_tier": "AUTH-01",
            "impact_card": None,
            "action_cards": [
                _make_action_card(
                    action_type="OPEN_LEXICON_TERM",
                    auth_tier="AUTH-01",
                    title="Inspect 40% Dry-Powder Floor in Lexicon v0.5",
                    description="Review the official Lexicon v0.5 definition and reserve rules.",
                    ui_target="glossary_drawer",
                    payload={"term_id": "dry-powder-floor-40", "search": "Dry-Powder"},
                )
            ],
            "citations": ["dry-powder-floor-40", "concentric-asset-rings", "adr-008-exact-cents"],
        }

    # 6. ADR-011 Banking Air-Gap & IFAS
    if any(
        marker in q
        for marker in (
            "adr-011",
            "adr 011",
            "air-gap",
            "air gap",
            "ifas",
            "bank",
            "banking",
            "ext-ref",
            "outbox",
            "funding",
            "routing",
        )
    ):
        content = (
            f"Under ADR-011 (Zero Banking Credentials & Air-Gapped Outbox), PDEUE never asks for, stores, or "
            "transmits bank routing numbers, bank account numbers, SWIFT/IBAN codes, or banking login credentials. "
            f"Inside PDEUE, your external funding rail is represented solely by your opaque deposit memo token "
            f"(`{bank_token}`). Accounting instructions cross to the separate Independent Financial Accounting "
            f"System (IFAS at `{ifas_host}`) exclusively through HMAC-SHA256 signed JSON-LD outbox events."
        )
        analogy = (
            "Think of ADR-011 like a valet coat-check ticket: PDEUE holds only your numbered paper stub "
            f"(`{bank_token}`), never the keys to your house or bank vault. When cash moves, a tamper-evident "
            "wax-sealed instruction (HMAC-SHA256 outbox) goes to the separate IFAS fiduciary desk."
        )
        return {
            "content": content,
            "analogy": analogy,
            "auth_tier": "AUTH-01",
            "impact_card": None,
            "action_cards": [
                _make_action_card(
                    action_type="OPEN_LEXICON_TERM",
                    auth_tier="AUTH-01",
                    title="Inspect ADR-011 Air-Gap in Lexicon v0.5",
                    description="Open the canonical ADR-011 Zero Banking Credentials glossary entry.",
                    ui_target="glossary_drawer",
                    payload={"term_id": "adr-011-air-gap", "search": "ADR-011"},
                )
            ],
            "citations": ["adr-011-air-gap", "adr-008-exact-cents"],
        }

    # 7. Quarter-Kelly Sizing
    if any(marker in q for marker in ("quarter-kelly", "quarter kelly", "kelly", "0.25f", "position size", "sizing")):
        content = (
            "Quarter-Kelly (0.25f*) starts with the mathematical Kelly position size, then uses only one quarter "
            "of it. That reduction creates a wide safety margin for imperfect probability estimates and limits the "
            "damage from normal losing streaks. Smaller positions make the chance of ruin much lower and preserve "
            "capital that can participate in later opportunities. Although defensive sizing may look slower on one "
            "trade, avoiding deep drawdowns usually lets compounding work faster and more reliably over the long term. "
            "In PDEUE, Quarter-Kelly is always an upper ceiling—never a spending quota—clamped further by your "
            f"risk dial ({risk_pct:.2f}%) and the 40% Dry-Powder Floor."
        )
        analogy = (
            "Think of Quarter-Kelly like driving at a quarter of a race car's top speed on a rainy mountain road: "
            "you still reach the destination steadily, and hitting one hidden pothole can never spin you off the cliff."
        )
        return {
            "content": content,
            "analogy": analogy,
            "auth_tier": "AUTH-01",
            "impact_card": None,
            "action_cards": [
                _make_action_card(
                    action_type="OPEN_LEXICON_TERM",
                    auth_tier="AUTH-01",
                    title="Inspect Quarter-Kelly (0.25f*) in Lexicon v0.5",
                    description="Open the canonical Quarter-Kelly sizing ceiling definition.",
                    ui_target="glossary_drawer",
                    payload={"term_id": "quarter-kelly", "search": "Quarter-Kelly"},
                )
            ],
            "citations": ["quarter-kelly", "dry-powder-floor-40"],
        }

    # 8. 87/10/3 Waterfall & Compounding (preserves all existing test phrases!)
    if any(
        marker in q
        for marker in (
            "87/10/3",
            "waterfall",
            "tpw",
            "simply",
            "snowball",
            "compound",
            "family treasury",
            "familial treasury",
            "cfcp",
            "faep",
            "stewardship",
        )
    ):
        content = (
            "The 87/10/3 waterfall divides each net realized gain above your High-Water Mark (ADR-012) into three "
            "purposeful buckets: 87% stays in your private SCMA to compound your balance; 10% (plus floor-division "
            "remainder cents under ADR-008) routes to the Familial Common Treasury (CFCP) to build our shared "
            "investment pool, debt relief facility (FSAP), and emergency shield; and 3% supports Platform "
            "Infrastructure & Stewardship (FAEP) to cover cloud servers and live data feeds. Stewardship is funded "
            "strictly from net profits—never from member pockets—and is never deducted on losing trades or during "
            "drawdown recovery."
        )
        analogy = (
            "Imagine harvesting 100 fresh apples above last season's record harvest: 87 apples go straight back "
            "into your personal orchard to grow next year's crop (SCMA), 10 go into the family community pantry "
            "(CFCP / FSAP), and 3 pay for the irrigation pipes and weather gauges (FAEP Stewardship). If a storm "
            "shrinks the harvest, nobody takes an apple from your basket."
        )
        return {
            "content": content,
            "analogy": analogy,
            "auth_tier": "AUTH-01",
            "impact_card": None,
            "action_cards": [
                _make_action_card(
                    action_type="OPEN_LEXICON_TERM",
                    auth_tier="AUTH-01",
                    title="Inspect 87/10/3 Waterfall in Lexicon v0.5",
                    description="Review exact-cent TPW conservation and High-Water Mark rules.",
                    ui_target="glossary_drawer",
                    payload={"term_id": "tpw-waterfall", "search": "87/10/3"},
                )
            ],
            "citations": ["tpw-waterfall", "high-water-mark-adr-012", "scma", "cfcp", "faep"],
        }

    # 9. Custodial / Children / Minors (preserves existing test phrases!)
    if any(marker in q for marker in ("children", "minors", "minor", "custodial")):
        content = (
            "Every member of the lineage—including children and minors—can hold an independent SCMA pre-funded "
            "with gifted seed capital. Because federal regulations prohibit minors from holding exchange accounts "
            "directly, all trades route through our family trust, while internal sub-ledgers track personal equity. "
            "Minor accounts are managed under custodial supervision (is_custodial: true), where parents (F2-H Head "
            "of Household) set conservative risk bounds and co-sign all withdrawals."
        )
        analogy = (
            "Think of a custodial SCMA like a locked family savings vault with the child's name engraved on it: "
            "the child can watch their savings grow transparently, while a parent holds the second key for any "
            "withdrawals or risk changes."
        )
        return {
            "content": content,
            "analogy": analogy,
            "auth_tier": "AUTH-01",
            "impact_card": None,
            "action_cards": [],
            "citations": ["scma", "active-hat-r06"],
        }

    # 10. Pay-It-Forward / Fostering / FSAP
    if any(marker in q for marker in ("foster", "sponsor", "pay it forward", "pay-it-forward", "fsap")):
        content = (
            "Pay-It-Forward Fostering lets a solvent member at the $25,000 float ceiling sponsor an incoming "
            "relative by transferring seed capital directly from protected swept bank cash. The sponsor becomes "
            "the new member's F1 Peer Mentor while lineage and custodial governance still apply. Alongside fostering, "
            "the Familial Stability Advance Pool (FSAP) uses the 10% CFCP treasury to extinguish predatory debt "
            "for relatives in need without disrupting trading velocity."
        )
        analogy = (
            "Once your own garden fills its $25,000 greenhouse and overflows into harvest baskets, you can hand "
            "a starter packet of seeds from your overflow to a cousin—helping them plant their own orchard while "
            "your greenhouse keeps humming."
        )
        return {
            "content": content,
            "analogy": analogy,
            "auth_tier": "AUTH-01",
            "impact_card": None,
            "action_cards": [],
            "citations": ["cfcp", "scma"],
        }

    # 11. Project FUTURE / Monthly After $25k
    if any(marker in q for marker in ("project future", "spawn 2.0", "diversification", "diversify")):
        content = (
            "Project FUTURE begins after the active trading float reaches its $25,000 ceiling. "
            "The same underwriting discipline then diversifies through SPAWN 2.0 into deep CME "
            "futures and rates, systematic sector equities and ETFs, G10 FX basis, and "
            "delta-neutral crypto funding while intraday rotation limits overnight gap risk."
        )
        analogy = (
            "Once one greenhouse reaches its optimal size ($25,000), instead of overcrowding it, the family "
            "opens five specialized greenhouses in deeper markets so no single season dictates the whole harvest."
        )
        return {
            "content": content,
            "analogy": analogy,
            "auth_tier": "AUTH-01",
            "impact_card": None,
            "action_cards": [],
            "citations": ["scma", "dry-powder-floor-40"],
        }

    if ("monthly" in q and not is_public_market_research_query(query)) or "after 25k" in q or "after $25k" in q or "float cap" in q:
        content = (
            "After the active float reaches $25,000, it remains intact while excess personal net profits sweep "
            "off-venue into protected bank cash. The illustrative steady-state cash run rate is approximately "
            "$7,800–$11,300 per month (illustrative only, not guaranteed), with swept cash earning 4.5% APY."
        )
        analogy = (
            "Picture a waterwheel with a $25,000 millpond: once the pond is full, extra rainwater spills cleanly "
            "into a calm reservoir (swept bank cash earning 4.5% APY) without flooding the wheel."
        )
        return {
            "content": content,
            "analogy": analogy,
            "auth_tier": "AUTH-01",
            "impact_card": None,
            "action_cards": [],
            "citations": ["scma", "adr-011-air-gap"],
        }

    # 11b. Additional Lane 1 Local Canon topics (Shadow Hunch rules, Phase I vs II, Active-Hat R-06, Directive R-12)
    canon_hit = match_local_canon_topic(query)
    if canon_hit is not None:
        return {
            "content": canon_hit["answer"],
            "analogy": (
                "PDEUE's local family canon pairs clear plain-English rules with exact-dollar examples "
                "so every family member knows exactly how their account is protected."
            ),
            "auth_tier": "AUTH-01",
            "impact_card": None,
            "action_cards": [],
            "citations": canon_hit["lexicon_citations"] or ["scma"],
            "dollar_example": canon_hit["dollar_example"],
            "university_pointer": canon_hit["university_pointer"],
            "lane": LANE_LOCAL_CANON,
        }

    # 12. Direct Lexicon v0.5 lookup for any remaining term (SCMA, Active-Hat R-06, Directive R-12, etc.)
    lex_hits = get_lexicon_payload(q=query).get("terms", []) if q else []
    if lex_hits:
        top = lex_hits[0]
        content = (
            f"{top['term']} ({top['authority_ref']}): {top['definition']} "
            f"For your own SCMA ({scma_id}), your current balance is {bal_str}, your High-Water Mark is "
            f"{hwm_str}, and your mandatory 40% Dry-Powder Floor is {floor_str}."
        )
        analogy = (
            "PDEUE's Lexicon v0.5 pairs every institutional rule with plain-English guardrails so you can always "
            "verify how your account is protected—without needing Wall Street jargon."
        )
        return {
            "content": content,
            "analogy": analogy,
            "auth_tier": "AUTH-01",
            "impact_card": None,
            "action_cards": [
                _make_action_card(
                    action_type="OPEN_LEXICON_TERM",
                    auth_tier="AUTH-01",
                    title=f"View {top['short_label']} in Lexicon {LEXICON_VERSION}",
                    description=top["tooltip"],
                    ui_target="glossary_drawer",
                    payload={"term_id": top["id"], "search": top["short_label"]},
                )
            ],
            "citations": [top["id"]],
            "lane": LANE_LOCAL_CANON,
        }

    # 12b. Lane 2 signal: general public market / economic / oracle / binary probability research
    if is_public_market_research_query(query):
        return {"lane": LANE_PUBLIC_WEB_RESEARCH}

    # 13. Friendly default grounded in the requesting member's own isolated SCMA posture.
    content = (
        f"I'm your Class M AI Literacy Tutor for {scma_id} (`unilateral_execution = False`). "
        f"Your current SCMA snapshot: balance {bal_str}, High-Water Mark {hwm_str}, mandatory 40% Dry-Powder "
        f"Floor {floor_str}, and downward-only risk dial {risk_pct:.2f}%. "
        "Ask me in everyday language about the 87/10/3 waterfall, 40% Dry-Powder Floor, Quarter-Kelly sizing, "
        "High-Water Mark (ADR-012), ADR-011 banking air-gap, Shadow Hunch rules, or general public market topics "
        "like CPI prints, Treasury yields, EIA energy storage, and NOAA weather oracles."
    )
    analogy = (
        "Think of this tutor as a patient family financial librarian: I can explain every gauge on your "
        "dashboard and model withdrawal trade-offs in exact cents, while leaving every real decision in your hands."
    )
    return {
        "content": content,
        "analogy": analogy,
        "auth_tier": "AUTH-01",
        "impact_card": None,
        "action_cards": [
            _make_action_card(
                action_type="OPEN_LEXICON_TERM",
                auth_tier="AUTH-01",
                title=f"Browse PDEUE Lexicon {LEXICON_VERSION}",
                description="Explore all plain-English definitions and aliases offline with zero network calls.",
                ui_target="glossary_drawer",
                payload={"search": ""},
            )
        ],
        "citations": ["scma", "tpw-waterfall", "dry-powder-floor-40"],
        "lane": LANE_LOCAL_CANON,
    }


class MemberLiteracyTutor:
    """Class M Member Dual-Lane AI Literacy Tutor wired through the pluggable BaseLLMClient layer."""

    def __init__(self, llm_client: Optional[BaseLLMClient] = None):
        self._llm_client = llm_client

    def _resolve_client(self) -> BaseLLMClient:
        if self._llm_client is not None:
            return self._llm_client
        return get_llm_client(fail_closed_to_mock=True)

    def answer_member_query(
        self,
        query: str,
        member_state: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Answer a Class M member literacy question with Dual-Lane routing, strict isolation & zero mutations."""
        prompt = (query or "").strip()
        member_ctx = build_member_tutor_context(member_state)
        client = self._resolve_client()

        # 1. Input prompt-injection, role-scope, secret, and cross-member guard runs FIRST.
        verdict = inspect_user_input(
            prompt,
            actor_role="MEMBER",
            actor_id=member_ctx["scma_id"],
            allowed_scma_id=member_ctx["scma_id"],
            member_name=member_ctx["member_name"],
        )
        if verdict.blocked:
            refusal = verdict.refusal_message or "Request refused under PDEUE constitutional guardrails."
            return {
                "role": "MEMBER_TUTOR",
                "query": prompt,
                "response": refusal,
                "answer": refusal,
                "analogy": None,
                "unilateral_execution": False,
                "auth_tier": "AUTH-01",
                "lane": LANE_REGULATORY_REFUSAL,
                "lane_badge": "Blocked — Constitutional Guardrail",
                "disclaimer_badge": None,
                "dollar_example": None,
                "university_pointer": None,
                "citations": [],
                "provider_used": client.provider_name if client.is_configured else "mock",
                "model_used": client.model_name if client.is_configured else "mock-v1",
                "fallback_used": not client.is_configured,
                "guard_blocked": True,
                "guard_category": verdict.category,
                "guard_reason": verdict.reason,
                "regulatory_blocked": False,
                "audit_event_id": verdict.audit_event_id,
                "lexicon_version": LEXICON_VERSION,
                "lexicon_citations": [],
                "impact_card": None,
                "action_cards": [],
                "member_scope": {
                    "scma_id": member_ctx["scma_id"],
                    "isolated": True,
                },
            }

        # 2. Nov 2026 CFTC / DEATH BETS Act Regulatory Content Filter (FAIL-CLOSED)
        reg = check_regulatory_content(verdict.sanitized_text)
        if not reg.allowed:
            return {
                "role": "MEMBER_TUTOR",
                "query": prompt,
                "response": reg.reason,
                "answer": reg.reason,
                "analogy": None,
                "unilateral_execution": False,
                "auth_tier": "AUTH-01",
                "lane": LANE_REGULATORY_REFUSAL,
                "lane_badge": REGULATORY_REFUSAL_BADGE,
                "disclaimer_badge": "Nov 2026 CFTC Event-Contract Scope & DEATH BETS Act",
                "dollar_example": None,
                "university_pointer": "Try this in PDEUE University: Chapter 1 — Eligible Regulated Markets & Ethics Charter (/companion?chapter=1)",
                "citations": [],
                "provider_used": "regulatory_filter",
                "model_used": "policy-v1",
                "fallback_used": False,
                "guard_blocked": True,
                "guard_category": PROHIBITED_CODE,
                "guard_reason": reg.reason,
                "regulatory_blocked": True,
                "prohibited_category": reg.prohibited_category,
                "audit_event_id": None,
                "lexicon_version": LEXICON_VERSION,
                "lexicon_citations": [],
                "impact_card": None,
                "action_cards": [],
                "member_scope": {
                    "scma_id": member_ctx["scma_id"],
                    "isolated": True,
                },
            }

        draft = _build_deterministic_tutor_draft(verdict.sanitized_text, member_ctx)

        # 3. Lane 2 — Grounded Public Market Research (unforeseen general economic/oracle/probability questions)
        if draft.get("lane") == LANE_PUBLIC_WEB_RESEARCH:
            llm_resp = client.research_public_web(
                verdict.sanitized_text,
                actor_role="MEMBER",
                actor_id=member_ctx["scma_id"],
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
                "role": "MEMBER_TUTOR",
                "query": prompt,
                "response": llm_resp.content,
                "answer": llm_resp.content,
                "analogy": (
                    "General public market research helps you understand how official economic, weather, "
                    "and energy benchmarks work—always separate public education from personal financial advice."
                ),
                "unilateral_execution": False,
                "auth_tier": "AUTH-01",
                "lane": LANE_PUBLIC_WEB_RESEARCH,
                "lane_badge": PUBLIC_RESEARCH_DISCLAIMER_BADGE,
                "disclaimer_badge": PUBLIC_RESEARCH_DISCLAIMER_BADGE,
                "dollar_example": None,
                "university_pointer": "Try testing this hypothesis risk-free in the Shadow Paper Hunch Studio below.",
                "citations": web_citations,
                "provider_used": llm_resp.provider,
                "model_used": llm_resp.model,
                "fallback_used": bool(llm_resp.fallback_used),
                "requested_provider": llm_resp.requested_provider,
                "guard_blocked": bool(llm_resp.guard_triggered),
                "guard_category": llm_resp.guard_category,
                "guard_reason": llm_resp.guard_reason,
                "regulatory_blocked": False,
                "audit_event_id": llm_resp.audit_event_id,
                "lexicon_version": LEXICON_VERSION,
                "lexicon_citations": [],
                "impact_card": None,
                "action_cards": [],
                "member_scope": {
                    "scma_id": member_ctx["scma_id"],
                    "isolated": True,
                },
            }

        # 4. Lane 1 — Local PDEUE Canon (grounded in LEXICON_BY_ID + member's isolated SCMA snapshot)
        canon_meta = match_local_canon_topic(verdict.sanitized_text) or {}
        dollar_example = draft.get("dollar_example") or canon_meta.get("dollar_example") or (
            f"Example: On your current {format_exact_cents(member_ctx['cash_cents'])} SCMA balance, "
            f"at least {format_exact_cents(member_ctx['reserve_floor_cents'])} remains sealed as your 40% Dry-Powder Floor."
        )
        university_pointer = draft.get("university_pointer") or canon_meta.get("university_pointer") or (
            "Try this in PDEUE University: Chapter 1 — PDEUE Canonical Rules & Safety Tour (/companion?chapter=1)"
        )

        llm_context = dict(member_ctx)
        llm_context["tutor_draft"] = draft

        llm_resp = client.generate_safe_response(
            system_prompt=MEMBER_TUTOR_SYSTEM_PROMPT,
            user_query=verdict.sanitized_text,
            context=llm_context,
            actor_role="MEMBER",
            actor_id=member_ctx["scma_id"],
            allowed_scma_id=member_ctx["scma_id"],
            member_name=member_ctx["member_name"],
        )

        # Ensure deterministic Lexicon citations and Yellow-Tier Impact Card survive any adapter.
        citations = [cid for cid in (llm_resp.citations or draft["citations"]) if cid in LEXICON_BY_ID]
        impact_card = llm_resp.impact_card if llm_resp.impact_card is not None else draft["impact_card"]
        action_cards = llm_resp.action_cards if llm_resp.action_cards else draft["action_cards"]
        final_text = llm_resp.content or draft["content"]

        return {
            "role": "MEMBER_TUTOR",
            "query": prompt,
            "response": final_text,
            "answer": final_text,
            "analogy": draft.get("analogy"),
            "unilateral_execution": False,
            "auth_tier": llm_resp.auth_tier or draft["auth_tier"],
            "lane": LANE_LOCAL_CANON,
            "lane_badge": LOCAL_CANON_BADGE,
            "disclaimer_badge": None,
            "dollar_example": dollar_example,
            "university_pointer": university_pointer,
            "citations": [],
            "provider_used": llm_resp.provider,
            "model_used": llm_resp.model,
            "fallback_used": bool(llm_resp.fallback_used),
            "requested_provider": llm_resp.requested_provider,
            "guard_blocked": bool(llm_resp.guard_triggered),
            "guard_category": llm_resp.guard_category,
            "guard_reason": llm_resp.guard_reason,
            "regulatory_blocked": False,
            "audit_event_id": llm_resp.audit_event_id,
            "lexicon_version": LEXICON_VERSION,
            "lexicon_citations": citations,
            "impact_card": impact_card,
            "action_cards": action_cards,
            "member_scope": {
                "scma_id": member_ctx["scma_id"],
                "isolated": True,
            },
        }
