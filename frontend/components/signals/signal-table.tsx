"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { formatPrice, formatConfidence } from "@/lib/utils";
import { DirectionBadge, StatusBadge } from "./direction-badge";
import { Button } from "@/components/ui/button";
import { format } from "date-fns";
import type { Signal } from "@/lib/types";

export function SignalTable({ signals }: { signals: Signal[] }) {
  const qc = useQueryClient();

  const confirm = useMutation({
    mutationFn: api.signals.confirm,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["signals"] }),
  });
  const reject = useMutation({
    mutationFn: api.signals.reject,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["signals"] }),
  });

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
              <td className="py-2.5 px-3 text-muted-foreground text-xs">{sig.news_bias ?? "—"}</td>
              <td className="py-2.5 px-3 text-muted-foreground text-xs">{format(new Date(sig.created_at), "HH:mm dd/MM")}</td>
              <td className="py-2.5 px-3">
                {sig.status === "PENDING" && (
                  <div className="flex gap-1.5">
                    <Button size="sm" onClick={() => confirm.mutate(sig.id)} disabled={confirm.isPending}>Confirm</Button>
                    <Button size="sm" variant="destructive" onClick={() => reject.mutate(sig.id)} disabled={reject.isPending}>Reject</Button>
                  </div>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
