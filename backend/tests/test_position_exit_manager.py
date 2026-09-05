from app.domain.position_exit_manager import PositionExitManager

def test_dynamic_hurdle_decay_trajectory():
    mgr = PositionExitManager(base_hurdle=0.85, min_hurdle=0.60)
    assert mgr.compute_dynamic_hurdle(elapsed_hours=0.0, total_hours=10.0) == 0.85
    assert mgr.compute_dynamic_hurdle(elapsed_hours=5.0, total_hours=10.0) == 0.725
    assert mgr.compute_dynamic_hurdle(elapsed_hours=10.0, total_hours=10.0) == 0.60
    assert mgr.compute_dynamic_hurdle(elapsed_hours=15.0, total_hours=10.0) == 0.60

def test_exit_trigger_respects_time_decay():
    mgr = PositionExitManager(base_hurdle=0.85, min_hurdle=0.60, fee_rate=0.01)
    entry = 0.25
    bid = 0.77
    
    early_check = mgr.evaluate_exit(entry_price=entry, current_bid=bid, elapsed_hours=1.0, total_hours=10.0)
    assert early_check['should_exit'] is False
    assert early_check['reason'] == 'HOLD_TO_MATURITY'

    late_check = mgr.evaluate_exit(entry_price=entry, current_bid=bid, elapsed_hours=9.0, total_hours=10.0)
    assert late_check['should_exit'] is True
    assert late_check['reason'] == 'DYNAMIC_PROFIT_HARVEST'

def test_loss_or_unprofitable_bid_never_exits_early():
    mgr = PositionExitManager()
    check = mgr.evaluate_exit(entry_price=0.50, current_bid=0.45, elapsed_hours=9.0, total_hours=10.0)
    assert check['should_exit'] is False
    assert check['net_unrealized_profit'] < 0.0
