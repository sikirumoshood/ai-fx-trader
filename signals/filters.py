from __future__ import annotations

from datetime import datetime, timedelta, time, timezone
from typing import Optional

import pandas as pd

from config.settings import (
    SESSION_FILTERS,
    ACTIVE_SESSIONS,
    CONFIDENCE_THRESHOLD,
    DEFAULT_MAX_SPREAD,
    NEWS_BLACKOUT_MINUTES,
    TREND_FAST_EMA,
    TREND_FILTER_ENABLED,
    TREND_LOOKBACK_CANDLES,
    TREND_MIN_MOMENTUM_PIPS,
    TREND_SLOW_EMA,
    pip_size,
)


# ── Session filter ────────────────────────────────────────────────────────────

def identify_session(dt: Optional[datetime] = None) -> str:
    """Return the name of whichever session dt falls in, regardless of active list.
    Returns empty string if no session matches.
    """
    if dt is None:
        dt = datetime.now(timezone.utc)
    t = dt.time().replace(second=0, microsecond=0)
    for name, sess in SESSION_FILTERS.items():
        start = _parse_time(sess["start"])
        end   = _parse_time(sess["end"])
        if _time_in_range(start, end, t):
            return name
    return ""


def check_session(
    dt: Optional[datetime] = None,
    sessions: Optional[list] = None,
) -> tuple[bool, str]:
    """Return (is_within_active_session, session_name).

    sessions: list of session names to check against. Defaults to ACTIVE_SESSIONS.
    Returns (False, "") if outside all specified sessions.
    """
    if dt is None:
        dt = datetime.now(timezone.utc)
    t = dt.time().replace(second=0, microsecond=0)

    active_list = sessions if sessions is not None else ACTIVE_SESSIONS

    for name in active_list:
        sess = SESSION_FILTERS.get(name.strip())
        if not sess:
            continue
        start = _parse_time(sess["start"])
        end   = _parse_time(sess["end"])
        if _time_in_range(start, end, t):
            return True, name.strip()

    return False, ""


def _parse_time(s: str) -> time:
    h, m = map(int, s.split(":"))
    return time(h, m)


def _time_in_range(start: time, end: time, t: time) -> bool:
    if start <= end:
        return start <= t <= end
    # crosses midnight (e.g. SYDNEY 21:00 → 06:00)
    return t >= start or t <= end


def minutes_until_session_end(
    session_name: str,
    dt: Optional[datetime] = None,
) -> Optional[int]:
    """Return remaining minutes until the current session window ends."""
    sess = SESSION_FILTERS.get(session_name.strip())
    if not sess:
        return None

    if dt is None:
        dt = datetime.now(timezone.utc)

    start = _parse_time(sess["start"])
    end = _parse_time(sess["end"])
    t = dt.time().replace(second=0, microsecond=0)

    if not _time_in_range(start, end, t):
        return None

    if start <= end:
        end_dt = datetime.combine(dt.date(), end, tzinfo=timezone.utc)
    else:
        # Session crosses midnight.
        if t >= start:
            end_dt = datetime.combine(dt.date() + timedelta(days=1), end, tzinfo=timezone.utc)
        else:
            end_dt = datetime.combine(dt.date(), end, tzinfo=timezone.utc)

    remaining = int((end_dt - dt).total_seconds() // 60)
    return max(0, remaining)


# ── RSI advisory ─────────────────────────────────────────────────────────────

def compute_rsi(candles: pd.DataFrame, period: int = 14) -> Optional[float]:
    """Compute RSI(14) from close prices using Wilder's EMA smoothing.

    Returns None if there are insufficient candles.
    """
    closes = candles["close"].astype(float).dropna()
    if len(closes) < period + 1:
        return None
    delta = closes.diff()
    gains = delta.clip(lower=0)
    losses = (-delta).clip(lower=0)
    avg_gain = gains.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = losses.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return round(float(rsi.iloc[-1]), 1)


def rsi_advisory(rsi_value: Optional[float], direction: str) -> tuple[str, Optional[float]]:
    """Return a human-readable RSI advisory and the RSI value.

    Returns (advisory_label, rsi_value). The label is one of:
        "OVERBOUGHT" — RSI > 70, BUY signals carry reversal risk
        "OVERSOLD"   — RSI < 30, SELL signals carry reversal risk
        "CLEAR"      — RSI in neutral 30–70 zone
        "UNAVAILABLE" — insufficient data to compute
    """
    if rsi_value is None:
        return "UNAVAILABLE", None

    if rsi_value > 70:
        label = "OVERBOUGHT"
        if direction == "BUY":
            label += " — BUY into exhaustion, reversal risk"
        else:
            label += " — SELL aligns with overbought momentum"
    elif rsi_value < 30:
        label = "OVERSOLD"
        if direction == "SELL":
            label += " — SELL into exhaustion, bounce risk"
        else:
            label += " — BUY aligns with oversold bounce"
    else:
        label = f"CLEAR ({rsi_value})"

    return label, rsi_value


# ── Confidence filter ─────────────────────────────────────────────────────────

def check_confidence(confidence: float, threshold: Optional[float] = None) -> bool:
    limit = threshold if threshold is not None else CONFIDENCE_THRESHOLD
    return confidence >= limit


# ── Pip movement filter ───────────────────────────────────────────────────────

def check_min_pips(predicted_pips: float, min_pips: float) -> bool:
    """True if the predicted move magnitude meets the minimum pip threshold."""
    return abs(predicted_pips) >= min_pips


# ── Spread filter ─────────────────────────────────────────────────────────────

def check_spread(spread_pips: float, max_spread: Optional[float] = None) -> bool:
    """True if current spread is within acceptable range."""
    limit = max_spread if max_spread is not None else DEFAULT_MAX_SPREAD
    return spread_pips <= limit


# ── Trend alignment filter ───────────────────────────────────────────────────

def resolve_trend_direction(
    candles: pd.DataFrame,
    pair: str,
    *,
    lookback: int = TREND_LOOKBACK_CANDLES,
    fast_ema: int = TREND_FAST_EMA,
    slow_ema: int = TREND_SLOW_EMA,
    min_momentum_pips: float = TREND_MIN_MOMENTUM_PIPS,
) -> tuple[str | None, str]:
    """Return a hard trend direction only when recent momentum is decisive.

    EMAs are useful context, but they lag at turning points. A strong reversal
    call should not be blocked just because EMA9 is still above/below EMA21.
    """
    if candles.empty or "close" not in candles:
        return None, "No close-price history"

    closes = candles["close"].astype(float).dropna()
    if len(closes) < lookback + 1:
        return None, "Insufficient history for trend filter"

    ps = pip_size(pair)
    recent_move = (closes.iloc[-1] - closes.iloc[-(lookback + 1)]) / ps
    if recent_move >= min_momentum_pips:
        return "BUY", f"Recent momentum {recent_move:.1f} pips over {lookback} candles"
    if recent_move <= -min_momentum_pips:
        return "SELL", f"Recent momentum {recent_move:.1f} pips over {lookback} candles"

    if len(closes) < slow_ema:
        return None, (
            f"No decisive recent trend: move {recent_move:.1f} pips over "
            f"{lookback} candles is below {min_momentum_pips:.1f} pips"
        )

    fast = closes.ewm(span=fast_ema, adjust=False).mean()
    slow = closes.ewm(span=slow_ema, adjust=False).mean()
    fast_slope_pips = (fast.iloc[-1] - fast.iloc[-2]) / ps

    ema_context = (
        f"EMA context: EMA{fast_ema} {'above' if fast.iloc[-1] > slow.iloc[-1] else 'below'} "
        f"EMA{slow_ema}, slope {fast_slope_pips:.1f} pips"
    )
    if fast.iloc[-1] > slow.iloc[-1] and fast_slope_pips >= 0:
        return None, (
            f"No decisive recent trend: move {recent_move:.1f} pips over "
            f"{lookback} candles is below {min_momentum_pips:.1f} pips. {ema_context}"
        )
    if fast.iloc[-1] < slow.iloc[-1] and fast_slope_pips <= 0:
        return None, (
            f"No decisive recent trend: move {recent_move:.1f} pips over "
            f"{lookback} candles is below {min_momentum_pips:.1f} pips. {ema_context}"
        )

    return None, (
        f"No decisive recent trend: move {recent_move:.1f} pips over "
        f"{lookback} candles is below {min_momentum_pips:.1f} pips. {ema_context}"
    )


def check_trend_alignment(
    direction: str,
    candles: pd.DataFrame,
    pair: str,
) -> tuple[bool, str | None, str]:
    """Return whether the signal direction agrees with the current trend."""
    if not TREND_FILTER_ENABLED:
        return True, None, "Trend filter disabled"

    trend_direction, detail = resolve_trend_direction(candles, pair)
    if trend_direction is None:
        return True, None, detail
    if direction != trend_direction:
        return False, trend_direction, detail
    return True, trend_direction, detail


def trend_from_candles(
    pair: str,
    lookback: int = 40,
) -> tuple[str | None, str]:
    """Determine trend direction from the last `lookback` closed M1 candles (~40 minutes).

    Uses EMA9 vs EMA20 crossover on closing prices.
    Returns ("BUY", detail), ("SELL", detail), or (None, detail) if flat/unclear.
    """
    try:
        from data import fetcher
        candles = fetcher.fetch_ohlcv(pair, "M1", count=lookback + 2)
        candles = candles.sort_values("time").reset_index(drop=True)
        closed  = candles.iloc[:-1]
    except Exception as exc:
        return None, f"M5 trend fetch failed: {exc}"

    if len(closed) < lookback:
        return None, f"Insufficient M1 candles ({len(closed)} < {lookback})"

    window = closed.iloc[-lookback:].reset_index(drop=True)
    closes = window["close"].astype(float)

    ema9  = closes.ewm(span=9,  adjust=False).mean()
    ema20 = closes.ewm(span=20, adjust=False).mean()

    ema9_val  = ema9.iloc[-1]
    ema20_val = ema20.iloc[-1]

    detail = f"M1 EMA9={'%.5f' % ema9_val} vs EMA20={'%.5f' % ema20_val} over last {lookback} M1 candles"

    if ema9_val > ema20_val:
        return "BUY", f"Bullish trend: {detail}"
    if ema9_val < ema20_val:
        return "SELL", f"Bearish trend: {detail}"
    return None, f"Flat trend: {detail}"


def m1_market_bias(
    pair: str,
    lookback: int = 20,
    min_net_pips: float = 2.0,
) -> tuple[str | None, str]:
    """Determine market bias from the last 20 closed M1 candles using momentum scoring.

    Three conditions must ALL agree on the same direction:
      1. EMA9 vs EMA20 crossover
      2. Bull body dominance > 50% (total size of bullish bodies vs bearish bodies)
      3. Net pip displacement of at least 2 pips in that direction

    Returns ("BUY", detail), ("SELL", detail), or (None, detail) if momentum
    is weak or mixed.
    """
    try:
        from data import fetcher
        candles = fetcher.fetch_ohlcv(pair, "M1", count=lookback + 2)
        candles = candles.sort_values("time").reset_index(drop=True)
        closed = candles.iloc[:-1]
    except Exception as exc:
        return None, f"M1 bias check failed: {exc}"

    if len(closed) < lookback:
        return None, "Insufficient M1 history for momentum check"

    window = closed.iloc[-lookback:].reset_index(drop=True)
    opens  = window["open"].astype(float)
    closes = window["close"].astype(float)

    # 1. EMA crossover
    ema9      = closes.ewm(span=9,  adjust=False).mean()
    ema20     = closes.ewm(span=20, adjust=False).mean()
    ema9_val  = ema9.iloc[-1]
    ema20_val = ema20.iloc[-1]
    ema_bullish = ema9_val > ema20_val

    # 2. Body dominance — total body size of bull vs bear candles
    bodies     = (closes - opens).abs()
    bull_body  = bodies[closes > opens].sum()
    bear_body  = bodies[closes < opens].sum()
    total_body = bull_body + bear_body
    bull_dominance = bull_body / total_body if total_body > 0 else 0.5

    # 3. Net pip displacement
    ps      = pip_size(pair)
    net_pip = (closes.iloc[-1] - closes.iloc[0]) / ps

    bear_dominance = 1.0 - bull_dominance
    detail = (
        f"M1 EMA9 {'>' if ema_bullish else '<'} EMA20 ({ema9_val:.5f} vs {ema20_val:.5f}), "
        f"bull body {bull_dominance:.0%} / bear body {bear_dominance:.0%}, "
        f"net {net_pip:+.2f} pips"
    )

    bullish_momentum = ema_bullish and bull_dominance > 0.5 and net_pip >= min_net_pips
    bearish_momentum = not ema_bullish and bear_dominance > 0.5 and net_pip <= -min_net_pips

    if bullish_momentum:
        return "BUY", f"Strong bullish momentum: {detail}"
    if bearish_momentum:
        return "SELL", f"Strong bearish momentum: {detail}"
    return None, f"Weak/mixed momentum: {detail}"


def m5_market_bias(pair: str) -> tuple[str | None, str]:
    """Determine market bias from the last 20 closed M5 candles (~100 minutes)."""
    try:
        from data import fetcher
        candles = fetcher.fetch_ohlcv(pair, "M5", count=22)
        candles = candles.sort_values("time").reset_index(drop=True)
        closed = candles.iloc[:-1]
    except Exception as exc:
        return None, f"M5 bias check failed: {exc}"

    if len(closed) < 20:
        return None, "Insufficient M5 history for trend detection"

    closes = closed["close"].astype(float).reset_index(drop=True).iloc[-20:]

    ema9  = closes.ewm(span=9,  adjust=False).mean()
    ema20 = closes.ewm(span=20, adjust=False).mean()

    ema9_val  = ema9.iloc[-1]
    ema20_val = ema20.iloc[-1]

    ema_bullish = ema9_val > ema20_val

    detail = (
        f"M5 EMA9 {'above' if ema_bullish else 'below'} EMA20 "
        f"({ema9_val:.5g} vs {ema20_val:.5g})"
    )

    if ema_bullish:
        return "BUY", f"Uptrend: {detail}"
    return "SELL", f"Downtrend: {detail}"


def h1_market_bias(pair: str) -> tuple[str | None, str]:
    """Determine the market bias from the last 50 closed H1 candles (~2 days).

    Returns ("BUY", detail), ("SELL", detail), or (None, detail) if no clear bias.
    Fetches H1 candles directly so this can be called from any signal engine
    regardless of the signal's own timeframe.
    """
    try:
        from data import fetcher
        candles = fetcher.fetch_ohlcv(pair, "H1", count=55)  # 55 fetched → 54 closed, enough for lookback=50
        candles = candles.sort_values("time").reset_index(drop=True)
        closed = candles.iloc[:-1]  # drop the still-forming bar
        return resolve_trend_direction(closed, pair, lookback=50, min_momentum_pips=TREND_MIN_MOMENTUM_PIPS)
    except Exception as exc:
        return None, f"H1 bias check failed: {exc}"


def h4_market_bias(pair: str) -> tuple[str | None, str]:
    """Determine the market bias from the last 600 closed 4H candles (~100 days).

    Uses EMA20 vs EMA50 crossover plus price position relative to EMA50.
    Both must agree on the same side before calling a trend direction.
    When they conflict (ranging / crossover zone), returns None.

    Returns ("BUY", detail), ("SELL", detail), or (None, detail).
    """
    try:
        from data import fetcher
        candles = fetcher.fetch_ohlcv(pair, "H4", count=21)  # 21 fetched → 20 closed
        candles = candles.sort_values("time").reset_index(drop=True)
        closed = candles.iloc[:-1]  # drop the still-forming bar
    except Exception as exc:
        return None, f"H4 bias check failed: {exc}"

    if len(closed) < 20:
        return None, "Insufficient 4H history for trend detection"

    closes = closed["close"].astype(float).reset_index(drop=True)

    ema9  = closes.ewm(span=9,  adjust=False).mean()
    ema20 = closes.ewm(span=20, adjust=False).mean()

    ema9_val  = ema9.iloc[-1]
    ema20_val = ema20.iloc[-1]

    ema_bullish = ema9_val > ema20_val  # fast above slow → uptrend structure

    detail = (
        f"4H EMA9 {'above' if ema_bullish else 'below'} EMA20 "
        f"({ema9_val:.5g} vs {ema20_val:.5g})"
    )

    if ema_bullish:
        return "BUY", f"Uptrend: {detail}"
    return "SELL", f"Downtrend: {detail}"


def check_h1_bias(direction: str, pair: str) -> tuple[bool, str | None, str]:
    """Return whether the signal direction aligns with the H1 4-hour market bias.

    When no clear bias exists the signal is allowed through — the filter only
    blocks signals that are clearly counter-trend.
    """
    if not TREND_FILTER_ENABLED:
        return True, None, "Trend filter disabled"

    bias, detail = h1_market_bias(pair)
    if bias is None:
        return True, None, detail
    if direction != bias:
        return False, bias, f"H1 bias is {bias}: {detail}"
    return True, bias, detail


# ── News blackout filter ──────────────────────────────────────────────────────

def check_news_blackout(
    events: list[dict],
    dt: Optional[datetime] = None,
    blackout_minutes: Optional[int] = None,
) -> tuple[bool, Optional[str]]:
    """Return (is_clear, blocking_event_name).

    Blocks trading if any HIGH-impact event falls within ±blackout_minutes
    of the given datetime.

    Each event dict must have:
        time   (datetime, UTC)
        impact (str: "HIGH" | "MEDIUM" | "LOW")
        name   (str)
    """
    if dt is None:
        dt = datetime.now(timezone.utc)
    window = timedelta(minutes=blackout_minutes or NEWS_BLACKOUT_MINUTES)

    for event in events:
        event_time: Optional[datetime] = event.get("time")
        if not event_time:
            continue
        if event.get("impact", "").upper() != "HIGH":
            continue
        if abs((event_time - dt).total_seconds()) <= window.total_seconds():
            return False, event.get("name", "Unknown high-impact event")

    return True, None


# ── Composite gate ────────────────────────────────────────────────────────────

def apply_all_filters(
    *,
    confidence: float,
    predicted_pips: float,
    spread_pips: float,
    events: list[dict],
    min_pips: float,
    max_spread: Optional[float] = None,
    dt: Optional[datetime] = None,
) -> tuple[bool, str]:
    """Run all filters in order. Returns (passed, skip_reason).

    Returns (True, "") if all filters pass.
    Returns (False, reason) on the first failing filter.
    """
    if not check_confidence(confidence):
        return False, f"Confidence {confidence:.2f} below threshold {CONFIDENCE_THRESHOLD}"

    if not check_min_pips(predicted_pips, min_pips):
        return False, (
            f"Predicted move magnitude {abs(predicted_pips):.1f} pips "
            f"below minimum {min_pips}"
        )

    if not check_spread(spread_pips, max_spread):
        limit = max_spread or DEFAULT_MAX_SPREAD
        return False, f"Spread {spread_pips:.1f} pips exceeds maximum {limit}"

    clear, event_name = check_news_blackout(events, dt)
    if not clear:
        return False, f"High-impact news blackout: {event_name}"

    active, session = check_session(dt)
    if not active:
        return False, "Outside active trading sessions"

    return True, ""
