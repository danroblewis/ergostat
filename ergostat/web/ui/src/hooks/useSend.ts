import { useEffect, useRef, useState } from "react";
import { apiSend, isAbort } from "../lib/api";

/* An answer to a POST whose body follows what the page holds (a draft tried, a query asked as it is typed): asked
   `delay` ms after the body last changed, the one in flight cancelled when it changes again. A null body asks nothing
   and forgets the answer. The answer kept is the last one that came back, so the page does not blank while it asks. */
export function useSend<T = any>(path: string, body: Record<string, unknown> | null, delay = 400) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const ctl = useRef<AbortController | null>(null);
  const key = body == null ? "" : JSON.stringify(body);
  useEffect(() => {
    ctl.current?.abort();
    if (!key) { setData(null); setError(null); setBusy(false); return; }
    const t = setTimeout(() => {
      const c = new AbortController();
      ctl.current = c;
      setBusy(true);
      apiSend<T>(path, JSON.parse(key), {}, c.signal)
        .then((r) => { setData(r); setError(null); })
        .catch((e) => { if (!isAbort(e)) setError(String((e as Error).message || e)); })
        .finally(() => { if (ctl.current === c) setBusy(false); });
    }, delay);
    return () => clearTimeout(t);
  }, [path, key, delay]);
  useEffect(() => () => ctl.current?.abort(), []);
  return { data, error, busy };
}
