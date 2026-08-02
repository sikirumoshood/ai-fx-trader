# AI FX Trader

An AI-powered FX trading server. Reads live OHLCV data from MetaTrader 5, predicts next candles using Kronos (a foundational time-series model), scores macro news with FinBERT, and generates BUY/SELL/SKIP signals via a REST API. Signals require explicit confirmation by default; schedules can optionally enable **auto-execution** to place trades immediately without manual intervention.

---

## Architecture

```
MT5 (live tick)
      │
      ▼
Candle closes → fetch last 400 OHLCV candles
      │
      ▼
Kronos predicts next N candles (O, H, L, C)
      │
      ▼
Rule-based filters (session, spread, volatility, news blackout)
      │
      ▼
FinBERT scores latest headlines + econ calendar impact
      │
      ▼
Signal Engine → BUY / SELL / SKIP
      │
      ▼
Signal created (status: PENDING) → returned via API
      │
      ├── POST /signals/{id}/confirm → EXECUTED on MT5
      └── POST /signals/{id}/reject  → REJECTED
```

---

## Project Structure

```
ai-fx-trader/
├── config/
│   └── settings.py           # All config (MT5 creds, model, defaults) — env-driven
│
├── data/
│   ├── fetcher.py             # MT5 → OHLCV DataFrame
│   └── store.py               # PostgreSQL ORM models + async session factory
│
├── model/
│   ├── base.py                # BasePredictor ABC — swap models via config
│   ├── kronos.py              # Kronos wrapper (lazy-load, confidence estimation)
│   ├── moirai.py              # Moirai wrapper (fallback)       [TODO]
│   └── tft.py                 # TFT wrapper (fallback)          [TODO]
│
├── news/
│   ├── calendar.py            # Forex Factory econ calendar scraper
│   └── sentiment.py           # FinBERT sentiment scoring (lazy-load)
│
├── signals/
│   ├── engine.py              # Full 14-step pipeline: MT5 → Kronos → FinBERT → Signal
│   ├── risk.py                # SL/TP calculation (pip-based, with optional predicted H/L to tighten SL)
│   └── filters.py             # Session, spread, confidence, min-pips, news blackout
│
├── execution/
│   └── trader.py              # MT5 order placement, modify SL/TP, close trade
│
├── scheduler/
│   └── jobs.py                # APScheduler singleton — add/pause/resume/remove cron jobs
│
├── api/
│   ├── server.py              # FastAPI app, lifespan startup/shutdown, API key middleware
│   ├── schemas.py             # Pydantic request/response models
│   └── routes/
│       ├── signals.py         # /signals/* — fully wired to engine + DB
│       ├── schedules.py       # /schedules/* — fully wired to APScheduler + DB
│       ├── trades.py          # /trades/* — fully wired to MT5 + DB
│       └── system.py          # /health (live checks), /pairs, /backtest/*
│
├── backtest/
│   ├── runner.py              # Async rolling-window backtester, persists to DB
│   └── metrics.py             # Sharpe, drawdown, win rate, profit factor, breakdowns
│
├── frontend/                  # Next.js 15 dashboard
│   ├── app/                   # App Router pages
│   │   ├── page.tsx           # Dashboard overview (stats + recent signals)
│   │   ├── signals/page.tsx   # Full signal list + analyze form
│   │   ├── schedules/page.tsx # Schedule CRUD + pause/resume
│   │   ├── trades/page.tsx    # Open/closed trade management
│   │   └── backtest/page.tsx  # Backtest runner + live results + equity curve
│   ├── components/
│   │   ├── layout/            # Sidebar + Header (with live MT5/model/DB status dots)
│   │   ├── ui/                # Badge, Button, Card, Dialog, Input, Label, Select
│   │   ├── signals/           # AnalyzeForm, SignalTable (with RSI column), DirectionBadge
│   │   ├── schedules/         # ScheduleTable, CreateScheduleForm
│   │   └── backtest/          # BacktestForm, BacktestResults (equity curve chart)
│   ├── lib/
│   │   ├── api.ts             # Full API client (all endpoints, X-API-Key auth)
│   │   ├── types.ts           # All TypeScript interfaces
│   │   └── utils.ts           # cn, formatPrice, formatPips, formatConfidence
│   ├── Dockerfile
│   └── .env.local.example
│
├── migrations/                # Alembic DB migrations
├── main.py                    # Starts FastAPI server (uvicorn)
├── Dockerfile
├── docker-compose.yml         # PostgreSQL + FastAPI + Next.js frontend
├── requirements.txt
└── .env.example               # Config template (never commit .env)
```

---

## Key Components

### `config/settings.py`
All configuration loaded from environment variables with sensible defaults. Key groups:
- **MT5**: login, password, server, terminal path
- **Kronos**: model variant (`Kronos-base`), device (`cpu`/`cuda:0`), context window (512), prediction length (5 candles)
- **Signal defaults**: timeframe (`H1`), min pips (15), SL pips (20), R:R (2.0), confidence threshold (0.62), signal expiry (5 min)
- **Supported timeframes**: M1, M5, M15, M30, H1, H4, D1, W1, MN1
- **Supported pairs**: all FX majors, minors, selected exotics, plus `XAUUSD` (Gold — pip size = 0.10)
- **Kronos sampling**: temperature (0.7), samples per call (5) — averaging reduces stochastic noise
- **Trend filter**: 12-candle lookback, 15-pip minimum momentum threshold (H1 meaningful moves only)
- **Sessions**: active trading sessions (`LONDON`, `NEW_YORK`) — configurable
- **API**: key (`X-API-Key` header), host/port
- **Database**: async PostgreSQL URL
- **Notifications**: Telegram (always-on when configured) + Resend email (opt-in per schedule, set `RESEND_API_KEY` and `RESEND_FROM_EMAIL`)

### `data/fetcher.py`
MT5 data layer. Key functions:

| Function | Description |
|----------|-------------|
| `initialize()` | Connect and log in to MT5 using `.env` credentials |
| `shutdown()` | Disconnect from MT5 |
| `is_connected()` | Check live connection status |
| `fetch_ohlcv(pair, timeframe, count)` | Fetch last N candles → DataFrame `[time, open, high, low, close, volume, spread]` |
| `fetch_ohlcv_range(pair, timeframe, start, end)` | Fetch candles in a date range (used by backtester) |
| `get_available_pairs()` | List all visible MT5 symbols |
| `get_current_spread_pips(pair)` | Live spread in pips |
| `get_account_balance()` | Account balance for position sizing |

### `data/store.py`
SQLAlchemy async ORM. Models:

| Table | Purpose |
|-------|---------|
| `signals` | Every generated signal with status, entry, SL, TP, confidence |
| `trades` | Executed trades with MT5 ticket, open/close prices, P&L |
| `schedules` | Recurring monitoring jobs (pair + cron + params) |
| `backtest_runs` | Backtest job metadata and status |
| `backtest_predictions` | Cached Kronos predictions (reused across warm reruns) |
| `backtest_signals` | Per-signal backtest records (predicted vs actual) |
| `backtest_metrics` | Aggregated results per backtest run |

### `model/base.py` / `model/kronos.py`
`BasePredictor` ABC — all models implement `predict(candles: DataFrame) -> DataFrame`. Swapping is a one-line config change (`MODEL_NAME=kronos|moirai|tft`).

`KronosPredictor` wraps `NeoQuasar/Kronos-base`. It lazy-loads on first call, infers candle frequency automatically, and adds `estimate_confidence(candles, pred_df)` which accepts the already-fetched prediction to avoid a second stochastic model call.

### `signals/filters.py`
Five independent gates applied in order — first failure short-circuits to SKIP:
1. `check_confidence` — confidence ≥ `CONFIDENCE_THRESHOLD` (default 0.62)
2. `check_min_pips` — predicted move ≥ `min_pips`
3. `check_spread` — current spread ≤ `max_spread`
4. `check_news_blackout` — no HIGH-impact event within ±`NEWS_BLACKOUT_MINUTES`
5. `check_session` — current UTC time is within an `ACTIVE_SESSIONS` window

RSI advisory (non-blocking):
- `compute_rsi(candles, period=14)` — Wilder EMA RSI from close prices
- `rsi_advisory(rsi_value, direction)` — returns a label: `OVERBOUGHT`, `OVERSOLD`, or `CLEAR (xx.x)` with context about whether the RSI zone agrees or conflicts with the signal direction
- Both `rsi` and `rsi_advisory` are persisted on signals created via `/signals/analyze` and scheduled jobs

`apply_all_filters()` runs all five gates and returns `(passed: bool, reason: str)`.

### `signals/risk.py`
SL is placed at the configured `stop_loss_pips` from entry. If Kronos predicts a high/low closer to entry than the configured SL, the tighter level is used instead (reducing risk). The predicted H/L can only tighten the SL — never widen it beyond `stop_loss_pips`. TP is always `actual_sl_pips × risk_reward`, so the R:R is respected and TP is never inflated beyond `stop_loss_pips × risk_reward`.

For **IFVG signals**, TP is based on the FVG zone width (`gap_pips × risk_reward`) rather than `stop_loss_pips × risk_reward`. A fixed pip-based TP would be structurally disconnected from the gap and could leave an auto-executed trade open indefinitely; the gap width is the natural momentum measure. Position sizing risks exactly `risk_percent` of account balance. At confirm time, if no `lot_size` is provided, lot size is calculated from the live account balance and the signal's actual SL distance — so gold and other high-notional instruments are sized correctly rather than using a flat default.

**Auto Close at Profit** (schedule field `auto_close_profit`): When `auto_execute=True`, enabling this option overrides the R:R-based TP. Instead, the TP price is recomputed so that hitting it yields exactly `auto_close_profit_amount` in account currency. The formula is `pips_needed = target_amount / (pip_value_per_lot × lot_size)`, then `TP = entry ± pips_needed × pip_size`. Live MT5 rates are used for pip value where available; the static fallback table is used otherwise. Requires `auto_execute=True` because lot size must be known at trade placement time.

### `news/calendar.py`
Scrapes Forex Factory for upcoming events. Filters by currencies in the pair and a lookahead window. Returns event dicts with `time` (UTC), `currency`, `impact` (HIGH/MEDIUM/LOW), `name`, `forecast`, `previous`.

### `news/sentiment.py`
Lazy-loads `ProsusAI/finbert` on first use. Scores individual headlines or batches of calendar events. `aggregate_bias()` averages scores across all headlines and requires a 5% edge over neutral before calling a directional bias.

### `signals/engine.py`
14-step pipeline orchestrated by `SignalEngine.generate()`:
1. Fetch 600 OHLCV candles from MT5
2. Read live spread
3. Fetch Forex Factory calendar
4. Spread filter
5. Session filter
6. News blackout filter
7. Kronos prediction (next N candles)
8. Resolve direction (BUY/SELL)
9. Confidence filter
10. Min-pips filter
11. FinBERT sentiment scoring
12. Sentiment conflict check (skips if news opposes prediction)
13. Calculate SL/TP
14. Build human-readable reason string → return `Signal` or `SkipSignal`

### `execution/trader.py`
MT5 order management — called only after explicit signal confirmation. Key functions: `place_order()`, `modify_trade()`, `close_trade()`, `get_open_positions()`, `get_closed_deals()`. Uses magic number `20260101` to identify system orders.

### `scheduler/jobs.py`
Singleton `AsyncIOScheduler` (APScheduler). Functions: `add_schedule()`, `remove_schedule()`, `pause_schedule()`, `resume_schedule()`, `get_next_run()`. Started and stopped in the FastAPI lifespan.

### `api/server.py`
FastAPI app with a `lifespan` context manager that on startup: creates DB tables, connects MT5, builds the `SignalEngine` (stored on `app.state`), and starts APScheduler. On shutdown: stops scheduler and disconnects MT5. All endpoints require `X-API-Key` header except `/health` and `/docs`.

### `api/schemas.py`
Pydantic v2 schemas for all request/response types.

### `backtest/runner.py`
Async rolling-window backtester. `submit_run()` creates a `BacktestRun` DB record and fires an async background task. For **Kronos**, the task runs a 400-candle rolling window, calls the model on each window, applies filters, compares against actual closes, and persists signal records in batches of 500. For **IFVG**, outcome is determined by `_simulate_zone_excursion`: after each inversion candle, the next 10 candles are scanned for the highest high and lowest low; the excursion that extends furthest beyond the FVG zone boundary wins, and pips are measured from entry to that extreme point. Session labeling uses the matched session name from `check_session` directly, avoiding mis-labeling of candles in overlapping session windows (e.g. 07:00–09:00 UTC belongs to LONDON not TOKYO). Polls via `GET /backtest/{job_id}`.

### `backtest/metrics.py`
Pure computation over backtest signal records. Produces: win rate, profit factor, Sharpe ratio (annualised for H1), max drawdown, directional accuracy, equity curve, breakdowns by session / confidence tier / news bias.

---

## API Overview

### Signals
| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/signals/analyze` | Run full pipeline, return PENDING signal |
| `GET`  | `/signals` | List all signals |
| `GET`  | `/signals/{id}` | Get signal detail |
| `POST` | `/signals/{id}/confirm` | Execute signal on MT5 (body: `stack_count`, optional `lot_size`) |
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
| `GET` | `/health` | Server + MT5 + model + DB status |
| `GET` | `/pairs` | Available trading pairs |
| `POST` | `/backtest` | Submit backtest job (async) |
| `GET`  | `/backtest/{job_id}` | Poll backtest status |
| `GET`  | `/backtest/{job_id}/results` | Fetch backtest results |

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

Startup order: PostgreSQL (healthcheck) → MT5 container → API → Frontend

- **Dashboard**: http://localhost:3000
- **API docs**: http://localhost:8000/docs

### 4. Log into MT5 broker (first run only)

The MT5 container exposes a browser-based VNC UI for the initial broker login:

```
http://localhost:5901
```

Login with the credentials set in `.env` (`MT5_VNC_USER` / `MT5_VNC_PASSWORD`, default `admin`/`admin`).

Inside the browser window, the MT5 terminal is running:
- **File → Login to Trade Account**
- Enter your `MT5_LOGIN`, `MT5_PASSWORD`, select your `MT5_SERVER`
- Click **Sign In**

MT5 connects to your broker and starts syncing history. Takes 1–2 minutes. This login is saved to the `mt5_data` Docker volume — never needed again after this.

Model weights (Kronos + FinBERT, ~840MB total) are cached in a named Docker volume (`model_cache`) and survive rebuilds.

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
curl http://localhost:8000/health
```

### 6. Generate a signal via API
```bash
curl -X POST http://localhost:8000/signals/analyze \
  -H "X-API-Key: your-key" \
  -H "Content-Type: application/json" \
  -d '{"pair":"EURUSD","timeframe":"H1","min_pips":15,"stop_loss_pips":20,"risk_reward":2.0,"risk_percent":1.0}'
```

---

## Signal Workflow

```
POST /signals/analyze
        │
        ▼
   PENDING (expires in 5 min)
        │
        ├── POST /signals/{id}/confirm → EXECUTED
        ├── POST /signals/{id}/reject  → REJECTED
        └── (timeout)                 → EXPIRED
```

---

## Models

Primary: **Kronos-base** (`NeoQuasar/Kronos-base`) — 102M params, pretrained on 12B K-line records from 45 exchanges.

### Vendored Kronos Snapshot

`vendor/Kronos` is intentionally committed as an internal snapshot (regular files), not a git submodule.

- This keeps the repository self-contained for cloning, CI, and deployments.
- The nested git metadata (`vendor/Kronos/.git`) is intentionally removed.
- To update Kronos, pull/copy changes into `vendor/Kronos` and commit the file diffs in this repo.

Fallback order if backtest results are poor:
1. Tune thresholds (warm rerun — seconds)
2. Fine-tune Kronos on FX data
3. Swap to Moirai zero-shot
4. Train TFT or PatchTST on MT5 historical data

---

## Backtesting

Backtest compares Kronos predictions against real MT5 historical closes — not SL/TP simulation.

- **Cold run**: Phase 1 (predictions) + Phase 2 (compare) + Phase 3 (metrics) — minutes to hours
- **Warm run**: predictions cached in DB, only Phase 2+3 reruns — seconds
- All results persisted to PostgreSQL, portable via `pg_dump`

Go-live thresholds: directional accuracy > 52%, win rate > 50%, profit factor > 1.2, profitable in ≥ 3 of 5 walk-forward windows.

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.11+ |
| API | FastAPI + Uvicorn |
| Validation | Pydantic v2 |
| MT5 interface | `MetaTrader5` |
| Foundational model | Kronos (`NeoQuasar/Kronos-base`) |
| Sentiment | FinBERT (`ProsusAI/finbert`, local) |
| ML framework | PyTorch |
| Database | PostgreSQL (async via SQLAlchemy + asyncpg) |
| Migrations | Alembic |
| Scheduling | APScheduler |
| Data processing | pandas, pandas-ta |
| Containerisation | Docker + docker-compose |
| WhatsApp (v2) | Baileys Node.js sidecar |

---

## Versioning

**v1 (current):** Full pipeline · REST API · Backtesting · No auto-execution · Zero-shot Kronos · Docker

**v2 (planned):** WhatsApp frontend via Baileys · Kronos fine-tuning on FX data

**v3 (planned):** Web dashboard · Meta WhatsApp Business API fallback
