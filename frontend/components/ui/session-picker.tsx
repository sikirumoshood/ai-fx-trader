"use client";

const ALL_SESSIONS = ["LONDON", "NEW_YORK", "TOKYO", "SYDNEY"] as const;

const SESSION_HOURS: Record<string, string> = {
  LONDON:   "07:00–16:00 UTC",
  NEW_YORK: "12:00–21:00 UTC",
  TOKYO:    "00:00–09:00 UTC",
  SYDNEY:   "21:00–06:00 UTC",
};

interface Props {
  value: string[];
  onChange: (sessions: string[]) => void;
}

export function SessionPicker({ value, onChange }: Props) {
  function toggle(session: string) {
    if (value.includes(session)) {
      onChange(value.filter((s) => s !== session));
    } else {
      onChange([...value, session]);
    }
  }

  return (
    <div className="grid gap-2 sm:flex sm:flex-wrap">
      {ALL_SESSIONS.map((session) => {
        const active = value.includes(session);
        return (
          <button
            key={session}
            type="button"
            onClick={() => toggle(session)}
            className={`rounded border px-3 py-1.5 text-left text-xs font-medium transition-colors sm:text-center ${
              active
                ? "bg-primary text-primary-foreground border-primary"
                : "bg-transparent text-muted-foreground border-border hover:border-primary/50"
            }`}
          >
            <span>{session}</span>
            <span className={`ml-1.5 ${active ? "opacity-70" : "opacity-40"}`}>
              {SESSION_HOURS[session]}
            </span>
          </button>
        );
      })}
    </div>
  );
}
