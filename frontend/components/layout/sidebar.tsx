"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import {
  LayoutDashboard, TrendingUp, Calendar, Briefcase,
  FlaskConical, Activity,
} from "lucide-react";

const links = [
  { href: "/",           label: "Dashboard",  icon: LayoutDashboard },
  { href: "/signals",    label: "Signals",    icon: TrendingUp },
  { href: "/schedules",  label: "Schedules",  icon: Calendar },
  { href: "/trades",     label: "Trades",     icon: Briefcase },
  { href: "/backtest",   label: "Backtest",   icon: FlaskConical },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="w-56 flex-shrink-0 border-r border-border bg-card flex flex-col">
      <div className="px-6 py-5 border-b border-border">
        <span className="font-bold text-lg tracking-tight text-primary">AI FX Trader</span>
      </div>
      <nav className="flex-1 px-3 py-4 space-y-1">
        {links.map(({ href, label, icon: Icon }) => (
          <Link
            key={href}
            href={href}
            className={cn(
              "flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-colors",
              pathname === href
                ? "bg-primary/10 text-primary"
                : "text-muted-foreground hover:text-foreground hover:bg-accent"
            )}
          >
            <Icon className="w-4 h-4" />
            {label}
          </Link>
        ))}
      </nav>
    </aside>
  );
}
