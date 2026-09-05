from typing import Dict, Any, Optional

class MakerExecutionEngine:
    """B7-EXE Passive Liquidity & Inside-Spread Capture Engine."""
    def __init__(self, maker_fee_rate: float = 0.0, taker_fee_rate: float = 0.01):
        self.maker_fee_rate = maker_fee_rate
        self.taker_fee_rate = taker_fee_rate

    def construct_maker_bid(
        self,
        best_bid: float,
        best_ask: float,
        model_prob: float,
        min_margin: float = 0.02
    ) -> Dict[str, Any]:
        if best_bid >= best_ask or best_bid <= 0:
            return {'status': 'REJECTED', 'reason': 'INVALID_MARKET_SPREAD'}

        maker_limit = round(best_bid + 0.01, 2)
        max_bid_ceiling = round(model_prob - min_margin, 2)

        if maker_limit >= best_ask:
            maker_limit = round(best_ask - 0.01, 2)

        if maker_limit > max_bid_ceiling or maker_limit <= best_bid:
            return {
                'status': 'ABSTAINED',
                'reason': 'MAKER_MARGIN_INSUFFICIENT',
                'maker_price': maker_limit,
                'ceiling': max_bid_ceiling
            }

        spread_discount = round(best_ask - maker_limit, 4)
        fee_savings = round((best_ask * self.taker_fee_rate) - (maker_limit * self.maker_fee_rate), 4)

        return {
            'status': 'POSTED',
            'maker_price': maker_limit,
            'best_bid': best_bid,
            'best_ask': best_ask,
            'spread_discount': spread_discount,
            'fee_savings': fee_savings,
            'net_basis_advantage': round(spread_discount + fee_savings, 4)
        }

    def evaluate_fill_probability(self, queue_ahead: int, cycle_volume: int) -> float:
        if queue_ahead <= 0:
            return 1.0
        if cycle_volume <= 0:
            return 0.0
        fill_ratio = cycle_volume / float(queue_ahead + cycle_volume)
        return round(min(1.0, max(0.0, fill_ratio)), 4)
