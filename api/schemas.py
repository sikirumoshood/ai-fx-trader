from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ── Common ────────────────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str
    mt5_connected: bool
    model_loaded: bool
    db_connected: bool
    timestamp: datetime


class PairsResponse(BaseModel):
    pairs: List[str]


# ── Signals ───────────────────────────────────────────────────────────────────

AVAILABLE_SESSIONS = ["LONDON", "NEW_YORK", "ASIA", "TOKYO", "SYDNEY"]

class AnalyzeRequest(BaseModel):
    pair:           str        = Field(...,              example="EURUSD")
    timeframe:      str        = Field("H1",           example="H1")
    min_pips:       float      = Field(15.0,             ge=1)
    stop_loss_pips: float      = Field(20.0,             ge=1)
    risk_reward:    float      = Field(2.0,              ge=0.5)
    risk_percent:   float      = Field(1.0,              ge=0.1, le=10.0)
    sessions:       List[str]  = Field(["LONDON", "NEW_YORK"], example=["LONDON", "NEW_YORK"])


class SignalResponse(BaseModel):
    id:          str
    status:      str
    expires_at:  datetime
    signal:      str
    entry:       float
    stop_loss:   float
    take_profit: float
    risk_reward: float
    confidence:  float
    news_bias:   Optional[str]
    reason:      Optional[str]
    pair:        str
    timeframe:   str
    created_at:  datetime


class ConfirmResponse(BaseModel):
    id:          str
    status:      str
    trade_id:    Optional[str]
    executed_at: Optional[datetime]


class RejectResponse(BaseModel):
    id:     str
    status: str


# ── Schedules ─────────────────────────────────────────────────────────────────

class CreateScheduleRequest(BaseModel):
    pair:           str        = Field(...,  example="EURUSD")
    timeframe:      str        = Field("H1", example="H1")
    cron:           str        = Field(...,  example="0 * * * *")
    min_pips:       float      = Field(15.0,  ge=1)
    stop_loss_pips: float      = Field(20.0,  ge=1)
    risk_reward:    float      = Field(2.0,   ge=0.5)
    risk_percent:   float      = Field(1.0,   ge=0.1, le=10.0)
    notify:         bool       = Field(True)
    sessions:       List[str]  = Field(["LONDON", "NEW_YORK"], example=["LONDON", "NEW_YORK"])


class UpdateScheduleRequest(BaseModel):
    min_pips:       Optional[float] = None
    stop_loss_pips: Optional[float] = None
    risk_reward:    Optional[float] = None
    risk_percent:   Optional[float] = None
    cron:           Optional[str]   = None
    notify:         Optional[bool]  = None
    sessions:       Optional[List[str]] = None


class ScheduleResponse(BaseModel):
    id:             str
    status:         str
    pair:           str
    timeframe:      str
    cron:           str
    min_pips:       float
    stop_loss_pips: float
    risk_reward:    float
    risk_percent:   float
    notify:         bool
    sessions:       Optional[List[str]] = None
    next_run:       Optional[datetime]
    created_at:     datetime


class ScheduleExecutionResponse(BaseModel):
    id:            int
    schedule_id:   str
    status:        str
    detail:        Optional[str]
    signal_id:     Optional[str]
    started_at:    datetime
    completed_at:  datetime
    duration_ms:   int


# ── Trades ────────────────────────────────────────────────────────────────────

class TradeResponse(BaseModel):
    id:          str
    mt5_ticket:  Optional[int]
    pair:        str
    direction:   str
    entry:       float
    stop_loss:   Optional[float]
    take_profit: Optional[float]
    lot_size:    Optional[float]
    open_price:  Optional[float]
    close_price: Optional[float]
    profit_pips: Optional[float]
    status:      str
    opened_at:   datetime
    closed_at:   Optional[datetime]


class ModifyTradeRequest(BaseModel):
    stop_loss:   Optional[float] = None
    take_profit: Optional[float] = None


class CreateTradeRequest(BaseModel):
    pair:        str   = Field(..., example="EURUSD")
    direction:   str   = Field(..., example="BUY")
    lot_size:    float = Field(..., gt=0)
    stop_loss:   float
    take_profit: float


# ── Backtest ──────────────────────────────────────────────────────────────────

class BacktestRequest(BaseModel):
    pair:            str       = Field(...,   example="EURUSD")
    timeframe:       str       = Field("H1",  example="H1")
    start_date:      str       = Field(...,   example="2020-01-01")
    end_date:        str       = Field(...,   example="2024-12-31")
    min_pips:        float     = Field(15.0,  ge=1)
    stop_loss_pips:  float     = Field(20.0,  ge=1)
    risk_reward:     float     = Field(2.0,   ge=0.5)
    risk_percent:    float     = Field(1.0,   ge=0.1, le=10.0)
    initial_balance: float     = Field(10000, ge=100)
    sessions:        List[str] = Field(["LONDON", "NEW_YORK"], example=["LONDON", "NEW_YORK"])


class BacktestJobResponse(BaseModel):
    job_id:     str
    status:     str
    created_at: datetime


class BacktestStatusResponse(BaseModel):
    job_id:          str
    status:          str
    created_at:      datetime
    completed_at:    Optional[datetime]
    error:           Optional[str]
    pair:            Optional[str]   = None
    timeframe:       Optional[str]   = None
    start_date:      Optional[datetime] = None
    end_date:        Optional[datetime] = None
    min_pips:        Optional[float] = None
    stop_loss_pips:  Optional[float] = None
    risk_reward:     Optional[float] = None
    risk_percent:    Optional[float] = None
    initial_balance: Optional[float] = None
    sessions:        Optional[List[str]] = None
    # Inline metrics (populated for DONE runs in list endpoint)
    traded:          Optional[int]   = None
    win_rate:        Optional[float] = None
    total_pips:      Optional[float] = None
    profit_factor:   Optional[float] = None
    max_drawdown:    Optional[float] = None
    sharpe_ratio:    Optional[float] = None


class BacktestResultsResponse(BaseModel):
    job_id:  str
    summary: Dict[str, Any]
    by_session:     Optional[Dict[str, Any]]
    by_confidence:  Optional[Dict[str, Any]]
    by_news_impact: Optional[Dict[str, Any]]
    equity_curve:   Optional[List[Any]]
