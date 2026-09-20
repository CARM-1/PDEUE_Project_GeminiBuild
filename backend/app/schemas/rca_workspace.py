"""Versioned, truthful read contracts for the RC-A Founder workspaces."""
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict


class QualificationState(str, Enum):
    QUALIFIED = "QUALIFIED"
    QUALIFICATION_PENDING = "QUALIFICATION_PENDING"
    BLOCKED = "BLOCKED"


class SourceMode(str, Enum):
    OFFLINE = "OFFLINE"
    PAPER = "PAPER"
    SHADOW = "SHADOW"
    PRODUCTION = "PRODUCTION"


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ExecutiveCapitalData(ContractModel):
    total_equity_cents: int
    unreserved_cash_cents: int
    dry_powder_floor_cents: int
    dry_powder_policy_version: str
    dry_powder_policy_status: str
    cfcp_balance_cents: int
    faep_balance_cents: int
    active_scma_count: int
    authoritative_as_of_utc: datetime


class ExecutiveCapitalEnvelope(ContractModel):
    schema_version: Literal["rca.capital-summary.v1"] = "rca.capital-summary.v1"
    qualification_state: QualificationState
    source_mode: SourceMode
    generated_at_utc: datetime
    reason_codes: List[str]
    data: Optional[ExecutiveCapitalData]


class DomainScannerData(ContractModel):
    domain: Literal["WEATHER", "CRYPTO", "MACRO", "SPORTS"]
    contract_id: Optional[str] = None
    model_probability: Optional[float] = None
    venue: Optional[str] = None
    venue_bid: Optional[float] = None
    venue_ask: Optional[float] = None
    net_edge: Optional[float] = None
    eligibility_state: str
    reason_codes: List[str]
    provenance: Dict[str, Any]


class ScannerSummaryEnvelope(ContractModel):
    schema_version: Literal["rca.scanner-summary.v1"] = "rca.scanner-summary.v1"
    qualification_state: QualificationState
    source_mode: SourceMode
    generated_at_utc: datetime
    reason_codes: List[str]
    data: List[DomainScannerData]


class PersonalScmaData(ContractModel):
    account_id: str
    principal_cents: int
    unreserved_cash_cents: int
    realized_pnl_cents: int
    unrealized_pnl_cents: Optional[int]
    retained_reinvestment_history_cents: Optional[List[int]]
    open_positions: Optional[List[Dict[str, Any]]]
    risk_policy_status: Optional[str]
    risk_ceiling: Optional[float]
    authoritative_as_of_utc: datetime


class PersonalScmaEnvelope(ContractModel):
    schema_version: Literal["rca.personal-scma.v1"] = "rca.personal-scma.v1"
    qualification_state: QualificationState
    source_mode: SourceMode
    generated_at_utc: datetime
    reason_codes: List[str]
    data: Optional[PersonalScmaData]

