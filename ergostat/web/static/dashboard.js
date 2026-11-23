/* The Dashboard: a grid of panels, kept as a draft in the address and in this browser. Nothing is written to the
   server. The panels themselves (chartPanel, queryPanels, queryFields) are panels.js's; the editor is
   panel-editor.js's, used when it is there. */
"use strict";

const DASH_COLUMNS = { s: 4, m: 6, l: 8, full: 12 };
const DASH_SIZES = Object.keys(DASH_COLUMNS);
const DASH_MOST = 24;                                  // panels on one dashboard (docs/proposals/dashboard.md, section 6)
const DASH_NARROW = "(max-width: 699px)";
const DASH_EVERY = { Off: 0, "10s": 10000, "30s": 30000, "1m": 60000, "5m": 300000 };
const DASH_LONGEST = { id: 64, title: 200, note: 500 };   // what a draft's words may run to
const DASH_QUERIES = 12;                               // queries on one panel
const dashOwn = (table, key) => typeof key === "string" && Object.hasOwn(table, key);   // never a name every object inherits
const DASH_WINDOW = "1d";                              // what a dashboard with no window of its own opens on
const DASH = { draft: null, kept: false, editing: false, cells: new Map(), undo: [], timer: null, wasHere: false,
               since: null, grid: null, head: null, live: null, said: null, page: 0, asked: 0, narrow: null, flight: null, retry: 0 };

/* ---- the draft, in the address and in localStorage ---- */

function dashEncode(d) {
  let bin = "";
  for (const b of new TextEncoder().encode(JSON.stringify(d))) bin += String.fromCharCode(b);
  return btoa(bin).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}
function dashDecode(text) {
  const bin = atob(text.replace(/-/g, "+").replace(/_/g, "/"));
  return JSON.parse(new TextDecoder().decode(Uint8Array.from(bin, (c) => c.charCodeAt(0))));
}
/* a draft as the page can use it, whatever it was read from; null when it is not one */
function dashClean(d) {
  if (!d || typeof d !== "object" || Array.isArray(d) || !Array.isArray(d.panels)) return null;
  const seen = new Set();
  const isObject = (x) => !!x && typeof x === "object" && !Array.isArray(x);
  const words = (v, most) => String(v ?? "").slice(0, most);
  const panels = d.panels.slice(0, DASH_MOST * 4).filter(isObject).slice(0, DASH_MOST).map((p) => {
    const base = typeof p.id === "string" && p.id ? p.id.slice(0, DASH_LONGEST.id) : "p";
    let id = base;
    for (let n = 2; seen.has(id); n++) id = `${base}-${n}`;
    seen.add(id);
    return { ...p, id, title: words(p.title, DASH_LONGEST.title), note: words(p.note, DASH_LONGEST.note),
             form: typeof p.form === "string" ? p.form : "line", display: isObject(p.display) ? p.display : {},
             queries: Array.isArray(p.queries) ? p.queries.filter(isObject).slice(0, DASH_QUERIES) : [],
             size: dashOwn(DASH_COLUMNS, p.size) ? p.size : "m", tall: p.tall === true };
  });
  return { title: words(d.title || "Dashboard", DASH_LONGEST.title), since: dashOwn(WINDOWS, d.since) ? d.since : null, panels };
}
const dashKey = () => `ergostat.dashboard.${S.status?.name || ""}`;
const dashEveryKey = () => `${dashKey()}.every`;
function dashStored() {
  try { return dashClean(JSON.parse(localStorage.getItem(dashKey()) || "null")); } catch (e) { return null; }
}
function dashAddress(d, since) {
  const q = new URLSearchParams();
  if (d) q.set("draft", dashEncode(d));
  if (since) q.set("since", since);
  return `/dashboard${q.toString() ? `?${q}` : ""}`;
}
function dashboardDraft() { return DASH.draft ? JSON.parse(JSON.stringify(DASH.draft)) : null; }
function saveDashboardDraft(d) {
  const clean = dashClean(d);
  if (!clean) return;
  clean.since ||= S.since;
  DASH.draft = clean;
  DASH.kept = true;
  try { localStorage.setItem(dashKey(), JSON.stringify(clean)); } catch (e) { /* kept in the address alone */ }
  if (parseRoute().path === "/dashboard") replaceRoute(dashAddress(clean, clean.since));
  if (DASH.grid?.isConnected) { dashDraw(); dashHead(); }
}

/* ---- the default, from what the record holds ---- */

const DASH_MONEY = /^(usd|eur|gbp|\$)/i, DASH_COST = /(^|[._-])(cost|spend|usd)([._-]|$)/i;
const DASH_REWORK = /fix|redo|rework|retry|replan/i;        // a state work comes back to, not one it passes through
const DASH_NOT_CHARTED = /(^|[._-])(id|ids|rank|seq|index|order|priority|number|at|ts|time|timestamp|epoch)$/i;
/* the numbers worth a chart of their own on the lead kind, where it has them: how each is read */
const DASH_WANTED = [
  { match: /attempt/i, word: "attempts", agg: "avg" },
  { match: /(^|[._-])net[._-]?lines?$/i, word: "net lines", agg: "sum", rate: true },
  { match: /loop.*(hour|minute|second)/i, word: "loop hours", agg: "avg" },
];
const dashIsCost = (f) => DASH_COST.test(f.name) || DASH_MONEY.test(f.unit || "");
const dashCostUnit = (f) => (DASH_MONEY.test(f.unit || "") ? f.unit : "usd");   // a cost recorded as a bare count is money

/* a kind as the default reads it. ``info`` is its row in /api/items (finished, paused, counts, relations);
   ``queue`` the states work waits in (/api/items-graph), when asked */
function dashKind(name, k, info, queue) {
  const states = k.states || [], now = info?.counts || {};
  const done = (info?.finished || states.slice(-1)).filter((x) => states.includes(x));
  const stopped = states.filter((x) => (info?.paused || []).includes(x) || (x === "dead" && info?.dead !== false && !done.includes(x)));
  const open = states.filter((x) => !done.includes(x) && !stopped.includes(x));
  const waits = new Set(queue || states.slice(0, 1));
  const waiting = open.filter((x) => waits.has(x)), working = open.filter((x) => !waits.has(x));
  const sum = (list) => list.reduce((n, x) => n + (now[x] || 0), 0);
  const self = Object.values(info?.relations || {}).some((to) => Array.isArray(to) && to.includes(name));
  const midway = states.slice(1).filter((x) => open.includes(x)).length;      // the states between arriving and finishing
  // work that moves through several states to a declared finish, and depends on its own kind, before any log of events
  const score = (info?.finished_from === "declared" ? 4 : 0) + (self ? 3 : 0) + (stopped.length ? 1 : 0) +
                Math.min(midway, 6) + (sum(open) ? 1 : 0) - (midway < 2 ? 6 : 0);
  return { name, states, open, done, stopped, waiting, working, midway, score, held: sum(states), inWork: sum(open), now, fields: k.fields || [] };
}
/* the kinds, the work first; ergostat's own bookkeeping last */
function dashKinds(fields, infos = [], queues = {}) {
  const by = new Map(infos.map((x) => [x.name, x]));
  const kinds = Object.entries(fields?.sources?.items?.kinds || {}).map(([name, k]) => dashKind(name, k, by.get(name), queues[name]))
    .filter((k) => k.states.length);
  const own = (k) => (k.name.startsWith("ergostat.") ? 1 : 0);
  kinds.sort((a, b) => own(a) - own(b) || b.score - a.score || b.inWork - a.inWork || b.held - a.held || a.name.localeCompare(b.name));
  return kinds.some((k) => k.held) ? kinds.filter((k) => k.held) : kinds;
}
/* the states whose time is worth showing: the two holding the most of those work waits in, and the one of those it
   is worked in, in the order work passes through them */
function dashStayStates(k) {
  const most = (list, n) => list.filter((x) => !DASH_REWORK.test(x)).sort((a, b) => (k.now[b] || 0) - (k.now[a] || 0)).slice(0, n);
  const picked = new Set([...most(k.waiting, 2), ...most(k.working, 1)]);
  return k.states.filter((x) => picked.has(x));
}
const dashRate = { agg: "count", transform: "rate", rate_per: "hour" };
const dashArrivals = (k) => ({ id: "a", source: "moves", kind: k.name, measure: "entries", state: k.states.slice(0, 1), ...dashRate, label: "arrivals" });
const dashCompletions = (k) => ({ id: "b", source: "moves", kind: k.name, measure: "entries", state: k.done, ...dashRate, label: "completions" });
const dashCount = (k, id, state, label) => ({ id, source: "counts", kind: k.name, state, group_by: "kind", agg: "last", transform: "none", label });
const dashStay = (k, id, state, agg = "p50") => ({ id, source: "moves", kind: k.name, measure: "time_in_state", state: [state], agg, transform: "none", label: state });
const dashCostQuery = (k, f) => ({ id: "a", source: "items", kind: k.name, field: f.name, agg: "sum", transform: "rate", rate_per: "hour", label: "cost" });
const dashLegend = (values = ["last", "max"]) => ({ legend: "right", legend_values: values });

/* a kind's charts: arrivals against completions, its open work as waiting, working and stopped (a kind may have many
   states; the finished are left out so the open work can be read), and how long the main states hold it */
function dashKindPanels(k) {
  const out = [];
  if (k.done.length) out.push({ title: `${k.name}: arrivals and completions per hour`, form: "line", queries: [dashArrivals(k), dashCompletions(k)],
                                display: { unit: "/h", decimals: 1, ...dashLegend(), y: { min: 0 } } });
  const groups = [["waiting", k.waiting], ["working", k.working], ["stopped", k.stopped]].filter(([, s]) => s.length);
  if (groups.length) out.push({ title: `${k.name}: work by state`, form: "stacked",
                                queries: groups.map(([word, s], i) => dashCount(k, "abc"[i], s, word)),
                                display: { unit: "items", decimals: 0, ...dashLegend(["last"]), y: { min: 0 } } });
  const stays = dashStayStates(k);
  if (stays.length) out.push({ title: `${k.name}: median time in ${stays.join(", ")}`, form: "line",
                               queries: stays.map((x, i) => dashStay(k, "abc"[i], x)),
                               display: { unit: "s", ...dashLegend(), y: { min: 0 } } });
  return out;
}
const DASH_RECENT = 10;                                // buckets a rate's number is averaged over
const dashStat = (title, query, unit, decimals) => ({ title, form: "stat", size: "s", queries: [query], ...(query.transform === "rate"
  ? { note: "recent average", display: { unit, decimals, recent: DASH_RECENT } } : { display: { unit, decimals } }) });
function dashFieldPanel(k, f, want) {
  const unit = f.unit && f.unit !== "count" ? f.unit : "";
  const rate = want?.rate ? { transform: "rate", rate_per: "hour" } : { transform: "none" };
  const word = want?.word || f.name;
  return { title: `${k.name}: ${word}${want?.rate ? " per hour" : want?.agg === "avg" ? ", average" : ""}`, form: "line", size: "m",
           queries: [{ id: "a", source: "items", kind: k.name, field: f.name, agg: want?.agg || "avg", ...rate, label: word }],
           display: { unit: want?.rate ? `${unit || "items"}/h` : unit, ...dashLegend() } };
}

/* the dashboard a project opens on: the lead kind's numbers in a row, its charts, then the next kinds' */
function dashDefault(fields, infos = [], queues = {}) {
  const kinds = dashKinds(fields, infos, queues), panels = [], lead = kinds[0];
  if (lead) {
    const costKind = lead.fields.some(dashIsCost) ? lead : kinds.find((k) => k.fields.some(dashIsCost));
    const cost = costKind && (costKind.fields.find((f) => DASH_MONEY.test(f.unit || "")) || costKind.fields.find(dashIsCost));
    const costUnit = cost ? `${dashCostUnit(cost)}/h` : null;
    const stays = dashStayStates(lead);
    if (lead.open.length) panels.push(dashStat(`${lead.name}: work in progress`, dashCount(lead, "a", lead.open, "in progress"), "items", 0));
    if (lead.done.length) panels.push(dashStat(`${lead.name}: completions per hour`, dashCompletions(lead), "/h", 1));
    if (stays[0]) panels.push(dashStat(`${lead.name}: median time in ${stays[0]}`, dashStay(lead, "a", stays[0]), "s"));
    if (cost) {                                        // two rows of three, so the row has no hole
      panels.push(dashStat(`${lead.name}: arrivals per hour`, dashArrivals(lead), "/h", 1));
      if (stays[1]) panels.push(dashStat(`${lead.name}: median time in ${stays[1]}`, dashStay(lead, "a", stays[1]), "s"));
      panels.push(dashStat(`${costKind.name}: cost per hour`, dashCostQuery(costKind, cost), costUnit, 2));
    }
    const first = dashKindPanels(lead).map((p) => ({ ...p, size: "m" }));
    if (cost) first.push({ title: `${costKind.name}: cost per hour`, form: "area", size: "m", queries: [dashCostQuery(costKind, cost)],
                           display: { unit: costUnit, decimals: 2, ...dashLegend(), y: { min: 0 } } });
    const asked = DASH_WANTED.map((want) => ({ want, f: lead.fields.find((f) => want.match.test(f.name)) })).filter((x) => x.f);
    const worth = asked.length ? asked : lead.fields.filter((f) => !dashIsCost(f) && !DASH_NOT_CHARTED.test(f.name) && f.unit && f.unit !== "count")
      .slice(0, 2).map((f) => ({ f }));
    for (const { want, f } of worth) first.push(dashFieldPanel(lead, f, want));
    if (first.length % 2) first[first.length - 1].size = "full";
    panels.push(...first);
    for (const k of kinds.slice(1).filter((x) => x.inWork && x.midway >= 2 && !x.name.startsWith("ergostat.")).slice(0, 2)) {
      const row = dashKindPanels(k);
      const size = { 1: "full", 2: "m", 3: "s" }[row.length];
      panels.push(...row.map((p) => ({ ...p, size })));
    }
  } else {
    for (const x of (fields?.sources?.series?.series || []).slice(0, 6))
      panels.push({ title: x.name, form: "line", size: "m", queries: [{ id: "a", source: "series", series: x.name, agg: "last", transform: "none" }],
                    display: { unit: x.unit || "", ...dashLegend() } });
  }
  return { title: "Overview", since: null, panels: panels.slice(0, DASH_MOST).map((p, i) => ({ note: "", tall: false, ...p, id: `p${i + 1}` })) };
}
async function dashBuildDefault() {
  const fields = await queryFields();
  const infos = (await api("items", { n: 1 }).catch(() => null))?.kinds || [];
  const top = dashKinds(fields, infos).filter((k) => !k.name.startsWith("ergostat.")).slice(0, 3).map((k) => k.name), queues = {};
  if (top.length) {
    const graph = await api("items-graph", { kinds: top.join(",") }).catch(() => null);
    for (const k of graph?.kinds || []) if (k.queue?.length) queues[k.name] = k.queue;
  }
  return dashDefault(fields, infos, queues);
}

/* what a panel is told of an answer: a labelled query's one series goes by the label alone ("completions", not
   "completions: entries") */
function dashNamed(config, results) {
  const label = new Map((config.queries || []).filter((q) => q.label).map((q) => [String(q.id), q.label]));
  return (results || []).map((r) => (label.has(String(r.id)) && r.series?.length === 1 ? { ...r, series: [{ ...r.series[0], name: "" }] } : r));
}
/* a rate's last bucket is often empty or half over, so a number read from it says 0/h between bursts: a stat with
   ``display.recent`` reads the average of that many buckets up to each moment */
function dashRecent(values, n, spans = null) {
  return values.map((_, i) => {
    let sum = 0, weight = 0;
    for (let k = Math.max(0, i - n + 1); k <= i; k++) {
      if (values[k] == null) continue;
      const span = spans?.[k] > 0 ? spans[k] : 1;      // the first and last buckets are cut to the window
      sum += values[k] * span;
      weight += span;
    }
    return weight ? sum / weight : null;
  });
}
/* how many seconds of the window each bucket covers */
function dashSpans(times, until) {
  if (!Array.isArray(times) || !times.length) return null;
  const step = times.length > 1 ? times[times.length - 1] - times[times.length - 2] : null;
  return times.map((t, i) => (i + 1 < times.length ? times[i + 1] : until ?? (step == null ? t : t + step)) - t);
}
function dashAnswer(config, results, meta = null) {
  const n = config.form === "stat" ? config.display?.recent : null;
  const read = n ? (results || []).map((r) => (r.series ? { ...r, series: r.series.map((x) => ({ ...x, values: dashRecent(x.values || [], n, dashSpans(r.times, meta?.until)) })) } : r)) : results;
  return dashNamed(config, read);
}
/* a change over the window means nothing from a start near zero ("5400%"): the panel then says none */
function dashStartsNearZero(results) {
  return (results || []).some((r) => (r.series || []).some((x) => {
    const known = (x.values || []).filter((v) => v != null);
    if (known.length < 2) return false;
    const most = Math.max(...known.map(Math.abs));
    return most > 0 && Math.abs(known[0]) < most * 0.05;
  }));
}

/* ---- the grid ---- */

const dashRows = (p) => (p.form === "stat" ? 4 : 7);    // a stat: its title, number, change and sparkline
const dashHeight = (p) => dashRows(p) * (p.tall ? 2 : 1) + (DASH.editing ? 1 : 0);
/* each panel in the first place it fits, in the draft's order: no holes, and the page's order is the order seen */
function dashPack(panels, cols) {
  const used = [];
  const bottom = panels.reduce((n, p) => n + dashHeight(p), 0);   // every panel fits by here, so the search always ends
  const free = (x, y, w, hi) => {
    for (let r = y; r < y + hi; r++) for (let c = x; c < x + w; c++) if (used[r]?.[c]) return false;
    return true;
  };
  return panels.map((p) => {
    const w = Math.min(cols, DASH_COLUMNS[p.size]), hi = dashHeight(p);
    for (let y = 0; y <= bottom; y++) for (let x = 0; x + w <= cols; x++) if (free(x, y, w, hi)) {
      for (let r = y; r < y + hi; r++) { used[r] ||= []; for (let c = x; c < x + w; c++) used[r][c] = true; }
      return { p, x, y, w, h: hi };
    }
    throw new Error("a panel found no place on the grid");
  });
}
function dashTool(text, label, onclick) {
  return h("button", { type: "button", class: "ghost", title: label, "aria-label": label, onclick }, text);
}
function dashCell(p) {
  const panel = chartPanel(p);
  const grip = h("button", { type: "button", class: "ghost dash-grip", title: "Drag to move", "aria-label": "Drag to move" }, "⠇");
  grip.addEventListener("pointerdown", (ev) => dashDragMove(ev, p.id));
  const edit = typeof openPanelEditor === "function" ? dashTool("Edit", "Edit this panel", () => dashEditPanel(p.id)) : null;
  const tools = h("div", { class: "dash-tools" }, grip, h("span", { class: "dash-gap" }),
                  dashTool("←", "Move earlier", () => dashMove(p.id, -1)), dashTool("→", "Move later", () => dashMove(p.id, 1)),
                  dashTool("−", "Narrower", () => dashResize(p.id, -1)), dashTool("+", "Wider", () => dashResize(p.id, 1)),
                  dashTool("↕", "Tall or short", () => dashTall(p.id)), edit,
                  dashTool("×", "Remove this panel", () => dashRemove(p.id)));
  const handle = h("span", { class: "dash-handle", title: "Drag to resize" });
  handle.addEventListener("pointerdown", (ev) => dashDragSize(ev, p.id));
  const el = h("section", { class: "dash-cell", "data-panel": p.id }, tools, h("div", { class: "dash-body" }, panel), h("div", { class: "dash-foot" }, handle));
  return { el, panel, sig: JSON.stringify(p), drawn: false };
}
/* the cells made, kept or dropped to match the draft, and placed: a panel that only moved keeps its chart */
function dashDraw() {
  const d = DASH.draft, grid = DASH.grid;
  if (!d || !grid) return;
  const focused = document.activeElement?.closest?.(".dash-cell")?.dataset.panel;
  const ids = new Set(d.panels.map((p) => p.id));
  for (const [id, c] of DASH.cells) if (!ids.has(id)) { c.panel.destroy?.(); c.el.remove(); DASH.cells.delete(id); }
  let fresh = false;
  for (const p of d.panels) {
    const c = DASH.cells.get(p.id);
    if (!c) { const made = dashCell(p); DASH.cells.set(p.id, made); made.panel.setState?.("loading"); fresh = true; continue; }
    const sig = JSON.stringify(p);
    if (c.sig !== sig) {
      const asks = (x) => JSON.stringify(JSON.parse(x).queries);
      if (asks(c.sig) !== asks(sig)) fresh = true;
      c.sig = sig;
      c.panel.setConfig?.(p);
    }
  }
  const narrow = matchMedia(DASH_NARROW).matches;
  const placed = dashPack(d.panels, narrow ? 1 : 12);
  const order = [...placed].sort((a, b) => a.y - b.y || a.x - b.x);
  order.forEach(({ p, x, y, w, h: hi }, i) => {
    const c = DASH.cells.get(p.id);
    for (const [k, v] of [["--x", x + 1], ["--y", y + 1], ["--w", w], ["--h", hi]]) c.el.style.setProperty(k, v);
    c.el.classList.toggle("is-stat", p.form === "stat");
    c.el.setAttribute("aria-label", p.title || "Panel");
    c.el.toggleAttribute("tabindex", DASH.editing);
    if (DASH.editing) c.el.setAttribute("tabindex", "0");
    if (grid.children[i] !== c.el) grid.insertBefore(c.el, grid.children[i] || null);
  });
  grid.classList.toggle("editing", DASH.editing);
  if (focused && DASH.cells.has(focused) && DASH.editing) DASH.cells.get(focused).el.focus({ preventScroll: true });
  if (fresh) dashRefresh();
}
/* an answer that does not come: the panels say late after a while and keep what they show; the request is then given
   up and asked again (by the poll, or once more when the page does not poll) */
const DASH_LATE = 8000, DASH_GIVE_UP = 25000, DASH_RETRY = 10000;
function dashAsk(panels, ctrl) {
  const gaveUp = new Promise((_, no) => ctrl.signal.addEventListener("abort", () => no(new DOMException("gave up", "AbortError")), { once: true }));
  return Promise.race([queryPanels(panels, { since: WINDOWS[S.since], until: S.at || null, signal: ctrl.signal }), gaveUp]);
}
function dashSayLate(words) {
  for (const c of DASH.cells.values()) c.panel.setState?.(c.drawn ? "late" : "error", words);
}
async function dashRefresh() {
  const d = DASH.draft, n = ++DASH.asked;
  DASH.flight?.abort();
  clearTimeout(DASH.retry);
  if (!d?.panels.length) return;
  const ctrl = DASH.flight = new AbortController();
  const late = setTimeout(() => { if (n === DASH.asked) dashSayLate(`waiting ${dur(DASH_LATE / 1000)} for the answer`); }, DASH_LATE);
  const giveUp = setTimeout(() => ctrl.abort(), DASH_GIVE_UP);
  try {
    const got = await dashAsk(d.panels, ctrl);
    if (n !== DASH.asked) return;
    for (const [id, c] of DASH.cells) {
      const a = got?.get?.(id);
      if (!a) continue;
      const p = d.panels.find((x) => x.id === id);
      const answer = dashAnswer(p, a.results, a.meta);
      c.el.classList.toggle("dash-no-change", dashStartsNearZero(answer));
      c.panel.update(answer, a.meta);
      c.drawn = true;
    }
    if (DASH.said) DASH.said.textContent = `Updated ${clock(nowS())}`;
  } catch (e) {
    if (n !== DASH.asked) return;
    const timedOut = e?.name === "AbortError";
    dashSayLate(timedOut ? `no answer in ${dur(DASH_GIVE_UP / 1000)}; asking again` : "The server did not answer");
    if (DASH.said) DASH.said.textContent = timedOut ? "No answer; asking again" : "Could not refresh; asking again";
    if (!DASH.timer) DASH.retry = setTimeout(() => { if (DASH.grid?.isConnected && !document.hidden) dashRefresh(); }, DASH_RETRY);
  } finally {
    clearTimeout(late);
    clearTimeout(giveUp);
    if (DASH.flight === ctrl) DASH.flight = null;
  }
}
function dashPoll() {
  DASH.timer?.stop();
  DASH.timer = null;
  const every = dashEvery();
  if (every && !S.at) DASH.timer = poll(dashRefresh, every, DASH.grid);     // (paused while the tab is hidden)
}
function dashEvery() {
  let v = null;
  try { v = localStorage.getItem(dashEveryKey()); } catch (e) { /* the default */ }
  return dashOwn(DASH_EVERY, v) ? DASH_EVERY[v] : DASH_EVERY["30s"];
}

/* ---- changing the draft: by keyboard, toolbar and mouse, all the same operations ---- */

function dashAnnounce(text) { if (DASH.live) DASH.live.textContent = text; }
function dashRemember() { DASH.undo = [...DASH.undo, JSON.stringify(DASH.draft)].slice(-20); }
function dashChange(fn, said) {
  dashRemember();
  const d = dashboardDraft();
  fn(d);
  saveDashboardDraft(d);
  if (said) dashAnnounce(said);
}
const dashIndex = (id) => DASH.draft.panels.findIndex((p) => p.id === id);
const dashTitle = (p) => p.title || "Panel";
function dashMove(id, by) {
  const i = dashIndex(id), j = i + by, ps = DASH.draft.panels;
  if (i < 0 || j < 0 || j >= ps.length) return;
  dashChange((d) => d.panels.splice(j, 0, d.panels.splice(i, 1)[0]), `${dashTitle(ps[i])}: moved to place ${j + 1} of ${ps.length}`);
}
function dashResize(id, by) {
  const p = DASH.draft.panels[dashIndex(id)];
  const size = p && DASH_SIZES[DASH_SIZES.indexOf(p.size) + by];
  if (!size) return;
  dashChange((d) => { d.panels[dashIndex(id)].size = size; }, `${dashTitle(p)}: ${DASH_COLUMNS[size]} of 12 columns`);
}
function dashTall(id, tall = null) {
  const p = DASH.draft.panels[dashIndex(id)];
  if (!p) return;
  const to = tall ?? !p.tall;
  if (to === p.tall) return;
  dashChange((d) => { d.panels[dashIndex(id)].tall = to; }, `${dashTitle(p)}: ${to ? "tall" : "short"}`);
}
function dashRemove(id) {
  const i = dashIndex(id), ps = DASH.draft.panels;
  if (i < 0) return;
  const next = ps[i + 1]?.id || ps[i - 1]?.id;
  dashChange((d) => d.panels.splice(i, 1), `${dashTitle(ps[i])}: removed`);
  const to = next && DASH.cells.get(next)?.el;
  (to || DASH.head?.querySelector(".dash-add") || DASH.head?.querySelector(".dash-edit"))?.focus();
}
function dashKeydown(ev) {
  if (!DASH.editing || /^(INPUT|SELECT|TEXTAREA)$/.test(ev.target.tagName)) return;
  const id = ev.target.closest?.(".dash-cell")?.dataset.panel;
  if (!id) return;
  const arrow = { ArrowLeft: -1, ArrowUp: -1, ArrowRight: 1, ArrowDown: 1 }[ev.key];
  if ((ev.key === "Delete" || ev.key === "Backspace") && ev.target.classList.contains("dash-cell")) dashRemove(id);
  else if (arrow && ev.altKey && ev.shiftKey) {
    if (ev.key === "ArrowUp" || ev.key === "ArrowDown") dashTall(id, ev.key === "ArrowDown");
    else dashResize(id, arrow);
  } else if (arrow && ev.altKey) dashMove(id, arrow);
  else return;
  ev.preventDefault();
}
/* a drag: ``fn`` at each move of the pointer. The draft is remembered once, for one Undo */
function dashDrag(ev, fn) {
  if (ev.button !== 0) return;
  ev.preventDefault();
  dashRemember();
  const marks = DASH.undo.length;
  const before = JSON.stringify(DASH.draft);
  const move = (e) => fn(e);
  const up = () => {
    removeEventListener("pointermove", move);
    removeEventListener("pointerup", up);
    removeEventListener("pointercancel", up);
    DASH.grid?.classList.remove("dragging");
    if (JSON.stringify(DASH.draft) === before) DASH.undo = DASH.undo.slice(0, marks - 1);
    else saveDashboardDraft(DASH.draft);
    dashHead();
  };
  DASH.grid?.classList.add("dragging");
  addEventListener("pointermove", move);
  addEventListener("pointerup", up);
  addEventListener("pointercancel", up);
}
function dashDragMove(ev, id) {
  let last = null;
  dashDrag(ev, (e) => {
    const over = [...DASH.cells.entries()].find(([k, c]) => {
      if (k === id) return false;
      const r = c.el.getBoundingClientRect();
      return e.clientX >= r.left && e.clientX <= r.right && e.clientY >= r.top && e.clientY <= r.bottom;
    })?.[0];
    if (!over || over === last) { if (!over) last = null; return; }
    last = over;
    const ps = DASH.draft.panels, i = dashIndex(id), j = dashIndex(over);
    ps.splice(j, 0, ps.splice(i, 1)[0]);
    dashDraw();
    dashAnnounce(`${dashTitle(ps[j])}: moved to place ${j + 1} of ${ps.length}`);
  });
}
function dashDragSize(ev, id) {
  dashDrag(ev, (e) => {
    const c = DASH.cells.get(id), p = DASH.draft.panels[dashIndex(id)];
    if (!c || !p) return;
    const r = c.el.getBoundingClientRect(), wide = DASH.grid.getBoundingClientRect().width / 12;
    const want = (e.clientX - r.left) / wide;
    const size = DASH_SIZES.reduce((a, b) => (Math.abs(DASH_COLUMNS[b] - want) < Math.abs(DASH_COLUMNS[a] - want) ? b : a));
    const cs = getComputedStyle(DASH.grid), short = dashRows(p) * (parseFloat(cs.gridAutoRows) + parseFloat(cs.rowGap));
    const tall = e.clientY - r.top > short * 1.5;
    if (size === p.size && tall === p.tall) return;
    p.size = size;
    p.tall = tall;
    dashDraw();
    dashAnnounce(`${dashTitle(p)}: ${DASH_COLUMNS[size]} of 12 columns${tall ? ", tall" : ""}`);
  });
}
function dashEditPanel(id) {
  const p = DASH.draft.panels[dashIndex(id)];
  if (!p || typeof openPanelEditor !== "function") return;
  const back = () => DASH.cells.get(id)?.el.focus();
  openPanelEditor(JSON.parse(JSON.stringify(p)), {
    onChange: () => {},
    onSave: (config) => { dashChange((d) => { d.panels[dashIndex(id)] = { ...config, id }; }, `${config.title || "Panel"}: changed`); back(); },
    onCancel: back,
  });
}
function dashAddPanel() {
  if (typeof openPanelEditor !== "function" || DASH.draft.panels.length >= DASH_MOST) return;
  const taken = new Set(DASH.draft.panels.map((p) => p.id));
  let n = DASH.draft.panels.length + 1;
  while (taken.has(`p${n}`)) n++;
  const id = `p${n}`, back = () => DASH.head?.querySelector(".dash-add")?.focus();
  openPanelEditor({ id, title: "New panel", note: "", form: "line", queries: [], display: { legend: "right" }, size: "m", tall: false }, {
    onChange: () => {},
    onSave: (config) => {
      dashChange((d) => d.panels.push({ ...config, id }), `${config.title || "Panel"}: added`);
      DASH.cells.get(id)?.el.focus();
    },
    onCancel: back,
  });
}
async function dashCopy() {
  const url = location.origin + dashAddress(DASH.draft, S.since);
  let ok = false;
  try { await navigator.clipboard.writeText(url); ok = true; } catch (e) {
    const t = h("textarea", { class: "dash-live", "aria-hidden": "true" }, url);
    document.body.append(t);
    t.select();
    try { ok = document.execCommand("copy"); } catch (e2) { ok = false; }
    t.remove();
  }
  const said = ok ? "Link copied" : "Could not copy: the address bar holds the link";
  if (!ok) replaceRoute(dashAddress(DASH.draft, S.since));
  if (DASH.said) DASH.said.textContent = said;
  dashAnnounce(said);
}
function dashUndo() {
  const last = DASH.undo[DASH.undo.length - 1];
  if (!last) return;
  DASH.undo = DASH.undo.slice(0, -1);
  saveDashboardDraft(JSON.parse(last));
  dashAnnounce("Undone");
}
async function dashReset() {
  dashRemember();
  try { localStorage.removeItem(dashKey()); } catch (e) { /* nothing kept */ }
  DASH.kept = false;
  replaceRoute(dashAddress(null, S.since));
  try {
    DASH.draft = dashClean(await dashBuildDefault());
    dashDraw();
    dashHead();
    dashAnnounce("Back to the default dashboard");
  } catch (e) { dashAnnounce("Could not make the default dashboard"); }
}

/* ---- the page ---- */

function dashHead() {
  const d = DASH.draft, box = DASH.head;
  if (!box || !d) return;
  const every = dashEvery();
  const word = Object.keys(DASH_EVERY).find((k) => DASH_EVERY[k] === every);
  const refresh = menu(every ? `Refresh: ${word}` : "Refresh: off", () => [
    h("div", { class: "menu-label" }, "Refresh every"),
    ...Object.keys(DASH_EVERY).map((k) => ({ label: k, checked: k === word, onclick: () => {
      try { localStorage.setItem(dashEveryKey(), k); } catch (e) { /* for this visit */ }
      dashPoll();
      dashHead();
    } })),
  ], { right: true, title: "How often the panels are read again" });
  const title = DASH.editing
    ? h("input", { class: "dash-title-input", value: d.title, "aria-label": "Dashboard title",
                   onchange: (ev) => dashChange((x) => { x.title = ev.target.value.trim() || "Dashboard"; }, "Title changed") })
    : h("h1", {}, d.title);
  const canEdit = typeof openPanelEditor === "function";
  box.replaceChildren(title, DASH.said, h("span", { class: "dash-actions" },
    DASH.editing && canEdit ? h("button", { type: "button", class: "dash-add", disabled: d.panels.length >= DASH_MOST ? "" : null, onclick: dashAddPanel }, "Add panel") : null,
    DASH.editing ? h("button", { type: "button", disabled: DASH.undo.length ? null : "", onclick: dashUndo }, "Undo") : null,
    DASH.editing && DASH.kept ? h("button", { type: "button", onclick: dashReset, title: "Drop this draft and go back to the default" }, "Reset") : null,
    refresh,
    h("button", { type: "button", onclick: dashCopy, title: "Copy a link to this dashboard" }, "Copy link"),
    h("button", { type: "button", class: `dash-edit${DASH.editing ? " on" : ""}`, "aria-pressed": String(DASH.editing), onclick: () => {
      DASH.editing = !DASH.editing;
      dashDraw();
      dashHead();
      DASH.head.querySelector(".dash-edit")?.focus();
    } }, DASH.editing ? "Done" : "Edit")));
}
function dashLeave(n) {
  return { stop() {
    if (n !== DASH.page) return;
    DASH.wasHere = parseRoute().path === "/dashboard";
    DASH.timer?.stop();
    DASH.timer = null;
    DASH.asked++;
    DASH.flight?.abort();
    clearTimeout(DASH.retry);
    for (const c of DASH.cells.values()) c.panel.destroy?.();
    DASH.cells.clear();
    DASH.narrow?.removeEventListener("change", dashDraw);
    DASH.grid = null;
  } };
}
async function pageDashboard(main, q) {
  const stayed = DASH.wasHere, n = ++DASH.page;
  DASH.wasHere = false;
  if (!stayed) { DASH.editing = false; DASH.undo = []; }
  S.timer = dashLeave(n);
  const p = h("div", { class: "page dash" });
  const notice = h("p", { class: "note", hidden: "" });
  DASH.head = h("header", { class: "dash-head" }, h("h1", {}, "Dashboard"));
  DASH.said = h("span", { class: "muted small dash-said" });
  DASH.live = h("div", { class: "dash-live", role: "status", "aria-live": "polite" });
  DASH.grid = h("div", { class: "dash-grid", onkeydown: dashKeydown }, h("p", { class: "muted page-loading" }, "Loading…"));
  p.append(DASH.head, notice, DASH.grid, DASH.live);
  main.append(p);
  if (SNAP) {                                          // its panels ask the server for what the window holds
    DASH.grid.replaceChildren(h("p", { class: "note dash-snapshot" }, "The Dashboard needs the live server: a snapshot keeps only the answers taken when it was made. Open it with ergostat web."));
    return;
  }
  if (typeof chartPanel !== "function" || typeof queryPanels !== "function") {
    DASH.grid.replaceChildren(h("p", { class: "note" }, "The panels did not load, so there is nothing to draw."));
    return;
  }
  let d = null, fromAddress = false;
  const text = q.get("draft");
  if (text) {
    try { d = dashClean(dashDecode(text)); } catch (e) { d = null; }
    fromAddress = !!d;
    if (!d) { notice.hidden = false; notice.textContent = "This link's dashboard could not be read, so this is the one kept here."; }
  }
  d ||= dashStored();
  DASH.kept = !!d;
  if (!d) {
    try { d = dashClean(await dashBuildDefault()); } catch (e) {
      if (n !== DASH.page) return;
      DASH.grid.replaceChildren(h("p", { class: "note" }, "Could not read what there is to chart. ",
                                  h("button", { type: "button", onclick: route }, "Try again")));
      return;
    }
    if (n !== DASH.page) return;
  }
  const asked = dashOwn(WINDOWS, q.get("since")) ? q.get("since") : null;
  const moved = stayed && DASH.since && S.since !== DASH.since;   // the header's window, changed here
  const since = moved ? S.since : asked || d.since || DASH_WINDOW;
  if (S.since !== since) { S.since = since; S.graphSig = ""; showAt(); refreshHeader(); }
  DASH.since = since;
  DASH.draft = d;
  if (DASH.kept) d.since = since;
  if (moved) replaceRoute(dashAddress(DASH.kept ? d : null, since));
  // a link opened is only shown: what this browser keeps changes when the reader changes something
  if (moved && DASH.kept && !fromAddress) try { localStorage.setItem(dashKey(), JSON.stringify(d)); } catch (e) { /* in the address */ }
  DASH.grid.replaceChildren();
  DASH.narrow = matchMedia(DASH_NARROW);
  DASH.narrow.addEventListener("change", dashDraw);
  dashHead();
  if (!d.panels.length) {
    DASH.grid.append(h("p", { class: "note dash-empty" }, "Nothing is recorded to chart yet. Panels appear here once the model has items or series."));
    return;
  }
  dashDraw();
  dashPoll();
}
