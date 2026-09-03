from app.domain.sports_adapter import SportsDomainAdapter
from app.domain.crypto_adapter import CryptoDomainAdapter
from app.domain.domain_registry import DomainRegistry
from app.domain.cross_category_screener import CrossCategoryScreener

def test_sports_adapter_probability():
    adapter = SportsDomainAdapter()
    prob = adapter.underwrite_game({'projected_margin': 7.0, 'target_spread': 3.5, 'sigma': 13.5})
    assert 0.55 < prob < 0.65

def test_crypto_adapter_probability():
    adapter = CryptoDomainAdapter()
    prob = adapter.underwrite_threshold({'spot_price': 100000.0, 'strike_price': 100000.0, 'annualized_vol': 0.50, 'days_to_expiry': 30.0})
    assert 0.45 < prob < 0.55

def test_cross_category_screener_four_domains():
    registry = DomainRegistry()
    screener = CrossCategoryScreener(registry=registry)
    board = [
        {'contract_id': 'WX-01', 'category': 'WEATHER', 'venue': 'KALSHI', 'yes_bid': 0.08, 'yes_ask': 0.12, 'underwriting_spec': {'strike_temp_c': 26.0, 'ensemble_members': [24.0, 24.5, 25.0, 25.5, 25.0], 'station_id': 'KORD'}},
        {'contract_id': 'MACRO-01', 'category': 'MACROECONOMIC', 'venue': 'KALSHI', 'yes_bid': 0.55, 'yes_ask': 0.60, 'underwriting_spec': {'threshold': 3.0, 'evidence': [{'source': 'BLS', 'value': 3.40, 'available_at': '2026-09-01T12:00:00Z'}]}},
        {'contract_id': 'NFL-01', 'category': 'SPORTS', 'venue': 'KALSHI', 'yes_bid': 0.45, 'yes_ask': 0.50, 'underwriting_spec': {'projected_margin': 7.0, 'target_spread': 3.5}},
        {'contract_id': 'CRYPTO-01', 'category': 'CRYPTO', 'venue': 'POLYMARKET', 'yes_bid': 0.20, 'yes_ask': 0.24, 'underwriting_spec': {'spot_price': 115000.0, 'strike_price': 120000.0, 'annualized_vol': 0.55, 'days_to_expiry': 14.0}}
    ]
    res = screener.screen_cross_category_board(board)
    assert res['total_evaluated'] == 4
    assert res['admissible_count'] >= 3
    categories = {item['category'] for item in res['leaderboard']}
    assert 'SPORTS' in categories
    assert 'CRYPTO' in categories
