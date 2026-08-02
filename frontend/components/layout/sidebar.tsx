"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import {
  LayoutDashboard, TrendingUp, Calendar, Briefcase,
  FlaskConical, BookOpen,
} from "lucide-react";

const links = [
  { href: "/",           label: "Dashboard",  icon: LayoutDashboard },
  { href: "/signals",    label: "Signals",    icon: TrendingUp },
  { href: "/schedules",  label: "Schedules",  icon: Calendar },
  { href: "/trades",     label: "Trades",     icon: Briefcase },
  { href: "/backtest",   label: "Backtest",   icon: FlaskConical },
  { href: "/journal",    label: "Journal",    icon: BookOpen },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="flex w-full flex-shrink-0 flex-col border-b border-border bg-card md:w-56 md:border-b-0 md:border-r">
      <div className="border-b border-border px-4 py-4 md:px-6 md:py-5">
        <span className="text-base font-bold tracking-tight text-primary md:text-lg">AI FX Trader</span>
      </div>
      <nav className="flex gap-1 overflow-x-auto px-3 py-2 md:flex-1 md:flex-col md:space-y-1 md:overflow-visible md:py-4">
        {links.map(({ href, label, icon: Icon }) => (
          <Link
            key={href}
            href={href}
            className={cn(
              "flex shrink-0 items-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-colors md:gap-3",
              pathname === href
                ? "bg-primary/10 text-primary"
                : "text-muted-foreground hover:text-foreground hover:bg-accent"
            )}
          >
            <Icon className="h-4 w-4" />
            {label}
          </Link>
        ))}
      </nav>
    </aside>
  );
}
