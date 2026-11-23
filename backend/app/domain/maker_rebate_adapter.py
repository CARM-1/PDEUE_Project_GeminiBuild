import uuid
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from app.domain.capital_ledger import CapitalLedger
from app.domain.settlement_engine import calculate_hwm_waterfall_cents, _require_int_cents

class MakerRebateLedgerAdapter:
    def __init__(self, ledger: Optional[CapitalLedger] = None):
        self.ledger = ledger or CapitalLedger()
        self.rebate_history = []

    def calculate_rebate_waterfall(
        self,
        rebate_cents: int,
        current_scma_equity_cents: int = 0,
        high_water_mark_cents: int = 0,
    ) -> Dict[str, int]:
        _require_int_cents(rebate_cents, "rebate_cents")
        if rebate_cents <= 0:
            return {
                'member_rebate_cents': 0,
                'central_family_pool_cents': 0,
                'founder_pool_cents': 0
            }
        # ADR-008 & ADR-012: exact integer-cent HWM waterfall; remainder cents route to CFCP.
        wf = calculate_hwm_waterfall_cents(
            realized_profit_cents=rebate_cents,
            current_scma_equity_cents=current_scma_equity_cents,
            high_water_mark_cents=high_water_mark_cents,
        )
        return {
            'member_rebate_cents': wf['scma_cents'],
            'central_family_pool_cents': wf['cfcp_cents'],
            'founder_pool_cents': wf['faep_cents']
        }

    def process_maker_rebate(
        self,
        member_id: str,
        rebate_cents: int,
        venue: str,
        contract_id: str,
        order_id: str
    ) -> Dict[str, Any]:
        _require_int_cents(rebate_cents, "rebate_cents")
        if rebate_cents < 0:
            raise ValueError('Rebate cents cannot be negative.')

        if rebate_cents > 0 and hasattr(self.ledger, 'members') and member_id in self.ledger.members:
            wf = self.ledger.settle_member_trade(member_id, rebate_cents)
            split = {
                'member_rebate_cents': wf['scma_cents'],
                'central_family_pool_cents': wf['cfcp_cents'],
                'founder_pool_cents': wf['faep_cents'],
            }
        else:
            split = self.calculate_rebate_waterfall(rebate_cents)
            if rebate_cents > 0:
                self.ledger.credit_member_balance(member_id, split['member_rebate_cents'])
                self.ledger.credit_central_family_pool(split['central_family_pool_cents'])
                self.ledger.credit_founder_pool(split['founder_pool_cents'])

        event = {
            'rebate_event_id': 'REBATE-' + uuid.uuid4().hex[:8],
            'member_id': member_id,
            'venue': venue.upper(),
            'contract_id': contract_id,
            'order_id': order_id,
            'total_rebate_cents': rebate_cents,
            'waterfall_split': split,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        self.rebate_history.append(event)
        return event
