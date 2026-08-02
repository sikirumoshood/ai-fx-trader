"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { BacktestJob } from "@/lib/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine } from "recharts";

function BreakdownTable({
  title,
  data,
  rowKey,
}: {
  title: string;
  data: Record<string, { trades: number; win_rate: number; total_pips: number; avg_pips: number }>;
  rowKey: string;
}) {
  const entries = Object.entries(data);
  if (entries.length === 0) return null;
  return (
    <Card>
      <CardHeader className="pb-2"><CardTitle className="text-sm">{title}</CardTitle></CardHeader>
      <CardContent className="pt-0">
        <div className="overflow-x-auto">
        <table className="w-full min-w-[520px] text-sm">
          <thead>
            <tr className="text-muted-foreground text-xs border-b border-border">
              <th className="text-left py-1.5">{rowKey}</th>
              <th className="text-right py-1.5">Trades</th>
              <th className="text-right py-1.5">Win Rate</th>
              <th className="text-right py-1.5">Avg Pips</th>
              <th className="text-right py-1.5">Total Pips</th>
            </tr>
          </thead>
          <tbody>
            {entries.map(([key, d]) => (
              <tr key={key} className="border-b border-border/40 last:border-0">
                <td className="py-1.5 font-medium">{key}</td>
                <td className="py-1.5 text-right text-muted-foreground">{d.trades}</td>
                <td className="py-1.5 text-right">{(d.win_rate * 100).toFixed(1)}%</td>
                <td className={`py-1.5 text-right font-mono text-xs ${d.avg_pips >= 0 ? "text-green-400" : "text-red-400"}`}>
                  {d.avg_pips > 0 ? "+" : ""}{d.avg_pips.toFixed(1)}
                </td>
                <td className={`py-1.5 text-right font-mono ${d.total_pips >= 0 ? "text-green-400" : "text-red-400"}`}>
                  {d.total_pips > 0 ? "+" : ""}{d.total_pips.toFixed(1)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        </div>
      </CardContent>
    </Card>
  );
}

export function BacktestResults({ jobId }: { jobId: string }) {
  const queryClient = useQueryClient();

  const { data: statusJob } = useQuery({
    queryKey: ["backtest-status", jobId],
    queryFn: () => api.backtest.status(jobId),
    refetchInterval: (q) => {
      const s = q.state.data?.status;
      return s === "DONE" || s === "FAILED" ? false : 3000;
    },
  });

  // The list query is always fresh (polls). Use it as the primary source for
  // run metadata (pair, timeframe, dates, params) — the status query may have
  // stale cache from before the endpoint was updated.
  const listJobs = queryClient.getQueryData<BacktestJob[]>(["backtests"]) ?? [];
  const listJob = listJobs.find((j) => j.job_id === jobId);

  // Merge: list data fills in metadata; status query provides live status
  const job: BacktestJob | undefined = statusJob
    ? { ...listJob, ...statusJob }
    : listJob;

  const { data: results } = useQuery({
    queryKey: ["backtest-results", jobId],
    queryFn: () => api.backtest.results(jobId),
    enabled: job?.status === "DONE",
  });

  if (!job) return null;

  const duration = job.completed_at && job.created_at
    ? (() => {
        const ms = new Date(job.completed_at).getTime() - new Date(job.created_at).getTime();
        const s = Math.round(ms / 1000);
        return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${s % 60}s`;
      })()
    : null;

  if (job.status === "QUEUED" || job.status === "RUNNING") {
    return (
      <div className="flex items-center gap-3 py-8 justify-center text-muted-foreground text-sm">
        <div className="w-4 h-4 border-2 border-primary border-t-transparent rounded-full animate-spin" />
        Backtest {job.status.toLowerCase()}...
      </div>
    );
  }

  if (job.status === "FAILED") {
    return <p className="text-red-400 text-sm py-4">Backtest failed: {job.error}</p>;
  }

  if (!results) return null;

  const s = results.summary;
  const equityCurve = results.equity_curve?.map((v, i) => ({ i, pips: v })) ?? [];

  const totalPips = typeof s.total_return_pips === "number" ? s.total_return_pips : 0;

  const summaryCards = [
    { label: "Trades",          value: s.traded,           sub: `of ${s.total_signals} signals` },
    { label: "Skipped",         value: s.skipped,          sub: null },
    { label: "Win Rate",        value: s.win_rate,         sub: null },
    { label: "Directional Acc", value: s.directional_acc,  sub: null },
    { label: "Total Pips",      value: `${totalPips > 0 ? "+" : ""}${totalPips.toFixed ? totalPips.toFixed(1) : totalPips}`, sub: null, positive: totalPips >= 0 },
    { label: "Profit Factor",   value: typeof s.profit_factor === "number" ? s.profit_factor.toFixed(2) : s.profit_factor, sub: null },
    { label: "Sharpe Ratio",    value: typeof s.sharpe_ratio === "number" ? s.sharpe_ratio.toFixed(2) : s.sharpe_ratio, sub: null },
    { label: "Max Drawdown",    value: s.max_drawdown,     sub: null },
  ];

  return (
    <div className="space-y-5">
      {/* Run metadata */}
      <div className="flex flex-wrap gap-x-6 gap-y-1 rounded-md border border-border bg-muted/30 px-4 py-3 text-sm">
        <span><span className="text-muted-foreground">Pair: </span><strong>{job.pair}</strong></span>
        <span><span className="text-muted-foreground">TF: </span><strong>{job.timeframe}</strong></span>
        {job.indicator && (
          <span><span className="text-muted-foreground">Indicator: </span><strong>{job.indicator.toUpperCase()}</strong></span>
        )}
        {job.start_date && job.end_date && (
          <span>
            <span className="text-muted-foreground">Range: </span>
            <strong>{String(job.start_date).slice(0, 10)} → {String(job.end_date).slice(0, 10)}</strong>
          </span>
        )}
        {job.indicator === "ifvg" ? (
          job.ifvg_threshold != null && job.ifvg_threshold > 0 && (
            <span><span className="text-muted-foreground">Gap threshold: </span><strong>{job.ifvg_threshold}</strong></span>
          )
        ) : (
          job.min_pips != null && (
            <span><span className="text-muted-foreground">Min pips: </span><strong>{job.min_pips}</strong></span>
          )
        )}
        {job.stop_loss_pips != null && (
          <span><span className="text-muted-foreground">SL: </span><strong>{job.stop_loss_pips} pips</strong></span>
        )}
        {job.risk_reward != null && (
          <span><span className="text-muted-foreground">RR: </span><strong>1:{job.risk_reward}</strong></span>
        )}
        {job.initial_balance != null && (
          <span><span className="text-muted-foreground">Balance: </span><strong>${job.initial_balance.toLocaleString()}</strong></span>
        )}
        {duration && (
          <span className="sm:ml-auto"><span className="text-muted-foreground">Duration: </span><strong>{duration}</strong></span>
        )}
      </div>

      {/* Summary metric cards */}
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {summaryCards.map(({ label, value, sub, positive }) => (
          <div key={label} className="rounded-md border border-border bg-card px-3 py-2.5">
            <p className="text-xs text-muted-foreground mb-1">{label}</p>
            <p className={`text-lg font-bold leading-none ${positive === false ? "text-red-400" : positive === true ? "text-green-400" : ""}`}>
              {value ?? "—"}
            </p>
            {sub && <p className="text-xs text-muted-foreground mt-0.5">{sub}</p>}
          </div>
        ))}
      </div>

      {/* Equity curve */}
      {equityCurve.length > 0 && (
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm">Equity Curve (pips)</CardTitle></CardHeader>
          <CardContent className="pt-0">
            <ResponsiveContainer width="100%" height={200}>
              <LineChart data={equityCurve}>
                <XAxis dataKey="i" hide />
                <YAxis width={50} tick={{ fontSize: 11 }} />
                <Tooltip formatter={(v) => [`${Number(v).toFixed(1)} pips`, "Equity"]} />
                <ReferenceLine y={0} stroke="#4b5563" strokeDasharray="4" />
                <Line type="monotone" dataKey="pips" stroke={totalPips >= 0 ? "#22c55e" : "#ef4444"} strokeWidth={1.5} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      )}

      {/* Breakdowns */}
      {results.by_session && Object.keys(results.by_session).length > 0 && (
        <BreakdownTable title="By Session" data={results.by_session} rowKey="Session" />
      )}

      {results.by_confidence && Object.keys(results.by_confidence).length > 0 && (
        <BreakdownTable title="By Confidence Tier" data={results.by_confidence} rowKey="Confidence" />
      )}

      {results.by_news_impact && Object.keys(results.by_news_impact).length > 0 && (
        <BreakdownTable title="By News Impact" data={results.by_news_impact} rowKey="Impact" />
      )}
    </div>
  );
}
