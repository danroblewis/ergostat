/* the engines the diagram can be laid out with, chosen by the page's ?layout= (the survey,
   scripts/layout_survey.py, compares them): ELK's layered algorithm with settings of its own, ELK's
   other algorithms, Graphviz's dot, dagre and WebCoLa. Each takes the ELK graph layoutGraph builds
   (parts, open systems as containers, lines) and answers as ELK does, so what follows (flattening,
   pins, valves turned, libavoid's routing) is the same whichever placed the parts. Only the parts'
   places matter: libavoid routes every line again. The other engines are loaded only when asked for. */
"use strict";

const LAYOUT = (() => { try { return new URLSearchParams(location.search).get("layout") || ""; } catch (e) { return ""; } })();

/* ELK's layered settings to try, over the default (diagram.js): on the root and on every open system */
const TIGHT = { "elk.layered.spacing.nodeNodeBetweenLayers": "56", "elk.spacing.nodeNode": "28", "elk.spacing.edgeNode": "14",
                "elk.spacing.componentComponent": "40" };
const ELK_PRESETS = {
  tight: { all: TIGHT },
  post: { all: { "elk.layered.compaction.postCompaction.strategy": "EDGE_LENGTH" } },
  "tight-post": { all: { ...TIGHT, "elk.layered.compaction.postCompaction.strategy": "EDGE_LENGTH" } },
  bk: { all: { "elk.layered.nodePlacement.strategy": "BRANDES_KOEPF", "elk.layered.nodePlacement.bk.fixedAlignment": "BALANCED" } },
  "tight-bk": { all: { ...TIGHT, "elk.layered.nodePlacement.strategy": "BRANDES_KOEPF", "elk.layered.nodePlacement.bk.fixedAlignment": "BALANCED" } },
  thorough: { all: { "elk.layered.thoroughness": "40" } },
  "no-order": { all: { "elk.layered.considerModelOrder.strategy": "NONE" } },
  longest: { all: { "elk.layered.layering.strategy": "LONGEST_PATH" } },
  "wrap-multi": { root: { "elk.layered.wrapping.strategy": "MULTI_EDGE" } },
  "wrap-single": { root: { "elk.layered.wrapping.strategy": "SINGLE_EDGE" } },
  "tight-wrap": { all: TIGHT, root: { "elk.layered.wrapping.strategy": "MULTI_EDGE" } },
  "pack-components": { root: { "elk.layered.compaction.connectedComponents": "true" } },
  // the command lines (a controller to the valve it opens) given to the layering backwards: the
  // controller is then laid out after its valve, beside the stock, instead of before the valve,
  // stretching the pipe into it by two columns (libavoid draws them the right way round)
  feedback: { feedback: true },
  "tight-feedback": { all: TIGHT, feedback: true },
  "tight-feedback-post": { all: { ...TIGHT, "elk.layered.compaction.postCompaction.strategy": "EDGE_LENGTH" }, feedback: true },
  // open systems laid out each on its own (each in rows if long), then the boxes packed
  separate: { separate: true },
  "separate-tight": { separate: true, all: TIGHT },
  "separate-rect": { separate: true, all: TIGHT, root: { "elk.algorithm": "rectpacking" } },
  "separate-feedback-rect": { separate: true, all: TIGHT, feedback: true, root: { "elk.algorithm": "rectpacking" } },
  "separate-wrap": { separate: true, all: { ...TIGHT, "elk.layered.wrapping.strategy": "MULTI_EDGE" } },
  // the combinations: tight, commands reversed, each open system on its own and wrapped into rows
  // when long, the systems' boxes packed
  combo: { separate: true, feedback: true, all: { ...TIGHT, "elk.layered.wrapping.strategy": "MULTI_EDGE" },
           root: { "elk.algorithm": "rectpacking" } },
  "combo-post": { separate: true, feedback: true, all: { ...TIGHT, "elk.layered.wrapping.strategy": "MULTI_EDGE",
                                                         "elk.layered.compaction.postCompaction.strategy": "EDGE_LENGTH" },
                  root: { "elk.algorithm": "rectpacking" } },
  "combo-single": { separate: true, feedback: true, all: { ...TIGHT, "elk.layered.wrapping.strategy": "SINGLE_EDGE" },
                    root: { "elk.algorithm": "rectpacking" } },
  "combo-layered": { separate: true, feedback: true, all: { ...TIGHT, "elk.layered.wrapping.strategy": "MULTI_EDGE" } },
  "combo-nowrap": { separate: true, feedback: true, all: TIGHT, root: { "elk.algorithm": "rectpacking" } },
  // like a circuit board's parts round a chip: each anchor with its satellites as one tight block (a
  // stock with the sensors reading it above it, a valve with the controller commanding only it above
  // it), the blocks laid out as the parts were
  anchors: { separate: true, feedback: true, anchors: true, all: TIGHT },
  "anchors-wrap": { separate: true, feedback: true, anchors: true, all: { ...TIGHT, "elk.layered.wrapping.strategy": "MULTI_EDGE" },
                    root: { "elk.algorithm": "rectpacking" } },
  "anchors-rect": { separate: true, feedback: true, anchors: true, all: TIGHT, root: { "elk.algorithm": "rectpacking" } },
  stress: { separate: true, all: { "elk.algorithm": "stress", "elk.stress.desiredEdgeLength": "120" }, overlap: true },
  force: { separate: true, all: { "elk.algorithm": "force", "elk.spacing.nodeNode": "40" }, overlap: true },
  mrtree: { separate: true, all: { "elk.algorithm": "mrtree", "elk.direction": "RIGHT" } },
};

function elkPreset(graph, g, p) {
  const hulls = [];
  const walk = (n) => { for (const c of n.children || []) if (c.id.startsWith("hull:")) { hulls.push(c); walk(c); } };
  walk(graph);
  // (rectpacking at the top only packs systems' boxes: a view of loose parts stays layered)
  const top = hulls.length ? p.root || {} : Object.fromEntries(Object.entries(p.root || {}).filter(([k, v]) => v !== "rectpacking"));
  Object.assign(graph.layoutOptions, p.all || {}, top);
  for (const h of hulls) Object.assign(h.layoutOptions, p.all || {});
  if (p.feedback) reverseCommands(graph, g);
  const groups = p.anchors ? anchorGroups(graph, g, p) : 0;
  if (p.separate && (hulls.length || groups)) {
    delete graph.layoutOptions["elk.hierarchyHandling"];
    graph.layoutOptions["elk.hierarchyHandling"] = "SEPARATE_CHILDREN";
    proxyEdges(graph);
  }
  return graph;
}

/* each anchor and its satellites made one block (an ELK node holding them, laid out on its own,
   downwards: the satellite above its anchor); flatten() lays the blocks open again */
function anchorGroups(graph, g, p) {
  const parent = {}, node = {};
  const walk = (n) => { for (const c of n.children || []) { parent[c.id] = n; node[c.id] = c; if (c.id.startsWith("hull:")) walk(c); } };
  walk(graph);
  const kind = Object.fromEntries(g.nodes.map((n) => [n.id, n.kind]));
  const ins = (id, k) => g.edges.filter((e) => e.target === id && e.kind === k).map((e) => e.source);
  const outs = (id, k) => g.edges.filter((e) => e.source === id && e.kind === k).map((e) => e.target);
  const taken = new Set(), blocks = [];
  // a valve and the one controller that commands it, when that controller commands nothing else
  for (const c of g.nodes.filter((n) => n.kind === "controller")) {
    const acts = outs(c.id, "action");
    if (acts.length === 1 && kind[acts[0]] === "valve" && ins(acts[0], "action").length === 1) blocks.push([acts[0], c.id]);
  }
  for (const [a] of blocks) taken.add(a);
  for (const [, b] of blocks) taken.add(b);
  // a stock (or variable) and the sensors that read only it
  for (const st of g.nodes.filter((n) => n.kind === "stock" || n.kind === "variable")) {
    const sens = outs(st.id, "measure").filter((x) => kind[x] === "sensor" && !taken.has(x) && ins(x, "measure").length === 1);
    if (sens.length) { blocks.push([st.id, ...sens]); taken.add(st.id); sens.forEach((x) => taken.add(x)); }
  }
  let n = 0;
  for (const ids of blocks) {
    const kids = ids.map((id) => node[id]).filter(Boolean);
    const home = parent[ids[0]];
    if (kids.length < 2 || !kids.every((k) => parent[k.id] === home)) continue;
    const grp = { id: "grp:" + ids[0], children: kids, edges: [], layoutOptions: {
      "elk.algorithm": "layered", "elk.direction": "UP", "elk.padding": "[top=0,left=0,bottom=0,right=0]",
      "elk.spacing.nodeNode": "16", "elk.layered.spacing.nodeNodeBetweenLayers": "22", "elk.spacing.labelNode": "6" } };
    home.children = home.children.filter((c) => !ids.includes(c.id));
    home.children.push(grp);
    n++;
  }
  return n;
}

/* a command line reversed for the layering (and its points put back the right way after) */
function reverseCommands(graph, g) {
  const kind = Object.fromEntries(g.edges.map((e) => [e.id, e.kind]));
  for (const e of graph.edges) if (kind[e.id] === "action") { [e.sources, e.targets] = [e.targets, e.sources]; e.reversed = true; }
}
function unreverse(lay, ids) {
  const all = [];
  const collect = (n) => { for (const e of n.edges || []) all.push(e); for (const c of n.children || []) collect(c); };
  collect(lay);
  for (const e of all) {
    if (!ids.has(e.id)) continue;
    [e.sources, e.targets] = [e.targets, e.sources];
    for (const s of e.sections || []) {
      [s.startPoint, s.endPoint] = [s.endPoint, s.startPoint];
      s.bendPoints = (s.bendPoints || []).slice().reverse();
    }
  }
}

/* with each open system laid out on its own, a line between two of them is given to the layout of
   the systems that hold them as a line between the two boxes (or a part and a box) at that level */
function proxyEdges(graph) {
  const parent = {}, owner = {};
  const walk = (n) => {
    for (const c of n.children || []) {
      parent[c.id] = n.id;
      for (const p of c.ports || []) owner[p.id] = c.id;
      walk(c);
    }
  };
  walk(graph);
  const chain = (id) => { const out = []; for (let x = id; x; x = parent[x]) out.push(x); return out; };
  const byId = { root: graph };                          // every node that holds others: open systems, anchor blocks
  const holders = (n) => { for (const c of n.children || []) if (c.children?.length) { byId[c.id] = c; holders(c); } };
  holders(graph);
  const keep = [], added = new Set(), dropped = [];
  for (const e of graph.edges) {
    const s = owner[e.sources[0]] || e.sources[0], t = owner[e.targets[0]] || e.targets[0];
    const cs = chain(s), ct = chain(t);
    const common = cs.find((x) => ct.includes(x) && x !== s && x !== t);
    if (parent[s] === "root" && parent[t] === "root") { keep.push(e); continue; }
    if (parent[s] === parent[t]) { e.container = parent[s]; (byId[parent[s]].edges ||= []).push(e); continue; }
    dropped.push(e);
    // the ancestors just below the common one
    const a = cs[cs.indexOf(common) - 1], b = ct[ct.indexOf(common) - 1];
    if (a && b && a !== b) {
      const k = `${a}>${b}`;
      if (!added.has(k)) {
        added.add(k);
        (common === "root" ? keep : (byId[common].edges ||= [])).push({ id: "proxy:" + k, sources: [a], targets: [b], container: common });
      }
    }
  }
  graph.edges = keep;
  graph.dropped = dropped;
}

/* ------------------------------------------------- the other engines: parts placed, ELK's shape back */

/* the parts, the open systems and the lines of an ELK graph, flat: each part's footprint is the part
   with its label under it */
function flatModel(graph, g) {
  const nodes = [], hulls = [], parent = {}, owner = {};
  const walk = (n, p) => {
    for (const c of n.children || []) {
      parent[c.id] = p;
      if (c.id.startsWith("hull:")) { hulls.push(c); walk(c, c.id); }
      else { nodes.push(c); for (const q of c.ports || []) owner[q.id] = c.id; }
    }
  };
  walk(graph, null);
  const kind = Object.fromEntries(g.edges.map((e) => [e.id, e.kind]));
  const edges = graph.edges.map((e) => ({ id: e.id, s: owner[e.sources[0]] || e.sources[0], t: owner[e.targets[0]] || e.targets[0], kind: kind[e.id] }))
    .filter((e) => e.s !== e.t);
  for (const c of nodes) {
    const l = (c.labels || [])[0];
    c.fw = l ? Math.max(c.width, l.width) : c.width;
    c.fh = l ? c.height + 6 + l.height : c.height;
  }
  return { nodes, hulls, parent, edges, dir: graph.layoutOptions["elk.direction"] || "RIGHT" };
}

/* the answer in ELK's shape: `at` gives each part's footprint's top-left (any coordinates); open
   systems are drawn round their parts */
function elkShaped(graph, m, at) {
  const PAD = { top: 44, side: 26 };
  const abs = {};                                  // footprints (and outlines), in the engine's coordinates
  for (const c of m.nodes) {
    const p = at[c.id] || { x: 0, y: 0 };
    abs[c.id] = { x: p.x, y: p.y, x1: p.x + c.fw, y1: p.y + c.fh };
  }
  // open systems round what they hold, the innermost first
  const depth = (id) => { let d = 0; for (let x = m.parent[id]; x; x = m.parent[x]) d++; return d; };
  for (const h of [...m.hulls].sort((a, b) => depth(b.id) - depth(a.id))) {
    const kids = (h.children || []).map((k) => abs[k.id]).filter(Boolean);
    abs[h.id] = kids.length ? { x: Math.min(...kids.map((k) => k.x)) - PAD.side, y: Math.min(...kids.map((k) => k.y)) - PAD.top,
                                x1: Math.max(...kids.map((k) => k.x1)) + PAD.side, y1: Math.max(...kids.map((k) => k.y1)) + PAD.side }
                            : { x: 0, y: 0, x1: 120, y1: 80 };
  }
  const all = Object.values(abs);
  const ox = 40 - Math.min(...all.map((b) => b.x)), oy = 40 - Math.min(...all.map((b) => b.y));
  const place = (n, px, py) => {
    for (const c of n.children || []) {
      const b = abs[c.id];
      if (c.id.startsWith("hull:")) {
        c.x = b.x + ox - px; c.y = b.y + oy - py; c.width = b.x1 - b.x; c.height = b.y1 - b.y;
        place(c, b.x + ox, b.y + oy);
        continue;
      }
      c.x = b.x + (c.fw - c.width) / 2 + ox - px; c.y = b.y + oy - py;
      for (const l of c.labels || []) { l.x = (c.width - l.width) / 2; l.y = c.height + 6; }
      for (const q of c.ports || []) {
        if (q.x != null && c.layoutOptions?.["elk.portConstraints"] === "FIXED_POS") continue;
        const side = q.layoutOptions?.["elk.port.side"];
        q.x = side === "WEST" ? 0 : side === "EAST" ? c.width : c.width / 2;
        q.y = side === "NORTH" ? 0 : side === "SOUTH" ? c.height : c.height / 2;
      }
    }
  };
  place(graph, 0, 0);
  const hgt = Object.fromEntries(m.nodes.map((c) => [c.id, c.height]));
  const mid = (id) => { const b = abs[id]; return { x: (b.x + b.x1) / 2 + ox, y: b.y + oy + (hgt[id] || 0) / 2 }; };
  const byOwner = Object.fromEntries(m.edges.map((e) => [e.id, e]));
  for (const e of graph.edges) {
    const f = byOwner[e.id];
    if (!f || !abs[f.s] || !abs[f.t]) continue;
    e.sections = [{ startPoint: mid(f.s), endPoint: mid(f.t), bendPoints: [] }];
    e.container = "root";
  }
  graph.width = Math.max(...all.map((b) => b.x1)) + ox + 40;
  graph.height = Math.max(...all.map((b) => b.y1)) + oy + 40;
  return graph;
}

const VENDOR = {};
function vendorScript(name, path) {              // a library from static/vendor, loaded once, when first asked for
  return (VENDOR[name] ||= new Promise((resolve, reject) => {
    const el = document.createElement("script");
    el.src = "/static/vendor/" + path;
    el.onload = () => resolve(window[name]);
    el.onerror = reject;
    document.head.append(el);
  }));
}

function numOpt(graph, k, d) { const v = parseFloat(graph.layoutOptions[k]); return Number.isFinite(v) ? v : d; }

/* Graphviz's dot (WebAssembly, @hpcc-js/wasm-graphviz): open systems as clusters */
async function layoutDot(graph, g, opts = {}) {
  VENDOR.gv ||= import("/static/vendor/graphviz/index.js").then((mod) => mod.Graphviz.load());
  const gv = await VENDOR.gv;
  const m = flatModel(graph, g);
  const q = (s) => JSON.stringify(s);
  const inch = (px) => (px / 72).toFixed(3);
  const sep = opts.tight ? [0.35, 0.6] : [numOpt(graph, "elk.spacing.nodeNode", 56) / 72, numOpt(graph, "elk.layered.spacing.nodeNodeBetweenLayers", 120) / 72];
  const lines = [`digraph G { graph [rankdir=${m.dir === "DOWN" ? "TB" : "LR"}, nodesep=${sep[0].toFixed(2)}, ranksep=${sep[1].toFixed(2)}, splines=false${opts.extra || ""}];`,
                 "node [shape=box, fixedsize=true, label=\"\"];"];
  const body = (n, ind) => {
    for (const c of n.children || []) {
      if (c.id.startsWith("hull:")) {
        lines.push(`${ind}subgraph ${q("cluster_" + c.id)} { graph [margin=26, label=" ", fontsize=26, labelloc=t];`);
        body(c, ind + "  ");
        lines.push(ind + "}");
      } else lines.push(`${ind}${q(c.id)} [width=${inch(c.fw)}, height=${inch(c.fh)}];`);
    }
  };
  body(graph, "");
  for (const e of m.edges) lines.push(`${q(e.s)} -> ${q(e.t)} [weight=${e.kind === "pipe" ? 8 : 1}${opts.feedback && e.kind === "action" ? ", dir=back, constraint=false" : ""}];`);
  lines.push("}");
  const out = JSON.parse(gv.layout(lines.join("\n"), "json", "dot"));
  const H = +out.bb.split(",")[3];
  const at = {};
  for (const o of out.objects || []) {
    if (!o.pos) continue;
    const [x, y] = o.pos.split(",").map(Number), c = m.nodes.find((n) => n.id === o.name);
    if (c) at[c.id] = { x: x - c.fw / 2, y: H - y - c.fh / 2 };
  }
  return elkShaped(graph, m, at);
}

/* dagre (a compound graph: open systems as its clusters) */
async function layoutDagre(graph, g, opts = {}) {
  const dagre = await vendorScript("dagre", "dagre/dagre.min.js");
  const m = flatModel(graph, g);
  const G = new dagre.graphlib.Graph({ compound: true, multigraph: true });
  G.setGraph({ rankdir: m.dir === "DOWN" ? "TB" : "LR", nodesep: opts.tight ? 28 : numOpt(graph, "elk.spacing.nodeNode", 56),
               ranksep: opts.tight ? 56 : numOpt(graph, "elk.layered.spacing.nodeNodeBetweenLayers", 120), marginx: 20, marginy: 20 });
  G.setDefaultEdgeLabel(() => ({}));
  for (const h of m.hulls) G.setNode(h.id, { paddingTop: 44, paddingLeft: 26, paddingRight: 26, paddingBottom: 26 });
  for (const c of m.nodes) G.setNode(c.id, { width: c.fw, height: c.fh });
  for (const [id, p] of Object.entries(m.parent)) if (p) G.setParent(id, p);
  for (const e of m.edges) {
    const back = opts.feedback && e.kind === "action";
    G.setEdge(back ? e.t : e.s, back ? e.s : e.t, { weight: e.kind === "pipe" ? 8 : 1, minlen: 1 }, e.id);
  }
  dagre.layout(G);
  const at = {};
  for (const c of m.nodes) { const n = G.node(c.id); at[c.id] = { x: n.x - c.fw / 2, y: n.y - c.fh / 2 }; }
  return elkShaped(graph, m, at);
}

/* WebCoLa: constraint layout, the lines' direction as a flow (each line's target at least a gap
   right of its source), no overlaps, open systems as groups; from ELK's places (elkcola) or not */
async function layoutCola(graph, g, opts = {}) {
  const cola = await vendorScript("cola", "webcola/cola.min.js");
  let start = null;
  if (opts.fromElk) {
    const lay = await elk.layout(JSON.parse(JSON.stringify(graph)));
    flatten(lay);
    start = Object.fromEntries(lay.children.map((c) => [c.id, c]));
  }
  const m = flatModel(graph, g);
  const index = Object.fromEntries(m.nodes.map((c, i) => [c.id, i]));
  const ns = m.nodes.map((c, i) => {
    const s = start?.[c.id];
    return { width: c.fw + 24, height: c.fh + 24, x: s ? s.x + c.width / 2 : (i % 8) * 200, y: s ? s.y + c.height / 2 : Math.floor(i / 8) * 150 };
  });
  const gIndex = Object.fromEntries(m.hulls.map((h, i) => [h.id, i]));
  const groups = m.hulls.map((h) => ({ padding: 30,
    leaves: (h.children || []).filter((c) => index[c.id] != null).map((c) => index[c.id]),
    groups: (h.children || []).filter((c) => gIndex[c.id] != null).map((c) => gIndex[c.id]) }));
  const links = m.edges.filter((e) => index[e.s] != null && index[e.t] != null && !(opts.feedback && e.kind === "action"))
    .map((e) => ({ source: index[e.s], target: index[e.t], length: e.kind === "pipe" ? 140 : 110 }));
  const L = new cola.Layout().size([1400, 900]).nodes(ns).links(links).avoidOverlaps(true).handleDisconnected(!start)
    .linkDistance((l) => l.length);
  if (groups.length) L.groups(groups);
  if (!opts.noFlow) L.flowLayout(m.dir === "DOWN" ? "y" : "x", (l) => (links.includes(l) ? 60 : 60));
  L.start(start ? 0 : 30, 20, 40, 0, false, false);
  const at = {};
  m.nodes.forEach((c, i) => { at[c.id] = { x: ns[i].x - c.fw / 2, y: ns[i].y - c.fh / 2 }; });
  return elkShaped(graph, m, at);
}

const ENGINES = {
  dot: (gr, g) => layoutDot(gr, g),
  "dot-tight": (gr, g) => layoutDot(gr, g, { tight: true }),
  "dot-feedback": (gr, g) => layoutDot(gr, g, { tight: true, feedback: true }),
  "dot-newrank": (gr, g) => layoutDot(gr, g, { tight: true, extra: ", newrank=true" }),
  dagre: (gr, g) => layoutDagre(gr, g),
  "dagre-tight": (gr, g) => layoutDagre(gr, g, { tight: true }),
  "dagre-feedback": (gr, g) => layoutDagre(gr, g, { tight: true, feedback: true }),
  cola: (gr, g) => layoutCola(gr, g),
  elkcola: (gr, g) => layoutCola(gr, g, { fromElk: true }),
  "elkcola-free": (gr, g) => layoutCola(gr, g, { fromElk: true, noFlow: true }),
};

/* the layout of an ELK graph by the engine asked for (ELK's layered, as set in diagram.js, by default) */
async function runLayout(graph, g, name = LAYOUT) {
  if (ENGINES[name]) {
    try { return await ENGINES[name](graph, g); } catch (e) { console.warn(`layout ${name} failed: ELK's instead`, e); }
  }
  let p = ELK_PRESETS[name];
  const plain = p ? JSON.parse(JSON.stringify(graph)) : null;
  let lay;
  const keep = (gr) => { const out = elkPreset(gr, g, p); state.dropped = out.dropped || []; state.reversed = new Set(out.edges.concat(out.dropped || []).filter((e) => e.reversed).map((e) => e.id)); return out; };
  const state = { dropped: [], reversed: new Set() };        // (ELK's answer does not carry what is not its own)
  try { lay = await elk.layout(p ? keep(graph) : graph); }
  catch (e) {                                     // ELK's wrapping fails on some graphs: the preset without it, else as given
    console.warn(`ELK failed with ${name}: again without wrapping`, e);
    const q = p && { ...p, all: { ...(p.all || {}), "elk.layered.wrapping.strategy": "OFF" }, root: { ...(p.root || {}), "elk.layered.wrapping.strategy": "OFF" } };
    try { lay = await elk.layout(((p = q), keep(JSON.parse(JSON.stringify(plain))))); }
    catch (e2) { state.dropped = []; state.reversed = new Set(); lay = await elk.layout(plain); }
  }
  unreverse(lay, state.reversed);
  restoreDropped(lay, state.dropped);
  if (p?.overlap) unoverlap(lay);
  return lay;
}

/* the lines left out of a layout of each system on its own (and the stand-ins given for them taken out):
   straight from part to part, until libavoid routes them */
function restoreDropped(lay, dropped) {
  const abs = { root: { x: 0, y: 0 } }, box = {}, owner = {};
  const walk = (n, ox, oy) => {
    for (const c of n.children || []) {
      const x = ox + c.x, y = oy + c.y;
      abs[c.id] = { x, y }; box[c.id] = { x: x + c.width / 2, y: y + c.height / 2 };
      for (const q of c.ports || []) { owner[q.id] = c.id; box[q.id] = { x: x + q.x + (q.width || 0) / 2, y: y + q.y + (q.height || 0) / 2 }; }
      walk(c, x, y);
    }
    n.edges = (n.edges || []).filter((e) => !e.id.startsWith("proxy:"));
  };
  walk(lay, 0, 0);
  for (const e of dropped) {
    const a = box[e.sources[0]], b = box[e.targets[0]];
    if (!a || !b) continue;
    e.sections = [{ startPoint: { ...a }, endPoint: { ...b }, bendPoints: [] }];
    e.container = "root";
    lay.edges.push(e);
  }
}

/* parts that a force or stress layout left on top of each other, pushed apart (top level only) */
function unoverlap(lay) {
  const kids = lay.children || [];
  for (let pass = 0; pass < 20; pass++) {
    let any = false;
    for (let i = 0; i < kids.length; i++) for (let j = i + 1; j < kids.length; j++) {
      const a = kids[i], b = kids[j], m = 20;
      const dx = Math.min(a.x + a.width, b.x + b.width) - Math.max(a.x, b.x) + m, dy = Math.min(a.y + a.height, b.y + b.height) - Math.max(a.y, b.y) + m;
      if (dx > 0 && dy > 0) { any = true; if (dx < dy) b.x += dx; else b.y += dy; }
    }
    if (!any) break;
  }
}
