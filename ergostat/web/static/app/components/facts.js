/* what a thing is, label by label: ``pairs`` [[label, value]], as a dl; a value that is null, undefined or "" is left
   out with its label (details.js dl's rule). The inline form (``inline``) is added by the first page that needs it */
import { html } from "/static/app/core.js";

export function Facts({ pairs }) {
  return html`<dl class="facts">${pairs.filter(([, v]) => v != null && v !== "").map(([k, v]) => html`<dt key=${`t${k}`}>${k}</dt><dd key=${`d${k}`}>${v}</dd>`)}</dl>`;
}
