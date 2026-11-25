import { createContext, useCallback, useContext, useMemo, type ReactNode } from "react";
import { useSearchParams } from "react-router-dom";

/* The window the page looks over (since=, "1h" unless the address says otherwise) and the moment it shows (at=,
   live when absent). Both live in the address, so a link pasted opens the same view. */
export const WINDOWS = { "10m": 600, "1h": 3600, "6h": 21600, "1d": 86400, "7d": 604800 } as const;
export type WindowKey = keyof typeof WINDOWS;
export const WINDOW_WORDS: Record<WindowKey, string> = {
  "10m": "Last 10 minutes", "1h": "Last hour", "6h": "Last 6 hours", "1d": "Last day", "7d": "Last 7 days",
};
export const isWindow = (k: string | null): k is WindowKey => k != null && Object.hasOwn(WINDOWS, k);

interface Time {
  since: WindowKey;
  seconds: number;
  /** The moment shown (epoch seconds), or null for live. */
  at: number | null;
  setSince: (k: WindowKey) => void;
  setAt: (t: number | null) => void;
}

const TimeContext = createContext<Time | null>(null);

export function TimeProvider({ children }: { children: ReactNode }) {
  const [q, setQ] = useSearchParams();
  const w = q.get("window");
  const since: WindowKey = isWindow(w) ? w : "1h";
  const atRaw = q.get("at");
  const at = atRaw && Number.isFinite(+atRaw) ? +atRaw : null;

  const setSince = useCallback(
    (k: WindowKey) => setQ((p) => { const n = new URLSearchParams(p); if (k === "1h") n.delete("window"); else n.set("window", k); return n; }, { replace: true }),
    [setQ],
  );
  const setAt = useCallback(
    (t: number | null) => setQ((p) => { const n = new URLSearchParams(p); if (t == null) n.delete("at"); else n.set("at", String(Math.round(t))); return n; }, { replace: true }),
    [setQ],
  );
  const value = useMemo(() => ({ since, seconds: WINDOWS[since], at, setSince, setAt }), [since, at, setSince, setAt]);
  return <TimeContext.Provider value={value}>{children}</TimeContext.Provider>;
}

export function useTime(): Time {
  const t = useContext(TimeContext);
  if (!t) throw new Error("useTime outside TimeProvider");
  return t;
}
