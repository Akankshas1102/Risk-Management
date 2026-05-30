from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.admin import router as admin_router
from app.api.analytics import router as analytics_router
from app.api.drivers import router as drivers_router
from app.api.ingest import router as ingest_router
from app.api.insights import router as insights_router
from app.api.predictions import router as predictions_router
from app.api.risk_scores import router as risk_scores_router
from app.core.config import settings
from app.core.scheduler import next_run_time, shutdown_scheduler, start_scheduler


# ---------------------------------------------------------------------------
# Application lifespan — startup + shutdown
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start the nightly-retrain scheduler on boot; stop it on shutdown."""
    import logging
    log = logging.getLogger(__name__)

    next_run = start_scheduler(settings.RETRAIN_CRON)
    if next_run:
        from datetime import timezone
        next_utc = next_run.astimezone(timezone.utc)
        log.info(
            "Nightly retrain scheduled — cron=%r  next_run=%s UTC",
            settings.RETRAIN_CRON,
            next_utc.strftime("%Y-%m-%d %H:%M:%S"),
        )
        # Also print to stdout so it's visible in docker / uvicorn console output
        print(
            f"[scheduler] Nightly retrain active — "
            f"cron={settings.RETRAIN_CRON!r}  "
            f"next_run={next_utc.strftime('%Y-%m-%d %H:%M:%S')} UTC"
        )

    yield   # application runs here

    shutdown_scheduler()


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(title="Risk Assessment Dashboard API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(admin_router)
app.include_router(analytics_router)
app.include_router(drivers_router)
app.include_router(ingest_router)
app.include_router(insights_router)
app.include_router(predictions_router)
app.include_router(risk_scores_router)


@app.get("/health")
def health_check():
    """Health probe — also reports next scheduled retrain time."""
    nrt = next_run_time()
    return {
        "status": "ok",
        "next_scheduled_retrain": nrt.isoformat() if nrt else None,
    }
