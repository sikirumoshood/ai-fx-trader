"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { SignalTable } from "@/components/signals/signal-table";
import { AnalyzeForm } from "@/components/signals/analyze-form";

export default function SignalsPage() {
  const { data: signals = [], isLoading } = useQuery({
    queryKey: ["signals"],
    queryFn: api.signals.list,
    refetchInterval: 10_000,
  });

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <h1 className="text-xl font-semibold">Signals</h1>
        <AnalyzeForm />
      </div>
      <Card>
        <CardHeader><CardTitle>All Signals</CardTitle></CardHeader>
        <CardContent className="p-0 pb-2">
          {isLoading ? (
            <p className="text-sm text-muted-foreground text-center py-8">Loading...</p>
          ) : (
            <SignalTable signals={signals} />
          )}
        </CardContent>
      </Card>
    </div>
  );
}
