from typing import Dict, Any, List, Optional
import math
from app.domain.domain_registry import DomainRegistry

class CrossCategoryScreener:
    def __init__(self, registry: Optional[DomainRegistry] = None, fee_rate: float = 0.0, min_edge_threshold: float = 0.03, max_expiry_hours: Optional[float] = None):
        self.registry = registry or DomainRegistry()
        self.fee_rate = fee_rate
        self.min_edge_threshold = min_edge_threshold
        self.max_expiry_hours = max_expiry_hours

    def screen_cross_category_board(self, board_candidates: List[Dict[str, Any]], max_expiry_hours: Optional[float] = None) -> Dict[str, Any]:
        horizon = max_expiry_hours if max_expiry_hours is not None else self.max_expiry_hours
        admitted = []
        for item in board_candidates:
            hours = item.get('hours_to_expiry', 24.0)
            if horizon is not None and hours > horizon:
                continue

            cat = item.get('category', '').upper()
            adapter = self.registry.get_adapter(cat)
            if not adapter:
                continue

            try:
                spec = item.get('underwriting_spec', {})
                if cat == 'WEATHER': p_model = adapter.underwrite_strike(spec)
                elif cat == 'MACROECONOMIC': p_model = adapter.underwrite_indicator(spec)
                elif cat == 'SPORTS': p_model = adapter.underwrite_game(spec)
                elif cat == 'CRYPTO': p_model = adapter.underwrite_threshold(spec)
                else: continue
            except Exception: continue

            yes_ask = item.get('yes_ask', 1.0)
            yes_bid = item.get('yes_bid', 0.0)
            net_edge_yes = p_model - (yes_ask * (1.0 + self.fee_rate))
            net_edge_no = (1.0 - p_model) - ((1.0 - yes_bid) * (1.0 + self.fee_rate))

            if net_edge_yes >= self.min_edge_threshold and net_edge_yes >= net_edge_no:
                side = 'BUY_YES'; net_edge = net_edge_yes; entry_price = yes_ask
            elif net_edge_no >= self.min_edge_threshold:
                side = 'BUY_NO'; net_edge = net_edge_no; entry_price = 1.0 - yes_bid
            else: continue

            variance = max(0.01, p_model * (1.0 - p_model))
            sharpe = net_edge / math.sqrt(variance)
            velocity_multiplier = 1.0 + (1.0 / max(0.5, hours))
            velocity_score = round(sharpe * velocity_multiplier, 4)

            admitted.append({
                'contract_id': item.get('contract_id'),
                'category': cat,
                'venue': item.get('venue'),
                'side': side,
                'model_prob': round(p_model, 4),
                'entry_price': round(entry_price, 4),
                'net_edge': round(net_edge, 4),
                'sharpe_ratio': round(sharpe, 4),
                'hours_to_expiry': hours,
                'velocity_score': velocity_score
            })

        admitted.sort(key=lambda x: x['velocity_score'], reverse=True)
        return {'total_evaluated': len(board_candidates), 'admissible_count': len(admitted), 'leaderboard': admitted}
