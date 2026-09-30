import hmac
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional

from jsonschema import Draft7Validator, FormatChecker

SECRET_KEY_DEFAULT = 'pdeue_fge_accounting_signing_key_v1'

_BANKING_KEYS = {'account_number', 'routing_number', 'bank_account', 'bank_credentials',
                 'iban', 'swift_code'}

class AccountingGateway:
    def __init__(self, secret_key: str = SECRET_KEY_DEFAULT):
        self.secret_key = secret_key.encode('utf-8')
        self.event_outbox: List[Dict[str, Any]] = []
        self.reconciliation_receipts: Dict[str, Dict[str, Any]] = {}
        self._seq_counter = 0
        schema_dir = Path(__file__).resolve().parents[3] / 'contracts' / 'schemas'
        self._fsap_validators = {}
        for interface_id, filename in {
            'IF-038': 'IF-038_DividendDistributionScheduled.json',
            'IF-039': 'IF-039_StabilityAdvanceFacilityRegistered.json',
            'IF-040': 'IF-040_DividendSweepAmortizationApplied.json',
            'IF-041': 'IF-041_ContributorIncentiveHarvested.json',
        }.items():
            with (schema_dir / filename).open(encoding='utf-8') as schema_file:
                schema = json.load(schema_file)
            self._fsap_validators[interface_id] = Draft7Validator(
                schema, format_checker=FormatChecker()
            )

    def _canonicalize_payload(self, payload: Dict[str, Any]) -> bytes:
        return json.dumps(payload, sort_keys=True, separators=(',', ':')).encode('utf-8')

    def sign_payload(self, canonical_bytes: bytes) -> str:
        return hmac.new(self.secret_key, canonical_bytes, hashlib.sha256).hexdigest()

    def verify_signature(self, canonical_bytes: bytes, signature: str) -> bool:
        expected = self.sign_payload(canonical_bytes)
        return hmac.compare_digest(expected, signature)

    def stage_event(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Stage a signed JSON-LD payload in the accounting outbox."""
        if payload.get('@context') != 'https://schema.pdeue.org/accounting/v1':
            raise ValueError('accounting events must use the accounting JSON-LD context')
        self._reject_banking_credentials(payload)
        self._seq_counter += 1
        seq_id = self._seq_counter
        event_id = f'ACT-EVT-{seq_id:08d}'
        canonical_bytes = self._canonicalize_payload(payload)
        envelope = {
            'event_id': event_id,
            'sequence_id': seq_id,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'payload': payload,
            'signature_hmac_sha256': self.sign_payload(canonical_bytes),
            'status': 'EMITTED'
        }
        self.event_outbox.append(envelope)
        return envelope

    def _reject_banking_credentials(self, value: Any) -> None:
        """Fail closed if an ADR-011 prohibited banking field is present."""
        if isinstance(value, dict):
            forbidden = _BANKING_KEYS.intersection(str(key).lower() for key in value)
            if forbidden:
                raise ValueError(f'banking credentials are prohibited: {sorted(forbidden)[0]}')
            for nested in value.values():
                self._reject_banking_credentials(nested)
        elif isinstance(value, list):
            for nested in value:
                self._reject_banking_credentials(nested)

    def verify_event(self, envelope: Dict[str, Any]) -> bool:
        signature = envelope.get('signature_hmac_sha256', '')
        return len(signature) == 64 and self.verify_signature(
            self._canonicalize_payload(envelope.get('payload', {})), signature
        )

    def emit_capital_sweep(self, settled_balance_cents: int, scma_id: str = 'MASTER',
                           destination_opaque_token: str = 'EXT-REF-IFAS') -> Optional[Dict[str, Any]]:
        """Stage only the amount above the $25,000 high-watermark."""
        if not isinstance(settled_balance_cents, int) or isinstance(settled_balance_cents, bool):
            raise TypeError('settled_balance_cents must be an integer')
        surplus = settled_balance_cents - 2_500_000
        if surplus <= 0:
            return None
        payload = {
            '@context': 'https://schema.pdeue.org/accounting/v1',
            'event_type': 'DIVIDEND_DISTRIBUTION_SCHEDULED',
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'scma_id': scma_id,
            'amount_cents': surplus,
            'tier': 'GREEN',
            'destination_opaque_token': destination_opaque_token,
            'source': 'FLOAT_CAP_SWEEP',
        }
        event = self.stage_if038_event(payload)
        event['event_type'] = 'CAPITAL_SWEEP'
        return event

    def stage_if038_event(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._stage_typed_event(payload, 'IF-038', 'DIVIDEND_DISTRIBUTION_SCHEDULED')

    def stage_if039_event(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._stage_typed_event(
            payload, 'IF-039', 'STABILITY_ADVANCE_FACILITY_REGISTERED'
        )

    def stage_if040_event(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._stage_typed_event(
            payload, 'IF-040', 'DIVIDEND_SWEEP_AMORTIZATION_APPLIED'
        )

    def stage_if041_event(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._stage_typed_event(
            payload, 'IF-041', 'CONTRIBUTOR_INCENTIVE_HARVESTED'
        )

    def _stage_typed_event(
        self, payload: Dict[str, Any], interface_id: str, expected_event_type: str
    ) -> Dict[str, Any]:
        if payload.get('event_type') != expected_event_type:
            raise ValueError(f'expected event_type {expected_event_type}')
        self._fsap_validators[interface_id].validate(payload)
        return self.stage_event(payload)

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
            'timestamp': ts,
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
