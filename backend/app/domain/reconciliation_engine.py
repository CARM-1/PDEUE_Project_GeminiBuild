import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

class ReconciliationEngine:
    def __init__(self):
        self.fills: Dict[str, List[Dict[str, Any]]] = {}
        self.reconciliations: Dict[str, Dict[str, Any]] = {}

    def record_fill(self, order_id: str, fill_price: float, fill_quantity: float, venue_execution_id: Optional[str] = None) -> Dict[str, Any]:
        fill_id = venue_execution_id or f'FILL-{uuid.uuid4().hex[:8].upper()}'
        fill = {
            'fill_id': fill_id,
            'order_id': order_id,
            'fill_price': fill_price,
            'fill_quantity': fill_quantity,
            'recorded_at': datetime.now(timezone.utc).isoformat()
        }
        if order_id not in self.fills:
            self.fills[order_id] = []
        self.fills[order_id].append(fill)
        return fill

    def reconcile(self, internal_order: Dict[str, Any], venue_report: Dict[str, Any]) -> Dict[str, Any]:
        order_id = internal_order.get('order_id', 'UNKNOWN')
        discrepancies: List[str] = []
        if internal_order.get('contract_id') != venue_report.get('contract_id'):
            discrepancies.append('CONTRACT_ID_MISMATCH')
        if internal_order.get('side') != venue_report.get('side'):
            discrepancies.append('SIDE_MISMATCH')
        ordered_qty = internal_order.get('quantity', 0)
        venue_filled_qty = venue_report.get('filled_quantity', 0)
        if venue_filled_qty > ordered_qty:
            discrepancies.append('OVERFILL_DETECTED')
        fills = self.fills.get(order_id, [])
        if fills:
            cum_qty = sum(f['fill_quantity'] for f in fills)
            vwap = round(sum(f['fill_price'] * f['fill_quantity'] for f in fills) / cum_qty, 4) if cum_qty > 0 else 0.0
        else:
            cum_qty = venue_filled_qty
            vwap = venue_report.get('average_price', internal_order.get('price', 0.0))
        is_reconciled = len(discrepancies) == 0
        summary = {
            'reconciliation_id': f'REC-{uuid.uuid4().hex[:8].upper()}',
            'order_id': order_id,
            'is_reconciled': is_reconciled,
            'status': venue_report.get('status', 'RECONCILED' if is_reconciled else 'DISCREPANCY'),
            'ordered_quantity': ordered_qty,
            'cumulative_filled_quantity': cum_qty,
            'remaining_quantity': max(0, ordered_qty - cum_qty),
            'vwap': vwap,
            'discrepancies': discrepancies,
            'reconciled_at': datetime.now(timezone.utc).isoformat()
        }
        self.reconciliations[order_id] = summary
        return summary
