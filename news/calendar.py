from __future__ import annotations

import re
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

import httpx
from bs4 import BeautifulSoup

_FF_URL = "https://www.forexfactory.com/calendar"
_ET_ZONE = ZoneInfo("America/New_York")  # Forex Factory uses US Eastern time
log = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

_IMPACT_MAP = {
    "icon--ff-impact-red":    "HIGH",
    "icon--ff-impact-ora":    "MEDIUM",
    "icon--ff-impact-yel":    "LOW",
    "icon--ff-impact-gra":    "HOLIDAY",
}


# ── Public API ────────────────────────────────────────────────────────────────

async def fetch_events(
    pairs: list[str],
    hours_ahead: int = 24,
    timeout: float = 10.0,
) -> list[dict]:
    """Fetch upcoming economic calendar events from Forex Factory.

    Returns a list of event dicts:
        time     (datetime, UTC)
        currency (str, e.g. "USD")
        impact   (str: "HIGH" | "MEDIUM" | "LOW" | "HOLIDAY")
        name     (str)
        forecast (str | None)
        previous (str | None)

    Filters to currencies relevant to the given pairs and within hours_ahead.
    """
    currencies = _currencies_from_pairs(pairs)
    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(hours=hours_ahead)

    try:
        # Some environments inject HTTP(S)_PROXY variables that ForexFactory blocks.
        # Use direct connection for this scrape request.
        async with httpx.AsyncClient(headers=_HEADERS, timeout=timeout, trust_env=False) as client:
            resp = await client.get(_FF_URL)
            resp.raise_for_status()
            html = resp.text
    except httpx.HTTPError as exc:
        log.warning("Calendar fetch failed from %s: %s", _FF_URL, exc)
        return []

    events = _parse_calendar(html, now.year)
    filtered = [
        e for e in events
        if e["currency"] in currencies and now <= e["time"] <= cutoff
    ]
    if not filtered:
        log.info(
            "Calendar fetch returned no relevant upcoming events "
            "(pairs=%s parsed=%d hours_ahead=%d)",
            ",".join(pairs),
            len(events),
            hours_ahead,
        )
    return filtered


def filter_high_impact(events: list[dict]) -> list[dict]:
    return [e for e in events if e.get("impact") == "HIGH"]


# ── Parsing ───────────────────────────────────────────────────────────────────

def _currencies_from_pairs(pairs: list[str]) -> set[str]:
    currencies: set[str] = set()
    for pair in pairs:
        p = pair.upper().replace("/", "")
        if len(p) >= 6:
            currencies.add(p[:3])
            currencies.add(p[3:6])
    return currencies


def _parse_calendar(html: str, year: int) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    rows = soup.select("tr.calendar__row")
    events: list[dict] = []
    current_date: Optional[datetime] = None

    for row in rows:
        # Date rows update the running date
        date_cell = row.select_one("td.calendar__date span")
        if date_cell:
            parsed = _parse_date(date_cell.get_text(strip=True), year)
            if parsed:
                current_date = parsed

        if current_date is None:
            continue

        # Time
        time_cell = row.select_one("td.calendar__time")
        if not time_cell:
            continue
        event_time = _parse_event_time(time_cell.get_text(strip=True), current_date)
        if event_time is None:
            continue

        # Currency
        currency_cell = row.select_one("td.calendar__currency")
        currency = currency_cell.get_text(strip=True) if currency_cell else ""
        if not currency:
            continue

        # Impact
        impact_cell = row.select_one("td.calendar__impact span")
        impact = "LOW"
        if impact_cell:
            for cls, label in _IMPACT_MAP.items():
                if cls in (impact_cell.get("class") or []):
                    impact = label
                    break

        # Event name
        name_cell = row.select_one("td.calendar__event span.calendar__event-title")
        name = name_cell.get_text(strip=True) if name_cell else ""

        # Forecast / Previous
        forecast_cell = row.select_one("td.calendar__forecast")
        previous_cell = row.select_one("td.calendar__previous")
        forecast = forecast_cell.get_text(strip=True) if forecast_cell else None
        previous = previous_cell.get_text(strip=True) if previous_cell else None

        events.append({
            "time":     event_time,
            "currency": currency,
            "impact":   impact,
            "name":     name,
            "forecast": forecast or None,
            "previous": previous or None,
        })

    return events


def _parse_date(text: str, year: int) -> Optional[datetime]:
    # e.g. "Mon Apr 21" or "Apr 21"
    text = text.strip()
    for fmt in ("%a %b %d", "%b %d"):
        try:
            dt = datetime.strptime(text, fmt).replace(year=year)
            return dt
        except ValueError:
            pass
    return None


def _parse_event_time(text: str, date: datetime) -> Optional[datetime]:
    text = text.strip()
    if not text or text.lower() in ("all day", "tentative"):
        # Use midnight for all-day events
        dt_et = datetime(date.year, date.month, date.day, 0, 0, tzinfo=_ET_ZONE)
        return dt_et.astimezone(timezone.utc)
    # e.g. "8:30am" or "12:00pm"
    match = re.match(r"(\d{1,2}):(\d{2})(am|pm)", text.lower())
    if not match:
        return None
    h, m, ampm = int(match.group(1)), int(match.group(2)), match.group(3)
    if ampm == "pm" and h != 12:
        h += 12
    elif ampm == "am" and h == 12:
        h = 0
    try:
        dt_et = datetime(date.year, date.month, date.day, h, m, tzinfo=_ET_ZONE)
        return dt_et.astimezone(timezone.utc)
    except ValueError:
        return None
