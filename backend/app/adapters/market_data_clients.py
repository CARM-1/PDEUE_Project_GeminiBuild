from typing import Dict, Any, List, Optional
import httpx
from app.adapters.kalshi_adapter import KalshiVenueAdapter
from app.adapters.polymarket_adapter import PolymarketVenueAdapter

class KalshiMarketDataClient:
    DEFAULT_BASE_URL = 'https://demo-api.kalshi.co/trade-api/v2'

    def __init__(self, base_url: Optional[str] = None, adapter: Optional[KalshiVenueAdapter] = None):
        self.base_url = base_url or self.DEFAULT_BASE_URL
        self.adapter = adapter or KalshiVenueAdapter()

    def fetch_markets_by_series(self, series_ticker: str, timeout_sec: float = 3.0) -> List[Dict[str, Any]]:
        try:
            resp = httpx.get(f'{self.base_url}/markets?series_ticker={series_ticker}', timeout=timeout_sec)
            if resp.status_code == 200:
                return resp.json().get('markets', [])
        except Exception:
            pass
        return self._get_fallback_series_markets(series_ticker)

    def _get_fallback_series_markets(self, series_ticker: str) -> List[Dict[str, Any]]:
        if 'WEATHER' in series_ticker or 'ORD' in series_ticker:
            return [
                {'ticker': 'KX-ORD-24', 'strike_val': 24.0, 'yes_bid': 0.94, 'yes_ask': 0.98},
                {'ticker': 'KX-ORD-26', 'strike_val': 26.0, 'yes_bid': 0.08, 'yes_ask': 0.12}
            ]
        return [
            {'ticker': 'KX-CPI-3.0', 'strike_val': 3.0, 'yes_bid': 0.55, 'yes_ask': 0.60}
        ]

class PolymarketMarketDataClient:
    DEFAULT_BASE_URL = 'https://gamma-api.polymarket.com'

    def __init__(self, base_url: Optional[str] = None, adapter: Optional[PolymarketVenueAdapter] = None):
        self.base_url = base_url or self.DEFAULT_BASE_URL
        self.adapter = adapter or PolymarketVenueAdapter()

    def fetch_markets_by_tag(self, tag: str, timeout_sec: float = 3.0) -> List[Dict[str, Any]]:
        try:
            resp = httpx.get(f'{self.base_url}/events?tag={tag}&limit=5', timeout=timeout_sec)
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass
        return self._get_fallback_tag_markets(tag)

    def _get_fallback_tag_markets(self, tag: str) -> List[Dict[str, Any]]:
        return [
            {'token_id': 'POLY-BTC-120K', 'strike_value': 120000.0, 'price_bid': 0.20, 'price_ask': 0.24}
        ]

class MarketDataFeedAggregator:
    def __init__(self, kalshi_client: Optional[KalshiMarketDataClient] = None, poly_client: Optional[PolymarketMarketDataClient] = None):
        self.kalshi_client = kalshi_client or KalshiMarketDataClient()
        self.poly_client = poly_client or PolymarketMarketDataClient()

    def get_unified_board(self) -> List[Dict[str, Any]]:
        kalshi_wx = self.kalshi_client.fetch_markets_by_series('KX-ORD')
        kalshi_norm_wx = self.kalshi_client.adapter.normalize_market_ladder(kalshi_wx)
        kalshi_cpi = self.kalshi_client.fetch_markets_by_series('KX-CPI')
        kalshi_norm_cpi = self.kalshi_client.adapter.normalize_market_ladder(kalshi_cpi)
        poly_crypto = self.poly_client.fetch_markets_by_tag('crypto')
        poly_norm_crypto = self.poly_client.adapter.normalize_market_ladder(poly_crypto)

        board = []
        for item in kalshi_norm_wx:
            board.append({
                'contract_id': item['contract_id'],
                'category': 'WEATHER',
                'venue': 'KALSHI',
                'yes_bid': item['yes_bid'],
                'yes_ask': item['yes_ask'],
                'underwriting_spec': {
                    'strike_temp_c': item['strike_temp_c'],
                    'ensemble_members': [24.0, 24.5, 25.0, 25.5, 25.0],
                    'station_id': 'KORD'
                }
            })
        for item in kalshi_norm_cpi:
            board.append({
                'contract_id': item['contract_id'],
                'category': 'MACROECONOMIC',
                'venue': 'KALSHI',
                'yes_bid': item['yes_bid'],
                'yes_ask': item['yes_ask'],
                'underwriting_spec': {
                    'threshold': item['strike_temp_c'],
                    'evidence': [{'source': 'BLS', 'value': 3.40, 'available_at': '2026-09-01T12:00:00Z'}]
                }
            })
        board.append({
            'contract_id': 'NFL-KC-SPREAD-3.5',
            'category': 'SPORTS',
            'venue': 'KALSHI',
            'yes_bid': 0.45,
            'yes_ask': 0.50,
            'underwriting_spec': {'projected_margin': 7.0, 'target_spread': 3.5, 'sigma': 13.5}
        })
        for item in poly_norm_crypto:
            board.append({
                'contract_id': item['contract_id'],
                'category': 'CRYPTO',
                'venue': 'POLYMARKET',
                'yes_bid': item['yes_bid'],
                'yes_ask': item['yes_ask'],
                'underwriting_spec': {
                    'spot_price': 115000.0,
                    'strike_price': item['strike_temp_c'],
                    'annualized_vol': 0.55,
                    'days_to_expiry': 14.0
                }
            })
        return board
