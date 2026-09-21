import asyncio
import json
import signal
from pathlib import Path

import pytest

from app.domain.telemetry_sink import INT64_MAX, TelemetryHealthSink, require_cents
from scripts.paper_soak_runner import PaperSoakRunner


def snapshots():
    return [
        {"contract_id": "b", "domain": "MACRO", "observed_at": 10, "available_at": 12, "order_cents": 100},
        {"contract_id": "a", "domain": "WEATHER", "observed_at": 8, "available_at": 10, "order_cents": 100},
        {"contract_id": "c", "domain": "SPORTS", "observed_at": 11, "available_at": 13, "order_cents": 100},
    ]


def runner(tmp_path, **kwargs):
    return PaperSoakRunner(health_export_path=str(tmp_path / "health.json"), **kwargs)


def test_accelerated_replay_is_deterministic(tmp_path):
    one = runner(tmp_path / "one", mode=PaperSoakRunner.ACCELERATED_PIT).replay(snapshots())
    two = runner(tmp_path / "two", mode=PaperSoakRunner.ACCELERATED_PIT).replay(reversed(snapshots()))
    assert one == two


def test_replay_is_availability_ordered(tmp_path):
    result = runner(tmp_path, mode=PaperSoakRunner.ACCELERATED_PIT).replay(snapshots())
    assert [row["domain"] for row in result] == ["WEATHER", "MACRO", "SPORTS"]


def test_replay_rejects_snapshot_available_before_observation(tmp_path):
    bad = [{"domain": "CRYPTO", "observed_at": 5, "available_at": 4}]
    with pytest.raises(ValueError, match="lookahead"):
        runner(tmp_path, mode=PaperSoakRunner.ACCELERATED_PIT).replay(bad)


def test_replay_rejects_unknown_domain(tmp_path):
    bad = [{"domain": "EQUITY", "observed_at": 1, "available_at": 1}]
    with pytest.raises(ValueError, match="domain"):
        runner(tmp_path, mode=PaperSoakRunner.ACCELERATED_PIT).replay(bad)


def test_continuous_cycle_loop_and_final_flush(tmp_path):
    subject = runner(tmp_path, total_cycles=3, cycle_interval_sec=0)
    asyncio.run(subject.run())
    report = json.loads((tmp_path / "health.json").read_text())
    assert subject.current_cycle == report["checkpoint_cycle"] == 3
    assert report["qualification_metrics"]["order_volume"] == 3


def test_sigterm_handler_requests_stop_and_flushes(tmp_path, monkeypatch):
    installed = {}
    monkeypatch.setattr(signal, "signal", lambda sig, callback: installed.setdefault(sig, callback))
    subject = runner(tmp_path, total_cycles=100, cycle_interval_sec=.001)
    subject.install_signal_handlers()

    async def interrupt_running_soak():
        task = asyncio.create_task(subject.run())
        await asyncio.sleep(.003)
        installed[signal.SIGTERM](signal.SIGTERM, None)
        await task

    asyncio.run(interrupt_running_soak())
    assert subject.current_cycle < subject.total_cycles
    assert (tmp_path / "health.json").exists()


def test_atomic_serialization_leaves_no_temporary_file(tmp_path):
    subject = runner(tmp_path, total_cycles=1, cycle_interval_sec=0)
    asyncio.run(subject.run())
    assert json.loads((tmp_path / "health.json").read_text())["schema_version"] == "rc-c.v1"
    assert list(tmp_path.glob("*.tmp")) == []


def test_atomic_serialization_replaces_existing_document(tmp_path):
    target = tmp_path / "health.json"
    target.write_text("old")
    sink = TelemetryHealthSink(target)
    sink.export_health_summary({"complete": True})
    assert json.loads(target.read_text()) == {"complete": True}


@pytest.mark.parametrize("value", [1.5, "100", True, None])
def test_monetary_fields_reject_non_integer_cents(value):
    with pytest.raises(TypeError):
        require_cents(value, "cash")


def test_monetary_fields_reject_int64_overflow():
    with pytest.raises(OverflowError):
        require_cents(INT64_MAX + 1, "cash")


def test_dry_powder_floor_allows_exactly_forty_percent(tmp_path):
    subject = runner(tmp_path)
    subject._assert_dry_powder(6_000)
    assert subject.circuit_breaker["is_tripped"] is False


def test_dry_powder_floor_fail_closed(tmp_path):
    subject = runner(tmp_path)
    with pytest.raises(ValueError, match="40%"):
        subject._assert_dry_powder(6_001)
    assert subject.circuit_breaker["trip_reason"] == "DRY_POWDER_FLOOR_BREACH"


def test_memory_state_is_bounded_across_full_soak(tmp_path):
    subject = runner(tmp_path, total_cycles=51_840)
    for _ in range(14):
        subject.equity_trajectory_cents.append(subject.equity_cents)
    assert subject.equity_trajectory_cents.maxlen == len(subject.equity_trajectory_cents) == 13


def test_checkpoint_contains_all_qualification_metrics(tmp_path):
    subject = runner(tmp_path, total_cycles=1, cycle_interval_sec=0)
    asyncio.run(subject.run())
    metrics = json.loads((tmp_path / "health.json").read_text())["qualification_metrics"]
    assert set(metrics) == {"equity_trajectory_cents", "order_volume", "empirical_fill_ratio",
                            "fifo_fill_ratio_expectation", "latency_sniping_events",
                            "legging_scratches", "collateral_drift_cents"}
    assert metrics["empirical_fill_ratio"] == 1.0
    assert metrics["fifo_fill_ratio_expectation"] == .75


def test_manifest_declares_network_isolation():
    manifest = json.loads((Path(__file__).parents[2] / "docs/acceptance/rc-c-manifest.json").read_text())
    assert manifest["invariants"]["live_network_actions"] == 0
    assert all(not mode["external_trading"] for mode in manifest["modes"].values())
