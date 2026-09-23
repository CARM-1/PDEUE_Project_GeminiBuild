"""
PDEUE 12-House Lineage Hierarchy & Sovereign Settlor Governance Engine
Enforces tribal partitioning, subordinate risk controls, and the
Sovereign Settlor / Trust Protector veto pattern over all House petitions.
"""
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

class LineageHierarchyService:
    """Authoritative registry for House lines, subordinate management, and sovereign governance."""

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
                    "role_tag": "Sovereign Settlor",
                    "cash_cents": 500000,
                    "risk_dial": 0.02,
                    "status": "ACTIVE",
                    "open_orders": ["KX-MIA-FRZ-32"]
                },
                {
                    "scma_id": "SCMA-ELEANOR_-B2B31C9E",
                    "name": "Eleanor Vance",
                    "role_tag": "Designated Advisor",
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
                    "role_tag": "Custodial Apprentice",
                    "cash_cents": 25000,
                    "risk_dial": 0.01,
                    "status": "ACTIVE",
                    "open_orders": ["POLY-239496"]
                }
            ],
            "governance_seat": True
        }
    }

    # In-memory proposal ledger
    PROPOSALS: Dict[str, Dict[str, Any]] = {
        "PROP-2026-001": {
            "proposal_id": "PROP-2026-001",
            "title": "Quarterly CFCP Educational Grant Sweep ($500.00)",
            "description": "Petition to disburse $500.00 from CFCP treasury to House 2 youth education fund.",
            "target_house_id": 2,
            "amount_cents": 50000,
            "affirmative_house_ids": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
            "house_ratified": True,
            "status": "PENDING_CHIEF_ADMIN_AUTHORIZATION",
            "created_at": "2026-09-17T03:00:00Z"
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
                            "role_tag": "Lineal Member",
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
            "aggregated_equity_cents": total_cash_cents,
            "active_margin_cents": sum(11875 * len(m["open_orders"]) for m in house["members"]),
            "drawdown_pct": round(-0.15 * house_id, 2),
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


    def list_proposals(self) -> List[Dict[str, Any]]:
        return list(self.PROPOSALS.values())

    def submit_house_petition(self, title: str, description: str, target_house_id: int, amount_cents: int, affirmative_house_ids: List[int]) -> Dict[str, Any]:
        """House petition intake: 75% quorum qualifies proposal for Chief Admin review."""
        unique_votes = set(hid for hid in affirmative_house_ids if 1 <= hid <= 12)
        vote_count = len(unique_votes)
        ratified = vote_count >= 9
        proposal_id = f"PROP-2026-{len(self.PROPOSALS) + 1:03d}"

        record = {
            "proposal_id": proposal_id,
            "title": title,
            "description": description,
            "target_house_id": target_house_id,
            "amount_cents": amount_cents,
            "affirmative_house_ids": list(unique_votes),
            "affirmative_count": vote_count,
            "house_ratified": ratified,
            "status": "PENDING_CHIEF_ADMIN_AUTHORIZATION" if ratified else "QUORUM_REJECTED",
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        self.PROPOSALS[proposal_id] = record
        return record

    def adjudicate_proposal(self, proposal_id: str, action: str, caller_scma: str) -> Dict[str, Any]:
        """
        Sovereign Settlor Adjudication:
        Only the Founder/Chief Admin can sign (EXECUTE) or permanently VETO petitions.
        A 75% House ratification without Founder authorization CANNOT execute.
        """
        prop = self.PROPOSALS.get(proposal_id)
        if not prop:
            raise ValueError(f"Proposal {proposal_id} does not exist.")

        # Invariant: Non-Founder cannot execute
        if not caller_scma.startswith("SCMA-FOUNDER"):
            raise PermissionError("Access Denied: Only Founder/Chief Administrator possesses Sovereign Veto and Execution authority.")

        action_upper = action.upper()
        if action_upper == "APPROVE_AND_EXECUTE":
            if not prop["house_ratified"]:
                raise ValueError("Invariant Violation: Proposal lacks the mandatory 75% House petition threshold.")
            prop["status"] = "SOVEREIGN_EXECUTED"
            prop["settled_by"] = caller_scma
            prop["settled_at"] = datetime.now(timezone.utc).isoformat()
        elif action_upper == "SOVEREIGN_VETO":
            prop["status"] = "SOVEREIGN_VETOED"
            prop["settled_by"] = caller_scma
            prop["settled_at"] = datetime.now(timezone.utc).isoformat()
        else:
            raise ValueError(f"Unknown adjudication action: {action}. Must be APPROVE_AND_EXECUTE or SOVEREIGN_VETO.")

        return prop

    def evaluate_bicameral_proposal(self, affirmative_house_ids: List[int]) -> Dict[str, Any]:
        """Evaluates whether the 75% House threshold (9 of 12) was achieved."""
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


# Routers must share one authoritative in-process hierarchy. Keeping the
# instance here prevents actions from being visible only to the mutating router.
_lineage_service: Optional[LineageHierarchyService] = None


def get_lineage_service() -> LineageHierarchyService:
    """Return the application's shared lineage hierarchy service."""
    global _lineage_service
    if _lineage_service is None:
        _lineage_service = LineageHierarchyService()
    return _lineage_service
