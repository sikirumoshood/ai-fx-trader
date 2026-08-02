"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { SessionPicker } from "@/components/ui/session-picker";
import { format } from "date-fns";
import type { Schedule } from "@/lib/types";

export function ScheduleTable({ schedules }: { schedules: Schedule[] }) {
  const [editing, setEditing] = useState<Schedule | null>(null);
  const [editSessions, setEditSessions] = useState<string[]>(["LONDON", "NEW_YORK"]);
  const [editProfitAmount, setEditProfitAmount] = useState("");
  const [editRiskAmount, setEditRiskAmount] = useState("");

  const qc = useQueryClient();
  const invalidate = () => qc.invalidateQueries({ queryKey: ["schedules"] });

  const pause  = useMutation({ mutationFn: api.schedules.pause,  onSuccess: invalidate });
  const resume = useMutation({ mutationFn: api.schedules.resume, onSuccess: invalidate });
  const del    = useMutation({ mutationFn: api.schedules.delete, onSuccess: invalidate });
  const update = useMutation({
    mutationFn: ({ id, body }: { id: string; body: Partial<Schedule> }) =>
      api.schedules.update(id, body),
    onSuccess: () => {
      invalidate();
      setEditing(null);
    },
  });

  const openEdit = (sch: Schedule) => {
    setEditing(sch);
    setEditSessions((sch.sessions && sch.sessions.length > 0) ? sch.sessions : ["LONDON", "NEW_YORK"]);
    setEditProfitAmount(sch.auto_close_profit_amount != null ? String(sch.auto_close_profit_amount) : "");
    setEditRiskAmount(sch.max_risk_amount != null ? String(sch.max_risk_amount) : "");
  };

  if (schedules.length === 0) {
    return <p className="text-sm text-muted-foreground py-8 text-center">No schedules yet.</p>;
  }

  return (
    <>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[900px] text-sm">
        <thead>
          <tr className="border-b border-border text-muted-foreground text-xs">
            <th className="text-left py-2 px-3">Pair</th>
            <th className="text-left py-2 px-3">Indicator</th>
            <th className="text-left py-2 px-3">Cron</th>
            <th className="text-left py-2 px-3">Status</th>
            <th className="text-right py-2 px-3">Min Pips</th>
            <th className="text-right py-2 px-3">SL Pips</th>
            <th className="text-right py-2 px-3">R:R</th>
            <th className="text-left py-2 px-3">Execution</th>
            <th className="text-left py-2 px-3">Sessions</th>
            <th className="text-left py-2 px-3">Next Run</th>
            <th className="py-2 px-3" />
          </tr>
        </thead>
        <tbody>
          {schedules.map(sch => (
            <tr key={sch.id} className="border-b border-border/50 hover:bg-accent/30">
              <td className="py-2.5 px-3 font-medium">{sch.pair}<span className="text-muted-foreground ml-1 text-xs">{sch.timeframe}</span></td>
              <td className="py-2.5 px-3">
                <Badge variant="warning">IFVG</Badge>
              </td>
              <td className="py-2.5 px-3 font-mono text-xs">{sch.cron}</td>
              <td className="py-2.5 px-3">
                <Badge variant={sch.status === "ACTIVE" ? "default" : sch.status === "PAUSED" ? "warning" : "secondary"}>
                  {sch.status}
                </Badge>
              </td>
              <td className="py-2.5 px-3 text-right">{sch.min_pips}</td>
              <td className="py-2.5 px-3 text-right">{sch.stop_loss_pips}</td>
              <td className="py-2.5 px-3 text-right">{sch.risk_reward}</td>
              <td className="py-2.5 px-3">
                {sch.auto_execute ? (
                  <div className="flex flex-col gap-1">
                    <Badge variant="default">
                      Auto{sch.auto_lot_size ? ` ${sch.auto_lot_size}L` : ""}
                    </Badge>
                    {sch.auto_close_profit && sch.auto_close_profit_amount && (
                      <span className="text-xs text-green-400">TP @ ${sch.auto_close_profit_amount}</span>
                    )}
                    {sch.max_risk_amount && (
                      <span className="text-xs text-red-400">SL @ ${sch.max_risk_amount}</span>
                    )}
                  </div>
                ) : (
                  <span className="text-xs text-muted-foreground">Signal only</span>
                )}
              </td>
              <td className="py-2.5 px-3 text-xs text-muted-foreground">
                {(sch.sessions && sch.sessions.length > 0) ? sch.sessions.join(", ") : "Default"}
              </td>
              <td className="py-2.5 px-3 text-muted-foreground text-xs">
                {sch.next_run ? format(new Date(sch.next_run), "HH:mm dd/MM") : "—"}
              </td>
              <td className="py-2.5 px-3">
                <div className="flex flex-wrap gap-1.5">
                  <Button size="sm" variant="outline" onClick={() => openEdit(sch)}>Edit</Button>
                  {sch.status === "ACTIVE"  && <Button size="sm" variant="outline" onClick={() => pause.mutate(sch.id)}>Pause</Button>}
                  {sch.status === "PAUSED"  && <Button size="sm" onClick={() => resume.mutate(sch.id)}>Resume</Button>}
                  {sch.status !== "CANCELED" && (
                    <Button size="sm" variant="destructive" onClick={() => del.mutate(sch.id)}>Delete</Button>
                  )}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
        </table>
      </div>

      <Dialog
        open={!!editing}
        onClose={() => setEditing(null)}
        title={editing ? `Edit — ${editing.pair} ${editing.timeframe}` : "Edit Schedule"}
      >
        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label>Sessions</Label>
            <SessionPicker value={editSessions} onChange={setEditSessions} />
          </div>

          {editing?.auto_execute && editing?.auto_close_profit && (
            <div className="rounded-md border border-border p-3 space-y-3">
              <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Auto Close Settings</p>
              <div className="space-y-1.5">
                <Label>Target Profit <span className="text-muted-foreground font-normal">(account currency)</span></Label>
                <Input
                  type="number"
                  step="0.01"
                  min="0.01"
                  placeholder="e.g. 20"
                  value={editProfitAmount}
                  onChange={e => setEditProfitAmount(e.target.value)}
                />
              </div>
              <div className="space-y-1.5">
                <Label>Max Risk Amount <span className="text-muted-foreground font-normal">(account currency)</span></Label>
                <Input
                  type="number"
                  step="0.01"
                  min="0.01"
                  placeholder="e.g. 30"
                  value={editRiskAmount}
                  onChange={e => setEditRiskAmount(e.target.value)}
                />
              </div>
            </div>
          )}

          {update.error && (
            <p className="text-xs text-sell">{(update.error as Error).message}</p>
          )}
          <div className="flex flex-col-reverse gap-2 pt-2 sm:flex-row sm:justify-end">
            <Button variant="outline" onClick={() => setEditing(null)}>Cancel</Button>
            <Button
              onClick={() => {
                if (!editing) return;
                update.mutate({
                  id: editing.id,
                  body: {
                    sessions: editSessions,
                    ...(editing.auto_execute && editing.auto_close_profit && {
                      auto_close_profit_amount: editProfitAmount ? +editProfitAmount : undefined,
                      max_risk_amount: editRiskAmount ? +editRiskAmount : undefined,
                    }),
                  },
                });
              }}
              disabled={update.isPending}
            >
              {update.isPending ? "Saving..." : "Save"}
            </Button>
          </div>
        </div>
      </Dialog>
    </>
  );
}
