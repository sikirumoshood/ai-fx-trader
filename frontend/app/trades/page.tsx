"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { DirectionBadge } from "@/components/signals/direction-badge";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { formatPrice, formatPips } from "@/lib/utils";
import { format } from "date-fns";

export default function TradesPage() {
  const [formOpen, setFormOpen] = useState(false);
  const [form, setForm] = useState({
    pair: "EURUSD",
    direction: "BUY" as "BUY" | "SELL",
    lot_size: 0.1,
    stop_loss: 0,
    take_profit: 0,
  });

  const qc = useQueryClient();
  const { data: trades = [], isLoading } = useQuery({
    queryKey: ["trades"],
    queryFn: api.trades.list,
    refetchInterval: 15_000,
  });
  const { data: pairsData } = useQuery({
    queryKey: ["pairs"],
    queryFn: api.pairs,
  });

  const createTrade = useMutation({
    mutationFn: api.trades.create,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["trades"] });
      setFormOpen(false);
    },
  });

  const open   = trades.filter(t => t.status === "OPEN");
  const closed = trades.filter(t => t.status === "CLOSED");
  const set = (k: string, v: string | number) => setForm(f => ({ ...f, [k]: v }));

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <h1 className="text-xl font-semibold">Trades</h1>
        <Button onClick={() => setFormOpen(true)} className="w-full sm:w-auto">Place Custom Trade</Button>
      </div>

      <Card>
        <CardHeader><CardTitle>Open Trades ({open.length})</CardTitle></CardHeader>
        <CardContent className="p-0 pb-2">
          {isLoading ? <p className="text-sm text-muted-foreground text-center py-8">Loading...</p> :
           open.length === 0 ? <p className="text-sm text-muted-foreground text-center py-8">No open trades.</p> :
          <div className="overflow-x-auto">
          <table className="w-full min-w-[680px] text-sm">
            <thead>
              <tr className="border-b border-border text-muted-foreground text-xs">
                <th className="text-left py-2 px-3">Pair</th>
                <th className="text-left py-2 px-3">Dir</th>
                <th className="text-right py-2 px-3">Entry</th>
                <th className="text-right py-2 px-3">SL</th>
                <th className="text-right py-2 px-3">TP</th>
                <th className="text-right py-2 px-3">Lots</th>
                <th className="text-left py-2 px-3">Opened</th>
              </tr>
            </thead>
            <tbody>
              {open.map(t => (
                <tr key={t.id} className="border-b border-border/50 hover:bg-accent/30">
                  <td className="py-2.5 px-3 font-medium">{t.pair}</td>
                  <td className="py-2.5 px-3"><DirectionBadge direction={t.direction} /></td>
                  <td className="py-2.5 px-3 text-right font-mono">{formatPrice(t.entry, t.pair)}</td>
                  <td className="py-2.5 px-3 text-right font-mono text-sell">{t.stop_loss ? formatPrice(t.stop_loss, t.pair) : "—"}</td>
                  <td className="py-2.5 px-3 text-right font-mono text-buy">{t.take_profit ? formatPrice(t.take_profit, t.pair) : "—"}</td>
                  <td className="py-2.5 px-3 text-right">{t.lot_size ?? "—"}</td>
                  <td className="py-2.5 px-3 text-muted-foreground text-xs">{format(new Date(t.opened_at), "HH:mm dd/MM")}</td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Closed Trades ({closed.length})</CardTitle></CardHeader>
        <CardContent className="p-0 pb-2">
          {closed.length === 0 ? <p className="text-sm text-muted-foreground text-center py-8">No closed trades.</p> :
          <div className="overflow-x-auto">
          <table className="w-full min-w-[620px] text-sm">
            <thead>
              <tr className="border-b border-border text-muted-foreground text-xs">
                <th className="text-left py-2 px-3">Pair</th>
                <th className="text-left py-2 px-3">Dir</th>
                <th className="text-right py-2 px-3">Entry</th>
                <th className="text-right py-2 px-3">Close</th>
                <th className="text-right py-2 px-3">Pips</th>
                <th className="text-left py-2 px-3">Closed</th>
              </tr>
            </thead>
            <tbody>
              {closed.map(t => (
                <tr key={t.id} className="border-b border-border/50 hover:bg-accent/30">
                  <td className="py-2.5 px-3 font-medium">{t.pair}</td>
                  <td className="py-2.5 px-3"><DirectionBadge direction={t.direction} /></td>
                  <td className="py-2.5 px-3 text-right font-mono">{formatPrice(t.entry, t.pair)}</td>
                  <td className="py-2.5 px-3 text-right font-mono">{t.close_price ? formatPrice(t.close_price, t.pair) : "—"}</td>
                  <td className={`py-2.5 px-3 text-right font-mono font-medium ${(t.profit_pips ?? 0) >= 0 ? "text-buy" : "text-sell"}`}>
                    {formatPips(t.profit_pips)}
                  </td>
                  <td className="py-2.5 px-3 text-muted-foreground text-xs">
                    {t.closed_at ? format(new Date(t.closed_at), "HH:mm dd/MM") : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>}
        </CardContent>
      </Card>

      <Dialog open={formOpen} onClose={() => setFormOpen(false)} title="Place Custom Trade">
        <div className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label>Pair</Label>
              <Select value={form.pair} onChange={e => set("pair", e.target.value)}>
                {(pairsData?.pairs ?? ["EURUSD"]).map(p => <option key={p}>{p}</option>)}
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>Direction</Label>
              <Select value={form.direction} onChange={e => set("direction", e.target.value as "BUY" | "SELL")}>
                <option value="BUY">BUY</option>
                <option value="SELL">SELL</option>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>Lot Size</Label>
              <Input type="number" step="0.01" min="0.01" value={form.lot_size} onChange={e => set("lot_size", +e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label>Stop Loss</Label>
              <Input type="number" step="0.00001" value={form.stop_loss} onChange={e => set("stop_loss", +e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label>Take Profit</Label>
              <Input type="number" step="0.00001" value={form.take_profit} onChange={e => set("take_profit", +e.target.value)} />
            </div>
          </div>

          {createTrade.error && (
            <p className="text-xs text-sell">{(createTrade.error as Error).message}</p>
          )}

          <div className="flex flex-col-reverse gap-2 pt-2 sm:flex-row sm:justify-end">
            <Button variant="outline" onClick={() => setFormOpen(false)}>Cancel</Button>
            <Button
              onClick={() => createTrade.mutate(form)}
              disabled={createTrade.isPending}
            >
              {createTrade.isPending ? "Placing..." : "Place Trade"}
            </Button>
          </div>
        </div>
      </Dialog>
    </div>
  );
}
