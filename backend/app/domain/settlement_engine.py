from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
import uuid
from app.domain.position_book import PositionBook
from app.domain.capital_ledger import CapitalLedger

class ResolutionEngine:
    def resolve_contract(self, category: str, spec: Dict[str, Any], observation: Dict[str, Any]) -> str:
        cat = category.upper()
        if cat == 'WEATHER':
            return 'YES' if float(observation.get('observed_temp_c', 0.0)) >= float(spec.get('strike_temp_c', 0.0)) else 'NO'
        elif cat == 'MACROECONOMIC':
            return 'YES' if float(observation.get('released_value', 0.0)) >= float(spec.get('threshold', 0.0)) else 'NO'
        elif cat == 'SPORTS':
            return 'YES' if float(observation.get('final_margin', 0.0)) > float(spec.get('target_spread', 0.0)) else 'NO'
        elif cat == 'CRYPTO':
            return 'YES' if float(observation.get('settlement_price', 0.0)) >= float(spec.get('strike_price', 0.0)) else 'NO'
        return 'VOID'

class PositionExitManager:
    def __init__(self, exit_profit_threshold: float = 0.80, fee_rate: float = 0.01):
        self.exit_profit_threshold = exit_profit_threshold
        self.fee_rate = fee_rate

    def evaluate_early_exit(self, position: Dict[str, Any], resting_bid: float, spread: float = 0.0) -> Dict[str, Any]:
        qty = position.get('quantity', 0)
        cost = position.get('total_cost_cents', 0)
        if qty <= 0 or cost <= 0:
            return {'action': 'HOLD_TO_MATURITY', 'reason': 'INVALID_POSITION'}
        max_profit = (qty * 100) - cost
        if max_profit <= 0:
            return {'action': 'HOLD_TO_MATURITY', 'reason': 'NO_POTENTIAL_MAX_PROFIT'}
        gross = int(round(qty * resting_bid * 100))
        fee = int(round(gross * self.fee_rate))
        spread_loss = int(round(qty * spread * 100))
        net_proceeds = gross - (fee + spread_loss)
        net_profit = net_proceeds - cost
        ratio = round(net_profit / max_profit, 4) if max_profit > 0 else 0.0
        if net_profit > 0 and ratio >= self.exit_profit_threshold:
            return {'action': 'EXIT_EARLY', 'net_proceeds_cents': net_proceeds, 'net_profit_cents': net_profit, 'profit_capture_ratio': ratio, 'target_threshold': self.exit_profit_threshold}
        return {'action': 'HOLD_TO_MATURITY', 'net_proceeds_cents': net_proceeds, 'net_profit_cents': net_profit, 'profit_capture_ratio': ratio, 'reason': 'PROFIT_BELOW_EXIT_HURDLE'}

class SettlementReconciler:
    def __init__(self, position_book: Optional[PositionBook] = None, ledger: Optional[CapitalLedger] = None, resolution_engine: Optional[ResolutionEngine] = None, exit_manager: Optional[PositionExitManager] = None):
        self.position_book = position_book or PositionBook()
        self.ledger = ledger or CapitalLedger()
        self.resolution_engine = resolution_engine or ResolutionEngine()
        self.exit_manager = exit_manager or PositionExitManager()
        self.settlement_history: List[Dict[str, Any]] = []

    def calculate_transaction_waterfall(self, profit_cents: int) -> Dict[str, int]:
        if profit_cents <= 0:
            return {'member_reinvest_cents': 0, 'central_family_pool_cents': 0, 'founder_pool_cents': 0}
        founder = int(round(profit_cents * 0.03))
        family = int(round(profit_cents * 0.10))
        member = profit_cents - (founder + family)
        return {'member_reinvest_cents': member, 'central_family_pool_cents': family, 'founder_pool_cents': founder}

    def settle_contract(self, contract_id: str, outcome: str, member_id: Optional[str] = None) -> Dict[str, Any]:
        outcome_u = outcome.upper()
        if outcome_u not in {'YES', 'NO', 'VOID'}:
            raise ValueError(f'Invalid outcome: {outcome}')
        pos_key = contract_id
        if pos_key not in self.position_book.positions:
            matches = [k for k, v in self.position_book.positions.items() if v.get('contract_id') == contract_id and (member_id is None or v.get('member_id') == member_id)]
            if matches:
                pos_key = matches[0]
            else:
                return {'status': 'ABSTAINED', 'reason': 'POSITION_NOT_FOUND', 'contract_id': contract_id}
        pos = self.position_book.positions[pos_key]
        qty, cost = pos['quantity'], pos['total_cost_cents']
        mid = pos.get('member_id', 'DEFAULT')
        payout = qty * 100 if outcome_u == 'YES' else (0 if outcome_u == 'NO' else cost)
        closed = self.position_book.close_position(pos_key, outcome_u, payout)
        pnl = closed['realized_pnl_cents']
        wf = self.calculate_transaction_waterfall(pnl)
        if self.ledger:
            if pnl > 0:
                self.ledger.credit_member_balance(mid, cost + wf['member_reinvest_cents'])
                self.ledger.credit_central_family_pool(wf['central_family_pool_cents'])
                self.ledger.credit_founder_pool(wf['founder_pool_cents'])
                if mid in self.ledger.members:
                    self.ledger.members[mid]['lifetime_profit_cents'] += pnl
            else:
                self.ledger.credit_member_balance(mid, payout)
        event = {'settlement_id': f'SETTLE-{uuid.uuid4().hex[:8]}', 'contract_id': pos['contract_id'], 'position_id': pos_key, 'member_id': mid, 'lifecycle': 'HOLD_TO_MATURITY', 'outcome': outcome_u, 'quantity': qty, 'cost_cents': cost, 'payout_cents': payout, 'realized_pnl_cents': pnl, 'waterfall': wf, 'timestamp': datetime.now(timezone.utc).isoformat()}
        self.settlement_history.append(event)
        return {'status': 'SETTLED', 'event': event}

    def liquidate_early_position(self, contract_id: str, resting_bid: float, spread: float = 0.0, member_id: Optional[str] = None) -> Dict[str, Any]:
        pos_key = contract_id
        if pos_key not in self.position_book.positions:
            matches = [k for k, v in self.position_book.positions.items() if v.get('contract_id') == contract_id and (member_id is None or v.get('member_id') == member_id)]
            if matches:
                pos_key = matches[0]
            else:
                return {'status': 'ABSTAINED', 'reason': 'POSITION_NOT_FOUND', 'contract_id': contract_id}
        pos = self.position_book.positions[pos_key]
        eval_res = self.exit_manager.evaluate_early_exit(pos, resting_bid, spread)
        if eval_res['action'] != 'EXIT_EARLY':
            return {'status': 'ABSTAINED', 'reason': eval_res.get('reason', 'EXIT_CONDITIONS_NOT_MET'), 'eval': eval_res}
        net_proceeds = eval_res['net_proceeds_cents']
        qty, cost = pos['quantity'], pos['total_cost_cents']
        mid = pos.get('member_id', 'DEFAULT')
        closed = self.position_book.close_position(pos_key, 'EARLY_EXIT', net_proceeds)
        pnl = closed['realized_pnl_cents']
        wf = self.calculate_transaction_waterfall(pnl)
        if self.ledger:
            if pnl > 0:
                self.ledger.credit_member_balance(mid, cost + wf['member_reinvest_cents'])
                self.ledger.credit_central_family_pool(wf['central_family_pool_cents'])
                self.ledger.credit_founder_pool(wf['founder_pool_cents'])
                if mid in self.ledger.members:
                    self.ledger.members[mid]['lifetime_profit_cents'] += pnl
            else:
                self.ledger.credit_member_balance(mid, net_proceeds)
        event = {'settlement_id': f'EARLY-{uuid.uuid4().hex[:8]}', 'contract_id': pos['contract_id'], 'position_id': pos_key, 'member_id': mid, 'lifecycle': 'EARLY_EXIT_HARVEST', 'resting_bid': resting_bid, 'spread': spread, 'quantity': qty, 'cost_cents': cost, 'payout_cents': net_proceeds, 'realized_pnl_cents': pnl, 'profit_capture_ratio': eval_res['profit_capture_ratio'], 'waterfall': wf, 'timestamp': datetime.now(timezone.utc).isoformat()}
        self.settlement_history.append(event)
        return {'status': 'LIQUIDATED_EARLY', 'event': event}
