from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
import uuid
from app.domain.position_book import PositionBook
from app.domain.capital_ledger import CapitalLedger

class ResolutionEngine:
    def resolve_contract(self, category: str, spec: Dict[str, Any], observation: Dict[str, Any]) -> str:
        cat = category.upper()
        if cat == 'WEATHER':
            strike = float(spec.get('strike_temp_c', 0.0))
            observed = float(observation.get('observed_temp_c', 0.0))
            return 'YES' if observed >= strike else 'NO'
        elif cat == 'MACROECONOMIC':
            threshold = float(spec.get('threshold', 0.0))
            released = float(observation.get('released_value', 0.0))
            return 'YES' if released >= threshold else 'NO'
        elif cat == 'SPORTS':
            target_spread = float(spec.get('target_spread', 0.0))
            final_margin = float(observation.get('final_margin', 0.0))
            return 'YES' if final_margin > target_spread else 'NO'
        elif cat == 'CRYPTO':
            strike_price = float(spec.get('strike_price', 0.0))
            settlement_price = float(observation.get('settlement_price', 0.0))
            return 'YES' if settlement_price >= strike_price else 'NO'
        return 'VOID'

class PositionExitManager:
    def __init__(self, exit_profit_threshold: float = 0.80, fee_rate: float = 0.01):
        self.exit_profit_threshold = exit_profit_threshold
        self.fee_rate = fee_rate

    def evaluate_early_exit(self, position: Dict[str, Any], resting_bid: float, spread: float = 0.0) -> Dict[str, Any]:
        qty = position.get('quantity', 0)
        cost_cents = position.get('total_cost_cents', 0)
        if qty <= 0 or cost_cents <= 0:
            return {'action': 'HOLD_TO_MATURITY', 'reason': 'INVALID_POSITION'}

        max_payout_cents = qty * 100
        max_profit_cents = max_payout_cents - cost_cents
        if max_profit_cents <= 0:
            return {'action': 'HOLD_TO_MATURITY', 'reason': 'NO_POTENTIAL_MAX_PROFIT'}

        gross_proceeds_cents = int(round(qty * resting_bid * 100))
        exit_fee_cents = int(round(gross_proceeds_cents * self.fee_rate))
        spread_cents = int(round(qty * spread * 100))
        net_proceeds_cents = gross_proceeds_cents - (exit_fee_cents + spread_cents)
        net_profit_cents = net_proceeds_cents - cost_cents
        profit_capture_ratio = round(net_profit_cents / max_profit_cents, 4) if max_profit_cents > 0 else 0.0

        if net_profit_cents > 0 and profit_capture_ratio >= self.exit_profit_threshold:
            return {'action': 'EXIT_EARLY', 'net_proceeds_cents': net_proceeds_cents, 'net_profit_cents': net_profit_cents, 'profit_capture_ratio': profit_capture_ratio, 'target_threshold': self.exit_profit_threshold}

        return {'action': 'HOLD_TO_MATURITY', 'net_proceeds_cents': net_proceeds_cents, 'net_profit_cents': net_profit_cents, 'profit_capture_ratio': profit_capture_ratio, 'target_threshold': self.exit_profit_threshold, 'reason': 'PROFIT_BELOW_EXIT_HURDLE'}

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
        founder_cut = int(round(profit_cents * 0.03))
        family_cut = int(round(profit_cents * 0.10))
        member_cut = profit_cents - (founder_cut + family_cut)
        return {'member_reinvest_cents': member_cut, 'central_family_pool_cents': family_cut, 'founder_pool_cents': founder_cut}
    def settle_contract(self, contract_id: str, outcome: str) -> Dict[str, Any]:
        outcome_upper = outcome.upper()
        if outcome_upper not in {'YES', 'NO', 'VOID'}:
            raise ValueError(f'Invalid settlement outcome: {outcome}')
        if contract_id not in self.position_book.positions:
            return {'status': 'ABSTAINED', 'reason': 'POSITION_NOT_FOUND', 'contract_id': contract_id}
        pos = self.position_book.positions[contract_id]
        qty = pos['quantity']
        cost_cents = pos['total_cost_cents']
        member_id = pos.get('member_id', 'DEFAULT')
        payout_cents = qty * 100 if outcome_upper == 'YES' else (0 if outcome_upper == 'NO' else cost_cents)
        closed = self.position_book.close_position(contract_id, outcome_upper, payout_cents)
        realized_pnl = closed['realized_pnl_cents']
        waterfall = self.calculate_transaction_waterfall(realized_pnl)
        if self.ledger:
            if realized_pnl > 0:
                self.ledger.credit_member_balance(member_id, cost_cents + waterfall['member_reinvest_cents'])
                self.ledger.credit_central_family_pool(waterfall['central_family_pool_cents'])
                self.ledger.credit_founder_pool(waterfall['founder_pool_cents'])
                if member_id in self.ledger.members:
                    self.ledger.members[member_id]['lifetime_profit_cents'] += realized_pnl
            else:
                self.ledger.credit_member_balance(member_id, payout_cents)
        settle_event = {'settlement_id': f'SETTLE-{uuid.uuid4().hex[:8]}', 'contract_id': contract_id, 'member_id': member_id, 'lifecycle': 'HOLD_TO_MATURITY', 'outcome': outcome_upper, 'quantity': qty, 'cost_cents': cost_cents, 'payout_cents': payout_cents, 'realized_pnl_cents': realized_pnl, 'waterfall': waterfall, 'timestamp': datetime.now(timezone.utc).isoformat()}
        self.settlement_history.append(settle_event)
        return {'status': 'SETTLED', 'event': settle_event}
    def liquidate_early_position(self, contract_id: str, resting_bid: float, spread: float = 0.0) -> Dict[str, Any]:
        if contract_id not in self.position_book.positions:
            return {'status': 'ABSTAINED', 'reason': 'POSITION_NOT_FOUND', 'contract_id': contract_id}
        pos = self.position_book.positions[contract_id]
        eval_res = self.exit_manager.evaluate_early_exit(pos, resting_bid, spread)
        if eval_res['action'] != 'EXIT_EARLY':
            return {'status': 'ABSTAINED', 'reason': eval_res.get('reason', 'EXIT_CONDITIONS_NOT_MET'), 'eval': eval_res}
        net_proceeds = eval_res['net_proceeds_cents']
        qty = pos['quantity']
        cost_cents = pos['total_cost_cents']
        member_id = pos.get('member_id', 'DEFAULT')
        closed = self.position_book.close_position(contract_id, 'EARLY_EXIT', net_proceeds)
        realized_pnl = closed['realized_pnl_cents']
        waterfall = self.calculate_transaction_waterfall(realized_pnl)
        if self.ledger:
            if realized_pnl > 0:
                self.ledger.credit_member_balance(member_id, cost_cents + waterfall['member_reinvest_cents'])
                self.ledger.credit_central_family_pool(waterfall['central_family_pool_cents'])
                self.ledger.credit_founder_pool(waterfall['founder_pool_cents'])
                if member_id in self.ledger.members:
                    self.ledger.members[member_id]['lifetime_profit_cents'] += realized_pnl
            else:
                self.ledger.credit_member_balance(member_id, net_proceeds)
        exit_event = {'settlement_id': f'EARLY-{uuid.uuid4().hex[:8]}', 'contract_id': contract_id, 'member_id': member_id, 'lifecycle': 'EARLY_EXIT_HARVEST', 'resting_bid': resting_bid, 'spread': spread, 'quantity': qty, 'cost_cents': cost_cents, 'payout_cents': net_proceeds, 'realized_pnl_cents': realized_pnl, 'profit_capture_ratio': eval_res['profit_capture_ratio'], 'waterfall': waterfall, 'timestamp': datetime.now(timezone.utc).isoformat()}
        self.settlement_history.append(exit_event)
        return {'status': 'LIQUIDATED_EARLY', 'event': exit_event}
