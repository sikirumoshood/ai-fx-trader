from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone

import pandas as pd
from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import pip_size
from data import fetcher
from data.store import (
    AsyncSessionLocal,
    BacktestRun, BacktestPrediction, BacktestSignal, BacktestMetric,
    BacktestStatus, SignalDirection, NewsBias,
)
from signals import filters, risk
from signals.filters import identify_session
from signals.fvg import detect_ifvg
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
    indicator: str = "ifvg",
    sessions: list[str] | None = None,
    ifvg_threshold: float = 0.0,
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
            indicator=indicator,
            sessions=sessions,
            ifvg_threshold=ifvg_threshold,
            status=BacktestStatus.QUEUED,
        )
        db.add(run)
        await db.commit()

    asyncio.create_task(
        _run_backtest_ifvg(
            run_id=run_id,
            pair=pair,
            timeframe=timeframe,
            start_date=start_date,
            end_date=end_date,
            stop_loss_pips=stop_loss_pips,
            risk_reward=risk_reward,
            sessions=sessions,
            ifvg_threshold=ifvg_threshold,
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
            direction   = risk.resolve_direction(next_candle["open"], next_candle["close"])
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
                    f"Counter-trend prediction blocked: trend is {trend_direction}; signal was {direction}"
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


# ── IFVG backtest ─────────────────────────────────────────────────────────────

_MAX_FORWARD  = 10    # candles to scan forward for zone excursion measurement
_FVG_LOOKBACK = 100   # candles to look back for open FVG zones


async def _run_backtest_ifvg(
    *,
    run_id: str,
    pair: str,
    timeframe: str,
    start_date: datetime,
    end_date: datetime,
    stop_loss_pips: float,
    risk_reward: float,
    sessions: list[str] | None = None,
    ifvg_threshold: float = 0.0,
) -> None:
    await _set_status(run_id, BacktestStatus.RUNNING)
    log.info("IFVG backtest %s started (%s %s %s→%s)", run_id, pair, timeframe, start_date.date(), end_date.date())

    try:
        # Fetch extra candles before start_date so FVG lookback has data
        buffer_start = start_date - _tf_buffer(timeframe, _FVG_LOOKBACK)
        all_candles = fetcher.fetch_ohlcv_range(pair, timeframe, buffer_start, end_date)
        all_candles = all_candles.sort_values("time").reset_index(drop=True)
        print(f"[IFVG {run_id}] fetched {len(all_candles)} candles "
              f"from {all_candles['time'].iloc[0]} to {all_candles['time'].iloc[-1]}", flush=True)

        # First index at or after start_date — this is where we begin emitting signals
        start_ts = pd.Timestamp(start_date) if start_date.tzinfo else pd.Timestamp(start_date).tz_localize("UTC")
        mask = all_candles["time"] >= start_ts
        if not mask.any():
            raise RuntimeError("No candles found at or after start_date")
        start_idx = int(mask.idxmax())
        print(f"[IFVG {run_id}] start_idx={start_idx}, signal bars={len(all_candles) - start_idx}, lookback={_FVG_LOOKBACK}", flush=True)

        if start_idx < _FVG_LOOKBACK:
            if len(all_candles) < _FVG_LOOKBACK + 1:
                raise RuntimeError(
                    f"Broker returned only {len(all_candles)} candles total — insufficient for {_FVG_LOOKBACK}-candle lookback."
                )
            log.warning(
                "Broker has no M%s data before %s (earliest: %s). "
                "Starting signals from bar %d (first bar with full lookback).",
                timeframe, start_date.date(), all_candles["time"].iloc[0], _FVG_LOOKBACK,
            )
            start_idx = _FVG_LOOKBACK

        ps = pip_size(pair)
        print(f"[IFVG {run_id}] pip_size={ps} sessions={sessions} threshold={ifvg_threshold}", flush=True)

        signal_records: list[dict] = []
        n_no_ifvg = 0
        n_timeout = 0
        n_session_skip = 0

        for i in range(start_idx, len(all_candles)):
            await asyncio.sleep(0)   # yield to event loop on every bar

            signal_candle = all_candles.iloc[i]
            candle_time   = signal_candle["time"]
            if hasattr(candle_time, "to_pydatetime"):
                candle_time = candle_time.to_pydatetime()

            # Session filter — always capture matched name for accurate labeling
            in_session, matched_session = filters.check_session(candle_time, sessions=sessions)
            if sessions and not in_session:
                n_session_skip += 1
                continue

            # Lookback window ending at bar i (inclusive)
            window = all_candles.iloc[i - _FVG_LOOKBACK: i + 1]
            result = detect_ifvg(window, lookback=_FVG_LOOKBACK, threshold=ifvg_threshold)

            if result is None:
                n_no_ifvg += 1
                continue

            zone, direction = result
            entry = float(signal_candle["close"])

            # Scan forward up to _MAX_FORWARD candles and compare zone excursions
            future  = all_candles.iloc[i + 1: i + 1 + _MAX_FORWARD]
            outcome, actual_pips = _simulate_zone_excursion(direction, zone.min, zone.max, entry, future, pair)
            print(f"[IFVG {run_id}] bar {i} {candle_time} {direction} entry={entry:.5f} zone=[{zone.min:.5f},{zone.max:.5f}] → {outcome} ({actual_pips:+.1f} pips)", flush=True)

            if outcome == "TIMEOUT":
                n_timeout += 1
                continue

            signal_records.append({
                "direction":         direction,
                "candle_time":       candle_time,
                "effective_entry":   round(entry, 5),
                "spread_pips":       0.0,
                "predicted_close":   round(entry, 5),
                "actual_close":      None,
                "predicted_pips":    None,
                "actual_pips":       actual_pips,
                "direction_correct": actual_pips > 0,
                "confidence":        1.0,
                "news_bias":         None,
                "session":           matched_session or identify_session(candle_time) or "OTHER",
            })

            if len(signal_records) % 500 == 0:
                await _persist_signals(run_id, signal_records[-500:])

        remainder = len(signal_records) % 500
        if remainder:
            await _persist_signals(run_id, signal_records[-remainder:])

        print(f"[IFVG {run_id}] DONE: no_ifvg={n_no_ifvg} timeout={n_timeout} session_skip={n_session_skip} traded={len(signal_records)}", flush=True)

        result_metrics = metrics_mod.compute(signal_records)
        await _persist_metrics(run_id, result_metrics)
        await _set_status(run_id, BacktestStatus.DONE)
        log.info(
            "IFVG backtest %s done — %d trades placed (%d WIN / %d LOSS)",
            run_id,
            result_metrics["traded"],
            round(result_metrics["traded"] * result_metrics["win_rate"]),
            round(result_metrics["traded"] * (1 - result_metrics["win_rate"])),
        )
        from notifications.telegram import send_backtest_alert
        await send_backtest_alert(run_id, result_metrics)

    except Exception as exc:
        log.exception("IFVG backtest %s failed", run_id)
        await _set_status(run_id, BacktestStatus.FAILED, error=str(exc))


def _simulate_zone_excursion(
    direction: str,
    zone_min: float,
    zone_max: float,
    entry: float,
    future_candles: pd.DataFrame,
    pair: str,
) -> tuple[str, float]:
    """
    Determine IFVG outcome by comparing max excursion above vs below the FVG zone.

    Finds the highest high and lowest low across all forward candles, then measures
    how far each moved beyond the zone boundary:
      above_zone = max_high - zone_max  (distance above the top of the gap)
      below_zone = zone_min - min_low   (distance below the bottom of the gap)

    The larger excursion determines the directional outcome. Pips are measured
    from entry to the extreme point in the winning direction.
    """
    if future_candles.empty:
        return "TIMEOUT", 0.0

    ps       = pip_size(pair)
    max_high = float(future_candles["high"].max())
    min_low  = float(future_candles["low"].min())

    above_zone = max(max_high - zone_max, 0.0)
    below_zone = max(zone_min - min_low, 0.0)

    if direction == "SELL":
        if below_zone >= above_zone:
            return "WIN",  round((entry - min_low) / ps, 1)
        else:
            return "LOSS", round(-(max_high - entry) / ps, 1)
    else:  # BUY
        if above_zone >= below_zone:
            return "WIN",  round((max_high - entry) / ps, 1)
        else:
            return "LOSS", round(-(entry - min_low) / ps, 1)


def _tf_buffer(timeframe: str, n_candles: int) -> timedelta:
    """Timedelta needed to cover n_candles of the given timeframe.

    Minute timeframes get a minimum of 7 days so the buffer always spans at
    least one full trading week, regardless of weekends or public holidays at
    the start boundary (e.g. Jan 1 being a holiday with no M5 candles).
    """
    tf  = timeframe.upper()
    pad = 1.4
    if tf.startswith("M") and tf[1:].isdigit():
        computed = timedelta(minutes=int(tf[1:]) * n_candles * pad)
        return max(computed, timedelta(days=7))
    if tf.startswith("H") and tf[1:].isdigit():
        return timedelta(hours=int(tf[1:]) * n_candles * pad)
    if tf == "D1":
        return timedelta(days=int(n_candles * pad * 1.5))
    if tf == "W1":
        return timedelta(weeks=int(n_candles * pad))
    return timedelta(days=30)
