"""
PDEUE Venue Opportunity Scanner & Lineage Router
Underwrites live venue depth against calibrated models and tags
candidate dispatches with the canonical 12-House lineal lineage identifier.
"""
from typing import Dict, Any, Optional

class VenueOpportunityScanner:
    """Multi-Venue Point-in-Time Underwriting & Lineal Allocation Scanner."""
    def __init__(self, min_edge_barrier: float = 0.28):
        self.min_edge_barrier = min_edge_barrier  # 28% margin barrier hurdle

    def evaluate_opportunity(
        self,
        orderbook: Dict[str, Any],
        weather_obs: Dict[str, Any],
        model_prob: float,
        target_house_id: int
    ) -> Dict[str, Any]:
        """
        Underwrites an orderbook against point-in-time weather observations.
        Embeds the target_house_id (1-12) directly into the dispatch contract.
        """
        if target_house_id < 1 or target_house_id > 12:
            raise ValueError(f"Invalid target_house_id: {target_house_id}. Must be between 1 and 12.")

        if not weather_obs.get("admissible", False):
            return {
                "status": "FILTERED_NON_ADMISSIBLE_EVIDENCE",
                "contract_ticker": orderbook.get("contract_ticker"),
                "admissible": False
            }

        yes_ask = orderbook.get("yes_ask", 1.0)
        yes_bid = orderbook.get("yes_bid", 0.0)

        # Net edge calculation
        edge_yes = round(model_prob - yes_ask, 4)
        edge_no = round((1.0 - model_prob) - (1.0 - yes_bid), 4)

        action = "PASS"
        chosen_edge = 0.0
        contract_price = 0.0

        if edge_yes >= self.min_edge_barrier:
            action = "BUY_YES"
            chosen_edge = edge_yes
            contract_price = yes_ask
        elif edge_no >= self.min_edge_barrier:
            action = "BUY_NO"
            chosen_edge = edge_no
            contract_price = round(1.0 - yes_bid, 4)

        is_qualified = (action != "PASS")
        house_code = f"HOUSE-{target_house_id:02d}"

        return {
            "opportunity_id": f"OPP-{orderbook.get('venue')}-{orderbook.get('contract_ticker')}",
            "venue": orderbook.get("venue"),
            "contract_ticker": orderbook.get("contract_ticker"),
            "target_house_id": target_house_id,
            "lineage_code": house_code,
            "model_prob": round(model_prob, 4),
            "market_price": round(contract_price, 4),
            "net_edge": round(chosen_edge, 4),
            "recommended_action": action,
            "edge_barrier_cleared": is_qualified,
            "status": "QUALIFIED" if is_qualified else "BELOW_EDGE_THRESHOLD",
            "microstructure": {
                "spread": orderbook.get("spread"),
                "mid_price": orderbook.get("mid_price"),
                "depth_cents": orderbook.get("total_depth_cents")
            }
        }
