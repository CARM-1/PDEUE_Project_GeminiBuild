"""Process-local, short-lived venue credential leases.

The broker deliberately has no serialization or persistence hooks.  Production
deployments can provide a callable which reads a secret manager on demand;
tests use ``register_credential`` to seed the process-local vault.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from threading import RLock
from typing import Callable, Dict, Mapping, Optional, Tuple
from uuid import uuid4


@dataclass
class TenantCredentialLease:
    tenant_id: str
    venue: str
    api_key: str = field(repr=False)
    api_secret: str = field(repr=False)
    expires_at: datetime
    lease_id: str = field(default_factory=lambda: f"LSE-{uuid4().hex}")
    _revoked: bool = field(default=False, repr=False, compare=False)

    def is_valid(self) -> bool:
        """Return whether this lease remains usable at the current UTC time."""
        return not self._revoked and datetime.now(timezone.utc) < self.expires_at

    def revoke(self) -> None:
        """Invalidate and best-effort scrub the credential strings in memory."""
        self._revoked = True
        self.api_key = ""
        self.api_secret = ""


CredentialProvider = Callable[[str, str], Optional[Tuple[str, str]]]


class CredentialBroker:
    """Issue and revoke credentials without ever touching disk or logs."""

    def __init__(
        self,
        provider: Optional[CredentialProvider] = None,
        credentials: Optional[Mapping[Tuple[str, str], Tuple[str, str]]] = None,
    ) -> None:
        self._provider = provider
        self._credentials: Dict[Tuple[str, str], Tuple[str, str]] = {
            (tenant, venue.upper()): value
            for (tenant, venue), value in (credentials or {}).items()
        }
        self._leases: Dict[str, TenantCredentialLease] = {}
        self._lock = RLock()

    def register_credential(
        self, tenant_id: str, venue: str, api_key: str, api_secret: str = ""
    ) -> None:
        """Seed the volatile vault (primarily for bootstrap code and tests)."""
        if not tenant_id or not venue or not api_key:
            raise ValueError("tenant_id, venue, and api_key are required")
        with self._lock:
            self._credentials[(tenant_id, venue.upper())] = (api_key, api_secret)

    def _purge_expired(self) -> None:
        for lease_id, lease in list(self._leases.items()):
            if not lease.is_valid():
                lease.revoke()
                self._leases.pop(lease_id, None)

    def acquire_lease(
        self, tenant_id: str, venue: str, ttl_seconds: int = 300
    ) -> TenantCredentialLease:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        normalized_venue = venue.upper()
        with self._lock:
            self._purge_expired()
            credential = (
                self._provider(tenant_id, normalized_venue)
                if self._provider is not None
                else self._credentials.get((tenant_id, normalized_venue))
            )
            if credential is None:
                raise KeyError(f"no credentials registered for {tenant_id}/{normalized_venue}")
            lease = TenantCredentialLease(
                tenant_id=tenant_id,
                venue=normalized_venue,
                api_key=credential[0],
                api_secret=credential[1],
                expires_at=datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds),
            )
            self._leases[lease.lease_id] = lease
            return lease

    def revoke_lease(self, lease_id: str) -> None:
        with self._lock:
            self._purge_expired()
            lease = self._leases.pop(lease_id, None)
            if lease is not None:
                lease.revoke()

    def validate_lease(self, lease_id: str) -> bool:
        with self._lock:
            self._purge_expired()
            lease = self._leases.get(lease_id)
            return bool(lease and lease.is_valid())
