"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { SignalTable } from "@/components/signals/signal-table";
import { AnalyzeForm } from "@/components/signals/analyze-form";
import { TrendingUp, Calendar, Briefcase, Activity } from "lucide-react";

export default function Dashboard() {
  const { data: signals = [] } = useQuery({ queryKey: ["signals"], queryFn: api.signals.list, refetchInterval: 15_000 });
  const { data: schedules = [] } = useQuery({ queryKey: ["schedules"], queryFn: api.schedules.list });
  const { data: trades = [] } = useQuery({ queryKey: ["trades"], queryFn: api.trades.list });

  const pending  = signals.filter(s => s.status === "PENDING").length;
  const executed = signals.filter(s => s.status === "EXECUTED").length;
  const active   = schedules.filter(s => s.status === "ACTIVE").length;
  const open     = trades.filter(t => t.status === "OPEN").length;

  const stats = [
    { label: "Pending Signals",    value: pending,  icon: TrendingUp, color: "text-skip" },
    { label: "Executed Signals",   value: executed, icon: Activity,   color: "text-buy" },
    { label: "Active Schedules",   value: active,   icon: Calendar,   color: "text-primary" },
    { label: "Open Trades",        value: open,     icon: Briefcase,  color: "text-foreground" },
  ];

  const recentSignals = signals.slice(0, 10);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Dashboard</h1>
        <AnalyzeForm />
      </div>

      <div className="grid grid-cols-4 gap-4">
        {stats.map(({ label, value, icon: Icon, color }) => (
          <Card key={label}>
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle className="text-muted-foreground">{label}</CardTitle>
                <Icon className={`w-4 h-4 ${color}`} />
              </div>
            </CardHeader>
            <CardContent>
              <p className={`text-3xl font-bold ${color}`}>{value}</p>
            </CardContent>
          </Card>
        ))}
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Recent Signals</CardTitle>
        </CardHeader>
        <CardContent className="p-0 pb-2">
          <SignalTable signals={recentSignals} />
        </CardContent>
      </Card>
    </div>
  );
}
