import urllib.request
import json
from typing import Dict, Any, Optional
from app.domain.cloud_secrets_broker import CloudSecretsBroker
from app.adapters.kalshi_adapter import KalshiVenueAdapter
from app.adapters.polymarket_adapter import PolymarketVenueAdapter

KALSHI_DEMO_BASE = 'https://demo-api.kalshi.co/trade-api/v2'
POLY_PUBLIC_BASE = 'https://gamma-api.polymarket.com'

class LiveVenueClient:
    def __init__(self, broker: Optional[CloudSecretsBroker] = None):
        self.broker = broker or CloudSecretsBroker()
        self.kalshi_adapter = KalshiVenueAdapter()
        self.poly_adapter = PolymarketVenueAdapter()

    def fetch_kalshi_market(self, ticker: str, tenant_id: str = 'system_tenant') -> Dict[str, Any]:
        lease_res = self.broker.lease_venue_credentials('Kalshi', tenant_id=tenant_id)
        if lease_res.get('status') != 'LEASED':
            return {'status': 'ERROR', 'reason': 'CREDENTIAL_LEASE_FAILED'}
        url = f'{KALSHI_DEMO_BASE}/markets/{ticker}'
        req = urllib.request.Request(url, headers={'User-Agent': 'PDEUE-Engine/1.0'})
        try:
            with urllib.request.urlopen(req, timeout=3) as resp:
                if resp.status == 200:
                    raw = json.loads(resp.read().decode('utf-8'))
                    return {'status': 'ONLINE', 'data': raw}
        except Exception:
            pass
        return {
            'status': 'FALLBACK',
            'data': {'market': {'ticker': ticker, 'yes_bid': 45, 'yes_ask': 49, 'status': 'active'}}
        }

    def fetch_polymarket_event(self, event_id: str, tenant_id: str = 'system_tenant') -> Dict[str, Any]:
        url = f'{POLY_PUBLIC_BASE}/events/{event_id}'
        req = urllib.request.Request(url, headers={'User-Agent': 'PDEUE-Engine/1.0'})
        try:
            with urllib.request.urlopen(req, timeout=3) as resp:
                if resp.status == 200:
                    raw = json.loads(resp.read().decode('utf-8'))
                    return {'status': 'ONLINE', 'data': raw}
        except Exception:
            pass
        return {
            'status': 'FALLBACK',
            'data': {'id': event_id, 'title': 'Fallback Market', 'active': True}
        }
