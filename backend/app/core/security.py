import base64
import json
import hmac
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

SECRET_KEY = "pdeue_dev_secret_key_change_in_production"
security_scheme = HTTPBearer()

def _b64_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("utf-8")

def _b64_decode(data_str: str) -> bytes:
    padding = "=" * ((4 - len(data_str) % 4) % 4)
    return base64.urlsafe_b64decode((data_str + padding).encode("utf-8"))

def create_jwt_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None, expires_in: Optional[int] = None) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    payload = data.copy()
    if expires_in is not None:
        delta = timedelta(seconds=expires_in)
    elif expires_delta is not None:
        delta = expires_delta
    else:
        delta = timedelta(hours=24)
    expire = (datetime.now(timezone.utc) + delta).timestamp()
    payload.update({"exp": expire})
    header_b64 = _b64_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    payload_b64 = _b64_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{header_b64}.{payload_b64}".encode("utf-8")
    signature = hmac.new(SECRET_KEY.encode("utf-8"), signing_input, hashlib.sha256).digest()
    sig_b64 = _b64_encode(signature)
    return f"{header_b64}.{payload_b64}.{sig_b64}"

create_access_token = create_jwt_token

def decode_jwt_token(token: str) -> Optional[Dict[str, Any]]:
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        header_b64, payload_b64, sig_b64 = parts
        signing_input = f"{header_b64}.{payload_b64}".encode("utf-8")
        expected_sig = _b64_encode(hmac.new(SECRET_KEY.encode("utf-8"), signing_input, hashlib.sha256).digest())
        if not hmac.compare_digest(sig_b64, expected_sig):
            return None
        payload = json.loads(_b64_decode(payload_b64).decode("utf-8"))
        if "exp" in payload and datetime.now(timezone.utc).timestamp() > payload["exp"]:
            return None
        return payload
    except Exception:
        return None

decode_access_token = decode_jwt_token

def verify_jwt_token(credentials: HTTPAuthorizationCredentials = Depends(security_scheme)) -> Dict[str, Any]:
    payload = decode_jwt_token(credentials.credentials)
    if not payload:
        raise HTTPException(status_code=403, detail="Invalid or expired authentication token")
    return payload
