from __future__ import annotations

from typing import Optional

import pandas as pd

BULLISH = "BULLISH"
BEARISH = "BEARISH"
NEUTRAL = "NEUTRAL"


def _parts(o: float, h: float, l: float, c: float) -> tuple[float, float, float, float]:
    body        = abs(c - o)
    upper_wick  = h - max(o, c)
    lower_wick  = min(o, c) - l
    rng         = (h - l) or 1e-10
    return body, upper_wick, lower_wick, rng


def _near_recent_low(candles: pd.DataFrame, lookback: int = 20) -> bool:
    window = candles.iloc[-lookback:]
    return float(candles.iloc[-1]["low"]) <= float(window["low"].min()) * 1.003


def _near_recent_high(candles: pd.DataFrame, lookback: int = 20) -> bool:
    window = candles.iloc[-lookback:]
    return float(candles.iloc[-1]["high"]) >= float(window["high"].max()) * 0.997


class CandlePatternDetector:
    """Detect candlestick patterns from the last 1–3 closed candles.

    Returns (pattern_name, bias) where bias is BULLISH, BEARISH, or NEUTRAL.
    Checks three-candle patterns first, then two-candle, then single-candle
    so the most significant pattern wins.
    """

    def detect(self, candles: pd.DataFrame) -> tuple[Optional[str], str]:
        """Run detection on the provided closed candles.

        Args:
            candles: DataFrame with open/high/low/close columns, sorted oldest→newest.
                     Caller must pass only closed candles (current forming bar excluded).

        Returns:
            (pattern_name, bias) — pattern_name is None when nothing is detected.
        """
        n = len(candles)
        if n < 1:
            return None, NEUTRAL

        c0 = candles.iloc[-1]

        if n >= 3:
            c2, c1 = candles.iloc[-3], candles.iloc[-2]
            for fn in (
                self._morning_star,
                self._evening_star,
                self._three_white_soldiers,
                self._three_black_crows,
            ):
                result = fn(c2, c1, c0)
                if result:
                    return result

        if n >= 2:
            c1 = candles.iloc[-2]
            for fn in (
                self._bullish_engulfing,
                self._bearish_engulfing,
                self._inside_bar,
            ):
                result = fn(c1, c0)
                if result:
                    return result

        for fn in (
            lambda c: self._hammer(c, candles),
            lambda c: self._shooting_star(c, candles),
            self._marubozu,
            lambda c: self._doji(c, candles),
        ):
            result = fn(c0)
            if result:
                return result

        return None, NEUTRAL

    # ── Single-candle ─────────────────────────────────────────────────────────

    def _hammer(self, c, candles: pd.DataFrame) -> Optional[tuple]:
        body, upper, lower, rng = _parts(c.open, c.high, c.low, c.close)
        if body > rng * 0.35:
            return None
        if lower < body * 2.0:
            return None
        if upper > body * 0.6:
            return None
        if _near_recent_low(candles):
            return "Bullish Hammer", BULLISH
        if _near_recent_high(candles):
            return "Hanging Man", BEARISH
        return None

    def _shooting_star(self, c, candles: pd.DataFrame) -> Optional[tuple]:
        body, upper, lower, rng = _parts(c.open, c.high, c.low, c.close)
        if body > rng * 0.35:
            return None
        if upper < body * 2.0:
            return None
        if lower > body * 0.6:
            return None
        if _near_recent_high(candles):
            return "Shooting Star", BEARISH
        if _near_recent_low(candles):
            return "Inverted Hammer", BULLISH
        return None

    def _marubozu(self, c) -> Optional[tuple]:
        body, upper, lower, rng = _parts(c.open, c.high, c.low, c.close)
        if body < rng * 0.85:
            return None
        if upper > rng * 0.05 or lower > rng * 0.05:
            return None
        if c.close > c.open:
            return "Bullish Marubozu", BULLISH
        return "Bearish Marubozu", BEARISH

    def _doji(self, c, candles: pd.DataFrame) -> Optional[tuple]:
        body, upper, lower, rng = _parts(c.open, c.high, c.low, c.close)
        if body > rng * 0.08:
            return None
        if upper > rng * 0.6 and _near_recent_high(candles):
            return "Gravestone Doji", BEARISH
        if lower > rng * 0.6 and _near_recent_low(candles):
            return "Dragonfly Doji", BULLISH
        return "Doji", NEUTRAL

    # ── Two-candle ────────────────────────────────────────────────────────────

    def _bullish_engulfing(self, c1, c0) -> Optional[tuple]:
        if c1.close >= c1.open:
            return None
        if c0.close <= c0.open:
            return None
        if c0.open < c1.close and c0.close > c1.open:
            return "Bullish Engulfing", BULLISH
        return None

    def _bearish_engulfing(self, c1, c0) -> Optional[tuple]:
        if c1.close <= c1.open:
            return None
        if c0.close >= c0.open:
            return None
        if c0.open > c1.close and c0.close < c1.open:
            return "Bearish Engulfing", BEARISH
        return None

    def _inside_bar(self, c1, c0) -> Optional[tuple]:
        if c0.high < c1.high and c0.low > c1.low:
            return "Inside Bar", NEUTRAL
        return None

    # ── Three-candle ──────────────────────────────────────────────────────────

    def _morning_star(self, c2, c1, c0) -> Optional[tuple]:
        body2 = abs(c2.close - c2.open)
        rng2  = (c2.high - c2.low) or 1e-10
        if c2.close >= c2.open or body2 < rng2 * 0.5:
            return None
        body1 = abs(c1.close - c1.open)
        rng1  = (c1.high - c1.low) or 1e-10
        if body1 > rng1 * 0.4:
            return None
        mid2 = (c2.open + c2.close) / 2
        if c0.close <= c0.open or c0.close <= mid2:
            return None
        return "Morning Star", BULLISH

    def _evening_star(self, c2, c1, c0) -> Optional[tuple]:
        body2 = abs(c2.close - c2.open)
        rng2  = (c2.high - c2.low) or 1e-10
        if c2.close <= c2.open or body2 < rng2 * 0.5:
            return None
        body1 = abs(c1.close - c1.open)
        rng1  = (c1.high - c1.low) or 1e-10
        if body1 > rng1 * 0.4:
            return None
        mid2 = (c2.open + c2.close) / 2
        if c0.close >= c0.open or c0.close >= mid2:
            return None
        return "Evening Star", BEARISH

    def _three_white_soldiers(self, c2, c1, c0) -> Optional[tuple]:
        for prev, curr in ((c2, c1), (c1, c0)):
            if curr.close <= curr.open:
                return None
            body = curr.close - curr.open
            rng  = (curr.high - curr.low) or 1e-10
            if (curr.high - curr.close) > body * 0.3:
                return None
            if curr.close <= prev.close:
                return None
        if c1.close <= c2.close or c0.close <= c1.close:
            return None
        return "Three White Soldiers", BULLISH

    def _three_black_crows(self, c2, c1, c0) -> Optional[tuple]:
        for prev, curr in ((c2, c1), (c1, c0)):
            if curr.close >= curr.open:
                return None
            body = curr.open - curr.close
            rng  = (curr.high - curr.low) or 1e-10
            if (curr.close - curr.low) > body * 0.3:
                return None
            if curr.close >= prev.close:
                return None
        if c1.close >= c2.close or c0.close >= c1.close:
            return None
        return "Three Black Crows", BEARISH
