/* the Process view: the process map of process mining, a directly-follows graph per kind of item (process.py),
   read from the record. Each kind's map is laid out on its own by ELK, left to right in time order, in a frame
   of its own; the frames are stacked, and the lines between kinds (an event on one item caused one on another:
   fan-out and join) are routed between them by libavoid, dashed. Plain ink: how often is the line's weight */
"use strict";

const PM = { PAD: 22, TITLE: 26, GAP: 64, H: 44, PILL: 28 };

function pmShow() { return S.pmShow === "times" ? "times" : "counts"; }
function pmLabel(e) {                                  // a line's words: how many, or the median time between its ends
  if (pmShow() === "times") return e.median != null ? dur(e.median) : "";
  return String(e.count);
}
function pmNodeSub(n) { return `${n.count}×` + (n.items !== n.count ? ` · ${n.items} item${n.items === 1 ? "" : "s"}` : ""); }
function pmNodeSize(n) {
  if (n.kind !== "activity") return [Math.max(76, textWidth(`${n.label} ${n.count}`) + 40), PM.PILL];
  return [Math.round(Math.max(96, textWidth(n.label) * 1.08 + 28, textWidth(pmNodeSub(n)) * 0.95 + 24)), PM.H];
}
function pmSig(g) {                                    // what the layout depends on: the nodes, the lines, their words
  return JSON.stringify(["process", pmShow(), g.nodes.map((n) => n.id + ":" + pmNodeSize(n)[0]),
                         g.edges.map((e) => e.id + ":" + pmLabel(e).length)]);
}

/* each kind's map, laid out alone: activities left to right in time order (the order process.py gives) */
async function pmLayoutKind(kind, nodes, edges) {
  const children = nodes.map((n) => { const [w, hgt] = pmNodeSize(n); return { id: n.id, width: w, height: hgt }; });
  const graph = {
    id: "kind:" + kind, children,
    edges: edges.map((e) => {
      const t = pmLabel(e);
      return { id: e.id, sources: [e.source], targets: [e.target], labels: t ? [{ id: e.id + ":l", text: t, width: textWidth(t) + 8, height: 14 }] : [] };
    }),
    layoutOptions: {
      "elk.algorithm": "layered", "elk.direction": "RIGHT", "elk.edgeRouting": "ORTHOGONAL",
      "elk.layered.considerModelOrder.strategy": "NODES_AND_EDGES", "elk.layered.cycleBreaking.strategy": "MODEL_ORDER",
      "elk.layered.nodePlacement.strategy": "NETWORK_SIMPLEX", "elk.layered.spacing.nodeNodeBetweenLayers": "56",
      "elk.spacing.nodeNode": "30", "elk.spacing.edgeNode": "16", "elk.spacing.edgeEdge": "10",
      "elk.layered.spacing.edgeNodeBetweenLayers": "16", "elk.layered.spacing.edgeEdgeBetweenLayers": "10",
      "elk.edgeLabels.placement": "CENTER", "elk.spacing.edgeLabel": "3", "elk.layered.edgeLabels.sideSelection": "SMART_UP",
      "elk.separateConnectedComponents": "false", "elk.padding": `[top=${PM.PAD + PM.TITLE},left=${PM.PAD},bottom=${PM.PAD},right=${PM.PAD}]`,
    },
  };
  return elk.layout(graph);
}

/* the whole map: each kind's frame laid out alone, then the frames packed in rows (shelves) to the screen's
   shape, in the kinds' order; the parts and lines in the page's coordinates */
async function pmLayout(g, aspect = 1.6) {
  const kinds = g.kinds.filter((k) => k.drawn).map((k) => k.name);
  const lay = { children: [], edges: [], containers: [], width: 0, height: 0 };
  const follows = g.edges.filter((e) => e.kind === "follows");
  const maps = [];
  for (const k of kinds) {
    const nodes = g.nodes.filter((n) => n.itemKind === k);
    if (nodes.length) maps.push([k, await pmLayoutKind(k, nodes, follows.filter((e) => e.itemKind === k))]);
  }
  const area = maps.reduce((a, [, m]) => a + (m.width + PM.GAP) * (m.height + PM.GAP), 0);
  const widest = Math.max(0, ...maps.map(([, m]) => m.width));
  const rowW = Math.max(widest, Math.sqrt(area * aspect));
  let x = 0, y = 0, rowH = 0;
  for (const [k, m] of maps) {
    if (x > 0 && x + m.width > rowW) { x = 0; y += rowH + PM.GAP; rowH = 0; }
    const dx = x, dy = y;
    for (const c of m.children) lay.children.push({ ...c, x: c.x + dx, y: c.y + dy });
    for (const le of m.edges || []) {
      for (const sec of le.sections || []) for (const p of [sec.startPoint, sec.endPoint, ...(sec.bendPoints || [])]) { p.x += dx; p.y += dy; }
      for (const l of le.labels || []) { l.x += dx; l.y += dy; }
      lay.edges.push(le);
    }
    lay.containers.push({ id: "hull:" + k, name: k, x: dx, y: dy, width: m.width, height: m.height });
    lay.width = Math.max(lay.width, dx + m.width);
    lay.height = Math.max(lay.height, dy + m.height);
    x += m.width + PM.GAP;
    rowH = Math.max(rowH, m.height);
  }
  // the lines between kinds: stand-ins, drawn grey, until libavoid's come
  const box = Object.fromEntries(lay.children.map((c) => [c.id, c]));
  for (const e of g.edges.filter((e) => e.kind === "caused")) {
    const a = box[e.source], b = box[e.target];
    if (!a || !b) continue;
    const [sd, td] = pmSides(a, b);
    const s0 = pmSidePoint(a, sd, 0.5), t0 = pmSidePoint(b, td, 0.5);
    const my = sd === td ? Math.max(s0.y, t0.y) + 16 : (s0.y + t0.y) / 2;
    const mid = [{ x: s0.x, y: my }, { x: t0.x, y: my }];
    lay.edges.push({ id: e.id, cross: true, stale: true, sections: [{ startPoint: s0, bendPoints: mid, endPoint: t0 }] });
  }
  lay.ox = 0; lay.oy = 0;
  return lay;
}
/* which sides a line between two kinds' parts leaves and arrives by: top or bottom, facing each other (a map's
   own lines take the left and right, as time runs); side by side, both from below */
function pmSides(a, b) {
  if (b.y >= a.y + a.height) return ["down", "up"];
  if (a.y >= b.y + b.height) return ["up", "down"];
  return ["down", "down"];
}
function pmSidePoint(c, d, f) {
  return d === "up" ? { x: c.x + c.width * f, y: c.y } : d === "down" ? { x: c.x + c.width * f, y: c.y + c.height }
       : d === "left" ? { x: c.x, y: c.y + c.height * f } : { x: c.x + c.width, y: c.y + c.height * f };
}

/* the lines between kinds, routed by libavoid around every part and every line's words: each leaves its part
   on the side facing the other kind and arrives the same way, a point of its own at each end */
function pmRoute(lay, g) {
  lay.routing = false;
  lay.whenRouted = Promise.resolve();
  const cross = lay.edges.filter((le) => le.cross);
  if (!cross.length || !AV.mode) return;
  const byId = Object.fromEntries(g.edges.map((e) => [e.id, e]));
  const box = Object.fromEntries(lay.children.map((c) => [c.id, c]));
  const ends = {};
  for (const le of cross) {
    const e = byId[le.id];
    const [sd, td] = pmSides(box[e.source], box[e.target]);
    (ends[e.source] ||= []).push([le.id, "s", sd]);
    (ends[e.target] ||= []).push([le.id, "t", td]);
  }
  const labels = (lay.edges.filter((le) => !le.cross).flatMap((le) => le.labels || []));
  const shapes = [], pin = {};
  for (const c of lay.children) {
    const mine = ends[c.id] || [], pins = [];
    const per = {};
    for (const [, , dir] of mine) per[dir] = (per[dir] || 0) + 1;
    const at = {};
    mine.forEach(([id, w, dir], i) => {                // each its own point, spread along its side
      at[dir] = (at[dir] || 0) + 1;
      const cls = 10 + i, p = pmSidePoint({ x: 0, y: 0, width: 1, height: 1 }, dir, at[dir] / (per[dir] + 1));
      pins.push({ cls, x: p.x, y: p.y, dir, shared: false, abs: false });
      pin[`${id}|${w}`] = cls;
    });
    shapes.push({ id: c.id, x: c.x, y: c.y, w: c.width, h: c.height, pins, labels: [] });
  }
  labels.forEach((l, i) => shapes.push({ id: "label:" + i, x: l.x, y: l.y, w: Math.max(1, l.width), h: Math.max(1, l.height), pins: [], labels: [] }));
  const conns = cross.map((le) => ({ id: le.id, s: byId[le.id].source, sp: pin[`${le.id}|s`], t: byId[le.id].target, tp: pin[`${le.id}|t`] }));
  const spec = { shapes, conns, crossingPenalty: 200, nudgeCommon: false };
  const seq = ++AV.seq;
  const done = (m) => {
    if (m && !m.skipped) {
      const byLe = Object.fromEntries(lay.edges.map((le) => [le.id, le]));
      for (const [id, pts] of Object.entries(m.routes)) setRoute(byLe[id], pts.map(([x, y]) => ({ x, y })));
      AV.ms = m.ms; AV.invalid = m.invalid;
    }
    lay.routing = false;
  };
  lay.routing = true;
  if (AV.mode === "page") { done(AV.core.route(spec)); return; }
  lay.whenRouted = new Promise((resolve) => {
    AV.waiting[`routed:${seq}:`] = (m) => { done(m); if (!m.skipped && lay === S.layout) S.redraw?.(); resolve(); };
  });
  AV.worker.postMessage({ type: "route", seq, spec });
}

function pmNode(n, w, hgt, most) {
  const g = s("g");
  if (n.kind !== "activity") {                         // a kind's start and end: pills, a play and a stop
    g.append(s("rect", { class: "hit", width: w, height: hgt, rx: hgt / 2, fill: "var(--panel)", stroke: "var(--ink)", "stroke-width": 1.4 }));
    const cy = hgt / 2;
    g.append(n.kind === "start" ? s("path", { d: `M13,${cy - 5} L21,${cy} L13,${cy + 5} Z`, fill: "var(--ink)" })
                                : s("rect", { x: 12, y: cy - 4.5, width: 9, height: 9, fill: "var(--ink)" }));
    g.append(s("text", { x: 28, y: cy + 4, class: "t-label" }, n.label, s("tspan", { class: "t-sub", dx: 6 }, String(n.count))));
    return g;
  }
  const f = most ? Math.sqrt(n.count / most) : 0;     // the more it happened, the darker: ink at most an eighth
  g.append(s("rect", { class: "hit", width: w, height: hgt, rx: 6, fill: "var(--panel)", stroke: "var(--ink)", "stroke-width": 1.2 }));
  g.append(s("rect", { x: 0.6, y: 0.6, width: w - 1.2, height: hgt - 1.2, rx: 5.5, fill: "var(--ink)", opacity: (0.02 + 0.10 * f).toFixed(3), "pointer-events": "none" }));
  g.append(s("text", { x: w / 2, y: 18, "text-anchor": "middle", class: "t-label" }, n.label));
  g.append(s("text", { x: w / 2, y: 34, "text-anchor": "middle", class: "t-sub" }, pmNodeSub(n)));
  return g;
}

function pmDraw(svg, g, lay) {
  S.drawN = (S.drawN || 0) + 1;
  const byId = Object.fromEntries(g.nodes.map((n) => [n.id, n]));
  const edgeById = Object.fromEntries(g.edges.map((e) => [e.id, e]));
  S.edgeById = edgeById;
  const most = {}, mostLine = {};
  for (const n of g.nodes) most.all = Math.max(most.all || 0, n.count);
  for (const e of g.edges) { const k = e.kind === "caused" ? "~" : "|"; mostLine[k] = Math.max(mostLine[k] || 0, e.count); }   // one scale for the map
  const vp = s("g", { id: "viewport" });
  const frames = s("g", { class: "pm-frames" });
  for (const f of lay.containers) {
    const k = g.kinds.find((x) => x.name === f.name) || {};
    frames.append(s("g", { class: "pm-frame", "data-kind": f.name },
      s("rect", { x: f.x, y: f.y, width: f.width, height: f.height, rx: 10 }),
      s("text", { x: f.x + 14, y: f.y + 22, class: "pm-title" }, f.name,
        s("tspan", { class: "t-sub", dx: 8 }, `${k.items} item${k.items === 1 ? "" : "s"} · ${k.by}`))));
  }
  const edgesG = s("g");
  for (const le of lay.edges) {
    const e = edgeById[le.id];
    const pts = edgePoints(le);
    if (!e || pts.length < 2) continue;
    const cross = e.kind === "caused";
    const top = mostLine[cross ? "~" : "|"] || 1;
    const wgt = (cross ? 1.1 : 1.2) + (cross ? 2.2 : 4.8) * Math.sqrt(e.count / top);
    const eg = s("g", { class: ["edge", "pm-" + e.kind, e.rework ? "rework" : "", le.stale ? "stale" : ""].join(" "), "data-id": e.id,
                        "data-nodes": `${e.source} ${e.target}`, "data-link": `${e.kind}:${e.source}>${e.target}`,
                        onpointerenter: () => { if (!S.dragging) hoverEdge(e); }, onpointerleave: () => hoverEdge(null) });
    const d = roundedPath(pts, 8);
    eg.append(s("path", { d, class: "info pm-line", style: `stroke-width:${wgt.toFixed(2)}` }));
    const ah = arrowHead(pts, "head", 6 + wgt * 0.9);
    ah.style.setProperty("--head", cross ? "var(--muted)" : "var(--ink)");
    eg.append(ah);
    const text = (e.rework && !cross ? "↺ " : "") + pmLabel(e);
    const l = (le.labels || [])[0];
    if (pmLabel(e)) {
      let x, y, anchor = "middle";
      if (l) { x = l.x + l.width / 2; y = l.y + 11; }
      else {                                            // a line between kinds: on its longest straight stretch
        let best = [pts[0], pts[1]], len = -1;
        for (let i = 1; i < pts.length; i++) { const L = Math.hypot(pts[i].x - pts[i - 1].x, pts[i].y - pts[i - 1].y); if (L > len) { len = L; best = [pts[i - 1], pts[i]]; } }
        const vertical = Math.abs(best[0].x - best[1].x) < 1;
        x = (best[0].x + best[1].x) / 2 + (vertical ? 6 : 0); y = (best[0].y + best[1].y) / 2 + (vertical ? 4 : -5);
        anchor = vertical ? "start" : "middle";
      }
      eg.append(s("text", { class: "elabel", x, y, "text-anchor": anchor, "paint-order": "stroke", stroke: "var(--bg)", "stroke-width": 4,
                            "stroke-linejoin": "round" }, text));
    }
    eg.append(s("path", { d, class: "edge-hit" }));
    edgesG.append(eg);
  }
  const nodesG = s("g");
  for (const ln of lay.children) {
    const n = byId[ln.id];
    if (!n) continue;
    const ng = s("g", { class: `node k-${n.kind} pm-node`, transform: `translate(${ln.x},${ln.y})`, "data-id": n.id,
                        onpointerdown: (ev) => { if (!ev.button) S.downOn = n.id; } });
    ng.append(pmNode(n, ln.width, ln.height, most.all));
    nodesG.append(ng);
  }
  vp.append(frames, edgesG, nodesG);
  svg.replaceChildren(vp);
  svg.classList.remove("sd");
  applyView(svg);
  if (S.hoverKey || S.selKey) trace(S.hoverKey || S.selKey);
  for (const x of svg.querySelectorAll(".node.sel")) x.classList.remove("sel");
  if (S.pmSel) svg.querySelector(`.node[data-id="${CSS.escape(S.pmSel)}"]`)?.classList.add("sel");
}

async function drawProcessView(svg, g) {
  for (const n of g.nodes) n.systems = [n.itemKind];   // (each part is inside its kind's frame: the audit reads it)
  const sg = pmSig(g);
  if (sg === S.graphSig && S.layout) { if (!S.layout.routing) pmDraw(svg, g, S.layout); return S.layout; }
  await avoidLoad();
  const r = svg.getBoundingClientRect();
  const lay = await pmLayout(g, r.width && r.height ? r.width / Math.max(r.height - 80, 200) : 1.6);
  S.layouts = (S.layouts || 0) + 1;
  S.graphSig = sg;
  S.layout = lay;
  pmDraw(svg, g, lay);
  pmRoute(lay, g);
  if (!lay.routing) pmDraw(svg, g, lay);
  return lay;
}

/* ---------------------------------------------------------------- the side panel */

const PM_WORD = { "^": "start", "$": "end" };
function pmStamp(t) { return new Date(t * 1000).toISOString().replace(/\.\d+Z$/, "Z"); }
function pmSet(params, says, how) {                   // the items behind it, as the side panel lists them (itemsets.js)
  const g = S.graph;
  return itemsSection({ of: { kind: "flow" }, says, how,
                        set: { ...params, by: [g.by], moved_since: [pmStamp(g.since)], moved_until: [pmStamp(g.until)] } });
}
function pmAct(a) { return PM_WORD[a] || a; }

function openProcessNode(n) {
  const g = S.graph;
  S.pmSel = n.id;
  for (const x of document.querySelectorAll(".node.sel")) x.classList.remove("sel");
  document.querySelector(`.node[data-id="${CSS.escape(n.id)}"]`)?.classList.add("sel");
  const into = g.edges.filter((e) => e.target === n.id && e.source !== n.id), out = g.edges.filter((e) => e.source === n.id && e.target !== n.id);
  const loop = g.edges.find((e) => e.source === n.id && e.target === n.id);
  const what = n.kind === "start" ? `where ${n.itemKind} items start: their first event, in the window`
    : n.kind === "end" ? `where ${n.itemKind} items end: they reached a state the kind counts as finished, in the window`
    : g.by === "states" && (g.kinds.find((k) => k.name === n.itemKind)?.states || []).includes(n.activity)
      ? `a state of ${n.itemKind}: each time an item entered it, in the window`
      : `an event about a ${n.itemKind} item: each time one was recorded, in the window`;
  const lines = (es, other) => es.length ? h("table", {}, es.map((e) => h("tr", { class: "click", onclick: () => openProcessEdge(e) },
    h("td", {}, e.kind === "caused" ? `${(other(e) || "").split(":")[1]} · ${pmAct(other(e).split(":").slice(2).join(":"))}` : pmAct(g.nodes.find((x) => x.id === other(e))?.activity ?? "")),
    h("td", { class: "muted" }, e.kind === "caused" ? "caused" : e.rework ? "rework" : ""),
    h("td", { class: "num" }, String(e.count)), h("td", { class: "num muted" }, e.median != null ? dur(e.median) : ""))))
    : h("p", { class: "muted" }, "None in the window.");
  showDetail(h("div", { class: "kind" }, n.kind === "activity" ? (g.by === "states" ? "State" : "Activity") : n.kind === "start" ? "Start" : "End"),
    h("h2", {}, pmAct(n.activity), h("span", { class: "muted" }, ` (${n.itemKind})`)),
    whatIs("activity"),
    h("p", { class: "muted" }, what[0].toUpperCase() + what.slice(1) + "."),
    dl([["happened", `${n.count} time${n.count === 1 ? "" : "s"} in the window`], ["items", String(n.items)],
        ["again on one item", loop ? `${loop.count} time${loop.count === 1 ? "" : "s"}, median ${loop.median != null ? dur(loop.median) : "–"} apart` : null]]),
    h("h3", {}, "Came from"), lines(into, (e) => e.source),
    h("h3", {}, "Went to"), lines(out, (e) => e.target),
    pmSet({ kind: [n.itemKind], through: [n.activity] }, `${n.itemKind}, ${n.kind === "activity" ? "through " + n.activity : n.kind === "start" ? "started" : "ended"}`,
          "the items behind this node of the process map, in its window"));
}

function openProcessEdge(e) {
  const g = S.graph;
  const nodeOf = (id) => g.nodes.find((x) => x.id === id) || { activity: id.split(":").slice(2).join(":"), itemKind: id.split(":")[1] };
  const a = nodeOf(e.source), b = nodeOf(e.target);
  const link = (n) => h("a", { href: "#", onclick: (ev) => { ev.preventDefault(); openProcessNode(n); } }, pmAct(n.activity));
  let kids;
  if (e.kind === "caused") {
    kids = [h("div", { class: "kind" }, "Caused, across kinds"), h("h2", {}, `${a.itemKind} ${pmAct(a.activity)}`, " ⇢ ", `${b.itemKind} ${pmAct(b.activity)}`), whatIs("caused"),
      h("p", { class: "muted" }, `An event on a ${a.itemKind} item caused one on a ${b.itemKind} item (its causedby, directly or through a run), ${e.count} time${e.count === 1 ? "" : "s"}: ` +
        (e.causes < e.items ? `${e.causes} ${a.itemKind} item${e.causes === 1 ? "" : "s"} fanned out into ${e.items} ${b.itemKind} items.` :
         e.causes > e.items ? `${e.causes} ${a.itemKind} items joined into ${e.items}.` : "one for one.")),
      dl([["cause", h("span", {}, link(a), ` on ${e.causes} ${a.itemKind} item${e.causes === 1 ? "" : "s"}`)],
          ["effect", h("span", {}, link(b), ` on ${e.items} ${b.itemKind} item${e.items === 1 ? "" : "s"}`)],
          ["median time", e.median != null ? dur(e.median) : null]]),
      h("h3", {}, "Event types"),
      h("table", {}, (e.types || []).map((t) => h("tr", {}, h("td", { class: "mono" }, t.cause), h("td", {}, "→"), h("td", { class: "mono" }, t.effect), h("td", { class: "num" }, String(t.count))))),
      pmSet({ kind: [b.itemKind], caused: [`${a.itemKind}:${a.activity}>${b.activity}`] }, `${b.itemKind}, ${pmAct(b.activity)} caused by ${pmAct(a.activity)} on a ${a.itemKind}`,
            "the items on which the effect happened, in the window")];
  } else {
    const word = e.source === e.target ? "again, on the same item (a loop)" : e.rework ? "back to an earlier step: rework" : "next";
    kids = [h("div", { class: "kind" }, e.rework ? "Directly follows: rework" : "Directly follows"),
      h("h2", {}, pmAct(a.activity), " → ", pmAct(b.activity), h("span", { class: "muted" }, ` (${e.itemKind})`)), whatIs("follows"),
      h("p", { class: "muted" }, `On one ${e.itemKind} item, ${pmAct(b.activity)} came ${word} after ${pmAct(a.activity)}, with nothing about the item between.`),
      dl([["from", link(a)], ["to", link(b)], ["times", `${e.count} in the window, on ${e.items} item${e.items === 1 ? "" : "s"}`],
          ["median time between", e.median != null ? dur(e.median) : e.source.endsWith(":^") || e.target.endsWith(":$") ? null : "not known"]]),
      pmSet({ kind: [e.itemKind], followed: [`${a.activity}>${b.activity}`] }, `${e.itemKind}, ${pmAct(a.activity)} → ${pmAct(b.activity)}`,
            "the items that went along this line, in the window")];
  }
  showDetail(...kids);
  S.selKey = `${e.kind}:${e.source}>${e.target}`;
  trace(S.selKey);
}

/* the side list: what was read, what was left out, and the kinds */
function pmSide(side, g) {
  side.append(h("h3", {}, "The process map"));
  const notes = [`${g.events} event${g.events === 1 ? "" : "s"} in the window; nodes are ${g.by === "states" ? "the states items entered" : "the event types about items"}.`];
  if (g.capped?.events) notes.push(`Only the newest ${g.most.events.toLocaleString()} events were read.`);
  if (g.capped?.items) notes.push("Only the latest moved items were read.");
  if (g.capped?.nodes || g.capped?.edges) notes.push(`Too many to draw: the ${g.most.nodes} most frequent nodes and ${g.most.edges} most frequent lines are drawn, of ${g.total.nodes} and ${g.total.edges}.`);
  if (g.paths > 0) notes.push(`Paths under ${Math.round(g.paths * 100)}% of their kind's most frequent hidden: ${g.hidden.edges} line${g.hidden.edges === 1 ? "" : "s"}, ${g.hidden.nodes} node${g.hidden.nodes === 1 ? "" : "s"}.`);
  side.append(...notes.map((t) => h("p", { class: "muted small" }, t)));
  side.append(h("h3", {}, "Kinds", h("span", { class: "muted" }, ` ${g.kinds.length}`)));
  if (!g.kinds.length) side.append(h("div", { class: "muted" }, "No kinds of item here."));
  for (const k of g.kinds) side.append(h("div", { class: "looprow" }, h("b", {}, h("a", { href: `/items?kind=${encodeURIComponent(k.name)}` }, k.name)), h("span"),
    h("div", { class: "sub" }, k.drawn ? `${k.items} item${k.items === 1 ? "" : "s"} in the window, by ${k.by}` : "nothing on the record in the window")));
}

function processLegend() {
  const row = (svgTxt, text) => [h("span", { html: `<svg width="30" height="20">${svgTxt}</svg>` }), h("span", {}, text)];
  return h("div", { class: "legend" },
    row('<rect x="2" y="3" width="26" height="14" rx="3" fill="var(--panel)" stroke="var(--ink)" stroke-width="1.2"/>',
        "an activity: a state its items entered, or an event type about them (States or Events); how many times in the window, darker the more"),
    row('<rect x="2" y="4" width="26" height="12" rx="6" fill="var(--panel)" stroke="var(--ink)" stroke-width="1.2"/><path d="M8,7 L13,10 L8,13 Z" fill="var(--ink)"/>',
        "start: items whose first event is in the window; end (a square): items that reached a state their kind counts as finished"),
    row('<path d="M1 10 H22" stroke="var(--ink)" stroke-width="1.4"/><path d="M21 6 L28 10 L21 14 Z" fill="var(--ink)"/>',
        "directly follows: on one item, the second came next after the first; heavier, more often; its number is how many times (Counts) or the median time between (Times)"),
    row('<path d="M1 10 H22" stroke="var(--ink)" stroke-width="3.5"/><path d="M21 5 L29 10 L21 15 Z" fill="var(--ink)"/>', "a busy path"),
    row('<text x="3" y="14" font-size="12" fill="var(--muted)">↺</text>', "a line back to an earlier step (right to left), or a loop on one activity: rework"),
    row('<path d="M1 10 H22" stroke="var(--muted)" stroke-width="1.4" stroke-dasharray="5 4"/><path d="M21 6 L28 10 L21 14 Z" fill="var(--muted)"/>',
        "caused, across kinds: an event on an item of one kind caused one on another (fan-out, join)"),
    row('<rect x="2" y="2" width="26" height="16" rx="4" fill="none" stroke="var(--line-strong)"/>', "a kind of item: its own map, left to right in time order"),
    h("span", { class: "sym" }, "%"), h("span", {}, "the Paths slider hides lines rarer than that share of their kind's most frequent, as process mining tools do"));
}
