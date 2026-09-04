from typing import Dict, Any, Optional

class TwoTierRiskEnvelope:
    def __init__(self, system_max_stake_pct: float = 0.05, kelly_scale: float = 0.25, max_factor_exposure_pct: float = 0.10):
        self.system_max_stake_pct = system_max_stake_pct
        self.kelly_scale = kelly_scale
        self.max_factor_exposure_pct = max_factor_exposure_pct

    def evaluate_stake(self, total_equity_cents: int, member_risk_pct: float, factor_committed_cents: int, raw_kelly_stake_cents: int) -> Dict[str, Any]:
        if total_equity_cents <= 0:
            return {'admitted': False, 'allocated_stake_cents': 0, 'reason': 'ZERO_OR_NEGATIVE_EQUITY'}

        effective_stake_pct = min(self.system_max_stake_pct, max(0.0, member_risk_pct))
        system_cap_cents = int(total_equity_cents * effective_stake_pct)

        max_factor_cents = int(total_equity_cents * self.max_factor_exposure_pct)
        factor_headroom_cents = max(0, max_factor_cents - factor_committed_cents)
        if factor_headroom_cents <= 0:
            return {'admitted': False, 'allocated_stake_cents': 0, 'effective_stake_pct': effective_stake_pct, 'reason': 'FACTOR_CONCENTRATION_EXCEEDED'}

        scaled_kelly_cents = int(raw_kelly_stake_cents * self.kelly_scale)
        allocated_cents = min(scaled_kelly_cents, system_cap_cents, factor_headroom_cents)
        if allocated_cents <= 0:
            return {'admitted': False, 'allocated_stake_cents': 0, 'effective_stake_pct': effective_stake_pct, 'reason': 'STAKE_BELOW_MINIMUM'}

        return {
            'admitted': True,
            'allocated_stake_cents': allocated_cents,
            'effective_stake_pct': effective_stake_pct,
            'system_cap_cents': system_cap_cents,
            'factor_headroom_cents': factor_headroom_cents,
            'scaled_kelly_cents': scaled_kelly_cents
        }
