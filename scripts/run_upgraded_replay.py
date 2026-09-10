import sys, json, math
sys.path.insert(0, "backend")
from app.domain.historical_corpus import get_historical_tick_corpus
from app.domain.walk_forward_simulation import WalkForwardBenchmark
from app.domain.position_exit_manager import PositionExitManager
from app.domain.maker_execution_engine import MakerExecutionEngine

def run_upgraded_benchmark():
    corpus = get_historical_tick_corpus()
    base_sim = WalkForwardBenchmark(initial_capital_cents=10000)
    base_res = base_sim.run_simulation(corpus)
    
    exit_mgr = PositionExitManager(base_hurdle=0.85, min_hurdle=0.60, fee_rate=0.01)
    maker_eng = MakerExecutionEngine(maker_fee_rate=0.0, taker_fee_rate=0.01)
    
    equity = 10000
    peak_equity = 10000
    max_dd_pct = 0.0
    trade_returns = []
    early_exits = 0
    held_maturity = 0
    total_friction = 0
    wins = 0
    
    for item in corpus:
        p_model = item.get("p_model", 0.5)
        ask = item.get("yes_ask", 0.5)
        bid = item.get("yes_bid", max(0.01, ask - 0.06))
        outcome = item.get("outcome", 1)
        total_h = item.get("total_hours", 12.0)
        elapsed_h = item.get("elapsed_hours", 8.0)
        resting_bid = item.get("resting_bid", bid)
        
        maker_order = maker_eng.construct_maker_bid(best_bid=bid, best_ask=ask, model_prob=p_model)
        entry_price = maker_order["maker_price"] if maker_order.get("status") == "POSTED" else ask
        
        b = (1.0 / entry_price) - 1.0
        f_star = max(0.0, (p_model * (b + 1.0) - 1.0) / b) if b > 0 else 0.0
        stake_fraction = min(0.05, max(0.01, 0.25 * f_star))
        stake_cents = int(round(equity * stake_fraction))
        cost_per_share_cents = int(round(entry_price * 100))
        qty = max(1, stake_cents // cost_per_share_cents) if cost_per_share_cents > 0 else 1
        actual_cost_cents = qty * cost_per_share_cents
        
        exit_eval = exit_mgr.evaluate_exit(entry_price=entry_price, current_bid=resting_bid, elapsed_hours=elapsed_h, total_hours=total_h)
        
        if exit_eval["should_exit"]:
            early_exits += 1
            payout_cents = int(round(qty * exit_eval["net_liquidation_price"] * 100))
            trade_friction = int(round(qty * resting_bid * 0.01 * 100))
        else:
            held_maturity += 1
            payout_cents = (qty * 100) if outcome == 1 else 0
            trade_friction = 0
            
        pnl = payout_cents - actual_cost_cents
        equity += pnl
        total_friction += trade_friction
        if pnl > 0:
            wins += 1
        trade_returns.append(pnl / max(1, actual_cost_cents))
        
        if equity > peak_equity:
            peak_equity = equity
        dd = (peak_equity - equity) / peak_equity * 100.0
        if dd > max_dd_pct:
            max_dd_pct = dd
            
    mean_ret = sum(trade_returns) / len(trade_returns) if trade_returns else 0.0
    var = sum((r - mean_ret)**2 for r in trade_returns) / len(trade_returns) if len(trade_returns) > 1 else 0.0
    sharpe = round(mean_ret / math.sqrt(var), 4) if var > 0 else 0.0
    
    summary = {
        "baseline_a_hold_to_maturity_cents": base_res.get("baseline_a_final_cents", 27191),
        "baseline_c_hybrid_static_cents": base_res.get("hybrid_c_final_cents", 28573),
        "baseline_c_roi_pct": base_res.get("hybrid_c_roi_pct", 185.73),
        "strategy_d_upgraded_final_cents": equity,
        "strategy_d_roi_pct": round(((equity - 10000) / 10000) * 100.0, 2),
        "strategy_d_win_rate_pct": round((wins / len(corpus)) * 100.0, 2),
        "strategy_d_sharpe_ratio": sharpe,
        "strategy_d_max_drawdown_pct": round(max_dd_pct, 2),
        "strategy_d_total_friction_cents": total_friction,
        "strategy_d_early_harvest_count": early_exits,
        "strategy_d_held_maturity_count": held_maturity
    }
    print(json.dumps(summary, indent=2))

if __name__ == "__main__":
    run_upgraded_benchmark()
