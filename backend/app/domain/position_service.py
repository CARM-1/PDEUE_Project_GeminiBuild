import uuid
from datetime import datetime, timezone
from typing import Dict, Any, Optional

class PositionStateService:
    """
    B7-EXE-05 Position State Service.
    Owns positions, cost basis, and exposure derived from authoritative fills.
    """
    def __init__(self):
        self.positions: Dict[str, Dict[str, Any]] = {}

    def _make_key(self, tenant_id: str, account_id: str, contract_id: str) -> str:
        return f'{tenant_id}:{account_id}:{contract_id}'

    def update_from_fill(self, tenant_id: str, account_id: str, contract_id: str, side: str, fill_price: float, fill_quantity: int) -> Dict[str, Any]:
        if fill_quantity <= 0:
            raise ValueError('Fill quantity must be positive')
        if fill_price < 0.0 or fill_price > 1.0:
            raise ValueError('Fill price must be between 0.0 and 1.0')
        key = self._make_key(tenant_id, account_id, contract_id)
        pos = self.positions.get(key, {
            'position_id': f'POS-{uuid.uuid4().hex[:8].upper()}',
            'tenant_id': tenant_id,
            'account_id': account_id,
            'contract_id': contract_id,
            'side': side.upper(),
            'quantity': 0,
            'average_entry_price': 0.0,
            'cost_basis_cents': 0,
            'realized_pnl_cents': 0,
            'updated_at': datetime.now(timezone.utc).isoformat()
        })
        if pos['quantity'] == 0:
            pos['side'] = side.upper()
            pos['quantity'] = fill_quantity
            pos['average_entry_price'] = round(fill_price, 4)
            pos['cost_basis_cents'] = int(round(fill_quantity * fill_price * 100))
        elif pos['side'] == side.upper():
            new_qty = pos['quantity'] + fill_quantity
            new_cost_cents = pos['cost_basis_cents'] + int(round(fill_quantity * fill_price * 100))
            pos['average_entry_price'] = round((new_cost_cents / 100.0) / new_qty, 4) if new_qty > 0 else 0.0
            pos['quantity'] = new_qty
            pos['cost_basis_cents'] = new_cost_cents
        else:
            close_qty = min(pos['quantity'], fill_quantity)
            closed_cost_cents = int(round(close_qty * pos['average_entry_price'] * 100))
            proceeds_cents = int(round(close_qty * fill_price * 100))
            realized = proceeds_cents - closed_cost_cents
            pos['realized_pnl_cents'] += realized
            pos['quantity'] -= close_qty
            pos['cost_basis_cents'] -= closed_cost_cents
            if pos['quantity'] == 0:
                pos['average_entry_price'] = 0.0
        pos['updated_at'] = datetime.now(timezone.utc).isoformat()
        self.positions[key] = pos
        return dict(pos)

    def mark_to_market(self, tenant_id: str, account_id: str, contract_id: str, market_price: float) -> Dict[str, Any]:
        key = self._make_key(tenant_id, account_id, contract_id)
        pos = self.positions.get(key)
        if not pos or pos['quantity'] == 0:
            return {'unrealized_pnl_cents': 0, 'current_value_cents': 0, 'quantity': 0}
        current_value_cents = int(round(pos['quantity'] * market_price * 100))
        unrealized_pnl_cents = current_value_cents - pos['cost_basis_cents']
        return {
            'contract_id': contract_id,
            'quantity': pos['quantity'],
            'cost_basis_cents': pos['cost_basis_cents'],
            'current_value_cents': current_value_cents,
            'unrealized_pnl_cents': unrealized_pnl_cents,
            'marked_at': datetime.now(timezone.utc).isoformat()
        }

    def get_position(self, tenant_id: str, account_id: str, contract_id: str) -> Optional[Dict[str, Any]]:
        return self.positions.get(self._make_key(tenant_id, account_id, contract_id))
