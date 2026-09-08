from typing import Dict, Any

class CrossVenueRebalanceManager:
    def __init__(self, target_ratio: float = 0.50, tolerance: float = 0.15):
        self.target_ratio = target_ratio
        self.tolerance = tolerance

    def check_rebalance_needed(self, kalshi_cents: int, polymarket_cents: int) -> Dict[str, Any]:
        total = kalshi_cents + polymarket_cents
        if total <= 0:
            return {'rebalance_needed': False, 'action': 'NONE', 'transfer_cents': 0}
        k_pct = kalshi_cents / total
        deviation = k_pct - self.target_ratio
        if abs(deviation) > self.tolerance:
            target_k = int(round(total * self.target_ratio))
            transfer = abs(kalshi_cents - target_k)
            source = 'KALSHI' if kalshi_cents > target_k else 'POLYMARKET'
            target = 'POLYMARKET' if source == 'KALSHI' else 'KALSHI'
            return {
                'rebalance_needed': True,
                'source_venue': source,
                'target_venue': target,
                'transfer_cents': transfer,
                'current_kalshi_pct': round(k_pct, 4)
            }
        return {
            'rebalance_needed': False,
            'source_venue': None,
            'target_venue': None,
            'transfer_cents': 0,
            'current_kalshi_pct': round(k_pct, 4)
        }
