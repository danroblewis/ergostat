/* a chip: a word with its count (``n``), coloured by ``tone`` ("bad", "warn", "quiet"), chosen (``on``); a link
   (``href``), a button (``onClick``, pressed when ``on``) or words alone, with an × to remove it (``onRemove``).
   StateChip is a chip for a state's word, its tone from one table */
import { html } from "/static/app/core.js";

export function Chip({ label, n = null, tone = undefined, on = false, href = null, onClick = null, onRemove = null, title = undefined }) {
  const body = html`${n != null ? html`<span class="chip-n">${n}</span> ` : null}${label}`;
  const inner = href ? html`<a href=${appHref(href)} title=${title}>${body}</a>`
    : onClick ? html`<button type="button" class="ghost" aria-pressed=${on ? "true" : "false"} title=${title} onClick=${onClick}>${body}</button>`
    : body;
  return html`<span class=${on ? "chip on" : "chip"} data-tone=${tone} title=${href || onClick ? undefined : title}>${inner}${onRemove
    ? html`<button type="button" class="chip-x ghost" aria-label=${`Remove ${label}`} title="Remove" onClick=${onRemove}>×</button>` : null}</span>`;
}

/* a goal's or an item's state as its word, coloured only when it needs someone (style.css "state"): off bad, open
   and stale warn, holding and unknown quiet; none "–" */
const TONES = { off: "bad", open: "warn", stale: "warn", holding: "quiet", unknown: "quiet" };
export function StateChip({ word, n = null, title = undefined, ...rest }) {
  return word ? html`<${Chip} label=${word} n=${n} tone=${TONES[word]} title=${title} ...${rest} />`
    : html`<span class="muted">–</span>`;
}
