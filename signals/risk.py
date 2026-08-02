from __future__ import annotations

import math

from config.settings import pip_size, price_decimals


# ── Direction from prediction ─────────────────────────────────────────────────

def resolve_direction(pred_open: float, pred_close: float) -> str:
    """Return 'BUY' if target price is above reference price, else 'SELL'."""
    return "BUY" if pred_close > pred_open else "SELL"


# ── Pip calculation ───────────────────────────────────────────────────────────

def pips_between(price_a: float, price_b: float, pair: str) -> float:
    """Absolute pip distance between two prices."""
    return abs(price_a - price_b) / pip_size(pair)


def predicted_move_pips(
    direction: str,
    entry: float,
    predicted_close: float,
    pair: str,
) -> float:
    """Signed pip move: positive = move in signal direction, negative = against."""
    ps = pip_size(pair)
    if direction == "BUY":
        return (predicted_close - entry) / ps
    return (entry - predicted_close) / ps


# ── SL / TP ───────────────────────────────────────────────────────────────────

def calculate_sl_tp(
    direction: str,
    entry: float,
    pair: str,
    stop_loss_pips: float,
    risk_reward: float,
    predicted_high: float | None = None,
    predicted_low: float | None = None,
) -> tuple[float, float]:
    """Calculate stop-loss and take-profit prices from entry using configured pips.

    predicted_high / predicted_low are accepted but ignored — predicted candle
    predictions are not reliable support/resistance levels and were previously
    causing SLs to be placed too close to entry.

    Returns (stop_loss, take_profit) rounded to appropriate decimal places.
    """
    ps = pip_size(pair)
    decimals = price_decimals(pair)

    if direction == "BUY":
        sl = entry - stop_loss_pips * ps
        tp = entry + stop_loss_pips * risk_reward * ps

    else:  # SELL
        sl = entry + stop_loss_pips * ps
        tp = entry - stop_loss_pips * risk_reward * ps

    return round(sl, decimals), round(tp, decimals)


# ── Position sizing ───────────────────────────────────────────────────────────

# Fallback pip value per standard lot (100,000 units) when live rates are unavailable.
# USD-quote pairs are always exactly $10; others are rough approximations.
# _live_pip_value_per_lot() is the preferred path — it uses live MT5 rates.
_PIP_VALUE_PER_LOT: dict[str, float] = {
    "EURUSD": 10.0, "GBPUSD": 10.0, "AUDUSD": 10.0, "NZDUSD": 10.0,
    "USDCAD": 7.5,  "USDCHF": 11.0, "USDJPY": 6.8,
    "XAUUSD": 10.0,
}
_DEFAULT_PIP_VALUE = 10.0


def _live_pip_value_per_lot(pair: str) -> float | None:
    """Return USD pip value per standard lot using live MT5 rates.

    pip_value = pip_size × 100,000 × (quote_currency / USD)

    Falls back to None if MT5 is unavailable or the rate cannot be resolved,
    so callers can fall back to the static table.
    """
    try:
        from data.fetcher import _mt5, _is_available  # lazy — avoids circular import
        if not _is_available():
            return None

        pair = pair.upper()
        ps = pip_size(pair)

        # XAU (gold): standard lot = 100 oz, not 100,000 units
        if pair.startswith("XAU"):
            return ps * 100

        lot = 100_000

        # USD is the quote currency — always exactly $10 (for 5-digit pairs)
        if pair.endswith("USD"):
            return ps * lot

        quote = pair[3:6]

        # Try quoteUSD (e.g. GBPUSD for EURGBP)
        tick = _mt5.symbol_info_tick(quote + "USD")
        if tick is not None:
            mid = (tick.ask + tick.bid) / 2
            if mid > 0:
                return ps * lot * mid

        # Try USDquote and invert (e.g. USDJPY → pip_val = pip_size × lot / mid)
        tick = _mt5.symbol_info_tick("USD" + quote)
        if tick is not None:
            mid = (tick.ask + tick.bid) / 2
            if mid > 0:
                return ps * lot / mid

        return None
    except Exception:
        return None


def calculate_lot_size(
    account_balance: float,
    risk_percent: float,
    stop_loss_pips: float,
    pair: str,
) -> float:
    """Return lot size (standard lots) to risk at most risk_percent of balance.

    Minimum lot: 0.01. Result floored to 2 decimal places.
    """
    if stop_loss_pips <= 0 or account_balance <= 0:
        return 0.01

    risk_amount = account_balance * (risk_percent / 100.0)
    return calculate_lot_size_from_amount(risk_amount, stop_loss_pips, pair)


def calculate_lot_size_from_amount(
    risk_amount: float,
    stop_loss_pips: float,
    pair: str,
) -> float:
    """Return lot size (standard lots) so that hitting SL costs at most risk_amount.

    Uses live MT5 rates when available for accurate pip value; falls back to
    static table. Always floors to 2 decimal places so rounding never exceeds
    the intended risk.

    Minimum lot: 0.01.
    """
    if stop_loss_pips <= 0 or risk_amount <= 0:
        return 0.01

    pip_val = _live_pip_value_per_lot(pair) or _PIP_VALUE_PER_LOT.get(pair.upper(), _DEFAULT_PIP_VALUE)
    sl_value_per_lot = stop_loss_pips * pip_val

    lots = risk_amount / sl_value_per_lot
    return max(0.01, math.floor(lots * 100) / 100)
