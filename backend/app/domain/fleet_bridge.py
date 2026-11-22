"""Backend bridge wiring root fleet_engine.py (12-category registry & CFTC 150.4 mutex) into scan_worker."""
from __future__ import annotations
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, Optional

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from fleet_engine import (  # noqa: E402
    ContractCollisionError,
    ContractMutexRegistry,
    FleetCategoryRegistry,
    HouseholdAffinityCollisionError,
)

CATEGORY_ALIAS_TO_ID: Dict[str, int] = {
    "WEATHER": 1, "WEATHER_TEMPERATURE": 1, "WEATHER_PRECIPITATION": 1,
    "MACRO_FED_RATES": 2, "FED_RATES": 2,
    "MACRO": 3, "MACRO_INFLATION_CPI": 3, "INFLATION": 3,
    "MACRO_EMPLOYMENT": 4, "EMPLOYMENT": 4,
    "ENERGY": 5, "ENERGY_EIA_INVENTORIES": 5,
    "TREASURY": 6, "TREASURY_AUCTIONS": 6,
    "EQUITY": 7, "EQUITY_INDEX_BRACKETS": 7,
    "TRANSPORTATION": 8, "TRANSPORTATION_TSA_FAA": 8,
    "FX": 9, "FX_DAILY_FIXINGS": 9,
    "CRYPTO": 10, "CRYPTO_VOLATILITY_BRACKETS": 10,
    "SPORTS": 11, "SPORTS_DISCRETE_MARGINS": 11,
    "PERPETUAL_FUNDING": 12,
}


class FleetMutexCoordinator:
    """Thread-safe SQLite coordinator for FleetCategoryRegistry (12 categories) & ContractMutexRegistry."""

    def __init__(self, db_path: str = ":memory:") -> None:
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self._init_schema()

    def _init_schema(self) -> None:
        cur = self.conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS contract_mutex_locks (
                contract_id TEXT PRIMARY KEY,
                venue TEXT NOT NULL,
                locked_by_account TEXT NOT NULL,
                category TEXT NOT NULL,
                series_ticker TEXT,
                acquired_at TEXT NOT NULL,
                expires_at REAL NOT NULL
            );
            """
        )
        self.conn.commit()

    @staticmethod
    def list_categories() -> Dict[int, Dict[str, str]]:
        return dict(FleetCategoryRegistry.CATEGORIES)

    @staticmethod
    def resolve_category(category: Any) -> Dict[str, Any]:
        if isinstance(category, int) and category in FleetCategoryRegistry.CATEGORIES:
            return {"category_id": category, **FleetCategoryRegistry.CATEGORIES[category]}
        key = str(category or "").strip().upper()
        cat_id = CATEGORY_ALIAS_TO_ID.get(key)
        if cat_id is None:
            for cid, meta in FleetCategoryRegistry.CATEGORIES.items():
                if meta["name"].upper() == key:
                    cat_id = cid
                    break
        if cat_id is None:
            raise ValueError(f"Unknown fleet category: {category}")
        return {"category_id": cat_id, **FleetCategoryRegistry.CATEGORIES[cat_id]}

    def reap_expired(self) -> int:
        cur = self.conn.cursor()
        reaped = ContractMutexRegistry.reap_expired_locks(cur)
        self.conn.commit()
        return reaped

    def acquire_contract_lock(
        self,
        contract_id: str,
        venue: str,
        scma_id: str,
        category: Any,
        series_ticker: Optional[str] = None,
        ttl_seconds: int = 300,
    ) -> Dict[str, Any]:
        meta = self.resolve_category(category)
        cur = self.conn.cursor()
        ContractMutexRegistry.acquire_lock(
            cur,
            contract_id=contract_id,
            venue=venue,
            scma_id=scma_id,
            category=meta["name"],
            series_ticker=series_ticker,
            ttl_seconds=ttl_seconds,
        )
        self.conn.commit()
        return meta

    def release_contract_lock(self, contract_id: str, scma_id: str) -> bool:
        cur = self.conn.cursor()
        released = ContractMutexRegistry.release_lock(cur, contract_id=contract_id, scma_id=scma_id)
        self.conn.commit()
        return released

    def active_lock_count(self) -> int:
        self.reap_expired()
        cur = self.conn.cursor()
        cur.execute("SELECT COUNT(*) FROM contract_mutex_locks;")
        return int(cur.fetchone()[0])


__all__ = [
    "ContractCollisionError",
    "FleetCategoryRegistry",
    "FleetMutexCoordinator",
    "HouseholdAffinityCollisionError",
]
