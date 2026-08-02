from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, extract
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas import CreateJournalEntryRequest, JournalEntryResponse
from data.store import get_db, JournalEntry as DBJournalEntry, JournalOutcome

router = APIRouter()


@router.post("", status_code=201, response_model=JournalEntryResponse)
async def create_journal_entry(
    req: CreateJournalEntryRequest,
    db: AsyncSession = Depends(get_db),
):
    outcome = JournalOutcome(req.outcome.upper())
    signed_amount = req.amount_usd if outcome == JournalOutcome.WIN else -req.amount_usd

    trade_date = datetime.strptime(req.trade_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)

    entry = DBJournalEntry(
        id=f"jrn_{uuid.uuid4().hex[:10]}",
        pair=req.pair.upper(),
        lot_size=req.lot_size,
        strategy=req.strategy.upper(),
        session=req.session.upper(),
        trade_mode=req.trade_mode.upper(),
        amount_usd=signed_amount,
        outcome=outcome,
        trade_date=trade_date,
        created_at=datetime.now(timezone.utc),
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return _to_response(entry)


@router.get("", response_model=list[JournalEntryResponse])
async def list_journal_entries(
    year: Optional[int] = Query(None),
    month: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    q = select(DBJournalEntry)
    if year is not None:
        q = q.where(extract("year", DBJournalEntry.trade_date) == year)
    if month is not None:
        q = q.where(extract("month", DBJournalEntry.trade_date) == month)
    q = q.order_by(DBJournalEntry.trade_date.asc())

    rows = await db.execute(q)
    return [_to_response(e) for e in rows.scalars().all()]


def _to_response(entry: DBJournalEntry) -> JournalEntryResponse:
    return JournalEntryResponse(
        id=entry.id,
        pair=entry.pair,
        lot_size=entry.lot_size,
        strategy=entry.strategy,
        session=entry.session,
        trade_mode=entry.trade_mode,
        amount_usd=entry.amount_usd,
        outcome=entry.outcome.value,
        trade_date=entry.trade_date,
        created_at=entry.created_at,
    )
