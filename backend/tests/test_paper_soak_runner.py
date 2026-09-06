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
        total_cycles=25,
        cycle_interval_sec=0.001,
        health_export_interval=5,
        health_export_path=export_file,
        initial_balance_cents=10000,
        limiter=test_limiter
    )
    asyncio.run(runner.run())
    assert runner.current_cycle == 25
    assert runner.maker_stats['posted'] == 100
    assert runner.maker_stats['filled'] == 75
    assert runner.maker_stats['expired'] == 25
    assert os.path.exists(export_file)
    with open(export_file, 'r', encoding='utf-8') as f:
        payload = json.load(f)
    assert payload['status'] == 'HEALTHY'
    assert payload['maker_execution_metrics']['bids_posted'] == 100
    assert payload['balances_cents']['founder_scma'] >= 10000

def test_paper_soak_runner_rate_limiting():
    throttled_limiter = VenueRateLimiter({
        'KALSHI': {'rate': 0.0, 'capacity': 0.0},
        'POLYMARKET': {'rate': 0.0, 'capacity': 0.0}
    })
    runner = PaperSoakRunner(
        total_cycles=5,
        cycle_interval_sec=0.001,
        limiter=throttled_limiter
    )
    res = runner.execute_cycle()
    assert res['posted'] == 0
    assert runner.maker_stats['posted'] == 0
    assert runner.limiter.warnings_count > 0

def test_paper_soak_runner_stop():
    runner = PaperSoakRunner(total_cycles=1000, cycle_interval_sec=0.5)
    res = runner.execute_cycle()
    assert res['cycle'] == 1
    runner.stop()
    assert runner.is_running is False
