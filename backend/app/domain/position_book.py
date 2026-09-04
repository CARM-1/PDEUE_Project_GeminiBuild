from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

class PositionBook:
    def __init__(self):
        self.positions: Dict[str, Dict[str, Any]] = {}
        self.settled_positions: List[Dict[str, Any]] = []
        self.realized_pnl_cents: int = 0

    def record_fill(self, contract_id: str, venue: str, category: str, side: str, price: float, quantity: int, fill_cost_cents: int, member_id: str = 'DEFAULT') -> Dict[str, Any]:
        if quantity <= 0:
            return {}
        pos = self.positions.get(contract_id)
        if not pos:
            vwap = price
            total_qty = quantity
            total_cost = fill_cost_cents
        else:
            total_qty = pos['quantity'] + quantity
            total_cost = pos['total_cost_cents'] + fill_cost_cents
            vwap = round((pos['vwap_price'] * pos['quantity'] + price * quantity) / total_qty, 4)

        self.positions[contract_id] = {
            'contract_id': contract_id,
            'venue': venue,
            'category': category,
            'side': side,
            'member_id': member_id,
            'quantity': total_qty,
            'vwap_price': vwap,
            'total_cost_cents': total_cost,
            'current_mid': vwap,
            'mtm_value_cents': total_cost,
            'unrealized_pnl_cents': 0,
            'roi_pct': 0.0,
            'last_updated': datetime.now(timezone.utc).isoformat()
        }
        return self.positions[contract_id]
    def close_position(self, contract_id: str, outcome: str, payout_cents: int) -> Optional[Dict[str, Any]]:
        pos = self.positions.pop(contract_id, None)
        if not pos:
            return None
        cost = pos['total_cost_cents']
        pnl = payout_cents - cost
        self.realized_pnl_cents += pnl
        record = {'contract_id': contract_id, 'venue': pos['venue'], 'category': pos['category'], 'side': pos['side'], 'member_id': pos.get('member_id', 'DEFAULT'), 'quantity': pos['quantity'], 'vwap_price': pos['vwap_price'], 'total_cost_cents': cost, 'outcome': outcome, 'payout_cents': payout_cents, 'realized_pnl_cents': pnl, 'closed_at': datetime.now(timezone.utc).isoformat()}
        self.settled_positions.append(record)
        return record

    def get_summary(self) -> Dict[str, Any]:
        total_invested = sum(p['total_cost_cents'] for p in self.positions.values())
        total_mtm = sum(p['mtm_value_cents'] for p in self.positions.values())
        total_unrealized = total_mtm - total_invested
        roi = round((total_unrealized / total_invested * 100.0), 2) if total_invested > 0 else 0.0
        return {'open_positions_count': len(self.positions), 'settled_positions_count': len(self.settled_positions), 'total_invested_cents': total_invested, 'total_mtm_value_cents': total_mtm, 'total_unrealized_pnl_cents': total_unrealized, 'portfolio_roi_pct': roi, 'realized_pnl_cents': self.realized_pnl_cents, 'positions': list(self.positions.values()), 'settled_positions': self.settled_positions}
