import { Badge } from "@/components/ui/badge";
import type { SignalDirection, SignalStatus } from "@/lib/types";

export function DirectionBadge({ direction }: { direction: SignalDirection }) {
  if (direction === "BUY")  return <Badge variant="buy">BUY</Badge>;
  if (direction === "SELL") return <Badge variant="sell">SELL</Badge>;
  return <Badge variant="skip">SKIP</Badge>;
}

export function StatusBadge({ status }: { status: SignalStatus }) {
  const map: Record<SignalStatus, "default" | "destructive" | "warning" | "secondary"> = {
    PENDING:  "warning",
    EXECUTED: "default",
    REJECTED: "secondary",
    EXPIRED:  "secondary",
  };
  return <Badge variant={map[status]}>{status}</Badge>;
}
