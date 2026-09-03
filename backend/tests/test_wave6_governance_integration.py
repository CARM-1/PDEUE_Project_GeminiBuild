from app.domain.governance_gate import UnifiedGovernanceGate
from app.domain.circuit_breaker import CircuitBreakerEngine
from app.domain.mode_controller import ModeController
from app.domain.source_qualification import SourceQualificationRegistry
from app.domain.identity_governance import IdentityGovernanceEngine

def test_unified_governance_gate_admission_success():
    sources = SourceQualificationRegistry()
    sources.register_source("SRC-NOAA", "NOAA Feed", "US_PUBLIC_DOMAIN", "TIER_1", is_public_or_lawful=True)
    
    identity = IdentityGovernanceEngine()
    identity.register_principal("usr_trader_01", "tenant_prime", ["OPERATOR"])

    gate = UnifiedGovernanceGate(source_registry=sources, identity_governance=identity)
    
    res = gate.evaluate_execution_admission(
        principal_id="usr_trader_01",
        tenant_id="tenant_prime",
        source_id="SRC-NOAA",
        venue="KALSHI",
        jurisdiction="US_IL",
        proposed_stake=10000.0
    )
    assert res["admitted"] is True
    assert len(res["denial_reasons"]) == 0
    assert res["chain_verified"] is True

def test_unified_governance_gate_fail_closed_on_killswitch():
    cb = CircuitBreakerEngine()
    cb.trip("Latency spike anomaly", actor_id="monitor")
    
    sources = SourceQualificationRegistry()
    sources.register_source("SRC-NOAA", "NOAA Feed", "US_PUBLIC_DOMAIN", "TIER_1", is_public_or_lawful=True)
    
    identity = IdentityGovernanceEngine()
    identity.register_principal("usr_trader_01", "tenant_prime", ["OPERATOR"])

    gate = UnifiedGovernanceGate(circuit_breaker=cb, source_registry=sources, identity_governance=identity)
    
    res = gate.evaluate_execution_admission(
        principal_id="usr_trader_01",
        tenant_id="tenant_prime",
        source_id="SRC-NOAA",
        venue="KALSHI",
        jurisdiction="US_IL",
        proposed_stake=5000.0
    )
    assert res["admitted"] is False
    assert any("CIRCUIT_BREAKER_TRIPPED" in r for r in res["denial_reasons"])
    assert res["chain_verified"] is True
