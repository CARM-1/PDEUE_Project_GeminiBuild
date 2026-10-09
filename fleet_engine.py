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


class ContractCollisionError(Exception):
    """Raised when an account attempts to acquire a lock already held by another account."""
    pass

class HouseholdAffinityCollisionError(Exception):
    """Raised when co-habitating nodes attempt to trade correlated contracts in the same event series."""
    pass

class ContractMutexRegistry:
    """
    Enforces contract-level mutual exclusion and household event affinity under CFTC Rule 150.4.
    Replaces static sector silos with a dynamic global mutex queue.
    """
    HOUSEHOLD_1_NODES = {"SCMA-FOUNDER", "SCMA-MEM-0001"}

    @classmethod
    def reap_expired_locks(cls, cursor) -> int:
        now = time.time()
        cursor.execute("DELETE FROM contract_mutex_locks WHERE expires_at <= ?;", (now,))
        return cursor.rowcount

    @classmethod
    def acquire_lock(cls, cursor, contract_id: str, venue: str, scma_id: str, 
                     category: str, series_ticker: str = None, ttl_seconds: int = 300) -> bool:
        cls.reap_expired_locks(cursor)
        now = time.time()
        expires_at = now + ttl_seconds

        # Invariant 1: Contract-Level Mutual Exclusion
        cursor.execute("SELECT locked_by_account FROM contract_mutex_locks WHERE contract_id = ?;", (contract_id,))
        row = cursor.fetchone()
        if row:
            if row[0] != scma_id:
                raise ContractCollisionError(
                    f"CONTRACT_COLLISION: Contract {contract_id} on {venue} is already locked by {row[0]}."
                )
            # Re-lock / refresh lease for the same owner
            cursor.execute(
                "UPDATE contract_mutex_locks SET expires_at = ? WHERE contract_id = ?;",
                (expires_at, contract_id)
            )
            return True

        # Invariant 2: Household 1 Event Sub-Series Affinity Filter (CFTC 150.4)
        if series_ticker and scma_id in cls.HOUSEHOLD_1_NODES:
            other_hh1 = "SCMA-MEM-0001" if scma_id == "SCMA-FOUNDER" else "SCMA-FOUNDER"
            cursor.execute(
                "SELECT contract_id FROM contract_mutex_locks WHERE locked_by_account = ? AND series_ticker = ?;",
                (other_hh1, series_ticker)
            )
            conflict = cursor.fetchone()
            if conflict:
                raise HouseholdAffinityCollisionError(
                    f"HOUSEHOLD_AFFINITY_COLLISION: {scma_id} cannot trade series {series_ticker}. "
                    f"Co-habitant {other_hh1} holds active lock on contract {conflict[0]}."
                )

        cursor.execute("""
            INSERT INTO contract_mutex_locks (contract_id, venue, locked_by_account, category, series_ticker, acquired_at, expires_at)
            VALUES (?, ?, ?, ?, ?, datetime('now'), ?);
        """, (contract_id, venue, scma_id, category, series_ticker, expires_at))
        return True

    @classmethod
    def release_lock(cls, cursor, contract_id: str, scma_id: str) -> bool:
        cursor.execute(
            "DELETE FROM contract_mutex_locks WHERE contract_id = ? AND locked_by_account = ?;",
            (contract_id, scma_id)
        )
        return cursor.rowcount > 0
