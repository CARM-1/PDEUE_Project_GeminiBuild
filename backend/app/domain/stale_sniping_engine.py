from typing import Dict, Any, List, Optional

class StaleQuoteSnipingEngine:
    def __init__(self):
        self.sniped_opportunities: List[Dict[str, Any]] = []

    def evaluate_quote_staleness(
        self,
        public_ground_truth: Dict[str, Any],
        resting_quote: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        ground_time = public_ground_truth.get('published_at_epoch', 0.0)
        quote_time = resting_quote.get('quoted_at_epoch', 0.0)
        true_probability = public_ground_truth.get('true_probability', 0.5)
        quote_ask = resting_quote.get('ask_price', 0.5)
        if ground_time > quote_time and (true_probability - quote_ask) >= 0.04:
            edge = round(true_probability - quote_ask, 4)
            sniped = {
                'ticker': resting_quote.get('ticker'),
                'venue': resting_quote.get('venue'),
                'stale_ask': quote_ask,
                'true_probability': true_probability,
                'captured_edge': edge,
                'action': 'SWEEP_STALE_LIQUIDITY'
            }
            self.sniped_opportunities.append(sniped)
            return sniped
        return None
