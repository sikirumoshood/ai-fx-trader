from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from config.settings import pip_size
from data.fetcher import _is_available

# Magic number used to identify orders placed by this system
_MAGIC     = 20260101
_DEVIATION = 10  # max price deviation in points


def _mt5():
    """Return the active MT5 connection, or raise if not connected."""
    if not _is_available():
        raise RuntimeError("MT5 not connected")
    from data.fetcher import _mt5 as _conn
    return _conn


def _filling_modes(m) -> list[int]:
    """Return available filling modes in retry order."""
    modes: list[int] = []
    for name in ("ORDER_FILLING_IOC", "ORDER_FILLING_FOK", "ORDER_FILLING_RETURN"):
        value = getattr(m, name, None)
        if isinstance(value, int) and value not in modes:
            modes.append(value)
    return modes


def _is_unsupported_filling(result) -> bool:
    if result is None:
        return False
    comment = (getattr(result, "comment", "") or "").lower()
    return getattr(result, "retcode", None) == 10030 or "unsupported filling mode" in comment


def _send_order_with_filling_fallback(m, request: dict):
    """Try broker-supported filling modes before failing."""
    last_result = None
    tried_modes: list[int] = []
    for mode in _filling_modes(m):
        tried_modes.append(mode)
        req = dict(request)
        req["type_filling"] = mode
        result = m.order_send(req)
        if result is None:
            last_result = None
            continue
        if result.retcode == m.TRADE_RETCODE_DONE:
            return result
        last_result = result
        if not _is_unsupported_filling(result):
            return result

    # Fallback: send once without type_filling for bridges/adapters that ignore it.
    req = dict(request)
    req.pop("type_filling", None)
    result = m.order_send(req)
    if result is not None:
        return result

    if last_result is not None:
        return last_result
    tried = ",".join(str(v) for v in tried_modes) if tried_modes else "none"
    raise RuntimeError(f"order_send returned None (filling modes tried: {tried}): {m.last_error()}")


# ── Order placement ───────────────────────────────────────────────────────────

def place_order(
    *,
    pair: str,
    direction: str,
    lot_size: float,
    stop_loss: float,
    take_profit: float,
    signal_id: str,
) -> dict:
    """Place a market order on MT5. Only called after explicit signal confirmation."""
    m = _mt5()
    tick = m.symbol_info_tick(pair)
    if tick is None:
        raise RuntimeError(f"Cannot get tick for {pair}")

    if direction == "BUY":
        order_type = m.ORDER_TYPE_BUY
        price = tick.ask
    else:
        order_type = m.ORDER_TYPE_SELL
        price = tick.bid

    request = {
        "action":       m.TRADE_ACTION_DEAL,
        "symbol":       pair,
        "volume":       lot_size,
        "type":         order_type,
        "price":        price,
        "sl":           stop_loss,
        "tp":           take_profit,
        "deviation":    _DEVIATION,
        "magic":        _MAGIC,
        "comment":      f"aifx:{signal_id[:8]}",
        "type_time":    m.ORDER_TIME_GTC,
    }

    result = _send_order_with_filling_fallback(m, request)
    if result.retcode != m.TRADE_RETCODE_DONE:
        raise RuntimeError(f"Order failed: retcode={result.retcode} comment={result.comment}")

    return {"ticket": result.order, "price": result.price, "volume": result.volume, "success": True}


# ── Modify open trade ─────────────────────────────────────────────────────────

def modify_trade(
    *,
    ticket: int,
    stop_loss: Optional[float] = None,
    take_profit: Optional[float] = None,
) -> dict:
    m = _mt5()
    position = _get_position(ticket, m)
    if position is None:
        raise RuntimeError(f"Position {ticket} not found")

    request = {
        "action":   m.TRADE_ACTION_SLTP,
        "position": ticket,
        "sl":       stop_loss   if stop_loss   is not None else position.sl,
        "tp":       take_profit if take_profit is not None else position.tp,
    }
    result = m.order_send(request)
    if result is None or result.retcode != m.TRADE_RETCODE_DONE:
        error = result.comment if result else m.last_error()
        raise RuntimeError(f"Modify failed: {error}")

    return {"ticket": ticket, "success": True}


# ── Close trade ───────────────────────────────────────────────────────────────

def close_trade(ticket: int) -> dict:
    m = _mt5()
    position = _get_position(ticket, m)
    if position is None:
        raise RuntimeError(f"Position {ticket} not found")

    direction = m.ORDER_TYPE_SELL if position.type == m.ORDER_TYPE_BUY else m.ORDER_TYPE_BUY
    tick  = m.symbol_info_tick(position.symbol)
    price = tick.bid if direction == m.ORDER_TYPE_SELL else tick.ask

    request = {
        "action":       m.TRADE_ACTION_DEAL,
        "position":     ticket,
        "symbol":       position.symbol,
        "volume":       position.volume,
        "type":         direction,
        "price":        price,
        "deviation":    _DEVIATION,
        "magic":        _MAGIC,
        "comment":      "aifx:close",
        "type_time":    m.ORDER_TIME_GTC,
    }
    result = _send_order_with_filling_fallback(m, request)
    if result is None or result.retcode != m.TRADE_RETCODE_DONE:
        error = result.comment if result else m.last_error()
        raise RuntimeError(f"Close failed: {error}")

    return {"ticket": ticket, "close_price": result.price, "success": True}


# ── Open positions ────────────────────────────────────────────────────────────

def get_open_positions(pair: Optional[str] = None) -> list[dict]:
    if not _is_available():
        return []
    m = _mt5()
    positions = m.positions_get(symbol=pair) if pair else m.positions_get()
    if positions is None:
        return []
    return [_position_to_dict(p) for p in positions if p.magic == _MAGIC]


def get_closed_deals(pair: Optional[str] = None) -> list[dict]:
    if not _is_available():
        return []
    m = _mt5()
    now   = datetime.now(timezone.utc)
    deals = m.history_deals_get(now - timedelta(days=30), now)
    if deals is None:
        return []
    result = [d for d in deals if d.magic == _MAGIC]
    if pair:
        result = [d for d in result if d.symbol == pair]
    return [_deal_to_dict(d) for d in result]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_position(ticket: int, m):
    positions = m.positions_get(ticket=ticket)
    return positions[0] if positions else None


def _position_to_dict(p) -> dict:
    return {
        "ticket":     p.ticket,
        "symbol":     p.symbol,
        "type":       "BUY" if p.type == 0 else "SELL",
        "volume":     p.volume,
        "open_price": p.price_open,
        "sl":         p.sl,
        "tp":         p.tp,
        "profit":     p.profit,
        "open_time":  datetime.fromtimestamp(p.time, tz=timezone.utc),
    }


def _deal_to_dict(d) -> dict:
    return {
        "ticket":  d.ticket,
        "order":   d.order,
        "symbol":  d.symbol,
        "type":    "BUY" if d.type == 0 else "SELL",
        "volume":  d.volume,
        "price":   d.price,
        "profit":  d.profit,
        "time":    datetime.fromtimestamp(d.time, tz=timezone.utc),
        "comment": d.comment,
    }
