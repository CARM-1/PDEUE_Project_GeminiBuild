import math
from typing import Dict, Any

class CryptoDomainAdapter:
    def underwrite_threshold(self, spec: Dict[str, Any]) -> float:
        spot = float(spec.get('spot_price', 100.0))
        strike = float(spec.get('strike_price', 100.0))
        vol = float(spec.get('annualized_vol', 0.60))
        days = float(spec.get('days_to_expiry', 7.0))
        if spot <= 0 or strike <= 0 or vol <= 0 or days <= 0:
            return 0.50
        t = days / 365.0
        sigma_sqrt_t = vol * math.sqrt(t)
        d2 = (math.log(spot / strike) - 0.5 * (vol ** 2) * t) / sigma_sqrt_t
        prob = 0.5 * (1.0 + math.erf(d2 / math.sqrt(2.0)))
        return max(0.01, min(0.99, round(prob, 4)))
