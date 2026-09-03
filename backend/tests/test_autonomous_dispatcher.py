from app.domain.autonomous_dispatcher import AutonomousOpportunityDispatcher
from app.domain.capital_ledger import CapitalLedger

def test_autonomous_dispatcher_happy_path():
    dispatcher = AutonomousOpportunityDispatcher()
    ensemble = [24.0, 24.5, 25.0, 25.5, 25.0]
    ladder = [
        {'contract_id': 'KX-ORD-20', 'strike_temp_c': 20.0, 'yes_bid': 0.95, 'yes_ask': 0.99},
        {'contract_id': 'KX-ORD-26', 'strike_temp_c': 26.0, 'yes_bid': 0.08, 'yes_ask': 0.12}
    ]
    res = dispatcher.dispatch_weather_ladder(
        tenant_id='tenant_auto',
        account_id='acc_auto_01',
        venue='KALSHI',
        event_id='EVT-WX-AUTO-01',
        ensemble_members=ensemble,
        strike_ladder=ladder,
        station_id='KORD',
        total_capital=10000.0
    )
    assert res['status'] == 'DISPATCHED'
    assert res['top_pick']['contract_id'] == 'KX-ORD-26'
    assert res['execution_result']['success'] is True
    assert res['execution_result']['stage'] == 'ROUTED'

def test_autonomous_dispatcher_abstain_on_fair_market():
    dispatcher = AutonomousOpportunityDispatcher()
    ensemble = [20.0, 20.0, 20.0]
    ladder = [{'contract_id': 'KX-FAIR-20', 'strike_temp_c': 20.0, 'yes_bid': 0.48, 'yes_ask': 0.52}]
    res = dispatcher.dispatch_weather_ladder(
        tenant_id='tenant_auto',
        account_id='acc_auto_01',
        venue='KALSHI',
        event_id='EVT-WX-AUTO-02',
        ensemble_members=ensemble,
        strike_ladder=ladder,
        station_id=None
    )
    assert res['status'] == 'ABSTAINED'
    assert res['reason'] == 'NO_ADMISSIBLE_OPPORTUNITY'

def test_autonomous_dispatcher_insufficient_ledger_capital():
    tiny_ledger = CapitalLedger(initial_balance_cents=10)
    dispatcher = AutonomousOpportunityDispatcher(ledger=tiny_ledger)
    ensemble = [24.0, 24.5, 25.0, 25.5, 25.0]
    ladder = [{'contract_id': 'KX-ORD-26', 'strike_temp_c': 26.0, 'yes_bid': 0.08, 'yes_ask': 0.12}]
    res = dispatcher.dispatch_weather_ladder(
        tenant_id='tenant_auto',
        account_id='acc_auto_01',
        venue='KALSHI',
        event_id='EVT-WX-AUTO-03',
        ensemble_members=ensemble,
        strike_ladder=ladder,
        station_id='KORD',
        total_capital=10000.0
    )
    assert res['status'] == 'BLOCKED'
    assert res['reason'] == 'INSUFFICIENT_LEDGER_BALANCE'
