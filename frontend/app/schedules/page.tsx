"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ScheduleTable } from "@/components/schedules/schedule-table";
import { CreateScheduleForm } from "@/components/schedules/create-schedule-form";

export default function SchedulesPage() {
  const { data: schedules = [], isLoading } = useQuery({
    queryKey: ["schedules"],
    queryFn: api.schedules.list,
    refetchInterval: 30_000,
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Schedules</h1>
        <CreateScheduleForm />
      </div>
      <Card>
        <CardHeader><CardTitle>All Schedules</CardTitle></CardHeader>
        <CardContent className="p-0 pb-2">
          {isLoading ? (
            <p className="text-sm text-muted-foreground text-center py-8">Loading...</p>
          ) : (
            <ScheduleTable schedules={schedules} />
          )}
        </CardContent>
      </Card>
    </div>
  );
}
