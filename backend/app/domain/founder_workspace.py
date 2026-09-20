"""Read-only aggregation and internal controls for the RC-A Founder surfaces."""
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Optional

from app.domain.capital_ledger import CapitalLedger
from app.schemas.rca_workspace import (
    DomainScannerData, ExecutiveCapitalData, ExecutiveCapitalEnvelope,
    PersonalScmaData, PersonalScmaEnvelope, QualificationState,
    ScannerSummaryEnvelope, SourceMode,
)

DOMAINS = ("WEATHER", "CRYPTO", "MACRO", "SPORTS")
PROVENANCE_FIELDS = {
    "WEATHER": ("station_id", "ensemble_source", "forecast_run_utc"),
    "CRYPTO": ("asset", "price_source", "observation_utc"),
    "MACRO": ("series_id", "release_source", "release_utc"),
    "SPORTS": ("league", "event_id", "odds_source", "observation_utc"),
}


class FounderWorkspaceService:
    def __init__(self, ledger: Optional[CapitalLedger] = None) -> None:
        self.ledger = ledger or CapitalLedger(initial_balance_cents=0)
        self.dry_powder_policy: Optional[Dict[str, Any]] = None
        self.scanner_records: Dict[str, Dict[str, Any]] = {}
        self.authoritative_as_of_utc: Optional[str] = None
        self.halted = False
        self.workers_stopped = False
        self.pending_approvals = []

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    def capital_summary(self) -> ExecutiveCapitalEnvelope:
        now = self._now()
        if not self.dry_powder_policy or not self.authoritative_as_of_utc:
            reasons = ["DRY_POWDER_POLICY_UNRESOLVED"] if not self.dry_powder_policy else []
            if not self.authoritative_as_of_utc:
                reasons.append("AUTHORITATIVE_CAPITAL_TIMESTAMP_UNAVAILABLE")
            return ExecutiveCapitalEnvelope(
                qualification_state=QualificationState.QUALIFICATION_PENDING,
                source_mode=SourceMode.OFFLINE, generated_at_utc=now,
                reason_codes=reasons, data=None,
            )
        reserved = sum(self.ledger.reservations.values())
        payload = ExecutiveCapitalData(
            total_equity_cents=int(self.ledger.balance_cents + reserved),
            unreserved_cash_cents=int(self.ledger.balance_cents),
            dry_powder_floor_cents=int(self.dry_powder_policy["floor_cents"]),
            dry_powder_policy_version=str(self.dry_powder_policy["version"]),
            dry_powder_policy_status=str(self.dry_powder_policy["status"]),
            cfcp_balance_cents=int(self.ledger.central_family_pool_cents),
            faep_balance_cents=int(self.ledger.founder_pool_cents),
            active_scma_count=len(self.ledger.members),
            authoritative_as_of_utc=datetime.fromisoformat(self.authoritative_as_of_utc),
        )
        return ExecutiveCapitalEnvelope(
            qualification_state=QualificationState.QUALIFIED, source_mode=SourceMode.OFFLINE,
            generated_at_utc=now, reason_codes=[], data=payload,
        )

    def scanner_summary(self) -> ScannerSummaryEnvelope:
        rows = []
        summary_reasons = []
        for domain in DOMAINS:
            record = self.scanner_records.get(domain)
            if record is None:
                reason = f"{domain}_AUTHORITATIVE_SCAN_UNAVAILABLE"
                summary_reasons.append(reason)
                rows.append(DomainScannerData(
                    domain=domain, eligibility_state="QUALIFICATION_PENDING",
                    reason_codes=[reason], provenance={},
                ))
                continue
            provenance = {k: record[k] for k in PROVENANCE_FIELDS[domain] if k in record}
            missing = [k for k in PROVENANCE_FIELDS[domain] if k not in provenance]
            reasons = [f"{domain}_PROVENANCE_{k.upper()}_UNAVAILABLE" for k in missing]
            rows.append(DomainScannerData(
                domain=domain, contract_id=record.get("contract_id"),
                model_probability=record.get("model_probability"), venue=record.get("venue"),
                venue_bid=record.get("venue_bid"), venue_ask=record.get("venue_ask"),
                net_edge=record.get("net_edge"),
                eligibility_state=record.get("eligibility_state", "QUALIFICATION_PENDING"),
                reason_codes=reasons + list(record.get("reason_codes", [])), provenance=provenance,
            ))
            summary_reasons.extend(reasons)
        state = QualificationState.QUALIFIED if not summary_reasons else QualificationState.QUALIFICATION_PENDING
        return ScannerSummaryEnvelope(
            qualification_state=state, source_mode=SourceMode.OFFLINE,
            generated_at_utc=self._now(), reason_codes=summary_reasons, data=rows,
        )

    def personal_summary(self, subject: str) -> PersonalScmaEnvelope:
        now = self._now()
        # The authoritative ownership key is the authenticated identity subject.
        account = self.ledger.members.get(subject)
        if not account or not self.authoritative_as_of_utc:
            reasons = []
            if not account:
                reasons.append("FOUNDER_ACCOUNT_OWNERSHIP_MAPPING_UNAVAILABLE")
            if not self.authoritative_as_of_utc:
                reasons.append("AUTHORITATIVE_PERSONAL_TIMESTAMP_UNAVAILABLE")
            return PersonalScmaEnvelope(
                qualification_state=QualificationState.QUALIFICATION_PENDING,
                source_mode=SourceMode.OFFLINE, generated_at_utc=now,
                reason_codes=reasons, data=None,
            )
        return PersonalScmaEnvelope(
            qualification_state=QualificationState.QUALIFIED, source_mode=SourceMode.OFFLINE,
            generated_at_utc=now, reason_codes=["POSITION_MARKS_UNAVAILABLE", "REINVESTMENT_HISTORY_UNAVAILABLE"],
            data=PersonalScmaData(
                account_id=subject, principal_cents=int(account.get("seed_capital_cents", account["balance_cents"])),
                unreserved_cash_cents=int(account["balance_cents"]),
                realized_pnl_cents=int(account.get("lifetime_profit_cents", 0)),
                unrealized_pnl_cents=None, retained_reinvestment_history_cents=None,
                open_positions=None, risk_policy_status=account.get("risk_policy_status"),
                risk_ceiling=account.get("max_risk_pct"),
                authoritative_as_of_utc=datetime.fromisoformat(self.authoritative_as_of_utc),
            ),
        )

    def system_halt(self, actor: str) -> Dict[str, Any]:
        self.halted = True
        self.workers_stopped = True
        return {
            "schema_version": "rca.system-halt.v1", "status": "HALTED",
            "actor": actor, "workers_stopped": True,
            "external_cancellation_state": "NOT_AUTHORIZED_NOT_ATTEMPTED",
            "generated_at_utc": self._now().isoformat(),
        }

