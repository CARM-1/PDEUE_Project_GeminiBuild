from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
import urllib.request
import json
from app.domain.accounting_gateway import AccountingGateway

class OutboxDispatcher:
    """ADR-009 Asynchronous Outbox Webhook Dispatcher & Alert Bus."""
    def __init__(self, accounting_gw: Optional[AccountingGateway] = None):
        self.accounting_gw = accounting_gw or AccountingGateway()
        self.dispatch_log: List[Dict[str, Any]] = []
        self.incident_alerts: List[Dict[str, Any]] = []

    def dispatch_pending_events(self, webhook_url: Optional[str] = None) -> Dict[str, Any]:
        events = self.accounting_gw.get_outbox_events(since_seq=0, limit=100)
        delivered = 0
        for evt in events:
            if evt.get('status') == 'DELIVERED':
                continue
            sig = evt['signature_hmac_sha256']
            payload = evt['payload']
            
            if webhook_url:
                try:
                    req = urllib.request.Request(
                        webhook_url,
                        data=json.dumps(payload).encode('utf-8'),
                        headers={
                            'Content-Type': 'application/json',
                            'X-PDEUE-Signature': sig,
                            'User-Agent': 'PDEUE-Dispatcher/1.0'
                        }
                    )
                    with urllib.request.urlopen(req, timeout=3) as resp:
                        if resp.status in (200, 202):
                            evt['status'] = 'DELIVERED'
                            delivered += 1
                except Exception:
                    evt['status'] = 'RETRY_PENDING'
            else:
                # Mock delivery in local/test execution
                evt['status'] = 'DELIVERED'
                delivered += 1

            self.dispatch_log.append({
                'event_id': evt['event_id'],
                'sequence_id': evt['sequence_id'],
                'status': evt['status'],
                'timestamp': datetime.now(timezone.utc).isoformat()
            })

        return {
            'status': 'COMPLETED',
            'total_processed': len(events),
            'delivered_count': delivered
        }

    def broadcast_incident_alert(self, alert_type: str, severity: str, details: Dict[str, Any]) -> Dict[str, Any]:
        alert = {
            'alert_type': alert_type,
            'severity': severity,
            'details': details,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'broadcast_status': 'EMITTED'
        }
        self.incident_alerts.append(alert)
        return alert
