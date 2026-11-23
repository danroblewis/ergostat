/* The Dashboard: a grid of panels, kept as a draft in the address and in this browser. Nothing is written to the
   server. The panels themselves (chartPanel, queryPanels, queryFields) are panels.js's; the editor is
   panel-editor.js's, used when it is there. */
"use strict";

const DASH_COLUMNS = { s: 4, m: 6, l: 8, full: 12 };
const DASH_SIZES = Object.keys(DASH_COLUMNS);
const DASH_MOST = 24;                                  // panels on one dashboard (docs/proposals/dashboard.md, section 6)
const DASH_NARROW = "(max-width: 699px)";
const DASH_EVERY = { Off: 0, "10s": 10000, "30s": 30000, "1m": 60000, "5m": 300000 };
const DASH_WINDOW = "1d";                              // what a dashboard with no window of its own opens on
const DASH = { draft: null, kept: false, editing: false, cells: new Map(), undo: [], timer: null, wasHere: false,
               since: null, grid: null, head: null, live: null, said: null, page: 0, asked: 0, narrow: null };

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
  if (!d || typeof d !== "object" || !Array.isArray(d.panels)) return null;
  const seen = new Set();
  const panels = d.panels.filter((p) => p && typeof p === "object" && !Array.isArray(p)).slice(0, DASH_MOST).map((p) => {
    let id = typeof p.id === "string" && p.id ? p.id : "p";
    for (let n = 2; seen.has(id); n++) id = `${p.id || "p"}-${n}`;
    seen.add(id);
    return { ...p, id, title: String(p.title ?? ""), queries: Array.isArray(p.queries) ? p.queries : [],
             size: DASH_COLUMNS[p.size] ? p.size : "m", tall: !!p.tall };
  });
  return { title: String(d.title || "Dashboard"), since: WINDOWS[d.since] ? d.since : null, panels };
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

const DASH_COST = /cost|spend/i, DASH_MONEY = /^(usd|eur|gbp|\$)/i;
const DASH_NOT_CHARTED = /(^|[._-])(id|ids|rank|seq|index|order|priority|number|at|ts|time|timestamp|epoch)$/i;
const dashIsCost = (f) => DASH_COST.test(f.name) || DASH_MONEY.test(f.unit || "");

/* the kinds, those holding the most first: a kind with work open before one that only holds finished work, and
   ergostat's own bookkeeping last. ``flows`` is /api/items-flow's answer for each kind, or nothing */
function dashKinds(fields, flows = {}) {
  const kinds = Object.entries(fields?.sources?.items?.kinds || {}).map(([name, k]) => {
    const states = k.states || [], fl = flows[name] || null, now = fl?.now || {};
    const done = (fl?.finished_states || states.slice(-1)).filter((x) => states.includes(x));
    const open = states.filter((x) => !done.includes(x));
    const most = (list) => [...list].sort((a, b) => (now[b] || 0) - (now[a] || 0))[0] || null;
    const held = states.reduce((n, x) => n + (now[x] || 0), 0), inWork = open.reduce((n, x) => n + (now[x] || 0), 0);
    return { name, states, open, done, held, inWork, busiest: most(open), finish: most(done), fields: k.fields || [] };
  }).filter((k) => k.states.length);
  const own = (k) => (k.name.startsWith("ergostat.") ? 1 : 0);
  kinds.sort((a, b) => own(a) - own(b) || (b.inWork > 0) - (a.inWork > 0) || b.held - a.held || a.name.localeCompare(b.name));
  return kinds.some((k) => k.held) ? kinds.filter((k) => k.held) : kinds;
}
const dashRate = { agg: "count", transform: "rate", rate_per: "hour" };
const dashFlowQueries = (k) => [
  { id: "a", source: "moves", kind: k.name, measure: "entries", state: k.states[0], ...dashRate, label: "arrivals" },
  ...(k.finish ? [{ id: "b", source: "moves", kind: k.name, measure: "entries", state: k.finish, ...dashRate, label: "completions" }] : []),
];
const dashWorkQuery = (k) => ({ id: "a", source: "counts", kind: k.name, where: { state: k.open }, agg: "last", transform: "none" });
const dashStayQuery = (k, id, agg) => ({ id, source: "moves", kind: k.name, measure: "time_in_state", state: k.busiest, agg, transform: "none", label: agg });
const dashCostQuery = (k, f) => ({ id: "a", source: "items", kind: k.name, field: f.name, agg: "sum", transform: "rate", rate_per: "hour" });

/* the panels a kind is charted by: arrivals against completions, its open work by state, and how long the state
   holding the most keeps it */
function dashKindPanels(k) {
  const out = [];
  if (k.states.length > 1) out.push({ title: `${k.name}: arrivals and completions per hour`, form: "line", queries: dashFlowQueries(k),
                                      display: { unit: "/h", decimals: 1, legend: "right", legend_values: ["last", "max"], y: { min: 0 } } });
  if (k.open.length) out.push({ title: `${k.name}: open work by state`, form: "stacked",
                                queries: [{ ...dashWorkQuery(k), group_by: "state" }],
                                display: { unit: "items", decimals: 0, legend: "right", legend_values: ["last"], y: { min: 0 } } });
  if (k.busiest && k.states.length > 1) out.push({ title: `${k.name}: time in ${k.busiest}, p50 and p90`, form: "line",
                                                   queries: [dashStayQuery(k, "a", "p50"), dashStayQuery(k, "b", "p90")],
                                                   display: { unit: "s", legend: "right", legend_values: ["last", "max"], y: { min: 0 } } });
  return out;
}
const dashStat = (title, query, unit, decimals) => ({ title, form: "stat", size: "s", queries: [query], display: { unit, decimals } });

/* the dashboard a project opens on: its main kind's numbers in a row, then its charts, then the next kinds' */
function dashDefault(fields, flows = {}) {
  const kinds = dashKinds(fields, flows), panels = [];
  const main = kinds[0];
  if (main) {
    const costKind = kinds.find((k) => k.fields.some(dashIsCost));
    const cost = costKind?.fields.find(dashIsCost);
    const costUnit = cost ? `${cost.unit || "usd"}/h` : null;
    panels.push(dashStat(`Work in progress (${main.name})`, dashWorkQuery(main), "items", 0));
    if (main.finish) panels.push(dashStat(`Completions per hour (${main.name})`, dashFlowQueries(main)[1], "/h", 1));
    if (main.busiest) panels.push(dashStat(`Median time in ${main.busiest}`, dashStayQuery(main, "a", "p50"), "s"));
    if (cost) {                                        // two rows of three, so the row has no hole
      panels.push(dashStat(`Arrivals per hour (${main.name})`, dashFlowQueries(main)[0], "/h", 1));
      if (main.busiest) panels.push(dashStat(`p90 time in ${main.busiest}`, dashStayQuery(main, "a", "p90"), "s"));
      panels.push(dashStat(`${cost.name} per hour (${costKind.name})`, dashCostQuery(costKind, cost), costUnit, 2));
    }
    const first = dashKindPanels(main).map((p) => ({ ...p, size: "m" }));
    if (cost) first.push({ title: `${costKind.name}: ${cost.name} per hour`, form: "area", size: "m", queries: [dashCostQuery(costKind, cost)],
                           display: { unit: costUnit, decimals: 2, legend: "right", legend_values: ["last", "max"], y: { min: 0 } } });
    const worth = kinds.slice(0, 3).flatMap((k) => k.fields.filter((f) => !dashIsCost(f) && !DASH_NOT_CHARTED.test(f.name)).map((f) => ({ k, f })))
      .sort((a, b) => !!b.f.unit - !!a.f.unit).slice(0, 2);
    for (const { k, f } of worth) first.push({ title: `${k.name}: ${f.name}, average`, form: "line", size: "m",
                                               queries: [{ id: "a", source: "items", kind: k.name, field: f.name, agg: "avg", transform: "none" }],
                                               display: { unit: f.unit || "", legend: "right", legend_values: ["last", "max"] } });
    if (first.length % 2) first[first.length - 1].size = "full";
    panels.push(...first);
    for (const k of kinds.slice(1).filter((x) => x.inWork && !x.name.startsWith("ergostat.")).slice(0, 2)) {   // those with work open
      const row = dashKindPanels(k);
      const size = { 1: "full", 2: "m", 3: "s" }[row.length];
      panels.push(...row.map((p) => ({ ...p, size })));
    }
  } else {
    for (const x of (fields?.sources?.series?.series || []).slice(0, 6))
      panels.push({ title: x.name, form: "line", size: "m", queries: [{ id: "a", source: "series", series: x.name, agg: "last", transform: "none" }],
                    display: { unit: x.unit || "", legend: "right", legend_values: ["last", "max"] } });
  }
  return { title: "Overview", since: null, panels: panels.slice(0, DASH_MOST).map((p, i) => ({ note: "", tall: false, ...p, id: `p${i + 1}` })) };
}
async function dashBuildDefault() {
  const fields = await queryFields();
  const names = Object.keys(fields?.sources?.items?.kinds || {}).slice(0, 12), flows = {};
  await Promise.all(names.map(async (k) => { flows[k] = await api("items-flow", { kind: k, points: 2 }).catch(() => null); }));
  return dashDefault(fields, flows);
}

/* ---- the grid ---- */

const dashRows = (p) => (p.form === "stat" ? 4 : 7);    // a stat: its title, number, change and sparkline
const dashHeight = (p) => dashRows(p) * (p.tall ? 2 : 1) + (DASH.editing ? 1 : 0);
/* each panel in the first place it fits, in the draft's order: no holes, and the page's order is the order seen */
function dashPack(panels, cols) {
  const used = [];
  const free = (x, y, w, hi) => {
    for (let r = y; r < y + hi; r++) for (let c = x; c < x + w; c++) if (used[r]?.[c]) return false;
    return true;
  };
  return panels.map((p) => {
    const w = Math.min(cols, DASH_COLUMNS[p.size]), hi = dashHeight(p);
    for (let y = 0; ; y++) for (let x = 0; x + w <= cols; x++) if (free(x, y, w, hi)) {
      for (let r = y; r < y + hi; r++) { used[r] ||= []; for (let c = x; c < x + w; c++) used[r][c] = true; }
      return { p, x, y, w, h: hi };
    }
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
async function dashRefresh() {
  const d = DASH.draft, n = ++DASH.asked;
  if (!d?.panels.length) return;
  try {
    const got = await queryPanels(d.panels, { since: WINDOWS[S.since], until: S.at || null });
    if (n !== DASH.asked) return;
    for (const [id, c] of DASH.cells) {
      const a = got?.get?.(id);
      if (a) { c.panel.update(a.results, a.meta); c.drawn = true; }
    }
    if (DASH.said) DASH.said.textContent = `Updated ${clock(nowS())}`;
  } catch (e) {
    if (n !== DASH.asked) return;
    for (const c of DASH.cells.values()) if (!c.drawn) c.panel.setState?.("error", "The server did not answer");
    if (DASH.said) DASH.said.textContent = "Could not refresh; asking again";
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
  return DASH_EVERY[v] ?? DASH_EVERY["30s"];
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
  const asked = WINDOWS[q.get("since")] ? q.get("since") : null;
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
