import { createContext, useContext, type ReactNode } from "react";
import { useApi } from "../hooks/useApi";

/* The project's status (/api/status), asked every 5 s for the whole app: its name, whether it runs, the goals off,
   what waits for the owner, rate units, how much is recorded. Every page reads it from here, never asks again. */
export type Status = Record<string, any> & {
  name: string;
  running?: boolean;
  first?: number;
  window?: number;
  recorded?: number;
  goals_off?: { system: number; own?: Record<string, number> };
  attention?: any[];
  loops?: Record<string, any>;
  rate_units?: Record<string, string>;
  edited?: { banner: string; errors: string[] } | null;
};

const StatusContext = createContext<{ status: Status | undefined; refresh: () => void }>({
  status: undefined,
  refresh: () => {},
});

export function StatusProvider({ children }: { children: ReactNode }) {
  const { data, refresh } = useApi<Status>("status", {}, { every: 5000 });
  return <StatusContext.Provider value={{ status: data, refresh }}>{children}</StatusContext.Provider>;
}

export const useStatus = () => useContext(StatusContext);

/** An entry that waits on a person: the header's "N for you". */
export const waitsOnYou = (a: any): boolean =>
  a.level !== "hint" && ((Array.isArray(a.answer) && a.kind !== "request") || !!a.waiting);

/** The goals off as the server counted them; "?" when not known, never read as none. */
export function goalsOff(st?: Status): { off: number | "?"; upkeep: number } {
  const g = st?.goals_off;
  return g ? { off: g.system, upkeep: Object.values(g.own || {}).reduce((a, b) => a + b, 0) } : { off: "?", upkeep: 0 };
}

/** A sensor whose newest read failed (/api/status's sensors_failing): what it measures (`stock.NAME`), and why. */
export type SensorFailing = { sensor: string; part: string; why: string; at: number; last_read: number | null; in_a_row: number };

/** The failing sensors of a diagram part, by its node id (`stock:NAME`, `flow:NAME`) or its part (`stock.NAME`). */
export const failingOf = (st: Status | undefined, id: string): SensorFailing[] =>
  ((st?.sensors_failing || []) as SensorFailing[]).filter((x) => x.part === id.replace(":", "."));
