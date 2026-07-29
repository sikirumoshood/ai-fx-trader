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

const CRON_PRESETS = [
  { label: "Every hour",    value: "0 * * * *" },
  { label: "Every 4 hours", value: "0 */4 * * *" },
  { label: "Every 15 min",  value: "*/15 * * * *" },
  { label: "Daily 8am UTC", value: "0 8 * * *" },
  { label: "Custom",        value: "" },
];

export function CreateScheduleForm() {
  const [open, setOpen] = useState(false);
  const [cronPreset, setCronPreset] = useState("0 * * * *");
  const [customCron, setCustomCron] = useState("");
  const qc = useQueryClient();

  const [form, setForm] = useState({
    pair: "EURUSD", timeframe: "H1",
    min_pips: 15, stop_loss_pips: 20,
    risk_reward: 2.0, risk_percent: 1.0, notify: true,
  });
  const [sessions, setSessions] = useState<string[]>(["LONDON", "NEW_YORK"]);

  const { data: pairsData } = useQuery({ queryKey: ["pairs"], queryFn: api.pairs });

  const mutation = useMutation({
    mutationFn: api.schedules.create,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["schedules"] }); setOpen(false); },
  });

  const cron = cronPreset || customCron;
  const set  = (k: string, v: string | number | boolean) => setForm(f => ({ ...f, [k]: v }));

  return (
    <>
      <Button onClick={() => setOpen(true)} className="w-full sm:w-auto">New Schedule</Button>
      <Dialog open={open} onClose={() => setOpen(false)} title="Create Schedule">
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
          </div>

          <div className="space-y-1.5">
            <Label>Schedule</Label>
            <Select value={cronPreset} onChange={e => setCronPreset(e.target.value)}>
              {CRON_PRESETS.map(p => <option key={p.value} value={p.value}>{p.label}</option>)}
            </Select>
            {!cronPreset && (
              <Input placeholder="0 * * * *" value={customCron} onChange={e => setCustomCron(e.target.value)} className="mt-2" />
            )}
          </div>

          <div className="space-y-1.5">
            <Label>Sessions</Label>
            <SessionPicker value={sessions} onChange={setSessions} />
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

          {mutation.error && <p className="text-xs text-sell">{(mutation.error as Error).message}</p>}

          <div className="flex flex-col-reverse gap-2 pt-2 sm:flex-row sm:justify-end">
            <Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
            <Button onClick={() => mutation.mutate({ ...form, cron, sessions })} disabled={mutation.isPending || !cron}>
              {mutation.isPending ? "Creating..." : "Create"}
            </Button>
          </div>
        </div>
      </Dialog>
    </>
  );
}
