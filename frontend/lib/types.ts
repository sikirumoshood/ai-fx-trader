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
  reason: string | null;
  pair: string;
  timeframe: string;
  created_at: string;
}

export interface Trade {
  id: string;
  mt5_ticket: number | null;
  pair: string;
  direction: SignalDirection;
  entry: number;
  stop_loss: number | null;
  take_profit: number | null;
  lot_size: number | null;
  open_price: number | null;
  close_price: number | null;
  profit_pips: number | null;
  status: string;
  opened_at: string;
  closed_at: string | null;
}

export interface Schedule {
  id: string;
  status: ScheduleStatus;
  pair: string;
  timeframe: string;
  cron: string;
  min_pips: number;
  stop_loss_pips: number;
  risk_reward: number;
  risk_percent: number;
  notify: boolean;
  sessions?: string[];
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
  min_pips: number;
  stop_loss_pips: number;
  risk_reward: number;
  risk_percent: number;
  notify: boolean;
  sessions: string[];
}

export interface CreateTradeRequest {
  pair: string;
  direction: "BUY" | "SELL";
  lot_size: number;
  stop_loss: number;
  take_profit: number;
}

export const AVAILABLE_SESSIONS = ["LONDON", "NEW_YORK", "ASIA", "TOKYO", "SYDNEY"] as const;
export type Session = typeof AVAILABLE_SESSIONS[number];

export interface BacktestRequest {
  pair: string;
  timeframe: string;
  start_date: string;
  end_date: string;
  min_pips: number;
  stop_loss_pips: number;
  risk_reward: number;
  risk_percent: number;
  initial_balance: number;
  sessions: string[];
}

export interface BacktestJob {
  job_id: string;
  status: BacktestStatus;
  created_at: string;
  completed_at?: string;
  error?: string;
  pair?: string;
  timeframe?: string;
  start_date?: string;
  end_date?: string;
  min_pips?: number;
  stop_loss_pips?: number;
  risk_reward?: number;
  risk_percent?: number;
  initial_balance?: number;
  sessions?: string[];
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
