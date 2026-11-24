/* a part of a page under its heading: ``title``, at ``level`` (2: h2), with ``aside`` beside it (a count, muted words)
   and ``actions`` at its end (buttons, a menu). Folding (``fold``) is added by the first page that folds one */
import { h, html } from "/static/app/core.js";

export function Section({ title, level = 2, aside = null, actions = null, id = undefined, children }) {
  return html`<section class="sec" id=${id}>
    ${h(`h${level}`, { class: "sec-head" }, title, aside != null && aside !== "" ? html` <span class="muted sec-aside">${aside}</span>` : null,
        actions ? html`<span class="sec-actions">${actions}</span>` : null)}
    ${children}
  </section>`;
}
