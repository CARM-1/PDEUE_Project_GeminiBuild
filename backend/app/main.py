from fastapi import FastAPI, Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import prometheus_client
from starlette.responses import Response

app = FastAPI(title="PDEUE Chief Administrator API", version="0.1.0-wave0")
security = HTTPBearer()

def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    if credentials.credentials != "pdeue_dev_secret_token":
        raise HTTPException(status_code=403, detail="Invalid authorization token")
    return credentials.credentials

@app.get("/health")
def get_health():
    return {
        "status": "HEALTHY",
        "phase": "Phase 1 Bootstrap",
        "wave": "Wave 0 Product Chassis",
        "blocked_domains": ["external_data", "aws_prod", "venue_apis", "orders", "money_movement"]
    }

@app.get("/version")
def get_version():
    return {
        "version": "0.1.0-wave0",
        "commit": "bootstrap-init",
        "environment": "local-harness"
    }

@app.get("/metrics", dependencies=[Depends(verify_token)])
def get_metrics():
    return Response(content=prometheus_client.generate_latest(), media_type="text/plain")
