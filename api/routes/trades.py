from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas import TradeResponse, ModifyTradeRequest, CreateTradeRequest
from data.store import get_db, Trade as DBTrade, SignalDirection

router = APIRouter()


# ── POST /trades ──────────────────────────────────────────────────────────────

@router.post("", status_code=status.HTTP_201_CREATED, response_model=TradeResponse)
async def create_trade(req: CreateTradeRequest, db: AsyncSession = Depends(get_db)):
    direction = req.direction.upper()
    if direction not in ("BUY", "SELL"):
        raise HTTPException(status_code=422, detail="direction must be BUY or SELL")

    from execution import trader

    try:
        order = trader.place_order(
            pair=req.pair.upper(),
            direction=direction,
            lot_size=req.lot_size,
            stop_loss=req.stop_loss,
            take_profit=req.take_profit,
            signal_id=f"manual_{uuid.uuid4().hex[:10]}",
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=f"MT5 order failed: {exc}")

    now = datetime.now(timezone.utc)
    trade = DBTrade(
        id=f"trd_{uuid.uuid4().hex[:10]}",
        mt5_ticket=order["ticket"],
        pair=req.pair.upper(),
        direction=SignalDirection(direction),
        entry=order["price"],
        stop_loss=req.stop_loss,
        take_profit=req.take_profit,
        lot_size=req.lot_size,
        open_price=order["price"],
        status="OPEN",
        opened_at=now,
    )
    db.add(trade)
    await db.commit()
    await db.refresh(trade)
    return _to_response(trade)


# ── GET /trades ───────────────────────────────────────────────────────────────

@router.get("", response_model=list[TradeResponse])
async def list_trades(db: AsyncSession = Depends(get_db)):
    rows = await db.execute(
        select(DBTrade).order_by(DBTrade.opened_at.desc()).limit(200)
    )
    return [_to_response(t) for t in rows.scalars().all()]


# ── GET /trades/{id} ──────────────────────────────────────────────────────────

@router.get("/{trade_id}", response_model=TradeResponse)
async def get_trade(trade_id: str, db: AsyncSession = Depends(get_db)):
    trade = await db.get(DBTrade, trade_id)
    if trade is None:
        raise HTTPException(status_code=404, detail="Trade not found")
    return _to_response(trade)


# ── PATCH /trades/{id} ────────────────────────────────────────────────────────

@router.patch("/{trade_id}", response_model=TradeResponse)
async def modify_trade(
    trade_id: str,
    req: ModifyTradeRequest,
    db: AsyncSession = Depends(get_db),
):
    trade = await _get_open_trade(trade_id, db)

    from execution import trader
    try:
        trader.modify_trade(
            ticket=trade.mt5_ticket,
            stop_loss=req.stop_loss,
            take_profit=req.take_profit,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=f"MT5 modify failed: {exc}")

    if req.stop_loss   is not None: trade.stop_loss   = req.stop_loss
    if req.take_profit is not None: trade.take_profit = req.take_profit
    await db.commit()
    await db.refresh(trade)
    return _to_response(trade)


# ── DELETE /trades/{id} ───────────────────────────────────────────────────────

@router.delete("/{trade_id}", status_code=status.HTTP_204_NO_CONTENT)
async def close_trade(trade_id: str, db: AsyncSession = Depends(get_db)):
    trade = await _get_open_trade(trade_id, db)

    from execution import trader
    try:
        result = trader.close_trade(ticket=trade.mt5_ticket)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=f"MT5 close failed: {exc}")

    trade.close_price = result["close_price"]
    trade.status      = "CLOSED"
    trade.closed_at   = datetime.now(timezone.utc)

    from config.settings import pip_size
    ps = pip_size(trade.pair)
    if trade.direction.value == "BUY":
        trade.profit_pips = (result["close_price"] - trade.open_price) / ps
    else:
        trade.profit_pips = (trade.open_price - result["close_price"]) / ps

    await db.commit()


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_open_trade(trade_id: str, db: AsyncSession) -> DBTrade:
    trade = await db.get(DBTrade, trade_id)
    if trade is None:
        raise HTTPException(status_code=404, detail="Trade not found")
    if trade.status != "OPEN":
        raise HTTPException(status_code=409, detail=f"Trade is {trade.status}, not OPEN")
    if trade.mt5_ticket is None:
        raise HTTPException(status_code=409, detail="Trade has no MT5 ticket")
    return trade


def _to_response(trade: DBTrade) -> TradeResponse:
    return TradeResponse(
        id=trade.id,
        mt5_ticket=trade.mt5_ticket,
        pair=trade.pair,
        direction=trade.direction.value,
        entry=trade.entry,
        stop_loss=trade.stop_loss,
        take_profit=trade.take_profit,
        lot_size=trade.lot_size,
        open_price=trade.open_price,
        close_price=trade.close_price,
        profit_pips=trade.profit_pips,
        status=trade.status,
        opened_at=trade.opened_at,
        closed_at=trade.closed_at,
    )
