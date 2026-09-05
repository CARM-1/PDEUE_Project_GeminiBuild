from typing import Dict, Any, List
import math

class WalkForwardBenchmark:
    def __init__(self, initial_capital_cents: int = 10000):
        self.initial_capital_cents = initial_capital_cents

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

        for tick in tick_series:
            stake = min(int(cap_c * 0.05), 500)
            if stake <= 0:
                break
            entry_ask = tick['entry_ask']
            final_payout = tick['final_payout']
            peak_mid = tick['peak_midpoint']
            fee_rate = tick.get('fee_rate', 0.01)
            contracts = stake / entry_ask
            fee_cents = int(stake * fee_rate)

            # Baseline A
            cap_a += int((contracts * final_payout) - stake - fee_cents)

            # Baseline B
            cap_b += int((contracts * peak_mid) - stake)

            # Baseline C (Hybrid Velocity)
            target_exit = entry_ask + (1.0 - entry_ask) * 0.80
            if peak_mid >= target_exit:
                c_harvested_early += 1
                effective_exit = peak_mid * 0.985
                slippage_cents = int((contracts * peak_mid) - (contracts * effective_exit))
                payout_cents = int(contracts * effective_exit)
                pnl = payout_cents - stake - fee_cents
                total_friction_cents += fee_cents + slippage_cents
            else:
                c_held_to_maturity += 1
                payout_cents = int(contracts * final_payout)
                pnl = payout_cents - stake - fee_cents
                total_friction_cents += fee_cents

            cap_c += pnl
            if pnl > 0:
                wins_c += 1
            ret = pnl / stake
            trade_returns_c.append(ret)

            if cap_c > peak_equity_c:
                peak_equity_c = cap_c
            dd = ((peak_equity_c - cap_c) / peak_equity_c) * 100.0 if peak_equity_c > 0 else 0.0
            if dd > max_drawdown_pct:
                max_drawdown_pct = dd

        roi_c = round(((cap_c - self.initial_capital_cents) / self.initial_capital_cents) * 100.0, 2)
        win_rate = round((wins_c / max(1, len(trade_returns_c))) * 100.0, 2)
        
        # Sharpe calculation
        if len(trade_returns_c) > 1:
            mean_ret = sum(trade_returns_c) / len(trade_returns_c)
            var = sum((r - mean_ret) ** 2 for r in trade_returns_c) / (len(trade_returns_c) - 1)
            std = math.sqrt(var) if var > 0 else 0.0001
            sharpe = round(mean_ret / std, 3)
        else:
            sharpe = 0.0

        return {
            'total_trades': trades_count,
            'baseline_a_final_cents': cap_a,
            'baseline_b_final_cents': cap_b,
            'hybrid_c_final_cents': cap_c,
            'hybrid_c_roi_pct': roi_c,
            'win_rate_pct': win_rate,
            'sharpe_ratio': sharpe,
            'max_drawdown_pct': round(max_drawdown_pct, 2),
            'total_friction_cents': total_friction_cents,
            'early_harvested_count': c_harvested_early,
            'held_to_maturity_count': c_held_to_maturity,
            'status': 'COMPLETED'
        }
