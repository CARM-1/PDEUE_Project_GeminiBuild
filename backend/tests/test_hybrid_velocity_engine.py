from app.domain.settlement_engine import PositionExitManager
from app.domain.cross_category_screener import CrossCategoryScreener
from app.domain.domain_registry import DomainRegistry

def test_expiry_horizon_and_velocity_scoring():
    screener = CrossCategoryScreener(registry=DomainRegistry())
    board = [
        {'contract_id': 'SLOW-48H', 'category': 'WEATHER', 'venue': 'KALSHI', 'yes_bid': 0.10, 'yes_ask': 0.15, 'hours_to_expiry': 48.0, 'underwriting_spec': {'strike_temp_c': 25.0, 'ensemble_members': [24.0, 24.5, 25.0], 'station_id': 'KORD'}},
        {'contract_id': 'FAST-2H', 'category': 'WEATHER', 'venue': 'KALSHI', 'yes_bid': 0.10, 'yes_ask': 0.15, 'hours_to_expiry': 2.0, 'underwriting_spec': {'strike_temp_c': 25.0, 'ensemble_members': [24.0, 24.5, 25.0], 'station_id': 'KORD'}}
    ]
    filtered = screener.screen_cross_category_board(board, max_expiry_hours=12.0)
    assert filtered['admissible_count'] == 1
    assert filtered['leaderboard'][0]['contract_id'] == 'FAST-2H'

def test_net_80_percent_early_exit_hurdle():
    mgr = PositionExitManager(exit_profit_threshold=0.80, fee_rate=0.01)
    pos = {'quantity': 50, 'total_cost_cents': 1000}
    hold_eval = mgr.evaluate_early_exit(pos, resting_bid=0.60, spread=0.02)
    assert hold_eval['action'] == 'HOLD_TO_MATURITY'
    assert hold_eval['reason'] == 'PROFIT_BELOW_EXIT_HURDLE'

    exit_eval = mgr.evaluate_early_exit(pos, resting_bid=0.92, spread=0.01)
    assert exit_eval['action'] == 'EXIT_EARLY'
    assert exit_eval['profit_capture_ratio'] >= 0.80
