from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

class LineageHierarchyService:
    """Authoritative registry for House lines, subordinate management, and consensus."""

    CANONICAL_HOUSES: Dict[int, Dict[str, Any]] = {
        1: {
            "house_id": 1,
            "lineage_code": "HOUSE-01",
            "name": "House of the Founder (Vance Prime)",
            "leader_name": "Eleanor Vance",
            "leader_role": "CLASS_H_LEADER",
            "members": [
                {
                    "scma_id": "SCMA-FOUNDER_-C8575D7E",
                    "name": "Founder Chief Admin",
                    "cash_cents": 500000,
                    "risk_dial": 0.02,
                    "status": "ACTIVE",
                    "open_orders": ["KX-MIA-FRZ-32"]
                },
                {
                    "scma_id": "SCMA-ELEANOR_-B2B31C9E",
                    "name": "Eleanor Vance",
                    "cash_cents": 125000,
                    "risk_dial": 0.015,
                    "status": "ACTIVE",
                    "open_orders": []
                }
            ],
            "governance_seat": True
        },
        2: {
            "house_id": 2,
            "lineage_code": "HOUSE-02",
            "name": "House of Julian (Secondary Line)",
            "leader_name": "Julian Vance",
            "leader_role": "CLASS_H_LEADER",
            "members": [
                {
                    "scma_id": "SCMA-JULIAN_-A1F98B21",
                    "name": "Julian Vance",
                    "cash_cents": 25000,
                    "risk_dial": 0.01,
                    "status": "ACTIVE",
                    "open_orders": ["POLY-239496"]
                }
            ],
            "governance_seat": True
        }
    }

    def __init__(self):
        for hid in range(3, 13):
            if hid not in self.CANONICAL_HOUSES:
                code = f"HOUSE-{hid:02d}"
                self.CANONICAL_HOUSES[hid] = {
                    "house_id": hid,
                    "lineage_code": code,
                    "name": f"House of Lineage {hid:02d}",
                    "leader_name": f"Delegate {hid:02d}",
                    "leader_role": "CLASS_H_LEADER",
                    "members": [
                        {
                            "scma_id": f"SCMA-{code}-SEED",
                            "name": f"Member {hid:02d}-A",
                            "cash_cents": 100000,
                            "risk_dial": 0.01,
                            "status": "ACTIVE",
                            "open_orders": []
                        }
                    ],
                    "governance_seat": True
                }

    def get_house_summary(self, house_id: int) -> Dict[str, Any]:
        if house_id < 1 or house_id > 12:
            raise ValueError(f"Invalid House ID: {house_id}. Must be between 1 and 12.")

        house = self.CANONICAL_HOUSES[house_id]
        total_cash_cents = sum(m["cash_cents"] for m in house["members"])
        active_members = [m for m in house["members"] if m["status"] == "ACTIVE"]
        avg_risk_dial = sum(m["risk_dial"] for m in active_members) / len(active_members) if active_members else 0.0

        return {
            "house_id": house["house_id"],
            "lineage_code": house["lineage_code"],
            "name": house["name"],
            "leader_name": house["leader_name"],
            "leader_role": house["leader_role"],
            "member_count": len(house["members"]),
            "total_cash_cents": total_cash_cents,
            "total_cash_formatted": f"${total_cash_cents / 100.0:,.2f}",
            "average_risk_dial_pct": round(avg_risk_dial * 100, 2),
            "members": house["members"]
        }

    def list_all_houses(self) -> List[Dict[str, Any]]:
        return [self.get_house_summary(hid) for hid in range(1, 13)]

    def cancel_subordinate_orders(self, house_id: int, scma_id: str) -> Dict[str, Any]:
        house = self.CANONICAL_HOUSES.get(house_id)
        if not house:
            raise ValueError(f"House {house_id} not found.")

        target = next((m for m in house["members"] if m["scma_id"] == scma_id), None)
        if not target:
            raise ValueError(f"Subordinate SCMA {scma_id} not found in House {house_id}.")

        cancelled = list(target["open_orders"])
        target["open_orders"] = []

        return {
            "status": "SUBORDINATE_ORDERS_CANCELLED",
            "house_id": house_id,
            "lineage_code": house["lineage_code"],
            "scma_id": scma_id,
            "cancelled_orders": cancelled,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    def freeze_subordinate_risk(self, house_id: int, scma_id: str) -> Dict[str, Any]:
        house = self.CANONICAL_HOUSES.get(house_id)
        if not house:
            raise ValueError(f"House {house_id} not found.")

        target = next((m for m in house["members"] if m["scma_id"] == scma_id), None)
        if not target:
            raise ValueError(f"Subordinate SCMA {scma_id} not found in House {house_id}.")

        target["risk_dial"] = 0.0
        target["status"] = "FROZEN_BY_HOUSE_LEADER"

        return {
            "status": "SUBORDINATE_RISK_FROZEN",
            "house_id": house_id,
            "lineage_code": house["lineage_code"],
            "scma_id": scma_id,
            "new_risk_dial": 0.0,
            "member_status": target["status"],
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    def evaluate_bicameral_proposal(self, affirmative_house_ids: List[int]) -> Dict[str, Any]:
        unique_votes = set(hid for hid in affirmative_house_ids if 1 <= hid <= 12)
        vote_count = len(unique_votes)
        ratified = vote_count >= 9

        return {
            "total_seats": 12,
            "affirmative_votes": vote_count,
            "ratification_threshold": 9,
            "affirmative_pct": round((vote_count / 12.0) * 100.0, 1),
            "ratified": ratified,
            "status": "RATIFIED" if ratified else "QUORUM_REJECTED",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
