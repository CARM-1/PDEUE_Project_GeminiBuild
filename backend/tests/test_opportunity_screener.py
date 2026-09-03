from app.domain.opportunity_screener import OpportunityScreener

def test_screen_strike_ladder_ranks_maximum_mispricing():
    screener = OpportunityScreener(min_edge_threshold=0.03, fee_rate=0.01)
    ensemble = [24.0, 24.5, 25.0, 25.5, 25.0]
    ladder = [
        {'contract_id': 'KX-ORD-20', 'strike_temp_c': 20.0, 'yes_bid': 0.95, 'yes_ask': 0.99},
        {'contract_id': 'KX-ORD-24', 'strike_temp_c': 24.0, 'yes_bid': 0.94, 'yes_ask': 0.98},
        {'contract_id': 'KX-ORD-26', 'strike_temp_c': 26.0, 'yes_bid': 0.08, 'yes_ask': 0.12},
        {'contract_id': 'KX-ORD-28', 'strike_temp_c': 28.0, 'yes_bid': 0.00, 'yes_ask': 0.02},
        {'contract_id': 'KX-ORD-30', 'strike_temp_c': 30.0, 'yes_bid': 0.00, 'yes_ask': 0.01}
    ]
    res = screener.screen_weather_strike_ladder(ensemble, ladder, station_id='KORD')
    assert res['total_evaluated'] == 5
    assert res['admissible_count'] >= 1
    top = res['top_pick']
    assert top is not None
    assert top['contract_id'] == 'KX-ORD-26'
    assert top['recommended_action'] == 'BUY_YES'
    assert top['rank'] == 1
    assert top['net_edge'] > 0.10

def test_screen_strike_ladder_filters_negative_edge():
    screener = OpportunityScreener(min_edge_threshold=0.05, fee_rate=0.01)
    ensemble = [20.0, 20.0, 20.0]
    ladder = [
        {'contract_id': 'KX-EFFICIENT-20', 'strike_temp_c': 20.0, 'yes_bid': 0.48, 'yes_ask': 0.52}
    ]
    res = screener.screen_weather_strike_ladder(ensemble, ladder, station_id=None)
    assert res['admissible_count'] == 0
    assert res['top_pick'] is None

def test_screener_direction_selection_buy_no():
    screener = OpportunityScreener(min_edge_threshold=0.03, fee_rate=0.01)
    ensemble = [18.0, 18.5, 19.0]
    ladder = [
        {'contract_id': 'KX-OVERPRICED-HIGH', 'strike_temp_c': 28.0, 'yes_bid': 0.30, 'yes_ask': 0.35}
    ]
    res = screener.screen_weather_strike_ladder(ensemble, ladder, station_id=None)
    assert res['admissible_count'] == 1
    pick = res['top_pick']
    assert pick['recommended_action'] == 'BUY_NO'
    assert pick['net_edge'] > 0.20
