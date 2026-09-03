from app.domain.cross_category_screener import CrossCategoryScreener
from app.domain.domain_registry import DomainRegistry

def test_cross_category_screening_and_ranking():
    screener = CrossCategoryScreener(min_edge_threshold=0.03)
    board = [
        {'contract_id': 'KX-ORD-26', 'category': 'WEATHER', 'venue': 'KALSHI', 'yes_bid': 0.08, 'yes_ask': 0.12, 'underwriting_spec': {'strike_temp_c': 26.0, 'ensemble_members': [24.0, 24.5, 25.0, 25.5, 25.0], 'station_id': 'KORD'}},
        {'contract_id': 'KX-CPI-3.0', 'category': 'MACROECONOMIC', 'venue': 'KALSHI', 'yes_bid': 0.55, 'yes_ask': 0.60, 'underwriting_spec': {'threshold': 3.0, 'evidence': [{'source': 'C1', 'value': 3.40, 'available_at': '2026-09-01T12:00:00Z'}, {'source': 'C2', 'value': 3.50, 'available_at': '2026-09-02T12:00:00Z'}]}},
        {'contract_id': 'KX-EFFICIENT', 'category': 'WEATHER', 'venue': 'KALSHI', 'yes_bid': 0.48, 'yes_ask': 0.52, 'underwriting_spec': {'strike_temp_c': 20.0, 'ensemble_members': [20.0, 20.0, 20.0], 'station_id': None}}
    ]
    res = screener.screen_cross_category_board(board)
    assert res['total_evaluated'] == 3
    assert res['admissible_count'] == 2
    top = res['top_opportunity']
    assert top['contract_id'] == 'KX-CPI-3.0'
    assert top['category'] == 'MACROECONOMIC'
    assert top['global_rank'] == 1
    second = res['leaderboard'][1]
    assert second['contract_id'] == 'KX-ORD-26'
    assert second['category'] == 'WEATHER'
    assert second['global_rank'] == 2

def test_custom_domain_registration_extensibility():
    registry = DomainRegistry()
    registry.register_domain('SPORTS_NFL', lambda spec: 0.85 if spec.get('spread', 0) > 3.0 else 0.40)
    screener = CrossCategoryScreener(registry=registry, min_edge_threshold=0.03)
    board = [{'contract_id': 'NFL-KC-MINUS-3', 'category': 'SPORTS_NFL', 'venue': 'KALSHI', 'yes_bid': 0.50, 'yes_ask': 0.55, 'underwriting_spec': {'spread': 3.5}}]
    res = screener.screen_cross_category_board(board)
    assert res['admissible_count'] == 1
    assert res['top_opportunity']['category'] == 'SPORTS_NFL'
    assert res['top_opportunity']['model_probability'] == 0.85

def test_unregistered_category_fails_closed():
    screener = CrossCategoryScreener()
    board = [{'contract_id': 'UNKNOWN-01', 'category': 'UNREGISTERED_CRYPTO', 'venue': 'KALSHI', 'yes_bid': 0.10, 'yes_ask': 0.20, 'underwriting_spec': {}}]
    res = screener.screen_cross_category_board(board)
    assert res['admissible_count'] == 0
    assert res['top_opportunity'] is None
