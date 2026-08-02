from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from datetime import timedelta
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
from signals.fvg import FVGSignalEngine, SkipSignal

router = APIRouter()

_TF_MINUTES: dict[str, int] = {
    "M1": 1, "M5": 5, "M15": 15, "M30": 30,
    "H1": 60, "H4": 240, "D1": 1440, "W1": 10080,
}

def _tf_window_minutes(timeframe: str) -> int:
    return _TF_MINUTES.get(timeframe.upper(), 60)

# Per-pair lock: prevents concurrent schedules for the same pair from both
# passing the dedup check before either has committed a trade to the DB.
_pair_execution_locks: dict[str, asyncio.Lock] = {}

def _pair_lock(pair: str) -> asyncio.Lock:
    if pair not in _pair_execution_locks:
        _pair_execution_locks[pair] = asyncio.Lock()
    return _pair_execution_locks[pair]


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
            "schedule_id":              schedule_id,
            "pair":                     req.pair.upper(),
            "timeframe":                req.timeframe.upper(),
            "indicator":                req.indicator,
            "min_pips":                 req.min_pips,
            "stop_loss_pips":           req.stop_loss_pips,
            "risk_reward":              req.risk_reward,
            "risk_percent":             req.risk_percent,
            "sessions":                 req.sessions or None,
            "notify":                   req.notify,
            "notify_email":             req.notify_email or None,
            "ifvg_threshold":           req.ifvg_threshold,
            "auto_execute":             req.auto_execute,
            "auto_lot_size":            req.auto_lot_size,
            "max_risk_amount":          req.max_risk_amount,
            "auto_close_profit":        req.auto_close_profit,
            "auto_close_profit_amount": req.auto_close_profit_amount,
        },
    )

    sched = DBSchedule(
        id=schedule_id,
        pair=req.pair.upper(),
        timeframe=req.timeframe.upper(),
        cron=req.cron,
        indicator=req.indicator,
        min_pips=req.min_pips,
        stop_loss_pips=req.stop_loss_pips,
        risk_reward=req.risk_reward,
        risk_percent=req.risk_percent,
        notify=req.notify,
        notify_email=req.notify_email or None,
        sessions=req.sessions or None,
        ifvg_threshold=req.ifvg_threshold,
        auto_execute=req.auto_execute,
        auto_lot_size=req.auto_lot_size,
        max_risk_amount=req.max_risk_amount,
        auto_close_profit=req.auto_close_profit,
        auto_close_profit_amount=req.auto_close_profit_amount,
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
    if req.notify_email is not None:
        sched.notify_email = req.notify_email or None
        should_refresh_job = True
    if req.sessions is not None:
        sched.sessions = req.sessions or None
        should_refresh_job = True
    if req.ifvg_threshold is not None:
        sched.ifvg_threshold = req.ifvg_threshold
        should_refresh_job = True
    if req.auto_execute is not None:
        sched.auto_execute = req.auto_execute
        should_refresh_job = True
    if req.auto_lot_size is not None:
        sched.auto_lot_size = req.auto_lot_size
        should_refresh_job = True
    if req.max_risk_amount is not None:
        sched.max_risk_amount = req.max_risk_amount
        should_refresh_job = True
    if req.auto_close_profit is not None:
        sched.auto_close_profit = req.auto_close_profit
        should_refresh_job = True
    if req.auto_close_profit_amount is not None:
        sched.auto_close_profit_amount = req.auto_close_profit_amount
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
    indicator: str = "ifvg",
    sessions: list[str] | None = None,
    notify: bool = False,
    notify_email: str | None = None,
    ifvg_threshold: float = 0.0,
    auto_execute: bool = False,
    auto_lot_size: float | None = None,
    max_risk_amount: float | None = None,
    auto_close_profit: bool = False,
    auto_close_profit_amount: float | None = None,
) -> None:
    """Called by APScheduler on each cron tick."""
    import logging

    log = logging.getLogger(__name__)
    audit_log = logging.getLogger("schedule.execution")
    started_at = datetime.now(timezone.utc)
    outcome = "FAILED"
    detail: str | None = None
    signal_id: str | None = None

    audit_log.info(
        "run.start schedule_id=%s pair=%s timeframe=%s indicator=%s cron_tick=%s",
        schedule_id,
        pair,
        timeframe,
        indicator,
        started_at.isoformat(),
    )

    try:
        fvg_engine = FVGSignalEngine()
        result = await fvg_engine.generate(
            pair=pair,
            timeframe=timeframe,
            stop_loss_pips=stop_loss_pips,
            risk_reward=risk_reward,
            risk_percent=risk_percent,
            threshold=ifvg_threshold,
            sessions=sessions,
        )
    except Exception as exc:
        detail = str(exc)
        log.exception("Schedule %s failed during engine dispatch", schedule_id)
        result = None

    if result is not None:
        try:
            if isinstance(result, SkipSignal):
                outcome = getattr(result, "code", "SKIPPED")
                detail = result.reason
                log.info("Schedule %s → %s (%s)", schedule_id, outcome, result.reason)
            else:
                async with _pair_lock(pair):
                    # Dedup: skip if a signal for this pair+timeframe already exists within the TF window.
                    # Lock ensures concurrent schedules for the same pair are serialized so the
                    # check-then-act is atomic — prevents all of them passing before any commits.
                    is_duplicate = False
                    window_minutes = _tf_window_minutes(timeframe)
                    window_start = started_at - timedelta(minutes=window_minutes)
                    async with AsyncSessionLocal() as check_db:
                        existing = await check_db.execute(
                            select(DBSignal)
                            .where(
                                DBSignal.pair == pair,
                                DBSignal.timeframe == timeframe,
                                DBSignal.created_at >= window_start,
                                DBSignal.status.in_([SignalStatus.PENDING, SignalStatus.EXECUTED]),
                            )
                            .limit(1)
                        )
                        if existing.scalar_one_or_none() is not None:
                            is_duplicate = True
                            outcome = "SKIPPED"
                            detail = f"Duplicate signal within {window_minutes}m TF window"
                            log.info("Schedule %s → SKIP (duplicate within %dm)", schedule_id, window_minutes)

                    if not is_duplicate:
                        outcome = "SUCCESS"
                        detail = f"{pair} {timeframe} {result.direction}"
                        log.info("Schedule %s → %s %s %s", schedule_id, pair, timeframe, result.direction)

                        if auto_execute:
                            saved_id = await _auto_execute_signal(
                                result=result,
                                risk_percent=risk_percent,
                                auto_lot_size=auto_lot_size,
                                max_risk_amount=max_risk_amount,
                                auto_close_profit=auto_close_profit,
                                auto_close_profit_amount=auto_close_profit_amount,
                                risk_reward=risk_reward,
                                schedule_id=schedule_id,
                                notify_email=notify_email,
                                log=log,
                            )
                            if saved_id is None:
                                # Guard tripped (duplicate pending or position limit) — downgrade to SKIPPED
                                outcome = "SKIPPED"
                                detail = f"{pair} {timeframe} {result.direction} — blocked by open position/pending order limit"
                            signal_id = saved_id
                        else:
                            async with AsyncSessionLocal() as db:
                                sig = DBSignal(
                                    id=result.id,
                                    status=SignalStatus.PENDING,
                                    direction=SignalDirection(result.direction),
                                    pair=result.pair,
                                    timeframe=result.timeframe,
                                    entry=result.entry,
                                    order_type=result.order_type,
                                    stop_loss=stop_loss,
                                    take_profit=result.take_profit,
                                    risk_reward=result.risk_reward,
                                    confidence=result.confidence,
                                    news_bias=NewsBias(result.news_bias) if result.news_bias else None,
                                    rsi=result.rsi_value,
                                    rsi_advisory=result.rsi_advisory,
                                    pattern_name=result.pattern_name,
                                    pattern_bias=result.pattern_bias,
                                    reason=result.reason,
                                    expires_at=result.expires_at,
                                    created_at=result.created_at,
                                )
                                db.add(sig)
                                await db.commit()
                            signal_id = result.id

                            if notify:
                                from notifications.telegram import send_signal_alert
                                await send_signal_alert(result)
                            if notify_email:
                                from notifications.email import send_signal_email
                                await send_signal_email(result, notify_email)
        except Exception as exc:
            detail = str(exc)
            signal_id = None  # signal may not have been committed — don't reference it
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


# ── Auto-execution helper ─────────────────────────────────────────────────────

async def _auto_execute_signal(
    result,
    risk_percent: float,
    auto_lot_size: float | None,
    max_risk_amount: float | None,
    schedule_id: str,
    log,
    notify_email: str | None = None,
    auto_close_profit: bool = False,
    auto_close_profit_amount: float | None = None,
    risk_reward: float = 1.0,
) -> str | None:
    """Place MT5 order and save signal. Returns signal_id if committed, None if skipped."""
    import uuid as _uuid
    from data.store import Trade as DBTrade
    from config.settings import DEFAULT_LOT_SIZE, pip_size, price_decimals
    from signals.risk import calculate_lot_size, calculate_lot_size_from_amount, _live_pip_value_per_lot, _PIP_VALUE_PER_LOT, _DEFAULT_PIP_VALUE
    from execution import trader

    now = datetime.now(timezone.utc)

    # For limit orders: skip if a pending (unfilled) limit order already exists on
    # MT5 for this pair. Check MT5 directly — not the DB — so stale DB records
    # never block new trades.
    if getattr(result, "order_type", "MARKET") == "LIMIT":
        try:
            pending_on_mt5 = trader.get_pending_orders(pair=result.pair)
            if pending_on_mt5:
                log.info(
                    "Schedule %s: %d pending limit order(s) already on MT5 for %s — skipping",
                    schedule_id, len(pending_on_mt5), result.pair,
                )
                return None
        except Exception as exc:
            log.warning("Schedule %s: could not check MT5 pending orders: %s", schedule_id, exc)

    # Hard stop: never place more than 2 open positions per pair at any time.
    try:
        open_positions = trader.get_open_positions(pair=result.pair)
        if len(open_positions) >= 2:
            log.info(
                "Schedule %s: %d open position(s) already exist for %s — skipping",
                schedule_id, len(open_positions), result.pair,
            )
            return None
    except Exception as exc:
        log.warning("Schedule %s: could not check open positions: %s", schedule_id, exc)

    if auto_lot_size is not None:
        lot_size = auto_lot_size
    elif max_risk_amount is not None and result.stop_loss is not None:
        try:
            sl_pips = abs(result.entry - result.stop_loss) / pip_size(result.pair)
            lot_size = calculate_lot_size_from_amount(max_risk_amount, sl_pips, result.pair)
        except Exception:
            lot_size = DEFAULT_LOT_SIZE
    else:
        try:
            from data import fetcher
            balance = fetcher.get_account_balance() or 0.0
            if balance > 0 and result.stop_loss is not None:
                sl_pips = abs(result.entry - result.stop_loss) / pip_size(result.pair)
                lot_size = calculate_lot_size(balance, risk_percent, sl_pips, result.pair)
            else:
                lot_size = DEFAULT_LOT_SIZE
        except Exception:
            lot_size = DEFAULT_LOT_SIZE

    # Recompute TP and SL in dollar terms when auto_close_profit is active.
    take_profit = result.take_profit
    stop_loss   = result.stop_loss
    if auto_close_profit and auto_close_profit_amount and lot_size > 0:
        try:
            pip_val  = _live_pip_value_per_lot(result.pair) or _PIP_VALUE_PER_LOT.get(result.pair.upper(), _DEFAULT_PIP_VALUE)
            ps       = pip_size(result.pair)
            decimals = price_decimals(result.pair)

            tp_pips = auto_close_profit_amount / (pip_val * lot_size)
            if result.direction == "BUY":
                take_profit = round(result.entry + tp_pips * ps, decimals)
            else:
                take_profit = round(result.entry - tp_pips * ps, decimals)
            log.info(
                "Schedule %s auto_close_profit: target=$%.2f lot=%.2f pip_val=%.4f → TP=%s (%.1f pips)",
                schedule_id, auto_close_profit_amount, lot_size, pip_val, take_profit, tp_pips,
            )

            effective_risk = max_risk_amount if max_risk_amount else auto_close_profit_amount / max(risk_reward, 0.1)
            sl_pips = effective_risk / (pip_val * lot_size)
            if result.direction == "BUY":
                stop_loss = round(result.entry - sl_pips * ps, decimals)
            else:
                stop_loss = round(result.entry + sl_pips * ps, decimals)
            source = "max_risk_amount" if max_risk_amount else f"TP/R:R ({auto_close_profit_amount}/{risk_reward})"
            log.info(
                "Schedule %s auto_close_profit SL: risk=$%.2f (from %s) lot=%.2f → SL=%s (%.1f pips)",
                schedule_id, effective_risk, source, lot_size, stop_loss, sl_pips,
            )
        except Exception as exc:
            log.warning("Schedule %s: could not recompute TP/SL for auto_close_profit: %s", schedule_id, exc)

    # Place 2 orders per signal
    orders: list[dict] = []
    for _ in range(2):
        try:
            if getattr(result, "order_type", "MARKET") == "LIMIT":
                order = trader.place_pending_order(
                    pair=result.pair,
                    direction=result.direction,
                    order_type="LIMIT",
                    entry=result.entry,
                    lot_size=lot_size,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    signal_id=result.id,
                )
            else:
                order = trader.place_order(
                    pair=result.pair,
                    direction=result.direction,
                    lot_size=lot_size,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    signal_id=result.id,
                )
            orders.append(order)
            log.info("Schedule %s auto-executed → ticket=%s lot=%.2f", schedule_id, order["ticket"], lot_size)
        except Exception as exc:
            log.error("Schedule %s auto-execution order failed: %s", schedule_id, exc)

    # Pre-generate trade IDs so Signal.trade_id and Trade.id reference the same value.
    trade_ids = [f"trd_{_uuid.uuid4().hex[:10]}" for _ in orders]

    if orders and notify_email:
        from notifications.email import send_signal_email
        await send_signal_email(result, notify_email)

    async with AsyncSessionLocal() as db:
        # Insert signal with trade_id=None first to break the circular FK:
        # signals.trade_id → trades.id  and  trades.signal_id → signals.id
        sig = DBSignal(
            id=result.id,
            status=SignalStatus.EXECUTED if orders else SignalStatus.PENDING,
            direction=SignalDirection(result.direction),
            pair=result.pair,
            timeframe=result.timeframe,
            entry=result.entry,
            order_type=result.order_type,
            stop_loss=stop_loss,
            take_profit=take_profit,
            risk_reward=result.risk_reward,
            confidence=result.confidence,
            news_bias=NewsBias(result.news_bias) if result.news_bias else None,
            rsi=result.rsi_value,
            rsi_advisory=result.rsi_advisory,
            pattern_name=result.pattern_name,
            pattern_bias=result.pattern_bias,
            reason=result.reason,
            expires_at=result.expires_at,
            created_at=result.created_at,
            executed_at=now if orders else None,
            trade_id=None,
        )
        db.add(sig)
        await db.flush()  # signal row now exists — trades can safely reference it

        for i, (order, trade_id) in enumerate(zip(orders, trade_ids)):
            db.add(DBTrade(
                id=trade_id,
                signal_id=result.id,
                stack_index=i,
                mt5_ticket=order["ticket"],
                pair=result.pair,
                direction=SignalDirection(result.direction),
                order_type=result.order_type,
                entry=result.entry,
                stop_loss=result.stop_loss,
                take_profit=take_profit,
                lot_size=lot_size,
                open_price=order["price"],
                status="EXECUTED",
                opened_at=now,
            ))

        await db.flush()  # trades now exist — safe to set signal.trade_id
        sig.trade_id = trade_ids[0] if trade_ids else None
        await db.commit()

    return result.id if orders else None


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
        "schedule_id":              sched.id,
        "pair":                     sched.pair,
        "timeframe":                sched.timeframe,
        "indicator":                sched.indicator,
        "min_pips":                 sched.min_pips,
        "stop_loss_pips":           sched.stop_loss_pips,
        "risk_reward":              sched.risk_reward,
        "risk_percent":             sched.risk_percent,
        "sessions":                 sched.sessions,
        "notify":                   sched.notify,
        "notify_email":             sched.notify_email,
        "ifvg_threshold":           sched.ifvg_threshold or 0.0,
        "auto_execute":             sched.auto_execute or False,
        "auto_lot_size":            sched.auto_lot_size,
        "max_risk_amount":          sched.max_risk_amount,
        "auto_close_profit":        sched.auto_close_profit or False,
        "auto_close_profit_amount": sched.auto_close_profit_amount,
    }


def _to_response(sched: DBSchedule) -> ScheduleResponse:
    return ScheduleResponse(
        id=sched.id,
        status=sched.status.value,
        pair=sched.pair,
        timeframe=sched.timeframe,
        cron=sched.cron,
        indicator=sched.indicator or "ifvg",
        min_pips=sched.min_pips,
        stop_loss_pips=sched.stop_loss_pips,
        risk_reward=sched.risk_reward,
        risk_percent=sched.risk_percent,
        notify=sched.notify,
        notify_email=sched.notify_email,
        sessions=sched.sessions,
        ifvg_threshold=sched.ifvg_threshold or 0.0,
        auto_execute=sched.auto_execute or False,
        auto_lot_size=sched.auto_lot_size,
        max_risk_amount=sched.max_risk_amount,
        auto_close_profit=sched.auto_close_profit or False,
        auto_close_profit_amount=sched.auto_close_profit_amount,
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
