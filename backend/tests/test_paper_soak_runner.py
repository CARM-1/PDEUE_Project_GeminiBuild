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
    assert runner.maker_stats['posted'] == 120
    assert runner.maker_stats['filled'] == 90
    assert runner.phase_bc_metrics['sniped_quotes'] >= 1
    assert os.path.exists(export_file)
    with open(export_file, 'r', encoding='utf-8') as f:
        payload = json.load(f)
    assert payload['partition_tag'] == 'PARTITION_2_ENHANCED_ALPHA'
    assert payload['status'] == 'HEALTHY'
