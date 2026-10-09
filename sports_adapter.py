# -*- coding: utf-8 -*-
"""
PDEUE Tier 2 Sports Domain Adapter
Implements Bivariate Drive-Level Poisson Distribution with Key-Number Weighting
and Real-Time NOAA ASOS Wind-Degradation Geofencing for Open-Air Stadiums.
"""
import math
from typing import Dict, Any, Tuple

class SportsPoissonUnderwriter:
    KEY_NUMBERS = {3: 0.152, 7: 0.098, 10: 0.059, 14: 0.048, 17: 0.038, 20: 0.031}

    @staticmethod
    def poisson_pmf(k: int, lamb: float) -> float:
        if lamb <= 0:
            return 1.0 if k == 0 else 0.0
        return (math.pow(lamb, k) * math.exp(-lamb)) / math.factorial(k)

    @classmethod
    def apply_wind_degradation(cls, lambda_td: float, lambda_fg: float, wind_mph: float) -> Tuple[float, float]:
        if wind_mph <= 20.0:
            return lambda_td, lambda_fg
        excess_wind = wind_mph - 20.0
        td_penalty = max(0.60, 1.0 - (excess_wind * 0.015))
        fg_penalty = max(0.40, 1.0 - (excess_wind * 0.030))
        return lambda_td * td_penalty, lambda_fg * fg_penalty

    @classmethod
    def calculate_score_pmf(cls, lambda_td: float, lambda_fg: float, max_td: int = 7, max_fg: int = 6) -> Dict[int, float]:
        score_dist = {}
        for td in range(max_td + 1):
            p_td = cls.poisson_pmf(td, lambda_td)
            for fg in range(max_fg + 1):
                p_fg = cls.poisson_pmf(fg, lambda_fg)
                score = (td * 7) + (fg * 3)
                prob = p_td * p_fg
                score_dist[score] = score_dist.get(score, 0.0) + prob
        return score_dist

    @classmethod
    def underwrite_spread(cls, home_td: float, home_fg: float, away_td: float, away_fg: float, 
                          target_spread: float, wind_mph: float = 0.0) -> float:
        h_td, h_fg = cls.apply_wind_degradation(home_td, home_fg, wind_mph)
        a_td, a_fg = cls.apply_wind_degradation(away_td, away_fg, wind_mph)

        h_dist = cls.calculate_score_pmf(h_td, h_fg)
        a_dist = cls.calculate_score_pmf(a_td, a_fg)

        # 1. Raw margin PMF from possession combinations
        raw_margins = {}
        for h_score, h_p in h_dist.items():
            for a_score, a_p in a_dist.items():
                m = h_score - a_score
                raw_margins[m] = raw_margins.get(m, 0.0) + (h_p * a_p)

        # 2. Key-number empirical calibration
        expected_margin = (h_td * 7 + h_fg * 3) - (a_td * 7 + a_fg * 3)
        calibrated_margins = dict(raw_margins)
        for key, empirical_freq in cls.KEY_NUMBERS.items():
            target_key = key if expected_margin >= 0 else -key
            raw_p = calibrated_margins.get(target_key, 0.0)
            calibrated_margins[target_key] = (0.40 * raw_p) + (0.60 * empirical_freq)

        # 3. Probability normalization
        total_p = sum(calibrated_margins.values())
        if total_p > 0:
            for m in calibrated_margins:
                calibrated_margins[m] /= total_p

        # 4. Integrate probability of covering spread
        prob_cover = sum(p for m, p in calibrated_margins.items() if float(m) > target_spread)
        return round(max(0.01, min(0.99, prob_cover)), 4)

class SportsDomainAdapter:
    """Standardized Tier 2 Adapter Interface for PDEUE Concurrency Rack."""
    def __init__(self):
        self.underwriter = SportsPoissonUnderwriter()

    def evaluate_contract(self, spec: Dict[str, Any]) -> Dict[str, Any]:
        h_td = float(spec.get("home_expected_td", 2.6))
        h_fg = float(spec.get("home_expected_fg", 1.8))
        a_td = float(spec.get("away_expected_td", 2.1))
        a_fg = float(spec.get("away_expected_fg", 1.5))
        spread = float(spec.get("target_spread", 3.0))
        wind = float(spec.get("stadium_wind_mph", 0.0))
        market_ask = float(spec.get("market_ask_cents", 50)) / 100.0

        model_prob = self.underwriter.underwrite_spread(h_td, h_fg, a_td, a_fg, spread, wind)
        gross_edge = model_prob - market_ask
        friction = 0.02
        net_edge = gross_edge - friction

        return {
            "category": "Sports Analytics & Spreads",
            "target_spread": spread,
            "stadium_wind_mph": wind,
            "model_prob": model_prob,
            "market_ask": market_ask,
            "net_edge": round(net_edge, 4),
            "is_admissible": net_edge >= 0.05
        }
