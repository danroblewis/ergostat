/* a link to a thing ergostat shows: ``to`` "item", "kind", "agent", "goal" or "part", and its ``id``. An ordinary
   link (Tab reaches it, a modified or middle click opens a new tab); with ``panel`` (an opener: openAgent, openLoop…)
   a plain click opens its side panel instead. A ``remote`` item links to that remote's item, read there; an id that
   cannot be opened there is its text alone (pages.js remoteItemLink's rule) */
import { html } from "/static/app/core.js";

const enc = encodeURIComponent;
const HREF = {
  item: (id, remote) => `/item/${enc(id)}${remote ? `?remote=${enc(remote)}` : ""}`,
  kind: (id) => kindHref(id),
  agent: (id) => agentHref(id),
  goal: (id) => `/goals?select=${enc(id)}`,
  part: (id) => partHref(id),
};
const openable = (id) => typeof id === "string" && id.length <= 200 && REMOTE_ID.test(id) && !id.includes("..");

export function Ref({ to, id, remote = null, panel = null, title = undefined, children }) {
  if (!HREF[to]) throw new Error(`Ref: no link to a ${to}`);
  if (remote && !openable(id)) return html`<span title="its id cannot be opened here: on its own page only">${children ?? id}</span>`;
  const click = panel ? (ev) => { if (plainClick(ev)) { ev.preventDefault(); panel(id); } } : undefined;
  return html`<a href=${appHref(HREF[to](id, remote))} class=${to === "agent" ? "agent-link" : undefined} title=${title}
    onClick=${click}>${children ?? id}</a>`;
}
