import uuid
from datetime import datetime, timezone
from typing import Dict, Any, Optional

class EconomicMarketMapper:
    def __init__(self, venue: str = 'KALSHI'):
        self.venue = venue.upper()

    def map_venue_contract(
        self,
        venue_symbol: str,
        canonical_event_id: str,
        threshold: float,
        target_period: str,
        strike_metric: str = 'CPI_YOY'
    ) -> Dict[str, Any]:
        return {
            'mapping_id': str(uuid.uuid4()),
            'contract_id': venue_symbol,
            'canonical_event_id': canonical_event_id,
            'venue': self.venue,
            'strike_metric': strike_metric,
            'threshold': threshold,
            'target_period': target_period,
            'status': 'ACTIVE',
            'mapped_at': datetime.now(timezone.utc).isoformat()
        }

    def evaluate_edge(
        self,
        calibrated_prob: float,
        market_yes_ask: float,
        fee_rate: float = 0.01
    ) -> Dict[str, Any]:
        fair_value = round(calibrated_prob, 4)
        cost_with_fee = round(market_yes_ask * (1.0 + fee_rate), 4)
        gross_edge = round(fair_value - market_yes_ask, 4)
        net_edge = round(fair_value - cost_with_fee, 4)
        admissible = net_edge > 0.0

        return {
            'evaluation_id': str(uuid.uuid4()),
            'fair_value': fair_value,
            'market_yes_ask': market_yes_ask,
            'fee_rate': fee_rate,
            'gross_edge': gross_edge,
            'net_edge': net_edge,
            'admissible': admissible,
            'evaluated_at': datetime.now(timezone.utc).isoformat()
        }
