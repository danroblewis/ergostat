/* the request timing overlay: off until Shift+T (or the address's ?timing=1), then each API call the page made (the
   call log util.js keeps: old pages' calls and useApi's), its path and milliseconds, slowest first. Shift+T closes it */
import { html, useEffect, useState } from "/static/app/core.js";

const typing = (el) => !!el && (el.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName));

export function Timing() {
  const [open, setOpen] = useState(() => new URLSearchParams(location.search).get("timing") === "1");
  const [, setCount] = useState(0);
  useEffect(() => {
    const key = (ev) => {
      if (ev.key !== "T" || !ev.shiftKey || ev.ctrlKey || ev.metaKey || ev.altKey || typing(ev.target)) return;
      setOpen((o) => !o);
    };
    document.addEventListener("keydown", key);
    return () => document.removeEventListener("keydown", key);
  }, []);
  useEffect(() => {                                  // drawn again as each call ends, while open
    if (!open) return undefined;
    const ended = () => setCount((n) => n + 1);
    window.addEventListener("ergostat:call", ended);
    return () => window.removeEventListener("ergostat:call", ended);
  }, [open]);
  if (!open) return null;
  const calls = [...(window.ERGOSTAT_CALLS || [])].sort((a, b) => b.ms - a.ms);
  return html`<div class="timing" role="region" aria-label="Request timing">
    <table>
      <thead><tr><th>path</th><th class="num">ms</th><th>status</th></tr></thead>
      <tbody>${calls.map((c) => html`<tr><td title=${c.url}>${c.path}</td><td class="num">${c.ms}</td><td>${c.status}</td></tr>`)}</tbody>
    </table>
  </div>`;
}
