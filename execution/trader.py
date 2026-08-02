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


def _send_order(m, request: dict):
    """Send a single order to MT5. No retries — retrying order placement risks duplicates."""
    result = m.order_send(request)
    if result is None:
        raise RuntimeError(f"order_send returned None: {m.last_error()}")
    return result


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

    result = _send_order(m, request)
    if result.retcode != m.TRADE_RETCODE_DONE:
        raise RuntimeError(f"Order failed: retcode={result.retcode} comment={result.comment}")

    return {"ticket": result.order, "price": result.price, "volume": result.volume, "success": True}


# ── Pending order placement ───────────────────────────────────────────────────

def place_pending_order(
    *,
    pair: str,
    direction: str,
    order_type: str,   # "LIMIT" or "STOP"
    entry: float,
    lot_size: float,
    stop_loss: float,
    take_profit: float,
    signal_id: str,
) -> dict:
    """Place a pending (limit or stop) order on MT5."""
    m = _mt5()

    _mt5_type = {
        ("BUY",  "LIMIT"): m.ORDER_TYPE_BUY_LIMIT,
        ("SELL", "LIMIT"): m.ORDER_TYPE_SELL_LIMIT,
        ("BUY",  "STOP"):  m.ORDER_TYPE_BUY_STOP,
        ("SELL", "STOP"):  m.ORDER_TYPE_SELL_STOP,
    }.get((direction, order_type))
    if _mt5_type is None:
        raise RuntimeError(f"Invalid pending order type: {direction} {order_type}")

    request = {
        "action":    m.TRADE_ACTION_PENDING,
        "symbol":    pair,
        "volume":    lot_size,
        "type":      _mt5_type,
        "price":     entry,
        "sl":        stop_loss,
        "tp":        take_profit,
        "magic":     _MAGIC,
        "comment":   f"aifx:{signal_id[:8]}",
        "type_time": m.ORDER_TIME_GTC,
    }
    result = m.order_send(request)
    if result is None or result.retcode != m.TRADE_RETCODE_DONE:
        error = result.comment if result else m.last_error()
        raise RuntimeError(f"Pending order failed: retcode={getattr(result, 'retcode', None)} comment={error}")

    return {"ticket": result.order, "price": entry, "volume": result.volume, "success": True}


def cancel_pending_order(ticket: int) -> dict:
    """Cancel a pending (unfilled) order on MT5."""
    m = _mt5()
    request = {"action": m.TRADE_ACTION_REMOVE, "order": ticket}
    result = m.order_send(request)
    if result is None or result.retcode != m.TRADE_RETCODE_DONE:
        error = result.comment if result else m.last_error()
        raise RuntimeError(f"Cancel failed: {error}")
    return {"ticket": ticket, "success": True}


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
    result = _send_order(m, request)
    if result.retcode != m.TRADE_RETCODE_DONE:
        raise RuntimeError(f"Close failed: retcode={result.retcode} comment={result.comment}")

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


def get_pending_orders(pair: Optional[str] = None) -> list[dict]:
    """Return unfilled limit/stop pending orders placed by this system."""
    if not _is_available():
        return []
    m = _mt5()
    orders = m.orders_get(symbol=pair) if pair else m.orders_get()
    if orders is None:
        return []
    return [
        {"ticket": o.ticket, "pair": o.symbol, "type": o.type, "volume": o.volume_initial}
        for o in orders if o.magic == _MAGIC
    ]


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
