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

        for tick in tick_series:
            stake = min(int(cap_c * 0.05), 500)
            if stake <= 0:
                break
            entry_ask = tick['entry_ask']
            final_payout = tick['final_payout']
            peak_mid = tick['peak_midpoint']
            fee_rate = tick.get('fee_rate', 0.01)
            contracts = stake / entry_ask

            # Baseline A: Hold to maturity
            cap_a += int((contracts * final_payout) - stake - (stake * fee_rate))

            # Baseline B: Unconstrained midpoint exit
            cap_b += int((contracts * peak_mid) - stake)

            # Baseline C: Hybrid Velocity (80% net hurdle with friction)
            target_exit = entry_ask + (1.0 - entry_ask) * 0.80
            if peak_mid >= target_exit:
                c_harvested_early += 1
                effective_exit = peak_mid * 0.985
                cap_c += int((contracts * effective_exit) - stake - (stake * fee_rate))
            else:
                c_held_to_maturity += 1
                cap_c += int((contracts * final_payout) - stake - (stake * fee_rate))

        roi_c = round(((cap_c - self.initial_capital_cents) / self.initial_capital_cents) * 100.0, 2)
        return {
            'total_trades': trades_count,
            'baseline_a_final_cents': cap_a,
            'baseline_b_final_cents': cap_b,
            'hybrid_c_final_cents': cap_c,
            'hybrid_c_roi_pct': roi_c,
            'early_harvested_count': c_harvested_early,
            'held_to_maturity_count': c_held_to_maturity,
            'status': 'COMPLETED'
        }
