import uuid
from datetime import datetime, timezone
from typing import Dict, Any, Optional

class SettlementInterface:
    """
    B7-EXE-06 Settlement Interface.
    Reconciles resolutions, payouts, fees, and net realized PnL.
    """
    VALID_OUTCOMES = {'YES', 'NO', 'VOID', 'CANCELLED'}
    def __init__(self):
        self.settlement_records: Dict[str, Dict[str, Any]] = {}

    def settle_position(self, tenant_id: str, account_id: str, contract_id: str, position: Dict[str, Any], outcome: str, settlement_fee_cents: int = 0) -> Dict[str, Any]:
        outcome_upper = outcome.upper()
        if outcome_upper not in self.VALID_OUTCOMES:
            return {'status': 'REJECTED', 'reason': f'INVALID_OUTCOME_{outcome_upper}', 'settlement_id': None}
        quantity = position.get('quantity', 0)
        cost_basis_cents = position.get('cost_basis_cents', 0)
        side = position.get('side', 'BUY').upper()
        if quantity <= 0:
            return {'status': 'REJECTED', 'reason': 'NO_OPEN_QUANTITY_TO_SETTLE', 'settlement_id': None}
        if outcome_upper in {'VOID', 'CANCELLED'}:
            gross_payout_cents = cost_basis_cents
            net_payout_cents = gross_payout_cents
            realized_pnl_cents = 0
        elif outcome_upper == side or (outcome_upper == 'YES' and side in {'BUY', 'YES'}):
            gross_payout_cents = quantity * 100
            net_payout_cents = max(0, gross_payout_cents - settlement_fee_cents)
            realized_pnl_cents = net_payout_cents - cost_basis_cents
        else:
            gross_payout_cents = 0
            net_payout_cents = 0
            realized_pnl_cents = -cost_basis_cents
        settlement_id = f'SETTLE-{uuid.uuid4().hex[:8].upper()}'
        record = {
            'settlement_id': settlement_id,
            'tenant_id': tenant_id,
            'account_id': account_id,
            'contract_id': contract_id,
            'side': side,
            'quantity_settled': quantity,
            'cost_basis_cents': cost_basis_cents,
            'outcome': outcome_upper,
            'gross_payout_cents': gross_payout_cents,
            'fee_cents': settlement_fee_cents,
            'net_payout_cents': net_payout_cents,
            'realized_pnl_cents': realized_pnl_cents,
            'status': 'SETTLED',
            'settled_at': datetime.now(timezone.utc).isoformat()
        }
        self.settlement_records[settlement_id] = record
        return {'status': 'SUCCESS', 'settlement_id': settlement_id, 'record': record}
