from datetime import datetime
from typing import List, Dict, Any

class PITSelector:
    """Point-in-Time (PIT) Knowledge Cutoff Engine."""
    def __init__(self, cutoff_time: datetime):
        self.cutoff_time = cutoff_time

    def filter_admissible_evidence(self, evidence_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        admissible = []
        for item in evidence_items:
            pub_time = datetime.fromisoformat(item["published_at"].replace("Z", "+00:00"))
            if pub_time <= self.cutoff_time:
                admissible.append(item)
        return admissible
