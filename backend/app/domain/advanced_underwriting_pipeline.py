from datetime import datetime
from typing import Dict, Any, List, Optional
from app.domain.pit_selector import PITSelector
from app.domain.station_bias_calibrator import StationBiasCalibrator
from app.domain.advanced_weather_engine import AdvancedWeatherEngine
from app.domain.market_comparator import MarketComparator

class AdvancedUnderwritingPipeline:
    """
    Asymmetric Weather Underwriting Pipeline.
    Combines PIT evidence filtering, station bias calibration, NGR/EVT modeling, and market edge calculation.
    """
    def __init__(self, station_calibrator: Optional[StationBiasCalibrator] = None):
        self.calibrator = station_calibrator or StationBiasCalibrator()
        self.weather_engine = AdvancedWeatherEngine(station_calibrator=self.calibrator)
        self.comparator = MarketComparator()

    def run_underwriting(
        self,
        cutoff: datetime,
        evidence_items: List[Dict[str, Any]],
        market_snapshot: Dict[str, Any],
        strike_temp_c: float,
        station_id: str = 'KORD'
    ) -> Dict[str, Any]:
        pit = PITSelector(cutoff_time=cutoff)
        admissible = pit.filter_admissible_evidence(evidence_items)
        
        ensemble_members: List[float] = []
        for item in admissible:
            members = item.get('payload', {}).get('member_temperatures_c', [])
            if members:
                ensemble_members.extend(members)
            elif 'temperature_c' in item.get('payload', {}):
                ensemble_members.append(item['payload']['temperature_c'])
        
        if not ensemble_members:
            return {
                'admissible_count': 0,
                'model_probability': 0.0,
                'distribution': {'mu': 0.0, 'sigma': 0.0, 'method': 'NO_DATA'},
                'edge_metrics': self.comparator.calculate_edge(0.0, market_snapshot)
            }
        
        prob_assessment = self.weather_engine.calculate_exceedance_probability(
            strike_temp_c=strike_temp_c,
            ensemble_members=ensemble_members,
            station_id=station_id
        )
        
        model_prob = prob_assessment['probability']
        edge_metrics = self.comparator.calculate_edge(model_prob, market_snapshot)
        
        return {
            'admissible_count': len(admissible),
            'station_id': station_id,
            'strike_temp_c': strike_temp_c,
            'model_probability': model_prob,
            'distribution': {
                'mu': prob_assessment['mu'],
                'sigma': prob_assessment['sigma'],
                'method': prob_assessment['method']
            },
            'edge_metrics': edge_metrics
        }
