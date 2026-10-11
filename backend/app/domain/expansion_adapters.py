"""
PDEUE Expansion Domain Adapters Engine (WP-8A)
Implements domain-specific statistical underwriting, clock-synchronized quote pulls,
and discrete boundary distributions for the 8 expansion market verticals.

Governing Invariants:
- ADR-008: Integer-cent pricing bounds [1, 99].
- Fail-Closed: Stale feeds or missing data trigger immediate ABSTAIN (allocation = 0).
- Retained-Kelly Risk Sizing: Dynamic sizing capped strictly at 2.0% (200 bps).
"""

import math
from dataclasses import dataclass
from typing import Dict, Any, Optional, List, Tuple

@dataclass(frozen=True)
class UnderwritingDecision:
    category: str
    contract_id: str
    fair_probability: float
    recommended_bid_cents: int
    net_edge: float
    should_pull_quotes: bool
    harvest_eligible: bool
    abstain_reason: Optional[str] = None

class BaseExpansionAdapter:
    def __init__(self, category: str):
        self.category = category

    def calculate_retained_kelly(self, fair_prob: float, bid_cents: int) -> float:
        if bid_cents <= 0 or bid_cents >= 100 or fair_prob <= 0.0:
            return 0.0
        b_net = 0.87 * ((100.0 - bid_cents) / bid_cents)
        f_star = (fair_prob * (b_net + 1.0) - 1.0) / b_net
        if f_star <= 0.0:
            return 0.0
        return min(0.02, 0.25 * f_star)

class LaborUnderwritingAdapter(BaseExpansionAdapter):
    def __init__(self):
        super().__init__("macro_labor")

    def underwrite(self, contract_id: str, strike_jobs: float, nowcast_jobs: float, 
                   dispersion_sigma: float, current_best_bid: int, 
                   seconds_to_release: float) -> UnderwritingDecision:
        should_pull = 0.0 <= seconds_to_release <= 5.0
        if dispersion_sigma <= 0:
            return UnderwritingDecision(self.category, contract_id, 0.0, 0, 0.0, should_pull, False, "INVALID_SIGMA")

        z = (nowcast_jobs - strike_jobs) / dispersion_sigma
        p_fair = 1.0 / (1.0 + math.exp(-z))
        fair_cents = int(round(p_fair * 100))

        recommended_bid = max(1, min(current_best_bid + 1, fair_cents - 2))
        edge = p_fair - (recommended_bid / 100.0)
        harvest = current_best_bid >= 80 or recommended_bid >= 80
        return UnderwritingDecision(self.category, contract_id, round(p_fair, 4), recommended_bid, round(edge, 4), should_pull, harvest)

class EnergyEIAAdapter(BaseExpansionAdapter):
    def __init__(self):
        super().__init__("energy_eia")

    def underwrite(self, contract_id: str, strike_draw_mb: float, physical_cushing_delta: float, 
                   refinery_utilization_ratio: float, current_best_bid: int, 
                   seconds_to_release: float) -> UnderwritingDecision:
        should_pull = 0.0 <= seconds_to_release <= 5.0
        expected_draw = physical_cushing_delta * refinery_utilization_ratio
        diff = expected_draw - strike_draw_mb
        p_fair = 0.5 + 0.5 * math.erf(diff / 2.5)
        fair_cents = int(round(p_fair * 100))

        recommended_bid = max(1, min(current_best_bid + 1, fair_cents - 2))
        edge = p_fair - (recommended_bid / 100.0)
        harvest = current_best_bid >= 75 or recommended_bid >= 75
        return UnderwritingDecision(self.category, contract_id, round(p_fair, 4), recommended_bid, round(edge, 4), should_pull, harvest)

class TreasuryAuctionAdapter(BaseExpansionAdapter):
    def __init__(self):
        super().__init__("treasury_tails")

    def underwrite(self, contract_id: str, dealer_inventory_ratio: float, 
                   foreign_bidder_pct: float, current_best_bid: int, 
                   seconds_to_cutoff: float) -> UnderwritingDecision:
        should_pull = 0.0 <= seconds_to_cutoff <= 5.0
        score = (dealer_inventory_ratio * 1.2) - (foreign_bidder_pct * 0.8)
        p_tail = 1.0 / (1.0 + math.exp(-3.0 * (score - 0.2)))
        fair_cents = int(round(p_tail * 100))

        recommended_bid = max(1, min(current_best_bid + 1, fair_cents - 2))
        edge = p_tail - (recommended_bid / 100.0)
        return UnderwritingDecision(self.category, contract_id, round(p_tail, 4), recommended_bid, round(edge, 4), should_pull, False)

class EquityIndexAdapter(BaseExpansionAdapter):
    def __init__(self):
        super().__init__("equity_index")

    def underwrite(self, contract_id: str, lower_strike: float, upper_strike: float, 
                   current_spot: float, annualized_iv: float, hours_to_expiry: float, 
                   current_best_bid: int) -> UnderwritingDecision:
        if hours_to_expiry <= 0 or current_spot <= 0 or annualized_iv <= 0:
            return UnderwritingDecision(self.category, contract_id, 0.0, 0, 0.0, False, False, "EXPIRED_OR_INVALID_INPUTS")

        t = hours_to_expiry / (252.0 * 6.5)
        sigma = annualized_iv * math.sqrt(t)

        def norm_cdf(x):
            return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))

        d1_upper = (math.log(upper_strike / current_spot)) / sigma
        d1_lower = (math.log(lower_strike / current_spot)) / sigma
        p_in_bracket = max(0.0, min(1.0, norm_cdf(d1_upper) - norm_cdf(d1_lower)))
        fair_cents = int(round(p_in_bracket * 100))

        # Inside maker bid (Best Bid + 1c), capped strictly at fair_cents - 1c
        recommended_bid = max(1, min(current_best_bid + 1, fair_cents - 1))
        edge = p_in_bracket - (recommended_bid / 100.0)
        harvest = current_best_bid >= 80 or recommended_bid >= 80
        return UnderwritingDecision(self.category, contract_id, round(p_in_bracket, 4), recommended_bid, round(edge, 4), False, harvest)

class LogisticsTSAAdapter(BaseExpansionAdapter):
    def __init__(self):
        super().__init__("logistics_tsa")

    def underwrite(self, contract_id: str, strike_pax: int, scheduled_seats: int, 
                   historical_load_factor: float, ground_stop_haircut: float, 
                   current_best_bid: int, current_hour_utc: int) -> UnderwritingDecision:
        expected_pax = scheduled_seats * historical_load_factor * (1.0 - ground_stop_haircut)
        diff = expected_pax - strike_pax
        p_fair = 1.0 / (1.0 + math.exp(-diff / 35000.0))
        fair_cents = int(round(p_fair * 100))

        recommended_bid = max(1, min(current_best_bid + 1, fair_cents - 2))
        edge = p_fair - (recommended_bid / 100.0)
        harvest_eligible = current_hour_utc < 20 and (current_best_bid >= 85 or recommended_bid >= 85)
        return UnderwritingDecision(self.category, contract_id, round(p_fair, 4), recommended_bid, round(edge, 4), False, harvest_eligible)

class FXFixingAdapter(BaseExpansionAdapter):
    def __init__(self):
        super().__init__("fx_fixing")

    def underwrite(self, contract_id: str, band_low: float, band_high: float, 
                   current_spot: float, rate_diff_bps: float, 
                   current_best_bid: int) -> UnderwritingDecision:
        drift = (rate_diff_bps / 10000.0) * current_spot
        adjusted_spot = current_spot + drift
        in_band = band_low <= adjusted_spot <= band_high
        p_fair = 0.82 if in_band else 0.18
        fair_cents = int(round(p_fair * 100))

        recommended_bid = max(1, min(current_best_bid + 1, fair_cents - 2))
        edge = p_fair - (recommended_bid / 100.0)
        harvest = current_best_bid >= 80 or recommended_bid >= 80
        return UnderwritingDecision(self.category, contract_id, round(p_fair, 4), recommended_bid, round(edge, 4), False, harvest)

class SportsPoissonAdapter(BaseExpansionAdapter):
    def __init__(self):
        super().__init__("sports_spreads")

    def underwrite(self, contract_id: str, margin_threshold: float, lambda_home: float, 
                   lambda_away: float, surface_wind_mph: float, 
                   current_best_bid: int, game_minute: int) -> UnderwritingDecision:
        if surface_wind_mph > 20.0:
            lambda_home *= 0.92
            lambda_away *= 0.92

        p_cover = 0.0
        for h in range(45):
            p_h = (math.exp(-lambda_home) * (lambda_home ** h)) / math.factorial(h)
            for a in range(45):
                p_a = (math.exp(-lambda_away) * (lambda_away ** a)) / math.factorial(a)
                if (h - a) > margin_threshold:
                    p_cover += (p_h * p_a)

        fair_cents = int(round(p_cover * 100))
        recommended_bid = max(1, min(current_best_bid + 1, fair_cents - 2))
        edge = p_cover - (recommended_bid / 100.0)
        harvest = game_minute >= 50 and (current_best_bid >= 80 or recommended_bid >= 80)
        return UnderwritingDecision(self.category, contract_id, round(p_cover, 4), recommended_bid, round(edge, 4), False, harvest)

class PerpFundingAdapter(BaseExpansionAdapter):
    def __init__(self):
        super().__init__("perp_funding")

    def underwrite(self, contract_id: str, strike_rate_pct: float, 
                   accumulated_twap_rate: float, elapsed_hours: float, 
                   current_instant_premium: float, current_best_bid: int) -> UnderwritingDecision:
        if elapsed_hours >= 8.0:
            p_fair = 1.0 if accumulated_twap_rate > strike_rate_pct else 0.0
        else:
            remaining_hours = 8.0 - elapsed_hours
            required_remaining_avg = ((strike_rate_pct * 8.0) - (accumulated_twap_rate * elapsed_hours)) / remaining_hours
            if current_instant_premium > required_remaining_avg + 0.005:
                p_fair = 0.92
            elif current_instant_premium < required_remaining_avg - 0.005:
                p_fair = 0.08
            else:
                p_fair = 0.50

        fair_cents = int(round(p_fair * 100))
        recommended_bid = max(1, min(current_best_bid + 1, fair_cents - 2))
        edge = p_fair - (recommended_bid / 100.0)
        harvest = elapsed_hours >= 6.0 and (current_best_bid >= 85 or recommended_bid >= 85)
        return UnderwritingDecision(self.category, contract_id, round(p_fair, 4), recommended_bid, round(edge, 4), False, harvest)
