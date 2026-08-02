# AI FX Trader

An IFVG (Inverse Fair Value Gap) based FX trading server. Reads live OHLCV data from MetaTrader 5, detects IFVG patterns on M1 candles, applies a trend filter, and generates BUY/SELL signals via a REST API. Signals can be auto-executed immediately or confirmed manually.

---

## Architecture

```
MT5 (live tick)
      │
      ▼
Candle closes → fetch last 102 closed M1 candles
      │
      ▼
Detect IFVG — scan for unmitigated FVG zones inverted by last closed candle
      │
      ▼
Trend filter — M1 EMA9 vs EMA20 over last 40 candles (BUY/SELL must match trend)
      │
      ▼
Signal created → LIMIT order at gap zone boundary
      │
      ├── Auto-executed (schedule: auto_execute=True) → placed on MT5 immediately
      └── Manual confirm (POST /signals/{id}/confirm) → placed on MT5
```

---

## Project Structure

```
ai-fx-trader/
├── config/
│   └── settings.py           # All config (MT5 creds, defaults) — env-driven
│
├── data/
│   ├── fetcher.py             # MT5 → OHLCV DataFrame
│   ├── mt5_bridge.py          # File-based bridge for Mac native MT5 (AiFxBridge EA)
│   └── store.py               # PostgreSQL ORM models + async session factory
│
├── news/
│   ├── calendar.py            # Forex Factory econ calendar scraper
│   └── sentiment.py           # FinBERT sentiment scoring (lazy-load)
│
├── signals/
│   ├── fvg.py                 # IFVG detection + FVGSignalEngine — core signal logic
│   ├── risk.py                # SL/TP calculation, lot sizing, pip value
│   └── filters.py             # Session, spread, trend filter (M1 EMA), momentum checks
│
├── execution/
│   └── trader.py              # MT5 order placement, modify SL/TP, close trade
│
├── scheduler/
│   └── jobs.py                # APScheduler singleton — cron + interval triggers
│
├── api/
│   ├── server.py              # FastAPI app, lifespan startup/shutdown, API key middleware
│   ├── schemas.py             # Pydantic request/response models
│   └── routes/
│       ├── signals.py         # /signals/* — list, confirm, reject
│       ├── schedules.py       # /schedules/* — CRUD + APScheduler + auto-execution
│       ├── trades.py          # /trades/* — MT5 + DB
│       └── system.py          # /health, /pairs, /backtest/*
│
├── backtest/
│   ├── runner.py              # Async IFVG backtester, persists to DB
│   └── metrics.py             # Sharpe, drawdown, win rate, profit factor, breakdowns
│
├── frontend/                  # Next.js 15 dashboard
│   ├── app/                   # App Router pages
│   │   ├── page.tsx           # Dashboard overview
│   │   ├── signals/page.tsx   # Signal list + confirm/reject
│   │   ├── schedules/page.tsx # Schedule CRUD + pause/resume
│   │   ├── trades/page.tsx    # Open/closed trade management
│   │   └── backtest/page.tsx  # Backtest runner + results + equity curve
│   ├── components/
│   │   ├── layout/            # Sidebar + Header
│   │   ├── ui/                # Badge, Button, Card, Dialog, Input, Label, Select
│   │   ├── signals/           # SignalTable, DirectionBadge
│   │   ├── schedules/         # ScheduleTable, CreateScheduleForm
│   │   └── backtest/          # BacktestForm, BacktestResults (equity curve chart)
│   └── lib/
│       ├── api.ts             # Full API client (all endpoints, X-API-Key auth)
│       ├── types.ts           # All TypeScript interfaces
│       └── utils.ts           # cn, formatPrice, formatPips
│
├── migrations/                # Alembic DB migrations
├── main.py                    # Starts FastAPI server (uvicorn)
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .env.example
```

---

## Key Components

### `config/settings.py`
All configuration loaded from environment variables. Key groups:
- **MT5**: login, password, server, terminal path, bridge files path
- **Signal defaults**: timeframe (M1), SL pips (20), R:R (2.0), signal expiry (5 min)
- **Supported timeframes**: M1, M5, M15, M30, H1, H4, D1, W1, MN1
- **Supported pairs**: all FX majors, minors, selected exotics, plus `XAUUSD` (Gold)
- **Sessions**: active trading sessions (`LONDON`, `NEW_YORK`) — configurable per schedule
- **API**: key (`X-API-Key` header), host/port
- **Database**: async PostgreSQL URL
- **Notifications**: Telegram + Resend email (opt-in per schedule)

### `data/fetcher.py`
MT5 data layer. Priority connection order:
1. **AiFxBridge** — file-based bridge to Mac native MT5 app via MQL5 EA
2. **mt5linux** — Docker RPyC bridge (Linux)
3. **MetaTrader5 package** — Windows native

Key functions: `initialize()`, `shutdown()`, `fetch_ohlcv()`, `fetch_ohlcv_range()`, `get_account_balance()`, `get_current_spread_pips()`

### `signals/fvg.py`
Core signal engine. IFVG detection logic:

**FVG formation:**
- Bullish FVG: `candle[i].low > candle[i-2].high` — gap above, closed by upward momentum
- Bearish FVG: `candle[i].high < candle[i-2].low` — gap below, closed by downward momentum

**IFVG inversion (signal trigger):**
- Bullish FVG inverted: last candle closes **below** `zone.min` → **SELL** limit at `zone.min`
- Bearish FVG inverted: last candle closes **above** `zone.max` → **BUY** limit at `zone.max`

Entry is placed at the near edge of the zone (where the gap starts), waiting for price to retrace to that level.

**Mitigation:** a zone is removed if any subsequent candle closes through the far edge — meaning the gap was already inverted by an earlier candle.

**Trend filter:** M1 EMA9 vs EMA20 over the last 40 candles. Signal direction must match the trend; counter-trend IFVGs are blocked. Flat/unclear trend is also blocked.

### `signals/risk.py`
- `calculate_sl_tp()` — pip-based SL/TP from entry using `stop_loss_pips` and `risk_reward`
- `calculate_lot_size()` — risk % of balance
- `calculate_lot_size_from_amount()` — risk fixed dollar amount
- `_live_pip_value_per_lot()` — live pip value from MT5 rates (falls back to static table)
- `price_decimals(pair)` — correct decimal places per pair (2 for JPY/XAU, 5 for others)

**Auto Close at Profit** (`auto_close_profit` on schedule): overrides the R:R-based TP with a price computed from `auto_close_profit_amount` in account currency:
```
tp_pips = auto_close_profit_amount / (pip_value_per_lot × lot_size)
```
SL is derived from `max_risk_amount` if set, otherwise from `auto_close_profit_amount / risk_reward` to enforce R:R. Requires `auto_execute=True`.

### `signals/filters.py`
- `check_session()` — current UTC time within configured session windows
- `trend_from_candles()` — M1 EMA9 vs EMA20 over last 40 candles for trend direction
- `m1_market_bias()` — momentum scoring: EMA crossover + body dominance + net pip displacement

### `execution/trader.py`
MT5 order management. Uses magic number `20260101` to identify system orders. Key functions: `place_order()`, `place_pending_order()`, `cancel_pending_order()`, `modify_trade()`, `close_trade()`, `get_open_positions()`, `get_pending_orders()`, `get_closed_deals()`.

### `scheduler/jobs.py`
Singleton `AsyncIOScheduler`. Supports standard 5-field crontab expressions **and** interval shorthand (e.g. `1s`, `5s`, `30s`) for sub-minute scheduling — critical for M1 IFVG detection to catch inversions as close to candle close as possible.

Functions: `add_schedule()`, `remove_schedule()`, `pause_schedule()`, `resume_schedule()`, `get_next_run()`, `register_maintenance_jobs()` (purges old schedule_executions at midnight UTC).

### `api/server.py`
FastAPI app. Lifespan: runs Alembic migrations → connects MT5 → starts APScheduler → restores active schedules from DB. All endpoints require `X-API-Key` header except `/health` and `/docs`.

### `backtest/runner.py`
IFVG backtester. `submit_run()` creates a `BacktestRun` DB record and fires a background task. Outcome is determined by `_simulate_zone_excursion`: after each inversion candle, the next 10 candles are scanned for the highest high and lowest low; the excursion that extends furthest beyond the FVG zone boundary wins. Session labeling uses the matched session name from `check_session` directly.

---

## Schedule Auto-Execution

When `auto_execute=True` on a schedule, signals are placed on MT5 automatically without manual confirmation. Key options:

| Field | Description |
|-------|-------------|
| `auto_lot_size` | Fixed lot size per trade — recommended when `auto_close_profit` is set |
| `max_risk_amount` | Max loss in account currency if SL is hit — used for lot sizing and SL price |
| `auto_close_profit` | Override TP with a fixed dollar profit target |
| `auto_close_profit_amount` | Target profit per trade in account currency |
| `risk_reward` | Used to derive SL from TP when `max_risk_amount` is not set |

**Lot size priority:** `auto_lot_size` → `max_risk_amount` → `risk_percent` of balance

**SL/TP override when `auto_close_profit=True`:**
```
tp_pips = auto_close_profit_amount / (pip_val × lot_size)
sl_amount = max_risk_amount  OR  auto_close_profit_amount / risk_reward
sl_pips = sl_amount / (pip_val × lot_size)
```

The dedup check prevents more than 2 open positions per pair at any time.

---

## API Overview

### Signals
| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET`  | `/signals` | List all signals |
| `GET`  | `/signals/{id}` | Get signal detail |
| `POST` | `/signals/{id}/confirm` | Execute signal on MT5 |
| `POST` | `/signals/{id}/reject` | Reject signal |

### Schedules
| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST`   | `/schedules` | Create monitoring schedule |
| `GET`    | `/schedules` | List all schedules |
| `GET`    | `/schedules/{id}` | Get schedule detail |
| `PATCH`  | `/schedules/{id}` | Update params |
| `DELETE` | `/schedules/{id}` | Cancel schedule |
| `POST`   | `/schedules/{id}/pause` | Pause schedule |
| `POST`   | `/schedules/{id}/resume` | Resume schedule |
| `GET`    | `/schedules/{id}/executions` | Execution history |

### Trades
| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET`    | `/trades` | List open and closed trades |
| `GET`    | `/trades/{id}` | Get trade detail |
| `PATCH`  | `/trades/{id}` | Modify SL/TP |
| `DELETE` | `/trades/{id}` | Close trade on MT5 |

### System
| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Server + MT5 + DB status |
| `GET` | `/pairs` | Available trading pairs |
| `POST` | `/backtest` | Submit IFVG backtest job |
| `GET`  | `/backtest/{job_id}` | Poll backtest status |
| `GET`  | `/backtest/{job_id}/results` | Fetch backtest results |
| `GET`  | `/backtests` | List all backtest runs |

---

## Quick Start

### 1. Configure environment
```bash
cp .env.example .env
# edit .env with your MT5 credentials and API key
```

### 2. Configure the frontend
```bash
cp frontend/.env.local.example frontend/.env.local
# set NEXT_PUBLIC_API_KEY to match FX_API_KEY in .env
```

### 3. Start all services
```bash
docker-compose up -d
```

- **Dashboard**: http://localhost:3000
- **API docs**: http://localhost:8022/docs

### 4. Run locally (without Docker)
```bash
# Terminal 1 — API
pip install -r requirements.txt
python main.py

# Terminal 2 — Frontend
cd frontend && npm install && npm run dev
```

### 5. Check health
```bash
curl http://localhost:8022/health
```

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.11+ |
| API | FastAPI + Uvicorn |
| Validation | Pydantic v2 |
| MT5 interface | AiFxBridge (file-based EA) / MetaTrader5 package |
| Signal strategy | IFVG (Inverse Fair Value Gap) |
| Sentiment | FinBERT (`ProsusAI/finbert`, local) |
| Database | PostgreSQL (async via SQLAlchemy + asyncpg) |
| Migrations | Alembic |
| Scheduling | APScheduler (cron + interval triggers) |
| Data processing | pandas |
| Containerisation | Docker + docker-compose |
