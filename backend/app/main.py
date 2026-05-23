from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.admin import router as admin_router
from app.api.analytics import router as analytics_router
from app.api.drivers import router as drivers_router
from app.api.ingest import router as ingest_router
from app.api.predictions import router as predictions_router
from app.api.risk_scores import router as risk_scores_router

app = FastAPI(title="Risk Assessment Dashboard API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(admin_router)
app.include_router(analytics_router)
app.include_router(drivers_router)
app.include_router(ingest_router)
app.include_router(predictions_router)
app.include_router(risk_scores_router)


@app.get("/health")
def health_check():
    return {"status": "ok"}
