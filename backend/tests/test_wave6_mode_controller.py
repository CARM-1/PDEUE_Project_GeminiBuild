import pytest
from app.domain.mode_controller import ModeController

def test_mode_controller_transitions():
    ctrl = ModeController(initial_mode="RESEARCH")
    assert ctrl.current_mode == "RESEARCH"
    assert ctrl.can_execute_orders() is False

    rec = ctrl.transition_to("PAPER", actor_id="admin_01", justification="Starting paper qualification")
    assert ctrl.current_mode == "PAPER"
    assert ctrl.can_execute_orders() is True
    assert rec["prior_mode"] == "RESEARCH"
    assert len(ctrl.history) == 1

def test_mode_controller_illegal_transition():
    ctrl = ModeController(initial_mode="RESEARCH")
    with pytest.raises(PermissionError):
        ctrl.transition_to("PRODUCTION", actor_id="admin_01", justification="Skip gates")

def test_mode_controller_halted_state():
    ctrl = ModeController(initial_mode="PAPER")
    ctrl.transition_to("HALTED", actor_id="watchdog", justification="Trip detected")
    assert ctrl.current_mode == "HALTED"
    assert ctrl.can_execute_orders() is False
    assert ctrl.can_ingest_live_data() is False
