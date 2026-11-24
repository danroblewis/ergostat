/* the shared hooks besides core.js's (useApi, usePoll, useStore): the window, one query key, and keys
   (docs/frontend.md, "Components"). The old code still owns the window and the address: these call its functions
   (setWindow, setQuery, route), so old and new pages say the same. */
import { useCallback, useEffect, useRef, useState, useStore } from "/static/app/core.js";

/* the window and the moment shown, from the store, and their setters (the header menu's own, main.js) */
export function useWindow() {
  const since = useStore((s) => s.window), at = useStore((s) => s.at);
  const setAt = useCallback((t) => { S.at = t || null; showAt(); refreshHeader(); route(); }, []);
  return { since, at, live: !at, words: WINDOW_WORDS[since] || since, setSince: setWindow, setAt };
}

/* one key of the address's query, as state: read when the page is drawn (back and forward draw it again: route()),
   written in place (setQuery: the history entry changed, nothing redrawn but the component). ``parse`` reads the
   text; ``write`` gives it, null to drop the key (by default: the default, empty or false dropped, true as "1") */
const dropped = (initial) => (v) => (v == null || v === "" || v === false || v === initial ? null : v === true ? "1" : String(v));
export function useQueryState(key, initial = "", { parse = (v) => v, write = dropped(initial) } = {}) {
  const [v, setV] = useState(() => { const x = parseRoute().q.get(key); return x == null ? initial : parse(x); });
  const set = useCallback((x) => { setQuery({ [key]: write(x) }); setV(x); }, [key]);
  return [v, set];
}

/* keys for a component while it is drawn (and ``when``): { "Escape": fn, "mod+Enter": fn } (mod: Ctrl or Cmd). One
   listener for all: the component first drawn last wins (a part's before its page's, a panel opened after the page
   before the page's), alone among them, its default prevented. A plain key typed into a field is the field's; Escape
   and mod+ keys are not. Other listeners (main.js's Escape closing the panel, util.js's closing menus, the timing
   overlay's Shift+T) still hear every key */
const typing = (el) => !!el && (el.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName));
const STACK = [];                                     // in the order first drawn: a page before its parts, a panel after
let drawn = 0;
document.addEventListener("keydown", (ev) => {
  const name = (ev.ctrlKey || ev.metaKey ? "mod+" : "") + ev.key;
  if (!name.startsWith("mod+") && name !== "Escape" && typing(ev.target)) return;
  for (let i = STACK.length - 1; i >= 0; i--) {
    const fn = STACK[i].when && STACK[i].map[name];
    if (fn) { ev.preventDefault(); fn(ev); return; }
  }
});
export function useKeys(map, { when = true } = {}) {
  const own = useRef(null);
  own.current ||= { at: ++drawn };                    // (drawn order: a parent draws before its children)
  Object.assign(own.current, { map, when });
  useEffect(() => {
    const k = own.current;
    STACK.push(k);
    STACK.sort((a, b) => a.at - b.at);
    return () => STACK.splice(STACK.indexOf(k), 1);
  }, []);
}
