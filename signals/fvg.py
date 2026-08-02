from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

import pandas as pd

from config.settings import pip_size, price_decimals, SIGNAL_EXPIRY_SECONDS
from data import fetcher
from signals.filters import check_session, trend_from_candles


# ── Signal dataclasses ────────────────────────────────────────────────────────

@dataclass
class Signal:
    direction:       str
    pair:            str
    timeframe:       str
    entry:           float
    stop_loss:       float
    take_profit:     float
    risk_reward:     float
    confidence:      float
    news_bias:       Optional[str]
    reason:          Optional[str]          = None
    order_type:      str                    = "MARKET"
    predicted_candle: dict                  = field(default_factory=dict)
    rsi_value:       Optional[float]        = None
    rsi_advisory:    Optional[str]          = None
    pattern_name:    Optional[str]          = None
    pattern_bias:    Optional[str]          = None
    id:              str                    = field(default_factory=lambda: f"sig_{uuid.uuid4().hex[:10]}")
    created_at:      datetime               = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at:      datetime               = field(default_factory=lambda: datetime.now(timezone.utc) + timedelta(seconds=SIGNAL_EXPIRY_SECONDS))


@dataclass
class SkipSignal:
    pair:      str
    timeframe: str
    reason:    str
    code:      str = "SKIPPED"



# ── FVG zone ──────────────────────────────────────────────────────────────────

@dataclass
class FVGZone:
    max: float      # top of gap
    min: float      # bottom of gap
    is_bull: bool
    bar_index: int  # position within the scanned slice


# ── Detection ─────────────────────────────────────────────────────────────────

def _scan_open_fvgs(candles: pd.DataFrame, threshold: float) -> list[FVGZone]:
    """
    Scan a candle slice for FVG patterns and return all unmitigated zones.

    Mirrors the Pine Script detect() logic exactly:
      Bullish:  low[0] > high[2]  and close[1] > high[2]  and gap% > threshold
      Bearish:  high[0] < low[2]  and close[1] < low[2]   and gap% > threshold

    Zones that are mitigated by a later candle within the same slice are removed.
    """
    n = len(candles)
    open_zones: list[FVGZone] = []

    for i in range(2, n):
        c0 = candles.iloc[i]
        c1 = candles.iloc[i - 1]
        c2 = candles.iloc[i - 2]

        bull = (
            c0["low"] > c2["high"]
            and c1["close"] > c2["high"]
            and (c0["low"] - c2["high"]) / c2["high"] > threshold
        )
        bear = (
            c0["high"] < c2["low"]
            and c1["close"] < c2["low"]
            and (c2["low"] - c0["high"]) / c0["high"] > threshold
        )

        if bull:
            open_zones.append(FVGZone(max=c0["low"], min=c2["high"], is_bull=True, bar_index=i))
        elif bear:
            open_zones.append(FVGZone(max=c2["low"], min=c0["high"], is_bull=False, bar_index=i))

    # Remove zones mitigated before the last candle
    surviving: list[FVGZone] = []
    for zone in open_zones:
        mitigated = False
        for j in range(zone.bar_index + 1, n):
            c = candles.iloc[j]
            if zone.is_bull and c["close"] < zone.min:
                mitigated = True
                break
            if not zone.is_bull and c["close"] > zone.max:
                mitigated = True
                break
        if not mitigated:
            surviving.append(zone)

    return surviving


def detect_ifvg(
    candles: pd.DataFrame,
    lookback: int = 100,
    threshold: float = 0.0,
) -> Optional[tuple[FVGZone, str]]:
    """
    Check whether the most recent closed candle just inverted an FVG.

    Scans the last `lookback` closed candles for open FVGs, then checks if the
    final candle's close broke through any of them. Returns the most recently
    formed zone that was inverted, plus the resulting trade direction:
      - Bullish FVG inverted (close < fvg.min)  → SELL
      - Bearish FVG inverted (close > fvg.max)  → BUY

    Returns None if no IFVG was triggered.
    """
    if len(candles) < 3:
        return None

    slice_ = candles.iloc[-lookback:].reset_index(drop=True)
    last = slice_.iloc[-1]

    # Scan all candles except the last for FVG formation; surviving zones are
    # those not yet mitigated as of the second-to-last bar.
    open_zones = _scan_open_fvgs(slice_.iloc[:-1], threshold)

    inverted: list[tuple[FVGZone, str]] = []
    for zone in open_zones:
        if zone.is_bull and last["close"] < zone.min:
            inverted.append((zone, "SELL"))
        elif not zone.is_bull and last["close"] > zone.max:
            inverted.append((zone, "BUY"))

    if not inverted:
        return None

    # Most recently formed zone wins
    inverted.sort(key=lambda x: x[0].bar_index, reverse=True)
    return inverted[0]


# ── Engine ────────────────────────────────────────────────────────────────────

import logging as _logging
_log = _logging.getLogger(__name__)


class FVGSignalEngine:
    """
    Signal engine that fires purely on IFVG events — no model, no filters.

    An IFVG signal is generated when the most recent closed candle's close
    breaks through an open FVG zone, inverting it:
      - Bullish FVG broken downward  → SELL
      - Bearish FVG broken upward    → BUY
    """

    async def generate(
        self,
        pair: str,
        timeframe: str = "H1",
        stop_loss_pips: float = 20.0,
        risk_reward: float = 2.0,
        risk_percent: float = 1.0,
        threshold: float = 0.0,
        sessions: list[str] | None = None,
    ) -> Signal | SkipSignal:
        # Session check first — cheapest filter, no MT5 call needed
        if sessions:
            from datetime import datetime, timezone
            in_session, _ = check_session(datetime.now(timezone.utc), sessions=sessions)
            if not in_session:
                return SkipSignal(pair, timeframe, "Outside selected sessions")

        try:
            candles = fetcher.fetch_ohlcv(pair, timeframe, count=103)
        except RuntimeError as exc:
            return SkipSignal(pair, timeframe, f"MT5 data fetch failed: {exc}")

        candles = candles.sort_values("time").reset_index(drop=True)
        closed = candles.iloc[:-1].copy()   # drop the still-forming bar

        _log.info("IFVG %s %s: fetched %d closed candles", pair, timeframe, len(closed))
        if len(closed) < 40:
            return SkipSignal(pair, timeframe, f"Insufficient candle history ({len(closed)} closed, need ≥ 40)")

        result = detect_ifvg(closed, lookback=100, threshold=threshold)
        if result is None:
            return SkipSignal(pair, timeframe, "No IFVG on last closed bar")

        zone, direction = result

        # Trend filter: only allow signals that match the H1 trend (last 40 H1 candles)
        trend, trend_detail = trend_from_candles(pair, lookback=40)
        _log.info("IFVG trend check %s %s: signal=%s trend=%s — %s", pair, timeframe, direction, trend, trend_detail)
        if trend is None:
            _log.info("IFVG %s %s: skipped — no clear trend", pair, timeframe)
            return SkipSignal(pair, timeframe, f"No clear trend — skipping: {trend_detail}", code="NO_TREND")
        if direction != trend:
            _log.info("IFVG %s %s: blocked — %s signal counter to %s trend", pair, timeframe, direction, trend)
            return SkipSignal(
                pair, timeframe,
                f"Counter-trend IFVG blocked: trend is {trend} but signal is {direction}. {trend_detail}",
                code="COUNTER_TREND",
            )
        _log.info("IFVG %s %s: trend filter passed — %s signal matches %s trend", pair, timeframe, direction, trend)

        ps = pip_size(pair)
        decimals = price_decimals(pair)
        gap_pips = (zone.max - zone.min) / ps

        _log.info("IFVG %s %s: gap=%.4f pips (zone %.*f–%.*f)", pair, timeframe, gap_pips, decimals, zone.min, decimals, zone.max)

        # Entry at the gap edge (limit order): wait for price to retrace to the zone boundary.
        # Bearish FVG inverted → BUY limit at zone.max (top of gap, now acts as support)
        # Bullish FVG inverted → SELL limit at zone.min (bottom of gap, now acts as resistance)
        sl_pips = gap_pips * 5

        if direction == "BUY":
            entry = round(zone.max, decimals)
            sl = round(entry - sl_pips * ps, decimals)
            tp = round(entry + sl_pips * risk_reward * ps, decimals)
        else:
            entry = round(zone.min, decimals)
            sl = round(entry + sl_pips * ps, decimals)
            tp = round(entry - sl_pips * risk_reward * ps, decimals)

        gap_type = "Bullish" if zone.is_bull else "Bearish"
        reason = (
            f"IFVG: {gap_type} FVG ({zone.min:.{decimals}f}–{zone.max:.{decimals}f}, "
            f"{gap_pips:.1f} pips) inverted on last closed bar. "
            f"Limit entry: {entry:.{decimals}f}. SL: {sl_pips:.1f} pips (5× gap), "
            f"TP: {sl_pips * risk_reward:.1f} pips ({risk_reward}R)."
        )

        return Signal(
            direction=direction,
            pair=pair,
            timeframe=timeframe,
            entry=entry,
            stop_loss=sl,
            take_profit=tp,
            risk_reward=risk_reward,
            confidence=1.0,
            news_bias="NEUTRAL",
            reason=reason,
            order_type="LIMIT",
            predicted_candle={
                "open": entry, "high": entry, "low": entry, "close": entry,
            },
        )
