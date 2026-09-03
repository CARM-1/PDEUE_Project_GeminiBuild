from typing import Dict, Any, List, Optional
from datetime import datetime

class EnsembleWeatherAdapter:
    """
    Adapter for multi-member Numerical Weather Prediction (NWP) ensemble feeds.
    Ingests ensemble temperature spreads with strict point-in-time metadata.
    """
    def parse_ensemble_payload(self, raw_payload: Dict[str, Any]) -> Dict[str, Any]:
        if 'station_id' not in raw_payload or 'member_forecasts_c' not in raw_payload:
            raise ValueError('Missing required ensemble payload fields')
        return {
            'evidence_id': raw_payload.get('evidence_id', 'EV-ENS-001'),
            'source': raw_payload.get('model_source', 'NWP_ENSEMBLE_OPEN'),
            'station_id': raw_payload['station_id'].upper(),
            'published_at': raw_payload.get('published_at', datetime.utcnow().isoformat() + 'Z'),
            'payload': {
                'member_temperatures_c': [float(t) for t in raw_payload['member_forecasts_c']],
                'ensemble_size': len(raw_payload['member_forecasts_c']),
                'target_date': raw_payload.get('target_date')
            }
        }
