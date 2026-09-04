import math
from typing import Dict, Any, List, Optional
from app.domain.domain_registry import DomainRegistry

class CrossCategoryScreener:
    def __init__(self, registry: Optional[DomainRegistry] = None, min_edge_threshold: float = 0.03, fee_rate: float = 0.0, max_expiry_hours: Optional[float] = None, **kwargs):
        self.registry = registry or DomainRegistry()
        self.min_edge_threshold = min_edge_threshold
        self.fee_rate = fee_rate
        self.max_expiry_hours = max_expiry_hours

    def screen_cross_category_board(self, board_candidates: List[Dict[str, Any]], max_expiry_hours: Optional[float] = None, **kwargs) -> Dict[str, Any]:
        horizon = max_expiry_hours if max_expiry_hours is not None else self.max_expiry_hours
        admitted = []
        for item in board_candidates:
            hours = item.get('hours_to_expiry', 24.0)
            if horizon is not None and hours > horizon:
                continue

            cat = item.get('category', '').upper()
            spec = item.get('underwriting_spec', {})
            fn = getattr(self.registry, 'get_domain', lambda c: None)(cat) or getattr(self.registry, 'get_underwriter', lambda c: None)(cat) or getattr(self.registry, 'domains', {}).get(cat)
            if not callable(fn):
                continue
            try:
                p_model = float(fn(spec))
            except Exception:
                continue

            yes_ask = float(item.get('yes_ask', 1.0))
            yes_bid = float(item.get('yes_bid', 0.0))
            net_edge_yes = p_model - (yes_ask * (1.0 + self.fee_rate))
            net_edge_no = (1.0 - p_model) - ((1.0 - yes_bid) * (1.0 + self.fee_rate))

            if net_edge_yes >= self.min_edge_threshold and net_edge_yes >= net_edge_no:
                side = 'BUY_YES'; net_edge = net_edge_yes; entry_price = yes_ask
            elif net_edge_no >= self.min_edge_threshold:
                side = 'BUY_NO'; net_edge = net_edge_no; entry_price = 1.0 - yes_bid
            else:
                continue

            variance = max(0.01, p_model * (1.0 - p_model))
            sharpe = net_edge / math.sqrt(variance)
            velocity_mult = 1.0 + (1.0 / max(0.5, hours))
            velocity_score = round(sharpe * velocity_mult, 4)

            admitted.append({
                'contract_id': item.get('contract_id'),
                'category': cat,
                'venue': item.get('venue'),
                'side': side,
                'model_probability': round(p_model, 4),
                'model_prob': round(p_model, 4),
                'entry_price': round(entry_price, 4),
                'net_edge': round(net_edge, 4),
                'sharpe_ratio': round(sharpe, 4),
                'hours_to_expiry': hours,
                'velocity_score': velocity_score
            })

        admitted.sort(key=lambda x: x.get('velocity_score', x.get('sharpe_ratio', 0.0)), reverse=True)
        top_opp = admitted[0] if admitted else None
        return {
            'total_evaluated': len(board_candidates),
            'admissible_count': len(admitted),
            'top_opportunity': top_opp,
            'top_pick': top_opp,
            'leaderboard': admitted
        }
