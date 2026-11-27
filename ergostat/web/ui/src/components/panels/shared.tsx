import { createContext, useContext, type ReactNode } from "react";
import type { ApiState } from "../../hooks/useApi";
import { endpointParams, usePanelApi } from "./usePanelApi";

/* Answers a page has asked for already, handed to its panels: a page made of panels that each read the same answer
   (an item's sections, a projection's) asks once, at its own pace, instead of once a panel. A panel not on such a page, or
   asking something the page did not, asks its own endpoint as always. */

type Entry = { path: string; params?: Record<string, unknown>; state: ApiState<any> };
const Answers = createContext<Record<string, ApiState<any>>>({});

const keyOf = (path: string, params: Record<string, unknown>) =>
  `${path}?${JSON.stringify(Object.entries(endpointParams(params)).sort(([a], [b]) => (a < b ? -1 : 1)))}`;

/** The page's answers, each by its path and the parameters it was asked with; each also stands for its path alone,
 *  for a panel that reads any answer of that path (`loose`). */
export function SharedAnswers({ answers, children }: { answers: Entry[]; children: ReactNode }) {
  const by: Record<string, ApiState<any>> = {};
  for (const a of answers) {
    by[keyOf(a.path, a.params || {})] = a.state;
    by[`${a.path}?*`] ??= a.state;
  }
  return <Answers.Provider value={by}>{children}</Answers.Provider>;
}

/** A panel's answer: the page's when it has asked the same (or, `loose`, anything of that path), else its own. */
export function usePanelAnswer<T = any>(path: string | null, params: Record<string, unknown>, every?: number | null,
  refreshKey?: unknown, loose = false): ApiState<T> {
  const by = useContext(Answers);
  const hit = path == null ? undefined : by[keyOf(path, params)] ?? (loose ? by[`${path}?*`] : undefined);
  const own = usePanelApi<T>(hit ? null : path, params, every, refreshKey);
  return hit ?? own;
}
