import pytest
from app.adapters.venue_connectors import KalshiMarketDataClient, PolymarketMarketDataClient
from app.adapters.noaa_feed import NOAAASOSAdapter
from app.domain.venue_scanner import VenueOpportunityScanner

def test_kalshi_connector_orderbook_normalization():
    client = KalshiMarketDataClient()
    raw = {
        "bids": [[42, 5000], [40, 10000]],
        "asks": [[46, 5000], [48, 10000]]
    }
    book = client.normalize_orderbook("KX-MIA-FRZ-32", raw)
    assert book["venue"] == "KALSHI"
    assert book["contract_ticker"] == "KX-MIA-FRZ-32"
    assert book["yes_bid"] == 0.42
    assert book["yes_ask"] == 0.46
    assert book["spread"] == 0.04
    assert book["mid_price"] == 0.44
    assert book["total_depth_cents"] > 0
    assert len(book["bids"]) == 2
    assert len(book["asks"]) == 2

def test_polymarket_connector_orderbook_normalization():
    client = PolymarketMarketDataClient()
    raw = {
        "bids": [{"price": "0.52", "size": "7500"}],
        "asks": [{"price": "0.55", "size": "7500"}]
    }
    book = client.normalize_orderbook("POLY-239496", raw)
    assert book["venue"] == "POLYMARKET"
    assert book["contract_ticker"] == "POLY-239496"
    assert book["yes_bid"] == 0.52
    assert book["yes_ask"] == 0.55
    assert book["spread"] == 0.03
    assert book["mid_price"] == 0.535
    assert book["total_depth_cents"] == round(0.52 * 100 * 7500 + 0.55 * 100 * 7500)

def test_noaa_feed_pit_admissibility():
    adapter = NOAAASOSAdapter()
    # 1. Admissible observation (published before cutoff)
    obs_valid = adapter.ingest_observation(
        station_id="KMIA",
        temp_f=31.0,
        observed_at_iso="2026-09-16T12:00:00Z",
        cutoff_iso="2026-09-16T14:00:00Z"
    )
    assert obs_valid["admissible"] is True
    assert obs_valid["freeze_condition_met"] is True
    assert obs_valid["observed_temp_c"] == -0.56

    # 2. Lookahead violation observation (published after cutoff)
    obs_future = adapter.ingest_observation(
        station_id="KMIA",
        temp_f=30.0,
        observed_at_iso="2026-09-16T15:00:00Z",
        cutoff_iso="2026-09-16T14:00:00Z"
    )
    assert obs_future["admissible"] is False
    assert obs_future["reason"] == "POST_CUTOFF_DATA_LEAKAGE"

def test_venue_scanner_edge_and_lineal_house_tagging():
    scanner = VenueOpportunityScanner(min_edge_barrier=0.28)
    client = KalshiMarketDataClient()
    raw_kalshi = {
        "bids": [[1, 2000]],
        "asks": [[3, 5000]]  # 3c ask price
    }
    book = client.normalize_orderbook("KX-MIA-FRZ-32", raw_kalshi)
    obs = {
        "station_id": "KMIA",
        "admissible": True,
        "observed_temp_f": 31.0
    }

    # Model projects 31.5% likelihood of freeze vs 3.0% market ask -> 28.5% edge
    opp = scanner.evaluate_opportunity(
        orderbook=book,
        weather_obs=obs,
        model_prob=0.315,
        target_house_id=3  # Tagged to House 3
    )

    assert opp["status"] == "QUALIFIED"
    assert opp["target_house_id"] == 3
    assert opp["lineage_code"] == "HOUSE-03"
    assert opp["recommended_action"] == "BUY_YES"
    assert opp["market_price"] == 0.03
    assert opp["net_edge"] == 0.285

def test_venue_scanner_house_id_validation():
    scanner = VenueOpportunityScanner()
    book = {"venue": "KALSHI", "yes_ask": 0.50, "yes_bid": 0.40}
    obs = {"admissible": True}

    with pytest.raises(ValueError):
        scanner.evaluate_opportunity(book, obs, model_prob=0.80, target_house_id=0)

    with pytest.raises(ValueError):
        scanner.evaluate_opportunity(book, obs, model_prob=0.80, target_house_id=13)
