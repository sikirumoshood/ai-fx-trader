from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config.settings import FX_API_KEY, MODEL_NAME, SCHEDULE_LOG_PATH
from api.routes import signals, schedules, trades, system

log = logging.getLogger(__name__)


# ── Startup / shutdown ────────────────────────────────────────────────────────

def _configure_schedule_execution_logging() -> None:
    """Ensure schedule execution logs are visible and persisted."""
    uvicorn_error = logging.getLogger("uvicorn.error")
    schedule_logger = logging.getLogger("schedule.execution")
    schedule_logger.setLevel(logging.INFO)

    if uvicorn_error.handlers:
        for handler in uvicorn_error.handlers:
            if handler not in schedule_logger.handlers:
                schedule_logger.addHandler(handler)

    log_path = Path(SCHEDULE_LOG_PATH)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    absolute_log_path = str(log_path.resolve())

    has_file_handler = any(
        isinstance(handler, logging.FileHandler)
        and getattr(handler, "baseFilename", None) == absolute_log_path
        for handler in schedule_logger.handlers
    )
    if not has_file_handler:
        file_handler = logging.FileHandler(absolute_log_path)
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
        )
        schedule_logger.addHandler(file_handler)

    schedule_logger.propagate = False
    schedule_logger.info("Schedule execution audit logger ready (file: %s)", absolute_log_path)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ────────────────────────────────────────────────────────────
    _configure_schedule_execution_logging()
    log.info("Starting AI FX Trader...")

    # 1. Create DB tables (idempotent)
    from data.store import create_all_tables
    await create_all_tables()
    log.info("DB tables ready")

    # 2. Connect to MT5
    from data import fetcher
    try:
        if fetcher.initialize():
            log.info("MT5 connected")
        else:
            log.warning("MT5 not available — live trading and data fetch disabled")
    except Exception as exc:
        log.warning("MT5 connection failed (%s) — live trading disabled", exc)

    # 3. Load prediction model
    from model.kronos import KronosPredictor
    predictor = KronosPredictor()
    # Model weights load lazily on first predict() call — no blocking at startup

    # 4. Build signal engine
    from signals.engine import SignalEngine
    app.state.signal_engine = SignalEngine(predictor)
    log.info("Signal engine ready (model: %s, lazy-load)", MODEL_NAME)

    # 5. Start APScheduler and restore active schedules from DB
    from scheduler import jobs
    from data.store import AsyncSessionLocal, Schedule as DBSchedule, ScheduleStatus
    from sqlalchemy import select
    from api.routes.schedules import _run_scheduled_signal, _job_kwargs

    jobs.start()

    async with AsyncSessionLocal() as db:
        rows = await db.execute(
            select(DBSchedule).where(DBSchedule.status == ScheduleStatus.ACTIVE)
        )
        restored = 0
        for sched in rows.scalars().all():
            next_run = jobs.add_schedule(
                schedule_id=sched.id,
                cron=sched.cron,
                func=_run_scheduled_signal,
                kwargs=_job_kwargs(sched),
            )
            sched.next_run = next_run
            restored += 1
        await db.commit()
    log.info("Restored %d active schedule(s) from DB", restored)

    yield

    # ── Shutdown ───────────────────────────────────────────────────────────
    from scheduler import jobs as sched_jobs
    sched_jobs.shutdown()
    fetcher.shutdown()
    log.info("AI FX Trader stopped")


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="AI FX Trader",
    version="1.0.0",
    description="AI-powered FX signal server. All signals require explicit confirmation.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── API key auth (all routes except /health, /docs) ───────────────────────────

@app.middleware("http")
async def require_api_key(request: Request, call_next):
    if request.method == "OPTIONS":
        return await call_next(request)
    if request.url.path in ("/health", "/docs", "/openapi.json", "/redoc"):
        return await call_next(request)
    key = request.headers.get("X-API-Key", "")
    if key != FX_API_KEY:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"detail": "Invalid or missing API key"},
        )
    return await call_next(request)


# ── Routers ───────────────────────────────────────────────────────────────────

app.include_router(system.router)
app.include_router(signals.router,   prefix="/signals",   tags=["Signals"])
app.include_router(schedules.router, prefix="/schedules", tags=["Schedules"])
app.include_router(trades.router,    prefix="/trades",    tags=["Trades"])
