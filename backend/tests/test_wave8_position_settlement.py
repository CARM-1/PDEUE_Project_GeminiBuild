from app.domain.position_service import PositionStateService
from app.domain.settlement_interface import SettlementInterface

def test_position_accumulation_and_mark_to_market():
    svc = PositionStateService()
    pos = svc.update_from_fill(tenant_id='tenant_1', account_id='acc_1', contract_id='KX-HIGH-75', side='BUY', fill_price=0.40, fill_quantity=50)
    assert pos['quantity'] == 50
    assert pos['cost_basis_cents'] == 2000
    assert pos['average_entry_price'] == 0.40
    pos2 = svc.update_from_fill(tenant_id='tenant_1', account_id='acc_1', contract_id='KX-HIGH-75', side='BUY', fill_price=0.50, fill_quantity=50)
    assert pos2['quantity'] == 100
    assert pos2['cost_basis_cents'] == 4500
    assert pos2['average_entry_price'] == 0.45
    mtm = svc.mark_to_market('tenant_1', 'acc_1', 'KX-HIGH-75', market_price=0.60)
    assert mtm['current_value_cents'] == 6000
    assert mtm['unrealized_pnl_cents'] == 1500

def test_position_partial_close():
    svc = PositionStateService()
    svc.update_from_fill('tenant_1', 'acc_1', 'KX-HIGH-75', 'BUY', 0.40, 100)
    pos = svc.update_from_fill('tenant_1', 'acc_1', 'KX-HIGH-75', 'SELL', 0.60, 40)
    assert pos['quantity'] == 60
    assert pos['cost_basis_cents'] == 2400
    assert pos['realized_pnl_cents'] == 800

def test_settlement_winning_contract():
    settler = SettlementInterface()
    position = {'quantity': 100, 'cost_basis_cents': 4500, 'side': 'YES'}
    res = settler.settle_position(tenant_id='tenant_1', account_id='acc_1', contract_id='KX-HIGH-75', position=position, outcome='YES', settlement_fee_cents=50)
    assert res['status'] == 'SUCCESS'
    rec = res['record']
    assert rec['gross_payout_cents'] == 10000
    assert rec['net_payout_cents'] == 9950
    assert rec['realized_pnl_cents'] == 5450

def test_settlement_losing_contract():
    settler = SettlementInterface()
    position = {'quantity': 100, 'cost_basis_cents': 4500, 'side': 'YES'}
    res = settler.settle_position(tenant_id='tenant_1', account_id='acc_1', contract_id='KX-HIGH-75', position=position, outcome='NO')
    assert res['status'] == 'SUCCESS'
    rec = res['record']
    assert rec['gross_payout_cents'] == 0
    assert rec['realized_pnl_cents'] == -4500

def test_settlement_voided_contract():
    settler = SettlementInterface()
    position = {'quantity': 50, 'cost_basis_cents': 2000, 'side': 'BUY'}
    res = settler.settle_position(tenant_id='tenant_1', account_id='acc_1', contract_id='KX-HIGH-75', position=position, outcome='VOID')
    assert res['status'] == 'SUCCESS'
    rec = res['record']
    assert rec['gross_payout_cents'] == 2000
    assert rec['net_payout_cents'] == 2000
    assert rec['realized_pnl_cents'] == 0

def test_settlement_invalid_outcome_fails_closed():
    settler = SettlementInterface()
    position = {'quantity': 50, 'cost_basis_cents': 2000, 'side': 'BUY'}
    res = settler.settle_position(tenant_id='tenant_1', account_id='acc_1', contract_id='KX-HIGH-75', position=position, outcome='UNKNOWN_CORRUPT')
    assert res['status'] == 'REJECTED'
    assert 'INVALID_OUTCOME' in res['reason']
