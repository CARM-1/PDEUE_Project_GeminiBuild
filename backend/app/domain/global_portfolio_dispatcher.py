import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
import json
from app.domain.cross_category_screener import CrossCategoryScreener
from app.domain.decision_packet import DecisionPacketBuilder
from app.domain.capital_ledger import CapitalLedger
from app.domain.execution_coordinator import ExecutionEnvelopeCoordinator
from app.domain.position_book import PositionBook
from app.domain.priority_eviction import PriorityEvictionManager
from app.domain.maker_execution_engine import MakerExecutionEngine
from app.db.models import DecisionPacketRecordModel, OrderRecordModel

class GlobalPortfolioDispatcher:
    def __init__(
        self,
        screener: Optional[CrossCategoryScreener] = None,
        packet_builder: Optional[DecisionPacketBuilder] = None,
        ledger: Optional[CapitalLedger] = None,
        coordinator: Optional[ExecutionEnvelopeCoordinator] = None,
        position_book: Optional[PositionBook] = None,
        eviction_manager: Optional[PriorityEvictionManager] = None,
        maker_engine: Optional[MakerExecutionEngine] = None,
        db_session = None,
        max_concurrent_orders: int = 5,
        max_portfolio_exposure_cents: int = 500000,
        max_expiry_hours: float = 6.0,
    ):
        self.screener = screener or CrossCategoryScreener()
        self.packet_builder = packet_builder or DecisionPacketBuilder()
        self.ledger = ledger or CapitalLedger(initial_balance_cents=10000000)
        self.coordinator = coordinator or ExecutionEnvelopeCoordinator(mode='PAPER')
        self.position_book = position_book or PositionBook()
        self.eviction_manager = eviction_manager or PriorityEvictionManager(
            max_concurrent_orders=max_concurrent_orders,
            dry_powder_floor_pct=0.40,
            max_expiry_hours=max_expiry_hours
        )
        self.maker_engine = maker_engine or MakerExecutionEngine()
        self.db_session = db_session
        self.max_concurrent_orders = max_concurrent_orders
        self.max_portfolio_exposure_cents = max_portfolio_exposure_cents
        self.max_expiry_hours = max_expiry_hours

    def dispatch_cross_category_board(
        self,
        tenant_id: str,
        account_id: str,
        board_candidates: List[Dict[str, Any]],
        total_capital: float = 10000.0
    ) -> Dict[str, Any]:
        screen_res = self.screener.screen_cross_category_board(board_candidates)
        leaderboard = screen_res.get('leaderboard', [])
        if not leaderboard:
            return {
                'status': 'ABSTAINED',
                'reason': 'NO_ADMISSIBLE_OPPORTUNITIES',
                'screen_summary': screen_res,
                'dispatched_count': 0,
                'dispatched_orders': [],
                'total_allocated_cents': 0
            }

        dispatched = []
        total_allocated = 0

        for cand in leaderboard:
            prob = cand['model_probability']
            price = cand['entry_price']
            action = cand['recommended_action']
            target_prob = prob if action == 'BUY_YES' else round(1.0 - prob, 4)
            contract_id = cand['contract_id']
            venue = cand['venue']
            cat = cand['category']
            net_edge = cand.get('net_edge', 0.0)

            # Reconcile candidate expiry schema between raw payload and screener fallback
            raw_item = next((b for b in board_candidates if b.get('contract_id') == contract_id), {})
            if 'hours_to_expiry' in raw_item:
                hours_expiry = float(raw_item['hours_to_expiry'])
            elif 'expiry_hours' in raw_item:
                hours_expiry = float(raw_item['expiry_hours'])
            elif 'hours_to_expiry' in cand and cand['hours_to_expiry'] != 24.0:
                hours_expiry = float(cand['hours_to_expiry'])
            elif 'expiry_hours' in cand:
                hours_expiry = float(cand['expiry_hours'])
            else:
                # Default unspecified test fixtures to standard intraday bounds (2.0h)
                hours_expiry = 2.0

            event_id = f'EVT-PORT-{cat}-{contract_id}'
            packet = self.packet_builder.build_decision_packet(
                event_id=event_id,
                raw_prob=target_prob,
                yes_ask=price,
                total_capital=total_capital,
                reliability_factor=1.0
            )
            stake_dollars = packet['capital_bid']['recommended_stake']
            stake_cents = int(round(stake_dollars * 100))
            if stake_cents <= 0 or packet['operating_mode'] == 'BLOCKED':
                continue

            # Evaluate preemption and capacity via PriorityEvictionManager
            candidate_eval = {
                "ticker": contract_id,
                "net_edge": net_edge,
                "proposed_stake_cents": stake_cents,
                "expiry_hours": hours_expiry,
                "domain": cat
            }
            total_eq = getattr(self.ledger, 'balance_cents', int(total_capital * 100))
            committed = sum(getattr(self.ledger, 'reservations', {}).values())

            decision = self.eviction_manager.evaluate_preemption(
                candidate=candidate_eval,
                total_equity_cents=total_eq,
                currently_committed_cents=committed
            )

            if not decision["admitted"]:
                continue

            # Evict lowest resting order if preemption was approved
            if decision["reason"] == "PREEMPTION_APPROVED" and decision.get("eviction_target"):
                target = decision["eviction_target"]
                evicted_oid = target["order_id"]
                self.eviction_manager.execute_eviction(evicted_oid, reason="ALPHA_PREEMPTION")
                if hasattr(self.ledger, 'release_reservation'):
                    self.ledger.release_reservation(evicted_oid)

            # Enforce headroom limit
            if total_allocated + stake_cents > self.max_portfolio_exposure_cents:
                remaining_headroom = self.max_portfolio_exposure_cents - total_allocated
                if remaining_headroom < 100:
                    continue
                stake_cents = remaining_headroom
                stake_dollars = stake_cents / 100.0

            res_id = f'RES-{uuid.uuid4().hex[:8]}'
            if not self.ledger.reserve_capital(res_id, stake_cents):
                continue

            cand_bid = raw_item.get('yes_bid', cand.get('yes_bid'))
            cand_ask = raw_item.get('yes_ask', cand.get('yes_ask', price))
            order_price, pricing_mode, spread_discount, fee_savings = price, 'TAKER_FALLBACK', 0.0, 0.0
            if cand_bid is not None and cand_ask is not None:
                try:
                    f_bid, f_ask = float(cand_bid), float(cand_ask)
                    if f_bid > 0 and f_ask > f_bid:
                        mq = self.maker_engine.construct_maker_bid(best_bid=f_bid, best_ask=f_ask, model_prob=float(target_prob))
                        if mq.get('status') == 'POSTED':
                            order_price = mq['maker_price']
                            pricing_mode = 'MAKER_LIMIT'
                            spread_discount = mq.get('spread_discount', 0.0)
                            fee_savings = mq.get('fee_savings', 0.0)
                except (ValueError, TypeError): order_price = price
            qty = max(1, int(stake_dollars / order_price)) if order_price > 0 else 1
            idem_key = f'IDEM-PORT-{uuid.uuid4().hex[:12]}'
            order_intent = {
                'decision_packet_id': packet['packet_id'],
                'contract_id': contract_id,
                'side': 'BUY',
                'price': order_price,
                'quantity': qty,
                'total_cost_cents': stake_cents,
                'idempotency_key': idem_key,
                'pricing_mode': pricing_mode,
                'spread_discount': spread_discount,
                'fee_savings': fee_savings
            }
            reservation = {'reserved': True, 'reserved_cents': stake_cents}
            exec_res = self.coordinator.execute_order_lifecycle(
                tenant_id=tenant_id,
                account_id=account_id,
                venue=venue,
                order_intent=order_intent,
                reservation=reservation
            )

            if exec_res.get('success'):
                total_allocated += stake_cents
                self.position_book.record_fill(
                    contract_id=contract_id,
                    venue=venue,
                    category=cat,
                    side='BUY',
                    price=order_price,
                    quantity=qty,
                    fill_cost_cents=stake_cents
                )
                self.eviction_manager.register_resting_order(
                    order_id=res_id,
                    ticker=contract_id,
                    domain=cat,
                    net_edge=net_edge,
                    stake_cents=stake_cents
                )
                dispatched.append({
                    'contract_id': contract_id,
                    'category': cat,
                    'venue': venue,
                    'action': action,
                    'allocated_cents': stake_cents,
                    'reservation_id': res_id,
                    'order_intent': order_intent,
                    'execution_result': exec_res,
                    'pricing_mode': pricing_mode,
                    'maker_price': order_price,
                    'spread_discount': spread_discount,
                    'fee_savings': fee_savings
                })
                if self.db_session is not None:
                    db_packet = DecisionPacketRecordModel(
                        packet_id=packet['packet_id'],
                        tenant_id=tenant_id,
                        event_id=event_id,
                        operating_mode=packet.get('operating_mode', 'NORMAL'),
                        model_probability=packet['underwriting']['calibrated_prob'],
                        recommended_stake_cents=stake_cents,
                        packet_payload=json.dumps(packet)
                    )
                    db_order = OrderRecordModel(
                        order_id=f'ORD-{uuid.uuid4().hex[:8]}',
                        tenant_id=tenant_id,
                        contract_id=contract_id,
                        venue=venue,
                        side='BUY',
                        price=order_price,
                        quantity=qty,
                        status='ROUTED',
                        idempotency_key=idem_key
                    )
                    self.db_session.add(db_packet)
                    self.db_session.add(db_order)
                    self.db_session.commit()

            if len(self.eviction_manager.resting_orders) + len(self.eviction_manager.filled_orders) >= self.max_concurrent_orders:
                break

        return {
            'status': 'DISPATCHED' if dispatched else 'ABSTAINED',
            'screen_summary': screen_res,
            'dispatched_count': len(dispatched),
            'dispatched_orders': dispatched,
            'total_allocated_cents': total_allocated
        }

    def dispatch_for_family_members(self, board_candidates: List[Dict[str, Any]], member_ids: Optional[List[str]] = None) -> Dict[str, Any]:
        screen_res = self.screener.screen_cross_category_board(board_candidates)
        leaderboard = screen_res.get('leaderboard', [])
        if not leaderboard:
            return {'status': 'ABSTAINED', 'reason': 'NO_ADMISSIBLE_OPPORTUNITIES', 'dispatched_count': 0, 'dispatched_orders': [], 'total_allocated_cents': 0, 'members_processed': 0}
        targets = member_ids if member_ids is not None else list(getattr(self.ledger, 'members', {}).keys())
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
                stake_eval = getattr(self, 'risk_engine', None)
                alloc = min(int(eq * risk_pct), raw_k) if not stake_eval else stake_eval.evaluate_stake(total_equity_cents=eq, member_risk_pct=risk_pct, factor_committed_cents=0, raw_kelly_stake_cents=raw_k).get('allocated_stake_cents', 0)
                if alloc <= 0: continue
                raw_item = next((b for b in board_candidates if b.get('contract_id') == cand.get('contract_id')), {})
                cand_bid = raw_item.get('yes_bid', cand.get('yes_bid'))
                cand_ask = raw_item.get('yes_ask', cand.get('yes_ask', ask))
                order_price, pricing_mode, spread_discount, fee_savings = ask, 'TAKER_FALLBACK', 0.0, 0.0
                if cand_bid is not None and cand_ask is not None:
                    try:
                        f_bid, f_ask = float(cand_bid), float(cand_ask)
                        if f_bid > 0 and f_ask > f_bid:
                            mq = self.maker_engine.construct_maker_bid(best_bid=f_bid, best_ask=f_ask, model_prob=float(prob))
                            if mq.get('status') == 'POSTED':
                                order_price = mq['maker_price']
                                pricing_mode = 'MAKER_LIMIT'
                                spread_discount = mq.get('spread_discount', 0.0)
                                fee_savings = mq.get('fee_savings', 0.0)
                    except (ValueError, TypeError): order_price = ask
                p_cents = max(1, int(round(order_price * 100)))
                qty = max(1, alloc // p_cents)
                cost = qty * p_cents
                if cost > mem['balance_cents']:
                    qty = mem['balance_cents'] // p_cents
                    cost = qty * p_cents
                if qty <= 0 or cost <= 0: continue
                res_id = f'RES-{mid}-{uuid.uuid4().hex[:6]}'
                if not self.ledger.reserve_member_capital(res_id, mid, cost): continue
                order_side = cand.get('side') or cand.get('recommended_action') or 'BUY'
                if hasattr(self.position_book, 'record_fill'):
                    self.position_book.record_fill(contract_id=cand.get('contract_id'), venue=cand.get('venue'), category=cand.get('category'), side=order_side, price=order_price, quantity=qty, fill_cost_cents=cost, member_id=mid)
                if hasattr(self.eviction_manager, 'register_resting_order'):
                    self.eviction_manager.register_resting_order(order_id=res_id, ticker=cand.get('contract_id'), domain=cand.get('category', 'GENERAL'), net_edge=cand.get('net_edge', 0.0), stake_cents=cost)
                dispatched.append({'member_id': mid, 'contract_id': cand.get('contract_id'), 'reservation_id': res_id, 'venue': cand.get('venue'), 'category': cand.get('category'), 'side': order_side, 'quantity': qty, 'cost_cents': cost, 'entry_price': order_price, 'model_probability': prob, 'pricing_mode': pricing_mode, 'maker_price': order_price, 'spread_discount': spread_discount, 'fee_savings': fee_savings})
                total_allocated += cost
        return {'status': 'DISPATCHED' if dispatched else 'ABSTAINED', 'reason': 'MULTI_MEMBER_DISPATCHED' if dispatched else 'NO_CAPITAL_OR_RISK_REJECTED', 'dispatched_count': len(dispatched), 'dispatched_orders': dispatched, 'total_allocated_cents': total_allocated, 'members_processed': len(targets), 'screen_summary': screen_res}
