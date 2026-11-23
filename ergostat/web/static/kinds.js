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
    h("p", {}, link(`/diagram?view=process&kinds=${encodeURIComponent(fp.kind)}`, "its states as a process map"))].filter(Boolean);
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

/* the Items page's overview (SPEC §5a, The overview): under each system, one compact card per item kind, in a dense
   grid: its name (a link to its own page, /items/KIND), how many are unfinished and in all, its states over the window
   and its rate in and out. All of it from one answer (/api/items-overview); no item is listed here. A chart shows the
   kind's state groups (waiting, working, stopped, done) or, with the page's one switch, every state: kept in the
   address (?states=all), and drawn again from the answer held, with no request */

const perHour = (x) => (x == null ? "–" : x >= 10 ? String(Math.round(x)) : x >= 1 ? x.toFixed(1) : x ? x.toFixed(2) : "0");

async function pageKinds(main, q) {
  const p = page(main, "Items");
  let all = q.get("states") === "all";
  const search = h("input", { type: "search", placeholder: "Search kinds, ids and fields", "aria-label": "Search" });
  search.addEventListener("change", () => { const w = search.value.trim(); if (w) navigate(`/items?q=${encodeURIComponent(w)}`); });
  const bar = h("span", { class: "rg-viewbar" });
  const box = h("div", { class: "kind-overview" }, h("p", { class: "muted page-loading" }, "Loading…"));
  const rbox = h("div", { class: "item-systems remote-systems" });   // each remote's own section, asked on its own
  p.append(h("div", { class: "filters" }, search, bar), box, rbox);
  const group = chartGroup("kinds");
  const ans = answers();
  let d = null, rbusy = false;

  const cardOf = (k) => {
    const href = `/items/${encodeURIComponent(k.name)}`;
    const name = h("a", { href, class: "kname" }, k.title || k.name, h("span", { class: "mono" }, k.title ? k.name : k.id));
    const said = k.why ? h("div", { class: "kind-counts muted small" }, k.why)
      : h("div", { class: "kind-counts small" }, h("b", {}, String(k.unfinished)), h("span", { class: "muted" }, ` unfinished of ${k.total}`),
          h("span", { class: "muted", title: `arrived in the window: ${k.arrived}; finished: ${k.left ?? "–"}` }, ` · in ${perHour(k.rate_in)}/h, out ${perHour(k.rate_out)}/h`));
    let chart = null;
    if (k.counts) {
      const states = all ? k.states : d.groups.filter((g) => g in k.by_group);
      chart = flowChart({ states, counts: all ? k.counts : k.by_group, now: all ? k.now : k.now_by_group, times: d.times, since: d.since, until: d.until },
        group, { kind: k, height: 64, xAxis: false, onState: (st) => navigate(all ? `${href}?state=${encodeURIComponent(st)}` : href) });
    }
    return h("div", { class: "kind-flow kind-card", "data-kind": k.name }, name, said, chart);
  };

  /* the switch and every card, from the answer held (``d``): never a request */
  function showStates() {
    const seg = (on, text, title, fn) => h("button", { class: on ? "on" : "", "aria-pressed": String(on), title, onclick: fn }, text);
    const pick = (to) => () => { if (all === to) return; all = to; replaceRoute(all ? "/items?states=all" : "/items"); showStates(); };
    bar.replaceChildren(h("span", { class: "seg", role: "group", "aria-label": "States" },
      seg(!all, "State groups", "Each kind's states as waiting, working, stopped and done", pick(false)),
      seg(all, "Every state", "Each kind's own states", pick(true))));
    const kindOf = Object.fromEntries(d.kinds.map((k) => [k.name, k]));
    const sections = d.systems.map((g) => {
      const ks = g.kinds.map((n) => kindOf[n]).filter((k) => k && !k.quiet);
      if (!ks.length) return null;
      const n = ks.reduce((a, k) => a + (k.total || 0), 0);
      return h("section", { class: "sys-group", "data-system": g.name },
        h("h2", { class: "sys-head" }, g.name, h("span", { class: "muted" }, ` ${n} item${n === 1 ? "" : "s"}, ${ks.length} kind${ks.length === 1 ? "" : "s"}`),
          g.description ? h("span", { class: "muted sys-desc" }, g.description) : null),
        h("div", { class: "kind-cards" }, ks.map(cardOf)));
    }).filter(Boolean);
    const quiet = d.kinds.filter((k) => k.quiet);
    box.replaceChildren(...sections,
      quiet.length ? h("p", { class: "muted kinds-quiet" }, "Nothing in the window: ",
        quiet.map((k, i) => [i ? ", " : "", h("a", { href: `/items/${encodeURIComponent(k.name)}` }, k.title || k.name)])) : "",
      d.unkinded ? h("p", { class: "note" }, `${d.unkinded} item${d.unkinded > 1 ? "s" : ""} match no kind of the model's.`) : "",
      d.kinds.length ? "" : h("p", { class: "muted" }, "No items yet. An item is what events with an id like ticket/12 are about; see the Guide."));
    sweepPlots();
  }
  /* end showStates */

  async function tick() {
    ans.begin();
    let got;
    try { got = await ans.api("items-overview"); }
    catch (err) { box.replaceChildren(h("p", { class: "note bad" }, String(err.message || err))); return; }
    if (!p.isConnected || (d && !ans.changed)) return;
    d = got;
    showStates();
    if (!rbusy && !SNAP && d.remotes.length) {          // (not waited on)
      rbusy = true;
      Promise.all(d.remotes.map(async (r) => remoteSection(r, await remoteApi("items", { remote: r.name, n: 25 }))))
        .then((secs) => { if (p.isConnected) rbox.replaceChildren(...secs); }).finally(() => { rbusy = false; });
    }
  }
  await tick();
  S.timer = poll(tick, 15000, p);
}
