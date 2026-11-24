/* the kind's page's own sections (SPEC §5a, *The kind's page*), read from GET /api/kinds/K: where the model counts,
   moves and takes it, and its definition. Apart from kinds.js, which holds the one bar and the overview and draws no
   table */
"use strict";

const partHref = (part, view = "dynamics") => `/diagram?view=${view}&around=${encodeURIComponent(part.replace(".", "/"))}`;
const listOf = (xs, none = "none") => (xs && xs.length ? xs.join(", ") : none);
const termOf = (v) => (v == null ? "the block's" : typeof v === "object" ? JSON.stringify(v) : typeof v === "number" ? dur(v) : String(v));

/* /api/kinds/K not read: a 404 is a kind the model does not declare; anything else (the server, the network, a snapshot
   without it) an error, said as one, never as a fact about the model. ``fp.err``: the request's failure (pages.js) */
function kindUnread(fp) {
  if (fp && !fp.err) return null;
  return fp?.status === 404 ? h("p", { class: "muted" }, "The model declares no such kind.")
    : h("p", { class: "note bad kind-unread" }, `Could not read the kind from the model: ${fp?.err || "no answer"}.`);
}

/* a kind's flow (/api/items-flow) summed into its state groups (fp.group, the overview's: waiting, working, stopped,
   done), the overview's default chart */
function groupedFlow(fl, of, order) {
  const gs = order.filter((g) => fl.states.some((s) => of[s] === g));
  const sum = (f) => Object.fromEntries(gs.map((g) => [g, f(g)]));
  return { times: fl.times, since: fl.since, until: fl.until, states: gs,
           counts: sum((g) => fl.times.map((_, i) => fl.states.reduce((a, s) => a + (of[s] === g ? fl.counts[s][i] : 0), 0))),
           now: sum((g) => fl.states.reduce((a, s) => a + (of[s] === g ? fl.now?.[s] || 0 : 0), 0)) };
}

/* In the model: a row a part that counts it, a flow that moves it, a block that takes it, a goal, a feedback loop; each
   name a link to the diagram drawn around it (a goal: its control loop and its evidence) */
function kindModel(fp, now) {
  const err = kindUnread(fp);
  if (err) return [err];
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
  for (const g of fp.goals) rows.push(["goal", link(`/diagram?around=loop/${encodeURIComponent(g.goal)}`, g.goal), `holds ${g.of.replace(".", " ")} ${g.hold} (${g.why})`, statusEl(goalWord(g))]);
  for (const lp of fp.loops) rows.push([`feedback loop ${lp.polarity}`, link(partHref(lp.through[0] || lp.parts[0]), lp.name),
    `${lp.polarity === "R" ? "reinforcing" : "balancing"}, through ${listOf(lp.through)}`, ""]);
  return [
    fp.why ? h("p", { class: "note kind-uncounted" }, `Nothing in the model counts it: ${fp.why}.`) : null,
    rows.length ? table(["", "part", "what", ["now", "num"]], rows.map(([a, b, c, d]) => h("tr", {}, h("td", { class: "muted nowrap" }, a),
      h("td", { class: "nowrap" }, b), h("td", {}, c), h("td", { class: "num nowrap" }, d))), "kind-model", "Where the model counts, moves and takes it") : null,
    fp.uncounted.length && !fp.why ? h("p", { class: "muted small" }, `States nothing counts: ${fp.uncounted.join(", ")}.`) : null,
    h("p", { class: "kind-links" }, link(`/diagram?view=process&kinds=${encodeURIComponent(fp.kind)}`, "its states as a process map"),
      // what it touches, drawn alone (SPEC §5a, *Drawn alone*): only when something counts or takes it
      ...(fp.why ? [] : ["; ", link(`/diagram?view=dynamics&kind=${encodeURIComponent(fp.kind)}`, "draw what it touches")]))].filter(Boolean);
}

/* its definition as declared, read-only: events to states, the fields shown and how each folds, its relations both
   ways, its joins, the lease rule */
function kindDefinition(fp) {
  const err = kindUnread(fp);
  if (err) return err;
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
