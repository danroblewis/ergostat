import { useEffect, useRef } from "react";
import { useApi } from "../../hooks/useApi";
import type { Params } from "../../lib/api";

/** A panel's parameters as its endpoint takes them, as the server's own `query()` (spec/dashboards.py) writes them: a
 *  list comma-separated, true as 1, false and empty left out. */
export function endpointParams(params: Record<string, unknown>): Params {
  const out: Params = {};
  for (const [k, v] of Object.entries(params)) {
    if (v == null || v === "" || v === false) continue;
    out[k] = v === true ? "1" : Array.isArray(v) ? v.join(",") : String(v);
  }
  return out;
}

/** A panel's answer from its endpoint, asked again every `every` ms and when `refreshKey` changes. */
export function usePanelApi<T = any>(path: string | null, params: Record<string, unknown>, every?: number | null, refreshKey?: unknown) {
  const got = useApi<T>(path, endpointParams(params), { every: every === undefined ? 30000 : every });
  const asked = useRef(refreshKey);
  useEffect(() => {
    if (asked.current === refreshKey) return;
    asked.current = refreshKey;
    got.refresh();
  }, [refreshKey]); // eslint-disable-line react-hooks/exhaustive-deps
  return got;
}
