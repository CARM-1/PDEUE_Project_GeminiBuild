import os
import json
import pytest
import asyncio
from app.adapters.rate_limiter import VenueRateLimiter
from scripts.paper_soak_runner import PaperSoakRunner

def test_paper_soak_runner_lifecycle(tmp_path):
    export_file = str(tmp_path / 'test_soak_health.json')
    test_limiter = VenueRateLimiter({
        'KALSHI': {'rate': 10000.0, 'capacity': 1000.0},
        'POLYMARKET': {'rate': 10000.0, 'capacity': 1000.0}
    })
    runner = PaperSoakRunner(
        total_cycles=30,
        cycle_interval_sec=0.001,
        health_export_interval=5,
        health_export_path=export_file,
        initial_balance_cents=10000,
        limiter=test_limiter
    )
    asyncio.run(runner.run())
    assert runner.current_cycle == 30
    assert runner.maker_stats['posted'] == 30
    assert runner.maker_stats['filled'] == 30
    assert runner.phase_bc_metrics['sniped_quotes'] >= 1
    assert os.path.exists(export_file)
    with open(export_file, 'r', encoding='utf-8') as f:
        payload = json.load(f)
    assert payload['partition_tag'] == 'PARTITION_2_ENHANCED_ALPHA'
    assert payload['status'] == 'HEALTHY'


def test_runner_sizes_resting_orders_and_preempts_only_for_ten_percent_edge(tmp_path):
    runner = PaperSoakRunner(
        health_export_path=str(tmp_path / "health.json"),
        max_concurrent_orders=1,
        dry_powder_floor=0.40,
    )
    first = runner.execute_cycle({
        "domain": "WEATHER", "observed_at": 1, "available_at": 1,
        "contract_id": "low", "order_cents": 500, "spread": 0.02,
        "net_edge": 0.04, "execution_status": "RESTING",
    })
    rejected = runner.execute_cycle({
        "domain": "MACRO", "observed_at": 2, "available_at": 2,
        "contract_id": "small-uplift", "order_cents": 500, "spread": 0.03,
        "net_edge": 0.13, "execution_status": "RESTING",
    })
    preempted = runner.execute_cycle({
        "domain": "SPORTS", "observed_at": 3, "available_at": 3,
        "contract_id": "high", "order_cents": 500, "spread": 0.01,
        "net_edge": 0.14, "execution_status": "RESTING",
    })

    assert first["admitted"] is True
    assert first["allocation_cents"] == 400
    assert first["resting_bids"] == first["slot_occupancy"] == 1
    assert rejected["admitted"] is False
    assert preempted["admitted"] is True
    assert preempted["evictions"] == preempted["total_evictions"] == 1
    assert set(runner.eviction_manager.resting_orders) == {"high"}


def test_runner_enforces_configured_dry_powder_floor(tmp_path):
    runner = PaperSoakRunner(
        health_export_path=str(tmp_path / "health.json"), dry_powder_floor=0.90
    )
    result = runner.execute_cycle({
        "domain": "CRYPTO", "observed_at": 1, "available_at": 1,
        "contract_id": "too-large", "order_cents": 2_000,
        "net_edge": 0.20, "execution_status": "RESTING",
    })
    assert result["admitted"] is False
    assert result["slot_occupancy"] == 0
