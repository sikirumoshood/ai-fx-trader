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
    <div className="flex flex-wrap gap-2">
      {ALL_SESSIONS.map((session) => {
        const active = value.includes(session);
        return (
          <button
            key={session}
            type="button"
            onClick={() => toggle(session)}
            className={`px-3 py-1.5 rounded text-xs font-medium border transition-colors ${
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
