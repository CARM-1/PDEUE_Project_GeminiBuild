from typing import Dict, Any

class PositionExitManager:
    """B7-EXE Dynamic Early-Harvest & Time-Decay Profit Liquidation Engine."""
    def __init__(self, base_hurdle: float = 0.85, min_hurdle: float = 0.60, fee_rate: float = 0.01):
        self.base_hurdle = base_hurdle
        self.min_hurdle = min_hurdle
        self.fee_rate = fee_rate

    def compute_dynamic_hurdle(self, elapsed_hours: float, total_hours: float) -> float:
        if total_hours <= 0:
            return self.min_hurdle
        decay_ratio = min(1.0, max(0.0, elapsed_hours / total_hours))
        hurdle_delta = self.base_hurdle - self.min_hurdle
        calculated = self.base_hurdle - (hurdle_delta * decay_ratio)
        return round(max(self.min_hurdle, min(self.base_hurdle, calculated)), 4)

    def evaluate_exit(
        self,
        entry_price: float,
        current_bid: float,
        elapsed_hours: float,
        total_hours: float
    ) -> Dict[str, Any]:
        dynamic_hurdle = self.compute_dynamic_hurdle(elapsed_hours, total_hours)
        net_liquidation_price = current_bid * (1.0 - self.fee_rate)
        max_potential_profit = max(0.01, 1.0 - entry_price)
        net_unrealized_profit = net_liquidation_price - entry_price
        profit_capture_ratio = max(0.0, net_unrealized_profit / max_potential_profit)

        should_exit = (net_unrealized_profit > 0.0) and (profit_capture_ratio >= dynamic_hurdle)
        reason = 'DYNAMIC_PROFIT_HARVEST' if should_exit else 'HOLD_TO_MATURITY'

        return {
            'should_exit': should_exit,
            'reason': reason,
            'dynamic_hurdle': dynamic_hurdle,
            'profit_capture_ratio': round(profit_capture_ratio, 4),
            'net_liquidation_price': round(net_liquidation_price, 4),
            'net_unrealized_profit': round(net_unrealized_profit, 4)
        }
