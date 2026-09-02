from app.domain.market_stream import MarketStreamAdapter

def test_market_stream_update_and_cache():
    adapter = MarketStreamAdapter(venue_id="KALSHI")
    book = adapter.update_order_book("KXCHICAGO-26SEP02", 0.42, 0.46, 5000)
    assert book["spread"] == 0.04
    assert book["mid_price"] == 0.44
    assert book["venue"] == "KALSHI"
    cached = adapter.get_latest_book("KXCHICAGO-26SEP02")
    assert cached is not None
    assert cached["yes_bid"] == 0.42
