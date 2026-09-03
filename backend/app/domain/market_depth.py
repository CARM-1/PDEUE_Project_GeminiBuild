from typing import Dict, Any, List, Optional

class MarketDepthEngine:
    def __init__(self, fee_rate: float = 0.01):
        self.fee_rate = fee_rate

    def evaluate_order_depth(
        self,
        order_book: List[Dict[str, float]],
        requested_volume: float
    ) -> Dict[str, Any]:
        if not order_book or requested_volume <= 0:
            return {
                "executable": False,
                "executed_volume": 0.0,
                "vwap": 0.0,
                "slippage": 0.0,
                "fee": 0.0,
                "reason": "EMPTY_BOOK_OR_ZERO_VOLUME"
            }

        total_available = sum(level.get("size", 0.0) for level in order_book)
        if total_available < requested_volume:
            return {
                "executable": False,
                "executed_volume": 0.0,
                "vwap": 0.0,
                "slippage": 0.0,
                "fee": 0.0,
                "reason": "INSUFFICIENT_LIQUIDITY",
                "available_volume": total_available
            }

        top_of_book = order_book[0].get("price", 0.0)
        remaining = requested_volume
        total_cost = 0.0

        for level in order_book:
            price = level.get("price", 0.0)
            size = level.get("size", 0.0)
            fill_amount = min(remaining, size)
            total_cost += fill_amount * price
            remaining -= fill_amount
            if remaining <= 0:
                break

        vwap = round(total_cost / requested_volume, 4)
        slippage = round(max(0.0, vwap - top_of_book), 4)
        fee = round(total_cost * self.fee_rate, 4)

        return {
            "executable": True,
            "executed_volume": requested_volume,
            "top_of_book": top_of_book,
            "vwap": vwap,
            "slippage": slippage,
            "fee": fee,
            "effective_unit_cost": round((total_cost + fee) / requested_volume, 4)
        }
