import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

class IdentityManager:
    def __init__(self):
        self.users: Dict[str, Dict[str, Any]] = {}
        self.accounts: Dict[str, Dict[str, Any]] = {}

    def register_user(self, username: str, email: str) -> Dict[str, Any]:
        user_id = f"USR-{uuid.uuid4().hex[:8]}"
        user = {"user_id": user_id, "username": username, "email": email, "created_at": datetime.now(timezone.utc).isoformat()}
        self.users[user_id] = user
        return user

    def create_account(self, user_id: str, account_name: str, initial_balance_cents: int) -> Dict[str, Any]:
        if user_id not in self.users:
            raise ValueError("User does not exist")
        account_id = f"ACC-{uuid.uuid4().hex[:8]}"
        account = {
            "account_id": account_id,
            "user_id": user_id,
            "account_name": account_name,
            "balance_cents": initial_balance_cents,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        self.accounts[account_id] = account
        return account

    def get_user_accounts(self, user_id: str) -> List[Dict[str, Any]]:
        return [acc for acc in self.accounts.values() if acc["user_id"] == user_id]

    def validate_account_access(self, user_id: str, account_id: str) -> bool:
        account = self.accounts.get(account_id)
        if not account:
            return False
        return account["user_id"] == user_id
