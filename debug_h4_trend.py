"""
Diagnostic script: verify H4 trend detection for XAUUSD.

Fetches 600 closed H4 candles, computes EMA20 and EMA50, prints full
diagnostic output to stdout as JSON and logs the verdict.

Run from the project root:
    python debug_h4_trend.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone

# ── Bootstrap ─────────────────────────────────────────────────────────────────

from data import fetcher

connected = fetcher.initialize()
if not connected:
    print("ERROR: Could not connect to MT5. Check bridge/connection.", file=sys.stderr)
    sys.exit(1)

PAIR = "XAUUSD"
COUNT = 601  # 601 fetched → 600 closed (last bar still forming)

# ── Fetch ──────────────────────────────────────────────────────────────────────

print(f"Fetching {COUNT} H4 candles for {PAIR}...", flush=True)
candles = fetcher.fetch_ohlcv(PAIR, "H4", count=COUNT)
candles = candles.sort_values("time").reset_index(drop=True)
closed  = candles.iloc[:-1].copy()  # drop the still-forming bar

print(f"  Total fetched : {len(candles)}")
print(f"  Closed bars   : {len(closed)}")
print(f"  Oldest bar    : {closed['time'].iloc[0]}")
print(f"  Latest closed : {closed['time'].iloc[-1]}")
print(f"  Still-forming : {candles['time'].iloc[-1]}")
print()

if len(closed) < 50:
    print("ERROR: Fewer than 50 closed bars — insufficient for trend detection.")
    sys.exit(1)

# ── Compute EMAs ──────────────────────────────────────────────────────────────

closes   = closed["close"].astype(float).reset_index(drop=True)
ema20    = closes.ewm(span=20, adjust=False).mean()
ema50    = closes.ewm(span=50, adjust=False).mean()

price     = closes.iloc[-1]
ema20_val = ema20.iloc[-1]
ema50_val = ema50.iloc[-1]

price_above = price > ema50_val
ema_bullish = ema20_val > ema50_val

# ── Verdict ───────────────────────────────────────────────────────────────────

if ema_bullish and price_above:
    bias   = "BUY"
    detail = "Uptrend"
elif not ema_bullish and not price_above:
    bias   = "SELL"
    detail = "Downtrend"
else:
    bias   = None
    detail = "No clear 4H trend (conflicted)"

# ── Last 10 closed bars (for spot-check) ──────────────────────────────────────

last10 = closed.tail(10)[["time", "open", "high", "low", "close"]].copy()
last10["time"] = last10["time"].astype(str)
last10["ema20"] = ema20.tail(10).round(5).values
last10["ema50"] = ema50.tail(10).round(5).values

# ── Output ────────────────────────────────────────────────────────────────────

result = {
    "generated_at":    datetime.now(timezone.utc).isoformat(),
    "pair":            PAIR,
    "timeframe":       "H4",
    "bars_fetched":    len(candles),
    "bars_closed":     len(closed),
    "oldest_bar":      str(closed["time"].iloc[0]),
    "latest_closed":   str(closed["time"].iloc[-1]),
    "still_forming":   str(candles["time"].iloc[-1]),
    "price":           round(price, 5),
    "ema20":           round(ema20_val, 5),
    "ema50":           round(ema50_val, 5),
    "ema20_above_ema50": bool(ema_bullish),
    "price_above_ema50": bool(price_above),
    "bias":            bias,
    "detail":          detail,
    "last_10_bars":    last10.to_dict(orient="records"),
}

print("=" * 60)
print(json.dumps(result, indent=2))
print("=" * 60)
print()
print(f"VERDICT: bias={bias}  ({detail})")
print(f"  price     = {price:.5g}")
print(f"  EMA20     = {ema20_val:.5g}  ({'above' if ema_bullish else 'below'} EMA50)")
print(f"  EMA50     = {ema50_val:.5g}")
print(f"  price vs EMA50 : {'ABOVE' if price_above else 'BELOW'}")
print(f"  EMA20 vs EMA50 : {'BULLISH' if ema_bullish else 'BEARISH'}")
