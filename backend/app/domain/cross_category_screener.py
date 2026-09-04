from typing import Dict, Any, List, Optional
import inspect
from app.domain._base_screener import CrossCategoryScreener as BaseScreener
from app.domain.domain_registry import DomainRegistry

class CrossCategoryScreener(BaseScreener):
    def __init__(self, *args, **kwargs):
        self.max_expiry_hours = kwargs.pop('max_expiry_hours', None)
        self.fee_rate = kwargs.pop('fee_rate', 0.0)
        sig = inspect.signature(BaseScreener.__init__)
        base_kw = {k: v for k, v in kwargs.items() if k in sig.parameters}
        super().__init__(*args, **base_kw)

    def screen_cross_category_board(self, board_candidates: List[Dict[str, Any]], *args, **kwargs) -> Dict[str, Any]:
        max_h = kwargs.pop('max_expiry_hours', None)
        h = max_h if max_h is not None else self.max_expiry_hours
        if h is not None:
            filtered = [c for c in board_candidates if float(c.get('hours_to_expiry', 24.0)) <= float(h)]
        else:
            filtered = board_candidates
        sig = inspect.signature(BaseScreener.screen_cross_category_board)
        base_kw = {k: v for k, v in kwargs.items() if k in sig.parameters}
        res = super().screen_cross_category_board(filtered, *args, **base_kw)
        h_map = {c.get('contract_id'): c.get('hours_to_expiry', 24.0) for c in board_candidates if 'contract_id' in c}
        lb = res.get('leaderboard', [])
        for cand in lb:
            cid = cand.get('contract_id')
            hours = float(cand.get('hours_to_expiry', h_map.get(cid, 24.0)))
            cand['hours_to_expiry'] = hours
            sharpe = float(cand.get('sharpe_ratio', cand.get('sharpe', 0.0)))
            vel_mult = 1.0 + (1.0 / max(0.5, hours))
            cand['velocity_score'] = round(sharpe * vel_mult, 4)
            prob = cand.get('model_probability') or cand.get('model_prob') or 0.5
            cand['model_probability'] = prob
            cand['model_prob'] = prob
        lb.sort(key=lambda x: x.get('velocity_score', 0.0), reverse=True)
        res['leaderboard'] = lb
        res['total_evaluated'] = len(board_candidates)
        top = lb[0] if lb else None
        res['top_opportunity'] = top
        res['top_pick'] = top
        res['admissible_count'] = len(lb)
        return res
