/* the bridge between old and new: an element made the old way (``node``: an old panel's, a chart's) shown in a
   component, or ``make(el)`` drawing into the component's own box (a drawing engine, an old page function) and giving
   back its cleanup. Done again when ``deps`` change (by default ``node`` and ``make``: pass ``deps`` when ``make`` is
   written inline, else it is made again at each drawing); cleaned up, its box emptied, when the component leaves */
import { h, useEffect, useRef } from "/static/app/core.js";

export function Dom({ node = null, make = null, deps = null, tag = "div", ...rest }) {
  const box = useRef(null);
  useEffect(() => {
    const el = box.current;
    if (node) { el.replaceChildren(node); return () => node.remove(); }
    const done = make?.(el);
    return () => { if (typeof done === "function") done(); el.replaceChildren(); };
  }, deps || [node, make]);
  return h(tag, { ref: box, ...rest });
}
