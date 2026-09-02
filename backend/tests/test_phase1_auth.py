from app.core.security import create_access_token, decode_access_token
from app.domain.identity import IdentityManager
import time

def test_token_creation_and_decoding():
    payload = {"sub": "USR-1234", "username": "trader1"}
    token = create_access_token(payload, expires_in=60)
    decoded = decode_access_token(token)
    assert decoded is not None
    assert decoded["sub"] == "USR-1234"
    assert decoded["username"] == "trader1"

def test_invalid_and_expired_token():
    payload = {"sub": "USR-1234"}
    token = create_access_token(payload, expires_in=-10)
    assert decode_access_token(token) is None
    
    valid_token = create_access_token(payload, expires_in=60)
    tampered = valid_token[:-4] + "0000"
    assert decode_access_token(tampered) is None

def test_tenant_authenticated_scope():
    identity_mgr = IdentityManager()
    user_a = identity_mgr.register_user("user_a", "a@pdeue.io")
    user_b = identity_mgr.register_user("user_b", "b@pdeue.io")
    
    token_a = create_access_token({"sub": user_a["user_id"]})
    token_b = create_access_token({"sub": user_b["user_id"]})
    
    claims_a = decode_access_token(token_a)
    claims_b = decode_access_token(token_b)
    
    acc_a = identity_mgr.create_account(user_a["user_id"], "Acc A", 1000)
    
    assert identity_mgr.validate_account_access(claims_a["sub"], acc_a["account_id"]) is True
    assert identity_mgr.validate_account_access(claims_b["sub"], acc_a["account_id"]) is False
