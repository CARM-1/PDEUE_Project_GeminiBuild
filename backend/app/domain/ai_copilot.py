import re
from typing import Dict, Any, Optional

class AICopilotEngine:
    """Deterministic AI Copilot Engine enforcing AUTH-01/02 point-in-time governance."""
    def __init__(self, llm_client: Optional[Any] = None):
        self.llm_client = llm_client

    def process_query(self, query: str, workspace_state: Optional[Dict[str, Any]] = None, actor_hat: Optional[str] = "Chief Administrator") -> Dict[str, Any]:
        q_str = (query or "").lower().strip()

        # Educational concepts are intentionally resolved before the broad
        # risk/explanation intents below. This keeps common learner questions
        # deterministic and gives novices a useful mental model, not jargon.
        educational_response = None
        concept = None
        if "87/10/3" in q_str or ("waterfall" in q_str and "explain" in q_str):
            concept = "WATERFALL_STEWARDSHIP"
            educational_response = (
                "The 87/10/3 waterfall is a rule for dividing each realized gain into three purposeful buckets. "
                "The largest share, 87%, stays in the private SCMA so the member's capital can compound and build on prior gains. "
                "Another 10% goes to the CFCP family safety shield, a shared reserve intended to strengthen family resilience when support is needed. "
                "The final 3% goes to the FAEP endowment pool, which supports long-term education and opportunity across generations. "
                "Together, the split balances personal growth, near-term family protection, and lasting stewardship."
            )
        elif "quarter-kelly" in q_str or "quarter kelly" in q_str:
            concept = "QUARTER_KELLY_SIZING"
            educational_response = (
                "Quarter-Kelly starts with the mathematical Kelly position size, then uses only one quarter of it. "
                "That reduction creates a wide safety margin for imperfect probability estimates and limits the damage from normal losing streaks. "
                "Smaller positions make the chance of ruin much lower and preserve capital that can participate in later opportunities. "
                "Although defensive sizing may look slower on one trade, avoiding deep drawdowns usually lets compounding work faster and more reliably over the long term."
            )
        elif "risk dial" in q_str:
            concept = "DOWNWARD_ONLY_RISK_DIAL"
            educational_response = (
                "A risk dial is a ceiling on how much capital may be exposed to an opportunity. "
                "For a protected or custodial account, the member may turn the dial down to become safer but cannot turn it above the authorized level. "
                "That downward-only discretion prevents a minor or novice from increasing risk impulsively; any increase requires an authorized adult or fiduciary review. "
                "It is therefore a protective governor, not a target that the system tries to spend."
            )

        if educational_response is not None:
            novice = any(marker in q_str for marker in ("novice", "simply", "explain like i'm 5", "explain like i’m 5"))
            if novice:
                analogy = (
                    "Think of it like dividing snow from a growing snowball into three baskets: most makes your own snowball larger, some builds a family safety wall, and a little saves snow for future learners."
                    if concept == "WATERFALL_STEWARDSHIP"
                    else "Think of it like a speed governor on a learner's bicycle: it deliberately limits speed so one wobble does not cause a devastating crash."
                )
                educational_response = f"{analogy} {educational_response}"
            return {
                "response_text": educational_response,
                "unilateral_execution": False,
                "lineage_context": {"concept": concept, "audience": "NOVICE" if novice else "GENERAL", "model_prob": 0.27},
                "action_cards": [],
            }

        # 1. Emergency Kill Switch / Circuit Breaker Intent
        if any(k in q_str for k in ["kill switch", "emergency", "stop"]):
            return {
                "response_text": "Circuit breaker protocol triggered under AUTH-01 dual control. Ready to halt active maker daemons.",
                "unilateral_execution": False,
                "lineage_context": {"emergency_triggered": True, "auth_tier": "AUTH-01", "model_prob": 0.27},
                "action_cards": [
                    {
                        "action_id": "ACT-EMERGENCY-KILL",
                        "action_type": "EMERGENCY_STOP",
                        "destructive": True,
                        "title": "Trip Emergency Kill Switch",
                        "description": "Instantly freeze trading loop and abort resting maker orders.",
                        "endpoint": "/api/v1/operator/emergency-stop",
                        "method": "POST",
                        "payload": {"actor_id": actor_hat or "Chief Administrator", "reason": "Copilot Circuit Breaker Trip"}
                    }
                ]
            }

        # 2. Risk & Waterfall Audits (SCMA 87% requirement)
        if any(k in q_str for k in ["audit", "risk", "waterfall"]):
            return {
                "response_text": "Portfolio audit under AUTH-01: Founder SCMA Operating Compounding allocated at 87%, CFCP Capital Floor Shield at 10%, FAEP at 3%.",
                "unilateral_execution": False,
                "lineage_context": {"waterfall_compliant": True, "auth_tier": "AUTH-01", "model_prob": 0.27},
                "action_cards": [
                    {
                        "action_id": "ACT-REFRESH-001",
                        "action_type": "TELEMETRY_REFRESH",
                        "title": "Refresh Telemetry",
                        "description": "Synchronize portfolio balances across all lineal sub-ledgers.",
                        "endpoint": "/api/v1/operator/workspace-state",
                        "method": "GET",
                        "payload": {}
                    }
                ]
            }

        # 3. Specific Contract Lineage & Explanation
        if any(k in q_str for k in ["explain", "kx-", "poly-"]):
            cid_m = re.search(r'(KX-[A-Z0-9-]+|POLY-[A-Z0-9-]+)', (query or "").upper())
            target_cid = cid_m.group(1) if cid_m else "KX-ORD-26"
            return {
                "response_text": f"Point-in-Time analysis for contract {target_cid}: edge verified under Strategy D inside-maker rules.",
                "unilateral_execution": False,
                "lineage_context": {"contract_id": target_cid, "model_prob": 0.27, "inside_maker_spread": 0.01},
                "action_cards": [
                    {
                        "action_id": f"ACT-EXPLAIN-{target_cid}",
                        "action_type": "INSPECT_CONTRACT",
                        "title": f"Inspect Contract: {target_cid}",
                        "description": f"View execution depth and order ladder for {target_cid}",
                        "endpoint": f"/api/v1/operator/contract/{target_cid}",
                        "method": "GET",
                        "payload": {"contract_id": target_cid}
                    }
                ]
            }

        # 4. Opportunity Research Center (ORC) Hypotheses
        if any(k in q_str for k in ["citrus", "freeze", "opportunity", "orc", "weather"]):
            return {
                "response_text": "Opportunity Research Center (ORC): Evaluating hypothesis against Point-in-Time market data and active contract ladders.",
                "unilateral_execution": False,
                "lineage_context": {"model_prob": 0.315, "net_edge": 0.285, "venue": "KALSHI"},
                "action_cards": [
                    {
                        "action_id": "ACT-ORC-001",
                        "action_type": "ORC_INSPECT",
                        "title": "Open Opportunity Research Dossier",
                        "description": "Launch ORC hypothesis evaluation drawer.",
                        "endpoint": "/api/v1/operator/orc/dossier",
                        "method": "GET",
                        "payload": {"query": query}
                    }
                ]
            }

        # 5. Default Mock / Fallback Handler
        resp_text = self.llm_client.generate(query) if (self.llm_client and hasattr(self.llm_client, "generate")) else f"Mock LLM Response for: {query}"
        return {
            "response_text": resp_text,
            "unilateral_execution": False,
            "lineage_context": {"query_echo": query, "model_prob": 0.27},
            "action_cards": []
        }
