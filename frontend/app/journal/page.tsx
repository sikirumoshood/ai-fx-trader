"use client";

import { useState, useMemo } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { format, getDaysInMonth, getDay, parseISO } from "date-fns";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Legend, Cell,
  AreaChart, Area, ReferenceLine,
} from "recharts";
import { Plus, ChevronLeft, ChevronRight } from "lucide-react";
import { toast } from "sonner";

import { api } from "@/lib/api";
import type { JournalEntry, JournalOutcome, JournalSession, JournalTradeMode } from "@/lib/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";

// ── Constants ─────────────────────────────────────────────────────────────────

const MONTH_NAMES = [
  "January","February","March","April","May","June",
  "July","August","September","October","November","December",
];
const DAY_LABELS = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"];

// ── Helpers ───────────────────────────────────────────────────────────────────

function toDateKey(iso: string) { return iso.substring(0, 10); }

function groupByDate(entries: JournalEntry[]) {
  const map = new Map<string, JournalEntry[]>();
  for (const e of entries) {
    const key = toDateKey(e.trade_date);
    if (!map.has(key)) map.set(key, []);
    map.get(key)!.push(e);
  }
  return map;
}

function isoWeekday(date: Date) { return (getDay(date) + 6) % 7; }

function fmt$(v: number) {
  return `${v >= 0 ? "+" : ""}$${Math.abs(v).toFixed(2)}`;
}

// ── Day Detail Modal ──────────────────────────────────────────────────────────

function DayDetailModal({ dateKey, entries, onClose }: {
  dateKey: string;
  entries: JournalEntry[];
  onClose: () => void;
}) {
  const date    = parseISO(dateKey);
  const net     = entries.reduce((s, e) => s + e.amount_usd, 0);
  const wins    = entries.filter(e => e.outcome === "WIN").length;
  const losses  = entries.filter(e => e.outcome === "LOSS").length;

  return (
    <Dialog
      open
      onClose={onClose}
      title={format(date, "EEEE, MMMM d yyyy")}
      className="max-w-xl"
    >
      {/* Day summary */}
      <div className="mb-4 flex items-center gap-4 rounded-md border border-border bg-background/50 px-4 py-3 text-sm">
        <span className={`font-semibold ${net >= 0 ? "text-emerald-400" : "text-red-400"}`}>
          {net >= 0 ? "+" : ""}${net.toFixed(2)} net
        </span>
        <span className="text-muted-foreground">·</span>
        <span className="text-emerald-400">{wins}W</span>
        <span className="text-muted-foreground">/</span>
        <span className="text-red-400">{losses}L</span>
        <span className="ml-auto text-muted-foreground">{entries.length} trade{entries.length !== 1 ? "s" : ""}</span>
      </div>

      {/* Trade rows */}
      <div className="space-y-2">
        {entries.map((e, i) => (
          <div
            key={e.id}
            className={`rounded-md border px-4 py-3 text-sm ${
              e.outcome === "WIN"
                ? "border-emerald-800/60 bg-emerald-900/20"
                : "border-red-800/60 bg-red-900/20"
            }`}
          >
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <span className="font-semibold">{e.pair}</span>
                <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${
                  e.outcome === "WIN" ? "bg-emerald-800/50 text-emerald-300" : "bg-red-800/50 text-red-300"
                }`}>{e.outcome}</span>
                <span className="text-[10px] text-muted-foreground">{e.trade_mode}</span>
              </div>
              <span className={`font-semibold ${e.amount_usd >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                {e.amount_usd >= 0 ? "+" : ""}${Math.abs(e.amount_usd).toFixed(2)}
              </span>
            </div>
            <div className="mt-1.5 flex flex-wrap gap-x-4 gap-y-0.5 text-[11px] text-muted-foreground">
              <span>Lot: <span className="text-foreground">{e.lot_size}</span></span>
              <span>Strategy: <span className="text-foreground">{e.strategy.replace("_", " ")}</span></span>
              <span>Session: <span className="text-foreground">{e.session.replace("_", " ")}</span></span>
            </div>
          </div>
        ))}
      </div>
    </Dialog>
  );
}

// ── Calendar ──────────────────────────────────────────────────────────────────

function MonthCalendar({ year, month, byDate, onDayClick }: {
  year: number;
  month: number;
  byDate: Map<string, JournalEntry[]>;
  onDayClick: (dateKey: string, entries: JournalEntry[]) => void;
}) {
  const firstDay    = new Date(year, month - 1, 1);
  const daysCount   = getDaysInMonth(firstDay);
  const startOffset = isoWeekday(firstDay);

  const cells: Array<{ day: number | null; key: string | null }> = [];
  for (let i = 0; i < startOffset; i++) cells.push({ day: null, key: null });
  for (let d = 1; d <= daysCount; d++) {
    const key = `${year}-${String(month).padStart(2,"0")}-${String(d).padStart(2,"0")}`;
    cells.push({ day: d, key });
  }

  return (
    <div className="min-w-[280px]">
      <p className="mb-2 text-center text-sm font-semibold">{MONTH_NAMES[month - 1]} {year}</p>
      <div className="mb-1 grid grid-cols-7 gap-1 text-center text-xs text-muted-foreground">
        {DAY_LABELS.map(l => <span key={l}>{l}</span>)}
      </div>
      <div className="grid grid-cols-7 gap-1">
        {cells.map((cell, i) => {
          if (!cell.day || !cell.key) return <div key={i} className="h-14 rounded" />;
          const dayEntries = byDate.get(cell.key) ?? [];
          const net     = dayEntries.reduce((s, e) => s + e.amount_usd, 0);
          const hasData = dayEntries.length > 0;
          const wins    = dayEntries.filter(e => e.outcome === "WIN").length;
          const losses  = dayEntries.filter(e => e.outcome === "LOSS").length;
          const bg = !hasData
            ? "bg-card border border-border"
            : net >= 0 ? "bg-emerald-900/60 border border-emerald-700"
                       : "bg-red-900/60 border border-red-800";
          return (
            <button
              key={cell.key}
              onClick={() => hasData && onDayClick(cell.key!, dayEntries)}
              className={`flex h-14 w-full flex-col items-center justify-center rounded px-0.5 text-center transition-opacity ${bg} ${
                hasData ? "cursor-pointer hover:opacity-80" : "cursor-default"
              }`}
            >
              <span className="text-[10px] text-muted-foreground">{cell.day}</span>
              {hasData && (
                <>
                  <span className={`text-[10px] font-semibold leading-none ${net >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                    {net >= 0 ? "+" : ""}{net.toFixed(2)}
                  </span>
                  <span className="text-[9px] leading-none text-muted-foreground">{wins}W / {losses}L</span>
                </>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}

// ── Summary Stats ─────────────────────────────────────────────────────────────

function SummaryStats({ entries }: { entries: JournalEntry[] }) {
  const wins    = entries.filter(e => e.outcome === "WIN").length;
  const losses  = entries.filter(e => e.outcome === "LOSS").length;
  const net     = entries.reduce((s, e) => s + e.amount_usd, 0);
  const total   = entries.length;
  const winRate = total > 0 ? ((wins / total) * 100).toFixed(1) : "0.0";

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      {[
        { label: "Net P&L",  value: `${net >= 0 ? "+" : ""}$${net.toFixed(2)}`, color: net >= 0 ? "text-emerald-400" : "text-red-400" },
        { label: "Win Rate", value: `${winRate}%`,  color: "text-foreground" },
        { label: "Wins",     value: String(wins),   color: "text-emerald-400" },
        { label: "Losses",   value: String(losses), color: "text-red-400" },
      ].map(({ label, value, color }) => (
        <Card key={label}>
          <CardContent className="p-4">
            <p className="text-xs text-muted-foreground">{label}</p>
            <p className={`mt-1 text-xl font-bold ${color}`}>{value}</p>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

// ── Tooltip styles ────────────────────────────────────────────────────────────

const TOOLTIP_STYLE = {
  contentStyle: {
    background: "hsl(var(--card))",
    border: "1px solid hsl(var(--border))",
    borderRadius: 6,
    fontSize: 12,
    color: "hsl(var(--foreground))",
  },
  labelStyle: { color: "hsl(var(--muted-foreground))", marginBottom: 4 },
};

const AXIS_TICK = { fontSize: 11, fill: "hsl(var(--muted-foreground))" };
const GRID     = { strokeDasharray: "3 3", stroke: "hsl(var(--border))" };

// ── Analytics Section ─────────────────────────────────────────────────────────

function AnalyticsSection({ allEntries, year }: { allEntries: JournalEntry[]; year: number }) {
  const now = new Date();
  const [month,   setMonth]   = useState(now.getMonth() + 1);
  const [pair,    setPair]    = useState("ALL");
  const [session, setSession] = useState("ALL");

  // Unique pairs in the data
  const availablePairs = useMemo(
    () => [...new Set(allEntries.map(e => e.pair))].sort(),
    [allEntries],
  );

  // Apply analytics filters
  const filtered = useMemo(() => allEntries.filter(e => {
    const d = parseISO(e.trade_date);
    if (d.getFullYear() !== year || d.getMonth() + 1 !== month) return false;
    if (pair    !== "ALL" && e.pair    !== pair)    return false;
    if (session !== "ALL" && e.session !== session) return false;
    return true;
  }), [allEntries, year, month, pair, session]);

  // Build per-day rows for the selected month
  const daysInMonth = getDaysInMonth(new Date(year, month - 1));

  const dailyData = useMemo(() => {
    let cumPnl = 0;
    return Array.from({ length: daysInMonth }, (_, i) => {
      const d   = i + 1;
      const key = `${year}-${String(month).padStart(2,"0")}-${String(d).padStart(2,"0")}`;
      const dayEntries = filtered.filter(e => toDateKey(e.trade_date) === key);
      const wins   = dayEntries.filter(e => e.outcome === "WIN");
      const losses = dayEntries.filter(e => e.outcome === "LOSS");
      const net    = dayEntries.reduce((s, e) => s + e.amount_usd, 0);
      cumPnl += net;
      return {
        day:        String(d),
        winCount:   wins.length,
        lossCount:  losses.length,
        totalWon:   parseFloat(wins.reduce((s, e) => s + e.amount_usd, 0).toFixed(2)),
        totalLost:  parseFloat(Math.abs(losses.reduce((s, e) => s + e.amount_usd, 0)).toFixed(2)),
        netPnl:     parseFloat(net.toFixed(2)),
        cumPnl:     parseFloat(cumPnl.toFixed(2)),
        hasTrades:  dayEntries.length > 0,
      };
    });
  }, [filtered, month, daysInMonth, year]);

  // For count / $ charts only show days that actually have trades
  const tradingDays = useMemo(() => dailyData.filter(d => d.hasTrades), [dailyData]);

  const isEmpty = filtered.length === 0;

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <CardTitle>Analytics</CardTitle>

          {/* Filters */}
          <div className="flex flex-wrap items-center gap-2">
            <Select
              value={String(month)}
              onChange={e => setMonth(Number(e.target.value))}
              className="h-8 w-32 text-xs"
            >
              {MONTH_NAMES.map((name, i) => (
                <option key={i + 1} value={i + 1}>{name}</option>
              ))}
            </Select>

            <Select
              value={pair}
              onChange={e => setPair(e.target.value)}
              className="h-8 w-28 text-xs"
            >
              <option value="ALL">All Pairs</option>
              {availablePairs.map(p => <option key={p} value={p}>{p}</option>)}
            </Select>

            <Select
              value={session}
              onChange={e => setSession(e.target.value)}
              className="h-8 w-32 text-xs"
            >
              <option value="ALL">All Sessions</option>
              <option value="LONDON">London</option>
              <option value="NEW_YORK">New York</option>
            </Select>
          </div>
        </div>
      </CardHeader>

      <CardContent className="space-y-8">
        {isEmpty ? (
          <p className="py-12 text-center text-sm text-muted-foreground">
            No trades for {MONTH_NAMES[month - 1]} {year}
            {pair !== "ALL" ? ` · ${pair}` : ""}
            {session !== "ALL" ? ` · ${session}` : ""}.
          </p>
        ) : (
          <>
            {/* ── Chart 1: Win/Loss Count by Day ────────────────────────── */}
            <div>
              <p className="mb-3 text-xs font-medium text-muted-foreground uppercase tracking-wide">
                Win / Loss Count by Day
              </p>
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={tradingDays} margin={{ top: 4, right: 8, left: -10, bottom: 0 }} barGap={2}>
                  <CartesianGrid {...GRID} />
                  <XAxis dataKey="day" tick={AXIS_TICK} label={{ value: "Day", position: "insideBottom", offset: -2, fontSize: 10, fill: "hsl(var(--muted-foreground))" }} />
                  <YAxis allowDecimals={false} tick={AXIS_TICK} />
                  <Tooltip
                    {...TOOLTIP_STYLE}
                    formatter={(val, name) => [val, name === "winCount" ? "Wins" : "Losses"]}
                    labelFormatter={day => `Day ${day}`}
                  />
                  <Legend
                    formatter={val => val === "winCount" ? "Wins" : "Losses"}
                    wrapperStyle={{ fontSize: 12 }}
                  />
                  <Bar dataKey="winCount"  name="winCount"  fill="#10b981" radius={[3,3,0,0]} />
                  <Bar dataKey="lossCount" name="lossCount" fill="#ef4444" radius={[3,3,0,0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>

            {/* ── Chart 2: Total Won vs Total Lost by Day ───────────────── */}
            <div>
              <p className="mb-3 text-xs font-medium text-muted-foreground uppercase tracking-wide">
                Total Won vs Total Lost by Day (USD)
              </p>
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={tradingDays} margin={{ top: 4, right: 8, left: -10, bottom: 0 }} barGap={2}>
                  <CartesianGrid {...GRID} />
                  <XAxis dataKey="day" tick={AXIS_TICK} label={{ value: "Day", position: "insideBottom", offset: -2, fontSize: 10, fill: "hsl(var(--muted-foreground))" }} />
                  <YAxis tick={AXIS_TICK} tickFormatter={v => `$${v}`} />
                  <Tooltip
                    {...TOOLTIP_STYLE}
                    formatter={(val, name) => [
                      typeof val === "number" ? `$${val.toFixed(2)}` : val,
                      name === "totalWon" ? "Total Won" : "Total Lost",
                    ]}
                    labelFormatter={day => `Day ${day}`}
                  />
                  <Legend
                    formatter={val => val === "totalWon" ? "Total Won" : "Total Lost"}
                    wrapperStyle={{ fontSize: 12 }}
                  />
                  <Bar dataKey="totalWon"  name="totalWon"  fill="#10b981" radius={[3,3,0,0]} />
                  <Bar dataKey="totalLost" name="totalLost" fill="#ef4444" radius={[3,3,0,0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>

            {/* ── Chart 3: Cumulative P&L ───────────────────────────────── */}
            <div>
              <p className="mb-3 text-xs font-medium text-muted-foreground uppercase tracking-wide">
                Cumulative P&L — {MONTH_NAMES[month - 1]} {year}
              </p>
              <ResponsiveContainer width="100%" height={200}>
                <AreaChart data={dailyData} margin={{ top: 4, right: 8, left: -10, bottom: 0 }}>
                  <defs>
                    <linearGradient id="pnlGradient" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%"  stopColor="#10b981" stopOpacity={0.25} />
                      <stop offset="95%" stopColor="#10b981" stopOpacity={0.02} />
                    </linearGradient>
                    <linearGradient id="pnlGradientNeg" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%"  stopColor="#ef4444" stopOpacity={0.25} />
                      <stop offset="95%" stopColor="#ef4444" stopOpacity={0.02} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid {...GRID} />
                  <XAxis dataKey="day" tick={AXIS_TICK} label={{ value: "Day", position: "insideBottom", offset: -2, fontSize: 10, fill: "hsl(var(--muted-foreground))" }} />
                  <YAxis tick={AXIS_TICK} tickFormatter={v => `$${v}`} />
                  <ReferenceLine y={0} stroke="hsl(var(--border))" strokeWidth={1.5} />
                  <Tooltip
                    {...TOOLTIP_STYLE}
                    formatter={val => [typeof val === "number" ? fmt$(val) : val, "Cumulative P&L"]}
                    labelFormatter={day => `Day ${day}`}
                  />
                  <Area
                    type="monotone"
                    dataKey="cumPnl"
                    stroke="#10b981"
                    strokeWidth={2}
                    fill="url(#pnlGradient)"
                    dot={false}
                    activeDot={{ r: 4, fill: "#10b981" }}
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>

            {/* ── Chart 4: Net P&L per Day (bar, colored by sign) ─────── */}
            <div>
              <p className="mb-3 text-xs font-medium text-muted-foreground uppercase tracking-wide">
                Net P&L per Day (USD)
              </p>
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={tradingDays} margin={{ top: 4, right: 8, left: -10, bottom: 0 }}>
                  <CartesianGrid {...GRID} />
                  <XAxis dataKey="day" tick={AXIS_TICK} label={{ value: "Day", position: "insideBottom", offset: -2, fontSize: 10, fill: "hsl(var(--muted-foreground))" }} />
                  <YAxis tick={AXIS_TICK} tickFormatter={v => `$${v}`} />
                  <ReferenceLine y={0} stroke="hsl(var(--border))" strokeWidth={1.5} />
                  <Tooltip
                    {...TOOLTIP_STYLE}
                    formatter={val => [typeof val === "number" ? fmt$(val) : val, "Net P&L"]}
                    labelFormatter={day => `Day ${day}`}
                  />
                  <Bar dataKey="netPnl" radius={[3,3,0,0]}>
                    {tradingDays.map((entry, idx) => (
                      <Cell key={idx} fill={entry.netPnl >= 0 ? "#10b981" : "#ef4444"} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}

// ── Add Entry Form ────────────────────────────────────────────────────────────

const FALLBACK_PAIRS = [
  "EURUSD","GBPUSD","USDJPY","USDCHF","AUDUSD",
  "USDCAD","NZDUSD","GBPJPY","EURJPY","EURGBP","XAUUSD",
];

type FormState = {
  pair:       string;
  lot_size:   string;
  strategy:   string;
  session:    JournalSession;
  trade_mode: JournalTradeMode;
  amount_usd: string;
  outcome:    JournalOutcome;
  trade_date: string;
};

const DEFAULT_FORM: FormState = {
  pair:       "EURUSD",
  lot_size:   "0.10",
  strategy:   "BOX_MODEL",
  session:    "LONDON",
  trade_mode: "MANUAL",
  amount_usd: "",
  outcome:    "WIN",
  trade_date: format(new Date(), "yyyy-MM-dd"),
};

function AddEntryDialog({ open, onClose, pairsData }: {
  open: boolean; onClose: () => void; pairsData?: string[];
}) {
  const [form, setForm] = useState<FormState>(DEFAULT_FORM);
  const qc = useQueryClient();

  const createEntry = useMutation({
    mutationFn: api.journal.create,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["journal"] });
      toast.success("Journal entry saved");
      setForm(DEFAULT_FORM);
      onClose();
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const set = (k: keyof FormState, v: string) => setForm(f => ({ ...f, [k]: v }));

  function handleSubmit() {
    const lot = parseFloat(form.lot_size);
    const amt = parseFloat(form.amount_usd);
    if (!form.pair || isNaN(lot) || lot <= 0 || isNaN(amt) || amt <= 0) {
      toast.error("Fill in all fields with valid values");
      return;
    }
    createEntry.mutate({
      pair:       form.pair,
      lot_size:   lot,
      strategy:   form.strategy as "BOX_MODEL",
      session:    form.session,
      trade_mode: form.trade_mode,
      amount_usd: amt,
      outcome:    form.outcome,
      trade_date: form.trade_date,
    });
  }

  const availablePairs = pairsData?.length ? pairsData : FALLBACK_PAIRS;

  return (
    <Dialog open={open} onClose={onClose} title="Add Journal Entry">
      <div className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label>Pair</Label>
            <Select value={form.pair} onChange={e => set("pair", e.target.value)}>
              {availablePairs.map(p => <option key={p}>{p}</option>)}
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label>Lot Size</Label>
            <Input type="number" step="0.01" min="0.01" placeholder="0.10"
              value={form.lot_size} onChange={e => set("lot_size", e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label>Strategy</Label>
            <Select value={form.strategy} onChange={e => set("strategy", e.target.value)}>
              <option value="BOX_MODEL">Box Model</option>
              <option value="IFVG">IFVG</option>
              <option value="BOX_BREAKOUT">Box Breakout</option>
              <option value="ORDER_BLOCK">Order Block</option>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label>Session</Label>
            <Select value={form.session} onChange={e => set("session", e.target.value as JournalSession)}>
              <option value="LONDON">London</option>
              <option value="NEW_YORK">New York</option>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label>Trade Mode</Label>
            <Select value={form.trade_mode} onChange={e => set("trade_mode", e.target.value as JournalTradeMode)}>
              <option value="MANUAL">Manual</option>
              <option value="AI">AI</option>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label>Outcome</Label>
            <Select value={form.outcome} onChange={e => set("outcome", e.target.value as JournalOutcome)}>
              <option value="WIN">Win</option>
              <option value="LOSS">Loss</option>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label>Amount Realised (USD)</Label>
            <Input type="number" step="0.01" min="0.01" placeholder="e.g. 120.00"
              value={form.amount_usd} onChange={e => set("amount_usd", e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label>Trade Date</Label>
            <Input type="date" value={form.trade_date} onChange={e => set("trade_date", e.target.value)} />
          </div>
        </div>

        {createEntry.error && (
          <p className="text-xs text-red-400">{(createEntry.error as Error).message}</p>
        )}
        <div className="flex flex-col-reverse gap-2 pt-2 sm:flex-row sm:justify-end">
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button onClick={handleSubmit} disabled={createEntry.isPending}>
            {createEntry.isPending ? "Saving…" : "Save Entry"}
          </Button>
        </div>
      </div>
    </Dialog>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export default function JournalPage() {
  const now = new Date();
  const [year, setYear]             = useState(now.getFullYear());
  const [selectedMonths, setMonths] = useState<number[]>([now.getMonth() + 1]);
  const [formOpen, setFormOpen]     = useState(false);
  const [dayDetail, setDayDetail]   = useState<{ dateKey: string; entries: JournalEntry[] } | null>(null);

  const { data: allEntries = [], isLoading } = useQuery({
    queryKey: ["journal", year],
    queryFn:  () => api.journal.list(year),
  });

  const { data: pairsData } = useQuery({
    queryKey: ["pairs"],
    queryFn:  api.pairs,
  });

  const calEntries = useMemo(
    () => allEntries.filter(e => selectedMonths.includes(parseISO(e.trade_date).getMonth() + 1)),
    [allEntries, selectedMonths],
  );

  const byDate = useMemo(() => groupByDate(calEntries), [calEntries]);

  function toggleMonth(m: number) {
    setMonths(prev =>
      prev.includes(m)
        ? prev.length === 1 ? prev : prev.filter(x => x !== m)
        : [...prev, m].sort((a, b) => a - b),
    );
  }

  const years = Array.from({ length: 5 }, (_, i) => now.getFullYear() - i);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <h1 className="text-xl font-semibold">Trade Journal</h1>
        <Button onClick={() => setFormOpen(true)} className="w-full sm:w-auto">
          <Plus className="mr-1.5 h-4 w-4" /> Add Entry
        </Button>
      </div>

      {/* Calendar filters */}
      <Card>
        <CardContent className="p-4">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center">
            <div className="flex items-center gap-2">
              <button onClick={() => { setYear(y => y - 1); setMonths([1]); }} className="rounded p-1 hover:bg-accent">
                <ChevronLeft className="h-4 w-4" />
              </button>
              <Select value={String(year)} onChange={e => { setYear(Number(e.target.value)); setMonths([now.getMonth() + 1]); }} className="w-24">
                {years.map(y => <option key={y} value={y}>{y}</option>)}
              </Select>
              <button onClick={() => { setYear(y => y + 1); setMonths([1]); }} className="rounded p-1 hover:bg-accent">
                <ChevronRight className="h-4 w-4" />
              </button>
            </div>
            <div className="flex flex-wrap gap-1">
              {MONTH_NAMES.map((name, i) => {
                const m = i + 1;
                const active = selectedMonths.includes(m);
                return (
                  <button key={m} onClick={() => toggleMonth(m)}
                    className={`rounded-full px-2.5 py-0.5 text-xs font-medium transition-colors ${
                      active ? "bg-primary text-primary-foreground" : "bg-accent text-muted-foreground hover:text-foreground"
                    }`}>
                    {name.slice(0, 3)}
                  </button>
                );
              })}
              <button onClick={() => setMonths([1,2,3,4,5,6,7,8,9,10,11,12])}
                className="rounded-full border border-border px-2.5 py-0.5 text-xs text-muted-foreground hover:text-foreground">
                All
              </button>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Summary stats */}
      <SummaryStats entries={calEntries} />

      {/* Calendar */}
      <Card>
        <CardHeader><CardTitle>Calendar</CardTitle></CardHeader>
        <CardContent>
          {isLoading
            ? <p className="py-12 text-center text-sm text-muted-foreground">Loading…</p>
            : <div className="flex flex-wrap gap-6">
                {selectedMonths.map(m => (
                  <MonthCalendar
                    key={m}
                    year={year}
                    month={m}
                    byDate={byDate}
                    onDayClick={(dateKey, entries) => setDayDetail({ dateKey, entries })}
                  />
                ))}
              </div>
          }
        </CardContent>
      </Card>

      {/* Analytics */}
      <AnalyticsSection allEntries={allEntries} year={year} />

      <AddEntryDialog open={formOpen} onClose={() => setFormOpen(false)} pairsData={pairsData?.pairs} />

      {dayDetail && (
        <DayDetailModal
          dateKey={dayDetail.dateKey}
          entries={dayDetail.entries}
          onClose={() => setDayDetail(null)}
        />
      )}
    </div>
  );
}
