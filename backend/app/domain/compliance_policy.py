import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Set, Optional

class CompliancePolicyEngine:
    DEFAULT_ALLOWED_VENUES: Set[str] = {"KALSHI", "POLYMARKET"}
    DEFAULT_RESTRICTED_JURISDICTIONS: Set[str] = {"RESTRICTED_REGION_A", "SANCTIONED_ZONE_B"}

    def __init__(
        self,
        max_single_event_exposure: float = 25000.0,
        allowed_venues: Optional[Set[str]] = None,
        restricted_jurisdictions: Optional[Set[str]] = None
    ):
        self.max_single_event_exposure = max_single_event_exposure
        self.allowed_venues = allowed_venues or self.DEFAULT_ALLOWED_VENUES
        self.restricted_jurisdictions = restricted_jurisdictions or self.DEFAULT_RESTRICTED_JURISDICTIONS

    def evaluate_compliance(
        self,
        tenant_id: str,
        venue: str,
        jurisdiction: str,
        proposed_stake: float
    ) -> Dict[str, Any]:
        policy_flags: List[str] = []

        if venue.upper() not in self.allowed_venues:
            policy_flags.append(f"UNAUTHORIZED_VENUE_{venue.upper()}")

        if jurisdiction.upper() in self.restricted_jurisdictions:
            policy_flags.append(f"RESTRICTED_JURISDICTION_{jurisdiction.upper()}")

        if proposed_stake > self.max_single_event_exposure:
            policy_flags.append("EXPOSURE_LIMIT_EXCEEDED")

        if proposed_stake <= 0.0:
            policy_flags.append("INVALID_STAKE_AMOUNT")

        is_admissible = len(policy_flags) == 0

        return {
            "decision_id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "admissible": is_admissible,
            "venue": venue.upper(),
            "jurisdiction": jurisdiction.upper(),
            "proposed_stake": proposed_stake,
            "policy_flags": policy_flags,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
