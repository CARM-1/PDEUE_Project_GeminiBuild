import uuid
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from app.domain.capital_ledger import CapitalLedger

class MakerRebateLedgerAdapter:
    def __init__(self, ledger: Optional[CapitalLedger] = None):
        self.ledger = ledger or CapitalLedger()
        self.rebate_history = []

    def calculate_rebate_waterfall(self, rebate_cents: int) -> Dict[str, int]:
        if rebate_cents <= 0:
            return {
                'member_rebate_cents': 0,
                'central_family_pool_cents': 0,
                'founder_pool_cents': 0
            }
        founder_cut = int(round(rebate_cents * 0.03))
        cfcp_cut = int(round(rebate_cents * 0.10))
        member_cut = rebate_cents - (founder_cut + cfcp_cut)
        return {
            'member_rebate_cents': member_cut,
            'central_family_pool_cents': cfcp_cut,
            'founder_pool_cents': founder_cut
        }

    def process_maker_rebate(
        self,
        member_id: str,
        rebate_cents: int,
        venue: str,
        contract_id: str,
        order_id: str
    ) -> Dict[str, Any]:
        if rebate_cents < 0:
            raise ValueError('Rebate cents cannot be negative.')

        split = self.calculate_rebate_waterfall(rebate_cents)

        if rebate_cents > 0:
            self.ledger.credit_member_balance(member_id, split['member_rebate_cents'])
            self.ledger.credit_central_family_pool(split['central_family_pool_cents'])
            self.ledger.credit_founder_pool(split['founder_pool_cents'])
            if hasattr(self.ledger, 'members') and member_id in self.ledger.members:
                self.ledger.members[member_id]['lifetime_profit_cents'] += split['member_rebate_cents']

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
