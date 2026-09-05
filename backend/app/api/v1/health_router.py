from fastapi import APIRouter, Response, status
from datetime import datetime, timezone
from app.domain.circuit_breaker import CircuitBreakerEngine

health_router = APIRouter(tags=['Health'])
_cb = CircuitBreakerEngine()

@health_router.get('/healthz')
def healthcheck(response: Response):
    is_healthy = _cb.validate_execution_allowed()
    payload = {
        'status': 'HEALTHY' if is_healthy else 'DEGRADED',
        'circuit_breaker_tripped': not is_healthy,
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'version': '1.0.0-rc1'
    }
    if not is_healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return payload
