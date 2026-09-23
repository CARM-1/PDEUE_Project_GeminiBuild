"""
PDEUE Quarter-Kelly Multi-House Order Dispatcher
Calculates defensive position sizing and attributes capital commitments
across member SCMAs assigned to the 12 canonical House Lines.
"""
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from app.domain.lineage_hierarchy import get_lineage_service

class QuarterKellyDispatcher:
    """Computes fractional Kelly stakes and manages margin commitments."""

    HOUSE_ALLOCATION_REGISTRY: Dict[int, List[Dict[str, Any]]] = {
        1: [
            {"scma_id": "SCMA-FOUNDER_-C8575D7E", "name": "Founder Chief Admin", "cash_cents": 500000, "risk_dial": 0.02},
            {"scma_id": "SCMA-ELEANOR_-B2B31C9E", "name": "Eleanor Vance", "cash_cents": 125000, "risk_dial": 0.015}
        ],
        2: [
            {"scma_id": "SCMA-JULIAN_-A1F98B21", "name": "Julian Vance", "cash_cents": 25000, "risk_dial": 0.01}
        ]
    }

    def __init__(self, kelly_fraction: float = 0.25):
        self.kelly_fraction = kelly_fraction  # Quarter-Kelly (1/4)

    def calculate_sizing(
        self,
        model_prob: float,
        market_price: float,
        available_cash_cents: int,
        risk_dial: float
    ) -> Dict[str, Any]:
        """
        Calculates position stake using Quarter-Kelly bounded by member risk dial.
        For binary contracts:
          Full Kelly f* = (b * p - q) / b = (model_prob - market_price) / (1 - market_price)
        """
        if market_price >= 1.0 or market_price <= 0.0:
            return {
                "stake_cents": 0,
                "contract_quantity": 0,
                "contracts": 0,
                "fraction": 0.0,
                "effective_fraction": 0.0,
                "reason": "INVALID_PRICE"
            }

        edge = model_prob - market_price
        if edge <= 0.0:
            return {
                "stake_cents": 0,
                "contract_quantity": 0,
                "contracts": 0,
                "fraction": 0.0,
                "effective_fraction": 0.0,
                "reason": "NEGATIVE_EDGE"
            }

        b = (1.0 - market_price) / market_price
        full_kelly = (b * model_prob - (1.0 - model_prob)) / b
        quarter_kelly = round(self.kelly_fraction * full_kelly, 4)

        # Enforce down-scaled member risk dial ceiling
        effective_fraction = max(0.0, min(quarter_kelly, risk_dial))
        target_cents = int(available_cash_cents * effective_fraction)
        
        # Contract cost in cents
        contract_cost_cents = int(round(market_price * 100))
        contracts = target_cents // contract_cost_cents if contract_cost_cents > 0 else 0
        actual_stake_cents = contracts * contract_cost_cents

        return {
            "model_prob": model_prob,
            "market_price": market_price,
            "net_edge": round(edge, 4),
            "full_kelly": round(full_kelly, 4),
            "quarter_kelly": quarter_kelly,
            "risk_dial_applied": risk_dial,
            "effective_fraction": effective_fraction,
            "stake_cents": actual_stake_cents,
            "contract_quantity": contracts,
            "contracts": contracts,
            "unit_cost_cents": contract_cost_cents
        }

    def dispatch_opportunity(
        self,
        contract_ticker: str,
        venue: str,
        target_house_id: int,
        side: str,
        market_price: float,
        model_prob: float
    ) -> Dict[str, Any]:
        """Allocates a staged opportunity to member accounts in the target House."""
        if target_house_id < 1 or target_house_id > 12:
            raise ValueError(f"Invalid House ID: {target_house_id}. Must be between 1 and 12.")

        house_code = f"HOUSE-{target_house_id:02d}"
        house = get_lineage_service().get_house_summary(target_house_id)
        if house["status"] == "QUARANTINED":
            return {
                "dispatch_id": f"DSP-{venue[:3]}-{contract_ticker}-{target_house_id}",
                "contract_ticker": contract_ticker,
                "venue": venue,
                "target_house_id": target_house_id,
                "lineage_code": house_code,
                "side": side,
                "market_price": market_price,
                "total_committed_cents": 0,
                "total_quantity": 0,
                "status": "SKIPPED_HOUSE_QUARANTINED",
                "member_allocations": [],
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        assigned_members = self.HOUSE_ALLOCATION_REGISTRY.get(
            target_house_id,
            [{"scma_id": f"SCMA-{house_code}-SEED", "name": f"House {target_house_id} Seed", "cash_cents": 100000, "risk_dial": 0.01}]
        )

        allocations = []
        total_committed_cents = 0
        total_quantity = 0

        for member in assigned_members:
            sizing = self.calculate_sizing(
                model_prob=model_prob,
                market_price=market_price,
                available_cash_cents=member["cash_cents"],
                risk_dial=member["risk_dial"]
            )
            if sizing["contract_quantity"] > 0:
                allocations.append({
                    "scma_id": member["scma_id"],
                    "member_name": member["name"],
                    "allocated_cents": sizing["stake_cents"],
                    "contract_qty": sizing["contract_quantity"],
                    "effective_risk_pct": round(sizing["effective_fraction"] * 100, 2)
                })
                total_committed_cents += sizing["stake_cents"]
                total_quantity += sizing["contract_quantity"]

        return {
            "dispatch_id": f"DSP-{venue[:3]}-{contract_ticker}-{target_house_id}",
            "contract_ticker": contract_ticker,
            "venue": venue,
            "target_house_id": target_house_id,
            "lineage_code": house_code,
            "side": side,
            "market_price": market_price,
            "total_committed_cents": total_committed_cents,
            "total_quantity": total_quantity,
            "status": "RESTING_MAKER",
            "member_allocations": allocations,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
def calculate_quarter_kelly_size(self, market_price: float, model_prob: float, member_cash_cents: int = 500000, member_risk_dial: float = 0.02) -> dict:
        """Alias for calculate_quarter_kelly_allocation for workspace integration."""
        if hasattr(self, "calculate_quarter_kelly_allocation"):
            return self.calculate_quarter_kelly_allocation(market_price, model_prob, member_cash_cents, member_risk_dial)
        elif hasattr(self, "calculate_allocation"):
            return self.calculate_allocation(market_price, model_prob, member_cash_cents, member_risk_dial)
        edge = model_prob - market_price
        if edge <= 0:
            return {"order_authorized": False, "rejection_reason": "NO_POSITIVE_EDGE", "total_committed_cents": 0, "contracts_to_buy": 0}
        cap = int(member_cash_cents * min(0.05, member_risk_dial))
        qty = max(1, int(cap / max(1, int(market_price * 100))))
        return {"order_authorized": True, "total_committed_cents": int(qty * market_price * 100), "contracts_to_buy": qty}
