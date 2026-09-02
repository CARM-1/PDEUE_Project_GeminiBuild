from fastapi import FastAPI
from app.api.v1.underwriting_router import router as underwriting_router
from app.api.v1.operator_router import router as operator_router

app = FastAPI(title="PDEUE Engine API")

@app.get("/health")
def health_check():
    return {"status": "ok"}

app.include_router(underwriting_router, prefix="/api/v1")
app.include_router(operator_router, prefix="/api/v1")
