import uuid
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Set

class SourceQualificationRegistry:
    VALID_TIERS: Set[str] = {"TIER_1", "TIER_2", "TIER_3"}

    def __init__(self):
        self.registry: Dict[str, Dict[str, Any]] = {}

    def register_source(
        self,
        source_id: str,
        name: str,
        license_type: str,
        quality_tier: str,
        is_public_or_lawful: bool = True,
        commercial_allowed: bool = True,
        expires_at: Optional[str] = None
    ) -> Dict[str, Any]:
        if quality_tier not in self.VALID_TIERS:
            raise ValueError(f"Invalid quality tier: {quality_tier}")
        
        record = {
            "source_id": source_id,
            "name": name,
            "license_type": license_type,
            "quality_tier": quality_tier,
            "is_public_or_lawful": is_public_or_lawful,
            "commercial_allowed": commercial_allowed,
            "expires_at": expires_at,
            "registered_at": datetime.now(timezone.utc).isoformat()
        }
        self.registry[source_id] = record
        return record

    def evaluate_source(self, source_id: str, current_time_iso: Optional[str] = None) -> Dict[str, Any]:
        source = self.registry.get(source_id)
        if not source:
            return {
                "qualification_id": str(uuid.uuid4()),
                "source_id": source_id,
                "qualified": False,
                "reason": "SOURCE_NOT_REGISTERED",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

        if not source["is_public_or_lawful"]:
            return {
                "qualification_id": str(uuid.uuid4()),
                "source_id": source_id,
                "qualified": False,
                "reason": "UNLAWFUL_OR_NONPUBLIC_DATA",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

        if not source["commercial_allowed"]:
            return {
                "qualification_id": str(uuid.uuid4()),
                "source_id": source_id,
                "qualified": False,
                "reason": "COMMERCIAL_USE_PROHIBITED",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

        if source["expires_at"]:
            eval_time = current_time_iso or datetime.now(timezone.utc).isoformat()
            if eval_time > source["expires_at"]:
                return {
                    "qualification_id": str(uuid.uuid4()),
                    "source_id": source_id,
                    "qualified": False,
                    "reason": "SOURCE_LICENSE_EXPIRED",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }

        return {
            "qualification_id": str(uuid.uuid4()),
            "source_id": source_id,
            "qualified": True,
            "quality_tier": source["quality_tier"],
            "license_type": source["license_type"],
            "reason": "QUALIFIED",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
