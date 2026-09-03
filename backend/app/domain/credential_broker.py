import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional

class VenueCredentialBroker:
    """
    B7-EXE-07 Venue Credential Broker.
    Presents least-privilege secret references without exposing plaintext credentials.
    """
    def __init__(self):
        self._secrets: Dict[str, str] = {}
        self._leases: Dict[str, Dict[str, Any]] = {}

    def register_credential(self, tenant_id: str, venue: str, secret_key: str) -> str:
        ref_id = f'REF-{uuid.uuid4().hex[:8].upper()}'
        storage_key = f'{tenant_id}:{venue.upper()}'
        self._secrets[storage_key] = secret_key
        return ref_id

    def acquire_lease(self, tenant_id: str, venue: str, ttl_seconds: int = 300) -> Dict[str, Any]:
        storage_key = f'{tenant_id}:{venue.upper()}'
        if storage_key not in self._secrets:
            return {'status': 'REJECTED', 'reason': 'CREDENTIAL_NOT_FOUND', 'lease_id': None}
        lease_id = f'LEASE-{uuid.uuid4().hex[:8].upper()}'
        now = datetime.now(timezone.utc)
        lease = {
            'lease_id': lease_id,
            'tenant_id': tenant_id,
            'venue': venue.upper(),
            'issued_at': now.isoformat(),
            'expires_at': (now + timedelta(seconds=ttl_seconds)).isoformat(),
            'is_revoked': False
        }
        self._leases[lease_id] = lease
        return {'status': 'GRANTED', 'lease': lease}

    def validate_lease(self, lease_id: str) -> bool:
        lease = self._leases.get(lease_id)
        if not lease or lease.get('is_revoked', False):
            return False
        expires_at = datetime.fromisoformat(lease['expires_at'])
        return datetime.now(timezone.utc) < expires_at

    def revoke_lease(self, lease_id: str) -> bool:
        if lease_id in self._leases:
            self._leases[lease_id]['is_revoked'] = True
            return True
        return False
