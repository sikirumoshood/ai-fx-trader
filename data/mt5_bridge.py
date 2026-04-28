"""
File-based bridge client for AiFxBridge.mq5.

The EA polls a shared folder (MT5 Common/Files) for request files and writes
response files. Python writes the request, waits for the request file to
disappear (EA's signal that the response is written), then reads the response.

Implements the same interface used by the native MetaTrader5 package so
fetcher.py can use it transparently.
"""
from __future__ import annotations

import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


_TIMEOUT = 15   # seconds to wait for EA to respond
_MAGIC   = 20260101
_RETCODE_DONE = 10009   # TRADE_RETCODE_DONE

_REQ_FILE = "aifx_req.txt"
_RES_FILE = "aifx_res.txt"


# ── Result / info stubs ───────────────────────────────────────────────────────

class _Tick:
    __slots__ = ("bid", "ask", "time")
    def __init__(self, bid: float, ask: float, time: int):
        self.bid  = bid
        self.ask  = ask
        self.time = time


class _SymbolInfo:
    __slots__ = ("spread", "point")
    def __init__(self, spread: int, point: float):
        self.spread = spread
        self.point  = point


class _AccountInfo:
    __slots__ = ("balance", "equity", "margin_free", "connected")
    def __init__(self, balance: float, equity: float, margin_free: float):
        self.balance     = balance
        self.equity      = equity
        self.margin_free = margin_free
        self.connected   = True


class _TerminalInfo:
    connected = True


class _Symbol:
    __slots__ = ("name", "visible")
    def __init__(self, name: str):
        self.name    = name
        self.visible = True


class _Position:
    __slots__ = (
        "ticket", "symbol", "type", "volume",
        "price_open", "sl", "tp", "profit", "time", "magic",
    )


class _Deal:
    __slots__ = (
        "ticket", "order", "symbol", "type",
        "volume", "price", "profit", "time", "comment", "magic",
    )


class _OrderResult:
    __slots__ = ("retcode", "order", "price", "volume", "comment")
    def __init__(self, retcode: int, order: int = 0, price: float = 0.0,
                 volume: float = 0.0, comment: str = ""):
        self.retcode = retcode
        self.order   = order
        self.price   = price
        self.volume  = volume
        self.comment = comment


# ── Bridge client ─────────────────────────────────────────────────────────────

class MT5Bridge:
    """File-based client for the AiFxBridge.mq5 Expert Advisor."""

    # Constants matching MetaTrader5 package integers
    TIMEFRAME_M1  = "M1"
    TIMEFRAME_M5  = "M5"
    TIMEFRAME_M15 = "M15"
    TIMEFRAME_M30 = "M30"
    TIMEFRAME_H1  = "H1"
    TIMEFRAME_H4  = "H4"
    TIMEFRAME_D1  = "D1"
    TIMEFRAME_W1  = "W1"
    TIMEFRAME_MN1 = "MN1"

    ORDER_TYPE_BUY  = 0
    ORDER_TYPE_SELL = 1

    TRADE_ACTION_DEAL = 1
    TRADE_ACTION_SLTP = 6

    ORDER_TIME_GTC    = 1
    ORDER_FILLING_IOC = 1

    TRADE_RETCODE_DONE = _RETCODE_DONE

    def __init__(self, files_path: str) -> None:
        self._dir  = Path(files_path)
        self._lock = threading.Lock()

    # ── Connection ────────────────────────────────────────────────────────────

    def connect(self) -> bool:
        """Verify the shared folder exists and the EA is responding."""
        if not self._dir.exists():
            return False
        try:
            resp = self._send_recv("PING")
            return resp.startswith("OK")
        except Exception:
            return False

    def shutdown(self) -> None:
        req = self._dir / _REQ_FILE
        res = self._dir / _RES_FILE
        req.unlink(missing_ok=True)
        res.unlink(missing_ok=True)

    # ── Low-level I/O ─────────────────────────────────────────────────────────

    def _send_recv(self, command: str) -> str:
        req_path = self._dir / _REQ_FILE
        res_path = self._dir / _RES_FILE

        with self._lock:
            # Remove stale files from a previous failed call
            req_path.unlink(missing_ok=True)
            res_path.unlink(missing_ok=True)

            # Write request
            req_path.write_text(command + "\n", encoding="ascii")

            # Wait for EA to consume the request file (EA deletes it after
            # writing the response — guarantees response is fully flushed)
            deadline = time.monotonic() + _TIMEOUT
            while req_path.exists():
                if time.monotonic() > deadline:
                    req_path.unlink(missing_ok=True)
                    raise RuntimeError(
                        "AiFxBridge timeout — is the EA attached to a chart?"
                    )
                time.sleep(0.05)

            # Read response
            if not res_path.exists():
                raise RuntimeError("AiFxBridge: response file missing")
            response = res_path.read_text(encoding="ascii").strip()
            res_path.unlink(missing_ok=True)
            return response

    def _ok(self, response: str) -> list[str]:
        parts = response.split("|")
        if parts[0] != "OK":
            raise RuntimeError(parts[1] if len(parts) > 1 else "Bridge error")
        return parts[1:]

    # ── MT5 interface (mirrors MetaTrader5 package) ───────────────────────────

    def terminal_info(self) -> _TerminalInfo:
        try:
            self._send_recv("PING")
            return _TerminalInfo()
        except Exception:
            return None  # type: ignore[return-value]

    def last_error(self):
        return (0, "No error")

    def symbol_info_tick(self, symbol: str) -> Optional[_Tick]:
        try:
            parts = self._ok(self._send_recv(f"TICK|{symbol}"))
            return _Tick(float(parts[0]), float(parts[1]), int(parts[2]))
        except Exception:
            return None

    def symbol_info(self, symbol: str) -> Optional[_SymbolInfo]:
        try:
            parts = self._ok(self._send_recv(f"SYMBOL_INFO|{symbol}"))
            return _SymbolInfo(int(parts[0]), float(parts[1]))
        except Exception:
            return None

    def copy_rates_from_pos(
        self, symbol: str, timeframe: str, pos: int, count: int
    ) -> list[dict]:
        resp  = self._send_recv(f"OHLCV|{symbol}|{timeframe}|{count}")
        parts = self._ok(resp)
        return [_parse_rate(r) for r in parts if r]

    def copy_rates_range(
        self, symbol: str, timeframe: str, start: datetime, end: datetime
    ) -> list[dict]:
        from_ts = int(start.timestamp())
        to_ts   = int(end.timestamp())
        resp    = self._send_recv(f"OHLCV_RANGE|{symbol}|{timeframe}|{from_ts}|{to_ts}")
        parts   = self._ok(resp)
        return [_parse_rate(r) for r in parts if r]

    def account_info(self) -> Optional[_AccountInfo]:
        try:
            parts = self._ok(self._send_recv("ACCOUNT"))
            return _AccountInfo(float(parts[0]), float(parts[1]), float(parts[2]))
        except Exception:
            return None

    def symbols_get(self) -> list[_Symbol]:
        try:
            parts = self._ok(self._send_recv("SYMBOLS"))
            return [_Symbol(n) for n in parts if n]
        except Exception:
            return []

    def positions_get(
        self, symbol: Optional[str] = None, ticket: Optional[int] = None
    ) -> list[_Position]:
        try:
            parts  = self._ok(self._send_recv("POSITIONS"))
            result = []
            for record in parts:
                if not record:
                    continue
                p = _parse_position(record)
                if symbol is not None and p.symbol != symbol:
                    continue
                if ticket is not None and p.ticket != ticket:
                    continue
                result.append(p)
            return result
        except Exception:
            return []

    def history_deals_get(
        self, date_from: datetime, date_to: datetime
    ) -> list[_Deal]:
        days = max(1, int((date_to - date_from).total_seconds() / 86400))
        try:
            parts = self._ok(self._send_recv(f"HISTORY|{days}"))
            return [_parse_deal(r) for r in parts if r]
        except Exception:
            return []

    def order_send(self, request: dict) -> _OrderResult:
        action = request.get("action")
        try:
            if action == self.TRADE_ACTION_DEAL:
                if "position" in request:
                    parts = self._ok(self._send_recv(f"CLOSE|{request['position']}"))
                    return _OrderResult(_RETCODE_DONE, price=float(parts[0]))
                else:
                    otype = "BUY" if request["type"] == self.ORDER_TYPE_BUY else "SELL"
                    parts = self._ok(self._send_recv(
                        f"ORDER|{request['symbol']}|{otype}"
                        f"|{request['volume']}|{request['price']}"
                        f"|{request['sl']}|{request['tp']}"
                        f"|{request.get('comment', 'aifx')}"
                    ))
                    return _OrderResult(
                        _RETCODE_DONE,
                        order=int(parts[0]),
                        price=float(parts[1]),
                        volume=float(parts[2]),
                    )
            elif action == self.TRADE_ACTION_SLTP:
                sl = request.get("sl", 0.0)
                tp = request.get("tp", 0.0)
                self._ok(self._send_recv(f"MODIFY|{request['position']}|{sl}|{tp}"))
                return _OrderResult(_RETCODE_DONE)
            else:
                return _OrderResult(10004, comment=f"Unknown action: {action}")
        except RuntimeError as exc:
            return _OrderResult(10006, comment=str(exc))


# ── Record parsers ────────────────────────────────────────────────────────────

def _parse_rate(record: str) -> dict:
    f = record.split(",")
    return {
        "time":        int(f[0]),
        "open":        float(f[1]),
        "high":        float(f[2]),
        "low":         float(f[3]),
        "close":       float(f[4]),
        "tick_volume": int(f[5]),
        "spread":      int(f[6]),
    }


def _parse_position(record: str) -> _Position:
    f = record.split(",")
    p = _Position()
    p.ticket     = int(f[0])
    p.symbol     = f[1]
    p.type       = int(f[2])
    p.volume     = float(f[3])
    p.price_open = float(f[4])
    p.sl         = float(f[5])
    p.tp         = float(f[6])
    p.profit     = float(f[7])
    p.time       = int(f[8])
    p.magic      = _MAGIC
    return p


def _parse_deal(record: str) -> _Deal:
    f = record.split(",")
    d = _Deal()
    d.ticket  = int(f[0])
    d.order   = int(f[1])
    d.symbol  = f[2]
    d.type    = int(f[3])
    d.volume  = float(f[4])
    d.price   = float(f[5])
    d.profit  = float(f[6])
    d.time    = int(f[7])
    d.comment = f[8] if len(f) > 8 else ""
    d.magic   = _MAGIC
    return d
