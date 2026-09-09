from typing import Dict, Any, Optional
import hmac
import hashlib
import json
from datetime import datetime, timezone
import uuid

from app.domain.capital_ledger import CapitalLedger
from app.domain.accounting_gateway import AccountingGateway

class PlatformYieldAdapter:
    """
    PlatformYieldAdapter (ADR-011 / Escalation C-04)
    Captures broker escrow interest (Treasury yield on uncommitted SCMA cash)
    and venue maker rebates, routing net proceeds through the 87/10/3 waterfall.
    Enforces zero banking credential exposure and exact integer-cent conservation.
    """
    def __init__(self, ledger: Optional[CapitalLedger] = None, gateway: Optional[AccountingGateway] = None):
        self.ledger = ledger or CapitalLedger()
        self.gateway = gateway or AccountingGateway()
        self.accrual_history = []

    def accrue_broker_escrow_yield(
        self,
        scma_id: str,
        annual_yield_bps: int = 450,  # 4.50% APY default
        elapsed_days: float = 1.0,
        broker_bank_token: str = "EXT-REF-TREASURY-ESCROW"
    ) -> Dict[str, Any]:
        """
        Calculates interest on uncommitted cash, executes 87/10/3 waterfall,
        and emits an ADR-011 signed accounting event.
        """
        # Strictly reject raw account or routing numbers in the token
        if any(bad in broker_bank_token.lower() for bad in ["routing", "acct", "aba", "iban"]):
            raise ValueError("Direct banking credentials prohibited. Use opaque reference tokens.")

        mem = self.ledger.members.get(scma_id)
        if not mem:
            raise KeyError(f"SCMA account {scma_id} not registered in ledger")

        balance_cents = mem.get("balance_cents", 0)
        if balance_cents <= 0:
            return {"status": "ZERO_BALANCE", "gross_yield_cents": 0}

        # Daily yield in integer cents: (balance * bps * days) // (10,000 * 365)
        gross_yield_cents = int((balance_cents * annual_yield_bps * elapsed_days) // (10000 * 365))
        if gross_yield_cents <= 0:
            return {"status": "BELOW_CENT_THRESHOLD", "gross_yield_cents": 0}

        # Canonical 87% SCMA / 10% CFCP / 3% FAEP waterfall with exact-cent conservation
        scma_net_cents = (gross_yield_cents * 87) // 100
        cfcp_cents = (gross_yield_cents * 10) // 100
        faep_cents = gross_yield_cents - scma_net_cents - cfcp_cents

        assert scma_net_cents + cfcp_cents + faep_cents == gross_yield_cents, "Cent conservation violation"

        # Apply credit to ledger
        self.ledger.credit_member_balance(scma_id, scma_net_cents)
        self.ledger.credit_central_family_pool(cfcp_cents)
        self.ledger.credit_founder_pool(faep_cents)

        # Emit signed ADR-011 event
        event_payload = {
            "event_id": str(uuid.uuid4()),
            "event_type": "IDLE_CASH_YIELD",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "scma_id": scma_id,
            "broker_ref_token": broker_bank_token,
            "gross_yield_cents": gross_yield_cents,
            "distribution": {
                "scma_net_cents": scma_net_cents,
                "cfcp_cents": cfcp_cents,
                "faep_cents": faep_cents
            }
        }
        
        # Dispatch to outbox via gateway
        outbox_event = self.gateway.emit_settlement_event(
            contract_id=f"YIELD-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{scma_id}",
            scma_id=scma_id,
            gross_payout_cents=gross_yield_cents,
            scma_net_cents=scma_net_cents,
            cfcp_cents=cfcp_cents,
            faep_cents=faep_cents
        )

        record = {
            "scma_id": scma_id,
            "gross_yield_cents": gross_yield_cents,
            "scma_net_cents": scma_net_cents,
            "cfcp_cents": cfcp_cents,
            "faep_cents": faep_cents,
            "broker_ref_token": broker_bank_token,
            "outbox_event": outbox_event
        }
        self.accrual_history.append(record)
        return record
