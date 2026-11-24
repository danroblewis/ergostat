/* a useApi answer shown: ``children(data)`` once there is data; ``loading`` words only before the first answer;
   "Still waiting for WHAT (N s)" while a call is slow, over the last data; "WHAT could not be read: why" with Retry on
   an error, the last data kept under it; ``empty`` (words, or { text, action } as a Note's) for an answer with nothing
   in it (an empty list or object). ``what`` names the answer in these messages ("the goals") */
import { html, useEffect, useState } from "/static/app/core.js";
import { Note } from "/static/app/components/note.js";

const isEmpty = (d) => (Array.isArray(d) ? d.length === 0 : typeof d === "object" && d !== null && Object.keys(d).length === 0);
const upper = (s) => s.charAt(0).toUpperCase() + s.slice(1);

export function Async({ of, what = "the answer", empty = null, loading = "Loading…", children }) {
  const [, tick] = useState(0);
  useEffect(() => {                                   // the seconds waited, said again each second while slow
    if (!of.slow) return undefined;
    const t = setInterval(() => tick((n) => n + 1), 1000);
    return () => clearInterval(t);
  }, [of.slow]);
  const slow = of.slow ? html`<p class="note async-slow" role="status">Still waiting for ${what} (${Math.round((performance.now() - of.slow) / 1000)} s)</p>` : null;
  const err = of.error ? html`<${Note} tone="bad" action=${{ label: "Retry", onClick: () => of.reload() }}>${upper(what)} could not be read: ${of.error.message}<//>` : null;
  if (of.data == null) return html`${err}${slow}${!err && !slow && of.loading ? html`<p class="muted">${loading}</p>` : null}`;
  const none = empty != null && isEmpty(of.data)
    ? html`<${Note} tone="muted" action=${empty.action}>${empty.text ?? empty}<//>` : null;
  return html`${err}${slow}${none || children(of.data)}`;
}
