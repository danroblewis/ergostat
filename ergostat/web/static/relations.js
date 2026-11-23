/* the Items page's Graph and Timeline: the items' relations (SPEC §5a, Relations; precedence.py), drawn.

   Graph: the items left to right, each after what it waits on (ELK, layered). A parent with children drawn (an
   epic) is a stadium its children hang off when nothing else they wait on is drawn; grouped by kind instead, each
   kind is a frame. A group other than a parent, of a kind not asked (a gap's milestone), is a frame its members are
   drawn inside, titled with its tally (rgTally); one with nothing drawn in it, a card; the Timeline a summary row. A card's left bar is its state, in the kind's chart's shade; its border its status: active (the
   accent, breathing), queued for a block's next step (the accent, dotted), unblocked (ink), blocked (dashed), paused (dotted on a fill), done (faint,
   ticked), a dead letter (bad). A set's where on a relation (a milestone's row on the kind's card) narrows both to
   its items and what they wait on. The critical path is
   drawn heavier, in the bad hue. Frontier: the unfinished items and what they wait on, however far back; collapse
   done: the finished vanish, and a chain through them is one dashed line, "via N done".

   Timeline: a Gantt chart. One row an item; its bar its states over time, from its moves (what happened), and for
   the unfinished, faint bars ahead: what the kind's medians project, each after what it waits on and each block at
   most its capacity at once (the levelled forward pass; the simulation's run once worked out). Arrows from each item to what waits on it; a now line, scrolled into view at load;
   ctrl or cmd and the wheel zoom it, a drag moves it.

   Both are kept across refreshes: drawn again only when what they show changed, in place, with the reader's pan
   and zoom kept. Bounded: RG.NODES cards, RG.BARS rows; a note says when that was reached. The Graph draws the kinds
   asked, what they wait on and their parents; past its bound it keeps whole connected groups, and cuts inside only the
   first that does not fit (its items by status), counting the lines it leaves out. */
"use strict";

const RG = { W: 210, H: 46, HUB_W: 190, HUB_H: 40, NODES: 600, BARS: 200, ROW: 24, BAR: 12, LABEL: 340, AXIS: 26 };
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
const rgTimes = (x) => [...(x.segments || []), ...(x.projected || [])].flatMap((g) => [g[1], g[2]]);   // a row's times

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
  // frames: an asked item's group other than its parent (a gap's milestone), of a kind not asked, is a frame its
  // members are drawn inside; the asked items with none, in a plain frame. A parent stays a hub; by kind, each kind
  // is a frame instead
  const groupsOf = {}, frameOf = {};
  for (const e of d.edges) if (e.kind === "group" && byId[e.from] && byId[e.to]) (groupsOf[e.to] ||= []).push(e);
  let rel = "";
  if (o.group !== "kind" && asked.size) for (const [id, es] of Object.entries(groupsOf)) {
    const f = asked.has(byId[id].kind) && es.find((e) => e.rel !== "parent" && !asked.has(byId[e.from].kind));
    if (f) { frameOf[id] = f.from; rel ||= f.rel; }
  }
  const frameKinds = new Set(Object.values(frameOf).map((f) => byId[f].kind));
  const parentOf = (id) => [byId[id].group, ...(groupsOf[id] || []).map((e) => e.from)]
    .find((g) => g && byId[g] && g !== frameOf[id] && !frameKinds.has(byId[g].kind)) ?? null;
  // a set's where on a relation of the kinds asked (a milestone's row: where=milestone:ID; none: :null), as the list
  // reads it: only those items, and what they wait on
  const wh = {};
  for (const w of o.where || []) { const i = w.indexOf(":"), f = w.slice(0, i); if (i > 0 && d.kinds.some((k) => k.asked && k.relations?.[f])) (wh[f] ||= []).push(w.slice(i + 1)); }
  const fits = (x) => Object.entries(wh).every(([f, vs]) => { const have = x.links?.[f] || []; return vs.some((v) => (v === "" || v === "null" ? !have.length : have.includes(v))); });
  for (const x of d.items) if ((!asked.size || asked.has(x.kind)) && (!o.frontier || !done(x.id)) && fits(x)) chain(x.id);
  for (const id of [...scope]) { const g = parentOf(id); if (g) scope.add(g); }
  const q = (o.q || "").trim().toLowerCase();
  if (q) for (const id of [...scope]) { const x = byId[id]; if (![x.id, x.title, x.state, x.kind, x.status].join(" ").toLowerCase().includes(q)) scope.delete(id); }
  if (o.status) for (const id of [...scope]) if (byId[id].status !== o.status) scope.delete(id);   // a status's count, clicked
  const frames = new Set();                              // each frame of an item kept, and the frames they wait on
  for (const id of scope) if (frameOf[id]) frames.add(frameOf[id]);
  for (const st = [...frames]; st.length;) for (const p of preds[st.pop()] || []) if (byId[p] && frameKinds.has(byId[p].kind) && !frames.has(p)) { frames.add(p); st.push(p); }
  for (const f of frames) scope.delete(f);
  const kids = {};
  for (const id of scope) { const g = parentOf(id); if (g && scope.has(g)) (kids[g] ||= []).push(id); }
  const hub = (id) => o.group !== "kind" && !!kids[id];
  const collapsed = new Set();
  if (o.collapse) for (const id of scope) if (done(id) && !(kids[id] || []).some((c) => !done(c))) collapsed.add(id);
  let folded = new Set();                                // frames with nothing drawn in them: each drawn as one card
  const memo = {};
  const eff = (id, stack = new Set()) => {              // {drawn ancestor: how many done between}
    if (memo[id]) return memo[id];
    const out = {};
    for (const p of preds[id] || []) {
      if (!scope.has(p) || stack.has(p)) continue;
      const f = frameOf[p];
      if (collapsed.has(p) && folded.has(f) && f !== frameOf[id]) { if (!(f in out)) out[f] = 0; }   // from its folded frame
      else if (collapsed.has(p)) { const s2 = new Set(stack); s2.add(id); for (const [a, via] of Object.entries(eff(p, s2))) if (!(a in out) || via + 1 < out[a]) out[a] = via + 1; }
      else out[p] = 0;
    }
    return (memo[id] = out);
  };
  const every = [...scope].filter((id) => !collapsed.has(id));
  let ids = every;
  const capped = every.length > RG.NODES ? every.length : 0;
  if (capped) {   // past the bound: whole connected groups (each item's part, graph_parts.py) in their order, each with
    // its parents; the first group that does not fit whole is cut inside, its items by status, and the rest left out
    const part = (id) => byId[id].part ?? id, groups = new Map(), ev = new Set(every), keep = new Set();
    for (const id of every) { const g = groups.get(part(id)); if (g) g.push(id); else groups.set(part(id), [id]); }    const up = (id) => { const out = []; for (let a = id; a && ev.has(a) && !keep.has(a) && !out.includes(a); a = parentOf(a)) out.push(a); return out; };
    const rank = (x) => [RG_STATUS.includes(x.status) ? RG_STATUS.indexOf(x.status) : RG_STATUS.length, x.es || x.first || 0];
    const byStatus = (a, b) => { const p = rank(byId[a]), q = rank(byId[b]); return p[0] - q[0] || p[1] - q[1] || (a < b ? -1 : 1); };
    const num = (p) => (typeof p === "number" ? p : Infinity);
    let room = RG.NODES;
    for (const p of [...groups.keys()].sort((a, b) => num(a) - num(b))) {
      const need = new Set(groups.get(p).flatMap(up));
      if (need.size <= room) { need.forEach((a) => keep.add(a)); room -= need.size; continue; }
      for (const id of groups.get(p).sort(byStatus)) { const n = up(id); if (n.length <= room) { n.forEach((a) => keep.add(a)); room -= n.length; } }
      break;
    }
    ids = every.filter((id) => keep.has(id));
  }
  const inFrame = (id) => (frames.has(frameOf[id]) ? frameOf[id] : frames.size && asked.has(byId[id].kind) ? RG_PLAIN : null);
  const held = new Set(ids.map(inFrame));
  folded = new Set([...frames].filter((f) => !held.has(f)));
  const drawn = new Set([...ids, ...frames]);
  const crit = new Set(d.edges.filter((e) => e.critical).map((e) => e.from + "\n" + e.to));
  const nodes = ids.map((id) => ({ id, x: byId[id], hub: hub(id), w: hub(id) ? RG.HUB_W : RG.W, h: hub(id) ? RG.HUB_H : RG.H, in: inFrame(id) }));
  // each frame's title: its name and state, and its members' tally (every one the answer holds, drawn or not)
  const members = {}, frameInfo = {};
  if (frames.size) for (const x of d.items) if (asked.has(x.kind)) (members[frames.has(frameOf[x.id]) ? frameOf[x.id] : x.id in frameOf ? "" : RG_PLAIN] ||= []).push(x);
  for (const f of [...frames, ...(held.has(RG_PLAIN) ? [RG_PLAIN] : [])]) frameInfo[f] = rgTally(f, byId[f], members[f] || [], frameOf, rel);
  for (const f of folded) {
    const t = frameInfo[f];
    nodes.push({ id: f, x: byId[f], fold: true, info: t, w: Math.min(440, Math.max(RG.W, textWidth(t.head) + 24, textWidth(t.sub) + 24)), h: 50 });
  }
  const edges = [];
  let lost = 0;                                          // dependency lines the bound left out, for the note
  for (const id of every) {
    const ps = o.collapse ? eff(id) : Object.fromEntries((preds[id] || []).filter((p) => scope.has(p)).map((p) => [p, 0]));
    if (!drawn.has(id)) { lost += Object.keys(ps).length; continue; }
    const shown = Object.entries(ps).filter(([p]) => drawn.has(p));
    lost += Object.keys(ps).length - shown.length;
    for (const [p, via] of shown)
      edges.push({ id: `p:${p}>${id}`, from: p, to: id, cls: via ? "via" : "dep", label: via ? `via ${via} done` : "", critical: !via && crit.has(p + "\n" + id) });
    const g = parentOf(id);
    if (!shown.length && g && drawn.has(g) && (hub(g) || o.group === "kind")) edges.push({ id: `g:${g}>${id}`, from: g, to: id, cls: "member", label: "" });
  }
  for (const f of frames) for (const p of preds[f] || []) if (frames.has(p))           // a frame after the frames it waits on
    edges.push({ id: `p:${p}>${f}`, from: p, to: f, cls: "dep", label: "", critical: crit.has(p + "\n" + f) });
  for (const e of d.edges) if (e.kind === "other" && drawn.has(e.from) && drawn.has(e.to)) edges.push({ id: `o:${e.from}>${e.to}:${e.rel}`, from: e.from, to: e.to, cls: "other", label: e.rel.replace(/_/g, " ") });
  const counts = {};
  for (const x of d.items) counts[x.status] = (counts[x.status] || 0) + 1;
  const framed = Object.fromEntries(ids.map((id) => [id, inFrame(id)]).filter(([, f]) => f));
  return { nodes, edges, kinds, counts, capped, lost, byId, scope, frameOf: framed, frameInfo, folded, members };
}

/* a frame's title (rgModel): its name and state, then its members' tally: done of all, working, ready, and blocked
   and on what (the items they wait on, each by its own frame when that is another); in full in its tooltip */
const RG_PLAIN = "(plain)";
function rgTally(f, x, xs, frameOf, rel) {
  const n = (st) => xs.filter((y) => st.includes(y.status)).length;
  const on = [];
  for (const y of xs) if (y.status === "blocked") for (const w of y.waiting || []) { const a = frameOf[w] && frameOf[w] !== f ? frameOf[w] : w; if (!on.includes(a)) on.push(a); }
  const short = (a) => a.split("/").pop();
  const parts = [`${n(["done"])}/${xs.length} done`, `${n(["active", "queued"])} working`, `${n(["unblocked"])} ready`,
    `${n(["blocked"])} blocked` + (on.length ? ` on ${on.slice(0, 3).map(short).join(", ")}${on.length > 3 ? ` +${on.length - 3}` : ""}` : ""),
    ...["paused", "dead"].filter((st) => n([st])).map((st) => `${n([st])} ${RG_WORD[st]}`)];
  const waits = x?.status === "blocked" && x.waiting?.length ? `waits on ${x.waiting.map(short).join(", ")}` : "";
  const head = x ? `${x.id}${x.title ? ` · ${x.title}` : ""} · ${x.state || RG_WORD[x.status] || ""}` : `no ${(rel || "frame").replace(/_/g, " ")}`;
  return { head, sub: [...parts, ...(waits ? [waits] : [])].join(" · "), done: n(["done"]), total: xs.length,
           said: [head, ...parts.slice(0, 3), `${n(["blocked"])} blocked${on.length ? ` on ${on.join(", ")}` : ""}`, ...parts.slice(4), waits].filter(Boolean).join("\n") };
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
  } else if (Object.keys(m.frameOf || {}).length) {         // each open frame (a milestone) holding its members
    const by = {};
    for (const n of m.nodes) if (n.in) (by[n.in] ||= []).push(n);
    children = [...Object.entries(by).map(([f, ns]) => {
      const t = m.frameInfo[f], w = Math.min(900, Math.max(textWidth(t.head), textWidth(t.sub)) + 28);
      return { id: f, children: ns.map(node), layoutOptions: { "elk.padding": "[top=46,left=14,bottom=14,right=14]",
        "elk.nodeSize.constraints": "MINIMUM_SIZE", "elk.nodeSize.minimum": `(${w},60)` } };
    }), ...m.nodes.filter((n) => !n.in).map(node)];
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
  if (n.fold) {                                          // a frame folded: its title alone (a completed milestone)
    g.setAttribute("class", `rg-node rg-fold rg-${st}`);
    g.append(s("title", {}, n.info.said), s("rect", { class: "rg-box", width: n.w, height: n.h, rx: 4 }),
      s("text", { class: "rg-id", x: 12, y: 19 }, rgClip(n.info.head, Math.floor((n.w - 20) / 6.4))),
      s("text", { class: "rg-sub", x: 12, y: 37 }, rgClip(n.info.sub, Math.floor((n.w - 20) / 5.6))));
    return g;
  }
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
    for (const f of got.frames) {
      const t = m.frameInfo?.[f.id], x = m.byId[f.id];
      if (!t) { parts.push(s("g", { class: "rg-frame" }, s("rect", { x: f.x, y: f.y, width: f.w, height: f.h, rx: 4 }),
        s("text", { x: f.x + 10, y: f.y + 18 }, f.id.slice(5) || "no kind"))); continue; }
      parts.push(s("g", { class: `rg-frame ${x ? `rg-ms rg-${x.status}` : "rg-plain"}`, "data-id": x ? f.id : "",
                          ...(x ? { role: "link", tabindex: 0, onclick: () => open(f.id), onkeydown: (ev) => { if (ev.key === "Enter") open(f.id); } } : {}) },
        s("title", {}, t.said), s("rect", { x: f.x, y: f.y, width: f.w, height: f.h, rx: 4 }),
        s("text", { class: "rg-fhead", x: f.x + 10, y: f.y + 18 }, t.head), s("text", { class: "rg-fsub", x: f.x + 10, y: f.y + 34 }, t.sub)));
    }
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
      + `(connected groups kept whole, those with active or unblocked work first; only the first that does not fit is cut, by status). Narrow it with the search, or choose a kind.` : "");
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
  const said = h("span"), held = h("span", { class: "rg-calibration" });   // held: how well last week's estimates held
  const note = h("p", { class: "note rg-note" }, said, held);
  el.append(tools, h("div", { class: "rg-stage rg-tstage" }, svg), note);
  const calibrated = (d) => patchKids(held, Object.entries(d.eta?.calibration || {}).map(([k, c]) =>
    h("span", { "data-kind": k, class: c.items >= 10 && c.coverage != null && c.coverage < 0.7 ? "lvl-warn" : "" }, ` ${c.said}.`)));
  let span = null, cur = null, width = 0, last = null;
  const byHand = {};                                     // each frame opened or folded by hand, kept across refreshes
  const toggle = (f, was) => { byHand[f] = !was; if (last) el.draw(...last); };
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
    const tick = (t) => new Date(t * 1000).toLocaleTimeString([], { hour12: false, hour: "2-digit", minute: "2-digit", ...(step < 60 ? { second: "2-digit" } : {}) });
    const clock = (t) => rgClock(t, d.now, step < 60), stamp = (t) => rgClock(t, d.now);
    const nx = X(d.now);
    for (let t = Math.ceil(a / step) * step; t <= b; t += step) {
      const x = X(t);
      parts.push(s("line", { class: "rg-grid", x1: x, x2: x, y1: RG.AXIS - 4, y2: H }));
      if (Math.abs(x - nx) > 40 && x < width - 30) parts.push(s("text", { class: "rg-tick", x, y: 14, "text-anchor": "middle" }, step >= 86400 ? new Date(t * 1000).toLocaleDateString() : tick(t)));
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
      if (x.sum) {                                         // a frame's summary: its span, how much is done, its tally
        const t = x.info, link = x.x ? { role: "link", tabindex: 0, onclick: () => open(x.id), onkeydown: (ev) => { if (ev.key === "Enter") open(x.id); } } : {};
        const row = s("g", { class: `rg-row rg-sumrow rg-${x.x?.status || "plain"}`, "data-id": x.id, "data-open": String(x.open) });
        if (i % 2) row.append(s("rect", { class: "rg-band", x: 0, y: y - RG.ROW / 2, width, height: RG.ROW }));
        row.append(s("text", { class: "rg-tri", x: 4, y: y + 4, role: "button", tabindex: 0, "aria-expanded": String(x.open),
                               "aria-label": `${x.open ? "Fold" : "Open"} ${t.head}`, onclick: () => toggle(x.id, x.open),
                               onkeydown: (ev) => { if (ev.key === "Enter") toggle(x.id, x.open); } }, x.open ? "▾" : "▸"),
          s("g", { class: "rg-label", ...link }, s("title", {}, t.said), s("text", { class: "rg-id", x: 16, y: y + 4 }, rgClip(t.head, Math.floor((x0 - 22) / 6.6)))));
        const tt = x.span, t0 = Math.min(...tt), t1 = Math.max(...tt);
        let lo = Infinity, hi = -Infinity;
        if (tt.length) {
          lo = X(t0); hi = X(t1);
          const xa = Math.max(x0, lo), xb = Math.min(x1, hi);
          if (xb > xa) row.append(s("rect", { class: "rg-msum", x: xa, y: y - RG.BAR / 2, width: xb - xa, height: RG.BAR, "data-t0": t0, "data-t1": t1 }, s("title", {}, `${t.said}\n${clock(t0)} to ${clock(t1)}`)),
            s("rect", { class: "rg-msdone", x: xa, y: y - RG.BAR / 2, width: (xb - xa) * (t.total ? t.done / t.total : 0), height: RG.BAR }));
        }
        const w = textWidth(t.sub), after = Math.min(x1, hi) + 6;   // no times at all: the tally at the axis
        const tx = !tt.length ? x0 + 4 : after + w <= x1 ? after : Math.max(x0, lo) - 6 - w >= x0 ? Math.max(x0, lo) - 6 - w : x0 + 4;
        row.append(s("text", { class: "rg-sub rg-tally", x: tx, y: y + 4 }, t.sub));
        at[x.id] = { lo, hi, y };
        parts.push(row);
        return;
      }
      const row = s("g", { class: `rg-row rg-${x.status}${x.critical && x.status !== "done" ? " rg-critical" : ""}`, "data-id": x.id });
      if (i % 2) row.append(s("rect", { class: "rg-band", x: 0, y: y - RG.ROW / 2, width, height: RG.ROW }));
      const ind = (x.depth || 0) * 12, room = Math.floor((x0 - 26 - ind) / 6.6), name = rgClip(x.id, room);   // the whole id where it fits
      const lab = s("g", { class: "rg-label", role: "link", tabindex: 0, onclick: () => open(x.id), onkeydown: (ev) => { if (ev.key === "Enter") open(x.id); } },
        s("title", {}, `${x.id}${x.title ? ": " + x.title : ""}\n${x.state || ""}: ${RG_WORD[x.status] || x.status}`),
        s("circle", { class: "rg-dot", cx: 10 + ind, cy: y, r: 3.5 }),
        s("text", { class: "rg-id", x: 19 + ind, y: y + 4 }, name),
        s("text", { class: "rg-sub", x: 19 + ind + name.length * 6.6 + 6, y: y + 4 }, rgClip(x.title || "", Math.max(0, room - name.length - 1))));
      row.append(lab);
      let lo = Infinity, hi = -Infinity;
      const seg = (st, t0, t1, proj, block = null) => {
        const xa = Math.max(x0, X(t0)), xb = Math.min(x1, X(t1));
        lo = Math.min(lo, X(t0)); hi = Math.max(hi, X(t1));
        if (xb - xa < 0.5) return;
        row.append(s("rect", { class: proj ? "rg-proj" : "rg-seg", x: xa, y: y - RG.BAR / 2, width: xb - xa, height: RG.BAR, fill: proj && x.summary ? "none" : rgShade(kinds, x.kind, st), ...(block ? { "data-block": block } : {}) },
          s("title", {}, `${x.id}: ${st}${proj ? ` (projected${block ? ` in ${block}` : ""})` : ""}, ${clock(t0)} to ${clock(t1)} (${dur(t1 - t0)})`)));
      };
      for (const [st, t0, t1] of x.segments || []) seg(st, t0, t1, false);
      for (const [st, t0, t1, block, lane] of x.projected || []) {
        if (lane === "wait") {                             // waiting in a block's queue: a thin line, not work
          const xa = Math.max(x0, X(t0)), xb = Math.min(x1, X(t1));
          lo = Math.min(lo, X(t0)); hi = Math.max(hi, X(t1));
          if (xb - xa >= 0.5) row.append(s("line", { class: "rg-wait", x1: xa, x2: xb, y1: y, y2: y }, s("title", {}, `${x.id}: queued in ${st}, ${clock(t0)} to ${clock(t1)} (${dur(t1 - t0)})`)));
        } else seg(st, t0, t1, true, block);
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
    for (const [a, f] of Object.entries(cur.alias || {})) at[a] ||= at[f];   // a folded frame's members: its summary row
    for (const e of edges) {
      const p = at[e.from], q = at[e.to];
      if (!p || !q || p === q || !isFinite(p.hi) || !isFinite(q.lo)) continue;
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
    // the rows: by frame when the Graph has frames; else a parent, then its children under it; the rest in the order
    // they start (projected or actual)
    last = [m, d];
    const ids = m.nodes.filter((n) => !n.fold).map((n) => n.id).filter((id) => m.byId[id]);
    const key = (x) => (x.segments?.[0]?.[1] ?? x.es ?? x.first);
    const order = ids.map((id) => m.byId[id]).sort((p, q) => key(p) - key(q) || (p.id < q.id ? -1 : 1));
    const placed = new Set(), alias = {};
    let rows = [], folds = 0;
    const fr = m.frameInfo || {};
    if (Object.keys(fr).length) {
      // by frame (a milestone): its summary row, its members under it while open (an active one, or the plain frame;
      // a click on the triangle opens or folds it); frames and the rest in the order they start, the schedule's
      const byF = {}, loose = [];
      for (const x of order) if (m.frameOf[x.id]) (byF[m.frameOf[x.id]] ||= []).push(x); else loose.push(x);
      // a frame's span: every member the answer holds, drawn or collapsed (under Frontier + Collapse done a completed
      // milestone's are all collapsed); none with times, the milestone's own
      const all = m.members || {}, span = {};
      for (const f of Object.keys(fr)) { span[f] = (all[f] || []).flatMap(rgTimes); if (!span[f].length && m.byId[f]) span[f] = rgTimes(m.byId[f]); }
      const start = (f) => Math.min(...(byF[f] || []).map(key), ...span[f], m.byId[f] ? key(m.byId[f]) : Infinity);
      const ent = [...Object.keys(fr).map((f) => ({ f, k: start(f) })), ...loose.map((x) => ({ x, k: key(x) }))]
        .sort((p, q) => p.k - q.k || ((p.f ?? p.x.id) < (q.f ?? q.x.id) ? -1 : 1));
      const open = new Set(Object.keys(fr).filter((f) => byHand[f] ?? (f === RG_PLAIN || ["active", "queued"].includes(m.byId[f]?.status))));
      let n = ent.reduce((a, e) => a + 1 + (e.f && open.has(e.f) ? (byF[e.f] || []).length : 0), 0);
      for (const e of [...ent].reverse()) {             // past the bound: the frames that start last are folded first
        if (n <= RG.BARS) break;
        if (e.f && open.has(e.f) && byF[e.f]?.length) { open.delete(e.f); n -= byF[e.f].length; folds++; }
      }
      for (const e of ent) {
        if (!e.f) { rows.push({ ...e.x, depth: 0 }); continue; }
        const xs = byF[e.f] || [];
        rows.push({ sum: true, id: e.f, x: m.byId[e.f], info: fr[e.f], open: open.has(e.f), kids: xs, span: span[e.f], depth: 0 });
        for (const x of xs) if (open.has(e.f)) rows.push({ ...x, depth: 1 });
        if (!open.has(e.f)) for (const x of [...xs, ...(all[e.f] || [])]) alias[x.id] = e.f;   // a folded one's lines: from its row
      }
    } else {                                            // a parent, then its children under it
      const kidsOf = {};
      for (const x of order) if (x.group && ids.includes(x.group)) (kidsOf[x.group] ||= []).push(x);
      const put = (x, depth) => { if (placed.has(x.id)) return; placed.add(x.id); rows.push({ ...x, depth }); for (const c of kidsOf[x.id] || []) put(c, Math.min(3, depth + 1)); };
      for (const x of order) if (!(x.group && ids.includes(x.group))) put(x, 0);
      for (const x of order) put(x, 0);
    }
    const shown = rows.slice(0, RG.BARS);
    const ts = shown.flatMap((x) => (x.sum ? x.span : rgTimes(x)));
    const lo = Math.max(d.since, Math.min(d.now, ...ts)), hi = Math.max(d.now, ...ts);
    const pad = (hi - lo) * 0.03 || 60;
    const edges = d.edges.filter((e) => e.kind === "precedence");
    const p90s = shown.map((x) => x.eta?.p90).filter((t) => t != null);
    const top = Math.max(hi, ...p90s);
    cur = { rows: shown, kinds: m.kinds, d, edges, alias, fit: [lo - pad, top + pad] };
    calibrated(d);
    setText(said, (folds ? `${folds} more folded to keep within ${RG.BARS} rows: the triangle opens one. ` : "")
      + (rows.length > RG.BARS ? `${RG.BARS} of ${rows.length} rows drawn: narrow it with the search, or choose a kind. ` : "")
      + (d.eta ? `Projected bars: one of ${d.eta.runs} runs of the simulation (levelled: no block more at once than its capacity); the tick its p50, the whisker its p90. Not modelled: a goal that switches a block off, a capacity no block declares.`
        + (Object.keys(d.eta.assumed || {}).length ? ` Assumed: ${Object.entries(d.eta.assumed).map(([b, w]) => `${b}, ${w}`).join("; ")}.` : "")
        : (d.eta_error ? `No estimates: the simulation failed: ${d.eta_error}. `
          : d.eta_pending && !SNAP ? "No estimates yet: the simulation is being worked out. " : "")
        + `Projected bars: levelled by each block's capacity, median times${d.eta_pending && !SNAP ? "; the simulation replaces it when worked out" : ""}.`
          + (d.assumed ? ` No item has finished a state yet: projected at ${dur(d.assumed)} each, assumed.` : "")));
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
    calibrated(d);
    setText(said, rows.length ? `Each block's lanes, at most its capacity at once (leases held over a lowered pool keep theirs until they end): one of ${d.eta.runs} runs of the simulation, levelled. A bar is an item's run; a click opens it. Not modelled: a goal that switches a block off, a capacity no block declares.` : "No block takes these items.");
    draw();
    el.dataset.drawn = String((+el.dataset.drawn || 0) + 1);
  }
  return el;
}

/* every time the Timeline prints: a clock time, rounded up to the minute (or the second; never earlier than it); its
   date and zone too when not today */
const rgClock = (t, now, secs = false) => {
  const c = new Date((secs ? Math.ceil(t) : Math.ceil(t / 60) * 60) * 1000);
  const hm = c.toLocaleTimeString([], { hour12: false, hour: "2-digit", minute: "2-digit", ...(secs ? { second: "2-digit" } : {}) });
  return c.toDateString() === new Date(now * 1000).toDateString() ? hm
    : `${c.toLocaleDateString([], { month: "short", day: "numeric" })} ${hm} ${c.toLocaleTimeString([], { timeZoneName: "short" }).split(" ").pop()}`;
};
/* when the last open item drawn is done, in one sentence: its kind's last finish (p50, p90), never before the
   levelled finish; before the estimates (and at a moment travelled to), the levelled finish itself */
function rgFinish(d) {
  const key = (txt, title = "") => h("span", { class: "rg-key rg-eta", key: "eta", title }, txt);
  if (!d.eta) return d.end > d.now ? key(`done about ${rgClock(d.end, d.now)}, levelled by each block's capacity, median times`
    + (d.eta_pending && !SNAP ? "; the simulation replaces it when worked out" : ""), "The last projected bar's end: each item after what it waits on, each block at most its capacity at once (pool, seats, daemon), each state its kind's median time") : null;
  const last = d.items.filter((x) => x.eta && x.status !== "done").reduce((a, x) => (a && (a.eta.p50 ?? Infinity) >= (x.eta.p50 ?? Infinity) ? a : x), null);
  if (!last) return null;
  const e = d.eta.kinds[last.kind] || last.eta, lo = Math.max(e.p50 ?? Infinity, d.end), who = `last ${last.kind} (${last.id.split("/").pop()})`;
  return key(e.p50 == null ? `${who} beyond the horizon` : `${who} expected ${rgClock(lo, d.now)}, `
      + (e.p90 != null ? `by ${rgClock(Math.max(e.p90, lo), d.now)} at worst (9 in 10)` : `no worst case under 20 runs (${d.eta.runs})`),
    `When the last open ${last.kind} is done: the p50 (expected) and the p90 (at worst) of ${d.eta.runs} runs of a simulation of every open item, each block at most its capacity at once (pool, seats, daemon), from the record's run times, failures and rework; never before the levelled finish (${rgClock(d.end, d.now)}). Not modelled: a goal that switches a block off, a capacity no block declares`
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
    crit ? h("span", { class: "rg-key rg-critkey", key: "crit", title: "The longest chain of unfinished work, by the kinds' median times, as if every block could take all of it at once: not when it is done (that is the finish beside it)" },
      h("i", {}), `critical path ${crit} item${crit === 1 ? "" : "s"}: the longest chain of waits, ignoring capacity`) : null,
    rgFinish(d),
    d.eta?.whatif?.length ? h("span", { class: "rg-key whatif-said", key: "whatif" }, `what if ${d.eta.whatif.join(" and ")} (not saved)`) : null,
    d.cycles.length ? h("span", { class: "rg-key bad", key: "cycle" }, `${d.cycles.length} cycle${d.cycles.length > 1 ? "s" : ""}: ${d.cycles.map((c) => c.join(" → ")).join("; ")}`) : null,
    Object.keys(d.capped || {}).length ? h("span", { class: "muted", key: "capped" }, "(the newest drawn: " + Object.keys(d.capped).join(", ") + " capped)") : null);
}
