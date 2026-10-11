"""
Unit and Microstructure Verification Suite for WP-8A Expansion Adapters
Verifies:
1. Mathematical distribution bounds [0.0, 1.0].
2. ADR-008 exact-cent bid recommendations [1, 99].
3. Clock-driven pre-release quote-pull triggers (Δt <= 5s).
4. Retained-Kelly (0.25f*) sizing ceiling (<= 2.0%).
5. Discrete key-number sensitivity and early harvesting flags.
"""

import pytest
from app.domain.expansion_adapters import (
    LaborUnderwritingAdapter,
    EnergyEIAAdapter,
    TreasuryAuctionAdapter,
    EquityIndexAdapter,
    LogisticsTSAAdapter,
    FXFixingAdapter,
    SportsPoissonAdapter,
    PerpFundingAdapter
)

def test_labor_adapter_quote_pull_and_pricing():
    adapter = LaborUnderwritingAdapter()
    dec_pull = adapter.underwrite("KX-NFP-200K", strike_jobs=200.0, nowcast_jobs=220.0, dispersion_sigma=25.0, current_best_bid=45, seconds_to_release=4.5)
    assert dec_pull.should_pull_quotes is True
    assert 1 <= dec_pull.recommended_bid_cents <= 99
    assert dec_pull.fair_probability > 0.50

    dec_safe = adapter.underwrite("KX-NFP-200K", strike_jobs=200.0, nowcast_jobs=220.0, dispersion_sigma=25.0, current_best_bid=45, seconds_to_release=120.0)
    assert dec_safe.should_pull_quotes is False
    kelly = adapter.calculate_retained_kelly(dec_safe.fair_probability, dec_safe.recommended_bid_cents)
    assert 0.0 <= kelly <= 0.02

def test_energy_adapter_eia_draw():
    adapter = EnergyEIAAdapter()
    dec = adapter.underwrite("KX-CRUDE-DRAW-2M", strike_draw_mb=2.0, physical_cushing_delta=3.2, refinery_utilization_ratio=0.95, current_best_bid=52, seconds_to_release=10.0)
    assert dec.fair_probability > 0.50
    assert dec.recommended_bid_cents == 53
    assert dec.should_pull_quotes is False

def test_treasury_auction_tail_trigger():
    adapter = TreasuryAuctionAdapter()
    dec = adapter.underwrite("KX-TREAS-10Y-TAIL", dealer_inventory_ratio=0.85, foreign_bidder_pct=0.45, current_best_bid=48, seconds_to_cutoff=3.0)
    assert dec.fair_probability > 0.70
    assert dec.should_pull_quotes is True

def test_equity_index_bracket_iv():
    adapter = EquityIndexAdapter()
    # Case 1: Underpriced market (bid=20c vs fair=27c) -> Posts inside maker bid at 21c (+6.41% edge)
    dec = adapter.underwrite("KX-SPX-5820-5840", lower_strike=5820.0, upper_strike=5840.0, current_spot=5830.0, annualized_iv=0.14, hours_to_expiry=2.0, current_best_bid=20)
    assert 0.0 < dec.fair_probability < 1.0
    assert dec.recommended_bid_cents == 21
    assert dec.net_edge > 0.05
    assert dec.should_pull_quotes is False

    # Case 2: Overpriced market (bid=35c vs fair=27c) -> Clamped at fair_cents - 1c = 26c, refusing to overpay
    dec_capped = adapter.underwrite("KX-SPX-5820-5840", lower_strike=5820.0, upper_strike=5840.0, current_spot=5830.0, annualized_iv=0.14, hours_to_expiry=2.0, current_best_bid=35)
    assert dec_capped.recommended_bid_cents == 26
    assert dec_capped.net_edge > 0.0

def test_logistics_tsa_settlement_lock():
    adapter = LogisticsTSAAdapter()
    dec = adapter.underwrite("KX-TSA-2.4M", strike_pax=2400000, scheduled_seats=2800000, historical_load_factor=0.89, ground_stop_haircut=0.01, current_best_bid=78, current_hour_utc=21)
    assert dec.fair_probability > 0.60
    assert dec.harvest_eligible is False

def test_fx_fixing_corridor():
    adapter = FXFixingAdapter()
    dec = adapter.underwrite("KX-EURUSD-CORRIDOR", band_low=1.0800, band_high=1.0850, current_spot=1.0825, rate_diff_bps=12.5, current_best_bid=60)
    assert dec.fair_probability == 0.82
    assert dec.recommended_bid_cents == 61

def test_sports_poisson_key_numbers_and_wind():
    adapter = SportsPoissonAdapter()
    # Case 1: Close match (bid=55c at minute 55) -> Hold, do not harvest prematurely at coin-flip odds
    dec_close = adapter.underwrite("KX-NFL-KC-MINUS-3", margin_threshold=2.5, lambda_home=24.0, lambda_away=20.0, surface_wind_mph=25.0, current_best_bid=55, game_minute=55)
    assert 0.0 < dec_close.fair_probability < 1.0
    assert dec_close.harvest_eligible is False

    # Case 2: Dominating lead in late game (bid=82c at minute 55) -> Harvest early to eliminate last-minute binary risk
    dec_blowout = adapter.underwrite("KX-NFL-KC-MINUS-3", margin_threshold=2.5, lambda_home=34.0, lambda_away=14.0, surface_wind_mph=10.0, current_best_bid=82, game_minute=55)
    assert dec_blowout.fair_probability > 0.80
    assert dec_blowout.harvest_eligible is True

def test_perp_funding_accumulation():
    adapter = PerpFundingAdapter()
    dec = adapter.underwrite("KX-BTC-PERP-FUNDING-POS", strike_rate_pct=0.01, accumulated_twap_rate=0.018, elapsed_hours=7.0, current_instant_premium=0.02, current_best_bid=86)
    assert dec.fair_probability == 0.92
    assert dec.harvest_eligible is True
