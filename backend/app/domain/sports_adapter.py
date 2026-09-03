import math
from typing import Dict, Any

class SportsDomainAdapter:
    DEFAULT_NFL_SIGMA = 13.5

    def underwrite_game(self, spec: Dict[str, Any]) -> float:
        proj_margin = float(spec.get('projected_margin', 0.0))
        target_spread = float(spec.get('target_spread', 0.0))
        sigma = float(spec.get('sigma', self.DEFAULT_NFL_SIGMA))
        if sigma <= 0:
            sigma = self.DEFAULT_NFL_SIGMA
        z = (proj_margin - target_spread) / sigma
        prob = 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))
        return max(0.01, min(0.99, round(prob, 4)))
