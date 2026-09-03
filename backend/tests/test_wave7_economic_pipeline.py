from app.domain.domain_adapter_sdk import EconomicIndicatorAdapter
from app.domain.economic_mapper import EconomicMarketMapper
from app.domain.source_qualification import SourceQualificationRegistry
from app.domain.identity_governance import IdentityGovernanceEngine
from app.domain.governance_gate import UnifiedGovernanceGate
from app.domain.decision_packet import DecisionPacketBuilder

def test_macroeconomic_full_underwriting_and_governance_pipeline():
    sources = SourceQualificationRegistry()
    sources.register_source(
        source_id='SRC-BLS-CPI',
        name='Bureau of Labor Statistics Consumer Price Index',
        license_type='US_PUBLIC_DOMAIN',
        quality_tier='TIER_1',
        is_public_or_lawful=True,
        commercial_allowed=True
    )
    src_eval = sources.evaluate_source('SRC-BLS-CPI')
    assert src_eval['qualified'] is True

    econ_adapter = EconomicIndicatorAdapter()
    event_spec = {
        'event_id': 'EVT-ECON-CPI-2026-08',
        'series_id': 'CPIAUCSL',
        'threshold': 3.0,
        'target_period': '2026-08',
        'resolution_authority': 'US_BLS'
    }
    event_def = econ_adapter.map_event_definition(event_spec)
    assert event_def['domain'] == 'MACROECONOMIC'

    pit_evidence = [
        {'source': 'CONSENSUS_1', 'value': 3.20, 'available_at': '2026-09-01T12:00:00Z'},
        {'source': 'CONSENSUS_2', 'value': 3.35, 'available_at': '2026-09-02T12:00:00Z'}
    ]
    features = econ_adapter.extract_features(pit_evidence)
    features['threshold'] = event_def['threshold']

    artifact = econ_adapter.underwrite(features)
    assert artifact['calibrated_probability'] > 0.50
    calibrated_prob = artifact['calibrated_probability']

    mapper = EconomicMarketMapper(venue='KALSHI')
    mapped_contract = mapper.map_venue_contract(
        venue_symbol='KALSHI-CPI-26AUG-T3.0',
        canonical_event_id=event_def['event_id'],
        threshold=event_def['threshold'],
        target_period=event_def['target_period']
    )
    assert mapped_contract['canonical_event_id'] == 'EVT-ECON-CPI-2026-08'

    comparison = mapper.evaluate_edge(calibrated_prob=calibrated_prob, market_yes_ask=0.55)
    assert comparison['gross_edge'] > 0
    assert comparison['admissible'] is True

    identity = IdentityGovernanceEngine()
    identity.register_principal('trader_macro_01', 'tenant_global', ['OPERATOR'])

    gate = UnifiedGovernanceGate(source_registry=sources, identity_governance=identity)
    gov_res = gate.evaluate_execution_admission(
        principal_id='trader_macro_01',
        tenant_id='tenant_global',
        source_id='SRC-BLS-CPI',
        venue='KALSHI',
        jurisdiction='US_IL',
        proposed_stake=5000.0
    )
    assert gov_res['admitted'] is True
    assert gov_res['chain_verified'] is True

    builder = DecisionPacketBuilder(kelly_fraction=0.25, max_position_pct=0.10)
    packet = builder.build_decision_packet(
        event_id=event_def['event_id'],
        raw_prob=calibrated_prob,
        yes_ask=0.55,
        total_capital=100000.0,
        reliability_factor=1.0
    )
    assert packet['operating_mode'] == 'NORMAL'
    assert packet['capital_bid']['recommended_stake'] > 0
    assert len(packet['blocked_reasons']) == 0
