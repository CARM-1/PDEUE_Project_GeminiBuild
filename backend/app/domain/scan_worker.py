"""Deterministic, offline autonomous market-scanning worker.

The worker exercises the same normalized venue contracts used by production code,
but it only consumes local fixture payloads.  It never performs venue retrieval or
order placement during R&D/MVP qualification.
"""
from datetime import datetime, timezone
from typing import Any, Dict

from app.adapters.venue_connectors import KalshiMarketDataClient, PolymarketMarketDataClient
from app.domain.domain_registry import DomainRegistry
from app.domain.priority_eviction import PriorityEvictionManager
from app.domain.venue_scanner import VenueOpportunityScanner


class AutonomousScanWorker:
    """Run category-neutral scans while retaining 12-House routing metadata."""

    OFFLINE_CONTRACTS = (
        {"ticker": "KX-MIA-FRZ-32", "category": "WEATHER", "venue": "KALSHI",
         "house_id": 1, "spec": {"strike_temp_c": 30.0,
                                     "ensemble_members": [31.0, 31.5, 32.0], "station_id": "KMIA"}},
        {"ticker": "POLY-239496", "category": "CRYPTO", "venue": "POLYMARKET",
         "house_id": 2, "spec": {"spot_price": 120.0, "strike_price": 100.0,
                                     "annualized_vol": 0.60, "days_to_expiry": 7.0}},
        {"ticker": "KX-CPI-3.0", "category": "MACRO", "venue": "KALSHI",
         "house_id": 3, "spec": {"threshold": 3.0, "evidence": [
             {"source": "OFFLINE_CONSENSUS", "value": 3.5,
              "available_at": "2026-09-01T12:00:00Z"}]}},
        {"ticker": "KX-NFL-DEMO", "category": "SPORTS", "venue": "KALSHI",
         "house_id": 4, "spec": {"projected_margin": 14.0, "target_spread": 3.0,
                                     "sigma": 13.5}},
    )

    def __init__(self, *args, **kwargs):
        self.circuit_breaker = kwargs.get("circuit_breaker")
        self.interval_seconds = kwargs.get("interval_seconds", 5.0)
        self.poll_interval_seconds = self.interval_seconds
        self.ledger = kwargs.get("ledger")
        self.dispatcher = kwargs.get("dispatcher")
        self.eviction_manager = kwargs.get("eviction_manager") or PriorityEvictionManager()
        self.kalshi_client = kwargs.get("kalshi_client") or KalshiMarketDataClient()
        self.poly_client = kwargs.get("poly_client") or PolymarketMarketDataClient()
        self.scanner = kwargs.get("scanner") or VenueOpportunityScanner()
        self.domain_registry = kwargs.get("domain_registry") or DomainRegistry()
        self.is_running = False
        self.status = "IDLE"
        self.cycle_count = 0
        self.latest_opportunities = []
        self.stats = {
            "cycles_completed": 0,
            "total_contracts_scanned": 0,
            "total_evictions_executed": 0,
            "last_cycle_status": "NOT_STARTED",
        }

    def start(self):
        self.is_running = True
        self.status = "RUNNING"
        return {"status": "STARTED"}

    def stop(self):
        self.is_running = False
        self.status = "STOPPED"
        return {"status": "STOPPED"}

    def run_single_cycle(self) -> Dict[str, Any]:
        self.cycle_count += 1
        if self.circuit_breaker and not self.circuit_breaker.validate_execution_allowed():
            self.stats["last_cycle_status"] = "HALTED_CIRCUIT_BREAKER"
            return {
                "cycle_number": self.cycle_count,
                "cycle": self.cycle_count,
                "status": "HALTED",
                "reason": "CIRCUIT_BREAKER_TRIPPED",
                "contracts_scanned": 0,
                "opportunities": [],
            }

        now_iso = datetime.now(timezone.utc).isoformat()
        opportunities = []
        for contract in self.OFFLINE_CONTRACTS:
            ticker = contract["ticker"]
            venue = contract["venue"]
            if venue == "POLYMARKET":
                book = self.poly_client.fetch_orderbook(ticker, {
                    "bids": [{"price": "0.02", "size": "7500"}],
                    "asks": [{"price": "0.04", "size": "15000"}],
                })
            else:
                book = self.kalshi_client.fetch_orderbook(ticker, {
                    "bids": [[1, 5000]], "asks": [[3, 10000]],
                })
            opportunity = self.scanner.evaluate_domain_opportunity(
                orderbook=book,
                category=contract["category"],
                underwriting_spec=contract["spec"],
                target_house_id=contract["house_id"],
                registry=self.domain_registry,
            )
            opportunities.append(opportunity)

        self.latest_opportunities = opportunities
        scanned = len(opportunities)
        self.stats["cycles_completed"] += 1
        self.stats["total_contracts_scanned"] += scanned
        self.stats["last_cycle_status"] = "COMPLETED"
        return {
            "cycle_number": self.cycle_count,
            "cycle": self.cycle_count,
            "status": "COMPLETED",
            "timestamp": now_iso,
            "contracts_scanned": scanned,
            "scanned_venues": sorted({c["venue"] for c in self.OFFLINE_CONTRACTS}),
            "qualified_count": sum(o["status"] == "QUALIFIED" for o in opportunities),
            "opportunities": opportunities,
        }

    def get_telemetry(self) -> Dict[str, Any]:
        if not self.latest_opportunities:
            self.run_single_cycle()
        return {
            "cycle_number": self.cycle_count,
            "worker": "AutonomousScanWorker",
            "status": self.status if self.status != "IDLE" else "NOMINAL",
            "is_running": self.is_running,
            "cycle": self.cycle_count,
            "latest_opportunities": self.latest_opportunities,
            "stats": dict(self.stats),
        }

    def evaluate_candidate_preemption(self, candidate, total_equity_cents, currently_committed_cents):
        return self.eviction_manager.evaluate_preemption(
            candidate, total_equity_cents, currently_committed_cents
        )

    def execute_eviction(self, order_id: str) -> dict:
        result = self.eviction_manager.execute_eviction(order_id)
        self.stats["total_evictions_executed"] += 1
        return result
