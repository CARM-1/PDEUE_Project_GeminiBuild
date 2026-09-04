from typing import Dict, Any, List, Optional
import uuid
from app.domain.cross_category_screener import CrossCategoryScreener
from app.domain.two_tier_risk import TwoTierRiskEnvelope
from app.domain.capital_ledger import CapitalLedger
from app.domain.position_book import PositionBook

class GlobalPortfolioDispatcher:
    def __init__(self, screener: Optional[CrossCategoryScreener] = None, risk_engine: Optional[TwoTierRiskEnvelope] = None, ledger: Optional[CapitalLedger] = None, position_book: Optional[PositionBook] = None, coordinator: Optional[Any] = None, db_session: Optional[Any] = None, max_portfolio_exposure_cents: int = 1000000, max_concurrent_orders: int = 5, **kwargs):
        self.screener = screener or CrossCategoryScreener()
        self.risk_engine = risk_engine or TwoTierRiskEnvelope()
        self.ledger = ledger or CapitalLedger()
        self.position_book = position_book or PositionBook()
        self.coordinator = coordinator
        self.db_session = db_session
        self.max_portfolio_exposure_cents = max_portfolio_exposure_cents
        self.max_concurrent_orders = max_concurrent_orders

    def dispatch_cross_category_board(self, tenant_id: str, account_id: str, board_candidates: List[Dict[str, Any]], total_capital: float = 10000.0) -> Dict[str, Any]:
        screen_res = self.screener.screen_cross_category_board(board_candidates)
        leaderboard = screen_res.get('leaderboard', [])
        if not leaderboard:
            return {'status': 'ABSTAINED', 'reason': 'NO_ADMISSIBLE_OPPORTUNITIES', 'screen_summary': screen_res, 'dispatched_count': 0, 'dispatched_orders': [], 'total_allocated_cents': 0}
        dispatched = []
        total_allocated = 0
        total_cap_cents = int(total_capital * 100)
        for cand in leaderboard[:self.max_concurrent_orders]:
            prob = cand.get('model_probability') or cand.get('model_prob', 0.5)
            ask = cand.get('entry_price', 0.50)
            edge = cand.get('net_edge', 0.05)
            variance = max(0.01, prob * (1.0 - prob))
            raw_stake = int(total_cap_cents * min(0.10, max(0.01, edge / variance * 0.25)))
            rem = max(0, self.max_portfolio_exposure_cents - total_allocated)
            if rem <= 0: break
            stake = min(raw_stake, rem)
            if stake <= 0: continue
            price_cents = max(1, int(round(ask * 100)))
            qty = max(1, stake // price_cents)
            cost = qty * price_cents
            if cost > rem:
                qty = rem // price_cents
                cost = qty * price_cents
            if qty <= 0 or cost <= 0: continue
            res_id = f'RES-{account_id}-{uuid.uuid4().hex[:6]}'
            self.ledger.reserve_capital(res_id, cost, account_id=account_id)
            self.position_book.record_fill(contract_id=cand.get('contract_id'), venue=cand.get('venue'), category=cand.get('category'), side=cand.get('side'), price=ask, quantity=qty, fill_cost_cents=cost, member_id=account_id)
            dispatched.append({'contract_id': cand.get('contract_id'), 'account_id': account_id, 'reservation_id': res_id, 'side': cand.get('side'), 'entry_price': ask, 'quantity': qty, 'allocated_cents': cost, 'model_probability': prob})
            total_allocated += cost
        return {'status': 'DISPATCHED' if dispatched else 'ABSTAINED', 'reason': 'EXECUTION_DISPATCHED' if dispatched else 'EXPOSURE_OR_CAPITAL_LIMIT', 'dispatched_count': len(dispatched), 'dispatched_orders': dispatched, 'total_allocated_cents': total_allocated, 'screen_summary': screen_res}

    def dispatch_for_family_members(self, board_candidates: List[Dict[str, Any]], member_ids: Optional[List[str]] = None) -> Dict[str, Any]:
        screen_res = self.screener.screen_cross_category_board(board_candidates)
        leaderboard = screen_res.get('leaderboard', [])
        if not leaderboard:
            return {'status': 'ABSTAINED', 'reason': 'NO_ADMISSIBLE_OPPORTUNITIES', 'dispatched_count': 0, 'dispatched_orders': [], 'total_allocated_cents': 0, 'members_processed': 0}
        targets = member_ids if member_ids is not None else list(self.ledger.members.keys())
        if not targets:
            return {'status': 'ABSTAINED', 'reason': 'NO_REGISTERED_MEMBERS', 'dispatched_count': 0, 'dispatched_orders': [], 'total_allocated_cents': 0, 'members_processed': 0}
        dispatched = []
        total_allocated = 0
        for mid in targets:
            mem = self.ledger.members.get(mid)
            if not mem or mem.get('balance_cents', 0) <= 0: continue
            eq = mem['balance_cents']
            risk_pct = mem.get('max_risk_pct', 0.05)
            for cand in leaderboard[:self.max_concurrent_orders]:
                prob = cand.get('model_probability') or cand.get('model_prob', 0.5)
                ask = cand.get('entry_price', 0.50)
                b_odds = (1.0 - ask) / max(0.01, ask)
                raw_k = int(eq * max(0.0, (b_odds * prob - (1.0 - prob)) / max(0.01, b_odds)))
                stake_eval = self.risk_engine.evaluate_stake(total_equity_cents=eq, member_risk_pct=risk_pct, factor_committed_cents=0, raw_kelly_stake_cents=raw_k)
                if not stake_eval.get('admitted') or stake_eval.get('allocated_stake_cents', 0) <= 0: continue
                alloc = stake_eval['allocated_stake_cents']
                p_cents = max(1, int(round(ask * 100)))
                qty = max(1, alloc // p_cents)
                cost = qty * p_cents
                if cost > mem['balance_cents']:
                    qty = mem['balance_cents'] // p_cents
                    cost = qty * p_cents
                if qty <= 0 or cost <= 0: continue
                res_id = f'RES-{mid}-{uuid.uuid4().hex[:6]}'
                if not self.ledger.reserve_member_capital(res_id, mid, cost): continue
                self.position_book.record_fill(contract_id=cand.get('contract_id'), venue=cand.get('venue'), category=cand.get('category'), side=cand.get('side'), price=ask, quantity=qty, fill_cost_cents=cost, member_id=mid)
                dispatched.append({'member_id': mid, 'contract_id': cand.get('contract_id'), 'reservation_id': res_id, 'venue': cand.get('venue'), 'category': cand.get('category'), 'side': cand.get('side'), 'quantity': qty, 'cost_cents': cost, 'entry_price': ask, 'model_probability': prob})
                total_allocated += cost
        return {'status': 'DISPATCHED' if dispatched else 'ABSTAINED', 'reason': 'MULTI_MEMBER_DISPATCHED' if dispatched else 'NO_CAPITAL_OR_RISK_REJECTED', 'dispatched_count': len(dispatched), 'dispatched_orders': dispatched, 'total_allocated_cents': total_allocated, 'members_processed': len(targets), 'screen_summary': screen_res}
