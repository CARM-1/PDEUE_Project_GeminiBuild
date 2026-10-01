"""Durable, exact-cent health telemetry for paper qualification runs."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


INT64_MIN = -(2**63)
INT64_MAX = 2**63 - 1


def require_cents(value: object, field: str) -> int:
    """Enforce ADR-008's signed 64-bit integer-cent representation."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field} must be an integer number of cents")
    if not INT64_MIN <= value <= INT64_MAX:
        raise OverflowError(f"{field} exceeds signed 64-bit cents")
    return value


class TelemetryHealthSink:
    """Compile and atomically replace the latest paper-soak checkpoint."""

    def __init__(self, export_path: str | os.PathLike[str] = "health_summary.json"):
        self.export_path = Path(export_path)

    def compile_health_payload(
        self,
        ledger_balances: Mapping[str, int],
        maker_stats: Mapping[str, int],
        spread_distributions: Mapping[str, float],
        circuit_breaker_status: Mapping[str, Any],
        rate_limiter_warnings: int = 0,
        *,
        cycle: int = 0,
        equity_trajectory_cents: list[int] | None = None,
        latency_sniping_events: int = 0,
        legging_scratches: int = 0,
        collateral_drift_cents: int = 0,
        timestamp: str | None = None,
    ) -> dict[str, Any]:
        balances = {
            str(name): require_cents(value, f"ledger_balances.{name}")
            for name, value in ledger_balances.items()
        }
        total = sum(balances.values())
        require_cents(total, "total_equity")
        trajectory = equity_trajectory_cents or [total]
        trajectory = [require_cents(v, "equity_trajectory_cents") for v in trajectory]
        posted = int(maker_stats.get("posted", 0))
        filled = int(maker_stats.get("filled", 0))
        expired = int(maker_stats.get("expired", 0))
        if min(posted, filled, expired) < 0 or filled > posted:
            raise ValueError("maker counters must be non-negative and fills cannot exceed posts")

        return {
            "schema_version": "rc-c.v1",
            "timestamp": timestamp or datetime.now(timezone.utc).isoformat(),
            "checkpoint_cycle": int(cycle),
            "status": "DEGRADED" if circuit_breaker_status.get("is_tripped", False) else "HEALTHY",
            "balances_cents": {
                "founder_scma": balances.get("founder_scma", 0),
                "cfcp_family_pool": balances.get("cfcp", 0),
                "faep_founder_pool": balances.get("faep", 0),
                "total_equity": total,
            },
            "qualification_metrics": {
                "equity_trajectory_cents": trajectory,
                "order_volume": posted,
                "empirical_fill_ratio": round(filled / posted, 6) if posted else 0.0,
                "fifo_fill_ratio_expectation": 0.75,
                "latency_sniping_events": int(latency_sniping_events),
                "legging_scratches": int(legging_scratches),
                "collateral_drift_cents": require_cents(collateral_drift_cents, "collateral_drift_cents"),
            },
            "maker_execution_metrics": {
                "bids_posted": posted,
                "bids_filled": filled,
                "bids_expired": expired,
                "fill_ratio": round(filled / posted, 4) if posted else 0.0,
            },
            "spread_distributions": {
                domain: float(spread_distributions.get(domain, 0.0))
                for domain in ("WEATHER", "MACRO", "SPORTS", "CRYPTO")
            },
            "runtime_safeguards": {
                "circuit_breaker_tripped": bool(circuit_breaker_status.get("is_tripped", False)),
                "trip_reason": circuit_breaker_status.get("trip_reason"),
                "rate_limiter_warnings": int(rate_limiter_warnings),
            },
        }

    def export_health_summary(self, payload: Mapping[str, Any]) -> str:
        """Write, fsync, and rename in one directory so readers never see tears."""
        self.export_path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(
            prefix=f".{self.export_path.name}.", suffix=".tmp", dir=self.export_path.parent
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(payload, stream, indent=2, sort_keys=True, allow_nan=False)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.export_path)
            directory_fd = os.open(self.export_path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except BaseException:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
            raise
        return str(self.export_path)
