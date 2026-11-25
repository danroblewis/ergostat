import { useCallback, useRef, useState } from "react";
import { apiGet, isAbort, type Params } from "../lib/api";
import { useTime } from "../state/time";
import { usePoll } from "./usePoll";

export interface ApiState<T> {
  data: T | undefined;
  error: Error | null;
  loading: boolean;
  /** Ask again now. */
  refresh: () => void;
}

/* An API answer, asked with the page's window and moment (since=, at=), and again every ``every`` ms when given.
   An answer whose text is the same as the last keeps the same object, so nothing re-renders for a refresh that
   changed nothing. ``path`` null asks nothing (a dependent query not ready yet). */
export function useApi<T = any>(
  path: string | null,
  params: Params = {},
  opts: { every?: number | null; window?: boolean } = {},
): ApiState<T> {
  const { since, at } = useTime();
  const withWindow = opts.window !== false;
  const full: Params = withWindow ? { since, ...(at ? { at } : {}), ...params } : params;
  const key = path == null ? "" : `${path}?${JSON.stringify(full)}`;
  const [state, setState] = useState<{ key: string; data: T | undefined; error: Error | null; text: string }>({
    key: "", data: undefined, error: null, text: "",
  });
  const [tick, setTick] = useState(0);
  const lastText = useRef("");

  usePoll(
    async (signal) => {
      if (path == null) return;
      try {
        const data = await apiGet<T>(path, full, signal);
        const text = key + JSON.stringify(data);   // the same answer to the same question changes nothing
        if (text === lastText.current) return;
        lastText.current = text;
        setState({ key, data, error: null, text });
      } catch (e) {
        if (!isAbort(e)) setState((s) => ({ ...s, key, error: e as Error }));
      }
    },
    opts.every ?? null,
    [key, tick],
  );

  const refresh = useCallback(() => {
    lastText.current = "";
    setTick((t) => t + 1);
  }, []);
  const current = state.key === key;
  return {
    data: state.data, // the last answer stays shown while the next is asked
    error: current ? state.error : null,
    loading: !current,
    refresh,
  };
}
