"""Familial Stability Advance Pool accounting rules.

The engine keeps monetary state exclusively as integer cents.  Percentages are
converted through their decimal string representation before any calculation,
so binary floating-point never participates in the accounting calculation.
"""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import json
from pathlib import Path
from typing import Any, Dict, Tuple

from jsonschema import Draft7Validator, FormatChecker


_SCHEMA_PATH = (
    Path(__file__).resolve().parents[3]
    / "contracts"
    / "schemas"
    / "IF-039_StabilityAdvanceFacilityRegistered.json"
)
_MIN_RATIO = Decimal("0.30")
_MAX_RATIO = Decimal("0.70")
_LOCK_PERIOD = timedelta(days=30)
_MAX_INT64 = 2**63 - 1
_REQUIRED_SIGNERS = {"F2_HEAD_OF_HOUSEHOLD", "CHIEF_ADMINISTRATOR"}


class FSAPEngine:
    """Register and amortize FSAP facilities in memory."""

    def __init__(self, schema_path: Path | str = _SCHEMA_PATH) -> None:
        with Path(schema_path).open(encoding="utf-8") as schema_file:
            schema = json.load(schema_file)
        Draft7Validator.check_schema(schema)
        self._registration_validator = Draft7Validator(
            schema, format_checker=FormatChecker()
        )
        self._facilities: Dict[str, Dict[str, Any]] = {}

    @staticmethod
    def _ratio(value: float) -> Decimal:
        if isinstance(value, bool):
            raise ValueError("interception percentage must be numeric")
        try:
            ratio = Decimal(str(value))
        except (InvalidOperation, ValueError) as exc:
            raise ValueError("interception percentage must be numeric") from exc
        if not ratio.is_finite() or not _MIN_RATIO <= ratio <= _MAX_RATIO:
            raise ValueError("interception percentage must be between 0.30 and 0.70")
        return ratio

    @staticmethod
    def _cents(value: int, name: str, *, allow_zero: bool = True) -> int:
        minimum = 0 if allow_zero else 1
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{name} must be integer cents")
        if value < minimum or value > _MAX_INT64:
            raise ValueError(f"{name} must be between {minimum} and {_MAX_INT64}")
        return value

    def register_facility(self, facility_data: dict) -> dict:
        """Validate and retain an IF-039 facility registration."""

        self._registration_validator.validate(facility_data)
        roles = [signature["role"] for signature in facility_data["governance_signatures"]]
        if len(roles) != 2 or set(roles) != _REQUIRED_SIGNERS:
            raise ValueError(
                "dual control requires exactly one F2 head and one chief administrator"
            )

        total = self._cents(
            facility_data["total_advance_cents"], "total_advance_cents", allow_zero=False
        )
        plan = facility_data["disbursement_plan"]
        allocated = self._cents(plan["initial_scma_seed_cents"], "initial_scma_seed_cents")
        allocated += sum(
            self._cents(payment["amount_cents"], "amount_cents", allow_zero=False)
            for payment in plan["direct_creditor_payments"]
        )
        if allocated != total:
            raise ValueError("disbursement plan must conserve total_advance_cents")

        facility_id = facility_data["facility_id"]
        if facility_id in self._facilities:
            raise ValueError(f"facility already registered: {facility_id}")
        ratio = self._ratio(facility_data["amortization_terms"]["interception_percentage"])
        self._facilities[facility_id] = {
            "registration": deepcopy(facility_data),
            "remaining_advance_cents": total,
            "interception_ratio": ratio,
            "last_ratio_adjusted_at": None,
        }
        return deepcopy(facility_data)

    def calculate_sweep_split(
        self, sweep_cents: int, interception_pct: float
    ) -> Tuple[int, int]:
        """Return a deterministic, cent-conserving amortization/member split."""

        sweep = self._cents(sweep_cents, "sweep_cents")
        ratio = self._ratio(interception_pct)
        amortization = int(
            (Decimal(sweep) * ratio).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        )
        return amortization, sweep - amortization

    def update_interception_ratio(
        self,
        facility_id: str,
        actor_role: str,
        new_pct: float,
        current_time: datetime,
    ) -> float:
        """Apply an authorized ratio change, subject to the 30-day lock."""

        if actor_role != "F2_HEAD_OF_HOUSEHOLD":
            raise PermissionError("only F2_HEAD_OF_HOUSEHOLD may adjust interception")
        if facility_id not in self._facilities:
            raise KeyError(f"unknown facility: {facility_id}")
        if not isinstance(current_time, datetime) or current_time.tzinfo is None:
            raise ValueError("current_time must be a timezone-aware datetime")
        ratio = self._ratio(new_pct)
        state = self._facilities[facility_id]
        last_adjusted = state["last_ratio_adjusted_at"]
        if last_adjusted is not None and current_time - last_adjusted < _LOCK_PERIOD:
            raise ValueError("interception ratio is locked for 30 days between adjustments")
        state["interception_ratio"] = ratio
        state["last_ratio_adjusted_at"] = current_time
        return float(ratio)

    def apply_amortization(self, facility_id: str, sweep_cents: int) -> dict:
        """Reduce the facility balance and produce an IF-040 payload."""

        if facility_id not in self._facilities:
            raise KeyError(f"unknown facility: {facility_id}")
        state = self._facilities[facility_id]
        sweep = self._cents(sweep_cents, "sweep_cents")
        proposed, member = self.calculate_sweep_split(
            sweep, float(state["interception_ratio"])
        )
        amortization = min(proposed, state["remaining_advance_cents"])
        member += proposed - amortization
        state["remaining_advance_cents"] -= amortization
        registration = state["registration"]
        return {
            "@context": "https://schema.pdeue.org/accounting/v1",
            "event_type": "DIVIDEND_SWEEP_AMORTIZATION_APPLIED",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "facility_id": facility_id,
            "scma_id": registration["recipient_scma_id"],
            "total_sweep_cents": sweep,
            "amortization_credit_cents": amortization,
            "member_liquid_cents": member,
            "remaining_advance_cents": state["remaining_advance_cents"],
        }
