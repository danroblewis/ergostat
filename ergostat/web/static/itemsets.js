/* what is going through the wires: in a stock's or a flow's side panel, its items (item_sets.py), a few listed and
   the rest one link away on the Items page, filtered to exactly that set. Filled in when the list comes */
"use strict";

const ITEMS_SHOWN = 10;
/* the Items page's address for a set: its params, as the server said them (a key may repeat: where); a whole kind is
   that kind's page */
function itemsHref(params) {
  const u = new URLSearchParams();
  for (const [k, vs] of Object.entries(params || {})) for (const v of [].concat(vs)) u.append(k, v);
  return [...u.keys()].join() === "kind" ? kindHref(u.get("kind")) : `/items?${u}`;
}
/* an item as a line in a list: its title, or its kind's columns */
function itemTitle(i) {
  const f = i.fields || {};
  if (f.title != null && f.title !== "") return String(f.title);
  return Object.entries(f).filter(([k, v]) => k !== "lease" && v != null && typeof v !== "object").map(([, v]) => String(v)).join(" · ");
}
function inWindowWords() { return S.at ? "in the window" : `in the last ${S.since}`; }
const timeOf = (t) => new Date(t * 1000).toLocaleTimeString([], { hour12: false });

/* the section: an element now, its list when it comes. ``info`` is the part's answer's items (server.py, _items_of) */
function itemsSection(info) {
  if (!info) return null;
  const isFlow = info.of?.kind === "flow";
  const box = h("section", { class: "item-set" }, h("h3", {}, isFlow ? "Items through it" : "Items in it"));
  if (info.none) { box.append(h("p", { class: "muted" }, `No items: ${info.none}.`)); return box; }
  if (info.events) { box.append(...eventItems(info.events)); return box; }
  const status = h("p", { class: "muted" }, "Reading its items…");
  box.append(status);
  const flat = {};
  for (const [k, vs] of Object.entries(info.set)) flat[k] = vs;
  api("items", { ...flat, alone: 1, n: ITEMS_SHOWN, shown: 1 }).then((d) => {
    const all = h("a", { href: itemsHref(info.set), class: "all-items" }, `all ${d.total} on the Items page`);
    const head = isFlow
      ? `${d.moves ?? d.total} went through ${inWindowWords()}` + (d.moves != null && d.moves !== d.total ? ` (${d.total} items)` : "")
      : `${d.total} item${d.total === 1 ? "" : "s"} now`;
    const rows = d.items.map((i) => {
      const lease = i.fields?.lease && typeof i.fields.lease === "object" && i.fields.lease.holder ? i.fields.lease : null;
      const last = (i.moved_at || []).slice(-1)[0];
      return h("tr", {},
        h("td", { class: "nowrap" }, h("a", { href: `/item/${encodeURIComponent(i.id)}` }, i.id)),
        h("td", { class: "cell" }, itemTitle(i)),
        isFlow ? h("td", { class: "num nowrap", title: (i.moved_at || []).map(timeOf).join(", ") },
                   last ? timeOf(last) + ((i.moved_at || []).length > 1 ? ` (${i.moved_at.length}×)` : "") : "")
               : h("td", { class: "num nowrap", title: "in its state for" }, i.state ? dur(nowS() - i.entered) : ""),
        h("td", { class: "muted nowrap" }, lease ? `leased by ${lease.block}` : isFlow ? "" : i.state || ""));
    });
    status.replaceWith(h("p", {}, h("b", {}, head), d.total ? h("span", { class: "muted" }, ": ", info.says) : null),
      ...(rows.length ? [h("div", { class: "table-wrap" }, h("table", { class: "item-list" }, tableCaption(head),
        headRow(h("th", {}, "item"), h("th", {}, ""), h("th", { class: "num" }, isFlow ? "when" : "in state"), h("th", {}, "")), rows))] : []),
      h("p", { class: "small" }, d.total > rows.length ? all : rows.length ? h("a", { href: itemsHref(info.set) }, "on the Items page") : null),
      h("p", { class: "muted small" }, info.how));
  }).catch((err) => status.replaceChildren(`Its items could not be read: ${err.message || err}`));
  return box;
}

/* a flow measured by events: its valve's openings (each with the items its run was about), or what its sensor saw */
function eventItems(ev) {
  const out = [h("p", {}, h("b", {}, `${ev.total} ${ev.valve ? "opening" : "observation"}${ev.total === 1 ? "" : "s"} ${inWindowWords()}`)),
               h("p", { class: "muted small" }, ev.how)];
  if (ev.rows?.length) out.push(h("div", { class: "table-wrap" }, h("table", { class: "item-list" }, tableCaption(ev.valve ? "Openings" : "Observations"),
    headRow(h("th", {}, "when"), h("th", {}, ev.valve ? "moved" : "event"), h("th", {}, "items")),
    ev.rows.slice(0, ITEMS_SHOWN).map((r) => h("tr", {}, h("td", { class: "nowrap" }, timeOf(r.time)),
      h("td", { class: ev.valve ? "num" : "muted" }, ev.valve ? fmt(r.amount) : r.type),
      h("td", {}, r.items.length ? r.items.flatMap((id, j) => [j ? ", " : "", h("a", { href: `/item/${encodeURIComponent(id)}` }, id)])
                                 : h("span", { class: "muted" }, "none named")))))));
  const rec = ev.valve ? `/record?type=valve.opened&item=${encodeURIComponent(ev.valve)}&window=1` : `/record?machine=${encodeURIComponent(ev.source)}&window=1`;
  out.push(h("p", { class: "small" }, h("a", { href: rec }, ev.total > ITEMS_SHOWN ? `all ${ev.total} in the Record` : "in the Record")));
  return out;
}

/* the same from a part's reference (stock.NAME, flow.NAME, auxiliary.NAME), as the Blocks view knows it: a place
   in the panel now, its section when the part's answer comes, nothing for a part of another kind */
function partItemsSection(ref) {
  const [k, ...rest] = String(ref || "").split(".");
  if (!["stock", "flow", "auxiliary"].includes(k) || !rest.length) return null;
  const box = h("div", { class: "item-set" });
  api(`part/${k === "auxiliary" ? "stock" : k}/${encodeURIComponent(rest.join("."))}`)
    .then((d) => { const s = itemsSection(d?.items); if (s) box.replaceWith(s); else box.remove(); })
    .catch(() => box.remove());
  return box;
}

/* the first lines of a stock's, flow's or valve's panel: what its sensor counts, its kind named, those very items one
   link away (``counts``, ``items.set``); and the items leased to the blocks that move it, a live list (``leases``) */
function countsLines(d) {
  const c = d?.counts, set = d?.items?.set;
  const named = (s, k) => (k ? s.split(k).flatMap((x, i) => (i ? [h("code", {}, k), x] : [x])) : [s]);
  return [c ? h("p", { class: "counts-line" }, ...named(c.says, c.kind),
                c.kind && set ? [". ", h("a", { href: itemsHref(set), class: "counts-link" }, "Show them on the Items page")] : null) : null,
          ...(d?.leases || []).map((l) => h("p", { class: "leases-line" }, `${l.block}${l.agent ? ` (${l.agent})` : ""} works items of kind `,
            h("code", {}, l.kind), `: ${l.held} leased now. `, h("a", { href: itemsHref(l.set), class: "leased-link" }, "Show the leased items")))]
    .filter(Boolean);
}
