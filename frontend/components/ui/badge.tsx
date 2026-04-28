import { cn } from "@/lib/utils";

const variants = {
  default:     "bg-primary/10 text-primary border-primary/20",
  destructive: "bg-red-500/10 text-red-400 border-red-500/20",
  warning:     "bg-yellow-500/10 text-yellow-400 border-yellow-500/20",
  secondary:   "bg-secondary text-secondary-foreground border-border",
  outline:     "border-border text-foreground",
  buy:         "bg-buy/10 text-buy border-buy/20",
  sell:        "bg-sell/10 text-sell border-sell/20",
  skip:        "bg-skip/10 text-skip border-skip/20",
};

export function Badge({
  children,
  variant = "default",
  className,
}: {
  children: React.ReactNode;
  variant?: keyof typeof variants;
  className?: string;
}) {
  return (
    <span className={cn("inline-flex items-center border rounded-full px-2 py-0.5 text-xs font-medium", variants[variant], className)}>
      {children}
    </span>
  );
}
