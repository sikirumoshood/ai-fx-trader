from __future__ import annotations

from datetime import datetime, timezone
from typing import AsyncGenerator

from sqlalchemy import (
    BigInteger, Boolean, Column, DateTime, Float, Integer,
    String, Text, JSON, ForeignKey, Enum as SAEnum,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, relationship
import enum

from config.settings import DATABASE_URL


# ── Engine & session factory ──────────────────────────────────────────────────

engine = create_async_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


# ── Base ──────────────────────────────────────────────────────────────────────

class Base(DeclarativeBase):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ── Enums ─────────────────────────────────────────────────────────────────────

class SignalStatus(str, enum.Enum):
    PENDING  = "PENDING"
    EXECUTED = "EXECUTED"
    REJECTED = "REJECTED"
    EXPIRED  = "EXPIRED"

class SignalDirection(str, enum.Enum):
    BUY  = "BUY"
    SELL = "SELL"
    SKIP = "SKIP"

class NewsBias(str, enum.Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"

class ScheduleStatus(str, enum.Enum):
    ACTIVE   = "ACTIVE"
    PAUSED   = "PAUSED"
    CANCELED = "CANCELED"

class BacktestStatus(str, enum.Enum):
    QUEUED  = "QUEUED"
    RUNNING = "RUNNING"
    DONE    = "DONE"
    FAILED  = "FAILED"


# ── Models ────────────────────────────────────────────────────────────────────

class Signal(Base):
    __tablename__ = "signals"

    id          = Column(String, primary_key=True)
    status      = Column(SAEnum(SignalStatus), nullable=False, default=SignalStatus.PENDING)
    direction   = Column(SAEnum(SignalDirection), nullable=False)
    pair        = Column(String(12), nullable=False)
    timeframe   = Column(String(8), nullable=False)
    entry       = Column(Float, nullable=False)
    stop_loss   = Column(Float, nullable=False)
    take_profit = Column(Float, nullable=False)
    risk_reward = Column(Float, nullable=False)
    confidence  = Column(Float, nullable=False)
    news_bias   = Column(SAEnum(NewsBias), nullable=True)
    reason      = Column(Text, nullable=True)
    expires_at  = Column(DateTime(timezone=True), nullable=False)
    created_at  = Column(DateTime(timezone=True), default=_now, nullable=False)
    executed_at = Column(DateTime(timezone=True), nullable=True)
    trade_id    = Column(String, ForeignKey("trades.id"), nullable=True)

    trade = relationship("Trade", back_populates="signal", uselist=False)


class Trade(Base):
    __tablename__ = "trades"

    id          = Column(String, primary_key=True)
    mt5_ticket  = Column(BigInteger, nullable=True)
    pair        = Column(String(12), nullable=False)
    direction   = Column(SAEnum(SignalDirection), nullable=False)
    entry       = Column(Float, nullable=False)
    stop_loss   = Column(Float, nullable=True)
    take_profit = Column(Float, nullable=True)
    lot_size    = Column(Float, nullable=True)
    open_price  = Column(Float, nullable=True)
    close_price = Column(Float, nullable=True)
    profit_pips = Column(Float, nullable=True)
    status      = Column(String(16), nullable=False, default="OPEN")
    opened_at   = Column(DateTime(timezone=True), default=_now, nullable=False)
    closed_at   = Column(DateTime(timezone=True), nullable=True)

    signal = relationship("Signal", back_populates="trade", uselist=False)


class Schedule(Base):
    __tablename__ = "schedules"

    id              = Column(String, primary_key=True)
    pair            = Column(String(12), nullable=False)
    timeframe       = Column(String(8), nullable=False)
    cron            = Column(String(64), nullable=False)
    min_pips        = Column(Float, nullable=False)
    stop_loss_pips  = Column(Float, nullable=False)
    risk_reward     = Column(Float, nullable=False)
    risk_percent    = Column(Float, nullable=False)
    notify          = Column(Boolean, default=True)
    sessions        = Column(JSON, nullable=True)
    status          = Column(SAEnum(ScheduleStatus), nullable=False, default=ScheduleStatus.ACTIVE)
    next_run        = Column(DateTime(timezone=True), nullable=True)
    created_at      = Column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at      = Column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)


class ScheduleExecution(Base):
    __tablename__ = "schedule_executions"

    id            = Column(Integer, primary_key=True, autoincrement=True)
    schedule_id   = Column(String, ForeignKey("schedules.id"), nullable=False)
    status        = Column(String(16), nullable=False)  # SUCCESS | SKIPPED | FAILED
    detail        = Column(Text, nullable=True)
    signal_id     = Column(String, ForeignKey("signals.id"), nullable=True)
    started_at    = Column(DateTime(timezone=True), nullable=False, default=_now)
    completed_at  = Column(DateTime(timezone=True), nullable=False)
    duration_ms   = Column(Integer, nullable=False)
    created_at    = Column(DateTime(timezone=True), nullable=False, default=_now)


class BacktestRun(Base):
    __tablename__ = "backtest_runs"

    id              = Column(String, primary_key=True)
    pair            = Column(String(12), nullable=False)
    timeframe       = Column(String(8), nullable=False)
    start_date      = Column(DateTime(timezone=True), nullable=False)
    end_date        = Column(DateTime(timezone=True), nullable=False)
    min_pips        = Column(Float, nullable=False)
    stop_loss_pips  = Column(Float, nullable=False)
    risk_reward     = Column(Float, nullable=False)
    risk_percent    = Column(Float, nullable=False)
    initial_balance = Column(Float, nullable=False)
    sessions        = Column(JSON, nullable=True)
    status          = Column(SAEnum(BacktestStatus), nullable=False, default=BacktestStatus.QUEUED)
    error           = Column(Text, nullable=True)
    created_at      = Column(DateTime(timezone=True), default=_now, nullable=False)
    completed_at    = Column(DateTime(timezone=True), nullable=True)

    predictions = relationship("BacktestPrediction", back_populates="run", cascade="all, delete-orphan")
    signals_bt  = relationship("BacktestSignal",     back_populates="run", cascade="all, delete-orphan")
    metrics     = relationship("BacktestMetric",     back_populates="run", uselist=False, cascade="all, delete-orphan")


class BacktestPrediction(Base):
    """Cached Kronos predictions — reused across runs with same pair/timeframe."""
    __tablename__ = "backtest_predictions"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    run_id      = Column(String, ForeignKey("backtest_runs.id"), nullable=False)
    candle_time = Column(DateTime(timezone=True), nullable=False)
    pred_open   = Column(Float, nullable=False)
    pred_high   = Column(Float, nullable=False)
    pred_low    = Column(Float, nullable=False)
    pred_close  = Column(Float, nullable=False)

    run = relationship("BacktestRun", back_populates="predictions")


class BacktestSignal(Base):
    __tablename__ = "backtest_signals"

    id                = Column(Integer, primary_key=True, autoincrement=True)
    run_id            = Column(String, ForeignKey("backtest_runs.id"), nullable=False)
    candle_time       = Column(DateTime(timezone=True), nullable=False)
    direction         = Column(SAEnum(SignalDirection), nullable=False)
    effective_entry   = Column(Float, nullable=False)
    spread_pips       = Column(Float, nullable=False)
    predicted_close   = Column(Float, nullable=False)
    actual_close      = Column(Float, nullable=True)
    predicted_pips    = Column(Float, nullable=True)
    actual_pips       = Column(Float, nullable=True)
    direction_correct = Column(Boolean, nullable=True)
    confidence        = Column(Float, nullable=True)
    news_bias         = Column(SAEnum(NewsBias), nullable=True)
    session           = Column(String(16), nullable=True)
    skip_reason       = Column(String(64), nullable=True)

    run = relationship("BacktestRun", back_populates="signals_bt")


class BacktestMetric(Base):
    __tablename__ = "backtest_metrics"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    run_id          = Column(String, ForeignKey("backtest_runs.id"), unique=True, nullable=False)
    total_signals   = Column(Integer, nullable=True)
    skipped         = Column(Integer, nullable=True)
    traded          = Column(Integer, nullable=True)
    win_rate        = Column(Float, nullable=True)
    profit_factor   = Column(Float, nullable=True)
    sharpe_ratio    = Column(Float, nullable=True)
    max_drawdown    = Column(Float, nullable=True)
    total_return    = Column(Float, nullable=True)
    directional_acc = Column(Float, nullable=True)
    by_session      = Column(JSON, nullable=True)
    by_confidence   = Column(JSON, nullable=True)
    by_news_impact  = Column(JSON, nullable=True)
    equity_curve    = Column(JSON, nullable=True)

    run = relationship("BacktestRun", back_populates="metrics")


# ── Schema creation helper (used in tests / first-run) ───────────────────────

async def create_all_tables() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
