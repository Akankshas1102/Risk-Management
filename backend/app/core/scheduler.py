"""
APScheduler background scheduler for nightly ML pipeline retrains.

Usage
-----
Call ``start_scheduler(cron_expr)`` once during application startup and
``shutdown_scheduler()`` during teardown.  Both are called from app/main.py's
lifespan context manager.

The cron expression is read from ``settings.RETRAIN_CRON`` (default "0 2 * * *"
= daily at 02:00 UTC).  Override with the RETRAIN_CRON environment variable.

APScheduler 3.x is used (already installed).  We use BackgroundScheduler so the
job runs in a dedicated thread without blocking the async event loop.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

log = logging.getLogger(__name__)

# Module-level singleton — created once, reused across requests.
_scheduler: Optional[BackgroundScheduler] = None


def _retrain_job() -> None:
    """Entry point for the scheduled job.  Imported lazily to avoid circular imports."""
    # Import here so the scheduler module can be imported before the service layer
    # is fully initialised (e.g. during Alembic migrations).
    from app.services.orchestrator import run_full_pipeline  # noqa: PLC0415

    log.info("Scheduled retrain starting (trigger=scheduled)")
    try:
        result = run_full_pipeline(trigger="scheduled")
        log.info(
            "Scheduled retrain finished — status=%s  duration=%.1fs",
            result["status"],
            result.get("total_duration_s", 0),
        )
    except Exception:
        log.exception("Scheduled retrain raised an unhandled exception")


def start_scheduler(cron_expr: str = "0 2 * * *") -> datetime | None:
    """
    Start the background scheduler and register the retrain job.

    Parameters
    ----------
    cron_expr : Standard 5-field cron string (UTC).
                Default "0 2 * * *" = daily at 02:00.

    Returns
    -------
    The datetime of the next scheduled run (UTC), or None on failure.
    """
    global _scheduler

    if _scheduler is not None and _scheduler.running:
        log.warning("Scheduler already running — skipping start_scheduler()")
        return None

    _scheduler = BackgroundScheduler(timezone="UTC")

    try:
        trigger = CronTrigger.from_crontab(cron_expr, timezone="UTC")
    except Exception as exc:
        log.error(
            "Invalid RETRAIN_CRON expression %r (%s) — falling back to '0 2 * * *'",
            cron_expr,
            exc,
        )
        trigger = CronTrigger.from_crontab("0 2 * * *", timezone="UTC")

    job = _scheduler.add_job(
        _retrain_job,
        trigger=trigger,
        id="nightly_retrain",
        name="ML pipeline nightly retrain",
        replace_existing=True,
        misfire_grace_time=3600,   # allow up to 1-hour misfire (e.g. server restart)
        coalesce=True,             # only fire once if multiple misfires stacked up
    )

    _scheduler.start()

    next_run: datetime | None = job.next_run_time
    if next_run:
        # APScheduler stores timezone-aware datetimes; convert to UTC string for logging
        next_utc = next_run.astimezone(timezone.utc)
        log.info(
            "Scheduler started — cron=%r  next_retrain=%s UTC",
            cron_expr,
            next_utc.strftime("%Y-%m-%d %H:%M:%S"),
        )
        return next_run
    else:
        log.warning("Scheduler started but next_run_time is None")
        return None


def shutdown_scheduler() -> None:
    """Gracefully stop the background scheduler (called on app shutdown)."""
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
        log.info("Scheduler shut down")
    _scheduler = None


def next_run_time() -> datetime | None:
    """Return the next scheduled retrain time, or None if the scheduler isn't running."""
    if _scheduler is None or not _scheduler.running:
        return None
    job = _scheduler.get_job("nightly_retrain")
    return job.next_run_time if job else None
