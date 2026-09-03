import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Set, Optional

ROLE_PERMISSIONS: Dict[str, Set[str]] = {
    "AUDITOR": {"VIEW_AUDIT", "EXPORT_MANIFEST", "VIEW_METRICS"},
    "OPERATOR": {"VIEW_AUDIT", "START_SESSION", "STOP_SESSION", "VIEW_METRICS"},
    "RISK_ADMIN": {"VIEW_AUDIT", "TRIP_KILL_SWITCH", "RESET_KILL_SWITCH", "OVERRIDE_RISK", "VIEW_METRICS"},
    "CHIEF_ADMIN": {"VIEW_AUDIT", "EXPORT_MANIFEST", "START_SESSION", "STOP_SESSION", "TRIP_KILL_SWITCH", "RESET_KILL_SWITCH", "OVERRIDE_RISK", "MANAGE_USERS", "LEASE_SECRETS", "VIEW_METRICS"}
}

class IdentityGovernanceEngine:
    def __init__(self):
        self.principals: Dict[str, Dict[str, Any]] = {}
        self.secret_vault_references: Dict[str, Dict[str, str]] = {}

    def register_principal(self, principal_id: str, tenant_id: str, roles: List[str]) -> Dict[str, Any]:
        record = {
            "principal_id": principal_id,
            "tenant_id": tenant_id,
            "roles": roles,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        self.principals[principal_id] = record
        return record

    def register_secret_reference(self, tenant_id: str, secret_alias: str, vault_uri: str) -> None:
        key = f"{tenant_id}:{secret_alias}"
        self.secret_vault_references[key] = {
            "tenant_id": tenant_id,
            "secret_alias": secret_alias,
            "vault_uri": vault_uri
        }

    def authorize_action(self, principal_id: str, target_tenant_id: str, action: str) -> Dict[str, Any]:
        decision_id = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc).isoformat()
        principal = self.principals.get(principal_id)

        if not principal:
            return {"decision_id": decision_id, "authorized": False, "reason": "PRINCIPAL_NOT_FOUND", "timestamp": timestamp}

        if principal["tenant_id"] != target_tenant_id:
            return {"decision_id": decision_id, "authorized": False, "reason": "CROSS_TENANT_ACCESS_DENIED", "timestamp": timestamp}

        effective_permissions: Set[str] = set()
        for role in principal["roles"]:
            effective_permissions.update(ROLE_PERMISSIONS.get(role, set()))

        if action not in effective_permissions:
            return {"decision_id": decision_id, "authorized": False, "reason": f"INSUFFICIENT_PERMISSIONS_FOR_{action}", "timestamp": timestamp}

        return {
            "decision_id": decision_id,
            "authorized": True,
            "principal_id": principal_id,
            "tenant_id": target_tenant_id,
            "action": action,
            "reason": "AUTHORIZED",
            "timestamp": timestamp
        }

    def lease_secret_reference(self, principal_id: str, tenant_id: str, secret_alias: str) -> Dict[str, Any]:
        auth_check = self.authorize_action(principal_id, tenant_id, "LEASE_SECRETS")
        if not auth_check["authorized"]:
            return {"success": False, "reason": auth_check["reason"]}

        key = f"{tenant_id}:{secret_alias}"
        secret_ref = self.secret_vault_references.get(key)
        if not secret_ref:
            return {"success": False, "reason": "SECRET_REFERENCE_NOT_FOUND"}

        return {
            "success": True,
            "lease_id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "secret_alias": secret_alias,
            "vault_uri": secret_ref["vault_uri"],
            "issued_at": datetime.now(timezone.utc).isoformat()
        }
