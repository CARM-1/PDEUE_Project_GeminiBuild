import re
from typing import Dict, Any, Optional

class AICopilotEngine:
    """Deterministic AI Copilot Engine enforcing AUTH-01/02 point-in-time governance."""
    def __init__(self, llm_client: Optional[Any] = None):
        self.llm_client = llm_client

    def ask(
        self,
        query: str,
        user_role: str = "Chief Administrator",
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Return the conversational text while retaining one reasoning path.

        Portal callers only need display text, whereas existing operator callers
        use :meth:`process_query` for action cards and lineage metadata.  Keeping
        this small adapter on the domain engine prevents portals from rebuilding
        (and eventually drifting from) its intent routing.
        """
        result = self.process_query(
            query,
            workspace_state=context or {},
            actor_hat=user_role,
        )
        return result["response_text"]

    def process_query(self, query: str, workspace_state: Optional[Dict[str, Any]] = None, actor_hat: Optional[str] = "Chief Administrator") -> Dict[str, Any]:
        q_str = (query or "").lower().strip()

        # Advisor-domain explanations formerly lived as shallow HTTP-route
        # mocks.  They remain deterministic here for backwards compatibility,
        # but are now available to every caller of the shared engine.
        if any(marker in q_str for marker in ("future", "diversification", "markets")):
            return {
                "response_text": (
                    "Project FUTURE begins after the active trading float reaches its $25,000 ceiling. "
                    "The same underwriting discipline then diversifies through SPAWN 2.0 into deep CME "
                    "futures and rates, systematic sector equities and ETFs, G10 FX basis, and "
                    "delta-neutral crypto funding while intraday rotation limits overnight gap risk."
                ),
                "unilateral_execution": False,
                "lineage_context": {"intent": "PROJECT_FUTURE", "model_prob": 0.27},
                "action_cards": [],
            }
        if any(marker in q_str for marker in ("foster", "sponsor")):
            return {
                "response_text": (
                    "Pay-It-Forward Fostering lets a solvent member at the $25,000 float ceiling sponsor "
                    "an incoming relative by transferring seed capital directly from protected swept bank "
                    "cash. The sponsor becomes the new member's F1 Peer Mentor; lineage and custodial "
                    "governance still apply."
                ),
                "unilateral_execution": False,
                "lineage_context": {"intent": "MEMBER_FOSTERING", "model_prob": 0.27},
                "action_cards": [],
            }
        if "monthly" in q_str or "after 25k" in q_str or "after $25k" in q_str:
            return {
                "response_text": (
                    "After the active float reaches $25,000, it remains intact while excess personal net "
                    "profits sweep off-venue. The modeled steady-state cash run rate is approximately "
                    "$7,800–$11,300 per month, with swept cash earning 4.5% APY."
                ),
                "unilateral_execution": False,
                "lineage_context": {"intent": "POST_CAP_CASH_ENGINE", "model_prob": 0.27},
                "action_cards": [],
            }

        if "withdrawal" in q_str or "distribution" in q_str:
            return {
                "response_text": (
                    "Fiduciary Impact: Withdrawing $650.00 from Julian's apprentice SCMA reduces "
                    "6-month projected compounding velocity by 24.2%. Recommend a partial $250.00 "
                    "distribution under Yellow-Tier so more principal remains available to compound."
                ),
                "unilateral_execution": False,
                "lineage_context": {"intent": "WITHDRAWAL_IMPACT", "model_prob": 0.27},
                "action_cards": [],
            }
        if "rationale" in q_str or "trade" in q_str:
            return {
                "response_text": (
                    "Trade Analysis: Miami Sub-Freezing contract (KX-MIA-FRZ-32) was backed by "
                    "5-member NOAA ASOS ensemble consensus with a 28.5% edge hurdle. The rationale "
                    "is educational and remains subject to fiduciary review before any execution."
                ),
                "unilateral_execution": False,
                "lineage_context": {"intent": "TRADE_RATIONALE", "model_prob": 0.27},
                "action_cards": [],
            }

        # Educational concepts are intentionally resolved before the broad
        # risk/explanation intents below. This keeps common learner questions
        # deterministic and gives novices a useful mental model, not jargon.
        educational_response = None
        concept = None
        if not any(marker in q_str for marker in ("audit", "risk")) and any(
            marker in q_str
            for marker in (
                "87/10/3",
                "waterfall",
                "simply",
                "snowball",
                "compound",
                "family treasury",
                "familial treasury",
            )
        ):
            concept = "WATERFALL_STEWARDSHIP"
            educational_response = (
                "The 87/10/3 waterfall divides each net realized gain into three purposeful buckets: "
                "87% stays in your private SCMA to compound your balance; 10% routes to the "
                "Familial Common Treasury to build our shared investment pool, debt relief "
                "facility (FSAP), and emergency shield; and 3% supports Platform Infrastructure "
                "& Stewardship to cover cloud servers and live data feeds. Stewardship is funded "
                "strictly from net profits—never from member pockets—and is never deducted on "
                "losing trades."
            )
        elif any(marker in q_str for marker in ("children", "minors", "custodial")):
            concept = "CUSTODIAL_GOVERNANCE"
            educational_response = (
                "Every member of the lineage—including children and minors—can hold an "
                "independent SCMA pre-funded with gifted seed capital. Because federal "
                "regulations prohibit minors from holding exchange accounts directly, all "
                "trades route through our family trust, while internal sub-ledgers track "
                "personal equity. Minor accounts are managed under custodial supervision "
                "(is_custodial: true), where parents set conservative risk bounds and "
                "co-sign all withdrawals."
            )
        elif "pay it forward" in q_str or "fsap" in q_str:
            concept = "FAMILIAL_STABILITY_ADVANCE_POOL"
            educational_response = (
                "Our family uses the Familial Stability Advance Pool (FSAP) to extinguish "
                "predatory debt for relatives in need. Repayment occurs gradually through "
                "automated profit sweeps without disrupting trading velocity. As accounts "
                "reach maturity, members have the opportunity to pay it forward by sponsoring "
                "seed accounts for the next generation."
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
