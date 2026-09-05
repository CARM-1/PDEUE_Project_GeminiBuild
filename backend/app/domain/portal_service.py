from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from app.domain.capital_ledger import CapitalLedger
from app.domain.position_book import PositionBook

class PortalService:
    def __init__(self, ledger: Optional[CapitalLedger] = None, position_book: Optional[PositionBook] = None):
        self.ledger = ledger or CapitalLedger()
        self.position_book = position_book or PositionBook()
        self.distribution_requests: List[Dict[str, Any]] = []

    def get_member_view(self, scma_id: str) -> Dict[str, Any]:
        member = self.ledger.members.get(scma_id)
        if not member:
            return {'status': 'NOT_FOUND', 'scma_id': scma_id}
        open_positions = [
            p for p in self.position_book.positions.values()
            if p.get('member_id') == scma_id and p.get('net_quantity', 0) != 0
        ]
        return {
            'status': 'OK',
            'scma_id': scma_id,
            'balance_cents': member['balance_cents'],
            'reserved_cents': member['reserved_cents'],
            'max_risk_pct': member['max_risk_pct'],
            'lifetime_profit_cents': member.get('lifetime_profit_cents', 0),
            'open_positions': open_positions,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }

    def update_member_risk_dial(self, scma_id: str, requested_risk_pct: float) -> Dict[str, Any]:
        member = self.ledger.members.get(scma_id)
        if not member:
            return {'status': 'NOT_FOUND', 'reason': 'Member account does not exist'}
        current_risk = float(member['max_risk_pct'])
        if requested_risk_pct > current_risk:
            return {
                'status': 'REJECTED',
                'reason': f'Risk dial is downward-only. Cannot increase from {current_risk} to {requested_risk_pct}',
                'current_risk_pct': current_risk
            }
        new_risk = max(0.005, round(requested_risk_pct, 4))
        member['max_risk_pct'] = new_risk
        return {'status': 'UPDATED', 'scma_id': scma_id, 'new_risk_pct': new_risk}

    def queue_distribution_request(self, scma_id: str, amount_cents: int) -> Dict[str, Any]:
        member = self.ledger.members.get(scma_id)
        if not member:
            return {'status': 'NOT_FOUND'}
        if amount_cents <= 0 or amount_cents > member['balance_cents']:
            return {'status': 'REJECTED', 'reason': 'Insufficient available balance'}
        req = {
            'request_id': f'DST-{len(self.distribution_requests)+1:05d}',
            'scma_id': scma_id,
            'amount_cents': amount_cents,
            'status': 'QUEUED',
            'created_at': datetime.now(timezone.utc).isoformat()
        }
        self.distribution_requests.append(req)
        return {'status': 'QUEUED', 'request': req}

    def get_advisor_household_view(self, household_id: str, member_ids: List[str]) -> Dict[str, Any]:
        members_data = []
        total_val_cents = 0
        for mid in member_ids:
            mem = self.ledger.members.get(mid)
            if mem:
                total_val_cents += mem['balance_cents'] + mem['reserved_cents']
                members_data.append({
                    'scma_id': mid,
                    'balance_cents': mem['balance_cents'],
                    'reserved_cents': mem['reserved_cents'],
                    'risk_dial': mem['max_risk_pct'],
                    'lifetime_profit_cents': mem.get('lifetime_profit_cents', 0)
                })
        return {
            'status': 'OK',
            'household_id': household_id,
            'total_valuation_cents': total_val_cents,
            'member_count': len(members_data),
            'members': members_data,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
