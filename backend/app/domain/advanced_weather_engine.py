import math
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from app.domain.station_bias_calibrator import StationBiasCalibrator

class AdvancedWeatherEngine:
    def __init__(self, station_calibrator: Optional[StationBiasCalibrator] = None):
        self.calibrator = station_calibrator or StationBiasCalibrator()

    @staticmethod
    def _normal_cdf(x: float, mu: float, sigma: float) -> float:
        if sigma <= 0.0:
            return 1.0 if x >= mu else 0.0
        z = (x - mu) / (sigma * math.sqrt(2.0))
        return 0.5 * (1.0 + math.erf(z))

    @staticmethod
    def _gpd_tail_survival(s: float, u: float, beta: float, xi: float) -> float:
        if s <= u:
            return 1.0
        if beta <= 0.0:
            return 0.0
        y = (s - u) / beta
        if abs(xi) < 1e-6:
            return math.exp(-y)
        val = 1.0 + xi * y
        if val <= 0.0:
            return 0.0 if xi > 0.0 else 1.0
        return math.pow(val, -1.0 / xi)

    def compute_ngr_distribution(self, ensemble_members: List[float], station_id: Optional[str] = None) -> Dict[str, float]:
        if not ensemble_members:
            return {'mu': 0.0, 'sigma': 1.0}
        if station_id:
            members = [self.calibrator.calibrate_observation(station_id, m)['calibrated_value'] for m in ensemble_members]
        else:
            members = list(ensemble_members)
        n = len(members)
        mu = sum(members) / n
        if n > 1:
            variance = sum((m - mu) ** 2 for m in members) / (n - 1)
            sigma = math.sqrt(max(variance, 0.01))
        else:
            sigma = 0.5
        return {'mu': round(mu, 4), 'sigma': round(sigma, 4)}

    def calculate_exceedance_probability(self, strike_temp_c: float, ensemble_members: List[float], station_id: Optional[str] = None, use_evt_tail: bool = True) -> Dict[str, Any]:
        dist = self.compute_ngr_distribution(ensemble_members, station_id=station_id)
        mu = dist['mu']
        sigma = dist['sigma']
        gaussian_prob = 1.0 - self._normal_cdf(strike_temp_c, mu, sigma)
        tail_threshold = mu + (1.5 * sigma)
        if use_evt_tail and strike_temp_c > tail_threshold:
            p_u = 1.0 - self._normal_cdf(tail_threshold, mu, sigma)
            beta = max(0.2, 0.8 * sigma)
            xi = 0.05
            p_tail_cond = self._gpd_tail_survival(strike_temp_c, tail_threshold, beta, xi)
            final_prob = min(0.9999, max(0.0001, p_u * p_tail_cond))
            method = 'EVT_GENERALIZED_PARETO'
        else:
            final_prob = min(0.9999, max(0.0001, gaussian_prob))
            method = 'NGR_GAUSSIAN'
        return {
            'strike_temp_c': strike_temp_c,
            'station_id': station_id,
            'mu': mu,
            'sigma': sigma,
            'method': method,
            'probability': round(final_prob, 4),
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
