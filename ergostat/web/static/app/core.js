/* the shared core of the new pages: the vendored Preact and htm (one ES module, no build step), the store of what
   every page shares (the window, the moment, the project, the route), and useApi, through which every API call of a
   new page goes, its latency recorded for the timing overlay (docs/frontend.md).

   Old and new run side by side: the old scripts (util.js, main.js, pages.js...) are ordinary scripts on the same
   page, so their globals (S, timed) are read here by name. The call log both write is util.js's (timed, into
   window.ERGOSTAT_CALLS), so the old pages' calls are timed too. */
import { useEffect, useRef, useState } from "/static/vendor/preact/htm-preact-standalone.module.js";

export * from "/static/vendor/preact/htm-preact-standalone.module.js";

/* a small store: one object, set by a patch, its listeners told when a value changed */
export function createStore(initial) {
  let state = { ...initial };
  const listeners = new Set();
  return {
    get: () => state,
    set(patch) {
      if (!Object.keys(patch).some((k) => !Object.is(state[k], patch[k]))) return;
      state = { ...state, ...patch };
      for (const f of [...listeners]) f(state);
    },
    subscribe(f) { listeners.add(f); return () => listeners.delete(f); },
  };
}

/* what every page shares: the window ("1h"...), the moment shown (null: live), the project's name, its status (the
   header's answer) and the page's route (its top path, "/agents"). The old code is its writer for now: sync() is
   called by util.js (route, refreshHeader) */
export const store = createStore({ window: "1h", at: null, project: "", status: null, route: "" });
export function sync(route) {
  store.set({ window: S.since, at: S.at || null, status: S.status, project: S.status?.name || "",
              ...(route != null ? { route } : {}) });
}

/* a component's view of the store: what ``pick`` reads from it, drawn again when that changes */
export function useStore(pick = (s) => s) {
  const [v, setV] = useState(() => pick(store.get()));
  const pickRef = useRef(pick);
  pickRef.current = pick;
  useEffect(() => store.subscribe((s) => setV(() => pickRef.current(s))), []);
  return v;
}

/* the address of an API answer: the store's window and moment, then the params (a list: its key repeated) */
export function apiUrl(path, params = {}, { window: w, at } = store.get()) {
  const q = new URLSearchParams({ since: w, ...(at ? { at: String(at) } : {}) });
  for (const [k, v] of Object.entries(params)) {
    q.delete(k);
    if (v != null) for (const x of [].concat(v)) q.append(k, x);
  }
  return `/api/${path}?${q}`;
}

/* one GET, timed into the call log (util.js timed): its text, or an error with its status */
async function getText(path, url, signal) {
  const { r, text } = await timed(path, url, { signal });
  if (!r.ok) throw Object.assign(new Error(`${path}: ${r.status}`), { status: r.status });
  return text;
}
export const apiGet = (path, params = {}, signal = undefined) => getText(path, apiUrl(path, params), signal);

/* an API answer for a component: { data, error, loading, ms, reload }. Asked again when the path, the params, the
   window or the moment change; the call in flight aborted when the component leaves (or asks again). ``every``: asked
   again that many ms after each answer (at least 500; shortened by ERGOSTAT_POLL_SPEED, as poll() is), never while
   the tab is hidden. An answer the same as the last changes nothing (``ms`` stays the last changed answer's), so
   nothing is drawn again for it. */
export function useApi(path, params = {}, { every = 0 } = {}) {
  const w = useStore((s) => s.window), at = useStore((s) => s.at);
  const [got, setGot] = useState({ data: null, error: null, loading: true, ms: null });
  const [asked, setAsked] = useState(0);
  const key = path == null ? null : apiUrl(path, params, { window: w, at });
  useEffect(() => {
    if (key == null) return undefined;
    const c = new AbortController();
    let timer = null, last = null, first = true, gone = false;
    const shown = () => { if (!document.hidden) run(); else document.addEventListener("visibilitychange", shown, { once: true }); };
    async function run() {
      timer = null;
      if (gone) return;
      if (document.hidden && !first) { document.addEventListener("visibilitychange", shown, { once: true }); return; }
      first = false;
      const t0 = performance.now();
      try {
        const text = await getText(path, key, c.signal);
        if (gone) return;
        const ms = Math.round(performance.now() - t0);
        if (text !== last) { last = text; setGot({ data: JSON.parse(text), error: null, loading: false, ms }); }
        else setGot((g) => (g.error ? { ...g, ms, error: null } : g));   // (the same answer: nothing drawn again)
      } catch (e) {
        if (gone || e?.name === "AbortError") return;
        setGot((g) => ({ ...g, error: e, loading: false }));
      }
      if (every > 0 && !gone) timer = setTimeout(run, Math.max(every, 500) / (window.ERGOSTAT_POLL_SPEED || 1));   // (never faster than 2 a second)
    }
    setGot((g) => (g.loading ? g : { ...g, loading: true }));
    run();
    return () => { gone = true; clearTimeout(timer); document.removeEventListener("visibilitychange", shown); c.abort(); };
  }, [key, every, asked]);
  return { ...got, reload: () => setAsked((n) => n + 1) };
}
