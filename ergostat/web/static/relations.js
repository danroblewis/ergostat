/* the Items page's Graph and Timeline: the items' relations (SPEC §5a, Relations; precedence.py), drawn.

   Graph: the items left to right, each after what it waits on (ELK, layered). A parent with children drawn (an
   epic) is a stadium its children hang off when nothing else they wait on is drawn; grouped by kind instead, each
   kind is a frame. A card's left bar is its state, in the kind's chart's shade; its border its status: active (the
   accent, breathing), queued for a block's next step (the accent, dotted), unblocked (ink), blocked (dashed), paused (dotted on a fill), done (faint,
   ticked), a dead letter (bad). The critical path is
   drawn heavier, in the bad hue. Frontier: the unfinished items and what they wait on, however far back; collapse
   done: the finished vanish, and a chain through them is one dashed line, "via N done".

   Timeline: a Gantt chart. One row an item; its bar its states over time, from its moves (what happened), and for
   the unfinished, faint bars ahead: what the kind's medians project, each after what it waits on (the critical
   path method's forward pass). Arrows from each item to what waits on it; a now line, scrolled into view at load;
   ctrl or cmd and the wheel zoom it, a drag moves it.

   Both are kept across refreshes: drawn again only when what they show changed, in place, with the reader's pan
   and zoom kept. Bounded: RG.NODES cards, RG.BARS rows; a note says when that was reached. The Graph draws the kinds
   asked, what they wait on and their parents; past its bound it keeps whole connected groups, never half a chain. */
"use strict";

const RG = { W: 210, H: 46, HUB_W: 190, HUB_H: 40, NODES: 600, BARS: 200, ROW: 24, BAR: 12, LABEL: 250, AXIS: 26 };
const RG_STATUS = ["active", "queued", "unblocked", "blocked", "paused", "dead", "done"];
const RG_WORD = { active: "active", queued: "queued", unblocked: "unblocked", blocked: "waiting", paused: "paused", dead: "dead letter", done: "done" };

/* a state's shade: its place in its kind's states, on the ramp its chart (the cumulative flow) uses */
function rgShade(kinds, kind, state) {
  const k = kinds[kind], states = k?.states || [];
  const ramp = ["--line", "--line-strong", "--muted", "--ink-2"];
  const i = Math.max(0, states.indexOf(state));
  return `var(${ramp[Math.min(ramp.length - 1, Math.floor((i / Math.max(1, states.length - 1)) * (ramp.length - 1) + 0.0001))]})`;
}
const rgClip = (t, n) => (t.length > n ? t.slice(0, n - 1) + "…" : t);

/* what is drawn, from the answer and the reader's choices: which items (frontier, the search), which done
   ones collapse into "via N done", the parents as hubs, and every line */
function rgModel(d, o) {
  const byId = Object.fromEntries(d.items.map((x) => [x.id, x]));
  const kinds = Object.fromEntries(d.kinds.map((k) => [k.name, k]));
  const preds = {};
  for (const e of d.edges) if (e.kind === "precedence") (preds[e.to] ||= []).push(e.from);
  const done = (id) => byId[id]?.status === "done";
  // from the kinds asked (graph_parts.py): another kind's item only when one waits on it, or as a parent; an item
  // the answer holds because it names one (a review of a gap) is not drawn
  const asked = new Set(d.kinds.filter((k) => k.asked).map((k) => k.name));
  const scope = new Set();
  const chain = (id) => { if (scope.has(id) || !byId[id]) return; scope.add(id); (preds[id] || []).forEach(chain); };
  for (const x of d.items) if ((!asked.size || asked.has(x.kind)) && (!o.frontier || !done(x.id))) chain(x.id);
  for (const id of [...scope]) { const g = byId[id].group; if (g && byId[g]) scope.add(g); }
  const q = (o.q || "").trim().toLowerCase();
  if (q) for (const id of [...scope]) { const x = byId[id]; if (![x.id, x.title, x.state, x.kind, x.status].join(" ").toLowerCase().includes(q)) scope.delete(id); }
  if (o.status) for (const id of [...scope]) if (byId[id].status !== o.status) scope.delete(id);   // a status's count, clicked
  const kids = {};
  for (const id of scope) { const g = byId[id].group; if (g && scope.has(g)) (kids[g] ||= []).push(id); }
  const hub = (id) => o.group !== "kind" && !!kids[id];
  const collapsed = new Set();
  if (o.collapse) for (const id of scope) if (done(id) && !(kids[id] || []).some((c) => !done(c))) collapsed.add(id);
  const memo = {};
  const eff = (id, stack = new Set()) => {              // {drawn ancestor: how many done between}
    if (memo[id]) return memo[id];
    const out = {};
    for (const p of preds[id] || []) {
      if (!scope.has(p) || stack.has(p)) continue;
      if (collapsed.has(p)) { const s2 = new Set(stack); s2.add(id); for (const [a, via] of Object.entries(eff(p, s2))) if (!(a in out) || via + 1 < out[a]) out[a] = via + 1; }
      else out[p] = 0;
    }
    return (memo[id] = out);
  };
  const every = [...scope].filter((id) => !collapsed.has(id));
  let ids = every;
  const capped = every.length > RG.NODES ? every.length : 0;
  if (capped) {               // past the bound: whole connected groups (each item's part, graph_parts.py), in their order
    const part = (id) => byId[id].part ?? id, size = new Map();
    for (const id of every) size.set(part(id), (size.get(part(id)) || 0) + 1);
    const keep = new Set();
    let room = RG.NODES;
    for (const p of [...size.keys()].sort((a, b) => (typeof a === "number" ? a : Infinity) - (typeof b === "number" ? b : Infinity)))
      if (size.get(p) <= room) { keep.add(p); room -= size.get(p); }
    ids = every.filter((id) => keep.has(part(id)));
  }
  const drawn = new Set(ids);
  const crit = new Set(d.edges.filter((e) => e.critical).map((e) => e.from + "\n" + e.to));
  const nodes = ids.map((id) => ({ id, x: byId[id], hub: hub(id), w: hub(id) ? RG.HUB_W : RG.W, h: hub(id) ? RG.HUB_H : RG.H }));
  const edges = [];
  let lost = 0;                                          // dependency lines the bound left out, for the note
  for (const id of every) {
    const ps = o.collapse ? eff(id) : Object.fromEntries((preds[id] || []).filter((p) => scope.has(p)).map((p) => [p, 0]));
    if (!drawn.has(id)) { lost += Object.keys(ps).length; continue; }
    const shown = Object.entries(ps).filter(([p]) => drawn.has(p));
    lost += Object.keys(ps).length - shown.length;
    for (const [p, via] of shown)
      edges.push({ id: `p:${p}>${id}`, from: p, to: id, cls: via ? "via" : "dep", label: via ? `via ${via} done` : "", critical: !via && crit.has(p + "\n" + id) });
    const g = byId[id].group;
    if (!shown.length && g && drawn.has(g) && (hub(g) || o.group === "kind")) edges.push({ id: `g:${g}>${id}`, from: g, to: id, cls: "member", label: "" });
  }
  for (const e of d.edges) if (e.kind === "other" && drawn.has(e.from) && drawn.has(e.to)) edges.push({ id: `o:${e.from}>${e.to}:${e.rel}`, from: e.from, to: e.to, cls: "other", label: e.rel.replace(/_/g, " ") });
  const counts = {};
  for (const x of d.items) counts[x.status] = (counts[x.status] || 0) + 1;
  return { nodes, edges, kinds, counts, capped, lost, byId, scope };
}

/* laid out by ELK, left to right; by kind, each kind a frame of its own */
async function rgLayout(m, o) {
  const node = (n) => ({ id: n.id, width: n.w, height: n.h });
  const opts = {
    "elk.algorithm": "layered", "elk.direction": "RIGHT", "elk.edgeRouting": "ORTHOGONAL",
    "elk.layered.considerModelOrder.strategy": "NODES_AND_EDGES", "elk.layered.nodePlacement.strategy": "NETWORK_SIMPLEX",
    "elk.layered.spacing.nodeNodeBetweenLayers": "56", "elk.spacing.nodeNode": "22", "elk.spacing.edgeNode": "14",
    "elk.spacing.edgeEdge": "8", "elk.layered.spacing.edgeNodeBetweenLayers": "14", "elk.spacing.componentComponent": "36",
    "elk.edgeLabels.placement": "CENTER", "elk.spacing.edgeLabel": "2", "elk.padding": "[top=16,left=16,bottom=16,right=16]",
    "elk.separateConnectedComponents": "true",
  };
  let children;
  if (o.group === "kind") {
    const by = {};
    for (const n of m.nodes) (by[n.x.kind || ""] ||= []).push(n);
    children = Object.entries(by).map(([k, ns]) => ({ id: `kind:${k}`, children: ns.map(node), layoutOptions: { "elk.padding": "[top=30,left=14,bottom=14,right=14]" } }));
    opts["elk.hierarchyHandling"] = "INCLUDE_CHILDREN";
  } else children = m.nodes.map(node);
  const g = { id: "root", layoutOptions: opts, children,
    edges: m.edges.map((e) => ({ id: e.id, sources: [e.from], targets: [e.to],
      labels: e.label ? [{ id: e.id + ":l", text: e.label, width: textWidth(e.label) * 0.92 + 6, height: 13 }] : [] })) };
  const lay = await elk.layout(g);
  const abs = { root: { x: 0, y: 0 } }, pos = {}, frames = [];
  const walk = (c, ox, oy) => {
    for (const k of c.children || []) {
      const x = ox + k.x, y = oy + k.y;
      abs[k.id] = { x, y };
      if (k.children?.length) { frames.push({ id: k.id, x, y, w: k.width, h: k.height }); walk(k, x, y); }
      else pos[k.id] = { x, y, w: k.width, h: k.height };
    }
  };
  walk(lay, 0, 0);
  const lines = {};
  for (const e of lay.edges || []) {
    const off = abs[e.container] || abs.root;
    const sec = e.sections?.[0];
    if (!sec) continue;
    const pts = [sec.startPoint, ...(sec.bendPoints || []), sec.endPoint].map((p) => ({ x: p.x + off.x, y: p.y + off.y }));
    const l = e.labels?.[0];
    lines[e.id] = { pts, label: l ? { x: l.x + off.x, y: l.y + off.y, w: l.width, h: l.height } : null };
  }
  return { pos, lines, frames, w: lay.width, h: lay.height };
}

function rgCard(n, kinds, open) {
  const x = n.x, st = x.status;
  const cls = `rg-node rg-${st}${x.critical && st !== "done" ? " rg-critical" : ""}${n.hub ? " rg-hub" : ""}${x.cycle ? " rg-cycle" : ""}`;
  const g = s("g", { class: cls, "data-id": x.id, transform: `translate(${n.px},${n.py})`, tabindex: 0, role: "link",
                     onclick: () => open(x.id), onkeydown: (ev) => { if (ev.key === "Enter") open(x.id); } });
  const said = [x.id, x.title, `${x.kind || "no kind"}, ${x.state || "no state"}: ${RG_WORD[st] || st}`,
                x.waiting?.length ? `waits on ${x.waiting.join(", ")}` : "", x.holder ? `leased by ${x.holder}` : "",
                x.slack != null ? (x.critical ? "on the critical path" : `slack ${dur(x.slack)}`) : "",
                x.ef ? `expected done ${new Date(x.ef * 1000).toLocaleTimeString([], { hour12: false, hour: "2-digit", minute: "2-digit" })}${x.known === false ? " (assumed)" : ""}` : ""].filter(Boolean).join("\n");
  g.append(s("title", {}, said));
  if (n.hub) {
    const c = x.children || { done: 0, total: 0 };
    g.append(s("rect", { class: "rg-box", width: n.w, height: n.h, rx: n.h / 2 }),
      s("text", { class: "rg-id", x: n.w / 2, y: 17, "text-anchor": "middle" }, rgClip(x.id + (x.title ? ` · ${x.title}` : ""), 28)),
      s("text", { class: "rg-sub", x: n.w / 2, y: 31, "text-anchor": "middle" }, `${c.done}/${c.total} done` + (st === "done" ? " · finished" : "")));
    return g;
  }
  g.append(s("rect", { class: "rg-box", width: n.w, height: n.h, rx: 4 }),
    s("rect", { class: "rg-bar", width: 6, height: n.h, rx: 2, fill: rgShade(kinds, x.kind, x.state) }),
    s("text", { class: "rg-id", x: 14, y: 18 }, (st === "done" ? "✓ " : "") + rgClip(x.id, 22)),
    s("text", { class: "rg-pill", x: n.w - 8, y: 18, "text-anchor": "end" },
      st === "blocked" ? `waits ${x.waiting.length}` : st === "active" && x.holder ? rgClip(x.holder, 12) : (x.state || RG_WORD[st])),
    s("text", { class: "rg-sub", x: 14, y: 35 }, rgClip(x.title || (x.state ? `${x.state}` : ""), 30)));
  return g;
}

/* the Graph: a box with its own pan and zoom, drawn again in place when its model changes */
function relGraph(open) {
  const view = { x: 0, y: 0, k: 1, moved: false };
  const vp = s("g", { class: "rg-view" });
  const svg = s("svg", { class: "rg-svg", role: "img", "aria-label": "Items and their relations" }, vp);
  const note = h("p", { class: "note rg-note" });
  const stage = h("div", { class: "rg-stage" }, svg);
  const zoomBy = (f) => { const r = stage.getBoundingClientRect(); zoomAt(r.width / 2, r.height / 2, f); };
  const tools = h("div", { class: "rg-tools" },
    h("button", { class: "ghost", title: "Fit the drawing to the box", onclick: () => { view.moved = false; fit(); } }, "Fit"),
    h("button", { class: "ghost", title: "Zoom in", "aria-label": "Zoom in", onclick: () => zoomBy(1.25) }, "+"),
    h("button", { class: "ghost", title: "Zoom out", "aria-label": "Zoom out", onclick: () => zoomBy(0.8) }, "−"));
  const el = h("div", { class: "rg-graph" }, tools, stage, note);
  let lay = null, seq = 0;
  const apply = () => vp.setAttribute("transform", `translate(${view.x.toFixed(1)},${view.y.toFixed(1)}) scale(${view.k.toFixed(4)})`);
  function fit() {
    if (!lay) return;
    const r = stage.getBoundingClientRect(), W = r.width || 800, H = r.height || 400;
    view.k = Math.min(1.1, Math.max(0.15, Math.min((W - 16) / Math.max(1, lay.w), (H - 16) / Math.max(1, lay.h))));
    view.x = (W - lay.w * view.k) / 2; view.y = Math.max(8, (H - lay.h * view.k) / 2);
    apply();
  }
  function zoomAt(mx, my, f) {
    const k = Math.min(3, Math.max(0.1, view.k * f));
    view.x = mx - (mx - view.x) * (k / view.k); view.y = my - (my - view.y) * (k / view.k); view.k = k; view.moved = true; apply();
  }
  let drag = null;
  stage.addEventListener("pointerdown", (e) => { if (e.button !== 0 || e.target.closest(".rg-node")) return; drag = { x: e.clientX, y: e.clientY, vx: view.x, vy: view.y }; stage.setPointerCapture(e.pointerId); stage.classList.add("dragging"); });
  stage.addEventListener("pointermove", (e) => { if (!drag) return; view.x = drag.vx + e.clientX - drag.x; view.y = drag.vy + e.clientY - drag.y; view.moved = true; apply(); });
  stage.addEventListener("pointerup", () => { drag = null; stage.classList.remove("dragging"); });
  stage.addEventListener("wheel", (e) => {
    if (!(e.ctrlKey || e.metaKey)) return;               // the page scrolls; with ctrl or cmd (or a pinch) the drawing zooms
    e.preventDefault();
    const r = stage.getBoundingClientRect();
    zoomAt(e.clientX - r.left, e.clientY - r.top, Math.exp(Math.max(-40, Math.min(40, -e.deltaY)) * 0.006));
  }, { passive: false });
  el.draw = async (m, o) => {
    const mine = ++seq;
    const got = await rgLayout(m, o);
    if (mine !== seq) return;                            // a newer drawing is on its way
    lay = got;
    const crit = (e) => e.critical ? " rg-crit" : "";
    const parts = [];
    for (const f of got.frames) parts.push(s("g", { class: "rg-frame" }, s("rect", { x: f.x, y: f.y, width: f.w, height: f.h, rx: 4 }),
      s("text", { x: f.x + 10, y: f.y + 18 }, f.id.slice(5) || "no kind")));
    for (const e of m.edges) {
      const l = got.lines[e.id];
      if (!l) continue;
      const d = "M" + l.pts.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" L");
      const gg = s("g", { class: `rg-edge rg-${e.cls}${crit(e)}` }, s("path", { d, fill: "none" }));
      if (e.cls !== "member") gg.append(arrowHead(l.pts, "rg-head", e.critical ? 7 : 6));
      if (l.label) gg.append(s("text", { class: "rg-elabel", x: (l.label.x + l.label.w / 2).toFixed(1), y: (l.label.y + 10).toFixed(1), "text-anchor": "middle" }, e.label));
      parts.push(gg);
    }
    for (const n of m.nodes) { const p = got.pos[n.id]; if (!p) continue; n.px = p.x; n.py = p.y; parts.push(rgCard(n, m.kinds, open)); }
    const hgt = Math.round(Math.min(Math.max(320, got.h + 40), Math.max(420, innerHeight * 0.7)));
    if (stage.style.height !== `${hgt}px`) stage.style.height = `${hgt}px`;
    vp.replaceChildren(...parts);
    if (!view.moved) fit(); else apply();
    const left = m.capped - m.nodes.length;
    setText(note, m.capped ? `${m.nodes.length} of ${m.capped} items drawn: ${left} item${left === 1 ? "" : "s"} and ${m.lost} dependency line${m.lost === 1 ? "" : "s"} not drawn `
      + `(whole connected groups left out, those with active or unblocked work kept first). Narrow it with the search, or choose a kind.` : "");
    el.dataset.drawn = String(mine);
  };
  return el;
}

/* the Timeline: a Gantt chart, its time axis zoomed and moved by hand (kept across refreshes) */
function relTimeline(open) {
  const el = h("div", { class: "rg-timeline" });
  const tools = h("div", { class: "rg-tools" },
    h("button", { class: "ghost", title: "The whole span", onclick: () => { span = null; draw(); } }, "Fit"),
    h("button", { class: "ghost", title: "Zoom in", "aria-label": "Zoom in", onclick: () => zoom(0.7) }, "+"),
    h("button", { class: "ghost", title: "Zoom out", "aria-label": "Zoom out", onclick: () => zoom(1.4) }, "−"));
  const svg = s("svg", { class: "rg-svg rg-gantt", role: "img", "aria-label": "Items over time: what happened, and what is projected" });
  const note = h("p", { class: "note rg-note" });
  el.append(tools, h("div", { class: "rg-stage rg-tstage" }, svg), note);
  let span = null, cur = null, width = 0;
  const domain = () => span || cur?.fit || [0, 1];
  function zoom(f, at = null) {
    const [a, b] = domain(), c = at ?? (a + b) / 2;
    span = [c - (c - a) * f, c + (b - c) * f];
    draw();
  }
  let drag = null;
  svg.addEventListener("pointerdown", (e) => { if (e.button !== 0 || e.target.closest("a, .rg-label")) return; drag = { x: e.clientX, d: domain() }; svg.setPointerCapture(e.pointerId); });
  svg.addEventListener("pointermove", (e) => {
    if (!drag || !cur) return;
    const per = (drag.d[1] - drag.d[0]) / Math.max(1, width - RG.LABEL - 12), dt = (e.clientX - drag.x) * per;
    span = [drag.d[0] - dt, drag.d[1] - dt]; draw();
  });
  svg.addEventListener("pointerup", () => { drag = null; });
  svg.addEventListener("wheel", (e) => {
    if (!(e.ctrlKey || e.metaKey) || !cur) return;
    e.preventDefault();
    const r = svg.getBoundingClientRect(), [a, b] = domain();
    const t = a + ((e.clientX - r.left - RG.LABEL) / Math.max(1, r.width - RG.LABEL - 12)) * (b - a);
    zoom(Math.exp(Math.max(-40, Math.min(40, e.deltaY)) * 0.006), t);
  }, { passive: false });
  let opened = false;                                    // at load, once: the page scrolled to the first unfinished row, at now
  const toNow = () => {
    const r = !opened && el.isConnected && cur && svg.querySelector(".rg-row:not(.rg-done):not(.rg-lane)");
    if (!r) return;
    opened = true;
    const b = r.getBoundingClientRect();
    if (b.top < 0 || b.bottom > innerHeight) r.scrollIntoView({ block: "center" });
  };
  new ResizeObserver(() => { if (cur && Math.abs(el.clientWidth - width) > 4) draw(); toNow(); }).observe(el);
  function draw() {
    if (!cur) return;
    width = el.clientWidth || 900;
    const { rows, kinds, d, edges } = cur;
    const [a, b] = domain();
    const x0 = RG.LABEL, x1 = width - 12;
    const X = (t) => x0 + ((t - a) / Math.max(1e-9, b - a)) * (x1 - x0);
    const Y = (i) => RG.AXIS + i * RG.ROW + RG.ROW / 2;
    const H = RG.AXIS + rows.length * RG.ROW + 8;
    const parts = [];
    const steps = [1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600, 7200, 10800, 21600, 43200, 86400, 172800, 604800];
    const step = steps.find((x) => ((x1 - x0) / ((b - a) / x)) >= 80) || steps[steps.length - 1];
    const clock = (t) => new Date(t * 1000).toLocaleTimeString([], { hour12: false, hour: "2-digit", minute: "2-digit", ...(step < 60 ? { second: "2-digit" } : {}) });
    const nx = X(d.now);
    const stamp = (t) => (new Date(t * 1000).toDateString() === new Date(d.now * 1000).toDateString() ? clock(t)
      : new Date(t * 1000).toLocaleString([], { hour12: false, month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }));
    for (let t = Math.ceil(a / step) * step; t <= b; t += step) {
      const x = X(t);
      parts.push(s("line", { class: "rg-grid", x1: x, x2: x, y1: RG.AXIS - 4, y2: H }));
      if (Math.abs(x - nx) > 40 && x < width - 30) parts.push(s("text", { class: "rg-tick", x, y: 14, "text-anchor": "middle" }, step >= 86400 ? new Date(t * 1000).toLocaleDateString() : clock(t)));
    }
    const at = {};                                         // where each row's bar starts and ends, for the arrows
    rows.forEach((x, i) => {
      const y = Y(i);
      if (x.lane) {                                        // a block's lane: the projected runs in it, one at a time
        const row = s("g", { class: "rg-row rg-lane", "data-block": x.block, "data-lane": x.k });
        if (i % 2) row.append(s("rect", { class: "rg-band", x: 0, y: y - RG.ROW / 2, width, height: RG.ROW }));
        row.append(s("g", { class: "rg-label" }, s("title", {}, `${x.block}: lane ${x.k + 1} of ${x.cap} (its capacity: pool, seats, daemon)`),
          s("text", { class: "rg-id", x: 10, y: y + 4 }, rgClip(x.block, 22)), s("text", { class: "rg-sub", x: 10 + Math.min(22, x.block.length) * 6.6 + 6, y: y + 4 }, `${x.k + 1}/${x.cap}`)));
        for (const [id, kind, st, t0, t1] of x.bars) {
          const xa = Math.max(x0, X(t0)), xb = Math.min(x1, X(t1));
          if (xb - xa < 0.5) continue;
          row.append(s("rect", { class: "rg-proj rg-lanebar", x: xa, y: y - RG.BAR / 2, width: xb - xa, height: RG.BAR, fill: rgShade(kinds, kind, st), "data-id": id,
                                 onclick: () => open(id) }, s("title", {}, `${id}: ${st} in ${x.block} (projected), ${clock(t0)} to ${clock(t1)} (${dur(t1 - t0)})`)));
          if (xb - xa > 46) row.append(s("text", { class: "rg-sub rg-inbar", x: xa + 3, y: y + 4 }, rgClip(id.split("/").pop(), Math.floor((xb - xa) / 6.5))));
        }
        parts.push(row);
        return;
      }
      const row = s("g", { class: `rg-row rg-${x.status}${x.critical && x.status !== "done" ? " rg-critical" : ""}`, "data-id": x.id });
      if (i % 2) row.append(s("rect", { class: "rg-band", x: 0, y: y - RG.ROW / 2, width, height: RG.ROW }));
      const lab = s("g", { class: "rg-label", role: "link", tabindex: 0, onclick: () => open(x.id), onkeydown: (ev) => { if (ev.key === "Enter") open(x.id); } },
        s("title", {}, `${x.id}${x.title ? ": " + x.title : ""}\n${x.state || ""}: ${RG_WORD[x.status] || x.status}`),
        s("circle", { class: "rg-dot", cx: 10 + (x.depth || 0) * 12, cy: y, r: 3.5 }),
        s("text", { class: "rg-id", x: 19 + (x.depth || 0) * 12, y: y + 4 }, rgClip(x.id, 18)),
        s("text", { class: "rg-sub", x: 19 + (x.depth || 0) * 12 + Math.min(18, x.id.length) * 6.6 + 6, y: y + 4 }, rgClip(x.title || "", Math.max(0, 22 - (x.depth || 0) * 2 - Math.min(18, x.id.length) / 2))));
      row.append(lab);
      let lo = Infinity, hi = -Infinity;
      const seg = (st, t0, t1, proj) => {
        const xa = Math.max(x0, X(t0)), xb = Math.min(x1, X(t1));
        lo = Math.min(lo, X(t0)); hi = Math.max(hi, X(t1));
        if (xb - xa < 0.5) return;
        row.append(s("rect", { class: proj ? "rg-proj" : "rg-seg", x: xa, y: y - RG.BAR / 2, width: xb - xa, height: RG.BAR, fill: proj && x.summary ? "none" : rgShade(kinds, x.kind, st) },
          s("title", {}, `${x.id}: ${st}${proj ? " (projected)" : ""}, ${clock(t0)} to ${clock(t1)} (${dur(t1 - t0)})`)));
      };
      for (const [st, t0, t1] of x.segments || []) seg(st, t0, t1, false);
      for (const [st, t0, t1, , lane] of x.projected || []) {
        if (lane === "wait") {                             // waiting in a block's queue: a thin line, not work
          const xa = Math.max(x0, X(t0)), xb = Math.min(x1, X(t1));
          lo = Math.min(lo, X(t0)); hi = Math.max(hi, X(t1));
          if (xb - xa >= 0.5) row.append(s("line", { class: "rg-wait", x1: xa, x2: xb, y1: y, y2: y }, s("title", {}, `${x.id}: queued in ${st}, ${clock(t0)} to ${clock(t1)} (${dur(t1 - t0)})`)));
        } else seg(st, t0, t1, true);
      }
      if (x.eta?.p50 != null && x.status !== "done") {   // the estimate: a tick at the p50, a whisker to the p90
        const xa = X(x.eta.p50), xb = x.eta.p90 != null ? X(x.eta.p90) : x1;
        if (xa >= x0 && xa <= x1) row.append(s("line", { class: "rg-p50", x1: xa, x2: xa, y1: y - RG.BAR / 2 - 2, y2: y + RG.BAR / 2 + 2 }));
        if (xb > xa) row.append(s("path", { class: "rg-whisker", d: `M${Math.max(x0, xa)},${y} H${Math.min(x1, xb)}${xb <= x1 ? ` M${xb},${y - 4} V${y + 4}` : ""}` },
          s("title", {}, `${x.id}: done by ${stamp(x.eta.p50)} (p50), ${x.eta.p90 != null ? stamp(x.eta.p90) : x.eta.runs < 20 ? "no p90 under 20 runs" : "beyond the horizon"} (p90)\n${x.eta.why || ""}`)));
        hi = Math.max(hi, Math.min(x1, xb));
      }
      if (x.summary && x.es != null) {                     // a parent: a bracket over its children's span
        const xa = Math.max(x0, X(x.es)), xb = Math.min(x1, X(x.ef));
        if (xb > xa) row.append(s("path", { class: "rg-summary", d: `M${xa},${y + 6} V${y - 3} H${xb} V${y + 6}` }));
      }
      at[x.id] = { lo, hi, y };
      parts.push(row);
    });
    for (const e of edges) {
      const p = at[e.from], q = at[e.to];
      if (!p || !q || !isFinite(p.hi) || !isFinite(q.lo)) continue;
      const xa = Math.min(x1, Math.max(x0, p.hi)), xb = Math.min(x1, Math.max(x0, q.lo));
      const mid = Math.max(xa + 5, Math.min(xb - 5, xa + 8));
      const pts = [{ x: xa, y: p.y }, { x: mid, y: p.y }, { x: mid, y: q.y }, { x: Math.max(xb, mid + 0.01), y: q.y }];
      parts.push(s("g", { class: `rg-edge rg-dep${e.critical ? " rg-crit" : ""}` },
        s("path", { d: "M" + pts.map((pt) => `${pt.x.toFixed(1)},${pt.y.toFixed(1)}`).join(" L"), fill: "none" }), arrowHead(pts, "rg-head", 5)));
    }
    if (nx >= x0 && nx <= x1) parts.push(s("g", { class: "rg-now" }, s("line", { x1: nx, x2: nx, y1: RG.AXIS - 6, y2: H }), s("text", { x: nx, y: 14, "text-anchor": "middle" }, "now")));
    parts.push(s("line", { class: "rg-axis", x1: x0, x2: x0, y1: RG.AXIS - 4, y2: H }));
    svg.setAttribute("width", width); svg.setAttribute("height", H); svg.setAttribute("viewBox", `0 0 ${width} ${H}`);
    svg.replaceChildren(...parts);
  }
  el.draw = (m, d, lanes = false) => {
    if (lanes && d.eta) return drawLanes(m, d);
    // the rows: a parent, then its children under it; the rest in the order they start (projected or actual)
    const ids = m.nodes.map((n) => n.id).filter((id) => m.byId[id]);
    const key = (x) => (x.segments?.[0]?.[1] ?? x.es ?? x.first);
    const order = ids.map((id) => m.byId[id]).sort((p, q) => key(p) - key(q) || (p.id < q.id ? -1 : 1));
    const placed = new Set(), rows = [];
    const kidsOf = {};
    for (const x of order) if (x.group && ids.includes(x.group)) (kidsOf[x.group] ||= []).push(x);
    const put = (x, depth) => { if (placed.has(x.id)) return; placed.add(x.id); rows.push({ ...x, depth }); for (const c of kidsOf[x.id] || []) put(c, Math.min(3, depth + 1)); };
    for (const x of order) if (!(x.group && ids.includes(x.group))) put(x, 0);
    for (const x of order) put(x, 0);
    const shown = rows.slice(0, RG.BARS);
    const ts = shown.flatMap((x) => [...(x.segments || []).flatMap((g) => [g[1], g[2]]), ...(x.projected || []).flatMap((g) => [g[1], g[2]])]);
    const lo = Math.max(d.since, Math.min(d.now, ...ts)), hi = Math.max(d.now, ...ts);
    const pad = (hi - lo) * 0.03 || 60;
    const edges = d.edges.filter((e) => e.kind === "precedence");
    const p90s = shown.map((x) => x.eta?.p90).filter((t) => t != null);
    const top = Math.max(hi, ...p90s);
    cur = { rows: shown, kinds: m.kinds, d, edges, fit: [lo - pad, top + pad] };
    setText(note, (rows.length > RG.BARS ? `${RG.BARS} of ${rows.length} items drawn: narrow it with the search, or choose a kind. ` : "")
      + (d.eta ? `Projected bars: one of ${d.eta.runs} runs of the simulation (levelled: no block more at once than its capacity); the tick its p50, the whisker its p90. Not modelled: a goal that switches a block off, a capacity no block declares.`
        + (Object.keys(d.eta.assumed || {}).length ? ` Assumed: ${Object.entries(d.eta.assumed).map(([b, w]) => `${b}, ${w}`).join("; ")}.` : "")
        : (d.eta_error ? `No estimates: the simulation failed: ${d.eta_error}. The bars are each item's median times, unlevelled. `
          : Math.abs(Date.now() / 1000 - d.now) < 5 && rows.some((x) => x.status !== "done") ? "No estimates yet: the simulation is being worked out; the bars are each item's median times, unlevelled. " : "")
        + (d.assumed ? `No item has finished a state yet: projected at ${dur(d.assumed)} each, assumed.` : "")));
    draw(); toNow();
    el.dataset.drawn = String((+el.dataset.drawn || 0) + 1);
  };
  /* by lanes: each block that takes items, a row a lane (at most its capacity), the projected runs in them */
  function drawLanes(m, d) {
    const bars = {};
    for (const n of m.nodes) {
      const x = m.byId[n.id];
      for (const [st, t0, t1, block, lane] of x?.projected || []) if (block && Number.isInteger(lane)) (bars[`${block}\n${lane}`] ||= []).push([x.id, x.kind, st, t0, t1]);
    }
    const rows = [];
    for (const [block, cap] of Object.entries(d.eta.capacity || {})) {
      if (!Object.keys(bars).some((b) => b.startsWith(block + "\n"))) continue;        // (a block with no run ahead: no rows)
      for (let k = 0; k < cap; k++) if (bars[`${block}\n${k}`] || cap <= 12) rows.push({ lane: true, block, k, cap, id: `${block}:${k}`, bars: bars[`${block}\n${k}`] || [] });
    }
    const ts = rows.flatMap((r) => r.bars.flatMap((b) => [b[3], b[4]]));
    const lo = d.now, hi = Math.max(d.now + 60, ...ts);
    cur = { rows, kinds: m.kinds, d, edges: [], fit: [lo - (hi - lo) * 0.02, hi + (hi - lo) * 0.03] };
    setText(note, rows.length ? `Each block's lanes, at most its capacity at once (leases held over a lowered pool keep theirs until they end): one of ${d.eta.runs} runs of the simulation, levelled. A bar is an item's run; a click opens it. Not modelled: a goal that switches a block off, a capacity no block declares.` : "No block takes these items.");
    draw();
    el.dataset.drawn = String((+el.dataset.drawn || 0) + 1);
  }
  return el;
}

/* a moment as a clock time, rounded up to the minute (never earlier than it); its date too when not today */
const rgClock = (t, now) => {
  const c = new Date(Math.ceil(t / 60) * 60 * 1000), hm = c.toLocaleTimeString([], { hour12: false, hour: "2-digit", minute: "2-digit" });
  return c.toDateString() === new Date(now * 1000).toDateString() ? hm : `${c.toLocaleDateString([], { month: "short", day: "numeric" })} ${hm}`;
};
/* when the last open item drawn is done, in one sentence: its kind's last finish (p50, p90), never before the
   critical path's end; while the first estimate is worked out, said so */
function rgFinish(d) {
  const key = (txt, title = "") => h("span", { class: "rg-key rg-eta", key: "eta", title }, txt);
  if (!d.eta) return d.eta_pending && !SNAP ? key("the last item's finish: being worked out") : null;
  const last = d.items.filter((x) => x.eta && x.status !== "done").reduce((a, x) => (a && (a.eta.p50 ?? Infinity) >= (x.eta.p50 ?? Infinity) ? a : x), null);
  if (!last) return null;
  const e = d.eta.kinds[last.kind] || last.eta, lo = Math.max(e.p50 ?? Infinity, d.end), who = `last ${last.kind} (${last.id.split("/").pop()})`;
  return key(e.p50 == null ? `${who} beyond the horizon` : `${who} expected ${rgClock(lo, d.now)}, `
      + (e.p90 != null ? `by ${rgClock(Math.max(e.p90, lo), d.now)} at worst (9 in 10)` : `no worst case under 20 runs (${d.eta.runs})`),
    `When the last open ${last.kind} is done: the p50 (expected) and the p90 (at worst) of ${d.eta.runs} runs of a simulation of every open item, each block at most its capacity at once (pool, seats, daemon), from the record's run times, failures and rework; never before the critical path's end (${rgClock(d.end, d.now)}). Not modelled: a goal that switches a block off, a capacity no block declares`
      + (e.visits && Object.keys(e.visits).length ? `\nExpected visits per state, from the first: ${Object.entries(e.visits).map(([st, v]) => `${st} ${v.toFixed(2)}`).join(", ")}` : ""));
}

/* the legend: how many of each status, the critical path and when the last item is expected done, any cycle */
function relLegend(m, d, pick = null, chosen = null) {
  const n = m.counts;
  const crit = d.critical.length;
  return h("div", { class: "rg-legend" },
    ...RG_STATUS.filter((st) => n[st]).map((st) => h(pick ? "button" : "span", {
      class: `rg-key rg-${st}${pick ? " ghost" : ""}${chosen === st ? " on" : ""}`, key: st,
      ...(pick ? { title: chosen === st ? "Show every status again" : `Show only the ${RG_WORD[st]}`, "aria-pressed": String(chosen === st), onclick: () => pick(st) } : {}) },
      h("i", {}), `${n[st]} ${RG_WORD[st]}`)),
    crit ? h("span", { class: "rg-key rg-critkey", key: "crit", title: "The longest chain of unfinished work, by the kinds' median times: nothing on it can slip without moving the end" },
      h("i", {}), `critical path ${crit} item${crit === 1 ? "" : "s"}` + (d.eta || (d.eta_pending && !SNAP) ? "" : `, ends about ${rgClock(d.end, d.now)}`)) : null,
    rgFinish(d),
    d.eta?.whatif?.length ? h("span", { class: "rg-key whatif-said", key: "whatif" }, `what if ${d.eta.whatif.join(" and ")} (not saved)`) : null,
    d.cycles.length ? h("span", { class: "rg-key bad", key: "cycle" }, `${d.cycles.length} cycle${d.cycles.length > 1 ? "s" : ""}: ${d.cycles.map((c) => c.join(" → ")).join("; ")}`) : null,
    Object.keys(d.capped || {}).length ? h("span", { class: "muted", key: "capped" }, "(the newest drawn: " + Object.keys(d.capped).join(", ") + " capped)") : null);
}
