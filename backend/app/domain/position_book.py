from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

class PositionBook:
    def __init__(self):
        self.positions: Dict[str, Dict[str, Any]] = {}
        self.realized_pnl_cents: int = 0

    def record_fill(self, contract_id: str, venue: str, category: str, side: str, price: float, quantity: int, fill_cost_cents: int) -> Dict[str, Any]:
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

    def update_market_prices(self, market_feed: List[Dict[str, Any]]) -> None:
        price_map = {}
        for item in market_feed:
            cid = item.get('contract_id')
            yes_bid = item.get('yes_bid', 0.0)
            yes_ask = item.get('yes_ask', 1.0)
            mid = round((yes_bid + yes_ask) / 2.0, 4)
            if cid:
                price_map[cid] = mid

        for cid, pos in self.positions.items():
            if cid in price_map:
                mid = price_map[cid]
                pos['current_mid'] = mid
                pos_val_dollars = pos['quantity'] * mid
                mtm_val_cents = int(round(pos_val_dollars * 100))
                pos['mtm_value_cents'] = mtm_val_cents
                pos['unrealized_pnl_cents'] = mtm_val_cents - pos['total_cost_cents']
                if pos['total_cost_cents'] > 0:
                    pos['roi_pct'] = round((pos['unrealized_pnl_cents'] / pos['total_cost_cents']) * 100.0, 2)
                pos['last_updated'] = datetime.now(timezone.utc).isoformat()

    def get_summary(self) -> Dict[str, Any]:
        total_invested = sum(p['total_cost_cents'] for p in self.positions.values())
        total_mtm = sum(p['mtm_value_cents'] for p in self.positions.values())
        total_unrealized = total_mtm - total_invested
        roi = round((total_unrealized / total_invested * 100.0), 2) if total_invested > 0 else 0.0
        return {
            'open_positions_count': len(self.positions),
            'total_invested_cents': total_invested,
            'total_mtm_value_cents': total_mtm,
            'total_unrealized_pnl_cents': total_unrealized,
            'portfolio_roi_pct': roi,
            'realized_pnl_cents': self.realized_pnl_cents,
            'positions': list(self.positions.values())
        }
