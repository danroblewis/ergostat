/* the Items page's overview (SPEC §5a, The overview): under each system, one compact card per item kind, in a dense
   grid: its name (a link to its own page, /items/KIND), how many are unfinished and in all, its states over the window
   and its rate in and out. All of it from one answer (/api/items-overview); no item is listed here. A chart shows the
   kind's state groups (waiting, working, stopped, done) or, with the page's one switch, every state: kept in the
   address (?states=all), and drawn again from the answer held, with no request */
"use strict";

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
    const pm = h("a", { class: "pm-link", href: `/diagram?view=process&kind=${encodeURIComponent(k.name)}&mode=states`,   // where its work queues
                        title: "Its process map: how many are in each state now, and how they moved" }, "process map");
    return h("div", { class: "kind-flow kind-card", "data-kind": k.name }, name, pm, said, chart);
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
