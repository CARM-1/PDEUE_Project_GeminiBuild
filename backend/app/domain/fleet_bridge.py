"""Hardened backend bridge for root fleet_engine.py (12-category registry & CFTC 150.4 mutex)."""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import threading
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Set, Tuple

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from fleet_engine import (  # noqa: E402
    ContractCollisionError,
    DomainCollusionError,
    FleetCategoryRegistry,
    FleetDomainRouter,
    HouseholdAffinityCollisionError,
)

APPROVED_PROVENANCE = frozenset({"OBSERVED_L2", "VERIFIED_L2"})
SERIES_REQUIRED_CATEGORIES = frozenset({1, 2, 3, 4, 5, 6})

CATEGORY_ALIAS_TO_ID: Dict[str, int] = {
    "WEATHER": 1, "WEATHER_TEMPERATURE": 1, "WEATHER_PRECIPITATION": 1, "NOAA": 1,
    "FED_RATES": 2, "FED_RATE": 2, "INTEREST_RATES": 2, "MACRO_FED_RATES": 2,
    "MACRO": 3, "MACRO_INFLATION_CPI": 3, "INFLATION": 3, "CPI": 3,
    "MACRO_EMPLOYMENT": 4, "EMPLOYMENT": 4, "NFP": 4,
    "ENERGY": 5, "ENERGY_EIA_INVENTORIES": 5, "OIL": 5,
    "TREASURY": 6, "TREASURY_AUCTIONS": 6,
    "EQUITY": 7, "EQUITY_INDEX_BRACKETS": 7,
    "TRANSPORTATION": 8, "TRANSPORTATION_TSA_FAA": 8,
    "FX": 9, "FX_DAILY_FIXINGS": 9,
    "CRYPTO": 10, "CRYPTO_VOLATILITY_BRACKETS": 10,
    "SPORTS": 11, "SPORTS_DISCRETE_MARGINS": 11,
    "PERPETUAL_FUNDING": 12, "FUNDING": 12,
}

CATEGORY_ID_TO_DOMAIN: Dict[int, str] = {
    1: "Weather (NOAA)",
    2: "Macro (Interest)",
    3: "Macro (BLS CPI)",
    6: "Treasury Yield Curves",
    10: "Crypto (Derivatives)",
}

_SHARED_LOCK = threading.Lock()
_SHARED_COORDINATOR: Optional["FleetMutexCoordinator"] = None


def normalize_provenance(raw: Any) -> str:
    if raw is None:
        return ""
    return str(raw).strip().upper().replace("-", "_").replace(" ", "_")


def is_approved_provenance(raw: Any) -> bool:
    return normalize_provenance(raw) in APPROVED_PROVENANCE


def _norm_account(scma_id: Any) -> str:
    val = str(scma_id or "").strip().upper()
    if not val:
        raise ValueError("MISSING_SCMA_ID: scma_id is required and cannot default implicitly")
    return val


def _norm_venue(venue: Any) -> str:
    val = str(venue or "").strip().upper()
    if not val:
        raise ValueError("MISSING_VENUE: venue is required")
    return val


def _norm_contract(contract_id: Any) -> str:
    val = str(contract_id or "").strip().upper()
    if not val:
        raise ValueError("MISSING_CONTRACT_ID: contract_id is required")
    return val


def _norm_series(series_ticker: Any) -> Optional[str]:
    if series_ticker is None:
        return None
    val = str(series_ticker).strip().upper()
    return val or None


def _account_household(scma_id: str) -> Optional[str]:
    policy = FleetDomainRouter.ASSIGNMENTS.get(scma_id)
    return policy["household"] if policy else None


class FleetMutexCoordinator:
    """Thread-safe, WAL-backed SQLite coordinator for FleetCategoryRegistry & CFTC 150.4 mutex."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path = db_path or ":memory:"
        self._lock = threading.Lock()
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False, isolation_level=None)
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            cur = self.conn.cursor()
            if self.db_path != ":memory:":
                cur.execute("PRAGMA journal_mode=WAL;")
            cur.execute("PRAGMA busy_timeout=5000;")
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS contract_mutex_locks (
                    venue TEXT NOT NULL,
                    contract_id TEXT NOT NULL,
                    locked_by_account TEXT NOT NULL,
                    category TEXT NOT NULL,
                    series_ticker TEXT,
                    order_id TEXT,
                    acquired_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    PRIMARY KEY (venue, contract_id)
                );
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS household_series_locks (
                    household TEXT NOT NULL,
                    series_ticker TEXT NOT NULL,
                    locked_by_account TEXT NOT NULL,
                    venue TEXT NOT NULL,
                    contract_id TEXT NOT NULL,
                    expires_at REAL NOT NULL,
                    PRIMARY KEY (household, series_ticker)
                );
                """
            )

    @staticmethod
    def list_categories() -> Dict[int, Dict[str, str]]:
        return dict(FleetCategoryRegistry.CATEGORIES)

    @staticmethod
    def resolve_category(category: Any, contract_id: Optional[str] = None) -> Dict[str, Any]:
        if isinstance(category, int) and category in FleetCategoryRegistry.CATEGORIES:
            return {"category_id": category, **FleetCategoryRegistry.CATEGORIES[category]}
        key = str(category or "").strip().upper().replace("-", "_").replace(" ", "_")
        if key == "MACRO" and contract_id and "FED" in str(contract_id).upper():
            return {"category_id": 2, **FleetCategoryRegistry.CATEGORIES[2]}
        cat_id = CATEGORY_ALIAS_TO_ID.get(key)
        if cat_id is None:
            for cid, meta in FleetCategoryRegistry.CATEGORIES.items():
                if meta["name"].upper() == key:
                    cat_id = cid
                    break
        if cat_id is None:
            raise ValueError(f"Unknown fleet category: {category}")
        return {"category_id": cat_id, **FleetCategoryRegistry.CATEGORIES[cat_id]}

    def _reap_in_tx(self, cur: sqlite3.Cursor) -> int:
        cur.execute("DELETE FROM contract_mutex_locks WHERE expires_at <= unixepoch('subsec');")
        n = cur.rowcount
        cur.execute("DELETE FROM household_series_locks WHERE expires_at <= unixepoch('subsec');")
        return n

    def reap_expired(self) -> int:
        with self._lock:
            cur = self.conn.cursor()
            cur.execute("BEGIN IMMEDIATE;")
            try:
                reaped = self._reap_in_tx(cur)
                cur.execute("COMMIT;")
                return reaped
            except Exception:
                cur.execute("ROLLBACK;")
                raise

    def acquire_contract_lock(
        self,
        contract_id: str,
        venue: str,
        scma_id: str,
        category: Any,
        series_ticker: Optional[str] = None,
        ttl_seconds: int = 300,
        order_id: Optional[str] = None,
        enforce_domain_router: bool = False,
        require_series_for_series_categories: bool = False,
        allow_same_account_renew: bool = False,
    ) -> Dict[str, Any]:
        norm_scma = _norm_account(scma_id)
        norm_venue = _norm_venue(venue)
        norm_contract = _norm_contract(contract_id)
        norm_series = _norm_series(series_ticker)
        meta = self.resolve_category(category, contract_id=norm_contract)

        if enforce_domain_router:
            domain = CATEGORY_ID_TO_DOMAIN.get(meta["category_id"], meta["name"])
            venue_title = "Kalshi" if norm_venue == "KALSHI" else ("Polymarket" if norm_venue == "POLYMARKET" else norm_venue)
            FleetDomainRouter.validate_order(norm_scma, domain, venue_title)

        if require_series_for_series_categories and meta["category_id"] in SERIES_REQUIRED_CATEGORIES and not norm_series:
            raise ValueError(f"MISSING_SERIES_TICKER: series_ticker required for category {meta['name']}")

        household = _account_household(norm_scma)
        with self._lock:
            cur = self.conn.cursor()
            cur.execute("BEGIN IMMEDIATE;")
            try:
                self._reap_in_tx(cur)
                cur.execute(
                    "SELECT locked_by_account FROM contract_mutex_locks WHERE venue = ? AND contract_id = ?;",
                    (norm_venue, norm_contract),
                )
                row = cur.fetchone()
                if row:
                    if row[0] != norm_scma:
                        raise ContractCollisionError(
                            f"CONTRACT_COLLISION: Contract {norm_contract} on {norm_venue} is already locked by {row[0]}."
                        )
                    if not allow_same_account_renew:
                        raise ContractCollisionError(
                            f"DUPLICATE_ACTIVE_LOCK: {norm_scma} already holds an active lock on {norm_venue}:{norm_contract}."
                        )
                    cur.execute(
                        "UPDATE contract_mutex_locks SET expires_at = unixepoch('subsec') + ?, order_id = COALESCE(?, order_id) "
                        "WHERE venue = ? AND contract_id = ?;",
                        (float(ttl_seconds), order_id, norm_venue, norm_contract),
                    )
                    if household and norm_series:
                        cur.execute(
                            "UPDATE household_series_locks SET expires_at = unixepoch('subsec') + ? "
                            "WHERE household = ? AND series_ticker = ? AND locked_by_account = ?;",
                            (float(ttl_seconds), household, norm_series, norm_scma),
                        )
                    cur.execute("COMMIT;")
                    return meta

                if household and norm_series:
                    cur.execute(
                        "SELECT locked_by_account, contract_id FROM household_series_locks "
                        "WHERE household = ? AND series_ticker = ?;",
                        (household, norm_series),
                    )
                    hh_row = cur.fetchone()
                    if hh_row and hh_row[0] != norm_scma:
                        raise HouseholdAffinityCollisionError(
                            f"HOUSEHOLD_AFFINITY_COLLISION: {norm_scma} ({household}) cannot trade series "
                            f"{norm_series}. Co-habitant {hh_row[0]} holds active lock on {hh_row[1]}."
                        )
                    if not hh_row:
                        try:
                            cur.execute(
                                "INSERT INTO household_series_locks "
                                "(household, series_ticker, locked_by_account, venue, contract_id, expires_at) "
                                "VALUES (?, ?, ?, ?, ?, unixepoch('subsec') + ?);",
                                (household, norm_series, norm_scma, norm_venue, norm_contract, float(ttl_seconds)),
                            )
                        except sqlite3.IntegrityError as exc:
                            raise HouseholdAffinityCollisionError(
                                f"HOUSEHOLD_AFFINITY_COLLISION: DB unique constraint blocked {norm_scma} on {household}:{norm_series}."
                            ) from exc

                cur.execute(
                    "INSERT INTO contract_mutex_locks "
                    "(venue, contract_id, locked_by_account, category, series_ticker, order_id, acquired_at, expires_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, unixepoch('subsec'), unixepoch('subsec') + ?);",
                    (norm_venue, norm_contract, norm_scma, meta["name"], norm_series, order_id, float(ttl_seconds)),
                )
                cur.execute("COMMIT;")
                return meta
            except Exception:
                cur.execute("ROLLBACK;")
                raise

    def release_contract_lock(self, contract_id: str, scma_id: str, venue: Optional[str] = None) -> bool:
        norm_contract = _norm_contract(contract_id)
        norm_scma = _norm_account(scma_id)
        norm_venue = _norm_venue(venue) if venue else None
        with self._lock:
            cur = self.conn.cursor()
            cur.execute("BEGIN IMMEDIATE;")
            try:
                if norm_venue:
                    cur.execute(
                        "DELETE FROM contract_mutex_locks WHERE venue = ? AND contract_id = ? AND locked_by_account = ?;",
                        (norm_venue, norm_contract, norm_scma),
                    )
                    released = cur.rowcount > 0
                    cur.execute(
                        "DELETE FROM household_series_locks WHERE venue = ? AND contract_id = ? AND locked_by_account = ?;",
                        (norm_venue, norm_contract, norm_scma),
                    )
                else:
                    cur.execute(
                        "DELETE FROM contract_mutex_locks WHERE contract_id = ? AND locked_by_account = ?;",
                        (norm_contract, norm_scma),
                    )
                    released = cur.rowcount > 0
                    cur.execute(
                        "DELETE FROM household_series_locks WHERE contract_id = ? AND locked_by_account = ?;",
                        (norm_contract, norm_scma),
                    )
                cur.execute("COMMIT;")
                return released
            except Exception:
                cur.execute("ROLLBACK;")
                raise

    def reconcile_live_orders(self, live_keys: Iterable[Tuple[str, str]]) -> int:
        """Delete any locks not backed by a live resting/pending order."""
        keep: Set[Tuple[str, str]] = {(_norm_venue(v), _norm_contract(c)) for v, c in live_keys}
        with self._lock:
            cur = self.conn.cursor()
            cur.execute("BEGIN IMMEDIATE;")
            try:
                cur.execute("SELECT venue, contract_id FROM contract_mutex_locks;")
                removed = 0
                for v, c in cur.fetchall():
                    if (v, c) not in keep:
                        cur.execute("DELETE FROM contract_mutex_locks WHERE venue = ? AND contract_id = ?;", (v, c))
                        cur.execute("DELETE FROM household_series_locks WHERE venue = ? AND contract_id = ?;", (v, c))
                        removed += 1
                cur.execute("COMMIT;")
                return removed
            except Exception:
                cur.execute("ROLLBACK;")
                raise

    def active_lock_count(self) -> int:
        """Pure read-only count; never mutates or commits database state."""
        with self._lock:
            cur = self.conn.cursor()
            cur.execute("SELECT COUNT(*) FROM contract_mutex_locks WHERE expires_at > unixepoch('subsec');")
            return int(cur.fetchone()[0])


def get_shared_fleet_coordinator(db_path: Optional[str] = None) -> FleetMutexCoordinator:
    """Return the process-wide shared WAL-backed FleetMutexCoordinator."""
    global _SHARED_COORDINATOR
    with _SHARED_LOCK:
        if _SHARED_COORDINATOR is None or (db_path and _SHARED_COORDINATOR.db_path != db_path):
            resolved = db_path or os.getenv(
                "PDEUE_MUTEX_DB_PATH",
                str(Path(tempfile.gettempdir()) / "pdeue_shared_fleet_mutex.sqlite3"),
            )
            _SHARED_COORDINATOR = FleetMutexCoordinator(db_path=resolved)
        return _SHARED_COORDINATOR


__all__ = [
    "APPROVED_PROVENANCE",
    "ContractCollisionError",
    "DomainCollusionError",
    "FleetCategoryRegistry",
    "FleetDomainRouter",
    "FleetMutexCoordinator",
    "HouseholdAffinityCollisionError",
    "get_shared_fleet_coordinator",
    "is_approved_provenance",
    "normalize_provenance",
]
