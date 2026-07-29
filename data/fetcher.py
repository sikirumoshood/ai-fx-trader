from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

import pandas as pd

from config.settings import (
    MT5_LOGIN, MT5_PASSWORD, MT5_SERVER, MT5_PATH,
    MT5_HOST, MT5_PORT, MT5_BRIDGE_FILES, MT5_BROKER_UTC_OFFSET_HOURS,
    pip_size,
)

# Populated by initialize() — None until a successful connection is made.
# No connection is attempted at import time.
_mt5 = None
_MT5_REMOTE = False  # True when using mt5linux (Mac/Linux Docker)
_AUTO_BROKER_UTC_OFFSET_HOURS: int | None = None


def _is_available() -> bool:
    return _mt5 is not None


# ── Connection ────────────────────────────────────────────────────────────────

def initialize() -> bool:
    """Connect to MT5. Returns True on success, False on any failure.

    Priority:
      1. AiFxBridge socket (Mac native MT5 app via MQL5 EA)
      2. mt5linux RPyC bridge (Docker on Linux)
      3. Native MetaTrader5 package (Windows only)

    Safe to call multiple times — reconnects if not already connected.
    """
    global _mt5, _MT5_REMOTE

    # 1. Try AiFxBridge — file-based bridge to Mac native MT5 app
    try:
        from data.mt5_bridge import MT5Bridge
        bridge = MT5Bridge(files_path=MT5_BRIDGE_FILES)
        if bridge.connect():
            _mt5 = bridge
            _MT5_REMOTE = False
            return True
    except Exception:
        pass

    # 2. Try mt5linux — Docker RPyC bridge (Linux)
    try:
        from mt5linux import MetaTrader5 as _MT5Class
        instance = _MT5Class(host=MT5_HOST, port=MT5_PORT)
        if not instance.initialize():
            return False
        if MT5_LOGIN and not instance.login(MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER):
            return False
        _mt5 = instance
        _MT5_REMOTE = True
        return True
    except Exception:
        pass

    # 3. Try native MetaTrader5 package — Windows only
    try:
        import MetaTrader5 as _native  # type: ignore[import]
        kwargs: dict = {}
        if MT5_PATH:
            kwargs["path"] = MT5_PATH
        if not _native.initialize(**kwargs):
            return False
        if MT5_LOGIN and not _native.login(MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER):
            return False
        _mt5 = _native
        _MT5_REMOTE = False
        return True
    except ImportError:
        pass

    return False


def shutdown() -> None:
    global _mt5
    if _mt5 is not None:
        try:
            # MT5Bridge exposes shutdown(); mt5linux and native MT5 expose shutdown() too
            _mt5.shutdown()
        except Exception:
            pass
        _mt5 = None


def is_connected() -> bool:
    if not _is_available():
        initialize()   # retry — EA may have started after server boot
    if not _is_available():
        return False
    try:
        info = _mt5.terminal_info()
        return info is not None and info.connected
    except Exception:
        return False


# ── Timeframe helpers ─────────────────────────────────────────────────────────

def _tf_map() -> dict:
    if not _is_available():
        return {}
    return {
        "M1":  _mt5.TIMEFRAME_M1,
        "M5":  _mt5.TIMEFRAME_M5,
        "M15": _mt5.TIMEFRAME_M15,
        "M30": _mt5.TIMEFRAME_M30,
        "H1":  _mt5.TIMEFRAME_H1,
        "H4":  _mt5.TIMEFRAME_H4,
        "D1":  _mt5.TIMEFRAME_D1,
        "W1":  _mt5.TIMEFRAME_W1,
        "MN1": _mt5.TIMEFRAME_MN1,
    }


def _require_mt5() -> None:
    if not _is_available():
        raise RuntimeError("MT5 not connected — call fetcher.initialize() first")


# ── Data fetching ─────────────────────────────────────────────────────────────

def fetch_ohlcv(pair: str, timeframe: str, count: int = 500) -> pd.DataFrame:
    """Fetch the most recent `count` candles for a pair/timeframe."""
    _require_mt5()
    tf_map = _tf_map()
    tf = tf_map.get(timeframe.upper())
    if tf is None:
        raise ValueError(f"Unsupported timeframe: {timeframe}. Valid: {list(tf_map)}")
    rates = _mt5.copy_rates_from_pos(pair, tf, 0, count)
    if rates is None or len(rates) == 0:
        raise RuntimeError(f"No data for {pair} {timeframe}: {_mt5.last_error()}")
    return _to_df(rates, timeframe=timeframe)


def fetch_ohlcv_range(
    pair: str,
    timeframe: str,
    start: datetime,
    end: datetime,
) -> pd.DataFrame:
    """Fetch OHLCV candles between start and end (UTC datetimes)."""
    _require_mt5()
    tf_map = _tf_map()
    tf = tf_map.get(timeframe.upper())
    if tf is None:
        raise ValueError(f"Unsupported timeframe: {timeframe}. Valid: {list(tf_map)}")
    _ensure_auto_broker_offset(pair, tf, timeframe)
    rates = _mt5.copy_rates_range(pair, tf, start, end)
    if rates is None or len(rates) == 0:
        raise RuntimeError(f"No data for {pair} {timeframe} {start}–{end}: {_mt5.last_error()}")
    return _to_df(rates, timeframe=timeframe)


def _to_df(rates, timeframe: str | None = None) -> pd.DataFrame:
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df = df.rename(columns={"tick_volume": "volume"})
    df = df[["time", "open", "high", "low", "close", "volume", "spread"]]
    return _normalise_broker_time(df, timeframe)


def _normalise_broker_time(df: pd.DataFrame, timeframe: str | None) -> pd.DataFrame:
    """Convert MT5 broker/server candle timestamps to UTC.

    The AiFxBridge returns MQL5 candle timestamps as provided by the terminal.
    Some brokers expose those in server time, which can be several hours ahead
    of UTC. Kronos and the scheduler expect UTC, so normalise here at the data
    boundary.
    """
    raw_offset = str(MT5_BROKER_UTC_OFFSET_HOURS).strip().lower()
    offset_hours: int | None

    if raw_offset in ("", "auto"):
        global _AUTO_BROKER_UTC_OFFSET_HOURS
        offset_hours = _infer_future_time_offset_hours(df, timeframe)
        if offset_hours is not None:
            _AUTO_BROKER_UTC_OFFSET_HOURS = offset_hours
        elif _AUTO_BROKER_UTC_OFFSET_HOURS is not None:
            offset_hours = _AUTO_BROKER_UTC_OFFSET_HOURS
    else:
        try:
            offset_hours = int(float(raw_offset))
        except ValueError:
            offset_hours = None

    if offset_hours:
        df = df.copy()
        df["time"] = df["time"] - pd.to_timedelta(offset_hours, unit="h")
    return df


def _ensure_auto_broker_offset(pair: str, tf, timeframe: str) -> None:
    if str(MT5_BROKER_UTC_OFFSET_HOURS).strip().lower() not in ("", "auto"):
        return
    if _AUTO_BROKER_UTC_OFFSET_HOURS is not None:
        return
    try:
        rates = _mt5.copy_rates_from_pos(pair, tf, 0, 10)
    except Exception:
        return
    if rates is None or len(rates) == 0:
        return
    _to_df(rates, timeframe=timeframe)


def _infer_future_time_offset_hours(
    df: pd.DataFrame,
    timeframe: str | None,
    now: datetime | None = None,
) -> int | None:
    if df.empty or "time" not in df:
        return None

    latest = df["time"].max()
    if hasattr(latest, "to_pydatetime"):
        latest = latest.to_pydatetime()
    if latest.tzinfo is None:
        latest = latest.replace(tzinfo=timezone.utc)

    now_utc = now or datetime.now(timezone.utc)
    tolerance = max(timedelta(minutes=10), _timeframe_delta(timeframe) / 4)
    future_skew = latest - now_utc
    if future_skew <= tolerance:
        return None

    return max(1, int(future_skew.total_seconds() // 3600) + 1)


def _timeframe_delta(timeframe: str | None) -> timedelta:
    tf = (timeframe or "").upper()
    if tf.startswith("M") and tf[1:].isdigit():
        return timedelta(minutes=int(tf[1:]))
    if tf.startswith("H") and tf[1:].isdigit():
        return timedelta(hours=int(tf[1:]))
    if tf.startswith("D") and tf[1:].isdigit():
        return timedelta(days=int(tf[1:]))
    if tf.startswith("W") and tf[1:].isdigit():
        return timedelta(weeks=int(tf[1:]))
    return timedelta(hours=1)


# ── Symbol info ───────────────────────────────────────────────────────────────

def get_available_pairs() -> list[str]:
    if not _is_available():
        return []
    symbols = _mt5.symbols_get()
    if symbols is None:
        return []
    return [s.name for s in symbols if s.visible]


def get_current_spread_pips(pair: str) -> float:
    _require_mt5()
    info = _mt5.symbol_info(pair)
    if info is None:
        raise RuntimeError(f"Symbol not found: {pair}")
    return round(info.spread * info.point / pip_size(pair), 1)


def get_account_balance() -> Optional[float]:
    if not _is_available():
        return None
    info = _mt5.account_info()
    return info.balance if info else None
