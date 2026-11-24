/* a page: its ``title`` (h1), ``aside`` beside it (muted: "· goals off 2"), a ``toolbar`` row under it (the
   filters: a search, chips, toggles) and what it shows. As pages.js page() draws one, so a moved page looks the same */
import { html } from "/static/app/core.js";

export function Page({ title, aside = null, toolbar = null, children }) {
  return html`<div class="page">
    <h1>${title}${aside != null && aside !== "" ? html`<span class="muted">${aside}</span>` : null}</h1>
    ${toolbar ? html`<div class="filters">${toolbar}</div>` : null}
    ${children}
  </div>`;
}
