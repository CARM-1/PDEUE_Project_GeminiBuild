from typing import Dict, Any, List, Optional
from app.domain.circuit_breaker import CircuitBreakerEngine
from app.domain.audit_retention import AuditRetentionEngine
from app.domain.mode_controller import ModeController
from app.domain.compliance_policy import CompliancePolicyEngine
from app.domain.source_qualification import SourceQualificationRegistry
from app.domain.identity_governance import IdentityGovernanceEngine

class UnifiedGovernanceGate:
    def __init__(
        self,
        circuit_breaker: Optional[CircuitBreakerEngine] = None,
        audit_retention: Optional[AuditRetentionEngine] = None,
        mode_controller: Optional[ModeController] = None,
        compliance_policy: Optional[CompliancePolicyEngine] = None,
        source_registry: Optional[SourceQualificationRegistry] = None,
        identity_governance: Optional[IdentityGovernanceEngine] = None
    ):
        self.circuit_breaker = circuit_breaker or CircuitBreakerEngine()
        self.audit_retention = audit_retention or AuditRetentionEngine()
        self.mode_controller = mode_controller or ModeController(initial_mode="PAPER")
        self.compliance_policy = compliance_policy or CompliancePolicyEngine()
        self.source_registry = source_registry or SourceQualificationRegistry()
        self.identity_governance = identity_governance or IdentityGovernanceEngine()

    def evaluate_execution_admission(
        self,
        principal_id: str,
        tenant_id: str,
        source_id: str,
        venue: str,
        jurisdiction: str,
        proposed_stake: float
    ) -> Dict[str, Any]:
        denial_reasons: List[str] = []

        # 1. Circuit Breaker Check
        if not self.circuit_breaker.validate_execution_allowed():
            denial_reasons.append(f"CIRCUIT_BREAKER_TRIPPED: {self.circuit_breaker.trip_reason}")

        # 2. Operating Mode Check
        if not self.mode_controller.can_execute_orders():
            denial_reasons.append(f"EXECUTION_DISALLOWED_IN_MODE_{self.mode_controller.current_mode}")

        # 3. Source Qualification Check
        source_res = self.source_registry.evaluate_source(source_id)
        if not source_res["qualified"]:
            reason = source_res["reason"]
            denial_reasons.append(f"UNQUALIFIED_SOURCE: {reason}")

        # 4. Compliance Policy Check
        comp_res = self.compliance_policy.evaluate_compliance(tenant_id, venue, jurisdiction, proposed_stake)
        if not comp_res["admissible"]:
            denial_reasons.extend(comp_res["policy_flags"])

        # 5. Identity & RBAC Check
        auth_res = self.identity_governance.authorize_action(principal_id, tenant_id, "START_SESSION")
        if not auth_res["authorized"]:
            reason = auth_res["reason"]
            denial_reasons.append(f"IDENTITY_DENIAL: {reason}")

        is_admitted = len(denial_reasons) == 0
        action_label = "GOVERNANCE_ADMISSION_GRANTED" if is_admitted else "GOVERNANCE_ADMISSION_DENIED"

        # 6. Immutable Audit Retention
        audit_entry = self.audit_retention.record_event(
            tenant_id=tenant_id,
            action=action_label,
            actor_id=principal_id,
            details={
                "admitted": is_admitted,
                "venue": venue,
                "jurisdiction": jurisdiction,
                "proposed_stake": proposed_stake,
                "denial_reasons": denial_reasons
            }
        )

        return {
            "admitted": is_admitted,
            "denial_reasons": denial_reasons,
            "audit_entry_hash": audit_entry["entry_hash"],
            "chain_verified": self.audit_retention.verify_chain_integrity()
        }
