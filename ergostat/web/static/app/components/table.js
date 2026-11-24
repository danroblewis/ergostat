/* a data table: ``columns`` [{ key, head, num, title, cls, cell(row) }] (a cell is row[key] unless ``cell`` says),
   ``rows`` keyed by ``rowKey`` (a field's name or a function), its ``caption`` said to screen readers only. ``groups``
   [{ key, head, rows }] in place of rows: a tbody each under its heading; ``total`` { key: content } a last row. A
   clickable row: ``rowHref(row)`` (a page: a plain click goes there, a modified or middle click opens a new tab, as
   util.js rowLink) or ``onRow(row)``; a click on a link or a button in it is its own. ``empty``: said in place of a
   table with no rows. ``hold``: while the pointer or the focus is in it, the rows stay as they are and "N updates
   waiting" is said over it; they are drawn once the reader has left (util.js holdStill's rule) */
import { html, useEffect, useRef, useState } from "/static/app/core.js";

const allRows = (v) => (v.groups ? v.groups.flatMap((g) => g.rows) : v.rows);
function changed(a, b, key) {                         // rows added, gone or different between two views
  const m = (v) => new Map(allRows(v).map((r) => [String(key(r)), JSON.stringify(r)]));
  const x = m(a), y = m(b);
  return [...new Set([...x.keys(), ...y.keys()])].filter((k) => x.get(k) !== y.get(k)).length;
}
const cellClass = (c) => [c.num ? "num" : "", c.cls || ""].filter(Boolean).join(" ") || undefined;

export function Table({ columns, rows = [], rowKey = "name", caption, cls = undefined, groups = null, total = null,
                        rowHref = null, onRow = null, empty = null, hold = false }) {
  const key = typeof rowKey === "function" ? rowKey : (r) => r[rowKey];
  const wrap = useRef(null), shown = useRef(null), [, release] = useState(0);
  const now = { rows, groups, total };
  const held = hold && !!shown.current && heldStill(wrap.current);
  if (!held) shown.current = now;
  const v = shown.current, waiting = held ? changed(v, now, key) : 0;
  useEffect(() => {
    if (!held) return undefined;
    const el = wrap.current, leave = () => setTimeout(() => { if (!heldStill(el)) release((n) => n + 1); });
    el.addEventListener("pointerleave", leave);
    el.addEventListener("focusout", leave);
    return () => { el.removeEventListener("pointerleave", leave); el.removeEventListener("focusout", leave); };
  }, [held]);
  if (empty != null && allRows(v).length === 0) return html`<p class="muted">${empty}</p>`;

  const row = (r) => {
    const k = String(key(r)), href = rowHref?.(r);
    const on = href ? rowLink(href) : onRow ? { onclick: (ev) => { if (!ev.target.closest?.("a, button, input, select")) onRow(r); } } : {};
    return html`<tr key=${k} data-row=${k} class=${href || onRow ? "click" : undefined} onClick=${on.onclick} onAuxClick=${on.onauxclick}>
      ${columns.map((c) => html`<td key=${c.key} class=${cellClass(c)}>${c.cell ? c.cell(r) : r[c.key]}</td>`)}</tr>`;
  };
  return html`<div class="table" ref=${wrap}>
    <div class="waiting" role="status">${waiting ? `${waiting} update${waiting === 1 ? "" : "s"} waiting` : ""}</div>
    <div class="table-wrap"><table class=${cls}><caption class="sr-only">${caption}</caption>
      <thead><tr>${columns.map((c) => html`<th key=${c.key} scope="col" class=${c.num ? "num" : undefined} title=${c.title}>${c.head ?? c.key}</th>`)}</tr></thead>
      ${v.groups ? v.groups.map((g) => html`<tbody class="group" key=${g.key}>
          <tr><th colspan=${columns.length} scope="colgroup">${g.head}</th></tr>${g.rows.map(row)}</tbody>`)
        : html`<tbody>${v.rows.map(row)}</tbody>`}
      ${v.total ? html`<tbody class="total"><tr data-total="">${columns.map((c) => html`<td key=${c.key} class=${cellClass(c)}>${v.total[c.key]}</td>`)}</tr></tbody>` : null}
    </table></div>
  </div>`;
}
