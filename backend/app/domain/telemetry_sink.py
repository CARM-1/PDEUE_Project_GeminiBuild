import json
import os
from datetime import datetime, timezone
from typing import Dict, Any, Optional

class TelemetryHealthSink:
    def __init__(self, export_path: str = 'health_summary.json'):
        self.export_path = export_path

    def compile_health_payload(
        self,
        ledger_balances: Dict[str, int],
        maker_stats: Dict[str, int],
        spread_distributions: Dict[str, float],
        circuit_breaker_status: Dict[str, Any],
        rate_limiter_warnings: int = 0
    ) -> Dict[str, Any]:
        posted = int(maker_stats.get('posted', 0))
        filled = int(maker_stats.get('filled', 0))
        expired = int(maker_stats.get('expired', 0))
        fill_ratio = round((filled / posted), 4) if posted > 0 else 0.0

        return {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'status': 'HEALTHY' if not circuit_breaker_status.get('is_tripped', False) else 'DEGRADED',
            'balances_cents': {
                'founder_scma': int(ledger_balances.get('founder_scma', 0)),
                'cfcp_family_pool': int(ledger_balances.get('cfcp', 0)),
                'faep_founder_pool': int(ledger_balances.get('faep', 0)),
                'total_equity': int(sum(ledger_balances.values()))
            },
            'maker_execution_metrics': {
                'bids_posted': posted,
                'bids_filled': filled,
                'bids_expired': expired,
                'fill_ratio': fill_ratio
            },
            'spread_distributions': {
                'WEATHER': float(spread_distributions.get('WEATHER', 0.0)),
                'MACRO': float(spread_distributions.get('MACRO', 0.0)),
                'SPORTS': float(spread_distributions.get('SPORTS', 0.0)),
                'CRYPTO': float(spread_distributions.get('CRYPTO', 0.0))
            },
            'runtime_safeguards': {
                'circuit_breaker_tripped': bool(circuit_breaker_status.get('is_tripped', False)),
                'trip_reason': circuit_breaker_status.get('trip_reason', None),
                'rate_limiter_warnings': int(rate_limiter_warnings)
            }
        }

    def export_health_summary(self, payload: Dict[str, Any]) -> str:
        tmp_path = self.export_path + '.tmp'
        with open(tmp_path, 'w', encoding='utf-8') as f:
            json.dump(payload, f, indent=2)
        os.replace(tmp_path, self.export_path)
        return self.export_path
