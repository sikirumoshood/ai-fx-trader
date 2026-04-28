from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas import AnalyzeRequest, SignalResponse, ConfirmResponse, RejectResponse
from data.store import (
    get_db, Signal as DBSignal, Trade as DBTrade,
    SignalStatus, SignalDirection, NewsBias,
)
from config.settings import DEFAULT_RISK_PERCENT, DEFAULT_STOP_LOSS_PIPS
from signals.engine import SignalEngine, SkipSignal
from signals.risk import calculate_lot_size
from data.fetcher import get_account_balance

router = APIRouter()


# ── Dependency: signal engine from app state ──────────────────────────────────

def _engine(request: Request) -> SignalEngine:
    engine: Optional[SignalEngine] = getattr(request.app.state, "signal_engine", None)
    if engine is None:
        raise HTTPException(status_code=503, detail="Signal engine not initialised")
    return engine


# ── POST /signals/analyze ─────────────────────────────────────────────────────

@router.post("/analyze", status_code=status.HTTP_201_CREATED, response_model=SignalResponse)
async def analyze(
    req: AnalyzeRequest,
    db: AsyncSession = Depends(get_db),
    engine: SignalEngine = Depends(_engine),
):
    result = await engine.generate(
        pair=req.pair.upper(),
        timeframe=req.timeframe.upper(),
        min_pips=req.min_pips,
        stop_loss_pips=req.stop_loss_pips,
        risk_reward=req.risk_reward,
        risk_percent=req.risk_percent,
        sessions=req.sessions if req.sessions else None,
    )

    if isinstance(result, SkipSignal):
        raise HTTPException(
            status_code=status.HTTP_200_OK,
            detail={"signal": "SKIP", "pair": result.pair, "reason": result.reason},
        )

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
    await db.refresh(sig)

    return _to_response(sig)


# ── GET /signals ──────────────────────────────────────────────────────────────

@router.get("", response_model=list[SignalResponse])
async def list_signals(db: AsyncSession = Depends(get_db)):
    await _expire_pending(db)
    rows = await db.execute(
        select(DBSignal).order_by(DBSignal.created_at.desc()).limit(100)
    )
    return [_to_response(s) for s in rows.scalars().all()]


# ── GET /signals/{id} ─────────────────────────────────────────────────────────

@router.get("/{signal_id}", response_model=SignalResponse)
async def get_signal(signal_id: str, db: AsyncSession = Depends(get_db)):
    await _expire_pending(db)
    sig = await db.get(DBSignal, signal_id)
    if sig is None:
        raise HTTPException(status_code=404, detail="Signal not found")
    return _to_response(sig)


# ── POST /signals/{id}/confirm ────────────────────────────────────────────────

@router.post("/{signal_id}/confirm", response_model=ConfirmResponse)
async def confirm_signal(signal_id: str, db: AsyncSession = Depends(get_db)):
    sig = await _get_pending(signal_id, db)

    balance  = get_account_balance() or 10_000.0
    lot_size = calculate_lot_size(
        account_balance=balance,
        risk_percent=DEFAULT_RISK_PERCENT,
        stop_loss_pips=DEFAULT_STOP_LOSS_PIPS,
        pair=sig.pair,
    )

    from execution import trader
    try:
        order = trader.place_order(
            pair=sig.pair,
            direction=sig.direction.value,
            lot_size=lot_size,
            stop_loss=sig.stop_loss,
            take_profit=sig.take_profit,
            signal_id=sig.id,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=f"MT5 order failed: {exc}")

    now      = datetime.now(timezone.utc)
    trade_id = f"trd_{uuid.uuid4().hex[:10]}"

    trade = DBTrade(
        id=trade_id,
        mt5_ticket=order["ticket"],
        pair=sig.pair,
        direction=sig.direction,
        entry=sig.entry,
        stop_loss=sig.stop_loss,
        take_profit=sig.take_profit,
        lot_size=lot_size,
        open_price=order["price"],
        status="OPEN",
        opened_at=now,
    )
    db.add(trade)

    sig.status      = SignalStatus.EXECUTED
    sig.executed_at = now
    sig.trade_id    = trade_id

    await db.commit()
    return ConfirmResponse(id=sig.id, status="EXECUTED", trade_id=trade_id, executed_at=now)


# ── POST /signals/{id}/reject ─────────────────────────────────────────────────

@router.post("/{signal_id}/reject", response_model=RejectResponse)
async def reject_signal(signal_id: str, db: AsyncSession = Depends(get_db)):
    sig = await _get_pending(signal_id, db)
    sig.status = SignalStatus.REJECTED
    await db.commit()
    return RejectResponse(id=sig.id, status="REJECTED")


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_pending(signal_id: str, db: AsyncSession) -> DBSignal:
    await _expire_pending(db)
    sig = await db.get(DBSignal, signal_id)
    if sig is None:
        raise HTTPException(status_code=404, detail="Signal not found")
    if sig.status != SignalStatus.PENDING:
        raise HTTPException(status_code=409, detail=f"Signal is {sig.status.value}, not PENDING")
    return sig


async def _expire_pending(db: AsyncSession) -> None:
    now = datetime.now(timezone.utc)
    rows = await db.execute(
        select(DBSignal).where(
            DBSignal.status == SignalStatus.PENDING,
            DBSignal.expires_at < now,
        )
    )
    for sig in rows.scalars().all():
        sig.status = SignalStatus.EXPIRED
    await db.commit()


def _to_response(sig: DBSignal) -> SignalResponse:
    return SignalResponse(
        id=sig.id,
        status=sig.status.value,
        expires_at=sig.expires_at,
        signal=sig.direction.value,
        entry=sig.entry,
        stop_loss=sig.stop_loss,
        take_profit=sig.take_profit,
        risk_reward=sig.risk_reward,
        confidence=sig.confidence,
        news_bias=sig.news_bias.value if sig.news_bias else None,
        reason=sig.reason,
        pair=sig.pair,
        timeframe=sig.timeframe,
        created_at=sig.created_at,
    )
