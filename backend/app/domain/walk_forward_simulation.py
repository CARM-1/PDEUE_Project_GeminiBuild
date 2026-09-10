from typing import Dict, Any, List
import math
from app.domain.position_exit_manager import PositionExitManager
from app.domain.maker_execution_engine import MakerExecutionEngine

class WalkForwardBenchmark:
    def __init__(self, initial_capital_cents: int = 10000):
        self.initial_capital_cents = initial_capital_cents
        self.exit_mgr = PositionExitManager(base_hurdle=0.85, min_hurdle=0.60, fee_rate=0.01)
        self.maker_eng = MakerExecutionEngine(maker_fee_rate=0.0, taker_fee_rate=0.01)

    def run_simulation(self, tick_series: List[Dict[str, Any]]) -> Dict[str, Any]:
        cap_a = self.initial_capital_cents
        cap_b = self.initial_capital_cents
        cap_c = self.initial_capital_cents
        trades_count = len(tick_series)
        c_harvested_early = 0
        c_held_to_maturity = 0
        wins_c = 0
        trade_returns_c: List[float] = []
        peak_equity_c = cap_c
        max_drawdown_pct = 0.0
        total_friction_cents = 0

        # Strategy D Execution Trackers (Inside Maker + Dynamic Bounds)
        cap_d = self.initial_capital_cents
        peak_equity_d = cap_d
        max_dd_d_pct = 0.0
        trade_returns_d: List[float] = []
        d_harvested_early = 0
        d_held_to_maturity = 0
        d_friction_cents = 0
        wins_d = 0

        for tick in tick_series:
            # Shared contract fields for Baselines A, B, and C
            entry_ask = tick.get('entry_ask', tick.get('yes_ask', 0.50))
            final_payout = tick.get('final_payout', 1.0 if tick.get('outcome', 1) == 1 else 0.0)
            peak_mid = tick.get('peak_midpoint', entry_ask)
            fee_rate = tick.get('fee_rate', 0.01)

            # --- Baseline A, B, C Logic ---
            stake_c = min(int(cap_c * 0.05), 500)
            if stake_c > 0 and entry_ask > 0:
                contracts_c = stake_c / entry_ask
                fee_cents_c = int(stake_c * fee_rate)

                # Baseline A (Hold to Maturity)
                cap_a += int((contracts_c * final_payout) - stake_c - fee_cents_c)

                # Baseline B (Peak Midpoint Exit)
                cap_b += int((contracts_c * peak_mid) - stake_c)

                # Baseline C (Hybrid Static Hurdle 80%)
                target_exit = entry_ask + (1.0 - entry_ask) * 0.80
                if peak_mid >= target_exit:
                    c_harvested_early += 1
                    effective_exit = peak_mid * 0.985
                    slippage_cents = int((contracts_c * peak_mid) - (contracts_c * effective_exit))
                    payout_cents = int(contracts_c * effective_exit)
                    pnl_c = payout_cents - stake_c - fee_cents_c
                    total_friction_cents += fee_cents_c + slippage_cents
                else:
                    c_held_to_maturity += 1
                    payout_cents = int(contracts_c * final_payout)
                    pnl_c = payout_cents - stake_c - fee_cents_c
                    total_friction_cents += fee_cents_c

                cap_c += pnl_c
                if pnl_c > 0:
                    wins_c += 1
                ret_c = pnl_c / stake_c
                trade_returns_c.append(ret_c)

                if cap_c > peak_equity_c:
                    peak_equity_c = cap_c
                dd_c = ((peak_equity_c - cap_c) / peak_equity_c) * 100.0 if peak_equity_c > 0 else 0.0
                if dd_c > max_drawdown_pct:
                    max_drawdown_pct = dd_c

            # --- Strategy D Logic (Exact Certified Replay Specs) ---
            p_model = tick.get("p_model", 0.5)
            ask = tick.get("yes_ask", 0.5)
            bid = tick.get("yes_bid", max(0.01, ask - 0.06))
            outcome = tick.get("outcome", 1)
            total_h = tick.get("total_hours", 12.0)
            elapsed_h = tick.get("elapsed_hours", 8.0)
            resting_bid = tick.get("resting_bid", bid)

            maker_order = self.maker_eng.construct_maker_bid(best_bid=bid, best_ask=ask, model_prob=p_model)
            entry_price = maker_order["maker_price"] if maker_order.get("status") == "POSTED" else ask

            b_odds = (1.0 / entry_price) - 1.0 if entry_price > 0 else 1.0
            f_star = max(0.0, (p_model * (b_odds + 1.0) - 1.0) / b_odds) if b_odds > 0 else 0.0
            stake_fraction = min(0.05, max(0.01, 0.25 * f_star))
            stake_d_cents = int(round(cap_d * stake_fraction))
            cost_per_share_cents = int(round(entry_price * 100))
            qty = max(1, stake_d_cents // cost_per_share_cents) if cost_per_share_cents > 0 else 1
            actual_cost_d_cents = qty * cost_per_share_cents

            exit_eval = self.exit_mgr.evaluate_exit(
                entry_price=entry_price,
                current_bid=resting_bid,
                elapsed_hours=elapsed_h,
                total_hours=total_h
            )

            if exit_eval["should_exit"]:
                d_harvested_early += 1
                payout_d_cents = int(round(qty * exit_eval["net_liquidation_price"] * 100))
                trade_friction_d = int(round(qty * resting_bid * 0.01 * 100))
            else:
                d_held_to_maturity += 1
                payout_d_cents = (qty * 100) if outcome == 1 else 0
                trade_friction_d = 0

            pnl_d = payout_d_cents - actual_cost_d_cents
            cap_d += pnl_d
            d_friction_cents += trade_friction_d
            if pnl_d > 0:
                wins_d += 1
            trade_returns_d.append(pnl_d / max(1, actual_cost_d_cents))

            if cap_d > peak_equity_d:
                peak_equity_d = cap_d
            dd_d = ((peak_equity_d - cap_d) / peak_equity_d) * 100.0 if peak_equity_d > 0 else 0.0
            if dd_d > max_dd_d_pct:
                max_dd_d_pct = dd_d

        # Baseline C Summary Metrics
        roi_c = round(((cap_c - self.initial_capital_cents) / self.initial_capital_cents) * 100.0, 2)
        win_rate_c = round((wins_c / max(1, len(trade_returns_c))) * 100.0, 2)
        if len(trade_returns_c) > 1:
            mean_ret_c = sum(trade_returns_c) / len(trade_returns_c)
            var_c = sum((r - mean_ret_c) ** 2 for r in trade_returns_c) / (len(trade_returns_c) - 1)
            std_c = math.sqrt(var_c) if var_c > 0 else 0.0001
            sharpe_c = round(mean_ret_c / std_c, 3)
        else:
            sharpe_c = 0.0

        # Strategy D Summary Metrics
        roi_d = round(((cap_d - self.initial_capital_cents) / self.initial_capital_cents) * 100.0, 2)
        win_rate_d = round((wins_d / max(1, len(trade_returns_d))) * 100.0, 2)
        if len(trade_returns_d) > 1:
            mean_ret_d = sum(trade_returns_d) / len(trade_returns_d)
            var_d = sum((r - mean_ret_d) ** 2 for r in trade_returns_d) / (len(trade_returns_d) - 1)
            std_d = math.sqrt(var_d) if var_d > 0 else 0.0001
            sharpe_d = round(mean_ret_d / std_d, 4)
        else:
            sharpe_d = 0.0

        return {
            'total_trades': trades_count,
            'baseline_a_final_cents': cap_a,
            'baseline_b_final_cents': cap_b,
            'hybrid_c_final_cents': cap_c,
            'hybrid_c_roi_pct': roi_c,
            'win_rate_pct': win_rate_c,
            'sharpe_ratio': sharpe_c,
            'max_drawdown_pct': round(max_drawdown_pct, 2),
            'total_friction_cents': total_friction_cents,
            'early_harvested_count': c_harvested_early,
            'held_to_maturity_count': c_held_to_maturity,
            'strategy_d_final_cents': cap_d,
            'strategy_d_roi_pct': roi_d,
            'strategy_d_win_rate_pct': win_rate_d,
            'strategy_d_sharpe_ratio': sharpe_d,
            'strategy_d_max_drawdown_pct': round(max_dd_d_pct, 2),
            'strategy_d_total_friction_cents': d_friction_cents,
            'strategy_d_early_harvest_count': d_harvested_early,
            'strategy_d_held_maturity_count': d_held_to_maturity,
            'status': 'COMPLETED'
        }
