/* a line of words beside the data: ``tone`` "note" (the default: small, muted), "muted", "warn" or "bad"; ``action``
   one thing to do about it, { label, href } (a link) or { label, onClick } (a button) */
import { html } from "/static/app/core.js";

export function Note({ tone = "note", action = null, children }) {
  const act = !action ? null : action.href ? html` <a href=${appHref(action.href)}>${action.label}</a>`
    : html` <button type="button" class="ghost" onClick=${action.onClick}>${action.label}</button>`;
  return html`<p class=${tone === "muted" ? "muted" : "note"} data-tone=${["warn", "bad"].includes(tone) ? tone : undefined}>${children}${act}</p>`;
}
