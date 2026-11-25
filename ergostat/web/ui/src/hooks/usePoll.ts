import { useEffect, useRef } from "react";

/* A refresh: ``fn`` again ``ms`` after the last one finished (never two at once, however slow the server), not while
   the tab is hidden (at once when it is shown again), and never after the component is gone. ``fn`` gets an
   AbortSignal that fires when the component unmounts or ``deps`` change. */
export function usePoll(fn: (signal: AbortSignal) => unknown, ms: number | null, deps: unknown[] = []): void {
  const latest = useRef(fn);
  latest.current = fn;

  useEffect(() => {
    const ctl = new AbortController();
    let timer: ReturnType<typeof setTimeout> | null = null;
    let running = false;
    const speed = (window as any).ERGOSTAT_POLL_SPEED || 1;

    const run = async () => {
      if (timer) clearTimeout(timer);
      timer = null;
      if (ctl.signal.aborted || running) return;
      if (document.hidden && ms != null) return; // shown again: run at once (below)
      running = true;
      try {
        await latest.current(ctl.signal);
      } catch {
        /* the server may be restarting: the next one asks again */
      }
      running = false;
      if (!ctl.signal.aborted && ms != null) timer = setTimeout(run, ms / speed);
    };
    const shown = () => {
      if (!document.hidden && !timer && !running) run();
    };
    document.addEventListener("visibilitychange", shown);
    run();
    return () => {
      ctl.abort();
      if (timer) clearTimeout(timer);
      document.removeEventListener("visibilitychange", shown);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ms, ...deps]);
}
