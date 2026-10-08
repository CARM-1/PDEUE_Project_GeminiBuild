"""Wave 5 deterministic, headless autonomous qualification harness."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.domain.accounting_gateway import AccountingGateway
from app.domain.capital_ledger import CapitalLedger
from app.domain.daemon_loop import AutonomousExecutionLoop


def run_qualification_soak(num_cycles: int = 50,
                           starting_cents: int = 10_000) -> Dict[str, int]:
    """Run and assert the complete autonomous paper lifecycle."""
    if not isinstance(num_cycles, int) or num_cycles <= 0:
        raise ValueError("num_cycles must be a positive integer")
    if not isinstance(starting_cents, int) or starting_cents < 4_000:
        raise ValueError("starting_cents must be an integer of at least 4000")
    gateway = AccountingGateway()
    loop = AutonomousExecutionLoop(
        ledger=CapitalLedger(initial_balance_cents=starting_cents),
        accounting_gateway=gateway,
    )
    for _ in range(num_cycles):
        cycle = loop.run_cycle()
        assert cycle["cash_balance_cents"] >= cycle["dry_powder_floor_cents"]
        assert cycle["active_slots"] <= loop.SLOT_CAPACITY
        for settlement in cycle["settlements"]:
            distribution = settlement["distribution"]
            assert sum(distribution.values()) == settlement["position"]["payout_cents"]
    for event in gateway.event_outbox:
        assert gateway.verify_event(event), f"invalid outbox HMAC: {event['event_id']}"
        assert "account_number" not in str(event).lower()
        assert "routing_number" not in str(event).lower()
    sequence_ids = [event["sequence_id"] for event in gateway.event_outbox]
    assert sequence_ids == sorted(sequence_ids) and len(sequence_ids) == len(set(sequence_ids))
    return {
        "cycles_completed": loop.cycles_completed,
        "orders_posted": loop.orders_posted,
        "orders_filled": loop.orders_filled,
        "evictions_executed": loop.evictions_executed,
        "sweeps_emitted": loop.sweeps_emitted,
        "final_equity_cents": loop.total_equity_cents(),
    }


if __name__ == "__main__":
    print(run_qualification_soak())
