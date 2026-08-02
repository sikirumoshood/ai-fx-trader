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
    pair: "EURUSD", timeframe: "H4", indicator: "ifvg" as "ifvg",
    start_date: "2025-01-01", end_date: "2025-12-31",
    min_pips: 15, stop_loss_pips: 20,
    risk_reward: 2.0, risk_percent: 1.0, initial_balance: 10000,
    ifvg_threshold: 0.0,
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
            {["M1","M5","M15","M30","H1","H4","D1","W1"].map(t => <option key={t}>{t}</option>)}
          </Select>
        </div>
      </div>


      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label>Start Date</Label>
          <Input type="date" value={form.start_date} onChange={e => set("start_date", e.target.value)} />
        </div>
        <div className="space-y-1.5">
          <Label>End Date</Label>
          <Input type="date" value={form.end_date} onChange={e => set("end_date", e.target.value)} />
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

      <div className="space-y-1.5">
          <Label>IFVG Min Gap Threshold</Label>
          <Input
            type="number"
            step="0.0001"
            min="0"
            max="0.1"
            value={form.ifvg_threshold}
            onChange={e => set("ifvg_threshold", +e.target.value)}
            placeholder="0.0"
          />
          <p className="text-xs text-muted-foreground">
            Minimum gap size as a <span className="font-medium">fraction of price</span> — <span className="font-medium text-yellow-400">not pips, not percent</span>. e.g. <span className="font-medium">0.001</span> ≈ 10 pips on EURUSD (0.1% of ~1.10). Entering <span className="font-medium">0.1</span> means a 1,100-pip gap — nothing will ever qualify. Leave at <span className="font-medium">0</span> to trade all FVGs.
          </p>
        </div>

      <Button
        onClick={() => mutation.mutate({ ...form, sessions })}
        disabled={mutation.isPending}
        className="w-full"
      >
        {mutation.isPending ? "Submitting..." : "Run Backtest"}
      </Button>
    </div>
  );
}
