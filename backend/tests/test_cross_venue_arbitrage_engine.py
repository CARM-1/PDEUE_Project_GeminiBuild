from app.domain.cross_venue_arbitrage_engine import CrossVenueArbitrageEngine

def test_cross_venue_arbitrage_detected_kalshi_yes_poly_no():
    engine = CrossVenueArbitrageEngine(fee_rate_kalshi=0.01, fee_rate_poly=0.0, min_profit_cents=2)
    k_mkt = {'ticker': 'KX-CPI-HIGH', 'yes_ask': 0.45}
    p_mkt = {'id': 'POLY-CPI-HIGH', 'no_ask': 0.48}
    res = engine.evaluate_parity_pair(k_mkt, p_mkt)
    assert len(res) == 1
    opp = res[0]
    assert opp['pairing'] == 'KALSHI_YES_POLY_NO'
    assert opp['kalshi_action'] == 'BUY_YES'
    assert opp['poly_action'] == 'BUY_NO'
    assert opp['net_profit_cents'] >= 2

def test_cross_venue_arbitrage_detected_kalshi_no_poly_yes():
    engine = CrossVenueArbitrageEngine(fee_rate_kalshi=0.01, fee_rate_poly=0.0, min_profit_cents=2)
    k_mkt = {'ticker': 'KX-BTC-100K', 'yes_bid': 0.50}
    p_mkt = {'id': 'POLY-BTC-100K', 'yes_ask': 0.42}
    res = engine.evaluate_parity_pair(k_mkt, p_mkt)
    assert len(res) == 1
    opp = res[0]
    assert opp['pairing'] == 'KALSHI_NO_POLY_YES'
    assert opp['kalshi_action'] == 'BUY_NO'
    assert opp['poly_action'] == 'BUY_YES'
    assert opp['net_profit_cents'] >= 2

def test_cross_venue_efficient_market_zero_arbitrage():
    engine = CrossVenueArbitrageEngine()
    k_mkt = {'ticker': 'KX-MKT', 'yes_ask': 0.55, 'yes_bid': 0.52}
    p_mkt = {'id': 'P-MKT', 'yes_ask': 0.54, 'no_ask': 0.50}
    res = engine.evaluate_parity_pair(k_mkt, p_mkt)
    assert len(res) == 0
