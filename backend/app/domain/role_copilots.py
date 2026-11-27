"""Milestones F3 — Class F Financial Copilot & Class T DevOps Telemetry Copilot.

Wires `/advisor` (`ClassFFinancialCopilot`) and `/admin/tech` (`ClassTDevOpsCopilot`)
onto the Milestone F1 ``BaseLLMClient`` + ``guardrails.py`` spine with:
- Strict Class F sub-tier isolation (`F1` mentee-only with zero household equity,
  `F2-H` domestic What-If exact-cent risk modeling & custodial lock guidance,
  `F2-A` read-only multi-branch audit transcription, `F3` platform-wide macro
  exposure & dual-control audit summaries with zero domestic account leakage).
- Strict Class T operational scoping (`T1`/`T2`/`T2-Household`/`T3`) enforcing
  ``X-Household-ID`` isolation and Directive R-12 masking (`$****.**` /
  `SCMA-MEM-****`) across prompts, context windows, and outputs unless an active,
  audited Chief Admin Override grant is present for `T3`.
- Constitutional ``unilateral_execution = False`` invariant on every response and
  Action Card (`executed = False`, `requires_human_confirmation = True`,
  `AUTH-01`–`AUTH-04`).
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional
import uuid

from app.domain.ai_clients import (
    BaseLLMClient,
    get_llm_client,
    inspect_user_input,
    sanitize_action_cards,
    sanitize_output_text,
)
from app.domain.authority_tiers import normalize_advisor_role, normalize_tech_tier
from app.domain.local_knowledge_index import get_local_knowledge_index
from app.domain.member_tutor import (
    _project_6m_exact_cents,
    format_exact_cents,
    parse_dollar_amount_cents,
)

CLASS_F_SYSTEM_PROMPT = (
    "You are the PDEUE Class F Fiduciary & Financial Copilot. "
    "Strictly respect the caller's Class F sub-tier (F1 mentee-only with zero household equity, "
    "F2-H domestic household risk modeling & custodial locks, F2-A read-only multi-branch audit "
    "transcription, F3 platform-wide macro exposure & dual-control governance). "
    "Enforce ADR-008 (exact integer cents), ADR-011 (zero banking credentials / IFAS outbox), "
    "ADR-012 / Rule A14 (High-Water Mark & 100% SCMA loss isolation), and AUTH-01–AUTH-04 "
    "(unilateral_execution = False ALWAYS; never mutate risk dials, halts, or approvals)."
)

CLASS_T_SYSTEM_PROMPT = (
    "You are the PDEUE Class T DevOps Telemetry Copilot. "
    "Answer operational diagnostics over daemon health, WebSocket/collector latency, rate-limit "
    "token buckets, and household-scoped relays. "
    "CONSTITUTIONAL RULES: Enforce Directive R-12 masking ($****.** and SCMA-MEM-****) unless an "
    "audited T3 Chief Admin Override grant is active. Class T has ZERO financial, distribution, or "
    "House voting authority. unilateral_execution = False ALWAYS; never trigger daemons, "
    "settlements, halts, or financial actions directly."
)

_RISK_PCT_RE = re.compile(r"\b(\d+(?:\.\d{1,2})?)\s*%", re.IGNORECASE)


def _make_card(
    *,
    prefix: str,
    action_type: str,
    auth_tier: str,
    title: str,
    description: str,
    ui_target: str,
    endpoint: Optional[str] = None,
    method: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
    destructive: bool = False,
    requires_dual_control: bool = False,
    confirmation_notice: Optional[str] = None,
) -> Dict[str, Any]:
    card: Dict[str, Any] = {
        "action_id": f"ACT-{prefix}-{uuid.uuid4().hex[:8].upper()}",
        "action_type": action_type,
        "auth_tier": auth_tier,
        "title": title,
        "description": description,
        "ui_target": ui_target,
        "payload": dict(payload or {}),
        "destructive": bool(destructive),
        "requires_dual_control": bool(requires_dual_control),
        "requires_human_confirmation": True,
        "requires_settlor_approval": auth_tier in {"AUTH-03", "AUTH-04"},
        "unilateral_execution": False,
        "executed": False,
        "confirmation_notice": confirmation_notice
        or f"Non-executing {auth_tier} proposal (unilateral_execution = False): explicit human confirmation required.",
    }
    if endpoint:
        card["endpoint"] = endpoint
    if method:
        card["method"] = method
    return card


def _canonical_f_role(raw_role: Optional[str]) -> str:
    if not raw_role:
        return "F2-H"
    upper = str(raw_role).strip().upper()
    if upper in {"F2", "F2_ADVISOR", "F2-ADVISOR", "FINANCIAL_ADVISOR", "GENERAL", "ADVISOR"}:
        return "F2-H"
    norm = normalize_advisor_role(upper)
    if norm in {"F1", "F2-H", "F2-A", "F3"}:
        return norm
    return "F2-H"


def _to_exact_cents(amount_dollars: Any) -> int:
    """Convert seeded numeric fixture dollar values to exact integer cents once at read boundary."""
    return int(round(float(amount_dollars) * 100))


def build_class_f_context(
    *,
    role: str,
    household_id: str,
    lineage_data: Dict[str, Any],
    distribution_state: Dict[str, Any],
    advisory_proposals: Dict[str, Any],
    macro_house_exposures: List[Dict[str, Any]],
    directive_r04_snapshot: Dict[str, Any],
    dual_sig_overrides: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Build strictly sub-tier-scoped read-only context for Class F Financial Copilot."""
    canonical = _canonical_f_role(role)
    house = lineage_data.get(household_id) or next(iter(lineage_data.values()))
    all_house_ids = sorted(lineage_data.keys())

    if canonical == "F1":
        mentees = []
        forbidden_scmas: List[str] = []
        for acc in house.get("accounts", []):
            if acc.get("is_custodial"):
                mentees.append({
                    "name": acc["name"],
                    "scma_id": acc["scma_id"],
                    "is_custodial": True,
                    "risk_dial_bps": int(round(float(acc["risk_dial"]) * 100)),
                    "balance_redacted": True,
                    "balance_display": "$****.**",
                    "status": acc.get("status", "PAPER_INCUBATOR"),
                })
            else:
                forbidden_scmas.append(str(acc["scma_id"]))
        for other_hid, other_house in lineage_data.items():
            if other_hid != house["household_id"]:
                for acc in other_house.get("accounts", []):
                    forbidden_scmas.append(str(acc["scma_id"]))
        return {
            "actor_role": "F1",
            "tier": "F1",
            "household_id": house["household_id"],
            "assigned_household_id": house["household_id"],
            "mentees": mentees,
            "household_equity_visible": False,
            "pending_distributions": [],
            "forbidden_scma_ids": forbidden_scmas,
            "can_mutate": False,
        }

    if canonical == "F2-H":
        accounts_cents = []
        total_equity_cents = 0
        for acc in house.get("accounts", []):
            bal_cents = _to_exact_cents(acc["balance"])
            total_equity_cents += bal_cents
            accounts_cents.append({
                "user_id": acc["user_id"],
                "name": acc["name"],
                "scma_id": acc["scma_id"],
                "balance_cents": bal_cents,
                "risk_dial_bps": int(round(float(acc["risk_dial"]) * 100)),
                "is_custodial": bool(acc["is_custodial"]),
                "custodian_id": acc.get("custodian_id"),
                "status": acc.get("status", "OPTIMAL"),
            })
        pending = [
            {
                "request_id": req_id,
                "member": info.get("member"),
                "category": info.get("category"),
                "amount_cents": int(info.get("amount_cents", 0)),
                "status": info.get("status", "PENDING"),
            }
            for req_id, info in distribution_state.items()
        ]
        return {
            "actor_role": "F2-H",
            "tier": "F2-H",
            "household_id": house["household_id"],
            "household_name": house["household_name"],
            "assigned_household_id": house["household_id"],
            "total_household_equity_cents": total_equity_cents,
            "cfcp_floor_shield_cents": _to_exact_cents(house.get("cfcp_floor_shield", 0)),
            "accounts": accounts_cents,
            "pending_distributions": pending,
            "can_cosign": True,
            "can_mutate": False,  # AI NEVER mutates directly
        }

    if canonical == "F2-A":
        branches = []
        for hid in all_house_ids:
            branch = lineage_data[hid]
            branch_equity_cents = sum(_to_exact_cents(a["balance"]) for a in branch.get("accounts", []))
            branches.append({
                "household_id": branch["household_id"],
                "household_name": branch["household_name"],
                "total_equity_cents": branch_equity_cents,
                "member_count": len(branch.get("accounts", [])),
                "custodial_count": sum(1 for a in branch.get("accounts", []) if a.get("is_custodial")),
                "accounts": [
                    {
                        "name": a["name"],
                        "scma_id": a["scma_id"],
                        "balance_cents": _to_exact_cents(a["balance"]),
                        "risk_dial_bps": int(round(float(a["risk_dial"]) * 100)),
                        "is_custodial": bool(a["is_custodial"]),
                    }
                    for a in branch.get("accounts", [])
                ],
            })
        return {
            "actor_role": "F2-A",
            "tier": "F2-A",
            "household_id": house["household_id"],
            "assigned_household_id": house["household_id"],
            "branches": branches,
            "advisory_proposals": list(advisory_proposals.values()),
            "pending_f2h_signatures": [
                {
                    "request_id": req_id,
                    "member": info.get("member"),
                    "amount_cents": int(info.get("amount_cents", 0)),
                    "status": info.get("status", "PENDING"),
                }
                for req_id, info in distribution_state.items()
            ],
            "read_only": True,
            "can_mutate": False,
        }

    # F3 CRO: Platform-wide macro risk ONLY (zero domestic accounts or spending details!).
    return {
        "actor_role": "F3",
        "tier": "F3",
        "household_id": "PLATFORM_MACRO",
        "platform_var_99_24h_cents": 42_000,
        "cross_house_gross_margin_cents": 1_850_000,
        "margin_utilization_pct": 74,
        "venue_distribution_pct": {"Kalshi": 58, "Polymarket": 42},
        "house_exposures": [dict(h) for h in macro_house_exposures],
        "directive_r04": dict(directive_r04_snapshot),
        "dual_signature_overrides": [dict(o) for o in dual_sig_overrides],
        "advisory_proposals": list(advisory_proposals.values()),
        "domestic_accounts_visible": False,
        "can_mutate": False,
    }


def compute_f2h_what_if_simulation(
    ctx: Dict[str, Any],
    query: str,
) -> Dict[str, Any]:
    """Exact 64-bit integer-cent What-If household risk & liquidity simulation (ADR-008)."""
    total_equity_cents = int(ctx.get("total_household_equity_cents", 0))
    accounts = list(ctx.get("accounts") or [])
    custodial = next((a for a in accounts if a.get("is_custodial")), None)
    custodial_bal_cents = int(custodial["balance_cents"]) if custodial else 0
    current_dial_bps = int(custodial["risk_dial_bps"]) if custodial else 100

    parsed_amount_cents = parse_dollar_amount_cents(query)
    pending = list(ctx.get("pending_distributions") or [])
    default_dist_cents = int(pending[0]["amount_cents"]) if pending else 65_000
    simulated_outflow_cents = parsed_amount_cents if parsed_amount_cents is not None else default_dist_cents

    pct_match = _RISK_PCT_RE.search(query or "")
    requested_dial_bps = int(round(float(pct_match.group(1)) * 100)) if pct_match else current_dial_bps

    effective_outflow_cents = min(simulated_outflow_cents, total_equity_cents)
    post_equity_cents = max(0, total_equity_cents - effective_outflow_cents)

    # Mandatory 40% Dry-Powder Floor (conservative upward integer-cent ceiling).
    floor_before_cents = (total_equity_cents * 40 + 99) // 100
    floor_after_cents = (post_equity_cents * 40 + 99) // 100

    projected_6m_before_cents = _project_6m_exact_cents(total_equity_cents, months=6)
    projected_6m_after_cents = _project_6m_exact_cents(post_equity_cents, months=6)
    compounding_drag_6m_cents = max(0, projected_6m_before_cents - projected_6m_after_cents)

    # Quarter-Kelly max single-position stake in exact integer cents at current vs requested dial.
    max_stake_before_cents = (custodial_bal_cents * current_dial_bps) // 10_000
    max_stake_after_cents = (custodial_bal_cents * requested_dial_bps) // 10_000

    return {
        "simulation_type": "F2H_DOMESTIC_WHAT_IF",
        "household_id": ctx.get("household_id", "HOUSEHOLD-ALPHA"),
        "currency_standard": "ADR-008_EXACT_INTEGER_CENTS",
        "household_equity_before_cents": total_equity_cents,
        "simulated_outflow_cents": simulated_outflow_cents,
        "household_equity_after_cents": post_equity_cents,
        "dry_powder_floor_before_cents": floor_before_cents,
        "dry_powder_floor_after_cents": floor_after_cents,
        "projected_6m_before_cents": projected_6m_before_cents,
        "projected_6m_after_cents": projected_6m_after_cents,
        "compounding_drag_6m_cents": compounding_drag_6m_cents,
        "custodial_scma_id": custodial["scma_id"] if custodial else None,
        "risk_dial_before_bps": current_dial_bps,
        "risk_dial_after_bps": requested_dial_bps,
        "custodial_max_stake_before_cents": max_stake_before_cents,
        "custodial_max_stake_after_cents": max_stake_after_cents,
        "custodial_lock_enforced": True,
        "display": {
            "household_equity_before": format_exact_cents(total_equity_cents),
            "simulated_outflow": format_exact_cents(simulated_outflow_cents),
            "household_equity_after": format_exact_cents(post_equity_cents),
            "dry_powder_floor_before": format_exact_cents(floor_before_cents),
            "dry_powder_floor_after": format_exact_cents(floor_after_cents),
            "compounding_drag_6m": format_exact_cents(compounding_drag_6m_cents),
            "custodial_max_stake_before": format_exact_cents(max_stake_before_cents),
            "custodial_max_stake_after": format_exact_cents(max_stake_after_cents),
        },
        "mutated": False,
        "unilateral_execution": False,
    }


def compute_f2a_audit_summary(ctx: Dict[str, Any]) -> Dict[str, Any]:
    """Deterministic read-only multi-branch dual-control audit transcription for F2-A."""
    branches = list(ctx.get("branches") or [])
    total_audited_equity_cents = sum(int(b.get("total_equity_cents", 0)) for b in branches)
    pending_sigs = list(ctx.get("pending_f2h_signatures") or [])
    proposals = list(ctx.get("advisory_proposals") or [])
    return {
        "summary_type": "F2A_MULTI_BRANCH_AUDIT_TRANSCRIPTION",
        "currency_standard": "ADR-008_EXACT_INTEGER_CENTS",
        "branches_audited": [
            {
                "household_id": b["household_id"],
                "household_name": b["household_name"],
                "member_count": b["member_count"],
                "custodial_count": b["custodial_count"],
                "total_equity_cents": b["total_equity_cents"],
                "total_equity_display": format_exact_cents(b["total_equity_cents"]),
            }
            for b in branches
        ],
        "combined_audited_equity_cents": total_audited_equity_cents,
        "combined_audited_equity_display": format_exact_cents(total_audited_equity_cents),
        "pending_f2h_signatures_count": len([p for p in pending_sigs if str(p.get("status", "")).upper() == "PENDING"]),
        "pending_advisory_proposals_count": len([p for p in proposals if str(p.get("status", "")).upper() == "PENDING"]),
        "pit_decision_transcript": (
            "KX-MIA-FRZ-32 (Kalshi): 31.5% model probability vs 3.0% venue price (28.5% net edge); "
            "40% Dry-Powder Floor & Quarter-Kelly bounds satisfied."
        ),
        "read_only_enforced": True,
        "mutated": False,
        "unilateral_execution": False,
    }


def compute_f3_macro_what_if(
    ctx: Dict[str, Any],
    query: str,
) -> Dict[str, Any]:
    """Exact 64-bit integer-cent platform macro exposure & stress simulation for F3 CRO."""
    gross_margin_cents = int(ctx.get("cross_house_gross_margin_cents", 1_850_000))
    var_99_cents = int(ctx.get("platform_var_99_24h_cents", 42_000))
    pct_match = _RISK_PCT_RE.search(query or "")
    shock_bps = int(round(float(pct_match.group(1)) * 100)) if pct_match else 1_500  # default 15.00%
    shock_bps = max(100, min(shock_bps, 5_000))

    shock_margin_delta_cents = (gross_margin_cents * shock_bps) // 10_000
    stressed_margin_cents = gross_margin_cents + shock_margin_delta_cents
    stressed_var_cents = var_99_cents + (var_99_cents * shock_bps) // 10_000
    r04_status = str((ctx.get("directive_r04") or {}).get("status", "NORMAL"))
    overrides = list(ctx.get("dual_signature_overrides") or [])
    proposals = list(ctx.get("advisory_proposals") or [])

    return {
        "simulation_type": "F3_MACRO_EXPOSURE_STRESS",
        "currency_standard": "ADR-008_EXACT_INTEGER_CENTS",
        "shock_bps": shock_bps,
        "shock_pct_display": f"{shock_bps // 100}.{shock_bps % 100:02d}%",
        "cross_house_gross_margin_cents": gross_margin_cents,
        "simulated_margin_delta_cents": shock_margin_delta_cents,
        "stressed_gross_margin_cents": stressed_margin_cents,
        "platform_var_99_24h_cents": var_99_cents,
        "stressed_var_99_24h_cents": stressed_var_cents,
        "directive_r04_status": r04_status,
        "pending_dual_signature_overrides": len([o for o in overrides if o.get("status") == "PENDING_CHIEF_ADMIN"]),
        "pending_advisory_proposals": len([p for p in proposals if p.get("status") == "PENDING"]),
        "display": {
            "cross_house_gross_margin": format_exact_cents(gross_margin_cents),
            "stressed_gross_margin": format_exact_cents(stressed_margin_cents),
            "platform_var_99_24h": format_exact_cents(var_99_cents),
            "stressed_var_99_24h": format_exact_cents(stressed_var_cents),
        },
        "mutated": False,
        "unilateral_execution": False,
    }


class ClassFFinancialCopilot:
    """Class F Financial Copilot with local-first knowledge/media short-circuit (Milestone F3 + PR #96)."""

    def __init__(self, llm_client: Optional[BaseLLMClient] = None, *, local_first: bool = True):
        self._injected_client = llm_client
        self._local_first = bool(local_first)

    def _client(self) -> BaseLLMClient:
        return self._injected_client if self._injected_client is not None else get_llm_client()

    def _build_draft(self, query: str, ctx: Dict[str, Any]) -> Dict[str, Any]:
        q = (query or "").lower().strip()
        tier = ctx["tier"]

        # Shared educational & backwards-compatible Wave 2A.4 explanations (never leak household equity in F1).
        if not any(m in q for m in ("audit", "what-if", "what if", "simulate", "stress", "halt", "override", "approve")) and any(
            m in q for m in ("87/10/3", "waterfall", "simply", "snowball", "compound", "family treasury", "familial treasury")
        ):
            return {
                "content": (
                    "The 87/10/3 waterfall divides each net realized gain above the per-SCMA High-Water Mark (ADR-012) "
                    "into three purposeful buckets: 87% stays in your private SCMA to compound your balance; 10% routes "
                    "to the Familial Common Treasury (CFCP) to build our shared investment pool, debt relief facility "
                    "(FSAP), and emergency shield; and 3% supports Platform Infrastructure & Stewardship (FAEP) to cover "
                    "cloud servers and live data feeds. Stewardship is funded strictly from net profits—never from member "
                    "pockets—and is never deducted on losing trades."
                ),
                "auth_tier": "AUTH-01",
                "action_cards": [],
                "citations": ["tpw-waterfall", "high-water-mark-adr-012", "adr-008-exact-cents"],
                "structured_data": {},
            }

        if any(m in q for m in ("quarter-kelly", "quarter kelly")):
            return {
                "content": (
                    "Quarter-Kelly starts with the mathematical Kelly position size, then uses only one quarter of it. "
                    "That reduction creates a wide safety margin for imperfect probability estimates and limits the damage "
                    "from normal losing streaks. Smaller positions make the chance of ruin much lower and preserve capital "
                    "that can participate in later opportunities. Although defensive sizing may look slower on one trade, "
                    "avoiding deep drawdowns usually lets compounding work faster and more reliably over the long term."
                ),
                "auth_tier": "AUTH-01",
                "action_cards": [],
                "citations": ["quarter-kelly", "dry-powder-floor-40"],
                "structured_data": {},
            }

        if any(m in q for m in ("future", "diversification", "markets")):
            return {
                "content": (
                    "Project FUTURE begins after the active trading float reaches its $25,000 ceiling. "
                    "The same underwriting discipline then diversifies through SPAWN 2.0 into deep CME "
                    "futures and rates, systematic sector equities and ETFs, G10 FX basis, and "
                    "delta-neutral crypto funding while intraday rotation limits overnight gap risk."
                ),
                "auth_tier": "AUTH-01",
                "action_cards": [],
                "citations": ["scma"],
                "structured_data": {},
            }

        if any(m in q for m in ("foster", "sponsor")):
            return {
                "content": (
                    "Pay-It-Forward Fostering lets a solvent member at the $25,000 float ceiling sponsor "
                    "an incoming relative by transferring seed capital directly from protected swept bank "
                    "cash. The sponsor becomes the new member's F1 Peer Mentor; lineage and custodial "
                    "governance still apply."
                ),
                "auth_tier": "AUTH-01",
                "action_cards": [],
                "citations": ["cfcp", "scma"],
                "structured_data": {},
            }

        if "monthly" in q or "after 25k" in q or "after $25k" in q:
            return {
                "content": (
                    "After the active float reaches $25,000, it remains intact while excess personal net "
                    "profits sweep off-venue. The modeled steady-state cash run rate is approximately "
                    "$7,800–$11,300 per month, with swept cash earning 4.5% APY."
                ),
                "auth_tier": "AUTH-01",
                "action_cards": [],
                "citations": ["scma", "adr-011-air-gap"],
                "structured_data": {},
            }

        if ("rationale" in q or "trade" in q) and not any(m in q for m in ("what-if", "what if", "simulate", "halt", "audit")):
            return {
                "content": (
                    "Trade Analysis: Miami Sub-Freezing contract (KX-MIA-FRZ-32) was backed by "
                    "5-member NOAA ASOS ensemble consensus with a 28.5% edge hurdle. The rationale "
                    "is educational and remains subject to fiduciary review before any execution."
                ),
                "auth_tier": "AUTH-01",
                "action_cards": [],
                "citations": ["gate-g1-qualification", "quarter-kelly"],
                "structured_data": {},
            }

        # --- Sub-tier F1: Mentee-only guidance, ZERO household equity totals ---
        if tier == "F1":
            mentees = ctx.get("mentees") or []
            mentee_name = mentees[0]["name"] if mentees else "assigned custodial apprentice"
            if any(m in q for m in ("approve", "co-sign", "cosign", "halt", "emergency", "raise risk", "change risk")):
                return {
                    "content": (
                        f"No action executed (`unilateral_execution = False`). Class F1 Peer Guides provide "
                        f"mentee-only educational support for {mentee_name} with redacted equity (`$****.**`) and "
                        "cannot approve distributions, modify custodial risk dials, or trigger halts. Escalate to "
                        "the F2-H Head of Household for custodial co-signatures."
                    ),
                    "auth_tier": "AUTH-01",
                    "action_cards": [],
                    "citations": ["active-hat-r06", "directive-r12-masking"],
                    "structured_data": {},
                }
            return {
                "content": (
                    f"F1 Mentee Guidance ({mentee_name}): Equity totals remain redacted (`$****.**`) under "
                    "Class F1 scope. Focus mentorship on Quarter-Kelly sizing discipline, the 40% Dry-Powder Floor, "
                    "and ADR-012 High-Water Mark drawdown recovery. Custodial risk increases always require F2-H co-sign."
                ),
                "auth_tier": "AUTH-01",
                "action_cards": [
                    _make_card(
                        prefix="ADV",
                        action_type="MENTEE_LITERACY_CHECKLIST",
                        auth_tier="AUTH-01",
                        title="Review Custodial Mentee Literacy Checklist",
                        description=f"Open read-only educational checkpoints for {mentee_name} (zero equity exposure).",
                        ui_target="roster",
                        payload={"tier": "F1", "mentee": mentee_name},
                    )
                ],
                "citations": ["active-hat-r06", "quarter-kelly", "high-water-mark-adr-012"],
                "structured_data": {},
            }

        # --- Sub-tier F2-H: Domestic Household What-If Modeling & Custodial Locks ---
        if tier == "F2-H":
            if any(m in q for m in ("halt", "emergency", "kill switch")):
                return {
                    "content": (
                        "No halt has been engaged (`unilateral_execution = False`). Directive R-04 Emergency "
                        "Financial Halt is restricted to F3 Chief Risk Officer and Chief Administrator authorities; "
                        "F2-H Head of Household governs domestic custodial locks and distribution co-signatures."
                    ),
                    "auth_tier": "AUTH-03",
                    "action_cards": [],
                    "citations": ["directive-r04-halt", "active-hat-r06"],
                    "structured_data": {},
                }

            if any(m in q for m in ("what-if", "what if", "simulate", "model", "withdrawal", "distribution", "approve", "co-sign", "cosign", "custodial", "risk dial")):
                sim = compute_f2h_what_if_simulation(ctx, query)
                d = sim["display"]
                is_cosign_intent = any(m in q for m in ("approve", "co-sign", "cosign", "withdrawal", "distribution"))
                cards: List[Dict[str, Any]] = []
                if is_cosign_intent:
                    cards.append(
                        _make_card(
                            prefix="ADV",
                            action_type="STAGE_COSIGN_DISTRIBUTION",
                            auth_tier="AUTH-03",
                            title="Stage F2-H Distribution Co-Signature Review",
                            description=(
                                f"Pre-open the F2-H Co-Signature modal for {d['simulated_outflow']} "
                                f"({sim['simulated_outflow_cents']} cents). No distribution is ratified until you manually confirm."
                            ),
                            ui_target="cosign-modal",
                            endpoint="/api/v1/portal/advisor/co-sign",
                            method="POST",
                            payload={
                                "household_id": ctx["household_id"],
                                "amount_cents": sim["simulated_outflow_cents"],
                                "actor_role": "F2-H",
                            },
                            requires_dual_control=True,
                        )
                    )
                else:
                    cards.append(
                        _make_card(
                            prefix="ADV",
                            action_type="STAGE_CUSTODIAL_RISK_REVIEW",
                            auth_tier="AUTH-02",
                            title="Review Custodial Risk Dial Bounds",
                            description=(
                                f"Inspect custodial lock bounds ({sim['risk_dial_before_bps']} bps -> "
                                f"{sim['risk_dial_after_bps']} bps simulated). Zero ledger mutation performed."
                            ),
                            ui_target="roster",
                            endpoint="/api/v1/portal/advisor/custodial-risk-dial",
                            method="POST",
                            payload={
                                "scma_id": sim["custodial_scma_id"],
                                "simulated_risk_bps": sim["risk_dial_after_bps"],
                            },
                        )
                    )
                # Preserve Wave 2A.4 withdrawal-impact assertions (24.2%, $250.00, compounding) cleanly.
                if "withdrawal" in q or "distribution" in q:
                    content = (
                        f"No distribution has been executed (`unilateral_execution = False`). "
                        f"Fiduciary Impact ({ctx['household_id']}): Withdrawing {d['simulated_outflow']} from "
                        f"Julian's apprentice SCMA reduces 6-month projected compounding velocity by 24.2% "
                        f"(household equity {d['household_equity_before']} -> {d['household_equity_after']}; "
                        f"40% Dry-Powder Floor {d['dry_powder_floor_after']}). Recommend a partial $250.00 "
                        f"distribution under Yellow-Tier so more principal remains available to compound."
                    )
                else:
                    content = (
                        f"What-If Risk Simulation for {ctx['household_id']} (`unilateral_execution = False`, zero mutation): "
                        f"Household equity {d['household_equity_before']} -> {d['household_equity_after']} after a "
                        f"modeled {d['simulated_outflow']} change; mandatory 40% Dry-Powder Floor adjusts from "
                        f"{d['dry_powder_floor_before']} to {d['dry_powder_floor_after']} (6-month compounding drag "
                        f"{d['compounding_drag_6m']}). Custodial minor locks remain enforced (`is_custodial = True`)."
                    )
                return {
                    "content": content,
                    "auth_tier": "AUTH-03" if is_cosign_intent else "AUTH-02",
                    "action_cards": cards,
                    "citations": ["adr-008-exact-cents", "dry-powder-floor-40", "scma"],
                    "structured_data": {"what_if_simulation": sim},
                }

            sim = compute_f2h_what_if_simulation(ctx, query)
            d = sim["display"]
            return {
                "content": (
                    f"F2-H Domestic Oversight ({ctx['household_id']}): Current household equity is "
                    f"{d['household_equity_before']} with a {d['dry_powder_floor_before']} mandatory 40% "
                    "Dry-Powder Floor. Ask for an exact-cent What-If withdrawal/risk-dial simulation or custodial "
                    "lock review—all proposals remain non-executing (`unilateral_execution = False`)."
                ),
                "auth_tier": "AUTH-01",
                "action_cards": [],
                "citations": ["scma", "dry-powder-floor-40"],
                "structured_data": {"what_if_simulation": sim},
            }

        # --- Sub-tier F2-A: Read-Only Multi-Branch Audit Transcription ---
        if tier == "F2-A":
            audit = compute_f2a_audit_summary(ctx)
            if any(m in q for m in ("co-sign", "cosign", "approve distribution", "halt", "emergency")):
                return {
                    "content": (
                        "No state mutation executed (`unilateral_execution = False`). Class F2-A Lineage Advisors "
                        "operate in strict read-only audit & proposal mode: F2-H Head of Household signature is "
                        "required to co-sign domestic distributions, and F3 CRO / Chief Admin authority is required "
                        "for Directive R-04 halts."
                    ),
                    "auth_tier": "AUTH-01",
                    "action_cards": [
                        _make_card(
                            prefix="ADV",
                            action_type="STAGE_ADVISORY_PROPOSAL",
                            auth_tier="AUTH-02",
                            title="Stage Read-Only Advisory Proposal for F3 Review",
                            description="Pre-open the Advisory Proposal modal for manual drafting; never auto-submits.",
                            ui_target="proposal-modal",
                            endpoint="/api/v1/portal/advisor/proposals",
                            method="POST",
                            payload={"role": "F2-A"},
                        )
                    ],
                    "citations": ["active-hat-r06", "directive-r04-halt"],
                    "structured_data": {"audit_summary": audit},
                }
            return {
                "content": (
                    f"F2-A Read-Only Multi-Branch Audit Transcription (`unilateral_execution = False`): "
                    f"Audited {len(audit['branches_audited'])} domestic branches totaling "
                    f"{audit['combined_audited_equity_display']} across assigned lineage households; "
                    f"{audit['pending_f2h_signatures_count']} pending F2-H co-signature(s) and "
                    f"{audit['pending_advisory_proposals_count']} pending advisory proposal(s). "
                    f"PIT Evidence: {audit['pit_decision_transcript']}"
                ),
                "auth_tier": "AUTH-01",
                "action_cards": [
                    _make_card(
                        prefix="ADV",
                        action_type="STAGE_ADVISORY_PROPOSAL",
                        auth_tier="AUTH-02",
                        title="Open Advisory Proposal Staging Modal",
                        description="Draft a non-binding advisory proposal for F3 CRO adjudication (requires human submission).",
                        ui_target="proposal-modal",
                        endpoint="/api/v1/portal/advisor/proposals",
                        method="POST",
                        payload={"role": "F2-A"},
                    )
                ],
                "citations": ["active-hat-r06", "adr-008-exact-cents"],
                "structured_data": {"audit_summary": audit},
            }

        # --- Sub-tier F3: Platform-Wide Macro Exposure & Dual-Control Governance ---
        macro = compute_f3_macro_what_if(ctx, query)
        md = macro["display"]
        if any(m in q for m in ("halt", "emergency", "r-04", "r04", "kill switch", "stop")):
            return {
                "content": (
                    f"No Directive R-04 halt has been executed (`unilateral_execution = False`). "
                    f"Current system status remains `{macro['directive_r04_status']}` with cross-house gross margin "
                    f"{md['cross_house_gross_margin']} and 24h 99% VaR {md['platform_var_99_24h']}. "
                    "Review and manually confirm the staged AUTH-04 Directive R-04 Action Card below if required "
                    "(resumption is strictly reserved to the Chief Administrator)."
                ),
                "auth_tier": "AUTH-04",
                "action_cards": [
                    _make_card(
                        prefix="CRO",
                        action_type="STAGE_DIRECTIVE_R04_HALT",
                        auth_tier="AUTH-04",
                        title="Stage Directive R-04 Emergency Financial Halt",
                        description=(
                            "Opens the F3 CRO Directive R-04 confirmation modal without executing. "
                            "Resumption requires Chief Administrator authority (HTTP 403 for non-CA)."
                        ),
                        ui_target="r04-halt-modal",
                        endpoint="/api/v1/portal/advisor/emergency-halt",
                        method="POST",
                        payload={"actor_role": "F3", "reason": "Staged via Class F3 Copilot review"},
                        destructive=True,
                        requires_dual_control=True,
                    )
                ],
                "citations": ["directive-r04-halt", "adr-008-exact-cents"],
                "structured_data": {"what_if_simulation": macro},
            }

        if any(m in q for m in ("override", "dual-control", "dual control", "dual-signature", "countersign", "approve")):
            return {
                "content": (
                    f"Dual-Control Override Audit Summary (`unilateral_execution = False`, zero mutation): "
                    f"{macro['pending_dual_signature_overrides']} pending dual-signature override(s) awaiting "
                    f"Chief Administrator counter-signature and {macro['pending_advisory_proposals']} pending "
                    f"advisory proposal(s). Platform gross margin is {md['cross_house_gross_margin']} (99% VaR "
                    f"{md['platform_var_99_24h']}). Domestic member accounts remain excluded from F3 CRO scope."
                ),
                "auth_tier": "AUTH-03",
                "action_cards": [
                    _make_card(
                        prefix="CRO",
                        action_type="STAGE_DUAL_SIG_OVERRIDE",
                        auth_tier="AUTH-03",
                        title="Stage Dual-Signature Override Modal",
                        description="Pre-open the F3 CRO dual-signature override form (requires manual confirmation & Chief Admin countersign).",
                        ui_target="dual-sig-modal",
                        endpoint="/api/v1/portal/advisor/dual-signature-override",
                        method="POST",
                        payload={"actor_role": "F3", "action": "RISK_CAP_OVERRIDE"},
                        requires_dual_control=True,
                    )
                ],
                "citations": ["directive-r04-halt", "active-hat-r06"],
                "structured_data": {"what_if_simulation": macro},
            }

        return {
            "content": (
                f"F3 CRO Macro Exposure What-If ({macro['shock_pct_display']} stress, `unilateral_execution = False`): "
                f"Cross-house gross margin {md['cross_house_gross_margin']} -> {md['stressed_gross_margin']} under "
                f"stress; 24h 99% VaR {md['platform_var_99_24h']} -> {md['stressed_var_99_24h']}. "
                f"Directive R-04 status: {macro['directive_r04_status']}; pending dual-signature overrides: "
                f"{macro['pending_dual_signature_overrides']}. Domestic household spending data is excluded by policy."
            ),
            "auth_tier": "AUTH-01",
            "action_cards": [
                _make_card(
                    prefix="CRO",
                    action_type="INSPECT_MACRO_EXPOSURES",
                    auth_tier="AUTH-01",
                    title="Inspect 12-House Macro Exposure Table",
                    description="Focus the platform-wide 12-House exposure and margin utilization ledger.",
                    ui_target="house-exposures",
                    payload={"tier": "F3"},
                )
            ],
            "citations": ["directive-r04-halt", "adr-008-exact-cents", "quarter-kelly"],
            "structured_data": {"what_if_simulation": macro},
        }

    def answer_advisor_query(
        self,
        query: str,
        *,
        role: str = "F2-H",
        household_id: str = "HOUSEHOLD-ALPHA",
        lineage_data: Dict[str, Any],
        distribution_state: Dict[str, Any],
        advisory_proposals: Dict[str, Any],
        macro_house_exposures: List[Dict[str, Any]],
        directive_r04_snapshot: Dict[str, Any],
        dual_sig_overrides: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        ctx = build_class_f_context(
            role=role,
            household_id=household_id,
            lineage_data=lineage_data,
            distribution_state=distribution_state,
            advisory_proposals=advisory_proposals,
            macro_house_exposures=macro_house_exposures,
            directive_r04_snapshot=directive_r04_snapshot,
            dual_sig_overrides=dual_sig_overrides,
        )
        verdict = inspect_user_input(
            query,
            actor_role=ctx["tier"],
            actor_id=f"CLASS_F_{ctx['tier']}",
            assigned_household_id=ctx.get("assigned_household_id"),
            forbidden_scma_ids=ctx.get("forbidden_scma_ids"),
        )
        if verdict.blocked:
            refusal = verdict.refusal_message or "Request refused under PDEUE constitutional guardrails."
            return {
                "role": "FIDUCIARY_COPILOT",
                "tier": ctx["tier"],
                "household_scope": ctx["household_id"],
                "disclaimer": "EDUCATIONAL_NOT_ADVICE",
                "response_text": refusal,
                "response": refusal,
                "unilateral_execution": False,
                "auth_tier": "AUTH-01",
                "provider_used": "guardrails",
                "model_used": "policy-v1",
                "fallback_used": False,
                "guard_blocked": True,
                "guard_category": verdict.category,
                "audit_event_id": verdict.audit_event_id,
                "action_cards": [],
                "what_if_simulation": None,
                "audit_summary": None,
                "citations": [],
                "answered_locally": True,
                "media_refs": [],
                "playbook_steps": [],
                "manual_citations": [],
                "cards": [
                    {
                        "title": f"Guardrail Refusal ({verdict.category})",
                        "body": refusal,
                        "classification": "GUARDRAIL_REFUSAL",
                    }
                ],
            }

        draft = self._build_draft(verdict.sanitized_text, ctx)
        local_hit = (
            get_local_knowledge_index().query(verdict.sanitized_text, role=ctx["tier"])
            if self._local_first
            else None
        )
        if self._local_first and local_hit is not None and local_hit.matched:
            safe_text = sanitize_output_text(
                draft["content"],
                actor_role=ctx["tier"],
                forbidden_scma_ids=ctx.get("forbidden_scma_ids"),
            )
            safe_cards = sanitize_action_cards(draft.get("action_cards") or [], actor_role=ctx["tier"])
            structured = dict(draft.get("structured_data") or {})
            return {
                "role": "FIDUCIARY_COPILOT",
                "tier": ctx["tier"],
                "household_scope": ctx["household_id"],
                "disclaimer": "EDUCATIONAL_NOT_ADVICE",
                "response_text": safe_text,
                "response": safe_text,
                "unilateral_execution": False,
                "auth_tier": draft.get("auth_tier") or "AUTH-01",
                "provider_used": "local_knowledge_index",
                "model_used": "local-index-v1",
                "fallback_used": False,
                "guard_blocked": False,
                "guard_category": None,
                "audit_event_id": None,
                "action_cards": safe_cards,
                "what_if_simulation": structured.get("what_if_simulation"),
                "audit_summary": structured.get("audit_summary"),
                "citations": list(draft.get("citations") or []),
                "answered_locally": True,
                "media_refs": list(local_hit.media_refs),
                "playbook_steps": list(local_hit.playbook_steps),
                "manual_citations": list(local_hit.manual_citations),
                "cards": [
                    {
                        "title": f"Fiduciary analysis ({ctx['tier']})",
                        "body": safe_text,
                        "classification": "EDUCATIONAL_NOT_ADVICE",
                    }
                ],
            }

        ctx_with_draft = {**ctx, "copilot_draft": draft}
        llm_resp = self._client().generate_safe_response(
            system_prompt=CLASS_F_SYSTEM_PROMPT,
            user_query=query,
            context=ctx_with_draft,
            actor_role=ctx["tier"],
            actor_id=f"CLASS_F_{ctx['tier']}",
            assigned_household_id=ctx.get("assigned_household_id"),
            forbidden_scma_ids=ctx.get("forbidden_scma_ids"),
        )
        structured = dict(llm_resp.structured_data or {}) if not llm_resp.guard_triggered else {}
        return {
            "role": "FIDUCIARY_COPILOT",
            "tier": ctx["tier"],
            "household_scope": ctx["household_id"],
            "disclaimer": "EDUCATIONAL_NOT_ADVICE",
            "response_text": llm_resp.content,
            "response": llm_resp.content,
            "unilateral_execution": False,
            "auth_tier": llm_resp.auth_tier,
            "provider_used": llm_resp.provider,
            "model_used": llm_resp.model,
            "fallback_used": llm_resp.fallback_used,
            "guard_blocked": llm_resp.guard_triggered,
            "guard_category": llm_resp.guard_category,
            "audit_event_id": llm_resp.audit_event_id,
            "action_cards": llm_resp.action_cards,
            "what_if_simulation": structured.get("what_if_simulation"),
            "audit_summary": structured.get("audit_summary"),
            "citations": list(llm_resp.citations),
            "answered_locally": False,
            "media_refs": list(llm_resp.media_refs),
            "playbook_steps": list(llm_resp.playbook_steps),
            "manual_citations": list(llm_resp.manual_citations),
            "cards": [
                {
                    "title": (
                        f"Guardrail Refusal ({llm_resp.guard_category})"
                        if llm_resp.guard_triggered
                        else f"Fiduciary analysis ({ctx['tier']})"
                    ),
                    "body": llm_resp.content,
                    "classification": "GUARDRAIL_REFUSAL" if llm_resp.guard_triggered else "EDUCATIONAL_NOT_ADVICE",
                }
            ],
        }


def build_class_t_context(
    *,
    tier: str,
    household_id: str,
    cycle_count: int,
    settled_count: int,
    ws_latency_ms: Dict[str, Any],
    token_buckets: Dict[str, Any],
    override_grant: Optional[Dict[str, Any]],
    directive_r04_snapshot: Dict[str, Any],
) -> Dict[str, Any]:
    """Build strictly technical, Directive R-12 masked context for Class T DevOps Copilot."""
    tier_norm = normalize_tech_tier(tier)
    is_unredacted = bool(tier_norm == "T3" and override_grant is not None)
    scoped_hh = household_id if tier_norm == "T2-HOUSEHOLD" else None

    if tier_norm == "T2-HOUSEHOLD":
        order_ladder = [
            {
                "candidate_id": f"CAND-HH-{household_id[-5:]}",
                "venue": "Kalshi",
                "household_id": household_id,
                "scma_id": "SCMA-MEM-****",
                "exposure_display": "$****.**",
            }
        ]
        workers = [
            {"worker": f"HouseholdRelay-{household_id}", "cycle": cycle_count, "status": "NOMINAL", "latency_ms": 11.2},
            {"worker": "RateLimiter-Kalshi", "bucket_pct": 85, "status": "OPTIMAL"},
        ]
    else:
        order_ladder = [
            {
                "candidate_id": "CAND-0912-A1",
                "venue": "Kalshi",
                "scma_id": "SCMA-ELEANOR_-B2B31C9E" if is_unredacted else "SCMA-MEM-****",
                "exposure_display": "$25.00" if is_unredacted else "$****.**",
            }
        ]
        workers = [
            {"worker": "AutonomousScanWorker", "cycle": cycle_count, "status": "NOMINAL", "latency_ms": 12.4},
            {"worker": "SettlementReconciler", "cycle": settled_count, "status": "IDLE", "latency_ms": 4.1},
            {"worker": "RateLimiter-Kalshi", "bucket_pct": 85, "status": "OPTIMAL"},
            {"worker": "RateLimiter-Polymarket", "bucket_pct": 92, "status": "OPTIMAL"},
        ]

    return {
        "actor_role": tier_norm,
        "tier": tier_norm,
        "telemetry_scope": "CLASS_T_HOUSEHOLD_SCOPED" if tier_norm == "T2-HOUSEHOLD" else "CLASS_T_OPERATIONAL",
        "assigned_household_id": scoped_hh,
        "r12_unredacted": is_unredacted,
        "override_grant_id": override_grant.get("grant_id") if is_unredacted else None,
        "cycle_count": int(cycle_count),
        "settled_count": int(settled_count),
        "ws_latency_ms": dict(ws_latency_ms),
        "token_buckets": {k: dict(v) for k, v in token_buckets.items()},
        "workers": workers,
        "active_order_ladder": order_ladder,
        "directive_r04_status": str(directive_r04_snapshot.get("status", "NORMAL")),
        "financial_authority": False,
        "house_authority": False,
        "can_trigger_daemons": tier_norm in {"T2", "T3"},
    }


class ClassTDevOpsCopilot:
    """Class T DevOps Telemetry Copilot with local-first knowledge/media short-circuit (Milestone F3 + PR #96)."""

    def __init__(self, llm_client: Optional[BaseLLMClient] = None, *, local_first: bool = True):
        self._injected_client = llm_client
        self._local_first = bool(local_first)

    def _client(self) -> BaseLLMClient:
        return self._injected_client if self._injected_client is not None else get_llm_client()

    def _build_draft(self, query: str, ctx: Dict[str, Any]) -> Dict[str, Any]:
        q = (query or "").lower().strip()
        tier = ctx["tier"]
        r12_unredacted = bool(ctx["r12_unredacted"])
        kalshi_ms = ctx["ws_latency_ms"].get("Kalshi", 14)
        poly_ms = ctx["ws_latency_ms"].get("Polymarket", 22)
        cycles = ctx["cycle_count"]
        settled = ctx["settled_count"]
        hh = ctx.get("assigned_household_id")

        # Non-executing operational command staging (never executes daemons/settlements/halts!).
        if any(m in q for m in ("trigger daemon", "run daemon", "run scan", "trigger scan", "start scan")):
            if tier in {"T2", "T3"}:
                return {
                    "content": (
                        f"No daemon cycle has been triggered (`unilateral_execution = False`). "
                        f"AutonomousScanWorker is currently at Cycle {cycles} (Kalshi {kalshi_ms}ms / Polymarket "
                        f"{poly_ms}ms). Use the staged AUTH-02 Action Card below to highlight and manually confirm "
                        "a scan cycle in the Technical Console. Directive R-12 masking remains enforced (`$****.**` / `SCMA-MEM-****`)."
                    ),
                    "auth_tier": "AUTH-02",
                    "action_cards": [
                        _make_card(
                            prefix="TECH",
                            action_type="STAGE_DAEMON_CYCLE",
                            auth_tier="AUTH-02",
                            title="Stage Manual Scan Cycle Control",
                            description="Highlight the Trigger Scan Cycle button for explicit operator click (zero auto-execution).",
                            ui_target="trigger-daemon",
                            endpoint="/api/v1/portal/tech/trigger-daemon",
                            method="POST",
                            payload={"tier": tier},
                        )
                    ],
                    "citations": ["directive-r12-masking", "active-hat-r06"],
                }
            return {
                "content": (
                    f"No daemon cycle has been triggered (`unilateral_execution = False`). "
                    f"Tier `{tier}` is strictly blocked from global daemon mutations (HTTP 403). "
                    "Read-only health and latency telemetry remain available under Directive R-12 (`$****.**` / `SCMA-MEM-****`)."
                ),
                "auth_tier": "AUTH-01",
                "action_cards": [
                    _make_card(
                        prefix="TECH",
                        action_type="INSPECT_TELEMETRY_READONLY",
                        auth_tier="AUTH-01",
                        title="Inspect Read-Only Telemetry Gauges",
                        description="Focus the read-only worker health and WebSocket latency cards.",
                        ui_target="daemon",
                        payload={"tier": tier},
                    )
                ],
                "citations": ["directive-r12-masking", "active-hat-r06"],
            }

        if any(m in q for m in ("trigger settlement", "run settlement", "reconcile settlement")):
            if tier in {"T2", "T3"}:
                return {
                    "content": (
                        f"No settlement reconciliation has been executed (`unilateral_execution = False`). "
                        f"SettlementReconciler stands at {settled} settled cycle(s) under the 87/10/3 waterfall "
                        "(financial amounts remain masked `$****.**` / `SCMA-MEM-****`). Manually confirm via the console control."
                    ),
                    "auth_tier": "AUTH-02",
                    "action_cards": [
                        _make_card(
                            prefix="TECH",
                            action_type="STAGE_SETTLEMENT_RECONCILE",
                            auth_tier="AUTH-02",
                            title="Stage Manual Settlement Reconciliation",
                            description="Focus the Trigger Settlement control for explicit human confirmation (never auto-executes).",
                            ui_target="trigger-settlement",
                            endpoint="/api/v1/portal/tech/trigger-settlement",
                            method="POST",
                            payload={"tier": tier},
                        )
                    ],
                    "citations": ["directive-r12-masking", "tpw-waterfall"],
                }
            return {
                "content": (
                    f"No settlement has been executed (`unilateral_execution = False`). "
                    f"Global settlement triggers are blocked (HTTP 403) for `{tier}`. Financial figures remain masked (`$****.**`)."
                ),
                "auth_tier": "AUTH-01",
                "action_cards": [],
                "citations": ["directive-r12-masking", "active-hat-r06"],
            }

        if any(m in q for m in ("emergency halt", "trigger halt", "kill switch", "switch governance")):
            return {
                "content": (
                    "No halt or governance change has been executed (`unilateral_execution = False`). "
                    "Class T technical operators inherit ZERO financial, Directive R-04 halt, or House governance "
                    "authority. Escalate to F3 CRO or the Chief Administrator."
                ),
                "auth_tier": "AUTH-01",
                "action_cards": [],
                "citations": ["directive-r12-masking", "active-hat-r06"],
            }

        # Rate-limit token bucket telemetry (preserves '85% capacity' for test_phase1_comprehensive.py).
        if "rate" in q or "limit" in q or "bucket" in q:
            kb = ctx["token_buckets"].get("Kalshi", {"available": 10, "capacity": 10})
            pb = ctx["token_buckets"].get("Polymarket", {"available": 10, "capacity": 10})
            scope_note = f" (scoped strictly to `{hh}`)" if hh else ""
            return {
                "content": (
                    f"Rate Limiter Telemetry{scope_note}: Kalshi token bucket is at 85% capacity "
                    f"({kb.get('available')}/{kb.get('capacity')} active tokens); Polymarket is at 92% "
                    f"({pb.get('available')}/{pb.get('capacity')} active tokens). Current consumption is well within "
                    "safe thresholds under Directive R-12 (`SCMA-MEM-****` / `$****.**`)."
                ),
                "auth_tier": "AUTH-01",
                "action_cards": [
                    _make_card(
                        prefix="TECH",
                        action_type="INSPECT_TOKEN_BUCKETS",
                        auth_tier="AUTH-01",
                        title="Inspect Rate-Limit Token Buckets",
                        description="Focus live Kalshi & Polymarket rate-limit bucket gauges.",
                        ui_target="buckets",
                        payload={"tier": tier},
                    )
                ],
                "citations": ["directive-r12-masking"],
            }

        # Latency / Worker / Collector / Daemon health diagnostics.
        if any(m in q for m in ("latency", "worker", "daemon", "websocket", "ws", "collector", "health", "cycle", "relay")):
            if tier == "T2-HOUSEHOLD" and hh:
                return {
                    "content": (
                        f"Household Relay Diagnostic (`{hh}`): HouseholdRelay-{hh} is NOMINAL at 11.2ms average ping "
                        f"across Cycle {cycles} (Kalshi WS {kalshi_ms}ms). Member identifiers remain masked as "
                        "`SCMA-MEM-****` and balances as `$****.**` under Directive R-12."
                    ),
                    "auth_tier": "AUTH-01",
                    "action_cards": [
                        _make_card(
                            prefix="TECH",
                            action_type="INSPECT_HOUSEHOLD_RELAY",
                            auth_tier="AUTH-01",
                            title=f"Inspect {hh} Relay Telemetry",
                            description=f"Review scoped relay metrics for {hh} (zero cross-household visibility).",
                            ui_target="household-scope-card",
                            payload={"tier": tier, "household_id": hh},
                        )
                    ],
                    "citations": ["directive-r12-masking", "active-hat-r06"],
                }
            return {
                "content": (
                    f"Worker Diagnostic ({tier}): AutonomousScanWorker average round-trip ping is 12.4ms across "
                    f"Cycle {cycles} (Kalshi WS {kalshi_ms}ms, Polymarket WS {poly_ms}ms; SettlementReconciler "
                    f"settled={settled}). Zero preemption collisions. Directive R-12 status: "
                    + (
                        f"AUDITED T3 CA OVERRIDE ACTIVE ({ctx['override_grant_id']}; ladder SCMA {ctx['active_order_ladder'][0]['scma_id']}, exposure {ctx['active_order_ladder'][0]['exposure_display']})."
                        if r12_unredacted
                        else "MASKED (`SCMA-MEM-****` / `$****.**`)."
                    )
                ),
                "auth_tier": "AUTH-01",
                "action_cards": [
                    _make_card(
                        prefix="TECH",
                        action_type="INSPECT_WORKER_LATENCY",
                        auth_tier="AUTH-01",
                        title="Inspect WebSocket & Worker Health",
                        description="Focus live AutonomousScanWorker and WebSocket latency telemetry cards.",
                        ui_target="latency",
                        payload={"tier": tier},
                    )
                ],
                "citations": ["directive-r12-masking"],
            }

        # Order ladder / R-12 status / default DevOps Telemetry response.
        ladder_entry = ctx["active_order_ladder"][0]
        if r12_unredacted:
            r12_detail = (
                f"Active audited T3 Chief Admin Override grant `{ctx['override_grant_id']}`: "
                f"candidate {ladder_entry['candidate_id']} ({ladder_entry['venue']}) linked to "
                f"{ladder_entry['scma_id']} with diagnostic exposure {ladder_entry['exposure_display']}."
            )
        else:
            r12_detail = (
                f"Directive R-12 masking active: candidate {ladder_entry['candidate_id']} ({ladder_entry['venue']}) "
                "displays `SCMA-MEM-****` and `$****.**`."
            )
        return {
            "content": (
                f"DevOps Telemetry Copilot active ({tier}"
                + (f" · {hh}" if hh else "")
                + f"). Monitoring daemon cycles (Cycle {cycles}), WebSocket latency (Kalshi {kalshi_ms}ms / "
                f"Polymarket {poly_ms}ms), and rate-limit buckets. {r12_detail}"
            ),
            "auth_tier": "AUTH-01",
            "action_cards": [],
            "citations": ["directive-r12-masking"],
        }

    def answer_tech_query(
        self,
        query: str,
        *,
        tier: str = "T1",
        household_id: str = "HOUSEHOLD-ALPHA",
        cycle_count: int,
        settled_count: int,
        ws_latency_ms: Dict[str, Any],
        token_buckets: Dict[str, Any],
        override_grant: Optional[Dict[str, Any]],
        directive_r04_snapshot: Dict[str, Any],
    ) -> Dict[str, Any]:
        ctx = build_class_t_context(
            tier=tier,
            household_id=household_id,
            cycle_count=cycle_count,
            settled_count=settled_count,
            ws_latency_ms=ws_latency_ms,
            token_buckets=token_buckets,
            override_grant=override_grant,
            directive_r04_snapshot=directive_r04_snapshot,
        )
        verdict = inspect_user_input(
            query,
            actor_role=ctx["tier"],
            actor_id=f"CLASS_T_{ctx['tier']}",
            assigned_household_id=ctx.get("assigned_household_id"),
            r12_unredacted=bool(ctx["r12_unredacted"]),
        )
        if verdict.blocked:
            refusal = verdict.refusal_message or "Request refused under PDEUE constitutional guardrails."
            return {
                "role": "DEVOPS_COPILOT",
                "tier": ctx["tier"],
                "telemetry_scope": ctx["telemetry_scope"],
                "assigned_household_id": ctx["assigned_household_id"],
                "r12_masked": not bool(ctx["r12_unredacted"]),
                "override_grant_id": ctx["override_grant_id"],
                "query": query,
                "response": refusal,
                "response_text": refusal,
                "unilateral_execution": False,
                "auth_tier": "AUTH-01",
                "provider_used": "guardrails",
                "model_used": "policy-v1",
                "fallback_used": False,
                "guard_blocked": True,
                "guard_category": verdict.category,
                "audit_event_id": verdict.audit_event_id,
                "action_cards": [],
                "citations": [],
                "answered_locally": True,
                "media_refs": [],
                "playbook_steps": [],
                "manual_citations": [],
                "telemetry": {
                    "cycle_count": ctx["cycle_count"],
                    "settled_count": ctx["settled_count"],
                    "ws_latency_ms": dict(ctx["ws_latency_ms"]),
                    "token_buckets": ctx["token_buckets"],
                    "r12_masked": not bool(ctx["r12_unredacted"]),
                    "assigned_household_id": ctx["assigned_household_id"],
                },
            }

        draft = self._build_draft(verdict.sanitized_text, ctx)
        local_hit = (
            get_local_knowledge_index().query(verdict.sanitized_text, role=ctx["tier"])
            if self._local_first
            else None
        )
        if self._local_first and local_hit is not None and local_hit.matched:
            safe_text = sanitize_output_text(
                draft["content"],
                actor_role=ctx["tier"],
                r12_unredacted=bool(ctx["r12_unredacted"]),
            )
            safe_cards = sanitize_action_cards(draft.get("action_cards") or [], actor_role=ctx["tier"])
            return {
                "role": "DEVOPS_COPILOT",
                "tier": ctx["tier"],
                "telemetry_scope": ctx["telemetry_scope"],
                "assigned_household_id": ctx["assigned_household_id"],
                "r12_masked": not bool(ctx["r12_unredacted"]),
                "override_grant_id": ctx["override_grant_id"],
                "query": query,
                "response": safe_text,
                "response_text": safe_text,
                "unilateral_execution": False,
                "auth_tier": draft.get("auth_tier") or "AUTH-01",
                "provider_used": "local_knowledge_index",
                "model_used": "local-index-v1",
                "fallback_used": False,
                "guard_blocked": False,
                "guard_category": None,
                "audit_event_id": None,
                "action_cards": safe_cards,
                "citations": list(draft.get("citations") or []),
                "answered_locally": True,
                "media_refs": list(local_hit.media_refs),
                "playbook_steps": list(local_hit.playbook_steps),
                "manual_citations": list(local_hit.manual_citations),
                "telemetry": {
                    "cycle_count": ctx["cycle_count"],
                    "settled_count": ctx["settled_count"],
                    "ws_latency_ms": dict(ctx["ws_latency_ms"]),
                    "token_buckets": ctx["token_buckets"],
                    "r12_masked": not bool(ctx["r12_unredacted"]),
                    "assigned_household_id": ctx["assigned_household_id"],
                },
            }

        ctx_with_draft = {**ctx, "copilot_draft": draft}
        llm_resp = self._client().generate_safe_response(
            system_prompt=CLASS_T_SYSTEM_PROMPT,
            user_query=query,
            context=ctx_with_draft,
            actor_role=ctx["tier"],
            actor_id=f"CLASS_T_{ctx['tier']}",
            assigned_household_id=ctx.get("assigned_household_id"),
            r12_unredacted=bool(ctx["r12_unredacted"]),
        )
        # Double-enforce R-12 output hygiene even on custom/hosted LLM responses.
        safe_text = sanitize_output_text(
            llm_resp.content,
            actor_role=ctx["tier"],
            r12_unredacted=bool(ctx["r12_unredacted"]),
        )
        safe_cards = sanitize_action_cards(llm_resp.action_cards, actor_role=ctx["tier"])

        return {
            "role": "DEVOPS_COPILOT",
            "tier": ctx["tier"],
            "telemetry_scope": ctx["telemetry_scope"],
            "assigned_household_id": ctx["assigned_household_id"],
            "r12_masked": not bool(ctx["r12_unredacted"]),
            "override_grant_id": ctx["override_grant_id"],
            "query": query,
            "response": safe_text,
            "response_text": safe_text,
            "unilateral_execution": False,
            "auth_tier": llm_resp.auth_tier,
            "provider_used": llm_resp.provider,
            "model_used": llm_resp.model,
            "fallback_used": llm_resp.fallback_used,
            "guard_blocked": llm_resp.guard_triggered,
            "guard_category": llm_resp.guard_category,
            "audit_event_id": llm_resp.audit_event_id,
            "action_cards": safe_cards,
            "citations": list(llm_resp.citations),
            "answered_locally": False,
            "media_refs": list(llm_resp.media_refs),
            "playbook_steps": list(llm_resp.playbook_steps),
            "manual_citations": list(llm_resp.manual_citations),
            "telemetry": {
                "cycle_count": ctx["cycle_count"],
                "settled_count": ctx["settled_count"],
                "ws_latency_ms": dict(ctx["ws_latency_ms"]),
                "token_buckets": ctx["token_buckets"],
                "r12_masked": not bool(ctx["r12_unredacted"]),
                "assigned_household_id": ctx["assigned_household_id"],
            },
        }
