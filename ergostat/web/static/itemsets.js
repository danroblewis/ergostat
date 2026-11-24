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
   link away (``counts``, ``items.set``); and for each block that takes items and moves it, how many it has taken now
   and how many wait for it (``leases``), then those it has taken, a live list (takenList) */
function countsLines(d) {
  const c = d?.counts, set = d?.items?.set;
  const named = (s, k) => (k ? s.split(k).flatMap((x, i) => (i ? [h("code", {}, k), x] : [x])) : [s]);
  return [c ? h("p", { class: "counts-line" }, ...named(c.says, c.kind),
                c.kind && set ? [". ", h("a", { href: itemsHref(set), class: "counts-link" }, "Show them on the Items page")] : null) : null,
          ...(d?.leases || []).flatMap((l) => {
            const n = h("span", { class: "taken-n" }, String(l.taken));
            return [h("p", { class: "leases-line" }, `${l.block}${l.agent ? ` (${l.agent})` : ""} works items of kind `, h("code", {}, l.kind), ": ", n,
              " leased now; ", l.waiting ? `${l.waiting} waiting at ${l.at.join(" or ")}` : "none waiting", ". ",
              h("a", { href: itemsHref(l.set), class: "leased-link" }, "Show the leased items")), takenList(l, n)];
          })]
    .filter(Boolean);
}

/* the items a block has taken now, under its line: up to ten, each with its state, its run and its lease (pages.js
   leaseTail). Read again every 4 s while the panel shows it (a lease taken or ended comes or goes without a reload);
   compared by what it would draw, so the clocks (taken for, expires in or overdue) move on each read, and an answer
   that draws the same as the last leaves the page alone */
function takenList(l, count) {
  const box = h("div", { class: "taken-list" });
  const none = () => h("p", { class: "muted small" }, `${l.block} is working nothing now`);
  if (!l.taken) box.append(none());
  let sig = null;
  const draw = (d) => {
    const rows = d.items.map((i) => {
      const x = i.fields?.lease || {};
      return h("tr", { key: i.id }, h("td", { class: "nowrap" }, h("a", { href: `/item/${encodeURIComponent(i.id)}` }, i.id)),
        h("td", { class: "cell" }, itemTitle(i)), h("td", { class: "muted nowrap" }, i.state || ""),
        h("td", { class: "mono small" }, h("a", { href: `/record?item=${encodeURIComponent(i.id)}`, title: `run ${x.holder}: its item's events in the Record` },
          String(x.holder || "").slice(0, 8))),
        h("td", { class: "num nowrap" }, x.taken ? dur(nowS() - x.taken) : ""), ...leaseTail(x, true));
    });
    const s = JSON.stringify([d.total, rows.map((r) => r.outerHTML)]);
    if (s === sig) return;
    sig = s;
    count.textContent = String(d.total);
    if (!d.total) return patch(box, none());
    patch(box, h("p", { class: "taken-head" }, h("b", {}, `being worked by ${l.block} (${d.total})`)),
      h("div", { class: "table-wrap" }, h("table", { class: "item-list taken" },
        h("tr", {}, ["item", "", "state", "run", "taken for", "expires in", ""].map((t) => h("th", {}, t))), rows)),
      d.total > rows.length ? h("p", { class: "small" }, h("a", { href: itemsHref(l.set), class: "all-taken" }, `all ${d.total} taken`)) : null);
  };
  const read = () => api("items", { ...l.set, alone: 1, n: ITEMS_SHOWN, shown: 1 }).then(draw);
  read().catch(() => {});
  poll(read, 4000, box);
  return box;
}

/* a kind's progress per group (``/api/items-groups``, spec/grouptally.py), on its card: a compact row a group (a
   gap's milestone), its bar done, in progress, waiting, stopped of its total, its state and what it waits on; the
   active ones, and the members in no group, shown; the rest folded behind one button (``more``). A row's click opens
   exactly its members (its set: ``where=REL:ID``) in the list, the Graph or the Timeline, whichever is shown */
const GP_STACKS = ["done", "in progress", "waiting", "stopped"];
function groupRows(g, { more = false, onMore, onPick, chosen = [] } = {}) {
  if (!g) return null;
  if (g.err) return h("p", { class: "note gp-err", key: "gp-err" }, `Progress per group not read: ${g.err.message || g.err}`);
  const short = (a) => String(a).split("/").pop();
  const shown = (r) => r.id == null || ["active", "queued"].includes(r.status);
  const row = (r) => {
    const c = r.counts, apart = [r.left ? `${r.left} closed as no work done, left out` : "", r.summaries ? `${r.summaries} split, counted as their parts` : ""].filter(Boolean);
    const name = r.id == null ? `no ${g.by.replace(/_/g, " ")}` : r.title ? `${short(r.id)} · ${r.title}` : short(r.id);
    const st = r.id == null ? "" : !r.item ? "no such item" : r.state + (r.waits_on.length ? ` · waits on ${r.waits_on.map(short).join(", ")}` : "");
    const says = `${GP_STACKS.map((s) => `${c[s]} ${s}`).join(", ")}, of ${r.total}`;
    const on = chosen.length && r.params.where.length === chosen.length && r.params.where.every((w) => chosen.includes(w));
    return h("a", { href: itemsHref(r.params), class: `gp-row${on ? " on" : ""}`, key: `gp:${r.id ?? ""}`, "data-group": r.id ?? "",
                    title: [r.id ?? name, st, says, ...apart].filter(Boolean).join("\n"), "aria-label": `${name}: ${says}${st ? `; ${st}` : ""}`,
                    onclick: (ev) => { ev.preventDefault(); onPick(r); } },
      h("span", { class: "gp-name" }, name),
      h("span", { class: "gp-bar", "aria-hidden": "true" }, ...GP_STACKS.map((s) => h("span", { class: `gp-${s.replace(" ", "-")}`, style: `flex-grow: ${c[s]}` }))),
      h("span", { class: "gp-n" }, `${c.done}/${r.total}`), h("span", { class: "gp-state" }, st));
  };
  const first = g.rows.filter(shown), rest = g.rows.filter((r) => !shown(r));
  const n = {};
  for (const r of rest) n[r.state || "no such item"] = (n[r.state || "no such item"] || 0) + 1;
  return h("div", { class: "gp-rows", key: `gp:${g.kind}:${g.by}`, role: "group", "aria-label": `${g.kind} by ${g.by}` },
    ...(more ? [...first.filter((r) => r.id != null), ...rest, ...first.filter((r) => r.id == null)] : first).map(row),
    rest.length ? h("button", { class: "ghost gp-more", key: "gp-more", "aria-expanded": String(more), onclick: onMore },
      more ? "Fold the rest" : `${rest.length} more (${Object.entries(n).map(([w, k]) => `${k} ${w}`).join(", ")})`) : null,
    g.odd_n ? h("p", { class: "note", key: "gp-odd" }, `${g.odd_n} whose ${g.by} is not one id, in no row: ${g.odd.join(", ")}`) : null);
}
