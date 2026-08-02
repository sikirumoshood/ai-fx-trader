"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { formatPrice, formatConfidence } from "@/lib/utils";
import { DirectionBadge, StatusBadge } from "./direction-badge";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { format } from "date-fns";
import type { Signal } from "@/lib/types";

function RsiCell({ rsi, advisory }: { rsi: number | null; advisory: string | null }) {
  if (rsi == null) return <span className="text-muted-foreground text-xs">—</span>;

  const isOverbought = rsi > 70;
  const isOversold   = rsi < 30;
  const color = isOverbought
    ? "text-orange-400"
    : isOversold
    ? "text-blue-400"
    : "text-green-500";

  const zone = isOverbought ? "OB" : isOversold ? "OS" : "OK";

  return (
    <span
      className={`text-xs font-mono cursor-default ${color}`}
      title={advisory ?? undefined}
    >
      {rsi} <span className="opacity-60">{zone}</span>
    </span>
  );
}

function PatternCell({ name, bias }: { name: string | null; bias: string | null }) {
  if (!name) return <span className="text-muted-foreground text-xs">—</span>;
  const color = bias === "BULLISH"
    ? "text-buy"
    : bias === "BEARISH"
    ? "text-sell"
    : "text-muted-foreground";
  return (
    <span className={`text-xs font-medium ${color}`} title={bias ?? undefined}>
      {name}
    </span>
  );
}

function StackActions({ sig }: { sig: Signal }) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [count, setCount] = useState(1);
  const [lotSize, setLotSize]   = useState("");
  const [sl, setSl]             = useState(String(sig.stop_loss   ?? ""));
  const [tp, setTp]             = useState(String(sig.take_profit ?? ""));
  const [error, setError]       = useState<string | null>(null);

  const confirm = useMutation({
    mutationFn: () => api.signals.confirm(
      sig.id,
      count,
      lotSize    ? parseFloat(lotSize) : undefined,
      sl         ? parseFloat(sl)      : undefined,
      tp         ? parseFloat(tp)      : undefined,
    ),
    onSuccess: () => {
      qc.setQueryData<Signal[]>(["signals"], old =>
        old?.map(s => s.id === sig.id ? { ...s, status: "EXECUTED" as const } : s)
      );
      qc.invalidateQueries({ queryKey: ["signals"] });
      setOpen(false);
    },
    onError: (err: Error) => setError(err.message),
  });

  const reject = useMutation({
    mutationFn: () => api.signals.reject(sig.id),
    onSuccess: () => {
      qc.setQueryData<Signal[]>(["signals"], old =>
        old?.map(s => s.id === sig.id ? { ...s, status: "REJECTED" as const } : s)
      );
      qc.invalidateQueries({ queryKey: ["signals"] });
    },
  });

  return (
    <>
      <div className="flex items-center gap-1.5">
        <Button size="sm" onClick={() => { setError(null); setOpen(true); }}>
          Confirm
        </Button>
        <Button
          size="sm"
          variant="destructive"
          onClick={() => reject.mutate()}
          disabled={reject.isPending}
        >
          {reject.isPending ? "…" : "Reject"}
        </Button>
      </div>

      <Dialog open={open} onClose={() => setOpen(false)} title="Confirm Trade">
        <div className="space-y-4">
          {/* Signal summary */}
          <div className="text-xs text-muted-foreground bg-accent/30 rounded-md px-3 py-2 space-y-0.5">
            <div className="font-medium text-foreground">
              {sig.pair} {sig.timeframe} —{" "}
              <span className={sig.signal === "BUY" ? "text-buy" : "text-sell"}>{sig.signal}</span>
            </div>
            <div>Confidence: {formatConfidence(sig.confidence)} · R:R {sig.risk_reward}</div>
            {sig.reason && <div className="truncate opacity-70">{sig.reason}</div>}
          </div>

          {/* Stack count */}
          <div className="flex items-center gap-3">
            <Label className="w-28 shrink-0">Stack</Label>
            <div className="flex items-center border border-border rounded-md overflow-hidden">
              <button
                className="px-2 py-1.5 text-xs text-muted-foreground hover:bg-accent/50 disabled:opacity-30"
                onClick={() => setCount(c => Math.max(1, c - 1))}
                disabled={count <= 1}
              >−</button>
              <span className="px-3 py-1.5 text-xs font-mono min-w-[2rem] text-center">{count}</span>
              <button
                className="px-2 py-1.5 text-xs text-muted-foreground hover:bg-accent/50 disabled:opacity-30"
                onClick={() => setCount(c => Math.min(10, c + 1))}
                disabled={count >= 10}
              >+</button>
            </div>
          </div>

          {/* Lot size */}
          <div className="flex items-center gap-3">
            <Label className="w-28 shrink-0">Lot Size</Label>
            <Input
              type="number" min="0.01" step="0.01" placeholder="auto"
              value={lotSize}
              onChange={e => setLotSize(e.target.value)}
              className="w-32 font-mono"
            />
          </div>

          {/* SL */}
          <div className="flex items-center gap-3">
            <Label className="w-28 shrink-0 text-sell">Stop Loss</Label>
            <Input
              type="number" step="0.00001"
              value={sl}
              onChange={e => { setSl(e.target.value); setError(null); }}
              className="w-40 font-mono"
            />
          </div>

          {/* TP */}
          <div className="flex items-center gap-3">
            <Label className="w-28 shrink-0 text-buy">Take Profit</Label>
            <Input
              type="number" step="0.00001"
              value={tp}
              onChange={e => { setTp(e.target.value); setError(null); }}
              className="w-40 font-mono"
            />
          </div>

          {error && <p className="text-xs text-destructive">{error}</p>}

          <div className="flex gap-2 justify-end pt-1">
            <Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
            <Button onClick={() => { setError(null); confirm.mutate(); }} disabled={confirm.isPending}>
              {confirm.isPending ? "Placing…" : count > 1 ? `Stack ×${count}` : "Place Trade"}
            </Button>
          </div>
        </div>
      </Dialog>
    </>
  );
}

export function SignalTable({ signals }: { signals: Signal[] }) {

  if (signals.length === 0) {
    return <p className="text-sm text-muted-foreground py-8 text-center">No signals yet.</p>;
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[880px] text-sm">
        <thead>
          <tr className="border-b border-border text-muted-foreground text-xs">
            <th className="text-left py-2 px-3">Pair</th>
            <th className="text-left py-2 px-3">Dir</th>
            <th className="text-left py-2 px-3">Status</th>
            <th className="text-right py-2 px-3">Entry</th>
            <th className="text-right py-2 px-3">SL</th>
            <th className="text-right py-2 px-3">TP</th>
            <th className="text-right py-2 px-3">Conf</th>
            <th className="text-left py-2 px-3">RSI</th>
            <th className="text-left py-2 px-3">Pattern</th>
            <th className="text-left py-2 px-3">News</th>
            <th className="text-left py-2 px-3">Time</th>
            <th className="py-2 px-3" />
          </tr>
        </thead>
        <tbody>
          {signals.map(sig => (
            <tr key={sig.id} className="border-b border-border/50 hover:bg-accent/30 transition-colors">
              <td className="py-2.5 px-3 font-medium">{sig.pair}<span className="text-muted-foreground ml-1 text-xs">{sig.timeframe}</span></td>
              <td className="py-2.5 px-3"><DirectionBadge direction={sig.signal} /></td>
              <td className="py-2.5 px-3"><StatusBadge status={sig.status} /></td>
              <td className="py-2.5 px-3 text-right font-mono">{formatPrice(sig.entry, sig.pair)}</td>
              <td className="py-2.5 px-3 text-right font-mono text-sell">{formatPrice(sig.stop_loss, sig.pair)}</td>
              <td className="py-2.5 px-3 text-right font-mono text-buy">{formatPrice(sig.take_profit, sig.pair)}</td>
              <td className="py-2.5 px-3 text-right">{formatConfidence(sig.confidence)}</td>
              <td className="py-2.5 px-3">
                <RsiCell rsi={sig.rsi} advisory={sig.rsi_advisory} />
              </td>
              <td className="py-2.5 px-3">
                <PatternCell name={sig.pattern_name} bias={sig.pattern_bias} />
              </td>
              <td className="py-2.5 px-3 text-muted-foreground text-xs">{sig.news_bias ?? "—"}</td>
              <td className="py-2.5 px-3 text-muted-foreground text-xs">{format(new Date(sig.created_at), "HH:mm dd/MM")}</td>
              <td className="py-2.5 px-3">
                {sig.status === "PENDING" && <StackActions sig={sig} />}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
