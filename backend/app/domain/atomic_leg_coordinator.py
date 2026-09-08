import time
from typing import Dict, Any, List, Optional

class AtomicLegCoordinator:
    def __init__(self, leg_timeout_ms: float = 750.0):
        self.leg_timeout_sec = leg_timeout_ms / 1000.0
        self.scratched_positions: List[Dict[str, Any]] = []

    def coordinate_legs(
        self,
        primary_leg: Dict[str, Any],
        secondary_leg: Dict[str, Any],
        simulate_leg2_latency_sec: float = 0.0,
        simulate_leg2_fail: bool = False
    ) -> Dict[str, Any]:
        primary_fill = {**primary_leg, 'status': 'FILLED', 'fill_time': time.monotonic()}
        if simulate_leg2_latency_sec > self.leg_timeout_sec or simulate_leg2_fail:
            scratch_event = {
                'action': 'SCRATCH_LIQUIDATION',
                'primary_leg_id': primary_leg.get('leg_id', 'LEG-1'),
                'secondary_leg_id': secondary_leg.get('leg_id', 'LEG-2'),
                'reason': 'LEG_2_TIMEOUT_EXCEEDED' if simulate_leg2_latency_sec > self.leg_timeout_sec else 'LEG_2_FILL_REJECTED',
                'slippage_cents': 1,
                'status': 'SCRATCHED'
            }
            self.scratched_positions.append(scratch_event)
            return {
                'is_atomic_success': False,
                'outcome': 'SCRATCHED',
                'primary_fill': primary_fill,
                'secondary_fill': None,
                'scratch_event': scratch_event
            }
        secondary_fill = {**secondary_leg, 'status': 'FILLED', 'fill_time': time.monotonic()}
        return {
            'is_atomic_success': True,
            'outcome': 'COMPLETE_SET_FILLED',
            'primary_fill': primary_fill,
            'secondary_fill': secondary_fill,
            'scratch_event': None
        }
