from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas import (
    HealthResponse, PairsResponse,
    BacktestRequest, BacktestJobResponse, BacktestStatusResponse, BacktestResultsResponse,
)
from config.settings import SUPPORTED_PAIRS
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from data.store import get_db, BacktestRun, BacktestStatus, BacktestMetric

router = APIRouter(tags=["System"])


# ── GET /health ───────────────────────────────────────────────────────────────

@router.get("/health", response_model=HealthResponse)
async def health(request: Request, db: AsyncSession = Depends(get_db)):
    # MT5
    try:
        from data.fetcher import is_connected
        mt5_ok = is_connected()
    except Exception:
        mt5_ok = False

    # Model
    engine = getattr(request.app.state, "signal_engine", None)
    model_ok = engine is not None and engine.predictor.is_loaded()

    # DB
    try:
        await db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False

    overall = "ok" if (mt5_ok and db_ok) else "degraded"
    return HealthResponse(
        status=overall,
        mt5_connected=mt5_ok,
        model_loaded=model_ok,
        db_connected=db_ok,
        timestamp=datetime.now(timezone.utc),
    )


# ── GET /pairs ────────────────────────────────────────────────────────────────

@router.get("/pairs", response_model=PairsResponse)
async def pairs():
    return PairsResponse(pairs=SUPPORTED_PAIRS)


# ── GET /backtests ────────────────────────────────────────────────────────────

@router.get("/backtests", response_model=list[BacktestStatusResponse])
async def list_backtests(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(BacktestRun)
        .options(selectinload(BacktestRun.metrics))
        .order_by(BacktestRun.created_at.desc())
        .limit(50)
    )
    runs = result.scalars().all()
    out = []
    for r in runs:
        m = r.metrics
        out.append(BacktestStatusResponse(
            job_id=r.id,
            status=r.status.value,
            created_at=r.created_at,
            completed_at=r.completed_at,
            error=r.error,
            pair=r.pair,
            timeframe=r.timeframe,
            start_date=r.start_date,
            end_date=r.end_date,
            min_pips=r.min_pips,
            stop_loss_pips=r.stop_loss_pips,
            risk_reward=r.risk_reward,
            risk_percent=r.risk_percent,
            initial_balance=r.initial_balance,
            sessions=r.sessions,
            traded=m.traded if m else None,
            win_rate=m.win_rate if m else None,
            total_pips=m.total_return if m else None,
            profit_factor=m.profit_factor if m else None,
            max_drawdown=m.max_drawdown if m else None,
            sharpe_ratio=m.sharpe_ratio if m else None,
        ))
    return out


# ── POST /backtest ────────────────────────────────────────────────────────────

@router.post("/backtest", status_code=status.HTTP_202_ACCEPTED, response_model=BacktestJobResponse)
async def submit_backtest(
    req: BacktestRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    from datetime import date
    from backtest.runner import submit_run

    engine = getattr(request.app.state, "signal_engine", None)
    if engine is None:
        raise HTTPException(status_code=503, detail="Signal engine not initialised")

    try:
        start = datetime.strptime(req.start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        end   = datetime.strptime(req.end_date,   "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        raise HTTPException(status_code=422, detail="Dates must be YYYY-MM-DD")

    if start >= end:
        raise HTTPException(status_code=422, detail="start_date must be before end_date")

    run_id = await submit_run(
        pair=req.pair.upper(),
        timeframe=req.timeframe.upper(),
        start_date=start,
        end_date=end,
        min_pips=req.min_pips,
        stop_loss_pips=req.stop_loss_pips,
        risk_reward=req.risk_reward,
        risk_percent=req.risk_percent,
        initial_balance=req.initial_balance,
        predictor=engine.predictor,
        sessions=req.sessions if req.sessions else None,
    )

    run = await db.get(BacktestRun, run_id)
    return BacktestJobResponse(job_id=run_id, status="QUEUED", created_at=run.created_at)


# ── GET /backtest/{job_id} ────────────────────────────────────────────────────

@router.get("/backtest/{job_id}", response_model=BacktestStatusResponse)
async def backtest_status(job_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(BacktestRun)
        .options(selectinload(BacktestRun.metrics))
        .where(BacktestRun.id == job_id)
    )
    run = result.scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail="Backtest job not found")
    m = run.metrics
    return BacktestStatusResponse(
        job_id=run.id,
        status=run.status.value,
        created_at=run.created_at,
        completed_at=run.completed_at,
        error=run.error,
        pair=run.pair,
        timeframe=run.timeframe,
        start_date=run.start_date,
        end_date=run.end_date,
        min_pips=run.min_pips,
        stop_loss_pips=run.stop_loss_pips,
        risk_reward=run.risk_reward,
        risk_percent=run.risk_percent,
        initial_balance=run.initial_balance,
        sessions=run.sessions,
        traded=m.traded if m else None,
        win_rate=m.win_rate if m else None,
        total_pips=m.total_return if m else None,
        profit_factor=m.profit_factor if m else None,
        max_drawdown=m.max_drawdown if m else None,
        sharpe_ratio=m.sharpe_ratio if m else None,
    )


# ── GET /backtest/{job_id}/results ────────────────────────────────────────────

@router.get("/backtest/{job_id}/results", response_model=BacktestResultsResponse)
async def backtest_results(job_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(BacktestRun)
        .where(BacktestRun.id == job_id)
        .options(selectinload(BacktestRun.metrics))
    )
    run = result.scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail="Backtest job not found")
    if run.status != BacktestStatus.DONE:
        raise HTTPException(
            status_code=409,
            detail=f"Backtest is {run.status.value}, not DONE",
        )

    m = run.metrics
    if m is None:
        raise HTTPException(status_code=404, detail="Metrics not found")

    return BacktestResultsResponse(
        job_id=job_id,
        summary={
            "total_signals":   m.total_signals,
            "skipped":         m.skipped,
            "traded":          m.traded,
            "win_rate":        f"{m.win_rate * 100:.1f}%",
            "profit_factor":   m.profit_factor,
            "sharpe_ratio":    m.sharpe_ratio,
            "max_drawdown":    f"{m.max_drawdown:.1f} pips",
            "total_return_pips": m.total_return,
            "directional_acc": f"{m.directional_acc * 100:.1f}%",
        },
        by_session=m.by_session,
        by_confidence=m.by_confidence,
        by_news_impact=m.by_news_impact,
        equity_curve=m.equity_curve,
    )
