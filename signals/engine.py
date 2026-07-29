from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import pandas as pd

from config.settings import (
    SIGNAL_EXPIRY_SECONDS,
    DEFAULT_MIN_PIPS,
    DEFAULT_STOP_LOSS_PIPS,
    DEFAULT_RISK_REWARD,
    DEFAULT_RISK_PERCENT,
    DEFAULT_MAX_SPREAD,
    pip_size,
)
from data import fetcher
from model.base import BasePredictor
from signals import filters, risk
from news import calendar, sentiment


# ── Signal result ─────────────────────────────────────────────────────────────

class Signal:
    """Fully resolved trading signal."""

    def __init__(
        self,
        *,
        direction: str,
        pair: str,
        timeframe: str,
        entry: float,
        stop_loss: float,
        take_profit: float,
        risk_reward: float,
        confidence: float,
        news_bias: str,
        reason: str,
        predicted_candle: dict,
    ) -> None:
        self.id        = f"sig_{uuid.uuid4().hex[:10]}"
        self.status    = "PENDING"
        self.direction = direction
        self.pair      = pair
        self.timeframe = timeframe
        self.entry     = entry
        self.stop_loss = stop_loss
        self.take_profit = take_profit
        self.risk_reward = risk_reward
        self.confidence  = confidence
        self.news_bias   = news_bias
        self.reason      = reason
        self.predicted_candle = predicted_candle
        self.created_at  = datetime.now(timezone.utc)
        self.expires_at  = self.created_at + timedelta(seconds=SIGNAL_EXPIRY_SECONDS)

    def to_dict(self) -> dict:
        return {
            "id":               self.id,
            "status":           self.status,
            "signal":           self.direction,
            "pair":             self.pair,
            "timeframe":        self.timeframe,
            "entry":            self.entry,
            "stop_loss":        self.stop_loss,
            "take_profit":      self.take_profit,
            "risk_reward":      self.risk_reward,
            "confidence":       self.confidence,
            "news_bias":        self.news_bias,
            "reason":           self.reason,
            "expires_at":       self.expires_at.isoformat(),
            "created_at":       self.created_at.isoformat(),
        }


class SkipSignal:
    """Returned when the pipeline decides not to trade."""

    def __init__(self, pair: str, timeframe: str, reason: str) -> None:
        self.direction = "SKIP"
        self.pair      = pair
        self.timeframe = timeframe
        self.reason    = reason
        self.created_at = datetime.now(timezone.utc)

    def to_dict(self) -> dict:
        return {
            "signal":    "SKIP",
            "pair":      self.pair,
            "timeframe": self.timeframe,
            "reason":    self.reason,
            "created_at": self.created_at.isoformat(),
        }


# ── Engine ────────────────────────────────────────────────────────────────────

class SignalEngine:
    """Orchestrates the full signal generation pipeline.

    Pipeline:
        1. Fetch latest OHLCV candles from MT5
        2. Run Kronos prediction
        3. Apply rule-based filters (spread, session, news, pips, confidence)
        4. Score news sentiment with FinBERT
        5. Check sentiment alignment with predicted direction
        6. Calculate entry, SL, TP and lot size
        7. Return Signal or SkipSignal
    """

    def __init__(self, predictor: BasePredictor) -> None:
        self.predictor = predictor

    async def generate(
        self,
        pair: str,
        timeframe: str = "H1",
        min_pips: float = DEFAULT_MIN_PIPS,
        stop_loss_pips: float = DEFAULT_STOP_LOSS_PIPS,
        risk_reward: float = DEFAULT_RISK_REWARD,
        risk_percent: float = DEFAULT_RISK_PERCENT,
        max_spread: float = DEFAULT_MAX_SPREAD,
        account_balance: Optional[float] = None,
        sessions: list[str] | None = None,
    ) -> Signal | SkipSignal:
        """Run the full pipeline and return a Signal or SkipSignal."""

        now = datetime.now(timezone.utc)

        # ── 1. OHLCV data ──────────────────────────────────────────────────
        try:
            candles = fetcher.fetch_ohlcv(pair, timeframe, count=600)
        except RuntimeError as exc:
            return SkipSignal(pair, timeframe, f"MT5 data fetch failed: {exc}")

        candles = candles.sort_values("time").reset_index(drop=True)
        # copy_rates_from_pos includes the current forming candle; drop it so
        # direction is based on fully closed bars only.
        closed_candles = candles.iloc[:-1].copy()

        if len(closed_candles) < 50:
            return SkipSignal(pair, timeframe, "Insufficient candle history")

        # ── 2. Current spread ──────────────────────────────────────────────
        try:
            spread_pips = fetcher.get_current_spread_pips(pair)
        except RuntimeError:
            # Fall back to last candle spread from history
            spread_pips = float(candles["spread"].iloc[-1]) * candles["open"].iloc[-1] / pip_size(pair)

        # ── 3. News calendar ───────────────────────────────────────────────
        try:
            events = await calendar.fetch_events([pair])
        except Exception:
            events = []

        # ── 4. Spread filter (cheap, run early) ────────────────────────────
        if not filters.check_spread(spread_pips, max_spread):
            return SkipSignal(pair, timeframe, f"Spread {spread_pips:.1f} pips exceeds max {max_spread}")

        # ── 5. Session filter ──────────────────────────────────────────────
        active, session_name = filters.check_session(now, sessions=sessions)
        if not active:
            return SkipSignal(pair, timeframe, "Outside active trading sessions")

        # ── 6. News blackout ───────────────────────────────────────────────
        clear, event_name = filters.check_news_blackout(events, now)
        if not clear:
            return SkipSignal(pair, timeframe, f"High-impact news blackout: {event_name}")

        # ── 7. Kronos prediction ───────────────────────────────────────────
        try:
            pred_df    = self.predictor.predict(closed_candles)
            next_candle = {
                "open":  float(pred_df["open"].iloc[0]),
                "high":  float(pred_df["high"].iloc[0]),
                "low":   float(pred_df["low"].iloc[0]),
                "close": float(pred_df["close"].iloc[0]),
            }
            confidence = self.predictor.estimate_confidence(closed_candles)  # type: ignore[attr-defined]
        except Exception as exc:
            return SkipSignal(pair, timeframe, f"Model prediction failed: {exc}")

        # ── 8. Direction (entry-relative, not predicted-candle-relative) ──
        # We trade from current price to predicted close; use that vector for direction.
        entry = float(closed_candles["close"].iloc[-1])
        direction = risk.resolve_direction(entry, next_candle["close"])
        trend_ok, trend_direction, trend_detail = filters.check_trend_alignment(
            direction,
            closed_candles,
            pair,
        )
        if not trend_ok:
            if trend_direction:
                return SkipSignal(
                    pair, timeframe,
                    f"Counter-trend prediction blocked: trend is {trend_direction} ({trend_detail}); "
                    f"Kronos predicted {direction} from entry to predicted close."
                )
            return SkipSignal(pair, timeframe, f"Trend filter unavailable: {trend_detail}")

        # ── 9. Confidence filter ───────────────────────────────────────────
        if not filters.check_confidence(confidence):
            return SkipSignal(
                pair, timeframe,
                f"Confidence {confidence:.2f} below threshold"
            )

        # ── 10. Min pips filter ────────────────────────────────────────────
        move  = risk.predicted_move_pips(direction, entry, next_candle["close"], pair)
        if not filters.check_min_pips(move, min_pips):
            return SkipSignal(
                pair, timeframe,
                f"Predicted move magnitude {abs(move):.1f} pips below minimum {min_pips}"
            )

        # ── 11. FinBERT sentiment ──────────────────────────────────────────
        try:
            news_bias, _news_conf = sentiment.score_events(events, pair)
        except Exception:
            news_bias = "NEUTRAL"

        # ── 12. Sentiment conflict check ───────────────────────────────────
        if _sentiment_conflicts(direction, news_bias):
            return SkipSignal(
                pair, timeframe,
                f"Sentiment conflict: model says {direction}, news bias is {news_bias}"
            )

        # ── 13. SL / TP ────────────────────────────────────────────────────
        sl, tp = risk.calculate_sl_tp(
            direction=direction,
            entry=entry,
            pair=pair,
            stop_loss_pips=stop_loss_pips,
            risk_reward=risk_reward,
            predicted_high=next_candle["high"],
            predicted_low=next_candle["low"],
        )

        # ── 14. Build reason string ────────────────────────────────────────
        session_minutes_left = filters.minutes_until_session_end(session_name, now)
        reason = _build_reason(
            direction=direction,
            confidence=confidence,
            move=move,
            news_bias=news_bias,
            session=session_name,
            session_minutes_left=session_minutes_left,
            spread_pips=spread_pips,
            trend_detail=trend_detail,
        )

        return Signal(
            direction=direction,
            pair=pair,
            timeframe=timeframe,
            entry=round(entry, 5),
            stop_loss=sl,
            take_profit=tp,
            risk_reward=risk_reward,
            confidence=confidence,
            news_bias=news_bias,
            reason=reason,
            predicted_candle=next_candle,
        )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _sentiment_conflicts(direction: str, news_bias: str) -> bool:
    """True if news bias is strongly opposed to the predicted direction."""
    if news_bias == "NEUTRAL":
        return False
    if direction == "BUY"  and news_bias == "BEARISH":
        return True
    if direction == "SELL" and news_bias == "BULLISH":
        return True
    return False


def _build_reason(
    *,
    direction: str,
    confidence: float,
    move: float,
    news_bias: str,
    session: str,
    session_minutes_left: int | None,
    spread_pips: float,
    trend_detail: str | None = None,
) -> str:
    parts = [
        f"Kronos predicts {direction} with {confidence:.0%} confidence.",
        f"Predicted move: {move:.1f} pips.",
    ]
    if trend_detail:
        parts.append(f"Trend aligned: {trend_detail}.")
    if news_bias != "NEUTRAL":
        parts.append(f"News sentiment: {news_bias.lower()}.")
    if session_minutes_left is not None and session_minutes_left <= 60:
        parts.append(
            f"Session ends in {session_minutes_left} minute(s) — trade with caution."
        )
    parts.append(f"Session: {session}. Spread: {spread_pips:.1f} pips.")
    return " ".join(parts)
