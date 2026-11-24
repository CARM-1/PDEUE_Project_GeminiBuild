"""Standardized Fail-Closed ReadModelEnvelope[T] Contract (Milestone E5).

Every PDEUE portal read-model endpoint surfaces a deterministic fail-closed
``ReadModelEnvelope[T]`` state so frontends render unmistakable institutional
status banners and never fabricate placeholder numbers when telemetry is
unavailable, Gate G1 is in ``HOLD_OBSERVATIONS_ONLY``, or Directive R-04
Emergency Halt is engaged.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
import os
from typing import Any, Dict, Generic, Optional, TypeVar

from pydantic import BaseModel, ConfigDict, model_validator

T = TypeVar("T")


class ReadModelStatus(str, Enum):
    OK = "OK"
    QUALIFICATION_PENDING = "QUALIFICATION_PENDING"
    TRADING_HALTED = "TRADING_HALTED"
    DEGRADED_RETRYING = "DEGRADED_RETRYING"


BANNER_COPY: Dict[ReadModelStatus, tuple[str, str]] = {
    ReadModelStatus.OK: (
        "OPERATIONAL — VERIFIED READ MODEL",
        "Authoritative telemetry verified under exact-cent ADR-008 invariants.",
    ),
    ReadModelStatus.QUALIFICATION_PENDING: (
        "NOT AVAILABLE — QUALIFICATION PENDING",
        "Gate G1 is in HOLD_OBSERVATIONS_ONLY (paper observation mode). Live venue execution telemetry is withheld until qualification sign-off.",
    ),
    ReadModelStatus.TRADING_HALTED: (
        "TRADING HALTED — EXECUTIVE OVERRIDE",
        "TRADING HALTED: DIRECTIVE R-04 ENGAGED — New execution is paused fail-closed until Chief Administrator resumption.",
    ),
    ReadModelStatus.DEGRADED_RETRYING: (
        "UNAVAILABLE — ENGINE UNREACHABLE",
        "Engine read-model telemetry is degraded or unreachable; retrying fail-closed with zero placeholder figures.",
    ),
}


class ReadModelEnvelope(BaseModel, Generic[T]):
    """Fail-closed generic read-model envelope shared across PDEUE portals."""

    model_config = ConfigDict(extra="forbid")

    status: ReadModelStatus
    data: Optional[T] = None
    reason: Optional[str] = None
    updated_at_utc: str
    banner_headline: str
    banner_detail: str
    surface: str = "portal"
    gate_g1_status: str = "HOLD_OBSERVATIONS_ONLY"
    directive_r04_status: str = "NORMAL"
    venue_mode: str = "paper"
    synthetic_fills_present: bool = False

    @model_validator(mode="after")
    def _enforce_fail_closed_invariants(self) -> "ReadModelEnvelope[T]":
        if self.status in {ReadModelStatus.TRADING_HALTED, ReadModelStatus.DEGRADED_RETRYING}:
            if self.data is not None:
                raise ValueError(
                    f"Fail-closed violation: ReadModelEnvelope.data MUST be None when status={self.status.value}"
                )
        if self.status != ReadModelStatus.OK and not (self.reason and self.reason.strip()):
            raise ValueError(
                f"Fail-closed violation: ReadModelEnvelope.reason is required when status={self.status.value}"
            )
        return self


def current_gate_g1_status() -> str:
    return (
        os.getenv("PDEUE_GATE_G1_STATUS", "HOLD_OBSERVATIONS_ONLY").strip().upper()
        or "HOLD_OBSERVATIONS_ONLY"
    )


def current_venue_mode() -> str:
    return os.getenv("PDEUE_VENUE_MODE", "paper").strip().lower() or "paper"


def build_read_model_envelope(
    data: Optional[T],
    *,
    surface: str = "portal",
    directive_r04_snapshot: Optional[Dict[str, Any]] = None,
    circuit_breaker_tripped: bool = False,
    circuit_breaker_reason: Optional[str] = None,
    gate_g1_status: Optional[str] = None,
    venue_mode: Optional[str] = None,
    degraded: bool = False,
    degraded_reason: Optional[str] = None,
    force_status: Optional[ReadModelStatus | str] = None,
    reason: Optional[str] = None,
    updated_at_utc: Optional[str] = None,
) -> ReadModelEnvelope[T]:
    """Resolve deterministic fail-closed ReadModelEnvelope state from live controls.

    Precedence (strictest fail-closed state wins):
    1. Explicit ``force_status`` (if supplied by caller or fault-injection test)
    2. ``TRADING_HALTED`` if Directive R-04 Emergency Halt or execution breaker is engaged
    3. ``DEGRADED_RETRYING`` if upstream engine/telemetry is unreachable or errored
    4. ``QUALIFICATION_PENDING`` if Gate G1 is ``HOLD_OBSERVATIONS_ONLY`` (default fail-closed)
    5. ``OK`` when qualified, healthy, and unhalted
    """
    now_utc = updated_at_utc or datetime.now(timezone.utc).isoformat()
    g1 = (gate_g1_status or current_gate_g1_status()).strip().upper()
    v_mode = (venue_mode or current_venue_mode()).strip().lower()
    r04 = directive_r04_snapshot or {"status": "NORMAL", "failsafe": "ARMED"}
    r04_status = str(r04.get("status", "NORMAL")).upper()
    is_halted = r04_status == "HALTED" or bool(circuit_breaker_tripped)

    resolved_status: ReadModelStatus
    resolved_reason: Optional[str] = reason
    resolved_data: Optional[T] = data

    if force_status is not None:
        resolved_status = (
            force_status
            if isinstance(force_status, ReadModelStatus)
            else ReadModelStatus(str(force_status).strip().upper())
        )
    elif is_halted:
        resolved_status = ReadModelStatus.TRADING_HALTED
    elif degraded:
        resolved_status = ReadModelStatus.DEGRADED_RETRYING
    elif g1 in {"HOLD_OBSERVATIONS_ONLY", "PENDING", "QUALIFICATION_PENDING"}:
        resolved_status = ReadModelStatus.QUALIFICATION_PENDING
    else:
        resolved_status = ReadModelStatus.OK

    headline, default_detail = BANNER_COPY[resolved_status]

    if resolved_status == ReadModelStatus.TRADING_HALTED:
        r04_status = "HALTED"
        resolved_data = None
        halt_detail = (
            resolved_reason
            or r04.get("halt_reason")
            or circuit_breaker_reason
            or "Directive R-04 Emergency Financial Halt engaged by executive control."
        )
        actor = r04.get("halted_by") or "EXECUTIVE_OVERRIDE"
        resolved_reason = f"TRADING HALTED: DIRECTIVE R-04 ENGAGED ({actor}) — {halt_detail}"
        banner_detail = resolved_reason
    elif resolved_status == ReadModelStatus.DEGRADED_RETRYING:
        resolved_data = None
        resolved_reason = (
            resolved_reason
            or degraded_reason
            or "UNAVAILABLE - ENGINE UNREACHABLE: telemetry stream unavailable; retrying fail-closed."
        )
        banner_detail = resolved_reason
    elif resolved_status == ReadModelStatus.QUALIFICATION_PENDING:
        resolved_data = None
        resolved_reason = (
            resolved_reason
            or f"NOT AVAILABLE - QUALIFICATION PENDING: Gate G1 is in {g1} ({v_mode} mode); live execution telemetry withheld."
        )
        banner_detail = resolved_reason
    else:
        resolved_reason = resolved_reason or None
        banner_detail = default_detail

    return ReadModelEnvelope[T](
        status=resolved_status,
        data=resolved_data,
        reason=resolved_reason,
        updated_at_utc=now_utc,
        banner_headline=headline,
        banner_detail=banner_detail,
        surface=surface,
        gate_g1_status=g1,
        directive_r04_status=r04_status,
        venue_mode=v_mode,
        synthetic_fills_present=False,
    )
