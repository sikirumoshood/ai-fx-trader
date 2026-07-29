"use client";

import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { SessionPicker } from "@/components/ui/session-picker";

interface Props { onJobCreated: (jobId: string) => void; }

export function BacktestForm({ onJobCreated }: Props) {
  const { data: pairsData } = useQuery({ queryKey: ["pairs"], queryFn: api.pairs });

  const [form, setForm] = useState({
    pair: "EURUSD", timeframe: "H4",
    start_date: "2025-01-01", end_date: "2025-12-31",
    min_pips: 15, stop_loss_pips: 20,
    risk_reward: 2.0, risk_percent: 1.0, initial_balance: 10000,
  });
  const [sessions, setSessions] = useState<string[]>(["LONDON", "NEW_YORK"]);

  const mutation = useMutation({
    mutationFn: api.backtest.submit,
    onSuccess: (data) => {
      toast.success("Backtest queued successfully");
      onJobCreated(data.job_id);
    },
    onError: (err: Error) => {
      toast.error("Failed to submit backtest", { description: err.message });
    },
  });

  const set = (k: string, v: string | number) => setForm(f => ({ ...f, [k]: v }));

  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label>Pair</Label>
          <Select value={form.pair} onChange={e => set("pair", e.target.value)}>
            {(pairsData?.pairs ?? ["EURUSD"]).map(p => <option key={p}>{p}</option>)}
          </Select>
        </div>
        <div className="space-y-1.5">
          <Label>Timeframe</Label>
          <Select value={form.timeframe} onChange={e => set("timeframe", e.target.value)}>
            {["M15","H1","H4","D1"].map(t => <option key={t}>{t}</option>)}
          </Select>
        </div>
        <div className="space-y-1.5">
          <Label>Start Date</Label>
          <Input type="date" value={form.start_date} onChange={e => set("start_date", e.target.value)} />
        </div>
        <div className="space-y-1.5">
          <Label>End Date</Label>
          <Input type="date" value={form.end_date} onChange={e => set("end_date", e.target.value)} />
        </div>
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
          <Label>Initial Balance ($)</Label>
          <Input type="number" value={form.initial_balance} onChange={e => set("initial_balance", +e.target.value)} />
        </div>
      </div>

      <div className="space-y-1.5">
        <Label>Sessions</Label>
        <SessionPicker value={sessions} onChange={setSessions} />
      </div>

      <Button onClick={() => mutation.mutate({ ...form, sessions })} disabled={mutation.isPending} className="w-full">
        {mutation.isPending ? "Submitting..." : "Run Backtest"}
      </Button>
    </div>
  );
}
