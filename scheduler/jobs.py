from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

log = logging.getLogger(__name__)

# Single shared scheduler instance
_scheduler = AsyncIOScheduler(timezone="UTC")


# ── Lifecycle ─────────────────────────────────────────────────────────────────

def start() -> None:
    if not _scheduler.running:
        _scheduler.start()
        log.info("APScheduler started")


def shutdown() -> None:
    if _scheduler.running:
        _scheduler.shutdown(wait=False)
        log.info("APScheduler stopped")


# ── Trigger factory ──────────────────────────────────────────────────────────

def _make_trigger(cron: str):
    """Return an APScheduler trigger from a cron string or interval shorthand.

    Interval shorthand: '30s' = every 30 seconds, '90s' = every 90 seconds.
    Everything else is treated as a standard 5-field crontab expression.
    """
    if cron.endswith("s") and cron[:-1].isdigit():
        return IntervalTrigger(seconds=int(cron[:-1]), timezone="UTC")
    return CronTrigger.from_crontab(cron, timezone="UTC")


# ── Job management ────────────────────────────────────────────────────────────

def add_schedule(
    schedule_id: str,
    cron: str,
    func: Callable,
    kwargs: dict[str, Any],
) -> datetime:
    """Add a cron job. Returns the next scheduled run time (UTC).

    If a job with this ID already exists it is replaced.
    """
    if _scheduler.get_job(schedule_id):
        _scheduler.remove_job(schedule_id)

    trigger = _make_trigger(cron)
    job = _scheduler.add_job(
        func,
        trigger=trigger,
        id=schedule_id,
        kwargs=kwargs,
        replace_existing=True,
        misfire_grace_time=60,
        coalesce=True,
    )
    return job.next_run_time


def remove_schedule(schedule_id: str) -> bool:
    """Remove a scheduled job. Returns True if it existed."""
    job = _scheduler.get_job(schedule_id)
    if job:
        _scheduler.remove_job(schedule_id)
        return True
    return False


def pause_schedule(schedule_id: str) -> bool:
    job = _scheduler.get_job(schedule_id)
    if job:
        job.pause()
        return True
    return False


def resume_schedule(schedule_id: str) -> Optional[datetime]:
    """Resume a paused job. Returns next run time or None if job not found."""
    job = _scheduler.get_job(schedule_id)
    if job:
        job.resume()
        return job.next_run_time
    return None


def get_next_run(schedule_id: str) -> Optional[datetime]:
    job = _scheduler.get_job(schedule_id)
    return job.next_run_time if job else None


def list_jobs() -> list[dict]:
    return [
        {
            "id":           job.id,
            "next_run":     job.next_run_time,
            "paused":       job.next_run_time is None,
        }
        for job in _scheduler.get_jobs()
    ]


# ── Maintenance jobs ──────────────────────────────────────────────────────────

async def _purge_old_executions() -> None:
    from datetime import timedelta
    from sqlalchemy import delete
    from data.store import AsyncSessionLocal, ScheduleExecution as DBScheduleExecution

    cutoff = datetime.now(timezone.utc) - timedelta(days=1)
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            delete(DBScheduleExecution).where(DBScheduleExecution.started_at < cutoff)
        )
        await db.commit()
    log.info("Purged %d schedule_execution row(s) older than 24h", result.rowcount)


def register_maintenance_jobs() -> None:
    _scheduler.add_job(
        _purge_old_executions,
        trigger=CronTrigger(hour=0, minute=0, timezone="UTC"),
        id="__maintenance_purge_executions",
        replace_existing=True,
        misfire_grace_time=3600,
        coalesce=True,
    )
    log.info("Registered maintenance job: purge schedule_executions every 24h")
