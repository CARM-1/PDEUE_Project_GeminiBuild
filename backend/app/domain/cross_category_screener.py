from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
import math
from app.domain.domain_registry import DomainRegistry

class CrossCategoryScreener:
    def __init__(self, registry: Optional[DomainRegistry] = None, min_edge_threshold: float = 0.03, default_fee_rate: float = 0.01):
        self.registry = registry or DomainRegistry()
        self.min_edge_threshold = min_edge_threshold
        self.default_fee_rate = default_fee_rate
    def screen_cross_category_board(self, board_candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
        evaluated = []
        category_counts: Dict[str, int] = {}
        venue_counts: Dict[str, int] = {}
        for item in board_candidates:
            cat = item.get('category', '').upper()
            venue = item.get('venue', 'KALSHI').upper()
            contract_id = item.get('contract_id', 'UNKNOWN')
            fee_rate = float(item.get('fee_rate', 0.00 if venue == 'POLYMARKET' else self.default_fee_rate))
            category_counts[cat] = category_counts.get(cat, 0) + 1
            venue_counts[venue] = venue_counts.get(venue, 0) + 1
            if not self.registry.has_domain(cat):
                continue
            prob_res = self.registry.calculate_probability(cat, item.get('underwriting_spec', {}))
            p_model = prob_res['model_probability']
            yes_bid = float(item.get('yes_bid', 0.0))
            yes_ask = float(item.get('yes_ask', 1.0))
            cost_yes = round(yes_ask * (1.0 + fee_rate), 4)
            net_edge_yes = round(p_model - cost_yes, 4)
            cost_no = round((1.0 - yes_bid) * (1.0 + fee_rate), 4)
            net_edge_no = round((1.0 - p_model) - cost_no, 4)
            if net_edge_yes >= net_edge_no and net_edge_yes >= self.min_edge_threshold:
                action, best_edge, entry_price, target_prob = 'BUY_YES', net_edge_yes, yes_ask, p_model
            elif net_edge_no > net_edge_yes and net_edge_no >= self.min_edge_threshold:
                action, best_edge, entry_price, target_prob = 'BUY_NO', net_edge_no, round(1.0 - yes_bid, 4), round(1.0 - p_model, 4)
            else:
                continue
            variance = max(0.0001, target_prob * (1.0 - target_prob))
            sharpe = round(best_edge / math.sqrt(variance), 4)
            evaluated.append({'contract_id': contract_id, 'category': cat, 'venue': venue, 'model_probability': p_model, 'yes_bid': yes_bid, 'yes_ask': yes_ask, 'recommended_action': action, 'net_edge': best_edge, 'entry_price': entry_price, 'sharpe_ratio': sharpe})
        evaluated.sort(key=lambda x: (x['net_edge'], x['sharpe_ratio']), reverse=True)
        for idx, cand in enumerate(evaluated, 1): cand['global_rank'] = idx
        return {'screened_at': datetime.now(timezone.utc).isoformat(), 'total_evaluated': len(board_candidates), 'admissible_count': len(evaluated), 'category_breakdown': category_counts, 'venue_breakdown': venue_counts, 'leaderboard': evaluated, 'top_opportunity': evaluated[0] if evaluated else None}
