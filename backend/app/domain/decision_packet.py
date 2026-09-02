import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List
from app.domain.calibration import ProbabilityCalibrationEngine
from app.domain.portfolio_allocation import PortfolioAllocationEngine

class DecisionPacketBuilder:
    def __init__(self, kelly_fraction: float = 0.25, max_position_pct: float = 0.10):
        self.calibrator = ProbabilityCalibrationEngine()
        self.allocator = PortfolioAllocationEngine(kelly_fraction=kelly_fraction, max_position_pct=max_position_pct)

    def build_decision_packet(
        self,
        event_id: str,
        raw_prob: float,
        yes_ask: float,
        total_capital: float,
        reliability_factor: float = 1.0
    ) -> Dict[str, Any]:
        calibrated = self.calibrator.calibrate_probability(raw_prob, reliability_factor)
        allocation = self.allocator.calculate_kelly_stake(calibrated, yes_ask, total_capital)
        
        edge = calibrated - yes_ask
        operating_mode = "NORMAL" if edge > 0.0 else "BLOCKED"
        blocked_reasons = [] if edge > 0.0 else ["NO_STATISTICAL_EDGE"]

        return {
            "packet_id": str(uuid.uuid4()),
            "event_id": event_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "operating_mode": operating_mode,
            "underwriting": {
                "raw_prob": raw_prob,
                "calibrated_prob": calibrated,
                "reliability_factor": reliability_factor
            },
            "risk_assessment": {
                "yes_ask": yes_ask,
                "edge": round(edge, 4)
            },
            "capital_bid": allocation,
            "blocked_reasons": blocked_reasons
        }
