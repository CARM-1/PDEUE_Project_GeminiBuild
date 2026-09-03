from datetime import datetime, timezone
from app.domain.pit_selector import PITSelector
from app.domain.weather_engine import WeatherProbabilityEngine
from app.domain.economic_engine import EconomicUnderwritingEngine
from app.domain.capital_ledger import CapitalLedger
from app.domain.decision_packet import DecisionPacketBuilder
from app.domain.market_depth import MarketDepthEngine
from app.domain.execution_coordinator import ExecutionEnvelopeCoordinator

def test_master_cross_domain_underwriting_and_execution_lifecycle():
    # 1. Weather Domain Underwriting (B1/B2)
    cutoff = datetime(2026, 9, 3, 12, 0, 0, tzinfo=timezone.utc)
    pit = PITSelector(cutoff_time=cutoff)
    weather_evidence = [
        {'evidence_id': 'EV-WX-01', 'published_at': '2026-09-03T11:30:00Z', 'payload': {'temperature_c': 24.5}},
        {'evidence_id': 'EV-WX-02', 'published_at': '2026-09-03T11:45:00Z', 'payload': {'temperature_c': 25.5}}
    ]
    admissible_wx = pit.filter_admissible_evidence(weather_evidence)
    assert len(admissible_wx) == 2
    wx_engine = WeatherProbabilityEngine()
    wx_prob = wx_engine.compute_probability(admissible_wx, strike_temp_c=23.0)
    assert wx_prob == 1.0

    # 2. Economic Domain Underwriting (B3)
    econ_engine = EconomicUnderwritingEngine()
    econ_eval = econ_engine.evaluate_cpi_event(released_cpi=3.4, target_cpi=3.1)
    econ_prob = econ_eval['calculated_probability']
    assert econ_prob > 0.5

    # 3. Capital Ledger & Kelly Allocation (B4)
    ledger = CapitalLedger(initial_balance_cents=1000000)
    builder = DecisionPacketBuilder(kelly_fraction=0.25, max_position_pct=0.10)
    packet = builder.build_decision_packet(
        event_id='EVT-MULTI-WX-01',
        raw_prob=wx_prob,
        yes_ask=0.55,
        total_capital=10000.0,
        reliability_factor=1.0
    )
    stake_dollars = packet['capital_bid']['recommended_stake']
    stake_cents = int(stake_dollars * 100)
    assert ledger.reserve_capital('RES-MASTER-01', stake_cents) is True

    # 4. Market Depth & Slippage Protection (B4)
    depth_engine = MarketDepthEngine(fee_rate=0.01)
    order_book = ['placeholder']  # verified via engine evaluation
    book_levels = [{'price': 0.55, 'size': 10000.0}]
    depth = depth_engine.evaluate_order_depth(book_levels, requested_volume=stake_dollars)
    assert depth['executable'] is True

    # 5. Execution Envelope Lifecycle (B7: B7-EXE-01 through B7-EXE-08)
    coordinator = ExecutionEnvelopeCoordinator(mode='PAPER')
    order_intent = {
        'decision_packet_id': packet['packet_id'],
        'contract_id': 'KX-CHICAGO-HIGH-75',
        'side': 'BUY',
        'price': 0.55,
        'quantity': int(stake_dollars),
        'total_cost_cents': stake_cents,
        'idempotency_key': 'IDEM-MASTER-EXEC-01'
    }
    reservation = {'reserved': True, 'reserved_cents': stake_cents}
    exec_res = coordinator.execute_order_lifecycle(
        tenant_id='tenant_primary',
        account_id='acc_alpha',
        venue='KALSHI',
        order_intent=order_intent,
        reservation=reservation
    )
    assert exec_res['success'] is True
    assert exec_res['stage'] == 'ROUTED'
    order_id = exec_res['order_id']

    # 6. Fill Reconciliation & Position MTM
    coordinator.reconciliation_engine.record_fill(order_id=order_id, fill_price=0.55, fill_quantity=int(stake_dollars))
    venue_report = {'contract_id': 'KX-CHICAGO-HIGH-75', 'side': 'BUY', 'filled_quantity': int(stake_dollars), 'status': 'FILLED'}
    rec = coordinator.reconciliation_engine.reconcile(exec_res['routed_payload'], venue_report)
    assert rec['is_reconciled'] is True

    pos = coordinator.position_service.update_from_fill(
        tenant_id='tenant_primary',
        account_id='acc_alpha',
        contract_id='KX-CHICAGO-HIGH-75',
        side='BUY',
        fill_price=0.55,
        fill_quantity=int(stake_dollars)
    )
    assert pos['quantity'] == int(stake_dollars)

    # 7. Final Settlement
    settlement = coordinator.settlement_interface.settle_position(
        tenant_id='tenant_primary',
        account_id='acc_alpha',
        contract_id='KX-CHICAGO-HIGH-75',
        position=pos,
        outcome='YES'
    )
    assert settlement['status'] == 'SUCCESS'
    assert settlement['record']['realized_pnl_cents'] > 0
