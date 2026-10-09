# -*- coding: utf-8 -*-
"""
PDEUE Orthogonal Fleet Engine (Stage 1A)
Enforces CFTC Rule 150.4 Anti-Aggregation, Ephemeral Credential Leasing,
and Statutory Minor Virtual Lineage Allocations.
"""
import time
from typing import Dict, List, Optional, Set

class DomainCollusionError(Exception):
    """Raised when an account attempts to place orders outside its assigned sector."""
    pass

class MinorProtectionError(PermissionError):
    """Raised when external exchange credentials or trading are requested for minors."""
    pass

class CredentialLease:
    def __init__(self, scma_id: str, venue: str, fingerprint: str, ttl_seconds: int = 300):
        self.scma_id = scma_id
        self.venue = venue
        self.fingerprint = fingerprint
        self.expires_at = time.time() + ttl_seconds

    def is_valid(self) -> bool:
        return time.time() < self.expires_at

class VenueCredentialBroker:
    """In-memory key lease broker adhering to ADR-011 (Zero Plaintext on Disk)."""
    def __init__(self):
        self._keyring: Dict[str, Dict[str, str]] = {}
        self._leases: Dict[str, CredentialLease] = {}

    def register_credential(self, scma_id: str, venue: str, key_material: str, is_custodial: bool = False):
        if is_custodial:
            raise MinorProtectionError(f"Statutory Violation: Minors ({scma_id}) cannot hold external exchange credentials.")
        if scma_id not in self._keyring:
            self._keyring[scma_id] = {}
        self._keyring[scma_id][venue] = key_material

    def acquire_lease(self, scma_id: str, venue: str, is_custodial: bool = False) -> CredentialLease:
        if is_custodial:
            raise MinorProtectionError(f"Statutory Violation: Minors ({scma_id}) cannot acquire trading leases.")
        fingerprint = f"LEAS-SHA256-{scma_id[:4]}-{venue[:3]}-{int(time.time())}"
        lease = CredentialLease(scma_id, venue, fingerprint)
        self._leases[f"{scma_id}:{venue}"] = lease
        return lease

class FleetDomainRouter:
    """CFTC Rule 150.4 Anti-Aggregation Engine ensuring zero cross-market overlap."""
    ASSIGNMENTS: Dict[str, Dict[str, str]] = {
        "SCMA-FOUNDER": {"domain": "Macro (Interest)", "venue": "Kalshi", "household": "Household 1"},
        "SCMA-MEM-0001": {"domain": "Weather (NOAA)", "venue": "Kalshi", "household": "Household 1"},
        "SCMA-MEM-0002": {"domain": "Macro (BLS CPI)", "venue": "Kalshi", "household": "Household 2"},
        "SCMA-MEM-0003": {"domain": "Crypto (Derivatives)", "venue": "Polymarket", "household": "Household 3"},
        "SCMA-MEM-0004": {"domain": "Treasury Yield Curves", "venue": "Kalshi", "household": "Household 3"},
    }

    @classmethod
    def validate_order(cls, scma_id: str, domain: str, venue: str) -> bool:
        policy = cls.ASSIGNMENTS.get(scma_id)
        if not policy:
            raise DomainCollusionError(f"Account {scma_id} has no registered market domain.")
        if policy["domain"] != domain or policy["venue"] != venue:
            raise DomainCollusionError(
                f"DOMAIN_COLLUSION_PROHIBITED: {scma_id} is locked to {policy['domain']} on {policy['venue']}. "
                f"Attempted {domain} on {venue}."
            )
        return True

class VirtualLineageVault:
    """Distributes 10% CFCP splits equally across registered virtual minor sub-shares."""
    @staticmethod
    def credit_cfcp_split(cursor, cfcp_net_cents: int, timestamp_iso: str):
        cursor.execute("SELECT scma_id, cash_cents FROM accounts WHERE is_custodial = 1 AND status = 'VIRTUAL_LINEAGE';")
        minors = cursor.fetchall()
        if not minors or cfcp_net_cents <= 0:
            return
        split_per_minor = cfcp_net_cents // len(minors)
        remainder = cfcp_net_cents % len(minors)
        for idx, (m_id, m_cash) in enumerate(minors):
            credit = split_per_minor + (1 if idx < remainder else 0)
            cursor.execute(
                "UPDATE accounts SET cash_cents = cash_cents + ?, lifetime_profit_cents = lifetime_profit_cents + ?, updated_at = ? WHERE scma_id = ?;",
                (credit, credit, timestamp_iso, m_id)
            )
