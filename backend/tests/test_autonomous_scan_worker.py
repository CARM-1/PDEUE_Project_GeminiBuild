from app.domain.scan_worker import AutonomousScanWorker
from app.domain.circuit_breaker import CircuitBreakerEngine
from fastapi.testclient import TestClient
from app.main import app

def test_scan_worker_single_cycle_dispatches():
    worker = AutonomousScanWorker()
    res = worker.run_single_cycle()
    assert res['cycle_number'] == 1
    assert res['contracts_scanned'] >= 4
    assert worker.stats['cycles_completed'] == 1
    assert worker.stats['total_contracts_scanned'] >= 4

def test_scan_worker_fails_closed_when_circuit_breaker_tripped():
    cb = CircuitBreakerEngine()
    cb.trip(reason='Manual Trip', actor_id='TEST_ADMIN')
    worker = AutonomousScanWorker(circuit_breaker=cb)
    res = worker.run_single_cycle()
    assert res['status'] == 'HALTED'
    assert res['reason'] == 'CIRCUIT_BREAKER_TRIPPED'
    assert worker.stats['last_cycle_status'] == 'HALTED_CIRCUIT_BREAKER'

def test_scan_worker_start_stop_lifecycle():
    worker = AutonomousScanWorker(interval_seconds=0.1)
    assert worker.is_running is False
    worker.start()
    assert worker.is_running is True
    worker.stop()
    assert worker.is_running is False

def test_scan_worker_api_endpoints():
    client = TestClient(app)
    stat_res = client.get('/api/v1/operator/daemon/status')
    assert stat_res.status_code == 200
    assert 'is_running' in stat_res.json()

    cycle_res = client.post('/api/v1/operator/daemon/cycle')
    assert cycle_res.status_code == 200
    assert 'cycle_number' in cycle_res.json()

    start_res = client.post('/api/v1/operator/daemon/start')
    assert start_res.status_code == 200
    assert start_res.json()['status'] == 'STARTED'

    stop_res = client.post('/api/v1/operator/daemon/stop')
    assert stop_res.status_code == 200
    assert stop_res.json()['status'] == 'STOPPED'
