/* The Dashboard: a grid of panels, kept as a draft in the address and in this browser. Nothing is written to the
   server. The panels themselves (chartPanel, queryPanels, queryFields) are panels.js's; the editor is
   panel-editor.js's, used when it is there. */
"use strict";

const DASH_COLUMNS = { s: 4, m: 6, l: 8, full: 12 };
const DASH_SIZES = Object.keys(DASH_COLUMNS);
const DASH_MOST = 32;                                  // panels on one dashboard (docs/proposals/dashboard.md, section 6)
const DASH_NARROW = "(max-width: 699px)";
const DASH_EVERY = { Off: 0, "10s": 10000, "30s": 30000, "1m": 60000, "5m": 300000 };
const DASH_LONGEST = { id: 64, title: 200, note: 500 };   // what a draft's words may run to
const DASH_QUERIES = 12;                               // queries on one panel
const DASH_ROWS = 16, DASH_VARS = 8;                   // rows on one dashboard; variables a panel may repeat by
const DASH_REPEAT_MOST = 24;                           // panels one repeated panel shows, itself included
const DASH_DRAWN_MOST = 64;                            // charts on the page, the copies of repeated panels included
const dashOwn = (table, key) => typeof key === "string" && Object.hasOwn(table, key);   // never a name every object inherits
const DASH_WINDOW = "1d";                              // what a dashboard with no window of its own opens on
const DASH = { draft: null, kept: false, editing: false, cells: new Map(), undo: [], timer: null, wasHere: false,
               since: null, grid: null, head: null, live: null, said: null, page: 0, asked: 0, narrow: null, flight: null, retry: 0,
               drag: null, pending: null, lifted: null, slot: null, settle: 0,
               values: new Map(), room: new Map(), got: null };   // a repeated panel's values and the grid rows kept for them

/* ---- the layout engine: pure, no page. An item is {id, x, y, w, h} on 12 columns and rows of equal height; a row
   ({row: true}) is a full-width line one high, and the panels under it, down to the next row, are its own ---- */

const DashLayout = (() => {
  const COLS = 12, MIN_W = 3, MIN_H = 3, MAX_H = 48, MAX_Y = 2000;     // a draft from a link is bounded, so every search ends
  const whole = (v, or) => (Number.isFinite(v) ? Math.round(v) : or);
  const hits = (a, b) => a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
  const reading = (a, b) => a.y - b.y || a.x - b.x || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0);
  function bounded(it) {
    const y = Math.min(MAX_Y, Math.max(0, whole(it.y, 0)));
    if (it.row) return { id: it.id, row: true, x: 0, y, w: COLS, h: 1 };
    const w = Math.min(COLS, Math.max(MIN_W, whole(it.w, 6))), h = Math.min(MAX_H, Math.max(MIN_H, whole(it.h, 7)));
    return { id: it.id, x: Math.min(COLS - w, Math.max(0, whole(it.x, 0))), y, w, h };
  }
  /* the row each panel sits under: the last above its top (null above the first row) */
  function owners(items) {
    const rows = items.filter((x) => x.row).sort(reading), of = new Map();
    for (const it of items) if (!it.row) of.set(it.id, rows.filter((r) => r.y < it.y).pop()?.id ?? null);
    return of;
  }
  /* overlaps cleared by pushing down only what is hit, and what that then hits: nothing rises, and what is ``fixed``
     never moves. A row pushed takes the panels under it along (as ``from`` had them), so a row stays a break */
  function push(items, fixed, from = items, start = [...fixed]) {
    const at = new Map(items.map((x) => [x.id, { ...x }]));
    const before = from.filter((x) => !fixed.has(x.id)), of = owners(before);
    const rows = before.filter((x) => x.row).sort(reading).map((r) => r.id);
    // each in its section's turn: what sits above the first row, the first row, what is under it, the next row...
    const rank = (x) => (x.row ? rows.indexOf(x.id) * 2 + 1 : of.has(x.id) ? (rows.indexOf(of.get(x.id)) + 1) * 2 : 0);
    const lower = (a, b) => (fixed.has(a.id) || fixed.has(b.id) ? (fixed.has(a.id) ? b : a) : rank(a) > rank(b) ? a : b);
    const queue = start.filter((id) => at.has(id)), last = new Map(), was = new Map(from.map((x) => [x.id, x.y]));
    // a panel carried down a long way can leap a row (one line high) without landing on it: its path counts
    const leapt = (a, b) => b.row && !a.row && last.has(a.id) && rank(b) > rank(a) && b.y >= last.get(a.id) && b.y < a.y + a.h;
    for (let n = 0; queue.length && n < 50000; n++) {
      const a = at.get(queue.shift());
      for (const b of at.values()) {
        if (b === a || !(hits(a, b) || leapt(a, b))) continue;
        const down = lower(a, b), up = down === a ? b : a;
        if (fixed.has(down.id)) continue;                                  // two the caller placed: theirs to keep apart
        const by = up.y + up.h - down.y;
        const carried = down.row ? [...at.values()].filter((x) => x !== up && !x.row && !fixed.has(x.id) && of.get(x.id) === down.id) : [];
        // what the row carries keeps its place under the row: one already pushed further goes no further
        const under = (m) => (was.has(m.id) && was.has(down.id) ? down.y + by + was.get(m.id) - was.get(down.id) - m.y : by);
        for (const [m, step] of [[down, by], ...carried.map((m) => [m, under(m)])]) {
          if (step <= 0) continue;
          last.set(m.id, Math.min(last.get(m.id) ?? m.y, m.y)); m.y += step; queue.push(m.id);
        }
        if (down === a) break;
      }
    }
    if (queue.length) {                                                  // never left overlapping: past the bound, each in
      const placed = [...at.values()].filter((x) => fixed.has(x.id));    // reading order goes below what it meets
      for (const x of [...at.values()].filter((v) => !fixed.has(v.id)).sort(reading)) {
        for (let b; (b = placed.find((p) => hits(p, x))); ) x.y = b.y + b.h;
        placed.push(x);
      }
    }
    return items.map((x) => at.get(x.id));
  }
  /* a panel put at ``to`` (a place, a size or both): only what it then covers moves, downward */
  function place(items, id, to) {
    const from = items.find((x) => x.id === id);
    if (!from) return items;
    const t = bounded({ ...from, ...to, id, row: from.row });
    return push(items.map((x) => (x.id === id ? t : x)), new Set([id]), items);
  }
  const move = (items, id, to) => place(items, id, { x: to.x, y: to.y });
  const resize = (items, id, to) => place(items, id, to);
  /* each in the first place it fits below what is ``placed``, in the order given */
  function pack(items, placed = []) {
    const out = [...placed], top = height(placed);
    for (const raw of items) {
      const it = bounded(raw);
      let found = null;
      for (let y = top; !found; y++) for (let x = 0; x + it.w <= COLS; x++) {
        const at = { ...it, x, y };
        if (!out.some((p) => hits(p, at))) { found = at; break; }
      }
      out.push(found);
    }
    return out.slice(placed.length);
  }
  /* one column, in the order given */
  function stack(items) {
    let y = 0;
    return items.map((it) => { const at = { ...bounded(it), x: 0, w: COLS, y }; y += at.h; return at; });
  }
  /* each row with its panels and the lines it spans, down to the next row (the last, down to its lowest panel) */
  function sections(items) {
    const rows = items.filter((x) => x.row).sort(reading), of = owners(items);
    return rows.map((row, i) => {
      const members = items.filter((x) => of.get(x.id) === row.id);
      const end = rows[i + 1]?.y ?? Math.max(row.y + 1, ...members.map((m) => m.y + m.h));
      return { row, members, span: end - row.y };
    });
  }
  /* a row taken, with its panels and the lines it spans, to be the ``index``-th row; the others close up around it */
  function moveRow(items, id, index) {
    const secs = sections(items), i = secs.findIndex((s) => s.row.id === id);
    if (i < 0) return items;
    const order = secs.filter((s) => s.row.id !== id);
    order.splice(Math.max(0, Math.min(order.length, index)), 0, secs[i]);
    const by = new Map();
    let y = secs[0].row.y;
    for (const s of order) { for (const x of [s.row, ...s.members]) by.set(x.id, y - s.row.y); y += s.span; }
    return items.map((x) => (by.has(x.id) ? { ...x, y: x.y + by.get(x.id) } : x));
  }
  /* a row folded: its panels kept aside (their place counted from the row) and what is below up by what it spanned */
  function fold(items, id) {
    const s = sections(items).find((x) => x.row.id === id);
    if (!s) return { items, hidden: [], span: 1 };
    const gone = new Set(s.members.map((m) => m.id)), below = s.row.y + s.span, by = s.span - 1;
    return { span: s.span, hidden: s.members.map((m) => ({ ...m, y: m.y - s.row.y })),
             items: items.filter((x) => !gone.has(x.id)).map((x) => (x.y >= below ? { ...x, y: x.y - by } : x)) };
  }
  /* and opened again: what is below goes down by the same, so folding and opening changes nothing */
  function unfold(items, id, hidden, span = 1) {
    const r = items.find((x) => x.id === id);
    if (!r) return items;
    const by = Math.max(span, 1, ...hidden.map((m) => m.y + m.h)) - 1;
    return [...items.map((x) => (x.y > r.y ? { ...x, y: x.y + by } : x)), ...hidden.map((m) => ({ ...m, y: r.y + m.y }))];
  }
  /* a panel's ``copies`` laid out beside it, line after line in its own columns onward; ``room`` grid rows down from
     its top are kept for them, so values that go away leave the room and nothing below moves back. ``reach``: the grid
     rows from its top that they and the room now take */
  function spread(items, id, copies, room = 0) {
    const s = items.find((x) => x.id === id);
    if (!s) return { items, reach: 0 };
    const per = Math.max(1, Math.floor((COLS - s.x) / s.w));
    const made = copies.map((cid, i) => ({ id: cid, x: s.x + ((i + 1) % per) * s.w, y: s.y + Math.floor((i + 1) / per) * s.h, w: s.w, h: s.h }));
    const reach = Math.min(MAX_Y, Math.max(whole(room, 0), Math.ceil((copies.length + 1) / per) * s.h));
    const kept = { id: "\u0000room", x: s.x, y: s.y, w: Math.min(COLS - s.x, per * s.w), h: reach };
    const out = push([...items, ...made, kept], new Set([id, ...copies, kept.id]));
    return { items: out.filter((x) => x.id !== kept.id), reach };
  }
  /* what a draft holds, made sound: laid-out items kept where they are (any overlap pushed down, in reading order),
     those with none (version 1, or just added) placed below them */
  function arrange(list) {
    const laid = list.filter((x) => x.layout && typeof x.layout === "object").map((x) => bounded({ ...x.layout, id: x.id, row: x.row }));
    const kept = push(laid, new Set(), laid, [...laid].sort(reading).map((x) => x.id));
    const fresh = pack(list.filter((x) => !(x.layout && typeof x.layout === "object"))
      .map((x) => ({ id: x.id, row: x.row, x: 0, y: 0, w: x.w, h: x.h })), kept);
    const by = new Map([...kept, ...fresh].map((p) => [p.id, p]));
    return list.map((x) => by.get(x.id));
  }
  /* a phone's new reading order: the panels take, in that order, the places the panels held in reading order */
  function reorder(items, order) {
    const panels = items.filter((x) => !x.row), slots = [...panels].sort(reading), by = new Map(panels.map((x) => [x.id, x]));
    const ids = order.filter((id) => by.has(id));
    const to = new Map(ids.map((id, i) => [id, bounded({ ...by.get(id), x: slots[i].x, y: slots[i].y })]));
    const next = items.map((x) => to.get(x.id) || x);
    return push(next, new Set(), items, [...next].sort(reading).map((x) => x.id));
  }
  const overlaps = (items) => items.some((a, i) => items.slice(i + 1).some((b) => hits(a, b)));
  function height(items) { return items.reduce((n, p) => Math.max(n, p.y + p.h), 0); }
  return { COLS, MIN_W, MIN_H, bounded, move, resize, pack, stack, sections, moveRow, fold, unfold, spread, arrange, reorder,
           overlaps, height, reading };
})();

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
  const named = (raw, or) => {                         // an id no other panel or row has; "~" is kept for copies
    const base = typeof raw === "string" && raw ? raw.slice(0, DASH_LONGEST.id).replace(/~/g, "-") : or;
    let id = base;
    for (let n = 2; seen.has(id); n++) id = `${base}-${n}`;
    seen.add(id);
    return id;
  };
  const vars = {};
  for (const [k, v] of Object.entries(isObject(d.vars) ? d.vars : {}).slice(0, DASH_VARS))
    if (Array.isArray(v)) vars[words(k, DASH_LONGEST.id)] = [...new Set(v.filter((x) => typeof x === "string" || Number.isFinite(x)).map((x) => words(x, DASH_LONGEST.id)))].slice(0, DASH_REPEAT_MOST);
  let room = DASH_MOST;
  const panelOf = (p) => {
    const r = isObject(p.repeat) ? p.repeat : null;
    const repeat = typeof r?.query === "string" ? { query: r.query.slice(0, DASH_LONGEST.id) } : typeof r?.var === "string" && dashOwn(vars, r.var) ? { var: r.var } : null;
    const { repeat: _, copyOf: __, ...rest } = p;
    return { ...rest, ...(repeat ? { repeat } : {}), id: named(p.id, "p"), title: words(p.title, DASH_LONGEST.title), note: words(p.note, DASH_LONGEST.note),
             form: typeof p.form === "string" ? p.form : "line", display: isObject(p.display) ? p.display : {},
             queries: Array.isArray(p.queries) ? p.queries.filter(isObject).slice(0, DASH_QUERIES) : [],
             size: dashOwn(DASH_COLUMNS, p.size) ? p.size : "m", tall: p.tall === true };
  };
  const some = (list) => { const got = (Array.isArray(list) ? list : []).slice(0, DASH_MOST * 4).filter(isObject).slice(0, room); room -= got.length; return got; };
  const panels = some(d.panels).map(panelOf);
  const span = (p) => ({ w: DASH_COLUMNS[p.size], h: dashRows(p) * (p.tall ? 2 : 1) });
  const rows = (Array.isArray(d.rows) ? d.rows : []).filter(isObject).slice(0, DASH_ROWS).map((r) => {
    const collapsed = r.collapsed === true;
    const hidden = collapsed ? some(r.panels).map(panelOf) : [];
    for (const p of hidden) {                          // placed from the row's line: one below it at least
      const it = DashLayout.bounded({ ...span(p), ...(isObject(p.layout) ? p.layout : {}), id: p.id });
      p.layout = { x: it.x, y: Math.max(1, it.y), w: it.w, h: it.h };
    }
    return { id: named(r.id, "row"), title: words(r.title || "Row", DASH_LONGEST.title), collapsed, layout: isObject(r.layout) ? r.layout : null,
             ...(collapsed ? { panels: hidden, span: Math.min(400, Math.max(1, Math.round(Number(r.span)) || 1)) } : {}) };
  });
  const list = [...panels.map((p) => ({ id: p.id, layout: p.layout, ...span(p) })), ...rows.map((r) => ({ id: r.id, row: true, layout: r.layout }))];
  const laid = new Map(DashLayout.arrange(list).map((x) => [x.id, x]));
  for (const p of panels) { const { x, y, w, h: hi } = laid.get(p.id); p.layout = { x, y, w, h: hi }; }
  for (const r of rows) r.layout = { y: laid.get(r.id).y };
  return { title: words(d.title || "Dashboard", DASH_LONGEST.title), since: dashOwn(WINDOWS, d.since) ? d.since : null, panels,
           ...(rows.length ? { rows } : {}), ...(Object.keys(vars).length ? { vars } : {}) };
}
const dashKey = () => `ergostat.dashboard.${S.status?.name || ""}`;
const dashEveryKey = () => `${dashKey()}.every`;
function dashStored() {
  try { return dashClean(JSON.parse(localStorage.getItem(dashKey()) || "null")); } catch (e) { return null; }
}
function dashAddress(d, since) {
  const q = new URLSearchParams();
  if (d && dashFitsLink(d)) q.set("draft", dashEncode(d));
  if (since) q.set("since", since);
  return `/dashboard${q.toString() ? `?${q}` : ""}`;
}
/* the server refuses a very long address (414), and proxies refuse shorter ones: a larger draft stays in this browser */
const DASH_LINK_MOST = 30000;
const dashFitsLink = (d) => dashEncode(d).length <= DASH_LINK_MOST;
const DASH_TOO_LONG = "Too large for a link: kept in this browser only";
function dashboardDraft() { return DASH.draft ? JSON.parse(JSON.stringify(DASH.draft)) : null; }
function saveDashboardDraft(d) {
  const clean = dashClean(d);
  if (!clean) return;
  clean.since ||= S.since;
  DASH.draft = clean;
  DASH.kept = true;
  DASH.declared = null;                                // a declared one changed is the reader's own draft
  try { localStorage.setItem(dashKey(), JSON.stringify(clean)); } catch (e) { /* kept in the address alone */ }
  if (parseRoute().path === "/dashboard") replaceRoute(dashAddress(clean, clean.since));
  if (DASH.grid?.isConnected) { dashDraw(); dashHead(); }
  if (!dashFitsLink(clean) && DASH.said) { DASH.said.textContent = DASH_TOO_LONG; dashAnnounce(DASH_TOO_LONG); }
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
const dashArrivals = (k) => ({ id: "a", source: "moves", kind: k.name, measure: "entries", first_only: true, state: k.states.slice(0, 1), ...dashRate, label: "arrivals" });
const dashCompletions = (k) => ({ id: "b", source: "moves", kind: k.name, measure: "entries", state: k.done, ...dashRate, label: "completions" });
const dashCount = (k, id, state, label) => ({ id, source: "counts", kind: k.name, state, group_by: "kind", agg: "last", transform: "none", label });
const dashStay = (k, id, state, agg = "p50") => ({ id, source: "moves", kind: k.name, measure: "time_in_state", state: [state], agg, transform: "none", label: state });
const dashCostQuery = (k, f) => ({ id: "a", source: "items", kind: k.name, field: f.name, agg: "sum", transform: "rate", rate_per: "hour", label: "cost" });
/* a duration's number, over the whole window: the median of everything that left the state, with what is still in it
   said beside it, since those have not finished waiting and are in no exit */
const dashStayStat = (k, state) => ({ ...dashStat(`${k.name}: median wait of items that left ${state}`, dashStay(k, "a", state), "s"),
                                      note: "whole window", display: { unit: "s", whole: true, still: { kind: k.name, state } } });
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
    if (stays[0]) panels.push(dashStayStat(lead, stays[0]));
    if (cost) {                                        // two rows of three, so the row has no hole
      panels.push(dashStat(`${lead.name}: arrivals per hour`, dashArrivals(lead), "/h", 1));
      if (stays[1]) panels.push(dashStayStat(lead, stays[1]));
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
    panels.push(...dashExamples(lead, fields, new Set(panels.map((p) => normalizeForm(p).form))));
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
  const out = { title: "Overview", since: null, panels: panels.slice(0, DASH_MOST).map((p, i) => ({ note: "", tall: false, ...p, id: `p${i + 1}` })) };
  const sql = (fields?.datasources || []).find((s) => s.type === "sql");
  const pipes = sql ? (fields?.pipelines || []).filter((x) => /^[A-Za-z_]\w*$/.test(x.kind.replace(/-/g, "_"))).slice(0, 2) : [];
  if (!pipes.length) return out;
  const span = (p) => ({ id: p.id, w: DASH_COLUMNS[p.size || "m"], h: dashRows(p) * (p.tall ? 2 : 1) });
  const laid = DashLayout.pack(out.panels.map(span));
  out.panels.forEach((p, i) => { p.layout = { x: laid[i].x, y: laid[i].y, w: laid[i].w, h: laid[i].h }; });
  out.rows = [];
  for (const [n, pipe] of pipes.entries()) {
    const top = DashLayout.height([...out.panels.map((p) => p.layout), ...out.rows.map((r) => ({ y: r.layout.y, h: 1 }))]);
    const mine = dashPipeline(pipe, sql.name).slice(0, DASH_MOST - out.panels.length).map((p, i) => ({ note: "", tall: false, ...p, id: `q${n + 1}-${i + 1}` }));
    const at = DashLayout.pack(mine.map(span), [{ x: 0, y: top, w: 12, h: 1 }]);
    mine.forEach((p, i) => { p.layout = { x: at[i].x, y: at[i].y, w: at[i].w, h: at[i].h }; });
    out.rows.push({ id: `row-${pipe.kind}`, title: pipe.title || pipe.kind, collapsed: false, layout: { y: top } });
    out.panels.push(...mine);
  }
  return out;
}
/* a pipeline's row (SPEC §5a, Stages): what its running item holds and the line waiting, its stage now and time left,
   that item's every stage, its recent items and the typical time of each stage; ordinary SQL panels over item_stages,
   item_progress and stage_estimates, which a person opens, edits and copies like any other */
function dashPipeline(pipe, src) {
  const lit = (s) => `'${String(s).replace(/'/g, "''")}'`, word = (s) => `"${s}"`, K = lit(pipe.kind);
  const view = (k) => k.replace(/-/g, "_");
  const live = `(select id from item_stages where kind = ${K} order by id in (select id from item_progress) desc, started desc limit 1)`;
  const q = (text) => [{ id: "a", source: src, text }];
  const out = [];
  const w = pipe.waiting;
  if (w && /^[A-Za-z_]\w*$/.test(view(w.kind))) {
    const f = (x) => `(select value from item_fields f where f.id = w.id and f.field = ${lit(x)})`;
    const order = [...w.order.flatMap((x) => [`${f(x)} is null`, f(x)]), "w.id"].join(", ");
    const held = pipe.holds ? `select w.id || ' in ' || l.id as item, 0 as turn from ${word(view(w.kind))} w, ` +
      `(select id, value from item_fields where field = ${lit(pipe.holds)} and id = ${live} and id in (select id from item_progress)) l ` +
      `where instr(l.value, '"' || w.id || '"') > 0 union all ` : "";
    out.push({ title: `${pipe.title || pipe.kind}: running, and waiting in the order taken`, form: "table", size: "m",
               queries: q(`${held}select * from (select w.id || ' waiting' as item, row_number() over (order by ${order}) as turn ` +
                          `from ${word(view(w.kind))} w where w.state = ${lit(w.state)}) order by turn`), display: {} });
  }
  // a table takes one dimension: each row's words in one column, its numbers (minutes) after
  const min = (x, as) => `round(${x} / 60.0, 1) as ${as}`;
  out.push({ title: `${pipe.title || pipe.kind}: now`, form: "table", size: "m", display: {},
             queries: q(`select id || ': ' || coalesce(stage, 'between stages') || case when note != '' then ' (' || note || ')' else '' end as stage, ` +
                        `${min("elapsed", "elapsed_min")}, ${min("expected", "expected_min")}, samples, ${min('"left"', "left_min")} ` +
                        `from item_progress where kind = ${K} order by id`) });
  out.push({ title: `${pipe.title || pipe.kind}: each stage of the running one`, form: "table", size: "m", display: {},
             queries: q(`select row_number() over (order by s.started) || '. ' || s.stage || ' (run ' || s.run || ' ' || s.run_kind || ': ' || ` +
                        `s.state || coalesce(', ' || s.outcome, '') || ')' as stage, ${min("s.seconds", "minutes")}, ${min("e.expected", "expected_min")} ` +
                        `from item_stages s left join stage_estimates e on e.kind = s.kind and e.run_kind = s.run_kind and e.stage = s.stage ` +
                        `where s.id = ${live} order by s.started`) });
  const size = pipe.holds ? `(select json_array_length(value) from item_fields f where f.id = s.id and f.field = ${lit(pipe.holds)}) as size, ` : "";
  out.push({ title: `${pipe.title || pipe.kind}: recent`, form: "table", size: "m", display: {},
             queries: q(`select s.id || ' ' || i.state || ': ' || group_concat(s.stage || ' ' || coalesce(round(s.seconds / 60.0, 1) || ' min', s.state), ', ') as item, ` +
                        `${size}${min("(max(coalesce(s.finished, s.started)) - min(s.started))", "minutes")} from (select * from item_stages where kind = ${K} order by started) s ` +
                        `join ${word(view(pipe.kind))} i on i.id = s.id group by s.id order by min(s.started) desc limit 10`) });
  out.push({ title: `${pipe.title || pipe.kind}: median minutes per stage`, form: "line", size: "full", display: { unit: "min", ...dashLegend(), y: { min: 0 } },
             queries: q(`select cast(finished / max(:step, 3600) as integer) * max(:step, 3600) as time, ` +
                        pipe.stages.map((s) => `median(case when stage = ${lit(s)} then seconds / 60.0 end) as ${word(s)}`).join(", ") +
                        ` from item_stages where kind = ${K} and outcome = 'passed' and finished >= :since and finished < :until group by 1 order by 1`) });
  return out;
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

const dashRows = (p) => (p.form === "stat" ? 4 : p.form === "diagram" ? 10 : 7);    // a stat: its title, number, change and sparkline
/* what is on the grid: the panels and the rows (a folded row keeps its panels in it, off the grid) */
const dashItems = (d) => [...d.panels.map((p) => ({ id: p.id, ...p.layout })),
                          ...(d.rows || []).map((r) => ({ id: r.id, row: true, x: 0, y: r.layout.y, w: DashLayout.COLS, h: 1 }))];
const dashHeld = (d) => d.panels.length + (d.rows || []).reduce((n, r) => n + (r.panels?.length || 0), 0);
const dashRow = (d, id) => (d.rows || []).find((r) => r.id === id);
/* a variable's name in a query's words, given its value */
function dashSub(v, name, value) {
  if (typeof v === "string") return v.split(`\${${name}}`).join(value).split(`$${name}`).join(value);
  if (Array.isArray(v)) return v.map((x) => dashSub(x, name, value));
  return v && typeof v === "object" ? Object.fromEntries(Object.entries(v).map(([k, x]) => [k, dashSub(x, name, value)])) : v;
}
/* the values a repeated panel shows one panel for: its variable's, or the series its query last answered with */
const dashValues = (d, p) => (p.repeat?.var ? d.vars?.[p.repeat.var] || [] : DASH.values.get(p.id) || []).slice(0, DASH_REPEAT_MOST);
/* what is drawn, and where: each repeated panel shows its first value and is followed by a copy for each other value,
   laid out beside it in its row. The copies are not in the draft; only they lay themselves out. Only a drawing that is
   ``kept`` (not a drag's or a lifted panel's preview) changes the room kept for them */
function dashView(d, items = dashItems(d), kept = false) {
  const panels = [];
  let at = items, left = DASH_DRAWN_MOST - d.panels.length;
  for (const p of d.panels) {
    const values = p.repeat ? dashValues(d, p).slice(0, 1 + Math.max(0, left)) : [];
    left -= Math.max(0, values.length - 1);
    if (!values.length) { panels.push(p); continue; }
    const one = (value, id) => ({ ...p, id, value, title: `${p.title}: ${value}`, ...(id === p.id ? {} : { copyOf: p.id }),
                                  ...(p.repeat.var ? { queries: dashSub(p.queries, p.repeat.var, value) } : {}) });
    const copies = values.slice(1).map((v) => `${p.id}~${v}`);
    panels.push(one(values[0], p.id), ...values.slice(1).map((v, i) => one(v, copies[i])));
    const got = DashLayout.spread(at, p.id, copies, DASH.room.get(p.id) || 0);
    at = got.items;
    if (kept) DASH.room.set(p.id, got.reach);
  }
  return { panels, items: at };
}
/* before the arrangement is changed by hand, the draft takes the places as drawn (what copies pushed down stays down)
   and the rooms are let go: removing, shrinking, moving or no longer repeating a panel then moves nothing else */
function dashSettle() {
  const d = DASH.draft;
  if (!d) return;
  const at = new Map(dashView(d).items.map((x) => [x.id, x]));
  for (const x of [...d.panels, ...(d.rows || [])]) if (at.has(x.id)) x.layout = { ...x.layout, y: at.get(x.id).y };
  DASH.room.clear();
}
/* the series of a repeated panel's query for one value; a panel repeated by its query's label asks nothing of its own */
const dashPick = (results, q, value) => (value == null ? results : (results || []).map((r) => (String(r.id) === q
  ? { ...r, series: (r.series || []).filter((x) => String(x.name) === value) } : r)));
const dashAsks = (p) => !(p.copyOf && p.repeat?.query);
/* the width and height the editor offers, kept true to the arrangement */
function dashNearestSize(w) {
  return DASH_SIZES.reduce((a, b) => (Math.abs(DASH_COLUMNS[b] - w) < Math.abs(DASH_COLUMNS[a] - w) ? b : a));
}
/* an arrangement written to a draft's panels and rows, which then read in its order */
function dashWrite(d, items) {
  const by = new Map(items.map((x) => [x.id, x]));
  for (const p of d.panels) {
    if (!by.has(p.id)) continue;
    const { x, y, w, h: hi } = by.get(p.id);
    p.layout = { x, y, w, h: hi };
    p.size = dashNearestSize(w);
    p.tall = hi >= dashRows(p) * 2;
  }
  for (const r of d.rows || []) if (by.has(r.id)) r.layout = { y: by.get(r.id).y };
  d.panels.sort((a, b) => DashLayout.reading({ id: a.id, ...a.layout }, { id: b.id, ...b.layout }));
}
function dashTool(text, label, onclick) {
  return h("button", { type: "button", class: "ghost", title: label, "aria-label": label, onclick }, text);
}
/* in edit mode a panel offers only Edit and remove, laid over its header's corner on hover or focus (a tap focuses
   it), so nothing moves; its title moves it, its edges resize it, and the keyboard does both (dashKeydown) */
function dashCell(p) {
  const diagram = p.form === "diagram", panel = diagram ? diagramPanel(p) : chartPanel(p);   // (an address: the editor has no form for it)
  const edit = typeof openPanelEditor === "function" && !diagram ? dashTool("Edit", "Edit this panel", () => dashEditPanel(p.id)) : null;
  const tools = h("div", { class: "dash-tools" }, edit, dashTool("×", "Remove this panel", () => dashRemove(p.id)));
  const edge = (cls, sides, title) => h("span", { class: cls, "data-resize": sides, title });
  const el = h("section", { class: "dash-cell", "data-panel": p.id, tabindex: "0",
                            "aria-description": "Press Enter to move or resize it with the arrow keys" },
               tools, h("div", { class: "dash-body" }, panel),
               edge("dash-edge dash-edge-r", "r", "Drag to resize"), edge("dash-edge dash-edge-b", "b", "Drag to resize"),
               edge("dash-edge dash-handle", "rb", "Drag to resize"));
  return { el, panel, sig: dashSig(p), drawn: false, at: "" };
}
/* a row: a full-width line that opens and folds its panels; in editing, renamed, moved up or down, dragged, removed */
function dashRowCell(r, sig) {
  const n = r.panels?.length || 0;
  const toggle = h("button", { type: "button", class: "ghost dash-row-toggle", "data-act": "toggle", "aria-expanded": String(!r.collapsed),
                               title: r.collapsed ? "Open this row" : "Fold this row", onclick: () => dashRowToggle(r.id) },
                   r.collapsed ? "▸ " : "▾ ", DASH.editing ? null : h("span", { class: "dash-row-title" }, r.title),
                   r.collapsed ? h("span", { class: "muted small" }, ` ${n} panel${n === 1 ? "" : "s"}`) : null);
  const tools = DASH.editing ? [
    h("input", { class: "dash-row-input", value: r.title, "aria-label": "Row title", "data-act": "title",
                 onchange: (ev) => dashChange((d) => { dashRow(d, r.id).title = ev.target.value.trim().slice(0, DASH_LONGEST.title) || "Row"; }, "Row title changed") }),
    h("span", { class: "dash-gap" }),
    dashTool("↑", "Row up", () => dashRowShift(r.id, -1)), dashTool("↓", "Row down", () => dashRowShift(r.id, 1)),
    dashTool("×", "Remove this row (its panels stay)", () => dashRowRemove(r.id))] : [];
  const el = h("section", { class: "dash-cell dash-row", "data-panel": r.id, "aria-label": `Row: ${r.title}` },
               h("div", { class: "dash-row-bar" }, toggle, ...tools));
  return { el, panel: {}, sig, row: true, drawn: true, at: "" };
}
/* what the chart depends on: where it sits on the grid is not part of it */
function dashSig(p) {
  const { layout, size, tall, ...rest } = p;
  return JSON.stringify(rest);
}
const dashIsNarrow = () => matchMedia(DASH_NARROW).matches;
/* the arrangement as drawn at this width */
const dashNarrowed = (items) => DashLayout.stack([...items].sort(DashLayout.reading));
const dashShown = (d) => (dashIsNarrow() ? dashNarrowed(dashView(d).items) : dashView(d).items);
function dashPut(c, it) {
  const at = `${it.x},${it.y},${it.w},${it.h}`;
  if (c.at === at) return;
  c.at = at;
  for (const [k, v] of [["--x", it.x], ["--y", it.y], ["--w", it.w], ["--h", it.h]]) c.el.style.setProperty(k, v);
}
/* uPlot keeps where its plot is on the page; a panel that moved must tell it */
function dashPlotsMoved() {
  clearTimeout(DASH.settle);
  DASH.settle = setTimeout(() => dispatchEvent(new Event("scroll")), 240);
}
function dashPlaceDom(list) {
  const grid = DASH.grid;
  list.forEach((it, i) => {
    const el = DASH.cells.get(it.id).el;
    if (grid.children[i] === el) return;
    if (grid.moveBefore) grid.moveBefore(el, grid.children[i] || null);
    else grid.insertBefore(el, grid.children[i] || null);
  });
}
/* the cells made, kept or dropped to match the draft, and placed: a panel that only moved keeps its chart */
function dashDraw() {
  const d = DASH.draft, grid = DASH.grid;
  if (!d || !grid) return;
  if (DASH.drag) dashDragEnd(false);
  if (DASH.lifted) dashDrop(false);
  const focused = document.activeElement?.closest?.(".dash-cell")?.dataset.panel, act = document.activeElement?.dataset?.act;
  const view = dashView(d, dashItems(d), true), rows = d.rows || [];
  const ids = new Set([...view.panels.map((p) => p.id), ...rows.map((r) => r.id)]);
  for (const [id, c] of DASH.cells) if (!ids.has(id)) { c.panel.destroy?.(); c.el.remove(); DASH.cells.delete(id); }
  for (const r of rows) {                              // a row has no chart: made again when it changes
    const sig = JSON.stringify([r.title, r.collapsed, DASH.editing, r.panels?.length]), c = DASH.cells.get(r.id);
    if (c?.sig === sig) continue;
    const made = dashRowCell(r, sig);
    if (c) c.el.replaceWith(made.el); else grid.append(made.el);
    DASH.cells.set(r.id, made);
  }
  let fresh = false, copied = false;
  for (const p of view.panels) {
    const c = DASH.cells.get(p.id);
    if (!c) {
      const made = dashCell(p);
      DASH.cells.set(p.id, made);
      grid.append(made.el);
      made.panel.setState?.("loading");
      if (dashAsks(p)) fresh = true; else copied = true;
      continue;
    }
    const sig = dashSig(p);
    if (c.sig !== sig) {
      const asks = (x) => JSON.stringify(JSON.parse(x).queries);
      if (asks(c.sig) !== asks(sig) || JSON.parse(c.sig).repeat?.query !== p.repeat?.query) fresh = true;
      c.sig = sig;
      c.panel.setConfig?.(c.still ? { ...p, note: c.still } : p);
    }
  }
  const shown = dashIsNarrow() ? dashNarrowed(view.items) : view.items, by = new Map(view.panels.map((p) => [p.id, p]));
  for (const it of shown) {
    const c = DASH.cells.get(it.id), p = by.get(it.id);
    dashPut(c, it);
    if (!p) continue;
    c.el.classList.toggle("is-stat", p.form === "stat");
    c.el.classList.toggle("is-copy", !!p.copyOf);
    c.el.setAttribute("aria-label", p.title || "Panel");
  }
  dashPlaceDom(dashIsNarrow() ? shown : [...shown].sort(DashLayout.reading));
  grid.style.setProperty("--rows", DashLayout.height(shown));
  grid.classList.add("placed");
  grid.classList.toggle("editing", DASH.editing);
  const back = focused && DASH.cells.get(focused)?.el;
  if (back) (act && back.querySelector(`[data-act="${act}"]`) || back).focus({ preventScroll: true });
  dashPlotsMoved();
  if (fresh) dashRefresh();
  else if (copied) dashFeed();
}
/* an answer that does not come: the panels say late after a while and keep what they show; the request is then given
   up and asked again (by the poll, or once more when the page does not poll) */
const DASH_LATE = 8000, DASH_GIVE_UP = 25000, DASH_RETRY = 10000;
/* one bucket holding the whole window: the grid's buckets lie on multiples of their width, so a width is found with no
   multiple inside the window (and a margin, as the server's clock reads a moment later) */
function dashWholeBucket(since, until) {
  const most = 400 * 86400;                            // the longest bucket the query takes
  for (let step = Math.ceil((until - since) / 60) * 60; step <= most; step += 60)
    if (Math.floor(since / step) === Math.floor((until + 120) / step)) return step;
  return null;
}
function dashWithWhole(panels) {
  const until = S.at || nowS(), bucket = dashWholeBucket(until - WINDOWS[S.since], until);
  if (!bucket) return panels;
  return panels.map((p) => (p.display?.whole ? { ...p, queries: p.queries.map((q) => ({ ...q, bucket })) } : p));
}
/* how many are still in the state and how long they have been there, from the item list; left unsaid when the list is cut */
const DASH_STILL_MOST = 1000;
function dashStillWords(items, matched, at) {
  if (matched > items.length) return `still waiting: ${matched}`;
  if (!items.length) return "none still waiting";
  const ages = items.map((i) => at - i.entered).filter(Number.isFinite).sort((a, b) => a - b);
  if (!ages.length) return `still waiting: ${items.length}`;
  const mid = ages.length / 2, median = ages.length % 2 ? ages[Math.floor(mid)] : (ages[mid - 1] + ages[mid]) / 2;
  return `still waiting: ${items.length}, median age ${dur(median)}`;
}
async function dashStill(n) {
  for (const p of DASH.draft?.panels || []) {
    const still = p.display?.still, c = DASH.cells.get(p.id);
    if (!still || !c) continue;
    const got = await api("items", { kind: still.kind, state: still.state, n: DASH_STILL_MOST, alone: 1 }).catch(() => null);
    if (n !== DASH.asked || !got || !DASH.cells.has(p.id)) return;
    const note = dashStillWords((got.items || []).filter((i) => i.kind === still.kind && i.state === still.state),
                                got.total ?? got.matched?.[still.kind] ?? 0, S.at || nowS());
    if (note !== c.still) { c.still = note; c.panel.setConfig?.({ ...p, note }); }
  }
}
function dashAsk(panels, ctrl) {
  const gaveUp = new Promise((_, no) => ctrl.signal.addEventListener("abort", () => no(new DOMException("gave up", "AbortError")), { once: true }));
  return Promise.race([queryPanels(dashWithWhole(panels), { since: WINDOWS[S.since], until: S.at || null, signal: ctrl.signal }), gaveUp]);
}
/* an answer still to come is late (a panel with nothing drawn yet says it is still loading); only one that failed is an error */
function dashSayLate(words, failed = false) {
  for (const c of DASH.cells.values()) c.panel.setState?.(failed && !c.drawn ? "error" : "late", words);
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
    const got = await dashAsk(dashView(d).panels.filter(dashAsks), ctrl);
    if (n !== DASH.asked) return;
    DASH.got = got;
    let changed = false;                               // a repeated panel's values, as its query now answers
    for (const p of d.panels.filter((x) => x.repeat?.query)) {
      const names = (got?.get?.(p.id)?.results || []).filter((r) => String(r.id) === p.repeat.query)
        .flatMap((r) => (r.series || []).map((x) => String(x.name)));
      const values = [...new Set(names)].slice(0, DASH_REPEAT_MOST);
      if (values.join("\u0000") !== (DASH.values.get(p.id) || []).join("\u0000")) { DASH.values.set(p.id, values); changed = true; }
    }
    if (changed) dashDraw();
    dashFeed();
    if (DASH.said) DASH.said.textContent = `Updated ${clock(nowS())}`;
    dashStill(n);
  } catch (e) {
    if (n !== DASH.asked) return;
    const timedOut = e?.name === "AbortError";
    dashSayLate(timedOut ? `no answer in ${dur(DASH_GIVE_UP / 1000)}; asking again` : "The server did not answer", !timedOut);
    if (DASH.said) DASH.said.textContent = timedOut ? "No answer; asking again" : "Could not refresh; asking again";
    if (!DASH.timer) DASH.retry = setTimeout(() => { if (DASH.grid?.isConnected && !document.hidden) dashRefresh(); }, DASH_RETRY);
  } finally {
    clearTimeout(late);
    clearTimeout(giveUp);
    if (DASH.flight === ctrl) DASH.flight = null;
  }
}
/* the last answers, given to each panel drawn; a copy of a panel repeated by its query's label reads its source's */
function dashFeed() {
  const got = DASH.got, d = DASH.draft;
  if (!got?.get || !d) return;
  for (const p of dashView(d).panels) {
    const c = DASH.cells.get(p.id), byLabel = !!p.repeat?.query, a = got.get(byLabel ? p.copyOf || p.id : p.id);
    if (!c || !a) continue;
    const answer = dashAnswer(p, byLabel ? dashPick(a.results, p.repeat.query, p.value) : a.results, a.meta);
    c.el.classList.toggle("dash-no-change", dashStartsNearZero(answer));
    c.panel.update(answer, a.meta);
    c.drawn = true;
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
  dashSettle();
  dashRemember();
  const d = dashboardDraft();
  fn(d);
  saveDashboardDraft(d);
  if (said) dashAnnounce(said);
}
const dashIndex = (id) => DASH.draft.panels.findIndex((p) => p.id === id);
const dashTitle = (p) => p.title || "Panel";
/* a column or a line over: what it then covers goes down, nothing else moves */
function dashNudge(id, dx, dy) {
  dashSettle();
  const p = DASH.draft.panels[dashIndex(id)];
  if (!p) return;
  const next = DashLayout.move(dashItems(DASH.draft), id, { x: p.layout.x + dx, y: p.layout.y + dy }), it = next.find((x) => x.id === id);
  if (it.x === p.layout.x && it.y === p.layout.y) { dashAnnounce(`${dashTitle(p)}: can go no further that way`); return; }
  dashChange((d) => dashWrite(d, next), dashSays(p, it));
}
function dashResizeTo(d, id, size) {
  const p = d.panels[d.panels.findIndex((x) => x.id === id)];
  dashWrite(d, DashLayout.resize(dashItems(d), id, size));
  return p;
}
/* rows: folded (their panels kept in them, what is below closing up) and opened again, moved up or down a row with
   their panels, added at the bottom, removed (their panels stay, under the row above) */
function dashUnfold(d, row) {
  const next = DashLayout.unfold(dashItems(d), row.id, row.panels.map((p) => ({ id: p.id, ...p.layout })), row.span);
  d.panels.push(...row.panels);
  row.collapsed = false;
  delete row.panels;
  delete row.span;
  dashWrite(d, next);
}
function dashRowToggle(id) {
  const r = dashRow(DASH.draft, id);
  if (!r) return;
  dashChange((d) => {
    const row = dashRow(d, id);
    if (row.collapsed) { dashUnfold(d, row); return; }
    const f = DashLayout.fold(dashItems(d), id), rel = new Map(f.hidden.map((x) => [x.id, x]));
    row.panels = d.panels.filter((p) => rel.has(p.id)).map((p) => { const { x, y, w, h: hi } = rel.get(p.id); return { ...p, layout: { x, y, w, h: hi } }; });
    d.panels = d.panels.filter((p) => !rel.has(p.id));
    row.collapsed = true;
    row.span = f.span;
    dashWrite(d, f.items);
  }, `${r.title}: ${r.collapsed ? "opened" : "folded"}`);
}
function dashRowShift(id, by) {
  const rows = [...(DASH.draft.rows || [])].sort((a, b) => a.layout.y - b.layout.y), i = rows.findIndex((r) => r.id === id);
  if (i < 0 || i + by < 0 || i + by >= rows.length) { dashAnnounce("The row can go no further that way"); return; }
  dashChange((d) => dashWrite(d, DashLayout.moveRow(dashItems(d), id, i + by)), `${rows[i].title}: row ${i + by + 1} of ${rows.length}`);
}
function dashRowRemove(id) {
  const r = dashRow(DASH.draft, id);
  if (!r) return;
  dashChange((d) => {
    const row = dashRow(d, id);
    if (row.collapsed) dashUnfold(d, row);
    d.rows = d.rows.filter((x) => x.id !== id);
  }, `${r.title}: row removed`);
  DASH.head?.querySelector(".dash-add-row")?.focus();
}
function dashAddRow() {
  const d = DASH.draft;
  if ((d.rows || []).length >= DASH_ROWS) return;
  const taken = new Set([...d.panels, ...(d.rows || []), ...(d.rows || []).flatMap((r) => r.panels || [])].map((x) => x.id));
  let n = (d.rows || []).length + 1;
  while (taken.has(`row${n}`)) n++;
  dashChange((x) => { x.rows = [...(x.rows || []), { id: `row${n}`, title: "Row", collapsed: false }]; }, "Row added at the bottom");
  DASH.cells.get(`row${n}`)?.el.querySelector("input, button")?.focus();
}
function dashResize(id, by) {
  const p = DASH.draft.panels[dashIndex(id)];
  const size = p && DASH_SIZES[DASH_SIZES.indexOf(p.size) + by];
  if (!size) return;
  dashChange((d) => dashResizeTo(d, id, { w: DASH_COLUMNS[size] }), `${dashTitle(p)}: ${DASH_COLUMNS[size]} of 12 columns`);
}
function dashTall(id, tall = null) {
  const p = DASH.draft.panels[dashIndex(id)];
  if (!p) return;
  const to = tall ?? !p.tall;
  if (to === p.tall) return;
  dashChange((d) => dashResizeTo(d, id, { h: dashRows(p) * (to ? 2 : 1) }), `${dashTitle(p)}: ${to ? "tall" : "short"}`);
}
function dashRemove(id) {
  const i = dashIndex(id), ps = DASH.draft.panels;
  if (i < 0) return;
  const next = ps[i + 1]?.id || ps[i - 1]?.id;
  dashChange((d) => d.panels.splice(i, 1), `${dashTitle(ps[i])}: removed`);
  const to = next && DASH.cells.get(next)?.el;
  (to || DASH.head?.querySelector(".dash-add") || DASH.head?.querySelector(".dash-edit"))?.focus();
}
const dashSays = (p, it) => `${dashTitle(p)}: column ${it.x + 1}, row ${it.y + 1}, ${it.w} columns wide, ${it.h} rows high`;
/* an arrangement shown while it is worked out: on a desktop, ``items`` are the draft's, shown with their copies */
function dashShowItems(items, held = null) {
  if (!dashIsNarrow()) items = dashView(DASH.draft, items).items;
  for (const it of items) {
    const c = DASH.cells.get(it.id);
    if (c) dashPut(c, it);
    if (it.id === held && DASH.slot) for (const [k, v] of [["--x", it.x], ["--y", it.y], ["--w", it.w], ["--h", it.h]]) DASH.slot.style.setProperty(k, v);
  }
  DASH.grid.style.setProperty("--rows", DashLayout.height(items) + (DASH.drag ? DASH.drag.room : 0));
}
/* a finished arrangement goes into the draft, as one Undo; ``order`` is a phone's new reading order, its panels then
   taking the places held in reading order (with the heights the phone gave them) */
function dashCommit(id, items, order) {
  const was = dashItems(DASH.draft), high = new Map(items.map((x) => [x.id, x.h]));
  const next = order ? DashLayout.reorder(was.map((x) => (!x.row && high.has(x.id) ? { ...x, h: high.get(x.id) } : x)), order) : items;
  const key = (list) => JSON.stringify(list.filter((x) => was.some((w) => w.id === x.id)).map(({ id: i, x, y, w, h: hi }) => [i, x, y, w, hi])
    .sort((a, b) => (a[0] < b[0] ? -1 : 1)));
  if (key(next) === key(was)) { dashDraw(); return false; }
  dashChange((d) => dashWrite(d, next));
  return true;
}

/* by keyboard: Enter lifts the panel, the arrows move it, Shift and the arrows resize it, Enter puts it down, Escape undoes */
function dashLift(id) {
  const c = DASH.cells.get(id), p = DASH.draft.panels[dashIndex(id)];
  if (!c || !p) return;
  dashSettle();
  const start = dashIsNarrow() ? dashShown(DASH.draft) : dashItems(DASH.draft);
  DASH.lifted = { id, start, now: start, order: start.map((x) => x.id) };
  c.el.classList.add("is-lifted");
  c.el.setAttribute("aria-grabbed", "true");
  dashAnnounce(`${dashTitle(p)} lifted. Arrow keys move it, Shift and arrow keys resize it, Enter puts it down, Escape cancels.`);
}
function dashDrop(keep) {
  const l = DASH.lifted;
  if (!l) return;
  DASH.lifted = null;
  const c = DASH.cells.get(l.id), p = DASH.draft.panels[dashIndex(l.id)];
  c?.el.classList.remove("is-lifted");
  c?.el.removeAttribute("aria-grabbed");
  if (!p) return;
  if (keep) {
    const it = l.now.find((x) => x.id === l.id);
    dashCommit(l.id, l.now, dashIsNarrow() ? l.order : null);
    dashAnnounce(`${dashSays(p, it)}. Put down.`);
  } else {
    dashShowItems(l.start);
    dashAnnounce(`${dashTitle(p)}: move cancelled`);
  }
  DASH.cells.get(l.id)?.el.focus({ preventScroll: true });
}
function dashLiftedKey(key, shift) {
  const l = DASH.lifted, p = DASH.draft.panels[dashIndex(l.id)], at = l.now.find((x) => x.id === l.id);
  const dx = { ArrowLeft: -1, ArrowRight: 1 }[key] || 0, dy = { ArrowUp: -1, ArrowDown: 1 }[key] || 0;
  let next = null;
  if (dashIsNarrow()) {
    if (shift) { if (dy) next = DashLayout.stack(l.now.map((x) => (x.id === l.id ? { ...x, h: Math.max(DashLayout.MIN_H, x.h + dy) } : x))); }
    else if (dy) {
      const i = l.order.indexOf(l.id), j = i + dy;
      if (j >= 0 && j < l.order.length) {
        l.order.splice(j, 0, l.order.splice(i, 1)[0]);
        const by = new Map(l.now.map((x) => [x.id, x]));
        next = DashLayout.stack(l.order.map((id) => by.get(id)));
      }
    }
  } else if (shift) next = DashLayout.resize(l.now, l.id, { w: at.w + dx, h: at.h + dy });
  else if (dx) next = DashLayout.move(l.now, l.id, { x: at.x + dx, y: at.y });
  else if (dy && at.y + dy >= 0) next = DashLayout.move(l.now, l.id, { x: at.x, y: at.y + dy });
  const to = next?.find((x) => x.id === l.id);
  if (!to || (to.x === at.x && to.y === at.y && to.w === at.w && to.h === at.h && (!dashIsNarrow() || shift))) {
    if (!dashIsNarrow() || !next) { dashAnnounce(`${dashTitle(p)}: can go no further that way`); return; }
  }
  l.now = next;
  dashShowItems(next);
  dashAnnounce(dashIsNarrow() && !shift ? `${dashTitle(p)}: place ${l.order.indexOf(l.id) + 1} of ${l.order.length}` : dashSays(p, to));
}
function dashKeydown(ev) {
  if (/^(INPUT|SELECT|TEXTAREA)$/.test(ev.target.tagName)) return;
  const id = ev.target.closest?.(".dash-cell")?.dataset.panel;
  if (!id || dashIndex(id) < 0) return;                            // a row, or a repeated panel's copy
  const onCell = ev.target.classList.contains("dash-cell");
  const isArrow = ev.key in { ArrowLeft: 1, ArrowUp: 1, ArrowRight: 1, ArrowDown: 1 };
  if (DASH.lifted?.id === id) {
    if (isArrow) dashLiftedKey(ev.key, ev.shiftKey);
    else if (ev.key === "Enter" || ev.key === " ") dashDrop(true);
    else if (ev.key === "Escape") dashDrop(false);
    else if (ev.key === "Tab") { dashDrop(true); return; }
    else return;
    ev.preventDefault();
    return;
  }
  if (onCell && (ev.key === "Enter" || ev.key === " ")) { dashLift(id); ev.preventDefault(); return; }
  if (!DASH.editing) return;
  const arrow = { ArrowLeft: -1, ArrowUp: -1, ArrowRight: 1, ArrowDown: 1 }[ev.key];
  if ((ev.key === "Delete" || ev.key === "Backspace") && onCell) dashRemove(id);
  else if (arrow && ev.altKey && ev.shiftKey) {
    if (ev.key === "ArrowUp" || ev.key === "ArrowDown") dashTall(id, ev.key === "ArrowDown");
    else dashResize(id, arrow);
  } else if (arrow && ev.altKey) dashNudge(id, ev.key === "ArrowUp" || ev.key === "ArrowDown" ? 0 : arrow, ev.key === "ArrowUp" || ev.key === "ArrowDown" ? arrow : 0);
  else return;
  ev.preventDefault();
}

/* by pointer: a header moves the panel, an edge or corner resizes it. Worked out once a frame, always from where the
   drag began, so a drag can be undone by moving back and Escape puts everything back */
const DASH_HOLD = 220, DASH_NUDGE = 4, DASH_SLIP = 8, DASH_EDGE = 56, DASH_SCROLL = 18;
function dashUnits() {
  const cs = getComputedStyle(DASH.grid), gap = parseFloat(cs.rowGap) || 8, row = parseFloat(cs.gridAutoRows) || 32;
  const r = DASH.grid.getBoundingClientRect();
  return { r, gap, col: (r.width + gap) / DashLayout.COLS, row: row + gap };
}
function dashScroller() {
  for (let e = DASH.grid; e; e = e.parentElement) {
    const o = getComputedStyle(e).overflowY;
    if ((o === "auto" || o === "scroll") && e.scrollHeight > e.clientHeight) return e;
  }
  return document.scrollingElement;
}
function dashPointerDown(ev) {
  if (ev.button !== 0 || DASH.drag || DASH.pending) return;
  const edge = ev.target.closest?.("[data-resize]");
  const head = !edge && ev.target.closest?.(".panel-head, .dash-row-bar");   // a panel moves by its title, a row by its bar
  if (!edge && !head) return;
  if (!edge && ev.target.closest("button, a, input, select, textarea, label, [role=button]")) return;
  const el = ev.target.closest(".dash-cell"), id = el?.dataset.panel;
  if (!id || el.classList.contains("is-copy") || (el.classList.contains("dash-row") && dashIsNarrow())) return;
  const sides = edge?.dataset.resize || null;
  const held = ev.pointerType === "touch" && !edge;                // on a phone a header also scrolls the page: hold to lift
  const pend = { id, sides, pointer: ev.pointerId, x0: ev.clientX, y0: ev.clientY, x: ev.clientX, y: ev.clientY, timer: 0 };
  const begin = () => { dashPendEnd(); dashDragBegin(pend); };
  const move = (e) => {
    if (e.pointerId !== pend.pointer) return;
    pend.x = e.clientX; pend.y = e.clientY;
    const far = Math.hypot(e.clientX - pend.x0, e.clientY - pend.y0);
    if (held ? far > DASH_SLIP : far >= DASH_NUDGE) { if (held) dashPendEnd(); else begin(); }
  };
  const stop = (e) => { if (e.pointerId === pend.pointer) dashPendEnd(); };
  pend.off = () => {
    removeEventListener("pointermove", move);
    removeEventListener("pointerup", stop);
    removeEventListener("pointercancel", stop);
    clearTimeout(pend.timer);
  };
  DASH.pending = pend;
  addEventListener("pointermove", move);
  addEventListener("pointerup", stop);
  addEventListener("pointercancel", stop);
  if (held) pend.timer = setTimeout(begin, DASH_HOLD);
  else ev.preventDefault();                                        // no text selection starts from a header or edge
}
function dashPendEnd() {
  DASH.pending?.off();
  DASH.pending = null;
}
function dashDragBegin(pend) {
  const { id, sides } = pend, c = DASH.cells.get(id);
  if (!c || !DASH.draft) return;
  if (DASH.lifted) dashDrop(true);
  dashSettle();
  const narrow = dashIsNarrow(), start = narrow ? dashShown(DASH.draft) : dashItems(DASH.draft), me = start.find((x) => x.id === id), u = dashUnits();
  if (!me) return;
  const box = c.el.getBoundingClientRect();
  const g = DASH.drag = { id, sides, narrow, start, now: start, me, pointer: pend.pointer, x: pend.x, y: pend.y, raf: 0, key: "",
                          grabX: pend.x0 - box.left, grabY: pend.y0 - box.top, boxW: box.width, boxH: box.height,
                          order: start.map((x) => x.id), room: me.h + 2, cell: c, x0: pend.x0, y0: pend.y0,
                          scrollAt: 0 };
  const scroller = dashScroller();
  g.scroller = scroller;
  g.scroll0 = scroller.scrollTop;
  DASH.slot = h("div", { class: "dash-slot", "aria-hidden": "true" });
  for (const [k, v] of [["--x", me.x], ["--y", me.y], ["--w", me.w], ["--h", me.h]]) DASH.slot.style.setProperty(k, v);
  DASH.grid.append(DASH.slot);
  DASH.grid.classList.add("dragging");
  document.documentElement.classList.add(sides ? "dash-sizing" : "dash-moving");
  if (sides) document.documentElement.dataset.dashSides = sides;
  c.el.classList.add("is-held");
  c.el.style.width = `${box.width}px`;
  c.el.style.height = `${box.height}px`;
  if (sides) dashFreezeBody(g, box.width, box.height);
  else c.el.style.transform = `translate(${box.left - u.r.left}px, ${box.top - u.r.top}px)`;
  g.move = (e) => { if (e.pointerId !== g.pointer) return; g.x = e.clientX; g.y = e.clientY; dashDragFrame(); };
  g.up = (e) => { if (e.pointerId === g.pointer) dashDragEnd(true); };
  g.cancel = (e) => { if (e.pointerId === g.pointer) dashDragEnd(false); };
  g.key_ = (e) => { if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); dashDragEnd(false); dashAnnounce("Move cancelled"); } };
  g.touch = (e) => { if (e.cancelable) e.preventDefault(); };      // the page must not scroll under a lifted panel
  addEventListener("pointermove", g.move);
  addEventListener("pointerup", g.up);
  addEventListener("pointercancel", g.cancel);
  addEventListener("keydown", g.key_, true);
  addEventListener("touchmove", g.touch, { passive: false });
  dashDragFrame();
}
/* the chart keeps its size between grid steps, so a resize redraws it only when the snapped size changes */
function dashFreezeBody(g, w, hi) {
  const body = g.cell.el.querySelector(".dash-body");
  body.style.flex = "none";
  body.style.width = `${w}px`;
  body.style.height = `${Math.max(0, hi - (g.cell.el.offsetHeight - body.offsetHeight))}px`;
}
function dashDragFrame() {
  const g = DASH.drag;
  if (g && !g.raf) g.raf = requestAnimationFrame(dashDragTick);
}
function dashAutoScroll(g) {
  const s = g.scroller, whole = s === document.scrollingElement;
  const top = whole ? 0 : s.getBoundingClientRect().top, bottom = whole ? innerHeight : s.getBoundingClientRect().bottom;
  const up = top + DASH_EDGE - g.y, down = g.y - (bottom - DASH_EDGE);
  const by = up > 0 ? -Math.ceil(DASH_SCROLL * Math.min(1, up / DASH_EDGE)) : down > 0 ? Math.ceil(DASH_SCROLL * Math.min(1, down / DASH_EDGE)) : 0;
  if (!by) return false;
  const was = s.scrollTop;
  s.scrollTop = was + by;
  return s.scrollTop !== was;
}
function dashDragTick() {
  const g = DASH.drag;
  if (!g) return;
  g.raf = 0;
  const scrolled = dashAutoScroll(g), u = dashUnits();
  if (g.sides) dashSizeFrame(g, u);
  else dashMoveFrame(g, u);
  if (scrolled) dashDragFrame();
}
function dashMoveFrame(g, u) {
  const px = g.x - u.r.left - g.grabX, py = g.y - u.r.top - g.grabY;
  g.cell.el.style.transform = `translate(${g.narrow ? 0 : px}px, ${py}px)`;
  if (g.narrow) {
    const others = g.order.filter((id) => id !== g.id), by = new Map(g.start.map((x) => [x.id, x]));
    const middle = (py + g.boxH / 2) / u.row;
    let at = 0, y = 0;
    for (const id of others) {
      const hi = by.get(id).h;
      if (middle > y + hi / 2) at++;
      y += hi;
    }
    const order = [...others.slice(0, at), g.id, ...others.slice(at)], key = order.join();
    if (key === g.key) return;
    g.key = key;
    g.now = DashLayout.stack(order.map((id) => by.get(id)));
    g.newOrder = order;
    dashShowItems(g.now, g.id);
    dashAnnounce(`${dashTitle(DASH.draft.panels[dashIndex(g.id)])}: place ${at + 1} of ${order.length}`);
    return;
  }
  const to = { x: Math.round(px / u.col), y: Math.max(0, Math.round(py / u.row)) };
  if (g.me.row) {                                                    // a row goes, with its panels, among the other rows
    const index = g.start.filter((x) => x.row && x.id !== g.id && x.y < to.y).length, key = `row ${index}`;
    if (key === g.key) return;
    g.key = key;
    g.now = DashLayout.moveRow(g.start, g.id, index);
    dashShowItems(g.now, g.id);
    dashAnnounce(`${dashRow(DASH.draft, g.id)?.title || "Row"}: row ${index + 1}`);
    return;
  }
  const key = `${to.x},${to.y}`;
  if (key === g.key) return;
  g.key = key;
  g.now = DashLayout.move(g.start, g.id, to);
  dashShowItems(g.now, g.id);
  const it = g.now.find((x) => x.id === g.id);
  dashAnnounce(dashSays(DASH.draft.panels[dashIndex(g.id)], it));
}
function dashSizeFrame(g, u) {
  const dx = g.sides.includes("r") && !g.narrow ? g.x - g.x0 : 0, dy = g.sides.includes("b") ? g.y - g.y0 + (g.scroller.scrollTop - g.scroll0) : 0;
  const pxW = Math.max(u.col * DashLayout.MIN_W - u.gap, Math.min(u.r.right - (u.r.left + g.me.x * u.col), g.boxW + dx));
  const pxH = Math.max(u.row * DashLayout.MIN_H - u.gap, g.boxH + dy);
  g.cell.el.style.width = `${pxW}px`;
  g.cell.el.style.height = `${pxH}px`;
  const w = g.narrow ? g.me.w : Math.round((pxW + u.gap) / u.col), hi = Math.round((pxH + u.gap) / u.row);
  const key = `${w},${hi}`;
  if (key === g.key) return;
  g.key = key;
  if (g.narrow) {
    const by = new Map(g.start.map((x) => [x.id, x]));
    g.now = DashLayout.stack(g.order.map((id) => (id === g.id ? { ...by.get(id), h: hi } : by.get(id))));
  } else g.now = DashLayout.resize(g.start, g.id, { w, h: hi });
  dashShowItems(g.now, g.id);
  const it = g.now.find((x) => x.id === g.id);
  dashFreezeBody(g, it.w * u.col - u.gap, it.h * u.row - u.gap);
  dashAnnounce(dashSays(DASH.draft.panels[dashIndex(g.id)], it));
}
function dashDragEnd(keep) {
  const g = DASH.drag;
  if (!g) return;
  if (g.raf) cancelAnimationFrame(g.raf);
  if (keep) { g.raf = 0; if (g.sides) dashSizeFrame(g, dashUnits()); else dashMoveFrame(g, dashUnits()); }
  removeEventListener("pointermove", g.move);
  removeEventListener("pointerup", g.up);
  removeEventListener("pointercancel", g.cancel);
  removeEventListener("keydown", g.key_, true);
  removeEventListener("touchmove", g.touch);
  DASH.drag = null;
  DASH.slot?.remove();
  DASH.slot = null;
  DASH.grid?.classList.remove("dragging");
  document.documentElement.classList.remove("dash-moving", "dash-sizing");
  delete document.documentElement.dataset.dashSides;
  const el = g.cell.el, body = el.querySelector(".dash-body");
  el.classList.remove("is-held");
  for (const k of ["transform", "width", "height"]) el.style.removeProperty(k);
  for (const k of ["flex", "width", "height"]) body?.style.removeProperty(k);       // (a row has no body)
  if (!DASH.grid) return;
  if (keep) {
    const order = g.narrow ? (g.newOrder || g.order) : null;
    if (dashCommit(g.id, g.now, order)) {
      const p = DASH.draft.panels[dashIndex(g.id)], it = dashShown(DASH.draft).find((x) => x.id === g.id);
      if (p && it) dashAnnounce(`${dashSays(p, it)}. Put down.`);
    }
    dashHead();
  } else dashDraw();
  dashPlotsMoved();
}
function dashEditPanel(id) {
  const p = DASH.draft.panels[dashIndex(id)];
  if (!p || typeof openPanelEditor !== "function") return;
  const back = () => DASH.cells.get(id)?.el.focus();
  openPanelEditor(JSON.parse(JSON.stringify(p)), {
    onChange: () => {},
    onSave: (config) => {
      dashChange((d) => {
        const i = d.panels.findIndex((x) => x.id === id), was = d.panels[i];
        d.panels[i] = { ...config, id, layout: was.layout, size: was.size, tall: was.tall };
        const w = config.size !== was.size ? DASH_COLUMNS[config.size] : was.layout.w;
        const hi = !!config.tall !== was.tall ? dashRows(config) * (config.tall ? 2 : 1) : was.layout.h;
        if (w !== was.layout.w || hi !== was.layout.h) dashResizeTo(d, id, { w, h: hi, x: Math.min(was.layout.x, DashLayout.COLS - w) });
      }, `${config.title || "Panel"}: changed`);
      back();
    },
    onCancel: back,
  });
}
function dashAddPanel() {
  if (typeof openPanelEditor !== "function" || dashHeld(DASH.draft) >= DASH_MOST) return;
  const taken = new Set([...DASH.draft.panels, ...(DASH.draft.rows || []), ...(DASH.draft.rows || []).flatMap((r) => r.panels || [])].map((p) => p.id));
  let n = DASH.draft.panels.length + 1;
  while (taken.has(`p${n}`)) n++;
  const id = `p${n}`, back = () => DASH.head?.querySelector(".dash-add")?.focus();
  openPanelEditor({ id, title: "New panel", note: "", form: "line", queries: [], display: { legend: "right" }, size: "m", tall: false }, {
    onChange: () => {},
    onSave: (config) => {
      dashChange((d) => { const { layout, ...fresh } = config; d.panels.push({ ...fresh, id }); }, `${config.title || "Panel"}: added`);
      DASH.cells.get(id)?.el.focus();
    },
    onCancel: back,
  });
}
async function dashCopy() {
  if (!dashFitsLink(DASH.draft)) {
    if (DASH.said) DASH.said.textContent = DASH_TOO_LONG;
    dashAnnounce(DASH_TOO_LONG);
    return;
  }
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
/* Keep: the draft sent to the server, which works out the dashboards: entry and files it as a display change; it is
   written only when the owner accepts it under Changes to review (nothing is written here) */
async function dashKeep() {
  DASH.said.textContent = "Keeping…";
  try {
    const got = await apiSend("propose?keep=dashboard", DASH.draft), name = String(got.target || "").replace(/^dashboard\./, "");
    DASH.said.replaceChildren("Kept as a change for you to accept in ", h("a", { href: "/model#review-queue" }, "Changes to review"),
      "; once accepted it is ", h("a", { href: `/dashboard?name=${encodeURIComponent(name)}` }, `the dashboard ${name}`));
    dashAnnounce("Kept as a change to review");
  } catch (e) {
    DASH.said.textContent = `Not kept: ${e.message || e}`;
    dashAnnounce(DASH.said.textContent);
  }
}
/* a declared dashboard's own panels (dashboards:, kind query) as a draft the page draws; null when it has none */
function dashDeclared(got) {
  const panels = (got?.panels || []).map((x) => x.panel).filter((x) => x?.panel === "query").map((x, i) => ({ ...x, id: `p${i + 1}`,
    size: String(x.size || "m").replace(/-tall$/, ""), tall: /-tall$/.test(x.size || ""), display: x.display || {} }));
  return panels.length ? dashClean({ title: got.title || got.name, since: Object.keys(WINDOWS).find((k) => WINDOWS[k] === got.window) || null, panels }) : null;
}
function dashUndo() {
  const last = DASH.undo[DASH.undo.length - 1];
  if (!last) return;
  DASH.undo = DASH.undo.slice(0, -1);
  DASH.room.clear();                                   // the rooms were the later arrangement's
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
    DASH.room.clear();
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
    DASH.editing && canEdit ? h("button", { type: "button", class: "dash-add", disabled: dashHeld(d) >= DASH_MOST ? "" : null, onclick: dashAddPanel }, "Add panel") : null,
    DASH.editing ? h("button", { type: "button", class: "dash-add-row", disabled: (d.rows || []).length >= DASH_ROWS ? "" : null, onclick: dashAddRow,
                                 title: "A titled line across the dashboard: the panels under it are its own" }, "Add row") : null,
    DASH.editing ? h("button", { type: "button", disabled: DASH.undo.length ? null : "", onclick: dashUndo }, "Undo") : null,
    DASH.editing && DASH.kept ? h("button", { type: "button", onclick: dashReset, title: "Drop this draft and go back to the default" }, "Reset") : null,
    refresh,
    h("button", { type: "button", onclick: dashCopy, title: "Copy a link to this dashboard" }, "Copy link"),
    DASH.kept && !DASH.declared && !SNAP ? h("button", { type: "button", class: "dash-keep", onclick: dashKeep,
      title: "Propose this draft as one of the model's dashboards: it is written when you accept it" }, "Keep") : null,
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
    dashPendEnd();
    if (DASH.drag) dashDragEnd(false);
    DASH.lifted = null;
    clearTimeout(DASH.settle);
    for (const c of DASH.cells.values()) c.panel.destroy?.();
    DASH.cells.clear();
    DASH.narrow?.removeEventListener("change", dashDraw);
    DASH.grid = null;
  } };
}
async function pageDashboard(main, q) {
  const stayed = DASH.wasHere, n = ++DASH.page;
  DASH.wasHere = false;
  if (!stayed) { DASH.editing = false; DASH.undo = []; DASH.values.clear(); DASH.room.clear(); }
  DASH.got = null;
  S.timer = dashLeave(n);
  const p = h("div", { class: "page dash" });
  const notice = h("p", { class: "note", hidden: "" });
  DASH.head = h("header", { class: "dash-head" }, h("h1", {}, "Dashboard"));
  DASH.said = h("span", { class: "muted small dash-said" });
  DASH.live = h("div", { class: "dash-live", role: "status", "aria-live": "polite" });
  DASH.grid = h("div", { class: "dash-grid", onkeydown: dashKeydown, onpointerdown: dashPointerDown,
                         oncontextmenu: (ev) => { if (DASH.pending || DASH.drag) ev.preventDefault(); },
                         onfocusout: (ev) => { if (DASH.lifted && !ev.relatedTarget?.closest?.(`[data-panel="${DASH.lifted.id}"]`) && document.hasFocus()) dashDrop(true); } }, h("p", { class: "muted page-loading" }, "Loading…"));
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
  DASH.declared = null;
  const named = q.get("name");
  if (!d && named) {                                   // a dashboard the model declares (dashboards:), drawn as one
    const got = await api(`dashboard/${encodeURIComponent(named)}`).catch(() => null);
    if (n !== DASH.page) return;
    d = dashDeclared(got);
    if (d) DASH.declared = named;
    else { notice.hidden = false; notice.textContent = `The model declares no dashboard ${named} of the page's own panels, so this is the one kept here.`; }
  }
  d ||= dashStored();
  DASH.kept = !!d && !DASH.declared;
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
  if (moved) replaceRoute(DASH.declared ? `/dashboard?${new URLSearchParams({ name: DASH.declared, since })}` : dashAddress(DASH.kept ? d : null, since));
  // a link opened is only shown: what this browser keeps changes when the reader changes something
  if (moved && DASH.kept && !fromAddress) try { localStorage.setItem(dashKey(), JSON.stringify(d)); } catch (e) { /* in the address */ }
  DASH.grid.replaceChildren();
  DASH.narrow = matchMedia(DASH_NARROW);
  DASH.narrow.addEventListener("change", dashDraw);
  dashHead();
  if (!d.panels.length && !d.rows?.length) {
    DASH.grid.append(h("p", { class: "note dash-empty" }, "Nothing is recorded to chart yet. Panels appear here once the model has items or series."));
    return;
  }
  dashDraw();
  dashPoll();
}
