from __future__ import annotations

from config.settings import pip_size


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
    """Calculate stop-loss and take-profit prices.

    Uses predicted_high/predicted_low as natural SL/TP anchors when available.
    Falls back to pip-based calculation from entry.

    Returns (stop_loss, take_profit) rounded to 5 decimal places.
    """
    ps = pip_size(pair)
    decimals = 2 if "JPY" in pair else 5

    if direction == "BUY":
        # SL: below predicted low (or fixed pips below entry)
        if predicted_low is not None:
            sl = min(predicted_low, entry - stop_loss_pips * ps)
        else:
            sl = entry - stop_loss_pips * ps

        actual_sl_pips = (entry - sl) / ps
        tp = entry + actual_sl_pips * risk_reward * ps

    else:  # SELL
        # SL: above predicted high (or fixed pips above entry)
        if predicted_high is not None:
            sl = max(predicted_high, entry + stop_loss_pips * ps)
        else:
            sl = entry + stop_loss_pips * ps

        actual_sl_pips = (sl - entry) / ps
        tp = entry - actual_sl_pips * risk_reward * ps

    return round(sl, decimals), round(tp, decimals)


# ── Position sizing ───────────────────────────────────────────────────────────

# USD pip value per standard lot, approximate for common pairs.
# For non-USD quote pairs this is an estimate; precise values require
# live exchange rate conversion which MT5 can provide when wired.
_PIP_VALUE_PER_LOT: dict[str, float] = {
    "EURUSD": 10.0, "GBPUSD": 10.0, "AUDUSD": 10.0,
    "NZDUSD": 10.0, "USDCAD": 7.7,  "USDCHF": 10.9,
    "USDJPY": 6.9,
}
_DEFAULT_PIP_VALUE = 10.0


def calculate_lot_size(
    account_balance: float,
    risk_percent: float,
    stop_loss_pips: float,
    pair: str,
) -> float:
    """Return lot size (standard lots) to risk exactly risk_percent of balance.

    Minimum lot: 0.01. Result rounded to 2 decimal places.
    """
    if stop_loss_pips <= 0 or account_balance <= 0:
        return 0.01

    risk_amount = account_balance * (risk_percent / 100.0)
    base = pair[:3].upper()
    quote = pair[3:6].upper()

    # Approximate pip value in account currency (USD assumed)
    pip_val = _PIP_VALUE_PER_LOT.get(pair.upper(), _DEFAULT_PIP_VALUE)
    sl_value_per_lot = stop_loss_pips * pip_val

    lots = risk_amount / sl_value_per_lot
    return max(0.01, round(lots, 2))
