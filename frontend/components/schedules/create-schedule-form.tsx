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
  { label: "Every second",  value: "1s" },
  { label: "Every 5 sec",   value: "5s" },
  { label: "Every 30 sec",  value: "30s" },
  { label: "Every minute",  value: "* * * * *" },
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
    pair: "EURUSD", timeframe: "H1", indicator: "ifvg" as "ifvg",
    min_pips: 15, stop_loss_pips: 20,
    risk_reward: 2.0, risk_percent: 1.0, notify: true,
    ifvg_threshold: 0.0,
    auto_execute: false,
    auto_close_profit: false,
  });
  const [sessions, setSessions] = useState<string[]>(["LONDON", "NEW_YORK"]);
  const [emailNotify, setEmailNotify] = useState(false);
  const [notifyEmail, setNotifyEmail] = useState("");
  const [autoLotSize, setAutoLotSize] = useState("");
  const [maxRiskAmount, setMaxRiskAmount] = useState("");
  const [autoCloseProfitAmount, setAutoCloseProfitAmount] = useState("");

  const { data: pairsData } = useQuery({ queryKey: ["pairs"], queryFn: api.pairs });

  const mutation = useMutation({
    mutationFn: api.schedules.create,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["schedules"] }); setOpen(false); },
  });

  const cron = cronPreset || customCron;
  const set  = (k: string, v: string | number | boolean) => setForm(f => ({ ...f, [k]: v }));

  const tpPips = Math.round(form.stop_loss_pips * form.risk_reward * 10) / 10;

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
                {["M1","M5","M15","M30","H1","H4","D1","W1"].map(t => <option key={t}>{t}</option>)}
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

          {form.indicator === "ifvg" && (
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
          )}

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

          {form.stop_loss_pips > 0 && form.risk_reward > 0 && (
            <p className="text-xs text-muted-foreground">
              TP = <span className="font-medium text-foreground">{tpPips} pips</span> ({form.stop_loss_pips} SL × {form.risk_reward} R:R)
            </p>
          )}

          {/* Auto Execute */}
          <div className="rounded-md border border-border p-3 space-y-3">
            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                id="auto-execute"
                checked={form.auto_execute}
                onChange={e => set("auto_execute", e.target.checked)}
                className="h-4 w-4 rounded border-gray-600 bg-gray-800 accent-green-500"
              />
              <Label htmlFor="auto-execute">Auto Execute Trades</Label>
            </div>
            {form.auto_execute && (
              <div className="space-y-3 pl-6">
                <div className="space-y-1.5">
                  <Label>Max Risk Amount <span className="text-muted-foreground font-normal">(optional — max loss in account currency if SL is hit)</span></Label>
                  <Input
                    type="number"
                    step="1"
                    min="0.01"
                    placeholder="e.g. 50"
                    value={maxRiskAmount}
                    onChange={e => { setMaxRiskAmount(e.target.value); if (e.target.value) setAutoLotSize(""); }}
                  />
                </div>
                <div className="space-y-1.5">
                  <Label>Fixed Lot Size <span className="text-muted-foreground font-normal">(optional — overrides Max Risk Amount)</span></Label>
                  <Input
                    type="number"
                    step="0.01"
                    min="0.01"
                    placeholder={`Auto (${form.risk_percent}% risk)`}
                    value={autoLotSize}
                    onChange={e => { setAutoLotSize(e.target.value); if (e.target.value) setMaxRiskAmount(""); }}
                  />
                </div>
                <p className="text-xs text-muted-foreground">
                  Priority: Fixed Lot Size &gt; Max Risk Amount &gt; Risk %. When enabled, signals are placed on MT5 automatically — no manual confirmation needed.
                </p>
                <div className="border-t border-border/50 pt-3 space-y-3">
                  <div className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      id="auto-close-profit"
                      checked={form.auto_close_profit}
                      onChange={e => {
                        set("auto_close_profit", e.target.checked);
                        if (!e.target.checked) setAutoCloseProfitAmount("");
                      }}
                      className="h-4 w-4 rounded border-gray-600 bg-gray-800 accent-green-500"
                    />
                    <Label htmlFor="auto-close-profit">Auto Close at Profit</Label>
                  </div>
                  {form.auto_close_profit && (
                    <div className="space-y-3">
                      <div className="space-y-1.5">
                        <Label>Target Profit <span className="text-muted-foreground font-normal">(account currency)</span></Label>
                        <Input
                          type="number"
                          step="0.01"
                          min="0.01"
                          placeholder="e.g. 25"
                          value={autoCloseProfitAmount}
                          onChange={e => setAutoCloseProfitAmount(e.target.value)}
                        />
                      </div>
                      <div className="space-y-1.5">
                        <Label>Target Loss <span className="text-muted-foreground font-normal">(account currency — sets SL price)</span></Label>
                        <Input
                          type="number"
                          step="0.01"
                          min="0.01"
                          placeholder="e.g. 30"
                          value={maxRiskAmount}
                          onChange={e => { setMaxRiskAmount(e.target.value); if (e.target.value) setAutoLotSize(""); }}
                        />
                      </div>
                      <p className="text-xs text-muted-foreground">
                        TP and SL prices are computed from these amounts using your lot size. Overrides the R:R-based TP/SL.
                      </p>
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>

          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                id="email-notify"
                checked={emailNotify}
                onChange={e => setEmailNotify(e.target.checked)}
                className="h-4 w-4 rounded border-gray-600 bg-gray-800 accent-green-500"
              />
              <Label htmlFor="email-notify">Email notifications</Label>
            </div>
            {emailNotify && (
              <Input
                type="email"
                placeholder="trader@example.com"
                value={notifyEmail}
                onChange={e => setNotifyEmail(e.target.value)}
              />
            )}
          </div>

          {mutation.error && <p className="text-xs text-sell">{(mutation.error as Error).message}</p>}

          <div className="flex flex-col-reverse gap-2 pt-2 sm:flex-row sm:justify-end">
            <Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
            <Button
              onClick={() => mutation.mutate({
                ...form,
                cron,
                sessions,
                notify_email: emailNotify ? notifyEmail : undefined,
                auto_lot_size: form.auto_execute && autoLotSize ? +autoLotSize : undefined,
                max_risk_amount: form.auto_execute && maxRiskAmount ? +maxRiskAmount : undefined,
                auto_close_profit: form.auto_execute && form.auto_close_profit,
                auto_close_profit_amount: form.auto_execute && form.auto_close_profit && autoCloseProfitAmount ? +autoCloseProfitAmount : undefined,
              })}
              disabled={
                mutation.isPending ||
                !cron ||
                (emailNotify && !notifyEmail) ||
                (form.auto_execute && form.auto_close_profit && !autoCloseProfitAmount)
              }
            >
              {mutation.isPending ? "Creating..." : "Create"}
            </Button>
          </div>
        </div>
      </Dialog>
    </>
  );
}
