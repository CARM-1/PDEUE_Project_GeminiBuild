import hmac
import hashlib
import base64
import json
import time
from typing import Dict, Any, Optional

SECRET_KEY = "pdeue_super_secret_phase1_key"

def create_access_token(payload: dict, expires_in: int = 3600) -> str:
    data = payload.copy()
    data["exp"] = int(time.time()) + expires_in
    header = base64.b64encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode()).decode().rstrip("=")
    body = base64.b64encode(json.dumps(data).encode()).decode().rstrip("=")
    signature = hmac.new(SECRET_KEY.encode(), f"{header}.{body}".encode(), hashlib.sha256).hexdigest()
    return f"{header}.{body}.{signature}"

def decode_access_token(token: str) -> Optional[dict]:
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        header, body, signature = parts
        expected_sig = hmac.new(SECRET_KEY.encode(), f"{header}.{body}".encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected_sig):
            return None
        padding = "=" * (-len(body) % 4)
        data = json.loads(base64.b64decode(body + padding).decode())
        if data.get("exp", 0) < time.time():
            return None
        return data
    except Exception:
        return None
