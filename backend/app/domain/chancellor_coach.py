"""Milestone F4 — Chief Administrator AI Chancellor Coach (`/dashboard`).

Wires the Chief Administrator AI Chancellor Coach onto the Milestone F1
``BaseLLMClient`` + ``guardrails.py`` spine, delivering:
- A structured **Constrained Policy Decision Matrix** comparing deterministic
  executive options with explicit invariant impact checks against:
  1. 87/10/3 Transaction Profit Waterfall (ADR-008 exact-cent conservation),
  2. ADR-012 Per-SCMA High-Water Mark (0% skim during drawdown recovery),
  3. Rule A14 100% SCMA Loss Isolation,
  4. ADR-011 Zero Banking Credentials & HMAC-SHA256 Signed IFAS Outbox,
  5. Executive Command / SHTF Posture, Founder Quarantine Immunity & Gate G1.
- Deterministic ``AUTH-01``–``AUTH-04`` Action Cards that pre-stage—but NEVER
  execute—administrative controls (`unilateral_execution = False`,
  `executed = False`, `requires_human_confirmation = True`).
- Prompt-injection, secret-exfiltration, and unilateral-execution bypass refusals
  logged to ``GovernanceAuditLog`` as ``AI_GUARDRAIL_REFUSAL``.
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
from app.domain.authority_tiers import get_directive_r04_controller
from app.domain.enclave_governance import (
    IMMUTABLE_CORE_INVARIANTS,
    MODE_EXECUTIVE_COMMAND,
    get_enclave_governance_service,
)
from app.domain.local_knowledge_index import get_local_knowledge_index

CHANCELLOR_SYSTEM_PROMPT = (
    "You are the PDEUE Chief Administrator AI Chancellor Coach on `/dashboard`. "
    "Deliver structured Constrained Policy Decision Matrices evaluating executive options against "
    "PDEUE's non-negotiable architectural invariants: 87/10/3 Transaction Profit Waterfall (ADR-008 "
    "exact integer cents), ADR-012 High-Water Mark, Rule A14 100% SCMA loss isolation, ADR-011 "
    "banking air-gap & signed IFAS outbox, Gate G1 fail-closed defaults, and Executive Command / "
    "SHTF posture with Absolute Founder Veto & quarantine immunity. "
    "CONSTITUTIONAL RULES: unilateral_execution = False ALWAYS. Pre-stage deterministic "
    "AUTH-01–AUTH-04 Action Cards only; NEVER execute administrative state mutations."
)

_IMMUTABLE_AMENDMENT_VERBS_RE = re.compile(
    r"\b(?:change|alter|modify|bypass|disable|remove|abolish|reduce|lower|increase|rewrite|socialize|share|store|save|override|replace|repeal|suspend)\b",
    re.IGNORECASE,
)


def _make_chancellor_card(
    *,
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
) -> Dict[str, Any]:
    card: Dict[str, Any] = {
        "action_id": f"ACT-CHANC-{uuid.uuid4().hex[:8].upper()}",
        "action_type": action_type,
        "auth_tier": auth_tier,
        "title": title,
        "description": description,
        "ui_target": ui_target,
        "payload": dict(payload or {}),
        "destructive": bool(destructive),
        "requires_dual_control": bool(requires_dual_control),
        "requires_human_confirmation": True,
        "requires_settlor_approval": True,
        "is_disabled": False,
        "unilateral_execution": False,
        "executed": False,
        "confirmation_notice": (
            f"Pre-staged under {auth_tier} (unilateral_execution = False): "
            "requires explicit Chief Administrator confirmation in the cockpit."
        ),
    }
    if endpoint:
        card["endpoint"] = endpoint
    if method:
        card["method"] = method
    return card


def _detect_immutable_invariant_conflict(query: str) -> List[str]:
    """Return IDs of any immutable core invariants the query asks to weaken/alter."""
    text = query or ""
    if not _IMMUTABLE_AMENDMENT_VERBS_RE.search(text):
        return []
    hits: List[str] = []
    for inv_id, _label, pattern in IMMUTABLE_CORE_INVARIANTS:
        if pattern.search(text):
            hits.append(inv_id)
    # Also catch numeric waterfall split proposals like "50/40/10" or "70/20/10".
    if re.search(r"\b\d{1,2}\s*/\s*\d{1,2}\s*/\s*\d{1,2}\b", text) and not re.search(r"\b87\s*/\s*10\s*/\s*3\b", text):
        if "87_10_3_WATERFALL" not in hits:
            hits.append("87_10_3_WATERFALL")
    return hits


def _build_invariant_checks(
    *,
    conflicts: List[str],
    gov_mode: str,
    r04_status: str,
) -> List[Dict[str, Any]]:
    conflict_set = set(conflicts)
    return [
        {
            "invariant_id": "TPW_87_10_3",
            "label": "87/10/3 Waterfall (ADR-008 Exact Cents)",
            "status": "BLOCKED_IMMUTABLE_CORE" if ("87_10_3_WATERFALL" in conflict_set or "FAEP_3_PERCENT" in conflict_set) else "PASS",
            "detail": (
                "Immutable Core Guardrail: 87% SCMA / 10% CFCP (+ remainder cents) / 3% FAEP cannot be altered."
                if ("87_10_3_WATERFALL" in conflict_set or "FAEP_3_PERCENT" in conflict_set)
                else "Exact-cent 87/10/3 split preserved; remainder cents routed to CFCP."
            ),
        },
        {
            "invariant_id": "ADR_012_HWM",
            "label": "ADR-012 Per-SCMA High-Water Mark",
            "status": "BLOCKED_IMMUTABLE_CORE" if "ADR_012_HWM" in conflict_set else "PASS",
            "detail": (
                "Immutable Core Guardrail: ADR-012 High-Water Mark zero-skim drawdown recovery is permanently locked."
                if "ADR_012_HWM" in conflict_set
                else "0% CFCP/FAEP skim during drawdown recovery; profit waterfall applies strictly above prior HWM."
            ),
        },
        {
            "invariant_id": "RULE_A14_LOSS_ISOLATION",
            "label": "Rule A14 100% SCMA Loss Isolation",
            "status": "BLOCKED_IMMUTABLE_CORE" if "RULE_A14_LOSS_ISOLATION" in conflict_set else "PASS",
            "detail": (
                "Immutable Core Guardrail: individual SCMA trading losses may never be socialized across CFCP/FAEP."
                if "RULE_A14_LOSS_ISOLATION" in conflict_set
                else "100% of trading losses remain contained inside the executing SCMA; CFCP & FAEP shielded."
            ),
        },
        {
            "invariant_id": "ADR_011_BANKING_AIRGAP",
            "label": "ADR-011 Banking Air-Gap & Signed Outbox",
            "status": "BLOCKED_IMMUTABLE_CORE" if "ADR_011_BANKING_AIRGAP" in conflict_set else "PASS",
            "detail": (
                "Immutable Core Guardrail: raw bank credentials remain permanently prohibited; HMAC-SHA256 IFAS outbox only."
                if "ADR_011_BANKING_AIRGAP" in conflict_set
                else "Zero banking credentials stored; opaque EXT-REF tokens and HMAC-SHA256 IFAS outbox enforced."
            ),
        },
        {
            "invariant_id": "EXECUTIVE_SHTF_POSTURE",
            "label": "Executive Command / SHTF & Founder Immunity",
            "status": "BLOCKED_IMMUTABLE_CORE" if "EMERGENCY_KILL_SWITCH" in conflict_set else "PASS",
            "detail": (
                "Immutable Core Guardrail: Directive R-04 Kill Switch, Absolute Founder Veto, and SHTF snap-back are non-removable."
                if "EMERGENCY_KILL_SWITCH" in conflict_set
                else f"Active governance mode `{gov_mode}`, Directive R-04 `{r04_status}`, Gate G1 `HOLD_OBSERVATIONS_ONLY`, 1-click SHTF snap-back & Founder quarantine immunity intact."
            ),
        },
    ]


def build_chancellor_context(
    live_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Harvest read-only Chief Administrator governance, R-04, and risk posture."""
    gov_state: Dict[str, Any] = {}
    try:
        gov_state = get_enclave_governance_service().get_governance_mode()
    except Exception:
        gov_state = {"governance_mode": MODE_EXECUTIVE_COMMAND, "stage": 1, "voting_enabled": False}

    r04_snapshot: Dict[str, Any] = {}
    pending_overrides: List[Dict[str, Any]] = []
    try:
        r04_ctrl = get_directive_r04_controller()
        r04_snapshot = r04_ctrl.snapshot()
        pending_overrides = [o for o in r04_ctrl.list_overrides() if o.get("status") == "PENDING_CHIEF_ADMIN"]
    except Exception:
        r04_snapshot = {"status": "NORMAL", "failsafe": "ARMED"}

    live = dict(live_context or {})
    dry_powder_cents = int(live.get("dry_powder_cents", 400_000))
    current_risk_pct = float(live.get("current_risk_pct", 1.5))

    return {
        "actor_role": "CHIEF_ADMINISTRATOR",
        "governance_mode": str(gov_state.get("governance_mode") or MODE_EXECUTIVE_COMMAND),
        "governance_stage": int(gov_state.get("stage") or 1),
        "voting_enabled": bool(gov_state.get("voting_enabled", False)),
        "bicameral_veto_enabled": bool(gov_state.get("bicameral_veto_enabled", False)),
        "directive_r04_status": str(r04_snapshot.get("status") or "NORMAL"),
        "directive_r04_failsafe": str(r04_snapshot.get("failsafe") or "ARMED"),
        "pending_dual_sig_overrides": len(pending_overrides),
        "gate_g1_status": "HOLD_OBSERVATIONS_ONLY",
        "venue_mode": "paper",
        "founder_quarantine_immunity": True,
        "shtf_snapback_ready": True,
        "dry_powder_cents": dry_powder_cents,
        "current_risk_pct": current_risk_pct,
        "downward_only_locked": bool(live.get("downward_only_locked", True)),
    }


def build_constrained_policy_decision_matrix(
    query: str,
    ctx: Dict[str, Any],
) -> Dict[str, Any]:
    """Produce a deterministic Constrained Policy Decision Matrix + AUTH-01–AUTH-04 Action Cards."""
    q = (query or "").lower().strip()
    gov_mode = ctx["governance_mode"]
    r04_status = ctx["directive_r04_status"]
    conflicts = _detect_immutable_invariant_conflict(query)
    invariant_checks = _build_invariant_checks(
        conflicts=conflicts,
        gov_mode=gov_mode,
        r04_status=r04_status,
    )

    posture = {
        "governance_mode": gov_mode,
        "governance_stage": ctx["governance_stage"],
        "directive_r04_status": r04_status,
        "gate_g1_status": ctx["gate_g1_status"],
        "venue_mode": ctx["venue_mode"],
        "shtf_snapback_ready": True,
        "founder_veto_absolute": True,
        "founder_quarantine_immunity": True,
    }

    # 1. Immutable Core Invariant Amendment Attempt -> Hard Policy Block, zero mutating Action Cards.
    if conflicts:
        matrix = {
            "matrix_id": f"MAT-{uuid.uuid4().hex[:8].upper()}",
            "topic": "IMMUTABLE_CORE_INVARIANT_BLOCK",
            "governance_posture": posture,
            "immutable_conflicts": conflicts,
            "options": [
                {
                    "option_id": "OPT-A",
                    "label": "Preserve Immutable Core Invariants (Required)",
                    "summary": "Maintain 87/10/3 TPW, ADR-012 HWM, Rule A14 100% SCMA loss isolation, ADR-011 air-gap, and Directive R-04 failsafe intact.",
                    "auth_tier": "AUTH-01",
                    "reversible": True,
                    "recommended": True,
                    "risk_level": "LOW",
                    "invariant_status": "PASS",
                },
                {
                    "option_id": "OPT-B",
                    "label": "Proposed Core Invariant Mutation (Permanently Blocked)",
                    "summary": f"Rejected fail-closed: violates immutable core pillar(s) {', '.join(conflicts)}.",
                    "auth_tier": "AUTH-04",
                    "reversible": False,
                    "recommended": False,
                    "risk_level": "PROHIBITED",
                    "invariant_status": "BLOCKED_IMMUTABLE_CORE",
                },
            ],
            "invariant_checks": invariant_checks,
            "unilateral_execution": False,
            "mutated": False,
        }
        return {
            "content": (
                f"Policy proposal blocked by Immutable Core Guardrail (`unilateral_execution = False`, zero mutation): "
                f"conflicts detected with {', '.join(conflicts)}. PDEUE's 87/10/3 waterfall, ADR-012 High-Water Mark, "
                "Rule A14 100% SCMA loss isolation, ADR-011 banking air-gap, and Directive R-04 / Founder immunity "
                "cannot be weakened in any governance stage."
            ),
            "auth_tier": "AUTH-01",
            "action_cards": [
                _make_chancellor_card(
                    action_type="INSPECT_GOVERNANCE_POSTURE",
                    auth_tier="AUTH-01",
                    title="Inspect Immutable Core Guardrail Ledger",
                    description="Review active governance posture and immutable invariant protections (read-only).",
                    ui_target="tab-btn-4",
                    endpoint="/api/v1/governance/state",
                    method="GET",
                    payload={"conflicts": conflicts},
                )
            ],
            "citations": ["tpw-waterfall", "high-water-mark-adr-012", "adr-011-air-gap", "directive-r04-halt"],
            "policy_decision_matrix": matrix,
        }

    # 2. Emergency Halt / SHTF / Kill Switch Intent -> AUTH-04 pre-staged Action Card (ZERO execution!)
    if any(m in q for m in ("emergency", "halt", "shtf", "kill switch", "snap back", "snap-back", "directive r-04", "r-04", "stop")):
        matrix = {
            "matrix_id": f"MAT-{uuid.uuid4().hex[:8].upper()}",
            "topic": "EMERGENCY_HALT_SHTF_POSTURE",
            "governance_posture": posture,
            "immutable_conflicts": [],
            "options": [
                {
                    "option_id": "OPT-A",
                    "label": "Hold & Audit Telemetry First",
                    "summary": "Keep Gate G1 in HOLD_OBSERVATIONS_ONLY (paper) and verify R-04 / daemon diagnostics before tripping halt.",
                    "auth_tier": "AUTH-01",
                    "reversible": True,
                    "recommended": r04_status == "NORMAL",
                    "risk_level": "LOW",
                    "invariant_status": "PASS",
                },
                {
                    "option_id": "OPT-B",
                    "label": "Stage Directive R-04 Emergency Halt",
                    "summary": "Freeze all new financial commitments across portals; resumption reserved strictly to Chief Administrator.",
                    "auth_tier": "AUTH-04",
                    "reversible": True,
                    "recommended": False,
                    "risk_level": "HIGH",
                    "invariant_status": "PASS",
                },
                {
                    "option_id": "OPT-C",
                    "label": "Stage 1-Click SHTF Snap-Back to Executive Command",
                    "summary": "Immediately revert governance to Stage 1 (EXECUTIVE_COMMAND), suspending House voting while preserving Founder sovereignty.",
                    "auth_tier": "AUTH-04",
                    "reversible": True,
                    "recommended": gov_mode != MODE_EXECUTIVE_COMMAND,
                    "risk_level": "HIGH",
                    "invariant_status": "PASS",
                },
            ],
            "invariant_checks": invariant_checks,
            "unilateral_execution": False,
            "mutated": False,
        }
        return {
            "content": (
                f"No emergency halt or SHTF snap-back has been executed (`unilateral_execution = False`). "
                f"Current posture: Governance `{gov_mode}`, Directive R-04 `{r04_status}`, Gate G1 `HOLD_OBSERVATIONS_ONLY` "
                "(paper mode). Review the Constrained Policy Decision Matrix and confirm a pre-staged AUTH-04 "
                "Action Card manually in the cockpit if emergency intervention is warranted."
            ),
            "auth_tier": "AUTH-04",
            "action_cards": [
                _make_chancellor_card(
                    action_type="EMERGENCY_STOP",
                    auth_tier="AUTH-04",
                    title="Pre-Stage Emergency Kill Switch (Directive R-04)",
                    description="Focus the Chief Administrator emergency circuit-breaker control. Zero automatic execution.",
                    ui_target="emergencyKillSwitchBtn",
                    endpoint="/api/v1/operator/emergency-stop",
                    method="POST",
                    payload={"actor_id": "Chief Administrator", "reason": "Chancellor Coach pre-staged review"},
                    destructive=True,
                ),
                _make_chancellor_card(
                    action_type="STAGE_SHTF_SNAPBACK",
                    auth_tier="AUTH-04",
                    title="Pre-Stage 1-Click SHTF Snap-Back (Stage 1)",
                    description="Navigate to Governance SHTF snap-back control for explicit Chief Administrator confirmation.",
                    ui_target="btn-shtf-snapback",
                    endpoint="/api/v1/governance/shtf-snapback",
                    method="POST",
                    payload={"target_mode": MODE_EXECUTIVE_COMMAND},
                    destructive=True,
                ),
            ],
            "citations": ["directive-r04-halt", "gate-g1-qualification", "active-hat-r06"],
            "policy_decision_matrix": matrix,
        }

    # 3. Governance Stage Transition / Bicameral Veto / House Petitions -> AUTH-03 pre-staged card (ZERO mutation!)
    if any(m in q for m in ("governance", "stage 2", "stage 3", "bicameral", "petition", "house vote", "switch mode", "governance mode", "veto")):
        matrix = {
            "matrix_id": f"MAT-{uuid.uuid4().hex[:8].upper()}",
            "topic": "GOVERNANCE_STAGE_TRANSITION",
            "governance_posture": posture,
            "immutable_conflicts": [],
            "options": [
                {
                    "option_id": "OPT-A",
                    "label": "Remain in Stage 1 — Executive Command",
                    "summary": "Keep House voting dormant and preserve direct Settlor command during fledgling paper/alpha qualification.",
                    "auth_tier": "AUTH-01",
                    "reversible": True,
                    "recommended": True,
                    "risk_level": "LOW",
                    "invariant_status": "PASS",
                },
                {
                    "option_id": "OPT-B",
                    "label": "Stage 2 — Advisory Petition Filter (9/12 Quorum)",
                    "summary": "Enable non-binding 9-of-12 House petitions while retaining Absolute Founder Veto and zero unilateral execution.",
                    "auth_tier": "AUTH-03",
                    "reversible": True,
                    "recommended": False,
                    "risk_level": "MODERATE",
                    "invariant_status": "PASS",
                },
                {
                    "option_id": "OPT-C",
                    "label": "Stage 3 — Bicameral Veto Active (With SHTF Snap-Back)",
                    "summary": "Enable binding chamber veto on eligible policy/CFCP petitions; Immutable Core Guardrail & 1-click SHTF snap-back remain permanent.",
                    "auth_tier": "AUTH-04",
                    "reversible": True,
                    "recommended": False,
                    "risk_level": "HIGH",
                    "invariant_status": "PASS",
                },
            ],
            "invariant_checks": invariant_checks,
            "unilateral_execution": False,
            "mutated": False,
        }
        return {
            "content": (
                f"No governance mode transition has been executed (`unilateral_execution = False`). "
                f"Active mode remains `{gov_mode}` (Stage {ctx['governance_stage']}). Under Sovereign Settlor "
                "Doctrine, 9/12 House petitions remain advisory in Stage 2 with Absolute Founder Veto, and 1-click "
                "SHTF snap-back plus Immutable Core Guardrails remain permanently intact across all stages."
            ),
            "auth_tier": "AUTH-03",
            "action_cards": [
                _make_chancellor_card(
                    action_type="STAGE_GOVERNANCE_MODE_TRANSITION",
                    auth_tier="AUTH-03",
                    title="Pre-Stage Governance Stage Controls (Tab 4)",
                    description="Open the Chief Administrator Governance & Dual-Control tab to review Stage 1/2/3 transition controls manually.",
                    ui_target="tab-btn-4",
                    endpoint="/api/v1/governance/mode",
                    method="POST",
                    payload={"current_mode": gov_mode},
                    requires_dual_control=False,
                ),
                _make_chancellor_card(
                    action_type="INSPECT_GOVERNANCE_POSTURE",
                    auth_tier="AUTH-01",
                    title="Audit Active House Petitions & Enclave Registry",
                    description="Read-only inspection of 12-House petitions and configured voter seats.",
                    ui_target="tab-btn-4",
                    endpoint="/api/v1/governance/state",
                    method="GET",
                    payload={},
                ),
            ],
            "citations": ["active-hat-r06", "directive-r04-halt"],
            "policy_decision_matrix": matrix,
        }

    # 4. Distribution / Dual-Signature Override / Treasury Policy -> AUTH-02 / AUTH-03 pre-staged cards
    if any(m in q for m in ("distribution", "approve", "override", "countersign", "dual-signature", "treasury", "cfcp", "ifas")):
        matrix = {
            "matrix_id": f"MAT-{uuid.uuid4().hex[:8].upper()}",
            "topic": "TREASURY_DISTRIBUTION_DUAL_CONTROL",
            "governance_posture": posture,
            "immutable_conflicts": [],
            "options": [
                {
                    "option_id": "OPT-A",
                    "label": "Audit Signed IFAS Outbox & HWM Conservation First",
                    "summary": "Verify ADR-008 exact-cent balance conservation, ADR-012 HWM eligibility, and ADR-011 HMAC-SHA256 outbox receipts.",
                    "auth_tier": "AUTH-01",
                    "reversible": True,
                    "recommended": True,
                    "risk_level": "LOW",
                    "invariant_status": "PASS",
                },
                {
                    "option_id": "OPT-B",
                    "label": "Pre-Stage Distribution / Co-Sign Review",
                    "summary": "Review pending Yellow/Red-Tier distribution impact and custodial co-signature requirements manually.",
                    "auth_tier": "AUTH-02",
                    "reversible": True,
                    "recommended": False,
                    "risk_level": "MODERATE",
                    "invariant_status": "PASS",
                },
                {
                    "option_id": "OPT-C",
                    "label": "Pre-Stage F3 CRO Dual-Signature Counter-Sign",
                    "summary": f"Inspect {ctx['pending_dual_sig_overrides']} pending F3 CRO dual-signature override(s) requiring Chief Administrator adjudication.",
                    "auth_tier": "AUTH-03",
                    "reversible": True,
                    "recommended": ctx["pending_dual_sig_overrides"] > 0,
                    "risk_level": "MODERATE",
                    "invariant_status": "PASS",
                },
            ],
            "invariant_checks": invariant_checks,
            "unilateral_execution": False,
            "mutated": False,
        }
        return {
            "content": (
                f"No distribution or dual-signature override has been approved (`unilateral_execution = False`). "
                "All accounting instructions cross to standalone IFAS strictly via ADR-011 HMAC-SHA256 signed outbox "
                "events with zero banking credentials inside PDEUE, and 87/10/3 waterfall splits apply strictly above "
                "each SCMA's ADR-012 High-Water Mark."
            ),
            "auth_tier": "AUTH-03",
            "action_cards": [
                _make_chancellor_card(
                    action_type="STAGE_DUAL_SIG_COUNTERSIGN",
                    auth_tier="AUTH-03",
                    title="Pre-Stage Dual-Signature Counter-Sign Review",
                    description="Open the Chief Administrator Governance & Dual-Control tab (requires explicit confirmation).",
                    ui_target="tab-btn-4",
                    endpoint="/api/v1/portal/advisor/dual-signature-overrides",
                    method="GET",
                    payload={"pending_overrides": ctx["pending_dual_sig_overrides"]},
                    requires_dual_control=True,
                ),
                _make_chancellor_card(
                    action_type="STAGE_IFAS_OUTBOX_AUDIT",
                    auth_tier="AUTH-02",
                    title="Inspect ADR-011 Signed Outbox & CFCP Ledger",
                    description="Verify exact-cent IFAS outbox events and lineal sub-ledgers without initiating capital movement.",
                    ui_target="tab-btn-2",
                    endpoint="/api/v1/accounting/events",
                    method="GET",
                    payload={},
                ),
            ],
            "citations": ["adr-011-air-gap", "adr-008-exact-cents", "tpw-waterfall", "high-water-mark-adr-012"],
            "policy_decision_matrix": matrix,
        }

    # 5. Default Executive Risk & Operational Policy Posture Matrix
    matrix = {
        "matrix_id": f"MAT-{uuid.uuid4().hex[:8].upper()}",
        "topic": "EXECUTIVE_RISK_POLICY_POSTURE",
        "governance_posture": posture,
        "immutable_conflicts": [],
        "options": [
            {
                "option_id": "OPT-A",
                "label": "Maintain Fail-Closed Paper Qualification (Gate G1)",
                "summary": "Preserve HOLD_OBSERVATIONS_ONLY in paper mode while continuing OBSERVED_L2 capture and 87/10/3 ledger audits.",
                "auth_tier": "AUTH-01",
                "reversible": True,
                "recommended": True,
                "risk_level": "LOW",
                "invariant_status": "PASS",
            },
            {
                "option_id": "OPT-B",
                "label": "Audit Cross-House Risk & 40% Dry-Powder Headroom",
                "summary": "Review live SCMA concentration, Quarter-Kelly bounds, and 40% Dry-Powder Floor compliance across all 12 Houses.",
                "auth_tier": "AUTH-02",
                "reversible": True,
                "recommended": False,
                "risk_level": "LOW",
                "invariant_status": "PASS",
            },
            {
                "option_id": "OPT-C",
                "label": "Keep Directive R-04 & SHTF Snap-Back Armed",
                "summary": "Retain instant fail-closed Directive R-04 halt and Stage 1 Executive Command snap-back readiness.",
                "auth_tier": "AUTH-04",
                "reversible": True,
                "recommended": False,
                "risk_level": "MODERATE",
                "invariant_status": "PASS",
            },
        ],
        "invariant_checks": invariant_checks,
        "unilateral_execution": False,
        "mutated": False,
    }
    return {
        "content": (
            f"Chief Administrator Policy Posture (`unilateral_execution = False`): Governance is in `{gov_mode}` "
            f"(Stage {ctx['governance_stage']}), Directive R-04 is `{r04_status}`, and Gate G1 remains fail-closed "
            "in `HOLD_OBSERVATIONS_ONLY` (paper mode). All 5 constitutional pillars (87/10/3 TPW, ADR-012 HWM, "
            "Rule A14 loss isolation, ADR-011 air-gap, and Executive/SHTF posture) pass with zero mutations."
        ),
        "auth_tier": "AUTH-01",
        "action_cards": [
            _make_chancellor_card(
                action_type="TELEMETRY_REFRESH",
                auth_tier="AUTH-01",
                title="Refresh Cockpit Telemetry & Risk Envelope",
                description="Inspect latest exact-cent portfolio, waterfall, and Gate G1 telemetry (read-only).",
                ui_target="tab-btn-1",
                endpoint="/api/v1/operator/workspace-state",
                method="GET",
                payload={},
            ),
            _make_chancellor_card(
                action_type="STAGE_GOVERNANCE_REVIEW",
                auth_tier="AUTH-02",
                title="Review Governance & SHTF Posture (Tab 4)",
                description="Focus the 12-House Governance & SHTF posture panel for manual Chief Administrator review.",
                ui_target="tab-btn-4",
                endpoint="/api/v1/governance/state",
                method="GET",
                payload={},
            ),
        ],
        "citations": ["tpw-waterfall", "high-water-mark-adr-012", "adr-011-air-gap", "gate-g1-qualification"],
        "policy_decision_matrix": matrix,
    }


class ChiefAdminChancellorCoach:
    """Chief Administrator AI Chancellor Coach with local-first knowledge/media short-circuit (Milestone F4 + PR #96)."""

    def __init__(self, llm_client: Optional[BaseLLMClient] = None, *, local_first: bool = True):
        self._injected_client = llm_client
        self._local_first = bool(local_first)

    def _client(self) -> BaseLLMClient:
        return self._injected_client if self._injected_client is not None else get_llm_client()

    def advise(
        self,
        query: str,
        *,
        actor_id: str = "Chief Administrator",
        live_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        ctx = build_chancellor_context(live_context=live_context)
        verdict = inspect_user_input(
            query,
            actor_role="CHIEF_ADMINISTRATOR",
            actor_id=actor_id,
        )
        if verdict.blocked:
            refusal = verdict.refusal_message or "Request refused under PDEUE constitutional guardrails."
            return {
                "answer_text": refusal,
                "response_text": refusal,
                "citations": ["constitutional-guardrails"],
                "action_cards": [],
                "risk_telemetry": {
                    "current_risk_pct": ctx["current_risk_pct"],
                    "dry_powder_cents": ctx["dry_powder_cents"],
                    "downward_only_locked": ctx["downward_only_locked"],
                },
                "provider_used": "guardrails",
                "model_used": "policy-v1",
                "fallback_used": False,
                "unilateral_execution": False,
                "auth_tier": "AUTH-01",
                "guard_blocked": True,
                "guard_category": verdict.category,
                "audit_event_id": verdict.audit_event_id,
                "policy_decision_matrix": None,
                "governance_posture": {
                    "governance_mode": ctx["governance_mode"],
                    "governance_stage": ctx["governance_stage"],
                    "directive_r04_status": ctx["directive_r04_status"],
                    "gate_g1_status": ctx["gate_g1_status"],
                    "venue_mode": ctx["venue_mode"],
                },
                "answered_locally": True,
                "media_refs": [],
                "playbook_steps": [],
                "manual_citations": [],
                "lineage_context": {
                    "governance_mode": ctx["governance_mode"],
                    "directive_r04_status": ctx["directive_r04_status"],
                    "auth_tier": "AUTH-01",
                    "guard_blocked": True,
                    "model_prob": 0.27,
                },
            }

        draft_pack = build_constrained_policy_decision_matrix(verdict.sanitized_text, ctx)
        local_hit = (
            get_local_knowledge_index().query(verdict.sanitized_text, role="CHIEF_ADMIN")
            if self._local_first
            else None
        )
        if self._local_first and local_hit is not None and local_hit.matched:
            safe_text = sanitize_output_text(
                draft_pack["content"],
                actor_role="CHIEF_ADMINISTRATOR",
            )
            safe_cards = sanitize_action_cards(
                draft_pack.get("action_cards") or [],
                actor_role="CHIEF_ADMINISTRATOR",
            )
            matrix = draft_pack.get("policy_decision_matrix")
            posture = (matrix or {}).get("governance_posture") or {
                "governance_mode": ctx["governance_mode"],
                "governance_stage": ctx["governance_stage"],
                "directive_r04_status": ctx["directive_r04_status"],
                "gate_g1_status": ctx["gate_g1_status"],
                "venue_mode": ctx["venue_mode"],
            }
            return {
                "answer_text": safe_text,
                "response_text": safe_text,
                "citations": list(draft_pack.get("citations") or ["live-context"]),
                "action_cards": safe_cards,
                "risk_telemetry": {
                    "current_risk_pct": ctx["current_risk_pct"],
                    "dry_powder_cents": ctx["dry_powder_cents"],
                    "downward_only_locked": ctx["downward_only_locked"],
                },
                "provider_used": "local_knowledge_index",
                "model_used": "local-index-v1",
                "fallback_used": False,
                "unilateral_execution": False,
                "auth_tier": draft_pack.get("auth_tier") or "AUTH-01",
                "guard_blocked": False,
                "guard_category": None,
                "audit_event_id": None,
                "policy_decision_matrix": matrix,
                "governance_posture": posture,
                "answered_locally": True,
                "media_refs": list(local_hit.media_refs),
                "playbook_steps": list(local_hit.playbook_steps),
                "manual_citations": list(local_hit.manual_citations),
                "lineage_context": {
                    "governance_mode": ctx["governance_mode"],
                    "directive_r04_status": ctx["directive_r04_status"],
                    "auth_tier": draft_pack.get("auth_tier") or "AUTH-01",
                    "guard_blocked": False,
                    "model_prob": 0.27,
                },
            }

        copilot_draft = {
            "content": draft_pack["content"],
            "auth_tier": draft_pack["auth_tier"],
            "action_cards": draft_pack["action_cards"],
            "citations": draft_pack["citations"],
            "structured_data": {
                "policy_decision_matrix": draft_pack["policy_decision_matrix"],
                "governance_posture": draft_pack["policy_decision_matrix"]["governance_posture"],
            },
        }
        llm_resp = self._client().generate_safe_response(
            system_prompt=CHANCELLOR_SYSTEM_PROMPT,
            user_query=query,
            context={**ctx, "copilot_draft": copilot_draft},
            actor_role="CHIEF_ADMINISTRATOR",
            actor_id=actor_id,
        )
        structured = dict(llm_resp.structured_data or {}) if not llm_resp.guard_triggered else {}
        return {
            "answer_text": llm_resp.content,
            "response_text": llm_resp.content,
            "citations": list(llm_resp.citations) or (["constitutional-guardrails"] if llm_resp.guard_triggered else ["live-context"]),
            "action_cards": llm_resp.action_cards,
            "risk_telemetry": {
                "current_risk_pct": ctx["current_risk_pct"],
                "dry_powder_cents": ctx["dry_powder_cents"],
                "downward_only_locked": ctx["downward_only_locked"],
            },
            "provider_used": llm_resp.provider,
            "model_used": llm_resp.model,
            "fallback_used": llm_resp.fallback_used,
            "unilateral_execution": False,
            "auth_tier": llm_resp.auth_tier,
            "guard_blocked": llm_resp.guard_triggered,
            "guard_category": llm_resp.guard_category,
            "audit_event_id": llm_resp.audit_event_id,
            "policy_decision_matrix": structured.get("policy_decision_matrix"),
            "governance_posture": structured.get("governance_posture") or {
                "governance_mode": ctx["governance_mode"],
                "governance_stage": ctx["governance_stage"],
                "directive_r04_status": ctx["directive_r04_status"],
                "gate_g1_status": ctx["gate_g1_status"],
                "venue_mode": ctx["venue_mode"],
            },
            "answered_locally": False,
            "media_refs": list(llm_resp.media_refs),
            "playbook_steps": list(llm_resp.playbook_steps),
            "manual_citations": list(llm_resp.manual_citations),
            "lineage_context": {
                "governance_mode": ctx["governance_mode"],
                "directive_r04_status": ctx["directive_r04_status"],
                "auth_tier": llm_resp.auth_tier,
                "guard_blocked": llm_resp.guard_triggered,
                "model_prob": 0.27,
            },
        }
