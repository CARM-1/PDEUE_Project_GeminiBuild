import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

class AuditRetentionEngine:
    GENESIS_HASH = "0" * 64

    def __init__(self):
        self.audit_chain: List[Dict[str, Any]] = []
        self.last_hash: str = self.GENESIS_HASH

    def _compute_hash(self, prev_hash: str, entry_dict: Dict[str, Any]) -> str:
        canonical_bytes = json.dumps(entry_dict, sort_keys=True).encode("utf-8")
        return hashlib.sha256(prev_hash.encode("utf-8") + canonical_bytes).hexdigest()

    def record_event(
        self,
        tenant_id: str,
        action: str,
        actor_id: str,
        details: Dict[str, Any]
    ) -> Dict[str, Any]:
        event_body = {
            "event_id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "action": action,
            "actor_id": actor_id,
            "details": details,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        entry_hash = self._compute_hash(self.last_hash, event_body)
        full_entry = {
            "event": event_body,
            "prev_hash": self.last_hash,
            "entry_hash": entry_hash
        }
        self.audit_chain.append(full_entry)
        self.last_hash = entry_hash
        return full_entry

    def verify_chain_integrity(self) -> bool:
        expected_prev = self.GENESIS_HASH
        for item in self.audit_chain:
            if item.get("prev_hash") != expected_prev:
                return False
            recomputed = self._compute_hash(expected_prev, item["event"])
            if item.get("entry_hash") != recomputed:
                return False
            expected_prev = item["entry_hash"]
        return True

    def export_tenant_manifest(self, tenant_id: str) -> Dict[str, Any]:
        tenant_entries = [e for e in self.audit_chain if e["event"]["tenant_id"] == tenant_id]
        return {
            "manifest_id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "total_records": len(tenant_entries),
            "chain_verified": self.verify_chain_integrity(),
            "latest_root_hash": self.last_hash,
            "records": tenant_entries
        }
