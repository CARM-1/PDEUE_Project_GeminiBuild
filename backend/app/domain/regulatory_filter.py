"""Nov 2026 CFTC Event-Contract Scope & DEATH BETS Act Regulatory Content Filter.

Strictly zero-financial-import educational/governance module safe for import on
BOTH the air-gapped social plane (`social_plane_router.py`, `dual_lane_tutor.py`)
and the Shadow Paper Hunch Research Studio (`shadow_hunch_service.py`).

Regulatory Guardrail (Fail-Closed):
- Permanently blocks sports/athletics wagers, casino-style gambling, war/armed
  conflict, terrorism/violent attacks, and death/mortality contracts.
- Restricts eligible Shadow Paper Hunch verticals exclusively to objectively
  verifiable, 100% fully collateralized regulated event contracts:
  WEATHER, MACRO_CPI, ENERGY_EIA, TREASURIES, EQUITY_INDICES, and FX.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Dict, List, Optional, Tuple

PROHIBITED_CODE = "PROHIBITED_EVENT_CATEGORY"
REGULATORY_CITATION = "Nov 2026 CFTC Event-Contract Scope & DEATH BETS Act"

ALLOWED_EVENT_VERTICALS: Dict[str, Dict[str, str]] = {
    "WEATHER": {
        "code": "WEATHER",
        "label": "Weather & Climate Oracles",
        "oracle": "NOAA / National Weather Service (ASOS / NHC)",
        "sample_ticker": "KX-NOAA-TEMP",
        "collateral_rule": "100% fully collateralized binary settlement ($1.00 / 100¢ cap)",
    },
    "MACRO_CPI": {
        "code": "MACRO_CPI",
        "label": "Macroeconomic & CPI Releases",
        "oracle": "U.S. Bureau of Labor Statistics (BLS CPI-U / NFP) & BEA",
        "sample_ticker": "KX-BLS-CPI",
        "collateral_rule": "100% fully collateralized binary settlement ($1.00 / 100¢ cap)",
    },
    "ENERGY_EIA": {
        "code": "ENERGY_EIA",
        "label": "Energy Inventories & EIA Storage",
        "oracle": "U.S. Energy Information Administration (EIA Weekly Storage & Petroleum)",
        "sample_ticker": "KX-EIA-NGAS",
        "collateral_rule": "100% fully collateralized binary settlement ($1.00 / 100¢ cap)",
    },
    "TREASURIES": {
        "code": "TREASURIES",
        "label": "U.S. Treasuries & Policy Rates",
        "oracle": "U.S. Department of the Treasury / Federal Reserve H.15 & FOMC",
        "sample_ticker": "KX-UST-10Y",
        "collateral_rule": "100% fully collateralized binary settlement ($1.00 / 100¢ cap)",
    },
    "EQUITY_INDICES": {
        "code": "EQUITY_INDICES",
        "label": "Broad Equity Indices & Volatility",
        "oracle": "S&P Dow Jones Indices / Nasdaq / Cboe Official Close",
        "sample_ticker": "KX-SPX-CLOSE",
        "collateral_rule": "100% fully collateralized binary settlement ($1.00 / 100¢ cap)",
    },
    "FX": {
        "code": "FX",
        "label": "G10 Foreign Exchange Benchmarks",
        "oracle": "Federal Reserve H.10 / WM Refinitiv G10 FX Fixing",
        "sample_ticker": "KX-FX-EURUSD",
        "collateral_rule": "100% fully collateralized binary settlement ($1.00 / 100¢ cap)",
    },
}

_PROHIBITED_RULES: Tuple[Tuple[str, str, Tuple[re.Pattern[str], ...]], ...] = (
    (
        "DEATH_CONTRACT",
        "Death, mortality, and human-life-outcome contracts are permanently prohibited under the DEATH BETS Act and PDEUE ethics policy.",
        (
            re.compile(r"\b(?:death|deaths|die|dying|dead\s+pool|deadpool|mortality\s+(?:bet|contract|wager|market)|life\s+expectancy\s+(?:bet|contract|wager)|obituary\s+bet|pass\s+away|passed\s+away)\b", re.IGNORECASE),
            re.compile(r"\b(?:assassination|assassinate|homicide|murder|suicide|fatalities|death\s+toll|casualties|casualty\s+count|body\s+count)\b", re.IGNORECASE),
        ),
    ),
    (
        "TERRORISM",
        "Terrorism and violent-attack contracts are permanently prohibited under Nov 2026 CFTC rules and PDEUE governance.",
        (
            re.compile(r"\b(?:terrorism|terrorist|terror\s+attack|bombing|hijacking|hostage|mass\s+shooting|extremist\s+attack|violent\s+attack)\b", re.IGNORECASE),
        ),
    ),
    (
        "WAR_CONFLICT",
        "War, military-strike, and armed-conflict event contracts are permanently prohibited under Nov 2026 CFTC rules.",
        (
            re.compile(r"\b(?:war|wars|warfare|invasion|invade|airstrike|air\s+strike|missile\s+strike|nuclear\s+strike|military\s+strike|armed\s+conflict|troop\s+deployment|artillery|battlefield|ceasefire\s+bet|coup\s+d'?etat)\b", re.IGNORECASE),
        ),
    ),
    (
        "SPORTS_WAGER",
        "Sports and athletics wagers are permanently prohibited under Nov 2026 CFTC event-contract scope and PDEUE policy.",
        (
            re.compile(r"\b(?:sports?|sportsbook|nfl|nba|mlb|nhl|ncaa|fifa|ufc|mma|pga|wimbledon|super\s+bowl|world\s+cup|world\s+series|stanley\s+cup|playoffs?|touchdown|quarterback|basketball|football|baseball|hockey|soccer|tennis|boxing|horse\s+racing|fanduel|draftkings|point\s+spread|moneyline|parlay)\b", re.IGNORECASE),
        ),
    ),
    (
        "CASINO_WAGER",
        "Casino-style gambling and games of chance are permanently prohibited under Nov 2026 CFTC scope and PDEUE policy.",
        (
            re.compile(r"\b(?:casino|blackjack|roulette|slot\s+machine|slots|poker|craps|baccarat|lottery|powerball|mega\s+millions|scratch-?off|dice\s+roll|gambling|gamble|betting\s+odds)\b", re.IGNORECASE),
        ),
    ),
)

_VERTICAL_MATCHERS: Tuple[Tuple[str, Tuple[re.Pattern[str], ...]], ...] = (
    (
        "WEATHER",
        (
            re.compile(r"\b(?:weather|noaa|nws|nhc|temperature|temp|freeze|frost|heatwave|heat\s+wave|hurricane|tropical\s+storm|rainfall|precipitation|snow|snowfall|blizzard|drought|el\s+nino|la\s+nina|climate|celsius|fahrenheit|degree\s+days?|hdd|cdd)\b", re.IGNORECASE),
        ),
    ),
    (
        "MACRO_CPI",
        (
            re.compile(r"\b(?:cpi|inflation|pce|bls|consumer\s+price|core\s+cpi|payroll|payrolls|nfp|nonfarm|unemployment|jobs\s+report|gdp|recession|retail\s+sales|ism|pmi|macro|macroeconomic|economic\s+release|fomc|federal\s+reserve|fed\s+rate|rate\s+cut|rate\s+hike)\b", re.IGNORECASE),
        ),
    ),
    (
        "ENERGY_EIA",
        (
            re.compile(r"\b(?:eia|natural\s+gas|natgas|henry\s+hub|crude\s+oil|wti|brent|petroleum|oil\s+inventory|inventories|gas\s+storage|bcf|opec|electricity|power\s+grid|energy|refinery|gasoline|diesel|lng)\b", re.IGNORECASE),
        ),
    ),
    (
        "TREASURIES",
        (
            re.compile(r"\b(?:treasury|treasuries|t-?bill|t-?note|t-?bond|10-?year|2-?year|30-?year|10y|2y|30y|yield\s+curve|bond\s+yield|sofr|fed\s+funds|auction\s+tail|sovereign\s+yield|rates)\b", re.IGNORECASE),
        ),
    ),
    (
        "EQUITY_INDICES",
        (
            re.compile(r"\b(?:s&p\s*500|spx|spy|nasdaq|ndx|qqq|dow\s+jones|djia|russell\s*2000|rut|vix|equity\s+index|equity\s+indices|stock\s+index|market\s+index)\b", re.IGNORECASE),
        ),
    ),
    (
        "FX",
        (
            re.compile(r"\b(?:fx|forex|foreign\s+exchange|eur/usd|eurusd|usd/jpy|usdjpy|gbp/usd|gbpusd|usd/chf|usd/cad|aud/usd|dxy|dollar\s+index|currency\s+pair|g10\s+fx|yen|euro|pound\s+sterling)\b", re.IGNORECASE),
        ),
    ),
)


@dataclass(frozen=True)
class RegulatoryFilterResult:
    allowed: bool
    code: Optional[str] = None
    prohibited_category: Optional[str] = None
    reason: Optional[str] = None
    matched_term: Optional[str] = None


def check_regulatory_content(text: str, *, extra_hint: Optional[str] = None) -> RegulatoryFilterResult:
    """Evaluate text against the Nov 2026 CFTC & DEATH BETS Act prohibited-contract filter."""
    combined = " ".join(part.strip() for part in (text or "", extra_hint or "") if part and part.strip())
    if not combined:
        return RegulatoryFilterResult(allowed=True)

    for category, reason, patterns in _PROHIBITED_RULES:
        for pat in patterns:
            m = pat.search(combined)
            if m:
                return RegulatoryFilterResult(
                    allowed=False,
                    code=PROHIBITED_CODE,
                    prohibited_category=category,
                    reason=(
                        f"{reason} Blocked under {REGULATORY_CITATION}. "
                        "PDEUE permits only objectively verifiable, 100% fully collateralized "
                        "economic, weather, energy, treasury, FX, and equity-index contracts."
                    ),
                    matched_term=m.group(0),
                )
    return RegulatoryFilterResult(allowed=True)


def map_eligible_vertical(text: str, *, vertical_hint: Optional[str] = None) -> Optional[Dict[str, str]]:
    """Map a hypothesis to one of the 6 allowed regulated event verticals (or None)."""
    hint = (vertical_hint or "").strip().upper().replace("-", "_").replace(" ", "_")
    alias_map = {
        "WEATHER": "WEATHER",
        "CLIMATE": "WEATHER",
        "NOAA": "WEATHER",
        "MACRO": "MACRO_CPI",
        "CPI": "MACRO_CPI",
        "MACRO_CPI": "MACRO_CPI",
        "ECONOMIC": "MACRO_CPI",
        "ENERGY": "ENERGY_EIA",
        "EIA": "ENERGY_EIA",
        "ENERGY_EIA": "ENERGY_EIA",
        "TREASURY": "TREASURIES",
        "TREASURIES": "TREASURIES",
        "RATES": "TREASURIES",
        "EQUITY": "EQUITY_INDICES",
        "EQUITIES": "EQUITY_INDICES",
        "EQUITY_INDICES": "EQUITY_INDICES",
        "INDEX": "EQUITY_INDICES",
        "FX": "FX",
        "FOREX": "FX",
        "CURRENCY": "FX",
    }
    if hint and hint in alias_map:
        return dict(ALLOWED_EVENT_VERTICALS[alias_map[hint]])

    source = text or ""
    for vertical_code, patterns in _VERTICAL_MATCHERS:
        for pat in patterns:
            if pat.search(source):
                return dict(ALLOWED_EVENT_VERTICALS[vertical_code])
    return None


def list_allowed_vertical_codes() -> List[str]:
    return list(ALLOWED_EVENT_VERTICALS.keys())
