# -*- coding: utf-8 -*-
"""
PDEUE Tier 2 U.S. Treasury Auction Tail Adapter
Models When-Issued (WI) vs. Stop-Out yield dispersion, Bid-to-Cover (BTC)
momentum, and primary dealer absorption pressure for Fiscal Service auctions.
"""
import math
from typing import Dict, Any

class TreasuryTailUnderwriter:
    """Calculates auction tail exceedance probability via asymmetric Student-t dispersion."""
    
    @staticmethod
    def calculate_tail_probability(expected_tail_bps: float, strike_tail_bps: float, 
                                   dealer_absorption_pct: float = 18.0, 
                                   btc_delta: float = 0.0) -> float:
        sigma = 1.20
        absorption_drift = (dealer_absorption_pct - 18.0) * 0.08
        btc_drift = -1.0 * btc_delta * 0.75
        
        adjusted_mu = expected_tail_bps + absorption_drift + btc_drift
        z = (strike_tail_bps - adjusted_mu) / sigma
        
        prob_exceed = 1.0 / (1.0 + math.exp(z * 1.60))
        return round(max(0.01, min(0.99, prob_exceed)), 4)

class TreasuryDomainAdapter:
    """Standardized Tier 2 Adapter Interface for PDEUE Concurrency Rack."""
    def __init__(self):
        self.underwriter = TreasuryTailUnderwriter()

    def evaluate_contract(self, spec: Dict[str, Any]) -> Dict[str, Any]:
        exp_tail = float(spec.get("expected_tail_bps", 0.2))
        strike_tail = float(spec.get("strike_tail_bps", 1.0))
        absorption = float(spec.get("dealer_absorption_pct", 18.0))
        btc_delta = float(spec.get("btc_delta", 0.0))
        market_ask = float(spec.get("market_ask_cents", 40)) / 100.0

        model_prob = self.underwriter.calculate_tail_probability(
            exp_tail, strike_tail, absorption, btc_delta
        )
        gross_edge = model_prob - market_ask
        friction = 0.02
        net_edge = gross_edge - friction

        return {
            "category": "U.S. Treasury Auction Tails",
            "strike_tail_bps": strike_tail,
            "expected_tail_bps": exp_tail,
            "model_prob": model_prob,
            "market_ask": market_ask,
            "net_edge": round(net_edge, 4),
            "is_admissible": net_edge >= 0.05
        }
