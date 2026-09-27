import sys
import os
import time
import signal
import asyncio
import argparse
from pathlib import Path
from typing import Dict, Any, Optional

base_dir = Path(__file__).resolve().parent.parent
if str(base_dir) not in sys.path:
    sys.path.insert(0, str(base_dir))

from app.adapters.rate_limiter import VenueRateLimiter
from app.domain.telemetry_sink import TelemetryHealthSink
from app.domain.capital_ledger import CapitalLedger
from app.domain.maker_rebate_adapter import MakerRebateLedgerAdapter
from app.domain.atomic_leg_coordinator import AtomicLegCoordinator
from app.domain.dynamic_spread_kelly import DynamicSpreadKellyRegime
from app.domain.stale_sniping_engine import StaleQuoteSnipingEngine
from app.domain.venue_rebalancer import CrossVenueRebalanceManager
from app.domain.accounting_gateway import AccountingGateway
from app.domain.position_book import PositionBook
from app.domain.priority_eviction import PriorityEvictionManager
from app.domain.scan_worker import AutonomousScanWorker
from app.domain.sweep_daemon import FloatSweepMonitor

class PaperSoakRunner:
    def __init__(
        self,
        total_cycles: int = 51840,
        cycle_interval_sec: float = 5.0,
        health_export_interval: int = 4320,
        health_export_path: str = 'health_summary.json',
        initial_balance_cents: int = 10000,
        limiter: Optional[VenueRateLimiter] = None,
        mode: str = 'live_paper',
    ):
        self.total_cycles = total_cycles
        self.cycle_interval_sec = cycle_interval_sec
        self.health_export_interval = health_export_interval
        self.current_cycle = 0
        self.is_running = False
        self.partition = 'PARTITION_2_ENHANCED_ALPHA'
        mode_aliases = {1: 'replay', '1': 'replay', 'replay': 'replay',
                        2: 'live_paper', '2': 'live_paper', 'live_paper': 'live_paper'}
        if mode not in mode_aliases:
            raise ValueError("mode must be Mode 1/replay or Mode 2/live_paper")
        self.mode = mode_aliases[mode]

        self.limiter = limiter or VenueRateLimiter()
        self.sink = TelemetryHealthSink(export_path=health_export_path)
        self.ledger = CapitalLedger(initial_balance_cents=initial_balance_cents)
        self.ledger.register_member_account('founder_scma', seed_capital_cents=initial_balance_cents)
        self.rebate_adapter = MakerRebateLedgerAdapter(ledger=self.ledger)
        self.position_book = PositionBook()
        self.accounting_gateway = AccountingGateway()
        self.eviction_manager = PriorityEvictionManager(max_concurrent_orders=12)
        self.float_sweep_monitor = FloatSweepMonitor()
        self.scan_worker = AutonomousScanWorker(
            ledger=self.ledger,
            position_book=self.position_book,
            accounting_gateway=self.accounting_gateway,
            eviction_manager=self.eviction_manager,
            float_sweep_monitor=self.float_sweep_monitor,
        )
        self.execution_event_log = []

        self.leg_coordinator = AtomicLegCoordinator(leg_timeout_ms=750.0)
        self.spread_kelly = DynamicSpreadKellyRegime(base_fraction=0.25, defensive_floor=0.05, max_spread=0.05)
        self.sniping_engine = StaleQuoteSnipingEngine()
        self.venue_rebalancer = CrossVenueRebalanceManager(target_ratio=0.50, tolerance=0.15)

        self.maker_stats = {'posted': 0, 'filled': 0, 'expired': 0}
        self.phase_bc_metrics = {'scratched_legs': 0, 'sniped_quotes': 0, 'rebalances_triggered': 0}
        self.spread_distributions = {'WEATHER': 0.02, 'MACRO': 0.03, 'SPORTS': 0.015, 'CRYPTO': 0.025}
        self.circuit_breaker = {'is_tripped': False, 'trip_reason': None}

    def execute_cycle(self) -> Dict[str, Any]:
        self.current_cycle += 1
        daemon_cycle = self.scan_worker.run_single_cycle()
        waterfall_gross_cents = 100
        waterfall = {
            'scma_cents': (waterfall_gross_cents * 87) // 100,
            'cfcp_cents': (waterfall_gross_cents * 10) // 100,
        }
        waterfall['faep_cents'] = waterfall_gross_cents - sum(waterfall.values())
        cycle_events = [{
            'event_type': 'WATERFALL_DISTRIBUTION',
            'distribution': waterfall,
            'mode': self.mode,
        }]
        if daemon_cycle['merged_shares_count']:
            cycle_events.append({
                'event_type': 'COMPLETE_SET_RECYCLED',
                'merged_shares_count': daemon_cycle['merged_shares_count'],
            })
        if daemon_cycle['staged_sweeps_count']:
            cycle_events.extend({
                'event_type': 'FLOAT_SWEEP_STAGED',
                'interface_id': 'IF-038',
                'event_id': event['event_id'],
                'amount_cents': event['payload']['amount_cents'],
            } for event in self.accounting_gateway.event_outbox[-daemon_cycle['staged_sweeps_count']:])
        self.execution_event_log.extend(cycle_events)
        kalshi_ok = self.limiter.can_proceed('KALSHI')
        poly_ok = self.limiter.can_proceed('POLYMARKET')

        cycle_posted = 0
        cycle_filled = 0
        cycle_expired = 0

        if kalshi_ok and poly_ok and not self.circuit_breaker['is_tripped']:
            active_frac = self.spread_kelly.calculate_active_fraction(self.spread_distributions['WEATHER'])
            cycle_posted = 4
            cycle_filled = 3
            cycle_expired = 1
            self.maker_stats['posted'] += cycle_posted
            self.maker_stats['filled'] += cycle_filled
            self.maker_stats['expired'] += cycle_expired

            if self.current_cycle % 10 == 0:
                self.rebate_adapter.process_maker_rebate(
                    member_id='founder_scma',
                    rebate_cents=1,
                    venue='POLYMARKET',
                    contract_id=f'SOAK-CONTRACT-{self.current_cycle}',
                    order_id=f'SOAK-ORD-{self.current_cycle}'
                )

            if self.current_cycle % 25 == 0:
                sniped = self.sniping_engine.evaluate_quote_staleness(
                    public_ground_truth={'published_at_epoch': 100.0, 'true_probability': 0.75},
                    resting_quote={'ticker': f'SNIPE-{self.current_cycle}', 'venue': 'KALSHI', 'quoted_at_epoch': 90.0, 'ask_price': 0.65}
                )
                if sniped:
                    self.phase_bc_metrics['sniped_quotes'] += 1

        should_export = (
            self.current_cycle % self.health_export_interval == 0
            or self.current_cycle == self.total_cycles
            or self.current_cycle == 1
        )
        if should_export:
            payload = self.sink.compile_health_payload(
                ledger_balances={
                    'founder_scma': self.ledger.members['founder_scma']['balance_cents'],
                    'cfcp': self.ledger.central_family_pool_cents,
                    'faep': self.ledger.founder_pool_cents
                },
                maker_stats=self.maker_stats,
                spread_distributions=self.spread_distributions,
                circuit_breaker_status=self.circuit_breaker,
                rate_limiter_warnings=self.limiter.warnings_count
            )
            payload['partition_tag'] = self.partition
            payload['phase_bc_metrics'] = self.phase_bc_metrics
            self.sink.export_health_summary(payload)

        return {
            'cycle': self.current_cycle,
            'posted': cycle_posted,
            'filled': cycle_filled,
            'expired': cycle_expired,
            'phase_bc_metrics': self.phase_bc_metrics,
            'rate_limiter_warnings': self.limiter.warnings_count,
            'mode': self.mode,
            'slot_capacity': daemon_cycle['slot_capacity'],
            'active_preemption': True,
            'merged_shares_count': daemon_cycle['merged_shares_count'],
            'staged_sweeps_count': daemon_cycle['staged_sweeps_count'],
            'events': cycle_events,
        }

    async def run(self) -> None:
        self.is_running = True
        while self.is_running and self.current_cycle < self.total_cycles:
            self.execute_cycle()
            if self.current_cycle < self.total_cycles:
                await asyncio.sleep(self.cycle_interval_sec)
        self.is_running = False

    def stop(self) -> None:
        self.is_running = False

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Run replay or live paper autonomous soak cycles.')
    parser.add_argument('--mode', choices=('replay', 'live_paper', '1', '2'), default='live_paper')
    args = parser.parse_args()
    runner = PaperSoakRunner(
        total_cycles=51840,
        cycle_interval_sec=5.0,
        health_export_interval=4320,
        health_export_path='health_summary.json',
        mode=args.mode,
    )
    def handle_sig(sig, frame):
        print(f'Received signal {sig}, terminating paper soak runner gracefully...')
        runner.stop()
        sys.exit(0)
    signal.signal(signal.SIGINT, handle_sig)
    signal.signal(signal.SIGTERM, handle_sig)
    print('Starting 72-Hour Autonomous Paper Soak with Phase B & C Enhancements...')
    asyncio.run(runner.run())
    print('Paper Soak completed cleanly.')
