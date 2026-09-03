import math
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

class BaseDomainAdapter(ABC):
    """
    B3-DOM-01 Domain Adapter SDK base contract.
    Ensures all event domains produce uniform IF-001 and IF-006 artifacts.
    """
    @abstractmethod
    def map_event_definition(self, raw_spec: Dict[str, Any]) -> Dict[str, Any]:
        """Maps raw domain event data into a canonical IF-001 EventDefinition."""
        pass

    @abstractmethod
    def extract_features(self, pit_evidence: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Transforms PIT-filtered raw evidence into model features."""
        pass

    @abstractmethod
    def underwrite(self, features: Dict[str, Any], model_version: str = "v1.0") -> Dict[str, Any]:
        """Generates a sealed IF-006 UnderwritingArtifact without market price input."""
        pass

class EconomicIndicatorAdapter(BaseDomainAdapter):
    """
    Reference implementation for macroeconomic indicator events (e.g., BLS CPI, Fed Funds Rate).
    Demonstrates zero weather-domain leakage across the PDEUE core pipeline.
    """
    def __init__(self, domain_name: str = "MACROECONOMIC"):
        self.domain_name = domain_name

    def map_event_definition(self, raw_spec: Dict[str, Any]) -> Dict[str, Any]:
        event_id = raw_spec.get("event_id", f"EVT-ECON-{uuid.uuid4().hex[:8].upper()}")
        return {
            "event_id": event_id,
            "domain": self.domain_name,
            "series_id": raw_spec.get("series_id", "CPI-U-YOY"),
            "target_period": raw_spec.get("target_period", "2026-M08"),
            "threshold": float(raw_spec.get("threshold", 3.0)),
            "resolution_authority": raw_spec.get("resolution_authority", "US_BUREAU_OF_LABOR_STATISTICS"),
            "status": "REGISTERED",
            "created_at": datetime.now(timezone.utc).isoformat()
        }

    def extract_features(self, pit_evidence: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not pit_evidence:
            return {"observations_count": 0, "latest_consensus": 0.0, "historical_mean": 0.0, "dispersion": 0.25}
        
        estimates = [e.get("value", 0.0) for e in pit_evidence if "value" in e]
        if not estimates:
            return {"observations_count": 0, "latest_consensus": 0.0, "historical_mean": 0.0, "dispersion": 0.25}

        historical_mean = sum(estimates) / len(estimates)
        latest_consensus = estimates[-1]
        dispersion = round(max(estimates) - min(estimates), 4) if len(estimates) > 1 else 0.25
        
        return {
            "observations_count": len(estimates),
            "latest_consensus": round(latest_consensus, 4),
            "historical_mean": round(historical_mean, 4),
            "dispersion": dispersion
        }

    def underwrite(self, features: Dict[str, Any], model_version: str = "econ-logit-v1.0") -> Dict[str, Any]:
        consensus = features.get("latest_consensus", 0.0)
        dispersion = features.get("dispersion", 0.25)
        std_dev = max(0.10, dispersion)
        threshold = features.get("threshold", 3.0)
        
        z = (consensus - threshold) / std_dev
        est_prob = 1.0 / (1.0 + math.exp(-z))
        calibrated_prob = max(0.01, min(0.99, round(est_prob, 4)))

        return {
            "artifact_id": str(uuid.uuid4()),
            "domain": self.domain_name,
            "model_version": model_version,
            "calibrated_probability": calibrated_prob,
            "fair_value_cents": round(calibrated_prob * 100, 2),
            "uncertainty_score": round(min(1.0, std_dev), 4),
            "features_used": features,
            "sealed_at": datetime.now(timezone.utc).isoformat()
        }
