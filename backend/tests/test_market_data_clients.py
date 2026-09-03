from app.adapters.market_data_clients import KalshiMarketDataClient, PolymarketMarketDataClient, MarketDataFeedAggregator
from app.domain.cross_category_screener import CrossCategoryScreener

def test_kalshi_market_data_client_fallback():
    client = KalshiMarketDataClient(base_url='http://localhost:9999/unreachable')
    markets = client.fetch_markets_by_series('KX-ORD')
    assert len(markets) == 2
    assert markets[0]['ticker'] == 'KX-ORD-24'

def test_polymarket_market_data_client_fallback():
    client = PolymarketMarketDataClient(base_url='http://localhost:9999/unreachable')
    markets = client.fetch_markets_by_tag('crypto')
    assert len(markets) == 1
    assert markets[0]['token_id'] == 'POLY-BTC-120K'

def test_market_data_feed_aggregator_cross_category():
    aggregator = MarketDataFeedAggregator()
    board = aggregator.get_unified_board()
    assert len(board) >= 4
    categories = {b['category'] for b in board}
    assert categories == {'WEATHER', 'MACROECONOMIC', 'SPORTS', 'CRYPTO'}

    screener = CrossCategoryScreener()
    screen_res = screener.screen_cross_category_board(board)
    assert screen_res['admissible_count'] >= 3
    assert screen_res['top_opportunity'] is not None
