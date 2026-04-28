import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatPrice(price: number, pair: string): string {
  const decimals = pair.includes("JPY") ? 3 : 5;
  return price.toFixed(decimals);
}

export function formatPips(pips: number | null | undefined): string {
  if (pips == null) return "—";
  return `${pips > 0 ? "+" : ""}${pips.toFixed(1)}`;
}

export function formatConfidence(conf: number): string {
  return `${(conf * 100).toFixed(0)}%`;
}
