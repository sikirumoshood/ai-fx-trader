const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const API_KEY = process.env.NEXT_PUBLIC_API_KEY || "";

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      "X-API-Key": API_KEY,
      ...options.headers,
    },
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail?.reason ?? err.detail ?? res.statusText);
  }

  if (res.status === 204) return undefined as T;
  return res.json();
}

// ── Health ────────────────────────────────────────────────────────────────────
import type {
  Health, Signal, Trade, Schedule, ConfirmResponse,
  AnalyzeRequest, CreateScheduleRequest, CreateTradeRequest,
  BacktestRequest, BacktestJob, BacktestResults,
  JournalEntry, CreateJournalEntryRequest,
} from "./types";

export const api = {
  health: () => request<Health>("/health"),
  pairs:  () => request<{ pairs: string[] }>("/pairs"),

  // Signals
  signals: {
    list:    ()         => request<Signal[]>("/signals"),
    get:     (id: string) => request<Signal>(`/signals/${id}`),
    analyze: (body: AnalyzeRequest) =>
      request<Signal>("/signals/analyze", { method: "POST", body: JSON.stringify(body) }),
    confirm: (id: string, stackCount = 1, lotSize?: number, stopLoss?: number, takeProfit?: number) =>
      request<ConfirmResponse>(`/signals/${id}/confirm`, {
        method: "POST",
        body: JSON.stringify({
          stack_count: stackCount,
          ...(lotSize    != null && { lot_size:    lotSize }),
          ...(stopLoss   != null && { stop_loss:   stopLoss }),
          ...(takeProfit != null && { take_profit: takeProfit }),
        }),
      }),
    reject:  (id: string) => request<{ id: string; status: string }>(`/signals/${id}/reject`, { method: "POST" }),
  },

  // Schedules
  schedules: {
    list:   ()           => request<Schedule[]>("/schedules"),
    get:    (id: string) => request<Schedule>(`/schedules/${id}`),
    create: (body: CreateScheduleRequest) =>
      request<Schedule>("/schedules", { method: "POST", body: JSON.stringify(body) }),
    update: (id: string, body: Partial<CreateScheduleRequest>) =>
      request<Schedule>(`/schedules/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
    delete: (id: string) => request<void>(`/schedules/${id}`, { method: "DELETE" }),
    pause:  (id: string) => request<Schedule>(`/schedules/${id}/pause`,  { method: "POST" }),
    resume: (id: string) => request<Schedule>(`/schedules/${id}/resume`, { method: "POST" }),
  },

  // Trades
  trades: {
    list:   ()           => request<Trade[]>("/trades"),
    get:    (id: string) => request<Trade>(`/trades/${id}`),
    create: (body: CreateTradeRequest) =>
      request<Trade>("/trades", { method: "POST", body: JSON.stringify(body) }),
    modify: (id: string, body: { stop_loss?: number; take_profit?: number }) =>
      request<Trade>(`/trades/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
    close:  (id: string) => request<void>(`/trades/${id}`, { method: "DELETE" }),
  },

  // Journal
  journal: {
    list: (year?: number, month?: number) => {
      const params = new URLSearchParams();
      if (year  != null) params.set("year",  String(year));
      if (month != null) params.set("month", String(month));
      const qs = params.toString();
      return request<JournalEntry[]>(`/journal${qs ? `?${qs}` : ""}`);
    },
    create: (body: CreateJournalEntryRequest) =>
      request<JournalEntry>("/journal", { method: "POST", body: JSON.stringify(body) }),
  },

  // Backtest
  backtest: {
    list:    ()           => request<BacktestJob[]>("/backtests"),
    submit:  (body: BacktestRequest) =>
      request<BacktestJob>("/backtest", { method: "POST", body: JSON.stringify(body) }),
    status:  (id: string) => request<BacktestJob>(`/backtest/${id}`),
    results: (id: string) => request<BacktestResults>(`/backtest/${id}/results`),
  },
};
