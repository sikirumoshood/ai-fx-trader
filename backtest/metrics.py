from __future__ import annotations

import math
from typing import Any


# ── Main metrics calculation ──────────────────────────────────────────────────

def compute(records: list[dict]) -> dict[str, Any]:
    """Compute all backtest metrics from a list of signal records.

    Each record must have (at minimum):
        direction         str   "BUY" | "SELL" | "SKIP"
        actual_pips       float | None  (None = SKIP)
        predicted_pips    float | None
        direction_correct bool  | None
        confidence        float | None
        news_bias         str   | None
        session           str   | None
        candle_time       datetime

    Returns a metrics dict ready for storage in BacktestMetric.
    """
    traded   = [r for r in records if r.get("direction") != "SKIP" and r.get("actual_pips") is not None]
    skipped  = [r for r in records if r.get("direction") == "SKIP"]

    if not traded:
        return _empty_metrics(len(records), len(skipped))

    wins   = [r for r in traded if r["actual_pips"] > 0]
    losses = [r for r in traded if r["actual_pips"] <= 0]

    win_rate      = len(wins) / len(traded)
    profit_factor = _profit_factor(wins, losses)
    sharpe        = _sharpe_ratio([r["actual_pips"] for r in traded])
    max_dd        = _max_drawdown([r["actual_pips"] for r in traded])
    total_return  = sum(r["actual_pips"] for r in traded)
    dir_correct   = [r for r in traded if r.get("direction_correct")]
    dir_acc       = len(dir_correct) / len(traded)

    return {
        "total_signals":   len(records),
        "skipped":         len(skipped),
        "traded":          len(traded),
        "win_rate":        round(win_rate, 4),
        "profit_factor":   round(profit_factor, 3),
        "sharpe_ratio":    round(sharpe, 3),
        "max_drawdown":    round(max_dd, 4),
        "total_return":    round(total_return, 1),
        "directional_acc": round(dir_acc, 4),
        "by_session":      _breakdown_by(traded, "session"),
        "by_confidence":   _breakdown_by_confidence(traded),
        "by_news_impact":  _breakdown_by(traded, "news_bias"),
        "equity_curve":    _equity_curve([r["actual_pips"] for r in traded]),
    }


# ── Breakdown helpers ─────────────────────────────────────────────────────────

def _breakdown_by(records: list[dict], field: str) -> dict[str, Any]:
    groups: dict[str, list] = {}
    for r in records:
        key = str(r.get(field) or "UNKNOWN")
        groups.setdefault(key, []).append(r["actual_pips"])

    result = {}
    for key, pips in groups.items():
        wins = [p for p in pips if p > 0]
        result[key] = {
            "trades":     len(pips),
            "win_rate":   round(len(wins) / len(pips), 4) if pips else 0,
            "total_pips": round(sum(pips), 1),
            "avg_pips":   round(sum(pips) / len(pips), 2) if pips else 0,
        }
    return result


def _breakdown_by_confidence(records: list[dict]) -> dict[str, Any]:
    """Bucket records into confidence tiers: 0.5-0.6, 0.6-0.7, 0.7+"""
    buckets = {
        "0.50-0.60": [],
        "0.60-0.70": [],
        "0.70+":     [],
    }
    for r in records:
        conf = r.get("confidence") or 0.0
        if conf < 0.60:
            buckets["0.50-0.60"].append(r["actual_pips"])
        elif conf < 0.70:
            buckets["0.60-0.70"].append(r["actual_pips"])
        else:
            buckets["0.70+"].append(r["actual_pips"])

    result = {}
    for key, pips in buckets.items():
        if not pips:
            continue
        wins = [p for p in pips if p > 0]
        result[key] = {
            "trades":     len(pips),
            "win_rate":   round(len(wins) / len(pips), 4),
            "total_pips": round(sum(pips), 1),
            "avg_pips":   round(sum(pips) / len(pips), 2),
        }
    return result


# ── Statistical helpers ───────────────────────────────────────────────────────

def _profit_factor(wins: list[dict], losses: list[dict]) -> float:
    gross_profit = sum(r["actual_pips"] for r in wins)
    gross_loss   = abs(sum(r["actual_pips"] for r in losses))
    if gross_loss == 0:
        return float("inf") if gross_profit > 0 else 0.0
    return gross_profit / gross_loss


def _sharpe_ratio(pips: list[float], risk_free: float = 0.0) -> float:
    if len(pips) < 2:
        return 0.0
    n    = len(pips)
    mean = sum(pips) / n
    variance = sum((p - mean) ** 2 for p in pips) / (n - 1)
    std  = math.sqrt(variance)
    if std == 0:
        return 0.0
    # Annualise assuming H1 candles: sqrt(6240) trading hours/year
    return round((mean - risk_free) / std * math.sqrt(6240), 3)


def _max_drawdown(pips: list[float]) -> float:
    """Maximum peak-to-trough drawdown in absolute pips."""
    if not pips:
        return 0.0
    peak = 0.0
    equity = 0.0
    max_dd = 0.0
    for p in pips:
        equity += p
        if equity > peak:
            peak = equity
        dd = peak - equity
        if dd > max_dd:
            max_dd = dd
    return max_dd


def _equity_curve(pips: list[float]) -> list[float]:
    """Running cumulative pip total."""
    curve = []
    total = 0.0
    for p in pips:
        total += p
        curve.append(round(total, 1))
    return curve


def _empty_metrics(total: int, skipped: int) -> dict[str, Any]:
    return {
        "total_signals":   total,
        "skipped":         skipped,
        "traded":          0,
        "win_rate":        0.0,
        "profit_factor":   0.0,
        "sharpe_ratio":    0.0,
        "max_drawdown":    0.0,
        "total_return":    0.0,
        "directional_acc": 0.0,
        "by_session":      {},
        "by_confidence":   {},
        "by_news_impact":  {},
        "equity_curve":    [],
    }
