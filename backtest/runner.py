from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import pip_size
from data import fetcher
from data.store import (
    AsyncSessionLocal,
    BacktestRun, BacktestPrediction, BacktestSignal, BacktestMetric,
    BacktestStatus, SignalDirection, NewsBias,
)
from model.base import BasePredictor
from signals import filters, risk
from signals.filters import identify_session
from backtest import metrics as metrics_mod

log = logging.getLogger(__name__)


# ── Public entry point ────────────────────────────────────────────────────────

async def submit_run(
    *,
    pair: str,
    timeframe: str,
    start_date: datetime,
    end_date: datetime,
    min_pips: float,
    stop_loss_pips: float,
    risk_reward: float,
    risk_percent: float,
    initial_balance: float,
    predictor: BasePredictor,
    sessions: list[str] | None = None,
) -> str:
    """Create a BacktestRun record and launch the backtest in the background.

    Returns the run_id immediately (async job pattern).
    """
    run_id = f"bt_{uuid.uuid4().hex[:10]}"

    async with AsyncSessionLocal() as db:
        run = BacktestRun(
            id=run_id,
            pair=pair,
            timeframe=timeframe,
            start_date=start_date,
            end_date=end_date,
            min_pips=min_pips,
            stop_loss_pips=stop_loss_pips,
            risk_reward=risk_reward,
            risk_percent=risk_percent,
            initial_balance=initial_balance,
            sessions=sessions,
            status=BacktestStatus.QUEUED,
        )
        db.add(run)
        await db.commit()

    # Fire-and-forget — caller polls GET /backtest/{run_id}
    asyncio.create_task(
        _run_backtest(
            run_id=run_id,
            pair=pair,
            timeframe=timeframe,
            start_date=start_date,
            end_date=end_date,
            min_pips=min_pips,
            stop_loss_pips=stop_loss_pips,
            risk_reward=risk_reward,
            predictor=predictor,
            sessions=sessions,
        )
    )

    return run_id


# ── Core backtest logic ───────────────────────────────────────────────────────

async def _run_backtest(
    *,
    run_id: str,
    pair: str,
    timeframe: str,
    start_date: datetime,
    end_date: datetime,
    min_pips: float,
    stop_loss_pips: float,
    risk_reward: float,
    predictor: BasePredictor,
    sessions: list[str] | None = None,
) -> None:
    await _set_status(run_id, BacktestStatus.RUNNING)
    log.info("Backtest %s started (%s %s %s→%s)", run_id, pair, timeframe, start_date.date(), end_date.date())

    try:
        # ── Phase 1: fetch full historical data ────────────────────────────
        all_candles = fetcher.fetch_ohlcv_range(pair, timeframe, start_date, end_date)
        all_candles = all_candles.sort_values("time").reset_index(drop=True)
        if len(all_candles) < 450:
            raise RuntimeError(f"Insufficient candles: {len(all_candles)} (need ≥ 450)")

        context_size = 400
        signal_records: list[dict] = []

        # ── Phase 2: rolling prediction window ────────────────────────────
        for i in range(context_size, len(all_candles)):
            context = all_candles.iloc[i - context_size: i]
            signal_candle = all_candles.iloc[i - 1]
            actual  = all_candles.iloc[i]

            # Candle time & session
            candle_time = signal_candle["time"]
            if hasattr(candle_time, "to_pydatetime"):
                candle_time = candle_time.to_pydatetime()
            in_session, session_name = filters.check_session(candle_time, sessions=sessions)
            if sessions and not in_session:
                signal_records.append(_skip_record(signal_candle, "Outside selected sessions"))
                continue
            # Use the matched session name from check_session so the label
            # reflects the user's chosen session, not dict-order first-match.
            # Fall back to identify_session only when no session filter is active.
            session_label = session_name if (sessions and session_name) else (identify_session(candle_time) or "OTHER")

            # Predict next candle (run in thread so event loop stays responsive)
            try:
                pred_df = await asyncio.to_thread(predictor.predict, context, 1)
                row = pred_df.iloc[0]
                next_candle = {
                    "open":  float(row["open"]),
                    "high":  float(row["high"]),
                    "low":   float(row["low"]),
                    "close": float(row["close"]),
                }
            except Exception as exc:
                log.warning("Prediction failed at index %d: %s", i, exc)
                signal_records.append(_skip_record(signal_candle, f"Prediction error: {exc}"))
                continue

            # Confidence: predicted move vs recent ATR
            recent      = context.iloc[-14:] if len(context) >= 14 else context
            atr         = float((recent["high"] - recent["low"]).mean()) if len(recent) >= 2 else 1e-5
            pred_move   = abs(next_candle["close"] - next_candle["open"])
            confidence  = round(min(0.95, 0.5 + 0.5 * (pred_move / (atr + 1e-8))), 3)

            entry       = float(signal_candle["close"])
            direction   = risk.resolve_direction(entry, next_candle["close"])
            spread_pts  = float(signal_candle["spread"])
            spread_pips = spread_pts / 10.0  # 10 points = 1 pip for 5-digit brokers

            if direction == "BUY":
                effective_entry = entry + spread_pips * pip_size(pair)
            else:
                effective_entry = entry - spread_pips * pip_size(pair)

            # Filters
            trend_ok, trend_direction, trend_detail = filters.check_trend_alignment(direction, context, pair)
            if not trend_ok:
                reason = (
                    f"Counter-trend prediction blocked: trend is {trend_direction}; Kronos predicted {direction}"
                    if trend_direction
                    else "Trend unavailable"
                )
                signal_records.append(_skip_record(signal_candle, f"{reason}: {trend_detail}"))
                continue
            if not filters.check_confidence(confidence):
                signal_records.append(_skip_record(signal_candle, "Low confidence"))
                continue
            predicted_pips = risk.predicted_move_pips(direction, effective_entry, next_candle["close"], pair)
            if not filters.check_min_pips(predicted_pips, min_pips):
                signal_records.append(_skip_record(signal_candle, "Min pips"))
                continue
            if not filters.check_spread(spread_pips):
                signal_records.append(_skip_record(signal_candle, "Spread"))
                continue

            # Outcome: close-to-close (simple, consistent, not distorted by SL/TP sizing)
            actual_close = float(actual["close"])
            actual_pips  = round(risk.predicted_move_pips(direction, effective_entry, actual_close, pair), 1)
            dir_correct  = (direction == "BUY" and actual_close > effective_entry) or \
                           (direction == "SELL" and actual_close < effective_entry)

            signal_records.append({
                "direction":         direction,
                "candle_time":       candle_time,
                "effective_entry":   round(effective_entry, 5),
                "spread_pips":       round(spread_pips, 2),
                "predicted_close":   round(next_candle["close"], 5),
                "actual_close":      round(actual_close, 5),
                "predicted_pips":    round(predicted_pips, 1),
                "actual_pips":       actual_pips,
                "direction_correct": dir_correct,
                "confidence":        confidence,
                "news_bias":         None,
                "session":           session_label,
            })

            # Persist in batches of 500 to avoid memory buildup
            if len(signal_records) % 500 == 0:
                await _persist_signals(run_id, signal_records[-500:])
            else:
                await asyncio.sleep(0)  # yield to event loop between predictions

        # Persist any remainder
        remainder = len(signal_records) % 500
        if remainder:
            await _persist_signals(run_id, signal_records[-remainder:])

        # ── Phase 3: aggregate metrics ─────────────────────────────────────
        result = metrics_mod.compute(signal_records)
        await _persist_metrics(run_id, result)
        await _set_status(run_id, BacktestStatus.DONE)
        log.info("Backtest %s done — %d signals, %d traded", run_id, result["total_signals"], result["traded"])
        from notifications.telegram import send_backtest_alert
        await send_backtest_alert(run_id, result)

    except Exception as exc:
        log.exception("Backtest %s failed", run_id)
        await _set_status(run_id, BacktestStatus.FAILED, error=str(exc))


# ── DB helpers ────────────────────────────────────────────────────────────────

async def _set_status(run_id: str, status: BacktestStatus, error: Optional[str] = None) -> None:
    async with AsyncSessionLocal() as db:
        run = await db.get(BacktestRun, run_id)
        if run:
            run.status = status
            if error:
                run.error = error
            if status in (BacktestStatus.DONE, BacktestStatus.FAILED):
                run.completed_at = datetime.now(timezone.utc)
            await db.commit()


async def _persist_signals(run_id: str, records: list[dict]) -> None:
    async with AsyncSessionLocal() as db:
        for r in records:
            sig = BacktestSignal(
                run_id=run_id,
                candle_time=r["candle_time"],
                direction=SignalDirection(r["direction"]) if r["direction"] != "SKIP" else SignalDirection.SKIP,
                effective_entry=r.get("effective_entry", 0),
                spread_pips=r.get("spread_pips", 0),
                predicted_close=r.get("predicted_close", 0),
                actual_close=r.get("actual_close"),
                predicted_pips=r.get("predicted_pips"),
                actual_pips=r.get("actual_pips"),
                direction_correct=r.get("direction_correct"),
                confidence=r.get("confidence"),
                news_bias=NewsBias(r["news_bias"]) if r.get("news_bias") else None,
                session=r.get("session"),
                skip_reason=_short_skip_reason(r.get("skip_reason")),
            )
            db.add(sig)
        await db.commit()


async def _persist_metrics(run_id: str, result: dict) -> None:
    async with AsyncSessionLocal() as db:
        m = BacktestMetric(
            run_id=run_id,
            total_signals=result["total_signals"],
            skipped=result["skipped"],
            traded=result["traded"],
            win_rate=result["win_rate"],
            profit_factor=result["profit_factor"],
            sharpe_ratio=result["sharpe_ratio"],
            max_drawdown=result["max_drawdown"],
            total_return=result["total_return"],
            directional_acc=result["directional_acc"],
            by_session=result["by_session"],
            by_confidence=result["by_confidence"],
            by_news_impact=result["by_news_impact"],
            equity_curve=result["equity_curve"],
        )
        db.add(m)
        await db.commit()


def _skip_record(candle, reason: str) -> dict:
    t = candle["time"]
    if hasattr(t, "to_pydatetime"):
        t = t.to_pydatetime()
    return {
        "direction":         "SKIP",
        "candle_time":       t,
        "effective_entry":   float(candle["close"]),
        "spread_pips":       0.0,
        "predicted_close":   float(candle["close"]),
        "actual_close":      None,
        "predicted_pips":    None,
        "actual_pips":       None,
        "direction_correct": None,
        "confidence":        None,
        "news_bias":         None,
        "session":           None,
        "skip_reason":       reason,
    }


def _short_skip_reason(reason: Optional[str]) -> Optional[str]:
    if reason is None or len(reason) <= 64:
        return reason
    return reason[:61] + "..."
