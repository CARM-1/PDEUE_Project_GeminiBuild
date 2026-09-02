import pytest
from app.domain.identity import IdentityManager

def test_user_and_multi_account_creation():
    manager = IdentityManager()
    user = manager.register_user("trader_alpha", "alpha@pdeue.io")
    acc1 = manager.create_account(user["user_id"], "Primary Trading", 500000)
    acc2 = manager.create_account(user["user_id"], "Hedge Portfolio", 250000)
    
    accounts = manager.get_user_accounts(user["user_id"])
    assert len(accounts) == 2
    assert acc1["balance_cents"] == 500000
    assert acc2["balance_cents"] == 250000

def test_multi_tenant_isolation():
    manager = IdentityManager()
    user_a = manager.register_user("user_a", "a@pdeue.io")
    user_b = manager.register_user("user_b", "b@pdeue.io")
    
    acc_a = manager.create_account(user_a["user_id"], "A Account", 100000)
    acc_b = manager.create_account(user_b["user_id"], "B Account", 100000)
    
    assert manager.validate_account_access(user_a["user_id"], acc_a["account_id"]) is True
    assert manager.validate_account_access(user_a["user_id"], acc_b["account_id"]) is False
