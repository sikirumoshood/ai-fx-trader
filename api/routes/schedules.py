from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas import (
    CreateScheduleRequest,
    UpdateScheduleRequest,
    ScheduleExecutionResponse,
    ScheduleResponse,
)
from data.store import (
    get_db, Schedule as DBSchedule, ScheduleStatus,
    Signal as DBSignal, SignalStatus, SignalDirection, NewsBias,
    ScheduleExecution as DBScheduleExecution,
    AsyncSessionLocal,
)
from scheduler import jobs
from signals.engine import SignalEngine, SkipSignal

router = APIRouter()


# ── POST /schedules ───────────────────────────────────────────────────────────

@router.post("", status_code=status.HTTP_201_CREATED, response_model=ScheduleResponse)
async def create_schedule(
    req: CreateScheduleRequest,
    db: AsyncSession = Depends(get_db),
):
    schedule_id = f"sch_{uuid.uuid4().hex[:10]}"
    now = datetime.now(timezone.utc)

    # Register with APScheduler
    next_run = jobs.add_schedule(
        schedule_id=schedule_id,
        cron=req.cron,
        func=_run_scheduled_signal,
        kwargs={
            "schedule_id":    schedule_id,
            "pair":           req.pair.upper(),
            "timeframe":      req.timeframe.upper(),
            "min_pips":       req.min_pips,
            "stop_loss_pips": req.stop_loss_pips,
            "risk_reward":    req.risk_reward,
            "risk_percent":   req.risk_percent,
            "sessions":       req.sessions or None,
            "notify":         req.notify,
        },
    )

    sched = DBSchedule(
        id=schedule_id,
        pair=req.pair.upper(),
        timeframe=req.timeframe.upper(),
        cron=req.cron,
        min_pips=req.min_pips,
        stop_loss_pips=req.stop_loss_pips,
        risk_reward=req.risk_reward,
        risk_percent=req.risk_percent,
        notify=req.notify,
        sessions=req.sessions or None,
        status=ScheduleStatus.ACTIVE,
        next_run=next_run,
        created_at=now,
        updated_at=now,
    )
    db.add(sched)
    await db.commit()
    await db.refresh(sched)

    return _to_response(sched)


# ── GET /schedules ────────────────────────────────────────────────────────────

@router.get("", response_model=list[ScheduleResponse])
async def list_schedules(db: AsyncSession = Depends(get_db)):
    await _sync_next_runs(db)
    rows = await db.execute(
        select(DBSchedule).order_by(DBSchedule.created_at.desc())
    )
    return [_to_response(s) for s in rows.scalars().all()]


# ── GET /schedules/{id} ───────────────────────────────────────────────────────

@router.get("/{schedule_id}", response_model=ScheduleResponse)
async def get_schedule(schedule_id: str, db: AsyncSession = Depends(get_db)):
    sched = await _get_active_schedule(schedule_id, db)
    sched.next_run = jobs.get_next_run(schedule_id)
    await db.commit()
    return _to_response(sched)


# ── GET /schedules/{id}/executions ────────────────────────────────────────────

@router.get("/{schedule_id}/executions", response_model=list[ScheduleExecutionResponse])
async def list_schedule_executions(
    schedule_id: str,
    limit: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    sched = await db.get(DBSchedule, schedule_id)
    if sched is None:
        raise HTTPException(status_code=404, detail="Schedule not found")

    rows = await db.execute(
        select(DBScheduleExecution)
        .where(DBScheduleExecution.schedule_id == schedule_id)
        .order_by(DBScheduleExecution.started_at.desc())
        .limit(limit)
    )
    return [_to_execution_response(r) for r in rows.scalars().all()]


# ── PATCH /schedules/{id} ─────────────────────────────────────────────────────

@router.patch("/{schedule_id}", response_model=ScheduleResponse)
async def update_schedule(
    schedule_id: str,
    req: UpdateScheduleRequest,
    db: AsyncSession = Depends(get_db),
):
    sched = await _get_active_schedule(schedule_id, db)
    should_refresh_job = False

    if req.min_pips is not None:
        sched.min_pips = req.min_pips
        should_refresh_job = True
    if req.stop_loss_pips is not None:
        sched.stop_loss_pips = req.stop_loss_pips
        should_refresh_job = True
    if req.risk_reward is not None:
        sched.risk_reward = req.risk_reward
        should_refresh_job = True
    if req.risk_percent is not None:
        sched.risk_percent = req.risk_percent
        should_refresh_job = True
    if req.notify is not None:
        sched.notify = req.notify
        should_refresh_job = True
    if req.sessions is not None:
        sched.sessions = req.sessions or None
        should_refresh_job = True

    if req.cron is not None:
        sched.cron = req.cron
        should_refresh_job = True

    if should_refresh_job:
        next_run = jobs.add_schedule(
            schedule_id=schedule_id,
            cron=sched.cron,
            func=_run_scheduled_signal,
            kwargs=_job_kwargs(sched),
        )
        if sched.status == ScheduleStatus.PAUSED:
            jobs.pause_schedule(schedule_id)
            sched.next_run = None
        else:
            sched.next_run = next_run

    sched.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(sched)
    return _to_response(sched)


# ── DELETE /schedules/{id} ────────────────────────────────────────────────────

@router.delete("/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_schedule(schedule_id: str, db: AsyncSession = Depends(get_db)):
    sched = await db.get(DBSchedule, schedule_id)
    if sched is None:
        raise HTTPException(status_code=404, detail="Schedule not found")
    jobs.remove_schedule(schedule_id)
    sched.status = ScheduleStatus.CANCELED
    sched.updated_at = datetime.now(timezone.utc)
    await db.commit()


# ── POST /schedules/{id}/pause ────────────────────────────────────────────────

@router.post("/{schedule_id}/pause", response_model=ScheduleResponse)
async def pause_schedule(schedule_id: str, db: AsyncSession = Depends(get_db)):
    sched = await _get_active_schedule(schedule_id, db)
    jobs.pause_schedule(schedule_id)
    sched.status     = ScheduleStatus.PAUSED
    sched.next_run   = None
    sched.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return _to_response(sched)


# ── POST /schedules/{id}/resume ───────────────────────────────────────────────

@router.post("/{schedule_id}/resume", response_model=ScheduleResponse)
async def resume_schedule(schedule_id: str, db: AsyncSession = Depends(get_db)):
    sched = await db.get(DBSchedule, schedule_id)
    if sched is None:
        raise HTTPException(status_code=404, detail="Schedule not found")
    if sched.status == ScheduleStatus.CANCELED:
        raise HTTPException(status_code=409, detail="Cannot resume a canceled schedule")

    next_run = jobs.resume_schedule(schedule_id)
    sched.status     = ScheduleStatus.ACTIVE
    sched.next_run   = next_run
    sched.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return _to_response(sched)


# ── Scheduled job callback ────────────────────────────────────────────────────

async def _run_scheduled_signal(
    schedule_id: str,
    pair: str,
    timeframe: str,
    min_pips: float,
    stop_loss_pips: float,
    risk_reward: float,
    risk_percent: float,
    sessions: list[str] | None = None,
    notify: bool = False,
) -> None:
    """Called by APScheduler on each cron tick."""
    import logging
    from api.server import app

    log = logging.getLogger(__name__)
    audit_log = logging.getLogger("schedule.execution")
    started_at = datetime.now(timezone.utc)
    outcome = "FAILED"
    detail: str | None = None
    signal_id: str | None = None

    audit_log.info(
        "run.start schedule_id=%s pair=%s timeframe=%s cron_tick=%s",
        schedule_id,
        pair,
        timeframe,
        started_at.isoformat(),
    )
    engine: SignalEngine = getattr(app.state, "signal_engine", None)
    if engine is None:
        log.warning("Scheduled run %s: signal engine not available", schedule_id)
        outcome = "FAILED"
        detail = "signal engine not available"
    else:
        try:
            result = await engine.generate(
                pair=pair,
                timeframe=timeframe,
                min_pips=min_pips,
                stop_loss_pips=stop_loss_pips,
                risk_reward=risk_reward,
                risk_percent=risk_percent,
                sessions=sessions,
            )
            if isinstance(result, SkipSignal):
                outcome = "SKIPPED"
                detail = result.reason
                log.info("Schedule %s → SKIP (%s)", schedule_id, result.reason)
            else:
                outcome = "SUCCESS"
                detail = f"{pair} {timeframe} {result.direction}"
                signal_id = result.id
                log.info("Schedule %s → %s %s %s", schedule_id, pair, timeframe, result.direction)
                async with AsyncSessionLocal() as db:
                    sig = DBSignal(
                        id=result.id,
                        status=SignalStatus.PENDING,
                        direction=SignalDirection(result.direction),
                        pair=result.pair,
                        timeframe=result.timeframe,
                        entry=result.entry,
                        stop_loss=result.stop_loss,
                        take_profit=result.take_profit,
                        risk_reward=result.risk_reward,
                        confidence=result.confidence,
                        news_bias=NewsBias(result.news_bias) if result.news_bias else None,
                        reason=result.reason,
                        expires_at=result.expires_at,
                        created_at=result.created_at,
                    )
                    db.add(sig)
                    await db.commit()
                if notify:
                    from notifications.telegram import send_signal_alert
                    await send_signal_alert(result)
        except Exception as exc:
            detail = str(exc)
            log.exception("Schedule %s failed", schedule_id)

    completed_at = datetime.now(timezone.utc)
    duration_ms = max(0, int((completed_at - started_at).total_seconds() * 1000))

    # Persist execution audit + update next_run in DB
    async with AsyncSessionLocal() as db:
        db.add(
            DBScheduleExecution(
                schedule_id=schedule_id,
                status=outcome,
                detail=detail,
                signal_id=signal_id,
                started_at=started_at,
                completed_at=completed_at,
                duration_ms=duration_ms,
            )
        )
        sched = await db.get(DBSchedule, schedule_id)
        if sched:
            sched.next_run   = jobs.get_next_run(schedule_id)
            sched.updated_at = datetime.now(timezone.utc)
        await db.commit()

    audit_log.info(
        "run.end schedule_id=%s status=%s duration_ms=%d signal_id=%s detail=%s",
        schedule_id,
        outcome,
        duration_ms,
        signal_id or "-",
        detail or "-",
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_active_schedule(schedule_id: str, db: AsyncSession) -> DBSchedule:
    sched = await db.get(DBSchedule, schedule_id)
    if sched is None:
        raise HTTPException(status_code=404, detail="Schedule not found")
    if sched.status == ScheduleStatus.CANCELED:
        raise HTTPException(status_code=409, detail="Schedule is canceled")
    return sched


async def _sync_next_runs(db: AsyncSession) -> None:
    """Sync next_run from APScheduler into DB for all active schedules."""
    rows = await db.execute(
        select(DBSchedule).where(DBSchedule.status == ScheduleStatus.ACTIVE)
    )
    for sched in rows.scalars().all():
        sched.next_run = jobs.get_next_run(sched.id)
    await db.commit()


def _job_kwargs(sched: DBSchedule) -> dict:
    return {
        "schedule_id":    sched.id,
        "pair":           sched.pair,
        "timeframe":      sched.timeframe,
        "min_pips":       sched.min_pips,
        "stop_loss_pips": sched.stop_loss_pips,
        "risk_reward":    sched.risk_reward,
        "risk_percent":   sched.risk_percent,
        "sessions":       sched.sessions,
        "notify":         sched.notify,
    }


def _to_response(sched: DBSchedule) -> ScheduleResponse:
    return ScheduleResponse(
        id=sched.id,
        status=sched.status.value,
        pair=sched.pair,
        timeframe=sched.timeframe,
        cron=sched.cron,
        min_pips=sched.min_pips,
        stop_loss_pips=sched.stop_loss_pips,
        risk_reward=sched.risk_reward,
        risk_percent=sched.risk_percent,
        notify=sched.notify,
        sessions=sched.sessions,
        next_run=sched.next_run,
        created_at=sched.created_at,
    )


def _to_execution_response(row: DBScheduleExecution) -> ScheduleExecutionResponse:
    return ScheduleExecutionResponse(
        id=row.id,
        schedule_id=row.schedule_id,
        status=row.status,
        detail=row.detail,
        signal_id=row.signal_id,
        started_at=row.started_at,
        completed_at=row.completed_at,
        duration_ms=row.duration_ms,
    )
