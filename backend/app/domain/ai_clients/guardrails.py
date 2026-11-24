"""Constitutional Guardrails, Prompt-Injection Sanitizer & AUTH-01–AUTH-04 Enforcement.

Enforces PDEUE's non-negotiable AI Authority Envelope across all ``BaseLLMClient``
adapters and role-scoped assistants:

1. ``unilateral_execution = False`` invariant on every response and Action Card.
2. Input prompt-injection / jailbreak detection with calm, logged refusals.
3. Role-scope & Active-Hat boundary protection (Directive R-06).
4. Cross-member data & Directive R-12 masking isolation.
5. Secret & ADR-011 banking-credential exfiltration prevention.
6. Output sanitization (secret/token scrubbing, foreign SCMA redaction, unsafe card stripping).
"""
from __future__ import annotations

from dataclasses import dataclass
import logging
import re
from typing import Any, Dict, List, Optional, Tuple
import uuid

from app.domain.authority_tiers import get_governance_audit_log

logger = logging.getLogger("pdeue.ai.guardrails")

VALID_AUTH_TIERS: Tuple[str, ...] = ("AUTH-01", "AUTH-02", "AUTH-03", "AUTH-04")

# Member endpoints / action types that Class M MUST NEVER receive in an Action Card.
_FORBIDDEN_MEMBER_ENDPOINT_PREFIXES: Tuple[str, ...] = (
    "/api/v1/operator/",
    "/api/v1/admin/",
    "/api/v1/workspace/",
    "/api/v1/lineage/house/",
    "/api/v1/accounting/",
    "/api/v1/portal/tech/",
    "/api/v1/portal/advisor/",
)

_FORBIDDEN_MEMBER_ACTION_TYPES: frozenset[str] = frozenset({
    "EMERGENCY_STOP",
    "ORC_INSPECT",
    "STAGE_ORC_TRACKING_ORDER",
    "SYSTEM_HALT",
    "EXECUTE_ORDER",
    "UNILATERAL_TRADE",
    "UNILATERAL_WITHDRAWAL",
    "MUTATE_RISK_DIAL",
    "PROMOTE_GOVERNANCE_STAGE",
    "QUARANTINE_HOUSE",
})

# Canonical lineage member first names used to detect cross-member balance probes
# from a Class M member asking about a DIFFERENT member's private SCMA.
_KNOWN_LINEAGE_NAMES: Tuple[str, ...] = (
    "eleanor",
    "julian",
    "marcus",
    "arthur",
    "clara",
    "sophia",
    "founder",
    "chief administrator",
)

_PROMPT_INJECTION_PATTERNS: Tuple[re.Pattern[str], ...] = (
    re.compile(
        r"\b(?:ignore|disregard|forget|override|drop)\s+(?:all\s+|any\s+|your\s+)?(?:previous|prior|above|earlier|system|constitutional|safety)\s+(?:instructions?|rules?|prompts?|directives?|constraints?|guardrails?)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:reveal|show|print|dump|output|repeat|leak|display)\s+(?:me\s+)?(?:your\s+|the\s+)?(?:system\s+prompt|hidden\s+(?:prompt|instructions?)|internal\s+(?:prompt|instructions?)|developer\s+prompt)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:jailbreak|dan\s+mode|developer\s+mode|god\s+mode|sudo\s+mode|unrestricted\s+mode)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:bypass|disable|turn\s+off|suspend|remove)\s+(?:all\s+)?(?:safety|guardrails?|auth-0[1-4]|constitutional\s+invariants?|restrictions?)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"unilateral_execution\s*[:=]\s*true\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bpretend\s+(?:that\s+)?(?:unilateral_execution|you\s+have\s+no\s+rules|you\s+are\s+unrestricted)\b",
        re.IGNORECASE,
    ),
)

_ROLE_ESCALATION_PATTERNS: Tuple[re.Pattern[str], ...] = (
    re.compile(
        r"\b(?:switch|elevate|promote|grant|escalate|change)\s+(?:me|my\s+(?:role|hat|session|privileges?|access))\s+(?:to|into)\s+(?:chief[ _-]?admin(?:istrator)?|founder|f3|t3|cro|cto|class\s*[tfh]|operator|admin)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:act|behave|respond|operate|pretend)\s+as\s+(?:the\s+)?(?:chief[ _-]?admin(?:istrator)?|root|superuser|t3\s*cto|f3\s*cro|operator|system\s+admin)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:bypass|override|skip|ignore)\s+(?:http\s*403|directive\s*r-06|active[ -]hat|role\s*(?:isolation|siloing|boundary)|portal\s*boundary)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:show|give|dump|list|reveal|export)\s+(?:me\s+)?(?:the\s+)?(?:admin|operator|tech|devops|class\s*t|fleet|orderbook|all\s+houses?)\s+(?:telemetry|logs?|audit\s+logs?|state|positions?|depth|secrets?|dashboard)\b",
        re.IGNORECASE,
    ),
)

_SECRET_EXFIL_PATTERNS: Tuple[re.Pattern[str], ...] = (
    re.compile(
        r"\b(?:openai|gemini|anthropic|kalshi|polymarket)[ _-]?(?:api[ _-]?key|secret|token|credentials?)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:reveal|show|print|dump|give|export|leak|tell\s+me|fetch|read)\s+(?:me\s+)?(?:the\s+|your\s+)?(?:api\s*keys?|secret\s*keys?|hmac\s*secret|jwt\s*secret|credential\s*broker|credentials?|\.env|environment\s*variables?|private\s*key)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:reveal|show|print|dump|give|export|leak|store|save|record|link)\s+(?:me\s+)?(?:the\s+|my\s+|a\s+)?(?:bank\s+)?(?:routing\s+number|bank\s+account\s+number|account\s+number|swift\s+code|iban)\b",
        re.IGNORECASE,
    ),
)

_CROSS_MEMBER_EXFIL_PATTERNS: Tuple[re.Pattern[str], ...] = (
    re.compile(
        r"\b(?:show|tell|give|reveal|list|dump|check|inspect|what\s+is|what\s+are|how\s+much\s+(?:does|is))\b.*\b(?:other\s+members?|all\s+members?|everyone'?s|every\s+member'?s|sibling\s+scmas?|another\s+member'?s|other\s+accounts?|all\s+scmas?)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:unmask|reveal|bypass|override|remove)\b.*\b(?:directive\s*r-12|\$\*{4}\.\*\*|masked\s+balances?|redacted\s+scma|r-12\s+masking)\b",
        re.IGNORECASE,
    ),
)

_UNILATERAL_EXECUTION_DEMAND_PATTERNS: Tuple[re.Pattern[str], ...] = (
    re.compile(
        r"\b(?:force|bypass\s+confirmation|without\s+(?:confirmation|approval|asking)|override\s+auth-0[1-4]|unilaterally)\b.*\b(?:execute|trade|buy|sell|withdraw|sweep|transfer|mutate|halt|change|order)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:execute|dispatch|fire|force)\b.*\b(?:order|trade|buy|sell|sweep|wire|ach|withdrawal)\b.*\b(?:unilaterally|without\s+(?:confirmation|approval)|skipping\s+(?:review|confirmation))\b",
        re.IGNORECASE,
    ),
)

_SCMA_TOKEN_RE = re.compile(r"\bSCMA[-_][A-Z0-9_-]{3,}\b", re.IGNORECASE)
_SECRET_OUTPUT_PATTERNS: Tuple[Tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"), "[REDACTED_API_KEY]"),
    (re.compile(r"\bAIza[A-Za-z0-9_-]{16,}\b"), "[REDACTED_API_KEY]"),
    (re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]{8,}=*"), "Bearer [REDACTED]"),
    (re.compile(r"(?is)<script[^>]*>.*?</script>"), ""),
)


@dataclass
class GuardVerdict:
    blocked: bool
    sanitized_text: str
    category: Optional[str] = None
    reason: Optional[str] = None
    refusal_message: Optional[str] = None
    audit_event_id: Optional[str] = None


def _record_guard_event(
    *,
    category: str,
    reason: str,
    actor_id: str,
    actor_role: str,
    scma_id: Optional[str],
    query_preview: str,
) -> str:
    logger.warning(
        "PDEUE AI guardrail blocked query | category=%s actor_role=%s actor_id=%s scma_id=%s reason=%s",
        category,
        actor_role,
        actor_id,
        scma_id or "none",
        reason,
    )
    try:
        entry = get_governance_audit_log().record(
            event_type="AI_GUARDRAIL_REFUSAL",
            actor_id=actor_id,
            actor_role=actor_role,
            target_id=scma_id or "",
            action="AI_LLM_GUARDRAIL_INSPECT",
            outcome=f"BLOCKED_{category}",
            http_status=200,
            detail=reason,
            metadata={
                "category": category,
                "unilateral_execution": False,
                "query_preview": query_preview[:160],
            },
        )
        return str(entry.get("event_id", f"GRD-{uuid.uuid4().hex[:8].upper()}"))
    except Exception:
        return f"GRD-{uuid.uuid4().hex[:8].upper()}"


def _cross_member_probe_detected(
    text: str,
    *,
    actor_role: str,
    allowed_scma_id: Optional[str],
    member_name: Optional[str],
) -> Optional[str]:
    if actor_role.upper() != "MEMBER":
        return None

    for pattern in _CROSS_MEMBER_EXFIL_PATTERNS:
        if pattern.search(text):
            return "Cross-member balance or Directive R-12 unmasking probe blocked for Class M scope."

    # Check if prompt mentions a specific SCMA ID that does NOT belong to the requesting member.
    allowed_norm = (allowed_scma_id or "").strip().upper()
    for match in _SCMA_TOKEN_RE.finditer(text):
        mentioned = match.group(0).strip().upper()
        if allowed_norm and mentioned != allowed_norm:
            return f"Requested foreign SCMA identifier ({mentioned}) outside requesting member scope."
        if not allowed_norm and mentioned not in {"SCMA-MEM-****"}:
            return f"Requested explicit SCMA identifier ({mentioned}) without matching member scope."

    # Check if a Class M member asks for another named lineage member's balance/account/positions.
    lowered = text.lower()
    own_name_tokens = {tok for tok in re.split(r"[^a-z]+", (member_name or "").lower()) if len(tok) >= 3}
    asks_financial_detail = bool(
        re.search(
            r"\b(?:balance|cash|equity|scma|account|positions?|how\s+much|money|funds|withdraw|risk\s+dial|seed|net\s+worth|wealth)\b",
            lowered,
        )
    )
    if asks_financial_detail:
        for candidate in _KNOWN_LINEAGE_NAMES:
            if candidate in own_name_tokens:
                continue
            if re.search(rf"\b{re.escape(candidate)}(?:'s|’s)?\b", lowered):
                return f"Cross-member data request referencing '{candidate}' blocked under Directive R-12 & SCMA tenant isolation."

    return None


def inspect_user_input(
    user_query: str,
    *,
    actor_role: str = "MEMBER",
    actor_id: str = "member_user",
    allowed_scma_id: Optional[str] = None,
    member_name: Optional[str] = None,
) -> GuardVerdict:
    """Inspect and sanitize an incoming prompt before it reaches any LLM adapter."""
    raw = (user_query or "").strip()
    sanitized = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", raw)
    role_norm = (actor_role or "MEMBER").upper().strip()

    checks: List[Tuple[str, Optional[str], str]] = []

    for pat in _PROMPT_INJECTION_PATTERNS:
        if pat.search(sanitized):
            checks.append((
                "PROMPT_INJECTION",
                "Detected prompt-injection or constitutional override attempt.",
                (
                    "I cannot override PDEUE's constitutional safety rules, reveal internal prompts, "
                    "or enable unilateral execution (`unilateral_execution = False` is permanently locked "
                    "under AUTH-01 through AUTH-04). I'm glad to explain your own SCMA concepts, "
                    "Lexicon v0.5 terms, or illustrative compounding impact in plain English."
                ),
            ))
            break

    if not checks:
        for pat in _ROLE_ESCALATION_PATTERNS:
            if pat.search(sanitized):
                checks.append((
                    "ROLE_ESCALATION",
                    "Detected attempt to escalate role scope or bypass Directive R-06 Active-Hat isolation.",
                    (
                        "I cannot switch roles, bypass HTTP 403 portal boundaries, or access Chief Administrator, "
                        "Class F, or Class T telemetry from this workspace. Under Directive R-06 (Active-Hat Isolation), "
                        "each portal remains strictly scoped to its active authority tier."
                    ),
                ))
                break

    if not checks:
        for pat in _SECRET_EXFIL_PATTERNS:
            if pat.search(sanitized):
                checks.append((
                    "SECRET_EXFILTRATION",
                    "Detected attempt to extract API credentials, secrets, or ADR-011 banking credentials.",
                    (
                        "I cannot access, display, or store API keys, system secrets, or banking credentials "
                        "(routing numbers, account numbers, SWIFT/IBAN). Under ADR-011 (Zero Banking Credentials), "
                        "PDEUE stores only opaque `EXT-REF-...` deposit memo tokens and communicates with IFAS "
                        "via signed outbox events."
                    ),
                ))
                break

    if not checks:
        cross_reason = _cross_member_probe_detected(
            sanitized,
            actor_role=role_norm,
            allowed_scma_id=allowed_scma_id,
            member_name=member_name,
        )
        if cross_reason:
            checks.append((
                "CROSS_MEMBER_EXFILTRATION",
                cross_reason,
                (
                    "I can only discuss your own Self-Contained Member Account (SCMA) and general PDEUE "
                    "educational concepts. Under Directive R-12 and Rule A14 tenant isolation, other members' "
                    "balances, SCMA identifiers, and private records are strictly inaccessible here."
                ),
            ))

    if not checks:
        for pat in _UNILATERAL_EXECUTION_DEMAND_PATTERNS:
            if pat.search(sanitized):
                checks.append((
                    "UNILATERAL_EXECUTION_DEMAND",
                    "Detected attempt to force unilateral trade, withdrawal, or governance execution.",
                    (
                        "I cannot execute trades, move funds, or modify governance settings unilaterally. "
                        "Under AUTH-01 through AUTH-04 (`unilateral_execution = False`), PDEUE AI assistants "
                        "may only explain concepts and stage non-executing Action Cards for explicit human confirmation."
                    ),
                ))
                break

    if checks:
        category, reason, refusal_msg = checks[0]
        event_id = _record_guard_event(
            category=category,
            reason=reason or category,
            actor_id=actor_id,
            actor_role=role_norm,
            scma_id=allowed_scma_id,
            query_preview=sanitized,
        )
        return GuardVerdict(
            blocked=True,
            sanitized_text=sanitized,
            category=category,
            reason=reason,
            refusal_message=refusal_msg,
            audit_event_id=event_id,
        )

    return GuardVerdict(blocked=False, sanitized_text=sanitized)


def sanitize_output_text(
    text: str,
    *,
    actor_role: str = "MEMBER",
    allowed_scma_id: Optional[str] = None,
) -> str:
    """Scrub secrets, unsafe markup, and foreign SCMA IDs from model output."""
    cleaned = str(text or "")
    for pattern, replacement in _SECRET_OUTPUT_PATTERNS:
        cleaned = pattern.sub(replacement, cleaned)

    if (actor_role or "").upper().strip() == "MEMBER":
        allowed_norm = (allowed_scma_id or "").strip().upper()

        def _mask_foreign_scma(match: re.Match[str]) -> str:
            token = match.group(0)
            if allowed_norm and token.upper() == allowed_norm:
                return token
            return "SCMA-MEM-****"

        cleaned = _SCMA_TOKEN_RE.sub(_mask_foreign_scma, cleaned)

    return cleaned.strip()


def enforce_constitutional_action_card(
    card: Dict[str, Any],
    *,
    actor_role: str = "MEMBER",
) -> Optional[Dict[str, Any]]:
    """Validate and normalize an Action Card to guarantee ``unilateral_execution = False``."""
    if not isinstance(card, dict):
        return None

    role_norm = (actor_role or "MEMBER").upper().strip()
    action_type = str(card.get("action_type") or "EDUCATIONAL_REVIEW").upper().strip()
    endpoint = str(card.get("endpoint") or "").strip()

    if role_norm == "MEMBER":
        if action_type in _FORBIDDEN_MEMBER_ACTION_TYPES:
            return None
        if endpoint and any(endpoint.startswith(prefix) for prefix in _FORBIDDEN_MEMBER_ENDPOINT_PREFIXES):
            return None

    auth_tier = str(card.get("auth_tier") or "AUTH-01").upper().strip()
    if auth_tier not in VALID_AUTH_TIERS:
        auth_tier = "AUTH-01"

    normalized = dict(card)
    normalized.setdefault("action_id", f"ACT-{uuid.uuid4().hex[:8].upper()}")
    normalized["action_type"] = action_type
    normalized["auth_tier"] = auth_tier
    normalized["unilateral_execution"] = False
    normalized["executed"] = False
    normalized["requires_human_confirmation"] = True
    normalized.setdefault(
        "confirmation_notice",
        "Non-executing proposal under AUTH-01–AUTH-04: explicit human confirmation is required.",
    )
    return normalized


def sanitize_action_cards(
    cards: List[Dict[str, Any]],
    *,
    actor_role: str = "MEMBER",
) -> List[Dict[str, Any]]:
    """Filter and constitutionally stamp every Action Card in a response."""
    sanitized: List[Dict[str, Any]] = []
    for card in cards or []:
        checked = enforce_constitutional_action_card(card, actor_role=actor_role)
        if checked is not None:
            sanitized.append(checked)
    return sanitized
