"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Dialog } from "@/components/ui/dialog";
import { SessionPicker } from "@/components/ui/session-picker";

const TIMEFRAMES = ["M1","M5","M15","M30","H1","H4","D1","W1"];

export function AnalyzeForm({ onDone }: { onDone?: () => void }) {
  const [open, setOpen] = useState(false);
  const qc = useQueryClient();

  const [form, setForm] = useState({
    pair: "EURUSD",
    timeframe: "H1",
    min_pips: 15,
    stop_loss_pips: 20,
    risk_reward: 2.0,
    risk_percent: 1.0,
  });

  const [sessions, setSessions] = useState<string[]>(["LONDON", "NEW_YORK"]);
  const { data: pairsData } = useQuery({ queryKey: ["pairs"], queryFn: api.pairs });

  const mutation = useMutation({
    mutationFn: api.signals.analyze,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["signals"] });
      setOpen(false);
      onDone?.();
    },
  });

  const set = (k: string, v: string | number) => setForm(f => ({ ...f, [k]: v }));

  return (
    <>
      <Button onClick={() => setOpen(true)} className="w-full sm:w-auto">Analyze Pair</Button>

      <Dialog open={open} onClose={() => setOpen(false)} title="Analyze Pair">
        <div className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="pair">Pair</Label>
              <Select id="pair" value={form.pair} onChange={e => set("pair", e.target.value)}>
                {(pairsData?.pairs ?? ["EURUSD"]).map(p => (
                  <option key={p} value={p}>{p}</option>
                ))}
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="tf">Timeframe</Label>
              <Select id="tf" value={form.timeframe} onChange={e => set("timeframe", e.target.value)}>
                {TIMEFRAMES.map(t => <option key={t}>{t}</option>)}
              </Select>
            </div>
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label>Min Pips</Label>
              <Input type="number" value={form.min_pips} onChange={e => set("min_pips", +e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label>SL Pips</Label>
              <Input type="number" value={form.stop_loss_pips} onChange={e => set("stop_loss_pips", +e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label>Risk:Reward</Label>
              <Input type="number" step="0.5" value={form.risk_reward} onChange={e => set("risk_reward", +e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label>Risk %</Label>
              <Input type="number" step="0.1" value={form.risk_percent} onChange={e => set("risk_percent", +e.target.value)} />
            </div>
          </div>

          <div className="space-y-1.5">
            <Label>Sessions</Label>
            <SessionPicker value={sessions} onChange={setSessions} />
          </div>

          {mutation.error && (
            <p className="text-xs text-sell">{(mutation.error as Error).message}</p>
          )}

          <div className="flex flex-col-reverse gap-2 pt-2 sm:flex-row sm:justify-end">
            <Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
            <Button onClick={() => mutation.mutate({ ...form, sessions })} disabled={mutation.isPending}>
              {mutation.isPending ? "Analyzing..." : "Run Analysis"}
            </Button>
          </div>
        </div>
      </Dialog>
    </>
  );
}
