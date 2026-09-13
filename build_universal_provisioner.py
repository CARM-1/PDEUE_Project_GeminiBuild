import sys
import os
import pathlib

# Ensure the backend directory is in the Python path
BACKEND_DIR = pathlib.Path(__file__).resolve().parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from app.db.session import engine, SessionLocal, Base
from app.db.models import UserModel, AccountModel, PrincipalModel, TenantModel, AuditLogRecordModel

# Authoritative Role Archetypes & Portal Bindings
ROLE_ARCHETYPES = {
    "CHIEF_ADMINISTRATOR": {
        "portal_route": "/dashboard",
        "description": "Executive Governance, Dual-Control, and Master Kill-Switch Authority",
        "default_risk_ceiling": 0.05,
        "requires_scma": True
    },
    "MEMBER_USER": {
        "portal_route": "/member",
        "description": "Autonomous Lineal Account, Downward-Only Risk Dial, Single-SCMA",
        "default_risk_ceiling": 0.02,
        "requires_scma": True
    },
    "F1_FINANCIAL_ADVISOR": {
        "portal_route": "/advisor",
        "description": "Lineal Peer Advisor, Household Portfolio Review, Read-Only Audit",
        "default_risk_ceiling": 0.05,
        "requires_scma": False
    },
    "F2_FINANCIAL_ADVISOR": {
        "portal_route": "/advisor",
        "description": "Household Elder Advisor, Multi-Account Oversight, Red-Tier Review",
        "default_risk_ceiling": 0.05,
        "requires_scma": False
    },
    "F3_FINANCIAL_ADVISOR": {
        "portal_route": "/advisor",
        "description": "Chief Risk Officer Context, Dual-Control Co-Signer for Market Bounds",
        "default_risk_ceiling": 0.05,
        "requires_scma": False
    },
    "T1_SYSTEM_ADMIN": {
        "portal_route": "/admin/tech",
        "description": "Junior Technical Operator, Daemon Telemetry, Redacted Logs",
        "default_risk_ceiling": 0.0,
        "requires_scma": False
    },
    "T2_SYSTEM_ADMIN": {
        "portal_route": "/admin/tech",
        "description": "Infrastructure Engineer, Rate-Limiter Tuning, Node Diagnostics",
        "default_risk_ceiling": 0.0,
        "requires_scma": False
    },
    "T3_SYSTEM_ADMIN": {
        "portal_route": "/admin/tech",
        "description": "Chief Technology Officer Context, Container Deployment, Dual-Control Co-Signer",
        "default_risk_ceiling": 0.0,
        "requires_scma": False
    }
}

class UniversalProvisioningEngine:
    def __init__(self):
        Base.metadata.create_all(bind=engine)

    def _append_audit_log(self, db: Session, action: str, tenant_id: str, payload: dict) -> str:
        now_iso = datetime.now(timezone.utc).isoformat()
        last_log = db.query(AuditLogRecordModel).order_by(AuditLogRecordModel.recorded_at.desc()).first()
        prev_hash = last_log.entry_hash if last_log else "GENESIS_PDEUE_PROVISION_HASH"
        
        payload_str = json.dumps(payload, sort_keys=True)
        entry_hash = hashlib.sha256(f"{prev_hash}:{payload_str}".encode()).hexdigest()

        audit_record = AuditLogRecordModel(
            entry_id=f"AUD-{str(uuid.uuid4())[:12]}",
            tenant_id=tenant_id,
            actor_id="CHIEF_ADMINISTRATOR",
            action=action,
            prev_hash=prev_hash,
            entry_hash=entry_hash,
            payload=payload_str,
            recorded_at=now_iso
        )
        db.add(audit_record)
        return entry_hash

    def provision_identity(
        self,
        db: Session,
        full_name: str,
        role: str,
        household_id: str = "HOUSEHOLD-ALPHA",
        seed_capital_cents: int = 0
    ) -> dict:
        role_upper = role.upper()
        if role_upper not in ROLE_ARCHETYPES:
            raise ValueError(f"Invalid role token: {role}. Must be one of {list(ROLE_ARCHETYPES.keys())}")

        archetype = ROLE_ARCHETYPES[role_upper]
        user_uid = str(uuid.uuid4())[:8].upper()
        clean_name = full_name.lower().replace(" ", "_")
        user_id = f"USR-{clean_name[:10]}-{user_uid}"
        now_iso = datetime.now(timezone.utc).isoformat()

        # 1. Ensure Tenant Exists
        tenant = db.query(TenantModel).filter(TenantModel.tenant_id == household_id).first()
        if not tenant:
            tenant = TenantModel(tenant_id=household_id, name=f"Lineage {household_id}")
            db.add(tenant)
            db.flush()

        # 2. Create User Identity
        user_record = UserModel(
            user_id=user_id,
            tenant_id=household_id,
            username=f"{clean_name}_{user_uid}",
            email=f"{clean_name}@{household_id.lower()}.pdeue.internal",
            role=role_upper,
            created_at=now_iso
        )
        db.add(user_record)

        # 3. Create Principal Permission Entity
        principal_record = PrincipalModel(
            principal_id=f"PRIN-{user_uid}",
            tenant_id=household_id,
            role=role_upper,
            created_at=now_iso
        )
        db.add(principal_record)

        # 4. Conditionally Allocate SCMA Ledger Partition
        account_id = None
        if archetype["requires_scma"] or seed_capital_cents > 0:
            account_id = f"SCMA-{clean_name[:8]}-{user_uid}".upper()
            account_record = AccountModel(
                account_id=account_id,
                user_id=user_id,
                tenant_id=household_id,
                balance_cents=seed_capital_cents,
                currency="USD",
                status="ACTIVE",
                created_at=now_iso
            )
            db.add(account_record)

        # 5. Append Sealed Audit Entry
        audit_payload = {
            "actor_id": "CHIEF_ADMINISTRATOR",
            "action": "PROVISION_UNIVERSAL_IDENTITY",
            "user_id": user_id,
            "full_name": full_name,
            "role": role_upper,
            "household_id": household_id,
            "account_id": account_id,
            "seed_capital_cents": seed_capital_cents,
            "portal_route": archetype["portal_route"],
            "timestamp": now_iso
        }
        entry_hash = self._append_audit_log(db, "PROVISION_UNIVERSAL_IDENTITY", household_id, audit_payload)
        db.commit()

        token_secret = hashlib.sha256(f"{user_id}:{now_iso}:PDEUE_SALT".encode()).hexdigest()[:24]
        activation_link = f"http://localhost:8000{archetype['portal_route']}?activation_token={token_secret}&user_id={user_id}"

        return {
            "status": "PROVISIONED",
            "user_id": user_id,
            "full_name": full_name,
            "role": role_upper,
            "household_id": household_id,
            "account_id": account_id,
            "portal_route": archetype["portal_route"],
            "activation_link": activation_link,
            "audit_hash": entry_hash
        }

    def transition_user_role(
        self,
        db: Session,
        user_id: str,
        new_role: str,
        justification: str = "Lineal Merit Promotion"
    ) -> dict:
        """
        Atomically transition/promote an existing identity to a new class (e.g., MEMBER -> F1 or T2).
        Preserves original SCMA partition while re-binding active portal and permissions.
        """
        new_role_upper = new_role.upper()
        if new_role_upper not in ROLE_ARCHETYPES:
            raise ValueError(f"Invalid new role: {new_role}. Must be one of {list(ROLE_ARCHETYPES.keys())}")

        user = db.query(UserModel).filter(UserModel.user_id == user_id).first()
        if not user:
            raise ValueError(f"Target identity {user_id} not found.")

        old_role = user.role
        if old_role == new_role_upper:
            return {"status": "NOOP", "message": f"User {user_id} already holds role {new_role_upper}"}

        now_iso = datetime.now(timezone.utc).isoformat()
        archetype = ROLE_ARCHETYPES[new_role_upper]

        # 1. Update UserModel Role Token
        user.role = new_role_upper

        # 2. Update or Attach Principal Entity
        principal = db.query(PrincipalModel).filter(PrincipalModel.tenant_id == user.tenant_id).first()
        if principal:
            principal.role = new_role_upper
        else:
            principal = PrincipalModel(
                principal_id=f"PRIN-{str(uuid.uuid4())[:8].upper()}",
                tenant_id=user.tenant_id,
                role=new_role_upper,
                created_at=now_iso
            )
            db.add(principal)

        # 3. Retain Existing SCMA (Capital Isolation)
        scma = db.query(AccountModel).filter(AccountModel.user_id == user_id).first()
        scma_id = scma.account_id if scma else None

        # 4. Append Immutable Role Transition Audit Record
        audit_payload = {
            "actor_id": "CHIEF_ADMINISTRATOR",
            "action": "TRANSITION_USER_ROLE",
            "user_id": user_id,
            "old_role": old_role,
            "new_role": new_role_upper,
            "household_id": user.tenant_id,
            "preserved_scma": scma_id,
            "justification": justification,
            "portal_route": archetype["portal_route"],
            "timestamp": now_iso
        }
        entry_hash = self._append_audit_log(db, "TRANSITION_USER_ROLE", user.tenant_id, audit_payload)
        db.commit()

        token_secret = hashlib.sha256(f"{user_id}:{new_role_upper}:{now_iso}:PDEUE_SALT".encode()).hexdigest()[:24]
        new_activation_link = f"http://localhost:8000{archetype['portal_route']}?session_token={token_secret}&user_id={user_id}"

        return {
            "status": "TRANSITIONED",
            "user_id": user_id,
            "old_role": old_role,
            "new_role": new_role_upper,
            "preserved_scma": scma_id,
            "target_portal": archetype["portal_route"],
            "new_access_link": new_activation_link,
            "audit_hash": entry_hash
        }

    def batch_provision_matrix(self, db: Session, roster: list) -> list:
        results = []
        for entry in roster:
            res = self.provision_identity(
                db=db,
                full_name=entry.get("name"),
                role=entry.get("role"),
                household_id=entry.get("household_id", "HOUSEHOLD-ALPHA"),
                seed_capital_cents=entry.get("seed_capital_cents", 0)
            )
            results.append(res)
        return results

if __name__ == "__main__":
    db = SessionLocal()
    engine_svc = UniversalProvisioningEngine()

    print("=== 1. Executing Universal Provisioning Verification Matrix ===")
    test_roster = [
        {"name": "Founder Chief Admin", "role": "CHIEF_ADMINISTRATOR", "household_id": "HOUSEHOLD-ALPHA", "seed_capital_cents": 500000},
        {"name": "Eleanor Vance", "role": "MEMBER_USER", "household_id": "HOUSEHOLD-ALPHA", "seed_capital_cents": 125000},
        {"name": "Marcus Aurelius Vance", "role": "F1_FINANCIAL_ADVISOR", "household_id": "HOUSEHOLD-ALPHA", "seed_capital_cents": 0},
        {"name": "DevOps Lead Alex", "role": "T3_SYSTEM_ADMIN", "household_id": "HOUSEHOLD-ALPHA", "seed_capital_cents": 0}
    ]

    manifest = engine_svc.batch_provision_matrix(db, test_roster)
    eleanor_id = None
    for m in manifest:
        print(f"* [{m['role']}] {m['full_name']} -> {m['portal_route']} (SCMA: {m['account_id']})")
        if "Eleanor" in m["full_name"]:
            eleanor_id = m["user_id"]

    print("\n=== 2. Testing Lineal Role Transition / Promotion Engine ===")
    if eleanor_id:
        print(f"Promoting {eleanor_id} from MEMBER_USER to F1_FINANCIAL_ADVISOR...")
        trans_result = engine_svc.transition_user_role(
            db=db,
            user_id=eleanor_id,
            new_role="F1_FINANCIAL_ADVISOR",
            justification="Passed Lineal Financial Mentorship Accreditation"
        )
        print("Promotion Successful:")
        print(f"  - User:           {trans_result['user_id']}")
        print(f"  - Transition:     {trans_result['old_role']} -> {trans_result['new_role']}")
        print(f"  - Preserved SCMA: {trans_result['preserved_scma']}")
        print(f"  - Re-routed To:   {trans_result['target_portal']}")
        print(f"  - Audit Hash:     {trans_result['audit_hash'][:24]}...")

    db.close()