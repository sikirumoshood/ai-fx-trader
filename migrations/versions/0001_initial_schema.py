"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-04-27

"""
from typing import Sequence, Union
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Enum types (DO block makes it safe to re-run) ─────────────────────────
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE signalstatus AS ENUM ('PENDING','EXECUTED','REJECTED','EXPIRED');
        EXCEPTION WHEN duplicate_object THEN NULL; END $$
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE signaldirection AS ENUM ('BUY','SELL','SKIP');
        EXCEPTION WHEN duplicate_object THEN NULL; END $$
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE newsbias AS ENUM ('BULLISH','BEARISH','NEUTRAL');
        EXCEPTION WHEN duplicate_object THEN NULL; END $$
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE schedulestatus AS ENUM ('ACTIVE','PAUSED','CANCELED');
        EXCEPTION WHEN duplicate_object THEN NULL; END $$
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE backteststatus AS ENUM ('QUEUED','RUNNING','DONE','FAILED');
        EXCEPTION WHEN duplicate_object THEN NULL; END $$
    """)

    # ── trades ────────────────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id           VARCHAR        PRIMARY KEY,
            mt5_ticket   BIGINT,
            pair         VARCHAR(12)    NOT NULL,
            direction    signaldirection NOT NULL,
            entry        DOUBLE PRECISION NOT NULL,
            stop_loss    DOUBLE PRECISION,
            take_profit  DOUBLE PRECISION,
            lot_size     DOUBLE PRECISION,
            open_price   DOUBLE PRECISION,
            close_price  DOUBLE PRECISION,
            profit_pips  DOUBLE PRECISION,
            status       VARCHAR(16)    NOT NULL DEFAULT 'OPEN',
            opened_at    TIMESTAMPTZ    NOT NULL DEFAULT now(),
            closed_at    TIMESTAMPTZ
        )
    """)

    # ── signals ───────────────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS signals (
            id          VARCHAR         PRIMARY KEY,
            status      signalstatus    NOT NULL DEFAULT 'PENDING',
            direction   signaldirection NOT NULL,
            pair        VARCHAR(12)     NOT NULL,
            timeframe   VARCHAR(8)      NOT NULL,
            entry       DOUBLE PRECISION NOT NULL,
            stop_loss   DOUBLE PRECISION NOT NULL,
            take_profit DOUBLE PRECISION NOT NULL,
            risk_reward DOUBLE PRECISION NOT NULL,
            confidence  DOUBLE PRECISION NOT NULL,
            news_bias   newsbias,
            reason      TEXT,
            expires_at  TIMESTAMPTZ     NOT NULL,
            created_at  TIMESTAMPTZ     NOT NULL DEFAULT now(),
            executed_at TIMESTAMPTZ,
            trade_id    VARCHAR         REFERENCES trades(id)
        )
    """)

    # ── schedules ─────────────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS schedules (
            id             VARCHAR         PRIMARY KEY,
            pair           VARCHAR(12)     NOT NULL,
            timeframe      VARCHAR(8)      NOT NULL,
            cron           VARCHAR(64)     NOT NULL,
            min_pips       DOUBLE PRECISION NOT NULL,
            stop_loss_pips DOUBLE PRECISION NOT NULL,
            risk_reward    DOUBLE PRECISION NOT NULL,
            risk_percent   DOUBLE PRECISION NOT NULL,
            notify         BOOLEAN         DEFAULT TRUE,
            status         schedulestatus  NOT NULL DEFAULT 'ACTIVE',
            next_run       TIMESTAMPTZ,
            created_at     TIMESTAMPTZ     NOT NULL DEFAULT now(),
            updated_at     TIMESTAMPTZ     NOT NULL DEFAULT now()
        )
    """)

    # ── backtest_runs ─────────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS backtest_runs (
            id              VARCHAR         PRIMARY KEY,
            pair            VARCHAR(12)     NOT NULL,
            timeframe       VARCHAR(8)      NOT NULL,
            start_date      TIMESTAMPTZ     NOT NULL,
            end_date        TIMESTAMPTZ     NOT NULL,
            min_pips        DOUBLE PRECISION NOT NULL,
            stop_loss_pips  DOUBLE PRECISION NOT NULL,
            risk_reward     DOUBLE PRECISION NOT NULL,
            risk_percent    DOUBLE PRECISION NOT NULL,
            initial_balance DOUBLE PRECISION NOT NULL,
            status          backteststatus  NOT NULL DEFAULT 'QUEUED',
            error           TEXT,
            created_at      TIMESTAMPTZ     NOT NULL DEFAULT now(),
            completed_at    TIMESTAMPTZ
        )
    """)

    # ── backtest_predictions ──────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS backtest_predictions (
            id          SERIAL           PRIMARY KEY,
            run_id      VARCHAR          NOT NULL REFERENCES backtest_runs(id) ON DELETE CASCADE,
            candle_time TIMESTAMPTZ      NOT NULL,
            pred_open   DOUBLE PRECISION NOT NULL,
            pred_high   DOUBLE PRECISION NOT NULL,
            pred_low    DOUBLE PRECISION NOT NULL,
            pred_close  DOUBLE PRECISION NOT NULL
        )
    """)

    # ── backtest_signals ──────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS backtest_signals (
            id                SERIAL           PRIMARY KEY,
            run_id            VARCHAR          NOT NULL REFERENCES backtest_runs(id) ON DELETE CASCADE,
            candle_time       TIMESTAMPTZ      NOT NULL,
            direction         signaldirection  NOT NULL,
            effective_entry   DOUBLE PRECISION NOT NULL,
            spread_pips       DOUBLE PRECISION NOT NULL,
            predicted_close   DOUBLE PRECISION NOT NULL,
            actual_close      DOUBLE PRECISION,
            predicted_pips    DOUBLE PRECISION,
            actual_pips       DOUBLE PRECISION,
            direction_correct BOOLEAN,
            confidence        DOUBLE PRECISION,
            news_bias         newsbias,
            session           VARCHAR(16)
        )
    """)

    # ── backtest_metrics ──────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS backtest_metrics (
            id              SERIAL   PRIMARY KEY,
            run_id          VARCHAR  NOT NULL UNIQUE REFERENCES backtest_runs(id) ON DELETE CASCADE,
            total_signals   INTEGER,
            skipped         INTEGER,
            traded          INTEGER,
            win_rate        DOUBLE PRECISION,
            profit_factor   DOUBLE PRECISION,
            sharpe_ratio    DOUBLE PRECISION,
            max_drawdown    DOUBLE PRECISION,
            total_return    DOUBLE PRECISION,
            directional_acc DOUBLE PRECISION,
            by_session      JSONB,
            by_confidence   JSONB,
            by_news_impact  JSONB,
            equity_curve    JSONB
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS backtest_metrics")
    op.execute("DROP TABLE IF EXISTS backtest_signals")
    op.execute("DROP TABLE IF EXISTS backtest_predictions")
    op.execute("DROP TABLE IF EXISTS backtest_runs")
    op.execute("DROP TABLE IF EXISTS schedules")
    op.execute("DROP TABLE IF EXISTS signals")
    op.execute("DROP TABLE IF EXISTS trades")
    op.execute("DROP TYPE IF EXISTS backteststatus")
    op.execute("DROP TYPE IF EXISTS schedulestatus")
    op.execute("DROP TYPE IF EXISTS newsbias")
    op.execute("DROP TYPE IF EXISTS signaldirection")
    op.execute("DROP TYPE IF EXISTS signalstatus")
