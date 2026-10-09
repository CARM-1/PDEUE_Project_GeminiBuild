# -*- coding: utf-8 -*-
"""
PDEUE Domain: Priority Eviction Engine
Governs concurrency slot preemption, filled inventory immunity, and anti-churn rules.
"""
import time
from typing import List, Dict, Any

class PriorityEvictionManager:
    def __init__(self, capacity: int = 12, min_edge_hurdle: float = 0.20, min_advantage: float = 0.10):
        self.capacity = capacity
        self.min_edge_hurdle = min_edge_hurdle
        self.min_advantage = min_advantage

    def evaluate_eviction(self, active_slots: List[Dict[str, Any]], candidate: Dict[str, Any]) -> Dict[str, Any]:
        cand_edge = float(candidate.get("net_edge", 0.0))
        
        if cand_edge < self.min_edge_hurdle:
            return {"action": "REJECT", "reason": "CANDIDATE_BELOW_MIN_EDGE_HURDLE", "evicted_slot": None}

        # Filled positions are strictly immune
        evictable = [
            s for s in active_slots 
            if s.get("status") in ("RESTING_MAKER", "PAPER_MAKER") and not s.get("is_filled", False)
        ]

        if not evictable:
            return {"action": "REJECT", "reason": "NO_EVICTABLE_RESTING_ORDERS_AVAILABLE", "evicted_slot": None}

        weakest = min(evictable, key=lambda s: float(s.get("net_edge", 1.0)))
        weakest_edge = float(weakest.get("net_edge", 1.0))
        edge_delta = cand_edge - weakest_edge

        if edge_delta >= self.min_advantage:
            return {
                "action": "EVICT_AND_REPLACE",
                "target_slot": weakest.get("slot_index"),
                "evicted_ticker": weakest.get("contract_ticker"),
                "resting_edge": weakest_edge,
                "candidate_edge": cand_edge,
                "edge_delta": round(edge_delta, 4),
                "reason": "PREEMPTION_ADVANTAGE_MET"
            }

        return {
            "action": "REJECT",
            "reason": "INSUFFICIENT_EDGE_ADVANTAGE",
            "resting_edge": weakest_edge,
            "candidate_edge": cand_edge,
            "edge_delta": round(edge_delta, 4),
            "evicted_slot": None
        }
