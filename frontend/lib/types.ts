export type SignalStatus = "PENDING" | "EXECUTED" | "REJECTED" | "EXPIRED";
export type SignalDirection = "BUY" | "SELL" | "SKIP";
export type NewsBias = "BULLISH" | "BEARISH" | "NEUTRAL";
export type ScheduleStatus = "ACTIVE" | "PAUSED" | "CANCELED";
export type BacktestStatus = "QUEUED" | "RUNNING" | "DONE" | "FAILED";

export interface Signal {
  id: string;
  status: SignalStatus;
  expires_at: string;
  signal: SignalDirection;
  entry: number;
  stop_loss: number;
  take_profit: number;
  risk_reward: number;
  confidence: number;
  news_bias: NewsBias | null;
  rsi: number | null;
  rsi_advisory: string | null;
  pattern_name: string | null;
  pattern_bias: string | null;
  reason: string | null;
  pair: string;
  timeframe: string;
  created_at: string;
}

export interface Trade {
  id: string;
  signal_id: string | null;
  stack_index: number | null;
  mt5_ticket: number | null;
  pair: string;
  direction: SignalDirection;
  order_type: "MARKET" | "LIMIT" | "STOP";
  entry: number;
  stop_loss: number | null;
  take_profit: number | null;
  lot_size: number | null;
  open_price: number | null;
  close_price: number | null;
  profit_pips: number | null;
  status: "OPEN" | "PENDING" | "CLOSED" | "CANCELED";
  opened_at: string;
  closed_at: string | null;
}

export interface ConfirmResponse {
  id: string;
  status: string;
  trade_ids: string[];
  stack_count: number;
  executed_at: string;
}

export type Indicator = "ifvg";

export interface Schedule {
  id: string;
  status: ScheduleStatus;
  pair: string;
  timeframe: string;
  cron: string;
  indicator: Indicator;
  min_pips: number;
  stop_loss_pips: number;
  risk_reward: number;
  risk_percent: number;
  notify: boolean;
  sessions?: string[];
  ifvg_threshold?: number;
  auto_execute: boolean;
  auto_lot_size?: number | null;
  max_risk_amount?: number | null;
  auto_close_profit: boolean;
  auto_close_profit_amount?: number | null;
  next_run: string | null;
  created_at: string;
}

export interface Health {
  status: string;
  mt5_connected: boolean;
  model_loaded: boolean;
  db_connected: boolean;
  timestamp: string;
}

export interface AnalyzeRequest {
  pair: string;
  timeframe: string;
  min_pips: number;
  stop_loss_pips: number;
  risk_reward: number;
  risk_percent: number;
  sessions: string[];
}

export interface CreateScheduleRequest {
  pair: string;
  timeframe: string;
  cron: string;
  indicator: Indicator;
  min_pips: number;
  stop_loss_pips: number;
  risk_reward: number;
  risk_percent: number;
  notify: boolean;
  notify_email?: string | null;
  sessions: string[];
  ifvg_threshold: number;
  auto_execute: boolean;
  auto_lot_size?: number | null;
  max_risk_amount?: number | null;
  auto_close_profit: boolean;
  auto_close_profit_amount?: number | null;
}

export interface CreateTradeRequest {
  pair: string;
  direction: "BUY" | "SELL";
  order_type: "MARKET" | "LIMIT" | "STOP";
  entry?: number;
  lot_size: number;
  stop_loss: number;
  take_profit: number;
}

export const AVAILABLE_SESSIONS = ["LONDON", "NEW_YORK", "ASIA", "TOKYO", "SYDNEY"] as const;
export type Session = typeof AVAILABLE_SESSIONS[number];

// ── Journal ───────────────────────────────────────────────────────────────────

export type JournalOutcome   = "WIN" | "LOSS";
export type JournalSession   = "LONDON" | "NEW_YORK";
export type JournalStrategy  = "BOX_MODEL";
export type JournalTradeMode = "AI" | "MANUAL";

export interface JournalEntry {
  id:         string;
  pair:       string;
  lot_size:   number;
  strategy:   JournalStrategy;
  session:    JournalSession;
  trade_mode: JournalTradeMode;
  amount_usd: number; // signed: positive = profit, negative = loss
  outcome:    JournalOutcome;
  trade_date: string;
  created_at: string;
}

export interface CreateJournalEntryRequest {
  pair:       string;
  lot_size:   number;
  strategy:   JournalStrategy;
  session:    JournalSession;
  trade_mode: JournalTradeMode;
  amount_usd: number; // always positive — backend applies sign from outcome
  outcome:    JournalOutcome;
  trade_date: string; // YYYY-MM-DD
}

export interface BacktestRequest {
  pair: string;
  timeframe: string;
  indicator: Indicator;
  start_date: string;
  end_date: string;
  min_pips: number;
  stop_loss_pips: number;
  risk_reward: number;
  risk_percent: number;
  initial_balance: number;
  sessions: string[];
  ifvg_threshold: number;
}

export interface BacktestJob {
  job_id: string;
  status: BacktestStatus;
  created_at: string;
  completed_at?: string;
  error?: string;
  pair?: string;
  timeframe?: string;
  indicator?: Indicator;
  start_date?: string;
  end_date?: string;
  min_pips?: number;
  stop_loss_pips?: number;
  risk_reward?: number;
  risk_percent?: number;
  initial_balance?: number;
  sessions?: string[];
  ifvg_threshold?: number;
  // inline metrics (present for DONE runs)
  traded?: number;
  win_rate?: number;
  total_pips?: number;
  profit_factor?: number;
  max_drawdown?: number;
  sharpe_ratio?: number;
}

export interface BacktestResults {
  job_id: string;
  summary: {
    total_signals: number;
    skipped: number;
    traded: number;
    win_rate: string;
    profit_factor: number;
    sharpe_ratio: number;
    max_drawdown: string;
    total_return_pips: number;
    directional_acc: string;
  };
  by_session: Record<string, { trades: number; win_rate: number; total_pips: number; avg_pips: number }>;
  by_confidence: Record<string, { trades: number; win_rate: number; total_pips: number; avg_pips: number }>;
  by_news_impact: Record<string, { trades: number; win_rate: number; total_pips: number; avg_pips: number }>;
  equity_curve: number[];
}
