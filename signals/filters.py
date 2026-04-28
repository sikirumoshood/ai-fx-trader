from __future__ import annotations

from datetime import datetime, timedelta, time, timezone
from typing import Optional

from config.settings import (
    SESSION_FILTERS,
    ACTIVE_SESSIONS,
    CONFIDENCE_THRESHOLD,
    DEFAULT_MAX_SPREAD,
    NEWS_BLACKOUT_MINUTES,
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
