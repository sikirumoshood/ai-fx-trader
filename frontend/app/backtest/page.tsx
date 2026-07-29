"use client";

import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { BacktestForm } from "@/components/backtest/backtest-form";
import { BacktestResults } from "@/components/backtest/backtest-results";
import { BacktestList } from "@/components/backtest/backtest-list";

export default function BacktestPage() {
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const queryClient = useQueryClient();

  function handleJobCreated(jobId: string) {
    setSelectedJobId(jobId);
    queryClient.invalidateQueries({ queryKey: ["backtests"] });
  }

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold">Backtest</h1>

      <div className="grid gap-6 lg:grid-cols-[280px_minmax(0,1fr)] lg:items-start">
        {/* Left column: history list + form */}
        <div className="space-y-4">
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">History</CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              <div className="max-h-72 overflow-y-auto">
                <BacktestList
                  selectedJobId={selectedJobId}
                  onSelect={setSelectedJobId}
                />
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader><CardTitle>New Backtest</CardTitle></CardHeader>
            <CardContent>
              <BacktestForm onJobCreated={handleJobCreated} />
            </CardContent>
          </Card>
        </div>

        {/* Right column: results */}
        <Card className="min-h-[400px] min-w-0">
          <CardHeader><CardTitle>Results</CardTitle></CardHeader>
          <CardContent>
            {selectedJobId ? (
              <BacktestResults jobId={selectedJobId} />
            ) : (
              <p className="text-sm text-muted-foreground py-8 text-center">
                Select a backtest from the history or run a new one.
              </p>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
