from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas import SignalResponse, ConfirmRequest, ConfirmResponse, RejectResponse
from data.store import (
    get_db, Signal as DBSignal, Trade as DBTrade,
    SignalStatus, SignalDirection, NewsBias,
)
from config.settings import DEFAULT_LOT_SIZE, DEFAULT_RISK_PERCENT, pip_size
from signals.risk import calculate_lot_size

log = logging.getLogger(__name__)

router = APIRouter()


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
async def confirm_signal(
    signal_id: str,
    req: ConfirmRequest = Body(default=ConfirmRequest()),
    db: AsyncSession = Depends(get_db),
):
    sig = await _get_pending(signal_id, db)

    if req.lot_size is not None:
        per_trade_lots = req.lot_size
    else:
        from data import fetcher
        balance = fetcher.get_account_balance() or 0.0
        if balance > 0 and sig.stop_loss is not None:
            sl_pips = abs(sig.entry - sig.stop_loss) / pip_size(sig.pair)
            per_trade_lots = calculate_lot_size(balance, DEFAULT_RISK_PERCENT, sl_pips, sig.pair)
        else:
            per_trade_lots = DEFAULT_LOT_SIZE

    from execution import trader
    now = datetime.now(timezone.utc)

    # Phase 1: place all MT5 orders up front, collecting results as plain dicts.
    # No DB writes happen here so a placement failure never leaves a partial DB state.
    placed: list[dict] = []
    sig_snap = {
        "id":          sig.id,
        "pair":        sig.pair,
        "direction":   sig.direction,
        "order_type":  sig.order_type,
        "entry":       sig.entry,
        "stop_loss":   req.stop_loss   if req.stop_loss   is not None else sig.stop_loss,
        "take_profit": req.take_profit if req.take_profit is not None else sig.take_profit,
    }

    for i in range(req.stack_count):
        try:
            if sig_snap["order_type"] == "LIMIT":
                order = trader.place_pending_order(
                    pair=sig_snap["pair"],
                    direction=sig_snap["direction"].value,
                    order_type="LIMIT",
                    entry=sig_snap["entry"],
                    lot_size=per_trade_lots,
                    stop_loss=sig_snap["stop_loss"],
                    take_profit=sig_snap["take_profit"],
                    signal_id=sig_snap["id"],
                )
            else:
                order = trader.place_order(
                    pair=sig_snap["pair"],
                    direction=sig_snap["direction"].value,
                    lot_size=per_trade_lots,
                    stop_loss=sig_snap["stop_loss"],
                    take_profit=sig_snap["take_profit"],
                    signal_id=sig_snap["id"],
                )
        except RuntimeError as exc:
            if not placed:
                raise HTTPException(status_code=502, detail=f"MT5 order failed: {exc}")
            # Partial stack — some trades placed; stop here and persist what succeeded.
            break

        placed.append({
            "trade_id":    f"trd_{uuid.uuid4().hex[:10]}",
            "stack_index": i,
            "mt5_ticket":  order["ticket"],
            "open_price":  order["price"],
        })

    trade_ids = [o["trade_id"] for o in placed]

    # Phase 2: persist — retry once on transient DB failure.
    # Trades are already LIVE on MT5 at this point; losing the DB record would
    # create a ghost trade with no local tracking.
    async def _write(session: AsyncSession) -> None:
        s = await session.get(DBSignal, sig_snap["id"])
        for o in placed:
            session.add(DBTrade(
                id=o["trade_id"],
                signal_id=sig_snap["id"],
                stack_index=o["stack_index"],
                mt5_ticket=o["mt5_ticket"],
                pair=sig_snap["pair"],
                direction=sig_snap["direction"],
                order_type=sig_snap["order_type"],
                entry=sig_snap["entry"],
                stop_loss=sig_snap["stop_loss"],
                take_profit=sig_snap["take_profit"],
                lot_size=per_trade_lots,
                open_price=o["open_price"],
                status="OPEN",
                opened_at=now,
            ))
        s.status      = SignalStatus.EXECUTED
        s.executed_at = now
        s.trade_id    = trade_ids[0]
        await session.commit()

    try:
        await _write(db)
    except Exception:
        await db.rollback()
        try:
            await _write(db)
        except Exception:
            log.critical(
                "CRITICAL: MT5 trades LIVE but DB write failed twice. "
                "signal_id=%s mt5_tickets=%s",
                sig_snap["id"], [o["mt5_ticket"] for o in placed],
            )
            raise HTTPException(
                status_code=500,
                detail={
                    "error": "Trades placed on MT5 but could not be recorded — they are LIVE.",
                    "mt5_tickets": [o["mt5_ticket"] for o in placed],
                    "signal_id": sig_snap["id"],
                },
            )

    return ConfirmResponse(
        id=sig_snap["id"],
        status="EXECUTED",
        trade_ids=trade_ids,
        stack_count=len(trade_ids),
        executed_at=now,
    )


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
        order_type=sig.order_type or "MARKET",
        entry=sig.entry,
        stop_loss=sig.stop_loss,
        take_profit=sig.take_profit,
        risk_reward=sig.risk_reward,
        confidence=sig.confidence,
        news_bias=sig.news_bias.value if sig.news_bias else None,
        rsi=sig.rsi,
        rsi_advisory=sig.rsi_advisory,
        pattern_name=sig.pattern_name,
        pattern_bias=sig.pattern_bias,
        reason=sig.reason,
        pair=sig.pair,
        timeframe=sig.timeframe,
        created_at=sig.created_at,
    )
