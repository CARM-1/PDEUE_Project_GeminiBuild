"""Deterministic $0 MockLLMClient adapter (default in paper/CI mode)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional
import uuid

from .base import BaseLLMClient, LLMResponse
from .guardrails import inspect_user_input, sanitize_action_cards, sanitize_output_text


def _deterministic_public_research(query: str, *, for_hunch: bool = False) -> tuple[str, List[Dict[str, str]]]:
    """Return deterministic, zero-network plain-English market education & citations."""
    q = (query or "").lower()

    if any(k in q for k in ("cpi", "inflation", "pce", "bls", "payroll", "nfp", "unemployment", "gdp", "fomc", "fed ")):
        citations = [
            {
                "title": "Consumer Price Index (CPI) Summary & Release Schedule",
                "url": "https://www.bls.gov/cpi/",
                "source": "U.S. Bureau of Labor Statistics (BLS)",
            },
            {
                "title": "Federal Open Market Committee (FOMC) Calendar & Policy Statements",
                "url": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
                "source": "Board of Governors of the Federal Reserve System",
            },
        ]
        if for_hunch:
            text = (
                "Corroboration audit (offline deterministic research): Macroeconomic releases such as BLS CPI-U, "
                "core inflation, and payroll prints settle against scheduled official government publications with "
                "clear revision calendars. Primary uncertainty drivers include shelter lag, energy pass-through, and "
                "consensus survey dispersion ahead of the 8:30 a.m. ET release."
            )
        else:
            text = (
                "The Consumer Price Index (CPI) is published monthly by the U.S. Bureau of Labor Statistics (BLS) "
                "to measure how fast prices for a standard basket of household goods and services are changing. "
                "In binary event markets, contracts typically settle against the exact official headline or core "
                "month-over-month or year-over-year print—so small surprises versus consensus estimates move implied "
                "probabilities quickly."
            )
        return text, citations

    if any(k in q for k in ("treasury", "treasuries", "yield", "t-bill", "10-year", "10y", "2-year", "2y", "bond", "sofr", "rate")):
        citations = [
            {
                "title": "Daily Treasury Par Yield Curve Rates",
                "url": "https://home.treasury.gov/resource-center/data-chart-center/interest-rates",
                "source": "U.S. Department of the Treasury",
            },
            {
                "title": "Selected Interest Rates — H.15 Release",
                "url": "https://www.federalreserve.gov/releases/h15/",
                "source": "Federal Reserve Board",
            },
        ]
        if for_hunch:
            text = (
                "Corroboration audit (offline deterministic research): U.S. Treasury benchmark yields (2Y, 10Y, 30Y) "
                "and H.15 daily fixings are objectively published by the U.S. Treasury and Federal Reserve. "
                "Key risk factors include auction demand tails, inflation prints, and central-bank guidance."
            )
        else:
            text = (
                "U.S. Treasury yields reflect the annual return investors demand for lending money to the U.S. "
                "government over a set term (such as 3-month T-bills or 10-year notes). Bond prices and yields move "
                "in opposite directions: when inflation or growth expectations rise, yields tend to climb and existing "
                "bond prices fall."
            )
        return text, citations

    if any(k in q for k in ("eia", "natural gas", "crude", "oil", "energy", "storage", "wti", "henry hub", "bcf", "petroleum")):
        citations = [
            {
                "title": "Weekly Natural Gas Storage Report",
                "url": "https://ir.eia.gov/ngs/ngs.html",
                "source": "U.S. Energy Information Administration (EIA)",
            },
            {
                "title": "Weekly Petroleum Status Report",
                "url": "https://www.eia.gov/petroleum/supply/weekly/",
                "source": "U.S. Energy Information Administration (EIA)",
            },
        ]
        if for_hunch:
            text = (
                "Corroboration audit (offline deterministic research): EIA weekly natural gas storage (Bcf) and "
                "petroleum inventory builds/draws are published on a fixed weekly schedule with transparent regional "
                "breakdowns. Weather-driven heating/cooling degree days and LNG export utilization drive variance."
            )
        else:
            text = (
                "The U.S. Energy Information Administration (EIA) publishes weekly inventory reports for underground "
                "natural gas storage (measured in billion cubic feet, Bcf) and commercial crude oil stocks. "
                "When actual storage builds are smaller than forecast—or winter draws are larger—energy contract "
                "prices generally tighten because supply cushions are thinner."
            )
        return text, citations

    if any(k in q for k in ("noaa", "weather", "nws", "temperature", "hurricane", "freeze", "rain", "snow", "climate", "degree day")):
        citations = [
            {
                "title": "National Weather Service Official Climate & ASOS Station Observations",
                "url": "https://www.weather.gov/",
                "source": "NOAA / National Weather Service (NWS)",
            },
            {
                "title": "NOAA National Centers for Environmental Information (NCEI)",
                "url": "https://www.ncei.noaa.gov/",
                "source": "NOAA NCEI",
            },
        ]
        if for_hunch:
            text = (
                "Corroboration audit (offline deterministic research): Weather contracts settle against official "
                "NOAA / NWS Daily Climate Reports (CLI) from designated ASOS airport stations. Ensemble forecast "
                "spread (GFS/ECMWF) and local urban heat-island station bias must be checked before valuing edge."
            )
        else:
            text = (
                "A NOAA weather oracle settles a contract using the official Daily Climate Report recorded by a "
                "specific National Weather Service airport station (such as Central Park or Miami International). "
                "Because weather forecasts carry measurable spread across ensemble models, comparing forecast "
                "probability distributions against a contract's quoted price helps learners understand calibration."
            )
        return text, citations

    if any(k in q for k in ("s&p", "spx", "nasdaq", "vix", "equity", "stock index", "fx", "forex", "eur/usd", "yen", "dollar index", "dxy")):
        citations = [
            {
                "title": "Foreign Exchange Rates — H.10 Weekly Release",
                "url": "https://www.federalreserve.gov/releases/h10/current/",
                "source": "Federal Reserve Board",
            },
            {
                "title": "CFTC Event Contracts & Designated Contract Markets Overview",
                "url": "https://www.cftc.gov/IndustryOversight/TradingOrganizations/DCMs/index.htm",
                "source": "Commodity Futures Trading Commission (CFTC)",
            },
        ]
        if for_hunch:
            text = (
                "Corroboration audit (offline deterministic research): Broad equity-index closes (S&P 500, Nasdaq-100) "
                "and G10 FX benchmarks settle against regulated exchange closing prices or published central-bank "
                "fixings with deep liquidity and objective audit trails."
            )
        else:
            text = (
                "Broad equity indices (like the S&P 500) track weighted baskets of public companies, while G10 FX "
                "pairs (like EUR/USD) measure the exchange rate between major sovereign currencies. Regulated event "
                "contracts tied to these benchmarks settle on published official closing levels or central-bank fixings."
            )
        return text, citations

    if any(k in q for k in ("binary", "probability", "implied", "expected value", "ev ", "calibration", "brier", "fee friction")):
        citations = [
            {
                "title": "CFTC Consumer Advisory: Event Contracts & Fully Collateralized Risk",
                "url": "https://www.cftc.gov/LearnAndProtect/AdvisoriesAndArticles/index.htm",
                "source": "Commodity Futures Trading Commission (CFTC)",
            },
            {
                "title": "FRED Economic Data & Probability Research Primer",
                "url": "https://fred.stlouisfed.org/",
                "source": "Federal Reserve Bank of St. Louis (FRED)",
            },
        ]
        text = (
            "A fully collateralized binary contract pays $1.00 (100 cents) if a clearly defined event occurs and "
            "$0.00 if it does not. A quoted price of 60 cents implies roughly a 60% market probability before fees. "
            "Positive expected value exists only when your well-calibrated fair probability minus the market price "
            "AND minus transaction fees is strictly greater than $0.00."
        )
        return text, citations

    citations = [
        {
            "title": "Federal Reserve Economic Data (FRED) Public Research Library",
            "url": "https://fred.stlouisfed.org/",
            "source": "Federal Reserve Bank of St. Louis (FRED)",
        },
        {
            "title": "CFTC Regulated Event Contracts Educational Guide",
            "url": "https://www.cftc.gov/LearnAndProtect/index.htm",
            "source": "Commodity Futures Trading Commission (CFTC)",
        },
    ]
    if for_hunch:
        text = (
            "Corroboration audit (offline deterministic research): Verified that the hypothesis maps to publicly "
            "observable benchmark data with an objective settlement oracle. Confirm base rates, upcoming release "
            "dates, and fee-adjusted net edge before staging even a zero-risk Shadow Paper practice bid."
        )
    else:
        text = (
            "In public economic and event markets, prices reflect a crowd's combined probability estimate for a "
            "verifiable future release—such as inflation data, energy inventories, Treasury yields, or weather "
            "observations. Good market literacy starts by identifying the official settlement source, checking "
            "historical base rates, and separating an educational estimate from any guarantee."
        )
    return text, citations


class MockLLMClient(BaseLLMClient):
    """Zero-cost deterministic LLM adapter for paper mode, offline local dev, and CI."""

    provider_name = "mock"
    model_name = "mock-v1"

    def __init__(
        self,
        default_response: Optional[str] = None,
        timeout_seconds: float = 15.0,
        max_output_tokens: int = 1024,
    ):
        self.default_response = default_response
        self.timeout_seconds = float(timeout_seconds)
        self.max_output_tokens = int(max_output_tokens)

    @property
    def is_configured(self) -> bool:
        return True

    def generate_response(
        self,
        system_prompt: str,
        user_query: str,
        tools: Optional[List[Dict[str, Any]]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> LLMResponse:
        ctx = dict(context or {})
        actor_role = str(ctx.get("actor_role") or "OPERATOR").upper().strip()
        allowed_scma_id = ctx.get("allowed_scma_id") or ctx.get("scma_id")
        member_name = ctx.get("member_name") or ctx.get("name")
        actor_id = str(ctx.get("actor_id") or allowed_scma_id or actor_role.lower())
        assigned_household_id = ctx.get("assigned_household_id")
        r12_unredacted = bool(ctx.get("r12_unredacted", False))
        forbidden_scma_ids = ctx.get("forbidden_scma_ids")

        # Enforce prompt-injection / exfiltration guard even on direct calls.
        verdict = inspect_user_input(
            user_query,
            actor_role=actor_role,
            actor_id=actor_id,
            allowed_scma_id=allowed_scma_id,
            member_name=member_name,
            assigned_household_id=assigned_household_id,
            r12_unredacted=r12_unredacted,
            forbidden_scma_ids=forbidden_scma_ids,
        )
        if verdict.blocked:
            return LLMResponse(
                content=verdict.refusal_message or "Request refused under PDEUE guardrails.",
                action_cards=[],
                provider=self.provider_name,
                model=self.model_name,
                unilateral_execution=False,
                auth_tier="AUTH-01",
                guard_triggered=True,
                guard_category=verdict.category,
                guard_reason=verdict.reason,
                audit_event_id=verdict.audit_event_id,
            )

        # Grounded role-scoped draft passthrough (Member Tutor, Class F/T Copilots, Chief Admin Chancellor Coach).
        draft = ctx.get("copilot_draft") if isinstance(ctx.get("copilot_draft"), dict) else (
            ctx.get("tutor_draft") if (actor_role == "MEMBER" and isinstance(ctx.get("tutor_draft"), dict)) else None
        )
        if isinstance(draft, dict):
            content = sanitize_output_text(
                str(draft.get("content") or self.default_response or ""),
                actor_role=actor_role,
                allowed_scma_id=allowed_scma_id,
                r12_unredacted=r12_unredacted,
                forbidden_scma_ids=forbidden_scma_ids,
            )
            cards = sanitize_action_cards(list(draft.get("action_cards") or []), actor_role=actor_role)
            return LLMResponse(
                content=content,
                action_cards=cards,
                provider=self.provider_name,
                model=self.model_name,
                unilateral_execution=False,
                auth_tier=str(draft.get("auth_tier") or "AUTH-01"),
                impact_card=draft.get("impact_card"),
                citations=list(draft.get("citations") or []),
                web_citations=list(draft.get("web_citations") or []),
                grounding_used=bool(draft.get("grounding_used", False)),
                structured_data=draft.get("structured_data"),
            )

        # Lane 2 Grounded Public Web Research / Shadow Hunch Corroboration (deterministic offline mock)
        if ctx.get("web_grounding") or ctx.get("hunch_corroboration"):
            research_text, web_citations = _deterministic_public_research(
                verdict.sanitized_text,
                for_hunch=bool(ctx.get("hunch_corroboration")),
            )
            return LLMResponse(
                content=sanitize_output_text(
                    research_text,
                    actor_role=actor_role,
                    allowed_scma_id=allowed_scma_id,
                    r12_unredacted=r12_unredacted,
                    forbidden_scma_ids=forbidden_scma_ids,
                ),
                action_cards=[],
                provider=self.provider_name,
                model=self.model_name,
                unilateral_execution=False,
                auth_tier="AUTH-01",
                web_citations=web_citations,
                grounding_used=True,
            )

        q = verdict.sanitized_text.lower()
        action_cards: List[Dict[str, Any]] = []
        auth_tier = "AUTH-01"

        if actor_role != "MEMBER" and any(w in q for w in ["kill", "emergency", "stop", "halt"]):
            auth_tier = "AUTH-04"
            content = "Emergency Kill Switch intent detected. Under AUTH-01, confirm using the Action Card below:"
            action_cards.append({
                "action_id": f"ACT-{uuid.uuid4().hex[:8]}",
                "action_type": "EMERGENCY_STOP",
                "auth_tier": "AUTH-04",
                "title": "Trip Emergency Circuit Breaker",
                "description": "Immediate fail-closed halt of all scanning and execution loops.",
                "endpoint": "/api/v1/operator/emergency-stop",
                "method": "POST",
                "payload": {"actor_id": "Chief Administrator", "reason": "AI Kill Switch"},
                "destructive": True,
                "requires_dual_control": False,
                "requires_human_confirmation": True,
                "unilateral_execution": False,
                "executed": False,
            })
        elif actor_role != "MEMBER" and any(w in q for w in ["orc", "research", "hunch", "opportunity"]):
            auth_tier = "AUTH-01"
            content = "Opportunity Research Center (ORC): Evaluating hypothesis against Point-in-Time market data and active contract ladders."
            action_cards.append({
                "action_id": f"ACT-{uuid.uuid4().hex[:8]}",
                "action_type": "ORC_INSPECT",
                "auth_tier": "AUTH-01",
                "title": "Open Opportunity Research Dossier",
                "description": "Launch ORC hypothesis evaluation drawer.",
                "endpoint": "/api/v1/operator/orc/dossier",
                "method": "GET",
                "payload": {"query": verdict.sanitized_text},
                "destructive": False,
                "requires_dual_control": False,
                "requires_human_confirmation": True,
                "unilateral_execution": False,
                "executed": False,
            })
        else:
            content = self.default_response or f"Mock LLM Response for: {verdict.sanitized_text}"

        return LLMResponse(
            content=sanitize_output_text(
                content,
                actor_role=actor_role,
                allowed_scma_id=allowed_scma_id,
                r12_unredacted=r12_unredacted,
                forbidden_scma_ids=forbidden_scma_ids,
            ),
            action_cards=sanitize_action_cards(action_cards, actor_role=actor_role),
            provider=self.provider_name,
            model=self.model_name,
            unilateral_execution=False,
            auth_tier=auth_tier,
        )
