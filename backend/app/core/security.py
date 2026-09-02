import jwt
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

SECRET_KEY = "pdeue_dev_secret_key_change_in_production"
ALGORITHM = "HS256"

security_scheme = HTTPBearer()

def create_jwt_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(hours=24))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

create_access_token = create_jwt_token

def decode_jwt_token(token: str) -> Dict[str, Any]:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except Exception:
        raise HTTPException(status_code=403, detail="Invalid or expired authentication token")

def verify_jwt_token(credentials: HTTPAuthorizationCredentials = Depends(security_scheme)) -> Dict[str, Any]:
    return decode_jwt_token(credentials.credentials)
