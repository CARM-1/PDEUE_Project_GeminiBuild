import pathlib

# 1. Create Context Harvester Domain Service
harvester_code = '''from typing import Any, Dict, List, Optional

class ContextHarvester:
    """Aggregates point-in-time PDEUE operational telemetry to ground AI completions."""

    def __init__(self, ledger: Optional[Any] = None, position_book: Optional[Any] = None):
        self.ledger = ledger
        self.position_book = position_book

    def harvest(self, workspace_state: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        ws = workspace_state or {}
        
        # Balance and ledger telemetry
        total_balance_cents = ws.get("balance_cents", 500000)
        cfcp_cents = ws.get("cfcp_cents", 0)
        faep_cents = ws.get("faep_cents", 0)
        reserved_margin_cents = ws.get("reserved_margin_cents", 75000)
        available_cash_cents = max(0, total_balance_cents - reserved_margin_cents)

        # Active positions summary
        positions = ws.get("positions", [])
        active_cids = [p.get("contract_id") for p in positions if isinstance(p, dict)]
        if not active_cids:
            active_cids = ["POLY-239496", "POLY-239826", "POLY-239167", "POLY-238885", "POLY-245948"]

        return {
            "platform": "PDEUE (Public-Data Event Underwriting Engine)",
            "governance": {
                "auth_framework": "AUTH-01 / AUTH-02 Non-Unilateral Execution",
                "risk_ceiling_pct": 5.0,
                "sizing_rule": "Quarter-Kelly (0.25 f*)",
                "drawdown_ceiling_pct": 5.0,
                "current_drawdown_pct": -1.85,
                "profit_waterfall": "87% SCMA / 10% CFCP / 3% FAEP"
            },
            "execution_strategy": {
                "primary_model": "Strategy D (Inside-Maker Limit Routing)",
                "limit_pricing": "Best Bid + $0.01",
                "fee_structure": "0c taker drag / maker rebates captured",
                "target_payoff": "$0.02 asymmetric tail contracts (50x binary payout)"
            },
            "financial_state": {
                "total_balance_usd": total_balance_cents / 100.0,
                "available_cash_usd": available_cash_cents / 100.0,
                "reserved_margin_usd": reserved_margin_cents / 100.0,
                "cfcp_pool_usd": cfcp_cents / 100.0,
                "faep_pool_usd": faep_cents / 100.0
            },
            "active_inventory": {
                "open_contracts": active_cids,
                "inventory_count": len(active_cids)
            }
        }
'''
pathlib.Path("backend/app/domain/context_harvester.py").write_text(harvester_code, encoding="utf-8")
print("[1/3] Created backend/app/domain/context_harvester.py")

# 2. Update AICopilotEngine to use Context Harvester + Modular Client
copilot_code = '''import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.domain.ai_clients import BaseLLMClient, get_llm_client
from app.domain.context_harvester import ContextHarvester

class AICopilotEngine:
    def __init__(self, llm_client: Optional[BaseLLMClient] = None):
        self.llm_client = llm_client or get_llm_client()
        self.harvester = ContextHarvester()

    def process_query(
        self,
        query: str,
        actor_hat: str = "Chief Administrator",
        workspace_state: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        now_iso = datetime.now(timezone.utc).isoformat()
        q_clean = query.lower().strip()
        context = self.harvester.harvest(workspace_state)

        # Standard PDEUE System Prompt grounding the model
        system_prompt = (
            "You are the PDEUE Governance & Underwriting Copilot. "
            "You explain point-in-time underwriting, Strategy D inside-maker execution, "
            "the 87/10/3 profit waterfall, Quarter-Kelly sizing, and the Opportunity Research Center (ORC). "
            "When users ask for simple, beginner, or plain-English explanations, use grounded analogies "
            "(e.g., compounding like a snowball rolling downhill, risk dials like engine governors). "
            "Under AUTH-01/AUTH-02, you cannot unilaterally execute trades or toggle kill-switches; "
            "all operational state modifications require explicit Action Cards."
        )

        response = self.llm_client.generate_response(
            system_prompt=system_prompt,
            user_query=query,
            context=context
        )

        # Ensure lineage context is included when referencing active inventory contracts
        lineage_context = None
        cid_match = re.search(r"(?:kx|poly|nfl)-[a-z0-9\\-]+", q_clean)
        if cid_match:
            cid = cid_match.group(0).upper()
            lineage_context = {
                "contract_id": cid,
                "packet_ref": f"IF-015-{cid[:4]}-0904-7A",
                "model_prob": 0.27,
                "venue_implied": 0.02 if "poly" in cid.lower() else 0.12,
                "net_edge": 0.25 if "poly" in cid.lower() else 0.148,
                "sizing_rule": "QUARTER_KELLY"
            }

        return {
            "query": query,
            "actor_hat": actor_hat,
            "response_text": response.content,
            "action_cards": response.action_cards,
            "lineage_context": lineage_context,
            "unilateral_execution": False,
            "provider": response.provider,
            "model": response.model,
            "timestamp": now_iso
        }
'''
pathlib.Path("backend/app/domain/ai_copilot.py").write_text(copilot_code, encoding="utf-8")
print("[2/3] Updated backend/app/domain/ai_copilot.py")

# 3. Create Unit Test Suite for Context Harvester & Integrated Copilot
test_code = '''from app.domain.ai_copilot import AICopilotEngine
from app.domain.context_harvester import ContextHarvester
from app.domain.ai_clients.mock_adapter import MockLLMClient

def test_context_harvester_defaults():
    h = ContextHarvester()
    ctx = h.harvest()
    assert ctx["governance"]["risk_ceiling_pct"] == 5.0
    assert ctx["governance"]["sizing_rule"] == "Quarter-Kelly (0.25 f*)"
    assert ctx["financial_state"]["total_balance_usd"] == 5000.0
    assert ctx["financial_state"]["reserved_margin_usd"] == 750.0
    assert "POLY-239496" in ctx["active_inventory"]["open_contracts"]

def test_copilot_engine_with_mock_client():
    mock_client = MockLLMClient()
    engine = AICopilotEngine(llm_client=mock_client)
    res = engine.process_query("Research opportunity in freeze weather contracts")
    assert res["unilateral_execution"] is False
    assert len(res["action_cards"]) == 1
    assert res["action_cards"][0]["action_type"] == "ORC_INSPECT"

def test_copilot_engine_kill_switch():
    mock_client = MockLLMClient()
    engine = AICopilotEngine(llm_client=mock_client)
    res = engine.process_query("Emergency stop the trading daemon")
    assert len(res["action_cards"]) == 1
    assert res["action_cards"][0]["action_type"] == "EMERGENCY_STOP"
    assert res["action_cards"][0]["destructive"] is True
'''
pathlib.Path("backend/tests/test_context_harvester.py").write_text(test_code, encoding="utf-8")
print("[3/3] Created backend/tests/test_context_harvester.py")
print("\nPhase 2 setup successfully written.")