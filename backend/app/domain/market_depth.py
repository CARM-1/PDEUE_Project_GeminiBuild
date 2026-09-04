from typing import Dict, Any, List, Optional

class MarketDepthEngine:
    def __init__(self, fee_rate: float = 0.01, max_slippage_pct: float = 0.05):
        self.fee_rate = fee_rate
        self.max_slippage_pct = max_slippage_pct

    def evaluate_order_depth(self, order_book: List[Dict[str, Any]], requested_volume: float, max_slippage_pct: Optional[float] = None) -> Dict[str, Any]:
        if not order_book or requested_volume <= 0:
            return {'executable': False, 'executed_volume': 0.0, 'vwap': 0.0, 'slippage': 0.0, 'reason': 'EMPTY_BOOK_OR_ZERO_VOLUME'}

        max_slip = max_slippage_pct if max_slippage_pct is not None else self.max_slippage_pct
        top_price = float(order_book[0].get('price', 0.0))
        if top_price <= 0:
            return {'executable': False, 'executed_volume': 0.0, 'vwap': 0.0, 'slippage': 0.0, 'reason': 'INVALID_PRICE'}

        remaining = requested_volume
        total_cost = 0.0
        total_filled = 0.0

        for level in order_book:
            lvl_price = float(level.get('price', 0.0))
            lvl_size = float(level.get('size', 0.0))
            fill_size = min(remaining, lvl_size)
            total_cost += fill_size * lvl_price
            total_filled += fill_size
            remaining -= fill_size
            if remaining <= 0:
                break

        if total_filled < requested_volume:
            return {'executable': False, 'executed_volume': total_filled, 'vwap': round(total_cost / total_filled, 4) if total_filled > 0 else 0.0, 'slippage': 0.0, 'reason': 'INSUFFICIENT_LIQUIDITY'}

        vwap = round(total_cost / requested_volume, 4)
        slippage = round(max(0.0, vwap - top_price), 4)
        slippage_pct = round(slippage / top_price, 4)

        if slippage_pct > max_slip:
            return {'executable': False, 'executed_volume': total_filled, 'vwap': vwap, 'slippage': slippage, 'slippage_pct': slippage_pct, 'reason': 'SLIPPAGE_EXCEEDED'}

        return {'executable': True, 'executed_volume': total_filled, 'vwap': vwap, 'slippage': slippage, 'slippage_pct': slippage_pct, 'fee_rate': self.fee_rate}

    def evaluate_net_edge_friction(self, raw_edge: float, spread: float, fee_rate: Optional[float] = None) -> Dict[str, Any]:
        fee = fee_rate if fee_rate is not None else self.fee_rate
        friction = spread + (fee * 2.0)
        net_edge = round(raw_edge - friction, 4)
        admissible = net_edge > 0.0
        return {'admissible': admissible, 'raw_edge': raw_edge, 'spread': spread, 'friction': friction, 'net_edge': net_edge, 'reason': 'PROFITABLE_NET_EDGE' if admissible else 'FRICTION_ELIMINATES_EDGE'}
