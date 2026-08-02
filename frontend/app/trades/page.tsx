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
import type { Trade } from "@/lib/types";

type OrderType = "MARKET" | "LIMIT" | "STOP";

function OrderTypeBadge({ type }: { type: string }) {
  const color =
    type === "LIMIT" ? "text-blue-400" :
    type === "STOP"  ? "text-orange-400" :
    "text-muted-foreground";
  return <span className={`text-xs font-medium ${color}`}>{type}</span>;
}

function CancelButton({ trade }: { trade: Trade }) {
  const qc = useQueryClient();
  const cancel = useMutation({
    mutationFn: () => api.trades.close(trade.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["trades"] }),
  });
  return (
    <Button
      size="sm"
      variant="destructive"
      onClick={() => cancel.mutate()}
      disabled={cancel.isPending}
    >
      {cancel.isPending ? "Cancelling…" : "Cancel"}
    </Button>
  );
}

export default function TradesPage() {
  const [formOpen, setFormOpen] = useState(false);
  const [form, setForm] = useState({
    pair:        "EURUSD",
    direction:   "BUY"    as "BUY" | "SELL",
    order_type:  "MARKET" as OrderType,
    entry:       0,
    lot_size:    0.1,
    stop_loss:   0,
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

  const pending = trades.filter(t => t.status === "PENDING");
  const open    = trades.filter(t => t.status === "OPEN");
  const closed  = trades.filter(t => t.status === "CLOSED" || t.status === "CANCELED");

  const set = (k: string, v: string | number) => setForm(f => ({ ...f, [k]: v }));

  const isPending = form.order_type !== "MARKET";

  function handleSubmit() {
    const payload: Parameters<typeof api.trades.create>[0] = {
      pair:        form.pair,
      direction:   form.direction,
      order_type:  form.order_type,
      lot_size:    form.lot_size,
      stop_loss:   form.stop_loss,
      take_profit: form.take_profit,
      ...(isPending && { entry: form.entry }),
    };
    createTrade.mutate(payload);
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <h1 className="text-xl font-semibold">Trades</h1>
        <Button onClick={() => setFormOpen(true)} className="w-full sm:w-auto">Place Custom Trade</Button>
      </div>

      {/* Pending orders */}
      {pending.length > 0 && (
        <Card>
          <CardHeader><CardTitle>Pending Orders ({pending.length})</CardTitle></CardHeader>
          <CardContent className="p-0 pb-2">
            <div className="overflow-x-auto">
              <table className="w-full min-w-[720px] text-sm">
                <thead>
                  <tr className="border-b border-border text-muted-foreground text-xs">
                    <th className="text-left py-2 px-3">Pair</th>
                    <th className="text-left py-2 px-3">Dir</th>
                    <th className="text-left py-2 px-3">Type</th>
                    <th className="text-right py-2 px-3">Entry</th>
                    <th className="text-right py-2 px-3">SL</th>
                    <th className="text-right py-2 px-3">TP</th>
                    <th className="text-right py-2 px-3">Lots</th>
                    <th className="text-left py-2 px-3">Placed</th>
                    <th className="py-2 px-3" />
                  </tr>
                </thead>
                <tbody>
                  {pending.map(t => (
                    <tr key={t.id} className="border-b border-border/50 hover:bg-accent/30">
                      <td className="py-2.5 px-3 font-medium">{t.pair}</td>
                      <td className="py-2.5 px-3"><DirectionBadge direction={t.direction} /></td>
                      <td className="py-2.5 px-3"><OrderTypeBadge type={t.order_type} /></td>
                      <td className="py-2.5 px-3 text-right font-mono">{formatPrice(t.entry, t.pair)}</td>
                      <td className="py-2.5 px-3 text-right font-mono text-sell">{t.stop_loss ? formatPrice(t.stop_loss, t.pair) : "—"}</td>
                      <td className="py-2.5 px-3 text-right font-mono text-buy">{t.take_profit ? formatPrice(t.take_profit, t.pair) : "—"}</td>
                      <td className="py-2.5 px-3 text-right">{t.lot_size ?? "—"}</td>
                      <td className="py-2.5 px-3 text-muted-foreground text-xs">{format(new Date(t.opened_at), "HH:mm dd/MM")}</td>
                      <td className="py-2.5 px-3"><CancelButton trade={t} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Open positions */}
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

      {/* Closed / cancelled */}
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
                <th className="text-left py-2 px-3">Status</th>
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
                    {t.status === "CANCELED" ? "—" : formatPips(t.profit_pips)}
                  </td>
                  <td className="py-2.5 px-3 text-xs text-muted-foreground">{t.status}</td>
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

      {/* Place trade dialog */}
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
            <div className="space-y-1.5 sm:col-span-2">
              <Label>Order Type</Label>
              <Select value={form.order_type} onChange={e => set("order_type", e.target.value as OrderType)}>
                <option value="MARKET">Market — execute at current price</option>
                <option value="LIMIT">Limit — buy below / sell above market</option>
                <option value="STOP">Stop — buy above / sell below market</option>
              </Select>
            </div>

            {isPending && (
              <div className="space-y-1.5 sm:col-span-2">
                <Label>Entry Price</Label>
                <Input
                  type="number"
                  step="0.00001"
                  min="0"
                  value={form.entry || ""}
                  placeholder="e.g. 1.08500"
                  onChange={e => set("entry", +e.target.value)}
                />
              </div>
            )}

            <div className="space-y-1.5">
              <Label>Lot Size</Label>
              <Input type="number" step="0.01" min="0.01" value={form.lot_size} onChange={e => set("lot_size", +e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label>Stop Loss</Label>
              <Input type="number" step="0.00001" value={form.stop_loss || ""} placeholder="e.g. 1.08200" onChange={e => set("stop_loss", +e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label>Take Profit</Label>
              <Input type="number" step="0.00001" value={form.take_profit || ""} placeholder="e.g. 1.09200" onChange={e => set("take_profit", +e.target.value)} />
            </div>
          </div>

          {createTrade.error && (
            <p className="text-xs text-sell">{(createTrade.error as Error).message}</p>
          )}

          <div className="flex flex-col-reverse gap-2 pt-2 sm:flex-row sm:justify-end">
            <Button variant="outline" onClick={() => setFormOpen(false)}>Cancel</Button>
            <Button onClick={handleSubmit} disabled={createTrade.isPending}>
              {createTrade.isPending
                ? "Placing…"
                : isPending
                ? `Place ${form.order_type} Order`
                : "Place Trade"}
            </Button>
          </div>
        </div>
      </Dialog>
    </div>
  );
}
