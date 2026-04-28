"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { BacktestJob } from "@/lib/types";
import { Badge } from "@/components/ui/badge";

const statusColor: Record<string, string> = {
  QUEUED:  "bg-yellow-500/15 text-yellow-400 border-yellow-500/30",
  RUNNING: "bg-blue-500/15 text-blue-400 border-blue-500/30",
  DONE:    "bg-green-500/15 text-green-400 border-green-500/30",
  FAILED:  "bg-red-500/15 text-red-400 border-red-500/30",
};

function hasActiveJob(jobs: BacktestJob[]) {
  return jobs.some(j => j.status === "QUEUED" || j.status === "RUNNING");
}

interface Props {
  selectedJobId: string | null;
  onSelect: (jobId: string) => void;
}

export function BacktestList({ selectedJobId, onSelect }: Props) {
  const { data: jobs = [], isLoading } = useQuery({
    queryKey: ["backtests"],
    queryFn: api.backtest.list,
    refetchInterval: (q) => hasActiveJob(q.state.data ?? []) ? 3000 : 10000,
  });

  if (isLoading) {
    return <p className="text-sm text-muted-foreground py-4 text-center">Loading...</p>;
  }

  if (jobs.length === 0) {
    return (
      <p className="text-sm text-muted-foreground py-8 text-center">
        No backtests yet. Run one using the form.
      </p>
    );
  }

  return (
    <div className="divide-y divide-border">
      {jobs.map((job) => {
        const isActive = job.status === "QUEUED" || job.status === "RUNNING";
        const isSelected = job.job_id === selectedJobId;

        return (
          <button
            key={job.job_id}
            onClick={() => onSelect(job.job_id)}
            className={`w-full text-left px-3 py-3 transition-colors hover:bg-muted/50 ${
              isSelected ? "bg-muted" : ""
            }`}
          >
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2 min-w-0">
                {isActive && (
                  <span className="shrink-0 w-2 h-2 rounded-full bg-blue-400 animate-pulse" />
                )}
                <span className="font-medium text-sm truncate">
                  {job.pair ?? "—"} {job.timeframe ?? ""}
                </span>
              </div>
              <span className={`shrink-0 text-[11px] px-2 py-0.5 rounded border font-medium ${statusColor[job.status] ?? ""}`}>
                {job.status}
              </span>
            </div>

            <div className="mt-1 text-xs text-muted-foreground flex gap-3">
              {job.start_date && job.end_date && (
                <span>
                  {job.start_date.slice(0, 10)} → {job.end_date.slice(0, 10)}
                </span>
              )}
              <span className="ml-auto">
                {new Date(job.created_at).toLocaleString(undefined, {
                  month: "short", day: "numeric",
                  hour: "2-digit", minute: "2-digit",
                })}
              </span>
            </div>

            {job.sessions && job.sessions.length > 0 && (
              <div className="mt-1.5 flex flex-wrap gap-1">
                {job.sessions.map((s) => (
                  <span
                    key={s}
                    className="text-[10px] px-1.5 py-0.5 rounded border bg-violet-500/10 text-violet-400 border-violet-500/25 font-medium"
                  >
                    {s.replace("_", " ")}
                  </span>
                ))}
              </div>
            )}

            {job.status === "DONE" && job.traded != null && (
              <div className="mt-1.5 flex gap-3 text-xs">
                <span className="text-muted-foreground">{job.traded} trades</span>
                <span className="text-muted-foreground">
                  WR: <span className="font-medium text-foreground">{(job.win_rate! * 100).toFixed(1)}%</span>
                </span>
                <span className={`font-medium ${job.total_pips! >= 0 ? "text-green-400" : "text-red-400"}`}>
                  {job.total_pips! > 0 ? "+" : ""}{job.total_pips!.toFixed(1)} pips
                </span>
                <span className="text-muted-foreground ml-auto">
                  PF: {job.profit_factor?.toFixed(2) ?? "—"}
                </span>
              </div>
            )}

            {job.status === "FAILED" && job.error && (
              <p className="mt-1 text-xs text-red-400 truncate">{job.error}</p>
            )}
          </button>
        );
      })}
    </div>
  );
}
