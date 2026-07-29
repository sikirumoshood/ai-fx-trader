"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Wifi, WifiOff, Brain, Database } from "lucide-react";

export function Header() {
  const { data: health } = useQuery({
    queryKey: ["health"],
    queryFn: api.health,
    refetchInterval: 30_000,
  });

  return (
    <header className="flex min-h-12 flex-wrap items-center justify-end gap-3 border-b border-border bg-card px-4 py-2 sm:min-h-14 sm:gap-4 sm:px-6">
      <StatusDot label="MT5" ok={health?.mt5_connected} icon={Wifi} />
      <StatusDot label="Model" ok={health?.model_loaded} icon={Brain} />
      <StatusDot label="DB"    ok={health?.db_connected}  icon={Database} />
    </header>
  );
}

function StatusDot({
  label, ok, icon: Icon,
}: { label: string; ok?: boolean; icon: React.ElementType }) {
  return (
    <div className="flex items-center gap-1.5 text-xs">
      <Icon className="h-3.5 w-3.5 text-muted-foreground" />
      <span className="text-muted-foreground">{label}</span>
      <span className={cn("w-2 h-2 rounded-full", ok ? "bg-buy" : "bg-sell")} />
    </div>
  );
}
