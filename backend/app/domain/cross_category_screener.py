from typing import Dict, Any, List, Optional
from app.domain._base_screener import CrossCategoryScreener as BaseScreener
from app.domain.domain_registry import DomainRegistry

class CrossCategoryScreener(BaseScreener):
    def __init__(self, registry: Optional[DomainRegistry] = None, fee_rate: float = 0.0, min_edge_threshold: float = 0.03, max_expiry_hours: Optional[float] = None):
        super().__init__(registry=registry, fee_rate=fee_rate, min_edge_threshold=min_edge_threshold)
        self.max_expiry_hours = max_expiry_hours

    def screen_cross_category_board(self, board_candidates: List[Dict[str, Any]], max_expiry_hours: Optional[float] = None) -> Dict[str, Any]:
        h = max_expiry_hours if max_expiry_hours is not None else self.max_expiry_hours
        filtered = [c for c in board_candidates if c.get('hours_to_expiry', 24.0) <= h] if h is not None else board_candidates
        res = super().screen_cross_category_board(filtered)
        h_map = {item.get('contract_id'): item.get('hours_to_expiry', 24.0) for item in board_candidates if 'contract_id' in item}
        lb = res.get('leaderboard', [])
        for cand in lb:
            cid = cand.get('contract_id')
            hours = cand.get('hours_to_expiry', h_map.get(cid, 24.0))
            cand['hours_to_expiry'] = hours
            sharpe = cand.get('sharpe_ratio', 0.0)
            cand['velocity_score'] = round(sharpe * (1.0 + 1.0 / max(0.5, hours)), 4)
            p = cand.get('model_probability') or cand.get('model_prob') or 0.5
            cand['model_probability'] = p
            cand['model_prob'] = p
        lb.sort(key=lambda x: x.get('velocity_score', 0.0), reverse=True)
        res['leaderboard'] = lb
        res['total_evaluated'] = len(board_candidates)
        top = lb[0] if lb else None
        res['top_opportunity'] = top
        res['top_pick'] = top
        res['admissible_count'] = len(lb)
        return res
