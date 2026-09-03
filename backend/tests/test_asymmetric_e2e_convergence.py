from datetime import datetime, timezone
from app.domain.advanced_underwriting_pipeline import AdvancedUnderwritingPipeline
from app.domain.decision_packet import DecisionPacketBuilder
from app.domain.capital_ledger import CapitalLedger
from app.domain.execution_coordinator import ExecutionEnvelopeCoordinator

def test_asymmetric_weather_e2e_lifecycle():
    pipeline = AdvancedUnderwritingPipeline()
    cutoff = datetime(2026, 9, 3, 12, 0, 0, tzinfo=timezone.utc)
    evidence = [{
        'evidence_id': 'EV-GEFS-CONV-01',
        'published_at': '2026-09-03T10:00:00Z',
        'payload': {'member_temperatures_c': [24.0, 24.5, 25.0, 25.2, 24.8, 25.5]}
    }]
    snapshot = {
        'market_id': 'MKT-WX-01',
        'contract_id': 'KX-CHICAGO-HIGH-28C',
        'yes_bid': 0.15,
        'yes_ask': 0.20,
        'timestamp': '2026-09-03T12:00:00Z'
    }
    underwriting = pipeline.run_underwriting(
        cutoff=cutoff,
        evidence_items=evidence,
        market_snapshot=snapshot,
        strike_temp_c=28.0,
        station_id='KORD'
    )
    assert underwriting['admissible_count'] == 1
    assert underwriting['station_id'] == 'KORD'
    assert underwriting['model_probability'] > 0.0

    builder = DecisionPacketBuilder(kelly_fraction=0.25, max_position_pct=0.10)
    packet = builder.build_decision_packet(
        event_id='EVT-WX-KORD-01',
        raw_prob=underwriting['model_probability'],
        yes_ask=0.20,
        total_capital=10000.0,
        reliability_factor=1.0
    )
    stake_dollars = packet['capital_bid']['recommended_stake']
    stake_cents = int(stake_dollars * 100)

    ledger = CapitalLedger(initial_balance_cents=1000000)
    assert ledger.reserve_capital('RES-ASYM-01', max(100, stake_cents)) is True

    coordinator = ExecutionEnvelopeCoordinator(mode='PAPER')
    order_qty = max(1, int(stake_dollars)) if stake_dollars > 0 else 10
    cost_cents = stake_cents if stake_cents > 0 else 200
    order_intent = {
        'decision_packet_id': packet['packet_id'],
        'contract_id': 'KX-CHICAGO-HIGH-28C',
        'side': 'BUY',
        'price': 0.20,
        'quantity': order_qty,
        'total_cost_cents': cost_cents,
        'idempotency_key': 'IDEM-ASYM-CONV-01'
    }
    reservation = {'reserved': True, 'reserved_cents': cost_cents + 100}
    exec_res = coordinator.execute_order_lifecycle(
        tenant_id='tenant_asym',
        account_id='acc_primary',
        venue='KALSHI',
        order_intent=order_intent,
        reservation=reservation
    )
    assert exec_res['success'] is True
    assert exec_res['stage'] == 'ROUTED'

    order_id = exec_res['order_id']
    coordinator.reconciliation_engine.record_fill(order_id=order_id, fill_price=0.20, fill_quantity=order_qty)
    venue_rep = {'contract_id': 'KX-CHICAGO-HIGH-28C', 'side': 'BUY', 'filled_quantity': order_qty, 'status': 'FILLED'}
    rec = coordinator.reconciliation_engine.reconcile(exec_res['routed_payload'], venue_rep)
    assert rec['is_reconciled'] is True

    pos = coordinator.position_service.update_from_fill(
        tenant_id='tenant_asym',
        account_id='acc_primary',
        contract_id='KX-CHICAGO-HIGH-28C',
        side='BUY',
        fill_price=0.20,
        fill_quantity=order_qty
    )
    assert pos['quantity'] == order_qty

    settle = coordinator.settlement_interface.settle_position(
        tenant_id='tenant_asym',
        account_id='acc_primary',
        contract_id='KX-CHICAGO-HIGH-28C',
        position=pos,
        outcome='YES'
    )
    assert settle['status'] == 'SUCCESS'
