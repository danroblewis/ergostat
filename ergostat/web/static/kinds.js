/* a kind of item (SPEC §5a, *The kind's page*): its one bar, drawn the same on the Items page and on the kind's page
   (/items/K) apart from its heading's level and whether the list under it is open; and the kind's page's sections
   read from GET /api/kinds/K: where the model counts, moves and takes it, and its definition */
"use strict";

const kindHref = (name, q = "") => `/items/${encodeURIComponent(name)}${q ? `?${q}` : ""}`;

/* the bar: title (its name small), id pattern, description, finishes or lives on, the state chips with their counts,
   the total, and its system (why on hover). Keyed by the kind's name; its handlers come in through opts, called
   with the state or nothing, never closed over a build's rows */
function kindBar(k, { level = 3, open = true, state = null, onState = null, onOpen = null } = {}) {
  const total = Object.values(k.counts || {}).reduce((a, b) => a + b, 0);
  const fin = k.lives_on ? "lives on" : k.finished?.length ? `finishes: ${k.finished.join(", ")}` : null;
  const chip = (st) => h("a", { href: kindHref(k.name, st ? `state=${encodeURIComponent(st)}` : ""), class: `stbox${k.counts?.[st] ? " some" : ""}${st && state === st ? " on" : ""}`,
    onclick: (ev) => { ev.preventDefault(); onState?.(st); } }, h("span", { class: "n" }, String(k.counts?.[st] || 0)), st || "items");
  return h("div", { class: "kind-bar", key: k.name, "data-kind": k.name },
    h(`h${level}`, { class: "kind-title" },
      h("button", { class: "ghost disclose", "aria-expanded": String(!!open), "aria-label": open ? `Hide the ${k.name} items` : `Show the ${k.name} items`,
                    onclick: () => onOpen?.() }, h("span", { class: "tri", "aria-hidden": "true" }, open ? "▾" : "▸")),
      h("a", { href: kindHref(k.name), class: "kname" }, k.title || k.name, k.title ? h("span", { class: "mono" }, k.name) : null),
      h("span", { class: "muted small mono kind-id" }, k.id || ""),
      h("span", { class: "muted kind-total" }, ` ${total} item${total === 1 ? "" : "s"}`)),
    k.description ? h("p", { class: "kind-desc" }, k.description) : null,
    h("div", { class: "states" }, (k.states?.length ? k.states : [""]).map((st, i) => [i ? h("span", { class: "arrow", "aria-hidden": "true" }, "→") : null, chip(st)])),
    h("p", { class: "muted small kind-says" }, fin ? h("span", { title: finishSaid(k) || "" }, fin) : null, fin && k.system ? " · " : null,
      k.system ? h("span", { class: "kind-sys", title: k.system_why || "" }, `in ${k.system}`) : null));
}

const partHref = (part, view = "dynamics") => `/diagram?view=${view}&around=${encodeURIComponent(part.replace(".", "/"))}`;
const listOf = (xs, none = "none") => (xs && xs.length ? xs.join(", ") : none);
const termOf = (v) => (v == null ? "the block's" : typeof v === "object" ? JSON.stringify(v) : typeof v === "number" ? dur(v) : String(v));

/* In the model: a row a part that counts it, a flow that moves it, a block that takes it, a goal, a feedback loop; each
   name a link to the diagram drawn around it (a goal: its control loop and its evidence) */
function kindModel(fp, now) {
  if (!fp) return [h("p", { class: "muted" }, "The model has no such kind.")];
  const on = Object.entries(fp.definition.on || {});
  const link = (href, text) => h("a", { href }, text);
  const rows = [];
  for (const c of fp.counted_in) {
    if (c.kind === "flow") {
      const st = c.entering ?? c.leaving, evs = on.filter(([, s]) => s === st).map(([e]) => e);
      rows.push(["moved by", link(partHref(c.part), c.name), `${c.entering != null ? "entering" : "leaving"} ${st} (${listOf(evs, "no event")})`, ""]);
    } else {
      const sts = c.states.length ? c.states : fp.definition.states.map((s) => s.state);
      rows.push(["counted in", link(partHref(c.part), c.name), `${c.kind}, ${c.states.length ? listOf(c.states) : "every state"}${c.where ? " (only some)" : ""}`,
                 String(sts.reduce((a, s) => a + (now[s] || 0), 0))]);
    }
  }
  for (const t of fp.taken_by) {
    const waiting = t.at.reduce((a, s) => a + (now[s] || 0), 0);
    rows.push(["taken by", link(partHref(`block.${t.block}`, "blocks"), t.block),
      `${t.says}, to ${listOf(t.to)}; pool ${t.pool_now ? `${t.pool_now} now, at most ` : ""}${termOf(t.pool)}, ${t.attempts ?? "?"} attempts, TTL ${termOf(t.ttl)}`,
      `${t.taken} taken, ${waiting} waiting`]);
  }
  for (const g of fp.goals) rows.push(["goal", link(`/diagram?around=loop/${encodeURIComponent(g.goal)}`, g.goal), `holds ${g.of.replace(".", " ")} ${g.hold} (${g.why})`, statusEl(g.status)]);
  for (const lp of fp.loops) rows.push([`feedback loop ${lp.polarity}`, link(partHref(lp.through[0] || lp.parts[0]), lp.name),
    `${lp.polarity === "R" ? "reinforcing" : "balancing"}, through ${listOf(lp.through)}`, ""]);
  return [
    fp.why ? h("p", { class: "note kind-uncounted" }, `Nothing in the model counts it: ${fp.why}.`) : null,
    rows.length ? table(["", "part", "what", ["now", "num"]], rows.map(([a, b, c, d]) => h("tr", {}, h("td", { class: "muted nowrap" }, a),
      h("td", { class: "nowrap" }, b), h("td", {}, c), h("td", { class: "num nowrap" }, d))), "kind-model", "Where the model counts, moves and takes it") : null,
    fp.uncounted.length && !fp.why ? h("p", { class: "muted small" }, `States nothing counts: ${fp.uncounted.join(", ")}.`) : null,
    h("p", {}, link(`/diagram?view=process&kinds=${encodeURIComponent(fp.kind)}`, "its states as a process map"))].filter(Boolean);
}

/* its definition as declared, read-only: events to states, the fields shown and how each folds, its relations both
   ways, its joins, the lease rule */
function kindDefinition(fp) {
  if (!fp) return h("p", { class: "muted" }, "Not declared.");
  const d = fp.definition, pair = (k, v) => [h("dt", {}, k), h("dd", {}, v)];
  const marks = (s) => [s.first && "first", s.finished && "finished", s.paused && "paused", s.final && "final", s.ergostat && "ergostat's"].filter(Boolean);
  return h("dl", { class: "kind-def" },
    pair("states", listOf(d.states.map((s) => (marks(s).length ? `${s.state} (${marks(s).join(", ")})` : s.state)))),
    pair("finished", d.finished_by),
    pair("events", listOf(Object.entries(d.on).map(([e, s]) => `${e} → ${s}`))),
    pair("fields shown", listOf(d.show)),
    pair("folds", listOf(Object.entries(d.fold).map(([f, r]) => `${f}: ${typeof r === "object" ? JSON.stringify(r) : r}`), "each field its latest value")),
    pair("relations", listOf(Object.entries(d.relations).map(([r, x]) => `${r} → ${x.kinds.join(" or ")}${x.precedence ? " (precedence)" : ""}`))),
    pair("named by", listOf(d.named_by.map((x) => `${x.kind}.${x.relation}`))),
    pair("joins", listOf(d.join.map((j) => `${j.all ? "all" : "any"} of its ${j.children} in ${listOf([].concat(j.states))} → ${j.to}`))),
    pair("lease", `TTL ${termOf(d.lease.ttl)}, ${d.lease.attempts ?? "the block's"} attempts`));
}
