from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


# ── Common ────────────────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

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
    id:           str
    status:       str
    expires_at:   datetime
    signal:       str
    order_type:   str
    entry:        float
    stop_loss:    float
    take_profit:  float
    risk_reward:  float
    confidence:   float
    news_bias:    Optional[str]
    rsi:          Optional[float] = None
    rsi_advisory: Optional[str]  = None
    pattern_name: Optional[str]  = None
    pattern_bias: Optional[str]  = None
    reason:       Optional[str]
    pair:         str
    timeframe:    str
    created_at:   datetime


class ConfirmRequest(BaseModel):
    stack_count: int             = Field(1,    ge=1, le=10, description="Number of trades to place simultaneously")
    lot_size:    Optional[float] = Field(None, gt=0,        description="Override the default lot size per trade")
    stop_loss:   Optional[float] = Field(None,              description="Override the signal stop loss")
    take_profit: Optional[float] = Field(None,              description="Override the signal take profit")

class ConfirmResponse(BaseModel):
    id:          str
    status:      str
    trade_ids:   list[str]
    stack_count: int
    executed_at: Optional[datetime]


class RejectResponse(BaseModel):
    id:     str
    status: str


# ── Schedules ─────────────────────────────────────────────────────────────────

AVAILABLE_INDICATORS = ["ifvg"]

class CreateScheduleRequest(BaseModel):
    pair:            str        = Field(...,  example="EURUSD")
    timeframe:       str        = Field("H1", example="H1")
    cron:            str        = Field(...,  example="0 * * * *")
    indicator:       str        = Field("ifvg", example="ifvg")
    min_pips:        float      = Field(15.0,  ge=1)
    stop_loss_pips:  float      = Field(20.0,  ge=1)
    risk_reward:     float      = Field(2.0,   ge=0.5)
    risk_percent:    float      = Field(1.0,   ge=0.1, le=10.0)
    notify:          bool            = Field(True)
    notify_email:    Optional[str]   = Field(None, example="trader@example.com")
    sessions:        List[str]       = Field(["LONDON", "NEW_YORK"], example=["LONDON", "NEW_YORK"])
    ifvg_threshold:  float           = Field(0.0,   ge=0.0, le=0.1)
    auto_execute:              bool            = Field(False)
    auto_lot_size:             Optional[float] = Field(None, gt=0, description="Fixed lot size for auto-execution; omit to calculate from risk %")
    max_risk_amount:           Optional[float] = Field(None, gt=0, description="Max loss in account currency if SL is hit; overrides risk_percent for lot sizing")
    auto_close_profit:         bool            = Field(False, description="Override TP so the trade closes when this profit amount (in account currency) is reached")
    auto_close_profit_amount:  Optional[float] = Field(None, gt=0, description="Target profit in account currency; required when auto_close_profit=True")

    @model_validator(mode="after")
    def _validate_indicator(self) -> "CreateScheduleRequest":
        if self.indicator not in AVAILABLE_INDICATORS:
            raise ValueError(f"indicator must be one of {AVAILABLE_INDICATORS}")
        if self.auto_close_profit:
            if not self.auto_execute:
                raise ValueError("auto_close_profit requires auto_execute=True (lot size must be known to compute TP)")
            if not self.auto_close_profit_amount:
                raise ValueError("auto_close_profit_amount is required when auto_close_profit=True")
        return self


class UpdateScheduleRequest(BaseModel):
    min_pips:                 Optional[float]     = None
    stop_loss_pips:           Optional[float]     = None
    risk_reward:              Optional[float]     = None
    risk_percent:             Optional[float]     = None
    cron:                     Optional[str]       = None
    notify:                   Optional[bool]      = None
    notify_email:             Optional[str]       = None
    sessions:                 Optional[List[str]] = None
    ifvg_threshold:           Optional[float]     = None
    auto_execute:             Optional[bool]      = None
    auto_lot_size:            Optional[float]     = None
    max_risk_amount:          Optional[float]     = None
    auto_close_profit:        Optional[bool]      = None
    auto_close_profit_amount: Optional[float]     = None


class ScheduleResponse(BaseModel):
    id:                       str
    status:                   str
    pair:                     str
    timeframe:                str
    cron:                     str
    indicator:                str
    min_pips:                 float
    stop_loss_pips:           float
    risk_reward:              float
    risk_percent:             float
    notify:                   bool
    notify_email:             Optional[str]       = None
    sessions:                 Optional[List[str]] = None
    ifvg_threshold:           Optional[float]     = 0.0
    auto_execute:             bool                = False
    auto_lot_size:            Optional[float]     = None
    max_risk_amount:          Optional[float]     = None
    auto_close_profit:        bool                = False
    auto_close_profit_amount: Optional[float]     = None
    next_run:                 Optional[datetime]
    created_at:               datetime


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
    order_type:  str
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
    pair:        str            = Field(..., example="EURUSD")
    direction:   str            = Field(..., example="BUY")
    order_type:  str            = Field("MARKET", pattern="^(MARKET|LIMIT|STOP)$")
    entry:       Optional[float] = Field(None, description="Required for LIMIT and STOP orders")
    lot_size:    float          = Field(..., gt=0)
    stop_loss:   float
    take_profit: float

    @model_validator(mode="after")
    def _entry_required_for_pending(self) -> "CreateTradeRequest":
        if self.order_type in ("LIMIT", "STOP") and self.entry is None:
            raise ValueError("entry price is required for LIMIT and STOP orders")
        return self


# ── Backtest ──────────────────────────────────────────────────────────────────

class BacktestRequest(BaseModel):
    pair:            str       = Field(...,        example="EURUSD")
    timeframe:       str       = Field("H1",       example="H1")
    indicator:       str       = Field("ifvg",   example="ifvg")
    start_date:      str       = Field(...,        example="2020-01-01")
    end_date:        str       = Field(...,        example="2024-12-31")
    min_pips:        float     = Field(15.0,       ge=1)
    stop_loss_pips:  float     = Field(20.0,       ge=1)
    risk_reward:     float     = Field(2.0,        ge=0.5)
    risk_percent:    float     = Field(1.0,        ge=0.1, le=10.0)
    initial_balance: float     = Field(10000,      ge=100)
    sessions:        List[str] = Field(["LONDON", "NEW_YORK"], example=["LONDON", "NEW_YORK"])
    ifvg_threshold:  float     = Field(0.0,        ge=0.0, le=0.1)

    @model_validator(mode="after")
    def _validate_indicator(self) -> "BacktestRequest":
        if self.indicator not in AVAILABLE_INDICATORS:
            raise ValueError(f"indicator must be one of {AVAILABLE_INDICATORS}")
        return self


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
    indicator:       Optional[str]   = None
    start_date:      Optional[datetime] = None
    end_date:        Optional[datetime] = None
    min_pips:        Optional[float] = None
    stop_loss_pips:  Optional[float] = None
    risk_reward:     Optional[float] = None
    risk_percent:    Optional[float] = None
    initial_balance: Optional[float] = None
    sessions:        Optional[List[str]] = None
    ifvg_threshold:  Optional[float]     = None
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


# ── Journal ───────────────────────────────────────────────────────────────────

JOURNAL_STRATEGIES  = ["BOX_MODEL", "IFVG", "BOX_BREAKOUT", "ORDER_BLOCK"]
JOURNAL_SESSIONS    = ["LONDON", "NEW_YORK"]
JOURNAL_TRADE_MODES = ["AI", "MANUAL"]

class CreateJournalEntryRequest(BaseModel):
    pair:       str   = Field(..., example="EURUSD")
    lot_size:   float = Field(..., gt=0)
    strategy:   str   = Field("BOX_MODEL", example="BOX_MODEL")
    session:    str   = Field(..., example="LONDON")
    trade_mode: str   = Field("MANUAL", example="MANUAL")
    amount_usd: float = Field(..., gt=0, description="Absolute realized amount in USD")
    outcome:    str   = Field(..., example="WIN")
    trade_date: str   = Field(..., example="2026-07-22", description="YYYY-MM-DD")

    @model_validator(mode="after")
    def _validate_fields(self) -> "CreateJournalEntryRequest":
        if self.session.upper() not in JOURNAL_SESSIONS:
            raise ValueError(f"session must be one of {JOURNAL_SESSIONS}")
        if self.outcome.upper() not in ("WIN", "LOSS"):
            raise ValueError("outcome must be WIN or LOSS")
        if self.trade_mode.upper() not in JOURNAL_TRADE_MODES:
            raise ValueError(f"trade_mode must be one of {JOURNAL_TRADE_MODES}")
        return self


class JournalEntryResponse(BaseModel):
    id:         str
    pair:       str
    lot_size:   float
    strategy:   str
    session:    str
    trade_mode: str
    amount_usd: float  # signed: positive = profit, negative = loss
    outcome:    str
    trade_date: datetime
    created_at: datetime
