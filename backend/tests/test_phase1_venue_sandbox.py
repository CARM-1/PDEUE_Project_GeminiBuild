from app.domain.venue_sandbox import KalshiSandboxAdapter

def test_kalshi_sandbox_book_query():
    adapter = KalshiSandboxAdapter()
    book = adapter.get_market_book("KXCHICAGO-26SEP02")
    assert book["ticker"] == "KXCHICAGO-26SEP02"
    assert book["yes_bid"] == 0.42

def test_kalshi_sandbox_order_execution():
    adapter = KalshiSandboxAdapter()
    order = adapter.place_order("KXCHICAGO-26SEP02", "buy", 10, 43)
    assert order["status"] == "FILLED"
    assert order["venue"] == "KALSHI_SANDBOX"
