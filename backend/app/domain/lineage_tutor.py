"""Class H (H1 / H2) & House Genealogist Local-First AI Tutor (PR #96).

100% local-first, zero outbound internet calls, zero LLM API dependencies.
Strictly grounded in:
- ``docs/manuals/CLASS_H_LINEAGE_AND_HERITAGE_MANUAL.md``
- ``docs/manuals/USER_QUICKSTART.md``
- ``backend/app/static/media/playbooks/registry.json`` (role-scoped to H1 / H2 / HOUSE_GENEALOGIST)
- ``backend/app/domain/lexicon_v05.py``

Constitutional & Governance Invariants:
- ``unilateral_execution = False`` on every response and staged Action Card.
- Directive R-12 masking strictly enforced for ``H1`` and ``HOUSE_GENEALOGIST``
  (``$****.**`` / ``SCMA-MEM-****`` — zero dollar balances or member SCMA leaks).
- Strict role isolation: ``H1``, ``H2``, and ``HOUSE_GENEALOGIST`` NEVER receive
  Chief Admin runbook sections or Class T3 CA override playbooks.
- Cross-House ``X-House-ID`` boundary enforced at the router layer (HTTP 403).
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional
import uuid

from app.domain.ai_clients.guardrails import (
    inspect_user_input,
    sanitize_action_cards,
    sanitize_output_text,
)
from app.domain.enclave_governance import format_cents
from app.domain.local_knowledge_index import (
    get_local_knowledge_index,
    normalize_knowledge_role,
)

ALLOWED_LINEAGE_TUTOR_ROLES = frozenset(
    {"H1", "H2", "HOUSE_GENEALOGIST", "CHIEF_ADMIN", "CHIEF_ADMIN_DEPUTY"}
)

_DOLLAR_RE = re.compile(r"\$\s?\d[\d,]*(?:\.\d{2})?")
_SCMA_RAW_RE = re.compile(r"\bSCMA-[A-Z0-9_]+-[A-F0-9]{4,12}\b", re.IGNORECASE)


def _scrub_r12_lineage_text(text: str, *, r12_masked: bool) -> str:
    if not r12_masked:
        return text
    scrubbed = _DOLLAR_RE.sub("$****.**", text)
    scrubbed = _SCMA_RAW_RE.sub("SCMA-MEM-****", scrubbed)
    return scrubbed


def _make_lineage_card(
    *,
    action_type: str,
    auth_tier: str,
    title: str,
    description: str,
    ui_target: str,
    payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "action_id": f"ACT-LIN-{uuid.uuid4().hex[:8].upper()}",
        "action_type": action_type,
        "auth_tier": auth_tier,
        "title": title,
        "description": description,
        "ui_target": ui_target,
        "payload": dict(payload or {}),
        "requires_human_confirmation": True,
        "unilateral_execution": False,
        "executed": False,
        "confirmation_notice": (
            "Non-executing proposal under AUTH-01–AUTH-04: explicit human confirmation is required."
        ),
    }


class ClassHLineageTutor:
    """Strictly local-first instructional aid for H1, H2, and HOUSE_GENEALOGIST (zero internet calls)."""

    def answer_lineage_query(
        self,
        query: str,
        *,
        role: str = "H1",
        house_id: int = 1,
        house_summary: Optional[Dict[str, Any]] = None,
        governance_state: Optional[Dict[str, Any]] = None,
        actor_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        cleaned = (query or "").strip()
        norm_role = normalize_knowledge_role(role)
        if norm_role not in ALLOWED_LINEAGE_TUTOR_ROLES:
            norm_role = "H1"  # fail-closed to least-privileged masked secretarial role

        safe_house_id = max(1, min(12, int(house_id or 1)))
        lineage_code = f"HOUSE-{safe_house_id:02d}"
        r12_masked = norm_role in {"H1", "HOUSE_GENEALOGIST"}
        effective_actor_id = actor_id or f"{norm_role}_{lineage_code}"

        # 1. Constitutional input guardrails (prompt injection, credential exfiltration, unilateral bypass)
        verdict = inspect_user_input(
            cleaned,
            actor_role=norm_role,
            actor_id=effective_actor_id,
            r12_unredacted=not r12_masked,
        )
        if verdict.blocked:
            refusal = _scrub_r12_lineage_text(
                verdict.refusal_message or "Request refused under PDEUE constitutional guardrails.",
                r12_masked=r12_masked,
            )
            return {
                "role": "LINEAGE_TUTOR",
                "active_role": norm_role,
                "house_id": safe_house_id,
                "lineage_code": lineage_code,
                "r12_masked": r12_masked,
                "query": cleaned,
                "answer": refusal,
                "response": refusal,
                "response_text": refusal,
                "answered_locally": True,
                "provider_used": "guardrails",
                "model_used": "policy-v1",
                "fallback_used": False,
                "unilateral_execution": False,
                "auth_tier": "AUTH-01",
                "guard_blocked": True,
                "guard_category": verdict.category,
                "audit_event_id": verdict.audit_event_id,
                "media_refs": [],
                "playbook_steps": [],
                "manual_citations": [],
                "action_cards": [],
            }

        q_lower = verdict.sanitized_text.lower()
        gov_mode = str((governance_state or {}).get("mode") or "EXECUTIVE_COMMAND")
        house_name = str((house_summary or {}).get("house_name") or f"House {safe_house_id:02d}")
        member_count = len((house_summary or {}).get("members") or [])

        # 2. Role-scoped local retrieval from manuals + playbooks/media + Lexicon v0.5
        index = get_local_knowledge_index()
        local_hit = index.query(verdict.sanitized_text, role=norm_role, allow_external_bypass=False)

        # If a broad/greeting Class H prompt didn't hit threshold, pull the primary routine playbook for this role
        if not local_hit.matched:
            fallback_seed = (
                "House Genealogist curate chronicles bordure differencing Hall of Arms"
                if norm_role == "HOUSE_GENEALOGIST"
                else "Class H House Roll Call R-12 Privacy Constitutional Stage Watch"
            )
            local_hit = index.query(fallback_seed, role=norm_role, allow_external_bypass=False)

        action_cards: List[Dict[str, Any]] = []
        auth_tier = "AUTH-01"

        # 3. Role-specific deterministic instructional framing (zero financial leaks for H1/HOUSE_GENEALOGIST)
        if norm_role == "H1":
            if any(k in q_lower for k in ("balance", "cash", "how much money", "dollar", "unmask")):
                lead = (
                    f"As H1 House Secretary for {lineage_code} ({house_name}), Directive R-12 privacy blinds are "
                    "permanently active on your desk: every member balance renders as `$****.**` and unredacted "
                    "financial figures are never exposed. You oversee secretarial roll call, roster status, and "
                    "family literacy without viewing personal savings."
                )
            elif any(k in q_lower for k in ("freeze", "cancel", "circuit breaker", "vote", "veto")):
                lead = (
                    f"H1 House Secretary ({lineage_code}) is a read-only secretarial office: subordinate circuit "
                    "breakers (Freeze Dial / Cancel Orders) and Bicameral voting are restricted to the H2 House Head "
                    "(HTTP 403 enforced server-side). Escalate urgent member safety issues to your H2 House Head or "
                    "Chief Administrator."
                )
            else:
                lead = (
                    f"H1 House Secretary Guidance ({lineage_code} · {house_name} · {member_count} rostered member(s), "
                    f"Governance Mode: {gov_mode}, Directive R-12 Masked `$****.**`): "
                    f"{local_hit.answer}"
                )
            action_cards.append(
                _make_lineage_card(
                    action_type="INSPECT_HOUSE_ROLL_CALL",
                    auth_tier="AUTH-01",
                    title=f"Focus {lineage_code} Scoped Custodial Lookup (R-12 Masked)",
                    description="Highlight the branch-confined lookup bar to verify House roster & literacy status.",
                    ui_target="custodial-lookup-input",
                    payload={"house_id": safe_house_id, "role": "H1"},
                )
            )
        elif norm_role == "HOUSE_GENEALOGIST":
            lead = (
                f"House Genealogist Curatorial Guidance ({lineage_code} · Hall of Arms Zero-Financial Space · "
                "Directive R-12 Masked `$****.**`): "
                f"{local_hit.answer}"
            )
            action_cards.append(
                _make_lineage_card(
                    action_type="OPEN_GENEALOGIST_DESK",
                    auth_tier="AUTH-01",
                    title="Focus Scoped Curatorial Desk (#genealogistDeskDrawer)",
                    description="Open the Hall of Arms Curatorial Desk to update authorized House chronicles or allied surnames (HTTP 403 enforced for cross-House edits).",
                    ui_target="genealogistDeskDrawer",
                    payload={"house_id": safe_house_id, "role": "HOUSE_GENEALOGIST"},
                )
            )
        else:
            # H2 House Head (or Chief Admin / Deputy inspecting Class H desk)
            total_cents = int((house_summary or {}).get("total_cash_cents") or 0)
            total_disp = format_cents(total_cents) if house_summary else "$0.00"
            if any(k in q_lower for k in ("freeze", "cancel", "circuit breaker", "errant", "emergency")):
                auth_tier = "AUTH-02"
                lead = (
                    f"H2 House Head Containment Guidance ({lineage_code} · {house_name}, `unilateral_execution = False`): "
                    "No subordinate dial has been frozen and no orders have been purged automatically. "
                    "Use the step-by-step playbook below to manually verify and confirm Freeze Dial (0%) or Cancel Orders. "
                    "Note: the Founder root SCMA carries permanent Sovereign Immunity (FOUNDER_APEX_IMMUNITY_VIOLATION)."
                )
                action_cards.append(
                    _make_lineage_card(
                        action_type="STAGE_HOUSE_CIRCUIT_BREAKER_REVIEW",
                        auth_tier="AUTH-02",
                        title=f"Review {lineage_code} Subordinate Circuit Breakers",
                        description="Manually inspect member risk dials and confirm any surgical freeze or order purge in the House table.",
                        ui_target="custodial-lookup-input",
                        payload={"house_id": safe_house_id, "role": norm_role},
                    )
                )
            elif any(k in q_lower for k in ("vote", "veto", "bicameral", "stage 1", "stage 2", "stage 3", "shtf")):
                auth_tier = "AUTH-02"
                lead = (
                    f"H2 Bicameral Chamber Guidance ({lineage_code} · Active Governance Mode: {gov_mode}, "
                    f"House Equity: {total_disp}, `unilateral_execution = False`): "
                    f"{local_hit.answer}"
                )
                action_cards.append(
                    _make_lineage_card(
                        action_type="INSPECT_BICAMERAL_CHAMBER",
                        auth_tier="AUTH-02",
                        title="Focus Bicameral CFCP Ratification Chamber",
                        description="Review the active constitutional stage (Stage 1 Executive / Stage 2 Advisory / Stage 3 Binding Veto) before casting any manual ballot.",
                        ui_target="vote-aye",
                        payload={"house_id": safe_house_id, "role": norm_role},
                    )
                )
            else:
                lead = (
                    f"H2 Sovereign Desk Guidance ({lineage_code} · {house_name} · {member_count} member(s), "
                    f"House Equity {total_disp}, Mode: {gov_mode}): {local_hit.answer}"
                )

        # 4. Output hygiene & R-12 scrubbing
        safe_text = sanitize_output_text(
            lead,
            actor_role=norm_role,
            r12_unredacted=not r12_masked,
        )
        safe_text = _scrub_r12_lineage_text(safe_text, r12_masked=r12_masked)
        safe_cards = sanitize_action_cards(action_cards, actor_role=norm_role)

        # Scrub any raw currency strings in citations/steps if R-12 masked
        safe_steps = [
            _scrub_r12_lineage_text(step, r12_masked=r12_masked)
            for step in local_hit.playbook_steps
        ]
        safe_citations = [
            {
                "manual_file": c["manual_file"],
                "section_title": c["section_title"],
                "excerpt": _scrub_r12_lineage_text(c.get("excerpt", ""), r12_masked=r12_masked),
            }
            for c in local_hit.manual_citations
        ]

        return {
            "role": "LINEAGE_TUTOR",
            "active_role": norm_role,
            "house_id": safe_house_id,
            "lineage_code": lineage_code,
            "r12_masked": r12_masked,
            "query": cleaned,
            "answer": safe_text,
            "response": safe_text,
            "response_text": safe_text,
            "answered_locally": True,
            "provider_used": "local_knowledge_index",
            "model_used": "local-index-v1",
            "fallback_used": False,
            "unilateral_execution": False,
            "auth_tier": auth_tier,
            "guard_blocked": False,
            "guard_category": None,
            "audit_event_id": None,
            "media_refs": list(local_hit.media_refs),
            "playbook_steps": safe_steps,
            "manual_citations": safe_citations,
            "action_cards": safe_cards,
        }


_DEFAULT_CLASS_H_TUTOR = ClassHLineageTutor()


def get_class_h_lineage_tutor() -> ClassHLineageTutor:
    return _DEFAULT_CLASS_H_TUTOR


__all__ = [
    "ALLOWED_LINEAGE_TUTOR_ROLES",
    "ClassHLineageTutor",
    "get_class_h_lineage_tutor",
]
