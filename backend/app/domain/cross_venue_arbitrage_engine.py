from typing import Dict, Any, List, Optional

class CrossVenueArbitrageEngine:
    """B7-EXE Cross-Venue Parity Box Arbitrage Engine (Kalshi vs Polymarket)."""
    def __init__(self, fee_rate_kalshi: float = 0.01, fee_rate_poly: float = 0.0, min_profit_cents: int = 2):
        self.fee_rate_kalshi = fee_rate_kalshi
        self.fee_rate_poly = fee_rate_poly
        self.min_profit_cents = min_profit_cents

    def evaluate_parity_pair(
        self,
        kalshi_market: Dict[str, Any],
        poly_market: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        opportunities = []

        # Leg Scenario 1: Buy Kalshi YES + Buy Poly NO
        k_yes_ask = float(kalshi_market.get('yes_ask', 1.0))
        p_no_ask = float(poly_market.get('no_ask', 1.0 - float(poly_market.get('yes_bid', 0.0))))
        cost_kalshi_1 = k_yes_ask * (1.0 + self.fee_rate_kalshi)
        cost_poly_1 = p_no_ask * (1.0 + self.fee_rate_poly)
        total_cost_1 = cost_kalshi_1 + cost_poly_1

        if total_cost_1 < 1.0:
            net_profit_cents_1 = int(round((1.0 - total_cost_1) * 100))
            if net_profit_cents_1 >= self.min_profit_cents:
                opportunities.append({
                    'type': 'CROSS_VENUE_PARITY_BOX',
                    'pairing': 'KALSHI_YES_POLY_NO',
                    'kalshi_contract_id': kalshi_market.get('ticker', 'K-MKT'),
                    'poly_contract_id': poly_market.get('id', 'P-MKT'),
                    'kalshi_action': 'BUY_YES',
                    'poly_action': 'BUY_NO',
                    'kalshi_ask': k_yes_ask,
                    'poly_ask': p_no_ask,
                    'total_entry_cents': int(round(total_cost_1 * 100)),
                    'net_profit_cents': net_profit_cents_1
                })

        # Leg Scenario 2: Buy Kalshi NO + Buy Poly YES
        k_no_ask = float(kalshi_market.get('no_ask', 1.0 - float(kalshi_market.get('yes_bid', 0.0))))
        p_yes_ask = float(poly_market.get('yes_ask', 1.0))
        cost_kalshi_2 = k_no_ask * (1.0 + self.fee_rate_kalshi)
        cost_poly_2 = p_yes_ask * (1.0 + self.fee_rate_poly)
        total_cost_2 = cost_kalshi_2 + cost_poly_2

        if total_cost_2 < 1.0:
            net_profit_cents_2 = int(round((1.0 - total_cost_2) * 100))
            if net_profit_cents_2 >= self.min_profit_cents:
                opportunities.append({
                    'type': 'CROSS_VENUE_PARITY_BOX',
                    'pairing': 'KALSHI_NO_POLY_YES',
                    'kalshi_contract_id': kalshi_market.get('ticker', 'K-MKT'),
                    'poly_contract_id': poly_market.get('id', 'P-MKT'),
                    'kalshi_action': 'BUY_NO',
                    'poly_action': 'BUY_YES',
                    'kalshi_ask': k_no_ask,
                    'poly_ask': p_yes_ask,
                    'total_entry_cents': int(round(total_cost_2 * 100)),
                    'net_profit_cents': net_profit_cents_2
                })

        return opportunities
