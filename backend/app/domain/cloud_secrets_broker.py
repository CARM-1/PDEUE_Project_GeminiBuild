from typing import Dict, Any, Optional
from datetime import datetime, timezone, timedelta
import uuid

class CloudSecretsBroker:
    """B7-EXE-07 Dynamic Venue Credential and Secrets Leasing Broker."""
    def __init__(self, use_mock_aws: bool = True):
        self.use_mock_aws = use_mock_aws
        self._mock_vault: Dict[str, Dict[str, str]] = {
            'KALSHI': {'api_key': 'kalshi_live_secret_mock_val', 'key_id': 'K-001'},
            'POLYMARKET': {'api_key': 'poly_live_secret_mock_val', 'key_id': 'P-001'}
        }
        self.active_leases: Dict[str, Dict[str, Any]] = {}

    def lease_venue_credentials(
        self,
        venue: str,
        tenant_id: str,
        ttl_seconds: int = 300
    ) -> Dict[str, Any]:
        venue_upper = venue.upper()
        if venue_upper not in self._mock_vault:
            return {'status': 'REJECTED', 'reason': f'Unknown venue: {venue}'}

        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=ttl_seconds)
        lease_id = f'LSE-{uuid.uuid4().hex[:8]}'
        creds = self._mock_vault[venue_upper]

        lease = {
            'lease_id': lease_id,
            'venue': venue_upper,
            'tenant_id': tenant_id,
            'key_id': creds['key_id'],
            'secret_token': creds['api_key'],
            'issued_at': now.isoformat(),
            'expires_at': expires_at.isoformat(),
            'revoked': False
        }
        self.active_leases[lease_id] = lease
        return {'status': 'LEASED', 'lease': lease}

    def validate_lease(self, lease_id: str) -> bool:
        lease = self.active_leases.get(lease_id)
        if not lease or lease['revoked']:
            return False
        expires_at = datetime.fromisoformat(lease['expires_at'])
        return datetime.now(timezone.utc) < expires_at

    def revoke_all_leases(self, reason: str = 'CIRCUIT_BREAKER_TRIPPED') -> int:
        count = 0
        for lease in self.active_leases.values():
            if not lease['revoked']:
                lease['revoked'] = True
                lease['revocation_reason'] = reason
                count += 1
        return count
