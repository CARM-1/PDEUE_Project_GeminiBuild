from app.domain.atomic_leg_coordinator import AtomicLegCoordinator
from app.domain.dynamic_spread_kelly import DynamicSpreadKellyRegime
from app.domain.stale_sniping_engine import StaleQuoteSnipingEngine
from app.domain.venue_rebalancer import CrossVenueRebalanceManager

def test_atomic_leg_coordinator_success():
    coord = AtomicLegCoordinator(leg_timeout_ms=750.0)
    res = coord.coordinate_legs({'leg_id': 'L1'}, {'leg_id': 'L2'})
    assert res['is_atomic_success'] is True
    assert res['outcome'] == 'COMPLETE_SET_FILLED'

def test_atomic_leg_coordinator_scratch_on_timeout():
    coord = AtomicLegCoordinator(leg_timeout_ms=750.0)
    res = coord.coordinate_legs({'leg_id': 'L1'}, {'leg_id': 'L2'}, simulate_leg2_latency_sec=1.0)
    assert res['is_atomic_success'] is False
    assert res['outcome'] == 'SCRATCHED'
    assert len(coord.scratched_positions) == 1

def test_dynamic_spread_kelly_scaling():
    regime = DynamicSpreadKellyRegime(base_fraction=0.25, defensive_floor=0.05, max_spread=0.05)
    assert regime.calculate_active_fraction(0.01) == 0.25
    assert regime.calculate_active_fraction(0.05) == 0.05
    assert 0.05 < regime.calculate_active_fraction(0.03) < 0.25

def test_stale_quote_sniping():
    sniper = StaleQuoteSnipingEngine()
    ground = {'published_at_epoch': 100.0, 'true_probability': 0.85}
    quote = {'ticker': 'KX-TEMP-75', 'venue': 'KALSHI', 'quoted_at_epoch': 90.0, 'ask_price': 0.60}
    op = sniper.evaluate_quote_staleness(ground, quote)
    assert op is not None
    assert op['captured_edge'] == 0.25

def test_venue_rebalancer_trigger():
    rebalancer = CrossVenueRebalanceManager(target_ratio=0.50, tolerance=0.15)
    res = rebalancer.check_rebalance_needed(kalshi_cents=8000, polymarket_cents=2000)
    assert res['rebalance_needed'] is True
    assert res['source_venue'] == 'KALSHI'
    assert res['target_venue'] == 'POLYMARKET'
    assert res['transfer_cents'] == 3000
