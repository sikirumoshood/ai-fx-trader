# AI FX Trader — Implementation Plan

> Last updated: 2026-04-12 (session 3)
> Status: Planning complete. Ready to implement.
> Rule: Always prompt user before updating this file at end of conversation.

---

## Overview

An AI-powered FX trading server that:
- Reads live OHLCV data from MetaTrader 5
- Uses Kronos (foundational model) to predict next candle(s)
- Performs sentiment analysis on macroeconomic news via FinBERT
- Generates trade signals (BUY / SELL / SKIP) with entry, SL, TP
- Exposes a REST API for signal management, scheduling, and trade confirmation
- Never auto-executes — all trades require explicit confirmation
- Designed for future WhatsApp/Telegram bot integration

---

## Core Principles

- **No auto-execution** — signals always require confirmation via API
- **No 3rd party LLM APIs** — use FinBERT locally + rule-based logic
- **No training in v1** — use Kronos zero-shot (pretrained)
- **MT5 as single data source** — live feed, historical data, and execution
- **Configurable via API** — timeframe, pips, SL, RR all passed per request

---

## Simplified Pipeline Flow

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
      ├── SKIP → log reason, wait for next candle
      │
      ▼
FinBERT scores latest headlines + econ calendar impact
      │
      ▼
Signal Engine combines:
  • Kronos predicted direction + confidence
  • Predicted H/L → natural SL/TP levels
  • FinBERT sentiment bias
  • Risk sizing from request params
      │
      ├── SKIP → predicted move too small or sentiment conflicts
      │
      ▼
Signal created (status: PENDING) → returned via API
      │
      ├── POST /signals/{id}/confirm → EXECUTED on MT5
      └── POST /signals/{id}/reject  → REJECTED
```

---

## Prediction Model

### Abstract Interface

All prediction models implement the same interface so swapping is a one-line config change:

```python
# model/base.py
class BasePredictor:
    def predict(self, candles: pd.DataFrame) -> pd.DataFrame:
        """
        Input:  OHLCV DataFrame (N candles context)
        Output: DataFrame with predicted next candle(s) (open, high, low, close)
        """
        raise NotImplementedError

class KronosPredictor(BasePredictor): ...
class MoiraiPredictor(BasePredictor): ...
class TFTPredictor(BasePredictor):    ...
```

```python
# config/settings.py
MODEL = "kronos"   # swap to "moirai" or "tft" — signal engine unchanged
```

### Model Options

| Model | By | OHLCV? | Zero-shot? | FX suited? | Notes |
|-------|----|--------|------------|------------|-------|
| **Kronos** | NeoQuasar | ✅ Native | ✅ | ⚠️ Uncertain | Best OHLCV-specific, primary choice |
| **Moirai** | Salesforce | ⚠️ Multivariate | ✅ | ✅ Better | Trained on diverse financial time series |
| **Chronos** | Amazon | ❌ Univariate | ✅ | ⚠️ Partial | Separate pass per O/H/L/C column |
| **TimesFM** | Google | ❌ Univariate | ✅ | ⚠️ Partial | Same limitation as Chronos |
| **TFT** | Open source | ✅ Multivariate | ❌ Train needed | ✅ Strong | Handles news scores as covariates |
| **PatchTST** | Open source | ✅ Multivariate | ❌ Train needed | ✅ Strong | SOTA on many benchmarks |
| **LightGBM** | Open source | ✅ Features | ❌ Train needed | ✅ Proven | Fast, no GPU, strong baseline |

### FX Microstructure Caveat

Kronos was trained primarily on equities and crypto. FX differs:

```
Equities/Crypto          FX
─────────────────────────────────────
Exchange-driven          OTC / decentralised
Volume meaningful        Tick volume only (no real volume)
Market hours             24hr (Sun-Fri)
Gaps between sessions    Nearly gapless
News impact              Central banks dominate
```

Zero-shot performance may be lower than the reported 58-65% on FX.
Backtest results will reveal the true performance. See Post-Backtest Considerations.

### Primary Choice — Kronos

- **Repository**: [shiyu-coder/Kronos](https://github.com/shiyu-coder/Kronos)
- **Paper**: AAAI 2026
- **HuggingFace**: NeoQuasar organization
- Pre-trained on 12 billion K-line records from 45 global exchanges
- Decoder-only autoregressive Transformer
- Input: OHLCV DataFrame (400 candle context window)
- Output: Predicted future candles (O, H, L, C)
- Reported accuracy: 58-65% directional on hourly data

| Model | Params | Context | Use Case |
|-------|--------|---------|----------|
| `Kronos-mini` | 4.1M | 2048 | CPU-friendly, fast |
| `Kronos-small` | 24.7M | 512 | Balanced |
| `Kronos-base` | 102.3M | 512 | Best open quality (recommended) |

```python
from model import Kronos, KronosTokenizer, KronosPredictor

tokenizer = KronosTokenizer.from_pretrained("NeoQuasar/Kronos-Tokenizer-base")
model     = Kronos.from_pretrained("NeoQuasar/Kronos-base")
predictor = KronosPredictor(model, tokenizer, device="cuda:0", max_context=512)

pred_df = predictor.predict(
    df=last_400_candles[['open','high','low','close','volume']],
    x_timestamp=...,
    y_timestamp=next_window_timestamps,
    pred_len=5,
    T=1.0,
    top_p=0.9,
    sample_count=10
)
```

### Fallback Order (if backtest results are poor)

```
1. Kronos zero-shot              ← v1, start here
        │
        └── poor results?
              │
2. Fine-tune Kronos on FX data   ← v2, same codebase, just add training pipeline
        │
        └── still poor?
              │
3. Moirai zero-shot              ← swap model/kronos.py wrapper only, no other changes
        │
        └── still poor?
              │
4. TFT or PatchTST               ← train custom model on MT5 FX historical data
```

MT5 provides all training data needed for steps 2-4. No external data required.

### What the Model Provides vs FinBERT

| Model (Kronos/alternative) | FinBERT + Rules |
|---------------------------|----------------|
| Predicts future OHLCV | Interprets news & macro context |
| Quantitative price forecast | Qualitative sentiment bias |
| Pattern recognition in candles | Language understanding |
| Runs every candle close | Called selectively per signal |

---

## Data Source — MetaTrader 5

Chosen over OANDA because:
- User is already familiar with MT5
- Tick data access (`copy_ticks_from()`)
- Virtually unlimited historical candles
- Free demo account for paper trading
- Broker-agnostic (switch broker freely)
- Spread included per candle in historical data

### MT5 Python Usage

```python
import MetaTrader5 as mt5

mt5.initialize()

# Historical OHLCV
rates = mt5.copy_rates_from_pos("EURUSD", mt5.TIMEFRAME_H1, 0, 500)
df = pd.DataFrame(rates)
# columns: time, open, high, low, close, tick_volume, spread, real_volume

# Live tick
tick = mt5.symbol_info_tick("EURUSD")

# Place order (only after confirmation)
mt5.order_send({ ... })

mt5.shutdown()
```

---

## LLM Usage — No 3rd Party APIs

| Component | Implementation |
|-----------|---------------|
| News sentiment | **FinBERT** (local, HuggingFace, ~440MB, CPU-friendly) |
| Signal narration | **Rule-based templates** (string formatting from signal data) |
| Skip advisor | **Rule-based filters** (hard thresholds) |
| Macro bias | **Scrape** Forex Factory + FinBERT on headlines |

### Rule-Based Skip Logic

```python
if confidence < 0.55:                → SKIP
if predicted_move < min_pips:        → SKIP  (low volatility)
if high_impact_event_within_30min:   → SKIP
if spread > max_spread:              → SKIP
if outside_trading_session:          → SKIP
```

---

## Project Structure

```
ai-fx-trader/
├── config/
│   └── settings.py           # MT5 credentials, model path, defaults
│
├── data/
│   ├── fetcher.py             # MT5 → OHLCV DataFrame
│   └── store.py               # PostgreSQL schema + async helpers
│
├── model/
│   ├── base.py                # BasePredictor abstract interface
│   ├── kronos.py              # Kronos wrapper (load, predict)
│   ├── moirai.py              # Moirai wrapper (fallback option 1)
│   └── tft.py                 # TFT wrapper (fallback option 2)
│
├── news/
│   ├── calendar.py            # Forex Factory econ calendar scraper
│   └── sentiment.py           # FinBERT sentiment scoring
│
├── signals/
│   ├── engine.py              # Kronos + sentiment → signal
│   ├── risk.py                # SL/TP/position sizing from request params
│   └── filters.py             # Session, spread, volatility, news gates
│
├── execution/
│   └── trader.py              # MT5 order placement (on confirmation only)
│
├── scheduler/
│   └── jobs.py                # APScheduler job management
│
├── api/
│   ├── server.py              # FastAPI app
│   ├── schemas.py             # Pydantic request/response models
│   └── routes/
│       ├── signals.py         # /signals/*
│       ├── schedules.py       # /schedules/*
│       ├── trades.py          # /trades/*
│       └── system.py          # /health, /pairs
│
├── backtest/
│   ├── runner.py              # Walk-forward backtester
│   └── metrics.py             # Sharpe, drawdown, win rate, profit factor
│
├── whatsapp/                  # v2 — Baileys Node.js sidecar
│   ├── gateway.js             # Baileys session + message routing
│   ├── commands.js            # Command parser → API calls
│   ├── formatter.js           # API responses → WhatsApp messages
│   ├── session/               # Baileys credentials (gitignored)
│   ├── package.json
│   └── .env                   # FX_API_KEY, API_BASE_URL
│
├── migrations/                # Alembic DB migrations
├── Dockerfile
├── docker-compose.yml         # runs FastAPI + PostgreSQL (+ Baileys in v2)
├── .env.example               # Template (never commit .env)
├── PLAN.md                    # This file
└── main.py                    # Starts FastAPI server
```

---

## API Design

### Signal State Machine

```
POST /signals/analyze
        │
        ▼
   PENDING signal created
        │
        ├── POST /signals/{id}/confirm → EXECUTED (sent to MT5)
        ├── POST /signals/{id}/reject  → REJECTED
        └── (timeout)                 → EXPIRED
```

### Schedule State Machine

```
POST /schedules (create)
        │
        ▼
      ACTIVE → monitors pair on interval
        │
        ├── PATCH /schedules/{id}        → update params
        ├── POST /schedules/{id}/pause   → PAUSED
        ├── POST /schedules/{id}/resume  → ACTIVE
        └── DELETE /schedules/{id}       → CANCELED
```

### Endpoints

#### Signals
| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/signals/analyze` | Run pipeline, return signal |
| `GET` | `/signals` | List all signals |
| `GET` | `/signals/{id}` | Get signal detail |
| `POST` | `/signals/{id}/confirm` | Execute signal on MT5 |
| `POST` | `/signals/{id}/reject` | Reject signal |

#### Schedules
| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/schedules` | Create monitoring schedule |
| `GET` | `/schedules` | List all schedules |
| `GET` | `/schedules/{id}` | Get schedule detail |
| `PATCH` | `/schedules/{id}` | Modify params |
| `DELETE` | `/schedules/{id}` | Cancel schedule |
| `POST` | `/schedules/{id}/pause` | Pause schedule |
| `POST` | `/schedules/{id}/resume` | Resume schedule |

#### Trades
| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/trades` | List all trades (open/closed) |
| `GET` | `/trades/{id}` | Get trade detail |
| `PATCH` | `/trades/{id}` | Modify SL/TP |
| `DELETE` | `/trades/{id}` | Close trade on MT5 |

#### System
| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Server + MT5 connection status |
| `GET` | `/pairs` | Available MT5 pairs |
| `POST` | `/backtest` | Run backtest with given params |

### Request/Response Schemas

#### POST /signals/analyze
```json
Request:
{
  "pair":           "EURUSD",
  "timeframe":      "H1",
  "min_pips":       15,
  "stop_loss_pips": 20,
  "risk_reward":    2.0,
  "risk_percent":   1.0
}

Response 201:
{
  "id":          "sig_abc123",
  "status":      "PENDING",
  "expires_at":  "2026-04-12T15:30:00Z",
  "signal":      "BUY",
  "entry":       1.08450,
  "stop_loss":   1.08200,
  "take_profit": 1.08950,
  "risk_reward": 2.0,
  "confidence":  0.74,
  "news_bias":   "BULLISH",
  "reason":      "Strong upward momentum. USD weak post-PPI.",
  "pair":        "EURUSD",
  "timeframe":   "H1"
}
```

#### POST /signals/{id}/confirm
```json
Response 200:
{
  "id":          "sig_abc123",
  "status":      "EXECUTED",
  "trade_id":    "trd_xyz789",
  "executed_at": "2026-04-12T15:10:00Z"
}
```

#### POST /schedules
```json
Request:
{
  "pair":           "EURUSD",
  "timeframe":      "H1",
  "cron":           "0 * * * *",
  "min_pips":       15,
  "stop_loss_pips": 20,
  "risk_reward":    2.0,
  "risk_percent":   1.0,
  "notify":         true
}

Response 201:
{
  "id":       "sch_def456",
  "status":   "ACTIVE",
  "next_run": "2026-04-12T16:00:00Z",
  "pair":     "EURUSD",
  "timeframe": "H1"
}
```

#### POST /backtest
```json
Request:
{
  "pair":            "EURUSD",
  "timeframe":       "H1",
  "start_date":      "2022-01-01",
  "end_date":        "2024-12-31",
  "min_pips":        15,
  "stop_loss_pips":  20,
  "risk_reward":     2.0,
  "risk_percent":    1.0,
  "initial_balance": 10000
}

Response 200:
{
  "summary": {
    "total_signals":  843,
    "skipped":        401,
    "traded":         442,
    "win_rate":       "61.3%",
    "profit_factor":  1.87,
    "sharpe_ratio":   1.42,
    "max_drawdown":   "8.2%",
    "total_return":   "34.6%"
  },
  "by_session":    { ... },
  "by_confidence": { ... },
  "by_news_impact": { ... },
  "equity_curve":  [ ... ]
}
```

---

## Backtesting

### What Backtesting Measures

Backtesting is NOT simulating live trades with SL/TP tracking.
It is comparing Kronos predictions against real historical outcomes:

```
For each candle i (rolling window):

  Input:   candles[i-400 : i]  → Kronos → predicted next candle (O,H,L,C)
  Actual:  candles[i+1]        → real next candle from MT5 history
  Spread:  candles[i].spread   → already in MT5 historical data

  Signal engine evaluates prediction → BUY / SELL / SKIP

  If BUY:
    effective_entry  = predicted_open + spread
    predicted_profit = predicted_close - effective_entry  (pips)
    actual_profit    = actual_close    - effective_entry  (pips)

  If SELL:
    effective_entry  = predicted_open - spread
    predicted_profit = effective_entry - predicted_close  (pips)
    actual_profit    = effective_entry - actual_close     (pips)
```

### Backtest Record Per Signal

```json
{
  "signal":             "BUY",
  "effective_entry":    1.08452,
  "spread_pips":        0.2,
  "predicted_close":    1.08950,
  "actual_close":       1.08650,
  "predicted_pips":     49.8,
  "actual_pips":        19.8,
  "direction_correct":  true,
  "news_bias":          "BULLISH",
  "confidence":         0.74,
  "session":            "LONDON",
  "candle_time":        "2024-03-15T10:00:00Z"
}
```

All records saved to PostgreSQL — portable across local, VPS, and cloud.

### Data Source

Real historical OHLCV from MT5 — same candles that traded live on the broker.
Spread is included per candle in the MT5 historical data (`df['spread']`).
No synthetic data.

```python
rates = mt5.copy_rates_range("EURUSD", mt5.TIMEFRAME_H1, start_date, end_date)
df = pd.DataFrame(rates)
# columns: time, open, high, low, close, tick_volume, spread ← real spread per candle
```

### Execution Architecture

**Phase 1 — Kronos predictions (parallel asyncio workers ✅ safe)**
```
Worker 1: predict candles 400-1000   ──┐
Worker 2: predict candles 1000-2000  ──┤──► PostgreSQL (predictions table)
Worker 3: predict candles 2000-3000  ──┘
```
Each worker is fully independent — no shared state. Parallelism is safe.
Run once per pair/timeframe, cached to DB permanently.

**Phase 2 — Compare predictions vs actuals (parallel ✅ safe)**
```
Each signal record is self-contained:
  predicted_close vs actual_close → direction_correct, actual_pips
No shared state. All workers independent.
```

**Phase 3 — Aggregate metrics (single pass)**
```
Pure pandas over saved results → metrics, equity curve, breakdowns
Runs in seconds regardless of record count.
```

### Backtest API — Async Job Pattern

Backtest runs can take minutes to hours (cold run). API returns immediately:

```
POST /backtest              → 202 Accepted, returns job_id
GET  /backtest/{job_id}     → poll status (QUEUED / RUNNING / DONE / FAILED)
GET  /backtest/{job_id}/results → fetch full results when DONE
```

### Re-running With Different Params (warm run)

Kronos predictions are cached permanently in PostgreSQL.
Changing min_pips, risk_reward, confidence threshold only reruns Phase 2+3:

```
Cold run (first time):  Phase 1 + 2 + 3  → minutes to hours
Warm run (param tweak): Phase 2 + 3 only → seconds
```

### Recommended Data Window

| Timeframe | Candles/Year | ~Signals/Year | Years for 500 trades |
|-----------|-------------|---------------|----------------------|
| M15 | 35,040 | 10,000-17,000 | < 1 month |
| H1 | 6,240 | 2,500-4,000 | < 3 months |
| H4 | 2,190 | 650-1,000 | ~6 months |
| D1 | 261 | 80-130 | ~4 years |

**Target: 5 years of data, H1 timeframe**
- ~31,200 prediction windows per pair
- ~13,500 trades per pair after skip filters
- Minimum 500 trades required for statistical significance

### Walk-Forward Validation (5 years example)

```
Total: Jan 2020 → Dec 2024

├── Window 1: Context [Jan-Dec 2020]     → Test [Jan-Jun 2021]
├── Window 2: Context [Jul 2020-Jun 2021]→ Test [Jul-Dec 2021]
├── Window 3: Context [Jan-Dec 2021]     → Test [Jan-Jun 2022]
├── Window 4: Context [Jul 2021-Jun 2022]→ Test [Jul-Dec 2022]
├── Window 5: Context [Jan-Dec 2022]     → Test [Jan-Jun 2023]
├── Window 6: Context [Jul 2022-Jun 2023]→ Test [Jul-Dec 2023]
├── Window 7: Context [Jan-Dec 2023]     → Test [Jan-Jun 2024]
└── Window 8: Context [Jul 2023-Jun 2024]→ Test [Jul-Dec 2024]

Aggregate all 8 test periods → final metrics
```

### Database Storage

All backtest data persisted to PostgreSQL for portability:

```
backtest_runs         — run metadata (pair, timeframe, date range, params, status)
backtest_predictions  — cached Kronos predictions (reused across runs)
backtest_signals      — per-signal records (entry, spread, predicted vs actual)
backtest_metrics      — aggregated results per run
```

Exporting to cloud: `pg_dump` → import to any PostgreSQL instance.

### Aggregate Metrics

```
Overall:
  • Directional accuracy     % of correct BUY/SELL calls
  • Win rate after spread    % of trades where actual_profit > 0
  • Avg predicted pips       how large Kronos expected the move to be
  • Avg actual pips          what actually happened
  • Prediction delta         avg(predicted_pips - actual_pips) — calibration
  • Profit factor            sum(wins) / sum(losses)
  • SKIP rate                % of windows filtered out

Breakdown by:
  • Session                  London, NY, Tokyo, overlap
  • Day of week
  • News impact level        low / medium / high
  • Confidence tier          0.5-0.6, 0.6-0.7, 0.7+  ← sets live skip threshold
```

---

## Post-Backtest Considerations

### Go-Live Thresholds (minimum acceptable)

```
Directional accuracy:   > 52%   (anything above 50% is a statistical edge)
Win rate after spread:  > 50%
Profit factor:          > 1.2
Consistency:            profitable in at least 3 of 5 walk-forward windows
```

If results fall below these thresholds, do NOT go live. Use the decision tree below.

### Decision Tree — Poor Backtest Results

```
Backtest result poor
        │
        ├── Directional accuracy < 50%?
        │         │
        │         └── Kronos zero-shot not calibrated for this pair/TF
        │                   → tune thresholds first (warm rerun, seconds)
        │                   → if still poor → fine-tune Kronos on FX data (v2)
        │
        ├── Accuracy OK but profit negative?
        │         │
        │         ├── Spread eating profits → increase min_pips threshold
        │         ├── Wrong sessions active → add/tighten session filter
        │         └── Low confidence trades dragging results
        │                   → raise confidence threshold, rerun
        │
        ├── Inconsistent across walk-forward windows?
        │         │
        │         └── Model sensitive to market regime changes
        │                   → only trade pairs/sessions that are consistently good
        │                   → consider H4 over H1 (less noise)
        │
        └── Good on some pairs, bad on others?
                  │
                  └── Whitelist only profitable pairs for live trading
                      Store per-pair performance in DB
                      Exclude poor-performing pairs from schedules
```

### Tuning Levers (warm reruns — seconds each)

```
1. min_pips threshold      → filters out low-volatility windows
2. confidence threshold    → filters out low-certainty predictions
3. session filter          → trade only London, NY, or overlap
4. news impact gate        → widen or tighten event blackout window
5. timeframe               → switch H1 → H4 for cleaner signals
6. pair selection          → trade only consistently profitable pairs
```

### Escalation Path

```
Poor results
    │
    ├── Step 1: Tune thresholds (warm reruns)          ← free, seconds
    ├── Step 2: Change timeframe or session filter      ← free, seconds
    ├── Step 3: Restrict to best-performing pairs       ← free, seconds
    ├── Step 4: Fine-tune Kronos on FX data (v2)        ← compute cost, days
    └── Step 5: Evaluate alternative foundation model   ← research cost
```

All backtest results are persisted to PostgreSQL so every tuning iteration is
traceable and comparable — no results are ever lost.

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.11+ |
| MT5 interface | `MetaTrader5` package |
| Data processing | `pandas`, `pandas-ta` |
| Foundational model | Kronos (`NeoQuasar/Kronos-base`) |
| Sentiment | FinBERT (HuggingFace, local) |
| ML framework | PyTorch |
| API server | FastAPI |
| Validation | Pydantic |
| Scheduling | APScheduler |
| Database | PostgreSQL (via Docker) |
| Async DB driver | `asyncpg` + SQLAlchemy async |
| Migrations | Alembic |
| Containerisation | Docker + docker-compose |
| WhatsApp (v2) | Baileys (`@whiskeysockets/baileys`) — Node.js 24+ |
| WhatsApp fallback (v3) | Meta WhatsApp Business API via kapso bridge |

---

## Versioning

### v1 (Current Scope)
- [x] Full pipeline: MT5 → Kronos → FinBERT → Signal → API
- [x] REST API with signals, schedules, trades, system endpoints
- [x] Backtesting with walk-forward validation
- [x] No auto-execution — confirmation required
- [x] Zero-shot Kronos (no fine-tuning)
- [x] Docker — runs locally and on VPS

### v2 (Future)
- [ ] WhatsApp frontend via Baileys Node.js sidecar
- [ ] Fine-tune Kronos on FX-specific data
- [ ] Per-pair model configs (`config/pairs.yaml`)

### v3 (Future)
- [ ] Swap Baileys for Meta WhatsApp Business API if needed
- [ ] Web dashboard

---

## WhatsApp Integration (v2)

### Library — Baileys (via OpenClaw pattern)

OpenClaw (247k stars) uses **Baileys** — an unofficial reverse-engineered WhatsApp Web
WebSocket library for Node.js. We repurpose the same pattern as a thin sidecar service.

- **Baileys repo**: `@whiskeysockets/baileys`
- **Runtime**: Node.js 24+ (Bun is incompatible with Baileys)
- **Auth**: QR code scan once → session persisted to files
- **Risk**: Unofficial API — use a dedicated WhatsApp number, not personal

### Architecture

```
WhatsApp User
      ↕
Baileys Node.js sidecar     ←→     FastAPI (Python)
  • receive message                  • POST /signals/analyze
  • parse command                    • POST /signals/{id}/confirm
  • call REST API                    • POST /schedules
  • format response                  • GET /trades
  • send reply                       • GET /health
```

FastAPI has zero knowledge of WhatsApp — the sidecar just calls the same REST endpoints
any web client would use.

### Command → API Mapping

```
User sends:                    Sidecar calls:
─────────────────────────────────────────────────────────
"check EURUSD H1"         →    POST /signals/analyze
"confirm"                 →    POST /signals/{id}/confirm
"reject"                  →    POST /signals/{id}/reject
"schedule EURUSD hourly"  →    POST /schedules
"my schedules"            →    GET /schedules
"pause sch_def456"        →    POST /schedules/sch_def456/pause
"cancel all"              →    DELETE each active schedule
"open trades"             →    GET /trades
"close trd_xyz789"        →    DELETE /trades/trd_xyz789
"status"                  →    GET /health
```

### Baileys Core Pattern

```javascript
// whatsapp/gateway.js
const { makeWASocket, useMultiFileAuthState } = require('@whiskeysockets/baileys')
const axios = require('axios')

async function start() {
  const { state, saveCreds } = await useMultiFileAuthState('./session')
  const sock = makeWASocket({ auth: state })

  sock.ev.on('creds.update', saveCreds)
  sock.ev.on('connection.update', ({ connection, qr }) => {
    if (qr) console.log('Scan QR to link WhatsApp')
    if (connection === 'close') start()   // auto-reconnect
  })

  sock.ev.on('messages.upsert', async ({ messages }) => {
    for (const msg of messages) {
      if (msg.key.fromMe) continue
      const from = msg.key.remoteJid
      const text = msg.message?.conversation?.trim().toLowerCase()
      const reply = await handleCommand(text)
      await sock.sendMessage(from, { text: reply })
    }
  })
}
```

### Escalation Path (if Baileys gets banned)

```
v2: Baileys (unofficial, free)
        │
        └── account banned?
              │
v3: Meta WhatsApp Business API (official, paid)
    via openclaw-kapso-whatsapp bridge pattern
```

---

## Implementation Order

```
1.  config/settings.py          — MT5 credentials, model path, defaults
2.  data/fetcher.py             — MT5 → OHLCV DataFrame
3.  data/store.py               — PostgreSQL schema + async helpers (SQLAlchemy + asyncpg)
4.  model/kronos.py             — Kronos wrapper (load, predict)
5.  signals/filters.py          — Rule-based gates
6.  signals/risk.py             — SL/TP/position sizing
7.  news/calendar.py            — Forex Factory scraper
8.  news/sentiment.py           — FinBERT sentiment scoring
9.  signals/engine.py           — Full signal generation
10. api/schemas.py              — Pydantic models
11. api/routes/signals.py       — /signals/* endpoints
12. api/routes/schedules.py     — /schedules/* endpoints
13. api/routes/trades.py        — /trades/* endpoints
14. api/routes/system.py        — /health, /pairs
15. scheduler/jobs.py           — APScheduler integration
16. execution/trader.py         — MT5 order placement
17. api/server.py               — FastAPI app assembly
18. backtest/runner.py          — Walk-forward backtester
19. backtest/metrics.py         — Metrics computation
20. main.py                     — Entry point
```

---

## Decisions Log

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Supported pairs | All majors, minors, selected exotics | Full coverage |
| Default timeframe | H1 (configurable per request) | Best signal/noise balance |
| Signal expiry | 5 minutes | Short enough to stay relevant on H1 |
| API authentication | Static API key (header: `X-API-Key`) | Simple, secure for v1 |
| Deployment | Docker — local + VPS (MT5 via Wine on Linux) | Portability |
| Database | PostgreSQL | Concurrent async writes, cloud portable |
| Backtest data | 5 years historical H1 | ~13,500 trades per pair |
| Backtest storage | All results persisted to PostgreSQL | Portable via pg_dump |
| Backtest approach | Kronos prediction vs actual close comparison | Real data, no SL/TP sim |
| Model interface | Abstract BasePredictor — swap model via config | Kronos → Moirai → TFT without touching signal engine |
| Spread handling | MT5 historical spread per candle applied to entry | Realistic P&L |
| Backtest API | Async job pattern (POST → job_id, GET to poll) | Non-blocking for long runs |
| WhatsApp library | Baileys (Node.js sidecar, OpenClaw pattern) | Unofficial but battle-tested, free |
| WhatsApp frontend | Thin sidecar — calls same REST API as any web client | Decoupled from core |

### Supported Pairs (v1)

```
Majors:       EURUSD, GBPUSD, USDJPY, USDCHF, AUDUSD, USDCAD, NZDUSD
Minors:       EURGBP, EURJPY, EURCHF, EURCAD, EURAUD, EURNZD
              GBPJPY, GBPCHF, GBPCAD, GBPAUD, GBPNZD
              AUDJPY, AUDCHF, AUDCAD, AUDNZD
              CADJPY, CADCHF, NZDJPY, NZDCHF, CHFJPY
Exotics:      USDZAR, USDMXN, USDNOK, USDSEK, USDDKK
              USDSGD, USDHKD, USDTRY
```

### Signal Expiry

- PENDING signals expire after **5 minutes**
- Rationale: on H1, a 5-min-old signal is still within the same candle and actionable
- After expiry, signal status changes to `EXPIRED` automatically

### API Authentication

```
Header: X-API-Key: <your-key>
Key stored in: config/settings.py (env variable: FX_API_KEY)
All endpoints protected except GET /health
```

### Deployment

- **Local**: `python main.py` — connects to local MT5 installation
- **VPS**: Docker container — MT5 runs via Wine on Linux VPS
- `Dockerfile` and `docker-compose.yml` included in v1
- Environment variables via `.env` file (never committed)
