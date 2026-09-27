"""SCMA float-cap monitoring and signed IF-038 sweep staging."""
from datetime import datetime, timezone
from typing import Dict, Optional
from uuid import uuid4

from app.domain.accounting_gateway import AccountingGateway
from app.domain.capital_ledger import CapitalLedger


class FloatSweepMonitor:
    """Keep venue cash at or below the $25,000 SCMA high-watermark."""

    HIGH_WATERMARK_CENTS = 2_500_000

    def scan_and_sweep(
        self,
        account_id: str,
        ledger: CapitalLedger,
        accounting_gateway: AccountingGateway,
    ) -> Optional[Dict]:
        if account_id != 'MASTER' and account_id in ledger.members:
            balance_cents = ledger.members[account_id]['balance_cents']
        else:
            balance_cents = ledger.balance_cents

        surplus_cents = balance_cents - self.HIGH_WATERMARK_CENTS
        if surplus_cents <= 0:
            return None

        reservation_id = f'FLOAT-SWEEP-{uuid4().hex[:12].upper()}'
        if not ledger.reserve_capital(reservation_id, surplus_cents, account_id=account_id):
            return None

        payload = {
            '@context': 'https://schema.pdeue.org/accounting/v1',
            'event_type': 'DIVIDEND_DISTRIBUTION_SCHEDULED',
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'scma_id': account_id,
            'amount_cents': surplus_cents,
            'tier': 'GREEN',
            'destination_opaque_token': 'IFAS',
            'source': 'FLOAT_CAP_SWEEP',
        }
        try:
            event = accounting_gateway.stage_if038_event(payload)
        except Exception:
            # Event staging and cash reservation are one logical operation.
            ledger.release_reservation(reservation_id, account_id=account_id)
            raise
        event['reservation_id'] = reservation_id
        return event
