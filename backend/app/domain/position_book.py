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
        pos_key = f'{member_id}:{contract_id}' if member_id != 'DEFAULT' else contract_id
        pos = self.positions.get(pos_key)
        if not pos:
            vwap = price
            total_qty = quantity
            total_cost = fill_cost_cents
        else:
            total_qty = pos['quantity'] + quantity
            total_cost = pos['total_cost_cents'] + fill_cost_cents
            vwap = round((pos['vwap_price'] * pos['quantity'] + price * quantity) / total_qty, 4)

        self.positions[pos_key] = {'contract_id': contract_id, 'position_id': pos_key, 'venue': venue, 'category': category, 'side': side, 'member_id': member_id, 'quantity': total_qty, 'vwap_price': vwap, 'total_cost_cents': total_cost, 'current_mid': vwap, 'mtm_value_cents': total_cost, 'unrealized_pnl_cents': 0, 'roi_pct': 0.0, 'last_updated': datetime.now(timezone.utc).isoformat()}
        return self.positions[pos_key]
    def close_position(self, contract_id: str, outcome: str, payout_cents: int) -> Optional[Dict[str, Any]]:
        pos_key = contract_id
        if pos_key not in self.positions:
            matches = [k for k, v in self.positions.items() if v.get('contract_id') == contract_id]
            if matches:
                pos_key = matches[0]
            else:
                return None
        pos = self.positions.pop(pos_key)
        cost = pos['total_cost_cents']
        pnl = payout_cents - cost
        self.realized_pnl_cents += pnl
        record = {'contract_id': pos['contract_id'], 'position_id': pos_key, 'venue': pos['venue'], 'category': pos['category'], 'side': pos['side'], 'member_id': pos.get('member_id', 'DEFAULT'), 'quantity': pos['quantity'], 'vwap_price': pos['vwap_price'], 'total_cost_cents': cost, 'outcome': outcome, 'payout_cents': payout_cents, 'realized_pnl_cents': pnl, 'closed_at': datetime.now(timezone.utc).isoformat()}
        self.settled_positions.append(record)
        return record

    def update_market_prices(self, market_feed: List[Dict[str, Any]]) -> None:
        price_map = {}
        for item in market_feed:
            cid = item.get('contract_id')
            yes_bid = item.get('yes_bid', 0.0)
            yes_ask = item.get('yes_ask', 1.0)
            if cid:
                price_map[cid] = round((yes_bid + yes_ask) / 2.0, 4)
        for pos in self.positions.values():
            cid = pos.get('contract_id')
            if cid in price_map:
                mid = price_map[cid]
                pos['current_mid'] = mid
                mtm = int(round(pos['quantity'] * mid * 100))
                pos['mtm_value_cents'] = mtm
                pos['unrealized_pnl_cents'] = mtm - pos['total_cost_cents']
                pos['roi_pct'] = round((pos['unrealized_pnl_cents'] / pos['total_cost_cents']) * 100.0, 2) if pos['total_cost_cents'] > 0 else 0.0
                pos['last_updated'] = datetime.now(timezone.utc).isoformat()

    def get_summary(self) -> Dict[str, Any]:
        total_inv = sum(p['total_cost_cents'] for p in self.positions.values())
        total_mtm = sum(p['mtm_value_cents'] for p in self.positions.values())
        return {'open_positions_count': len(self.positions), 'settled_positions_count': len(self.settled_positions), 'total_invested_cents': total_inv, 'total_mtm_value_cents': total_mtm, 'total_unrealized_pnl_cents': total_mtm - total_inv, 'realized_pnl_cents': self.realized_pnl_cents, 'positions': list(self.positions.values()), 'settled_positions': self.settled_positions}
