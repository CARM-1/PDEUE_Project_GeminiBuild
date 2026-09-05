import hmac
import hashlib
import json
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

SECRET_KEY_DEFAULT = 'pdeue_fge_accounting_signing_key_v1'

class AccountingGateway:
    def __init__(self, secret_key: str = SECRET_KEY_DEFAULT):
        self.secret_key = secret_key.encode('utf-8')
        self.event_outbox: List[Dict[str, Any]] = []
        self.reconciliation_receipts: Dict[str, Dict[str, Any]] = {}
        self._seq_counter = 0

    def _canonicalize_payload(self, payload: Dict[str, Any]) -> bytes:
        return json.dumps(payload, sort_keys=True, separators=(',', ':')).encode('utf-8')

    def sign_payload(self, canonical_bytes: bytes) -> str:
        return hmac.new(self.secret_key, canonical_bytes, hashlib.sha256).hexdigest()

    def verify_signature(self, canonical_bytes: bytes, signature: str) -> bool:
        expected = self.sign_payload(canonical_bytes)
        return hmac.compare_digest(expected, signature)

    def emit_settlement_event(
        self,
        contract_id: str,
        scma_id: str,
        gross_payout_cents: int,
        scma_net_cents: int,
        cfcp_cents: int,
        faep_cents: int,
        settled_at: Optional[str] = None
    ) -> Dict[str, Any]:
        assert scma_net_cents + cfcp_cents + faep_cents == gross_payout_cents, 'ADR-008 Integer Cent Conservation Violation'
        self._seq_counter += 1
        seq_id = self._seq_counter
        event_id = f'ACT-EVT-{seq_id:08d}'
        ts = settled_at or datetime.now(timezone.utc).isoformat()

        body = {
            '@context': 'https://schema.pdeue.org/accounting/v1',
            '@type': 'WaterfallDistributionEvent',
            'event_id': event_id,
            'sequence_id': seq_id,
            'timestamp': ts,
            'contract_id': contract_id,
            'scma_id': scma_id,
            'amounts_cents': {
                'gross_payout': gross_payout_cents,
                'scma_net': scma_net_cents,
                'cfcp_allocation': cfcp_cents,
                'faep_allocation': faep_cents
            }
        }

        canonical_bytes = self._canonicalize_payload(body)
        sig = self.sign_payload(canonical_bytes)

        envelope = {
            'event_id': event_id,
            'sequence_id': seq_id,
            'payload': body,
            'signature_hmac_sha256': sig,
            'status': 'EMITTED'
        }
        self.event_outbox.append(envelope)
        return envelope

    def get_outbox_events(self, since_seq: int = 0, limit: int = 50) -> List[Dict[str, Any]]:
        return [e for e in self.event_outbox if e['sequence_id'] > since_seq][:limit]

    def acknowledge_receipt(
        self,
        ack_id: str,
        sequence_id: int,
        system_id: str,
        received_hash: str
    ) -> Dict[str, Any]:
        if ack_id in self.reconciliation_receipts:
            return {'status': 'DUPLICATE', 'ack_id': ack_id, 'acknowledged': True}

        matching_events = [e for e in self.event_outbox if e['sequence_id'] == sequence_id]
        if not matching_events:
            return {'status': 'REJECTED', 'reason': 'EVENT_NOT_FOUND'}

        evt = matching_events[0]
        c_bytes = self._canonicalize_payload(evt['payload'])
        if hashlib.sha256(c_bytes).hexdigest() != received_hash:
            return {'status': 'REJECTED', 'reason': 'HASH_MISMATCH'}

        evt['status'] = 'RECONCILED'
        receipt = {
            'ack_id': ack_id,
            'sequence_id': sequence_id,
            'system_id': system_id,
            'received_hash': received_hash,
            'reconciled_at': datetime.now(timezone.utc).isoformat()
        }
        self.reconciliation_receipts[ack_id] = receipt
        return {'status': 'SUCCESS', 'ack_id': ack_id, 'acknowledged': True}
