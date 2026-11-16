/* how ELK lays the diagram out: the settings layoutGraph's ELK graph is given, chosen by the page's
   ?layout= (scripts/layout_survey.py compares them on every example and view). Only the parts' places
   matter: libavoid routes every line again (avoid.js), so the graph ELK is given can differ from the one
   drawn: command lines reversed, lines between systems given as lines between their boxes, a part and
   its satellites as one block. Graphviz's dot, dagre and WebCoLa were tried the same way (the commit
   that brought this file in has them) and placed the parts no better. */
"use strict";

/* the default (the survey's choice): ELK layered, tight, with each part and its satellites as one block,
   the command lines reversed for the layering, each open system laid out on its own, the systems wrapped
   into rows, and one chain far wider than the screen wrapped too. ?layout=elk is ELK as it was set
   before (diagram.js alone); any other name below is one that was tried */
const DEFAULT_LAYOUT = "anchors-wrap";
const LAYOUT = (() => { try { return new URLSearchParams(location.search).get("layout") || DEFAULT_LAYOUT; } catch (e) { return DEFAULT_LAYOUT; } })();

const TIGHT = { "elk.layered.spacing.nodeNodeBetweenLayers": "56", "elk.spacing.nodeNode": "28", "elk.spacing.edgeNode": "14",
                "elk.spacing.componentComponent": "40" };
const MID = { "elk.layered.spacing.nodeNodeBetweenLayers": "72", "elk.spacing.nodeNode": "36", "elk.spacing.edgeNode": "18",
              "elk.spacing.componentComponent": "48" };
const WRAP = { "elk.layered.wrapping.strategy": "MULTI_EDGE" };
const WRAP_WIDE = 1600;          // a chain wider than this (it does not fit the screen at a legible zoom) and
const WRAP_OVER = 3.5;           // wider than tall by this much is laid out again, wrapped into rows
const WRAP_LINES = 400;          // past this many lines nothing is wrapped: libavoid's routing across rows takes long

/* ELK's settings, over diagram.js's: `all` on the root and on every open system, `root` on the root,
   `hullsRoot` on the root when systems are open; feedback, separate, anchors and wrapOver as below */
const ELK_PRESETS = {
  tight: { all: TIGHT },
  post: { all: { "elk.layered.compaction.postCompaction.strategy": "EDGE_LENGTH" } },
  "tight-post": { all: { ...TIGHT, "elk.layered.compaction.postCompaction.strategy": "EDGE_LENGTH" } },
  bk: { all: { "elk.layered.nodePlacement.strategy": "BRANDES_KOEPF", "elk.layered.nodePlacement.bk.fixedAlignment": "BALANCED" } },
  thorough: { all: { "elk.layered.thoroughness": "40" } },
  longest: { all: { "elk.layered.layering.strategy": "LONGEST_PATH" } },
  "wrap-multi": { root: WRAP },
  "wrap-single": { root: { "elk.layered.wrapping.strategy": "SINGLE_EDGE" } },
  "pack-components": { root: { "elk.layered.compaction.connectedComponents": "true" } },
  // the command lines (a controller to the valve it opens) given to the layering backwards: the
  // controller is then laid out after its valve, beside the stock, instead of before the valve,
  // stretching the pipe into it by two columns (libavoid draws them the right way round)
  feedback: { feedback: true },
  "tight-feedback-post": { all: { ...TIGHT, "elk.layered.compaction.postCompaction.strategy": "EDGE_LENGTH" }, feedback: true },
  // open systems laid out each on its own, then the boxes packed (rectpacking) or wrapped
  "separate-rect": { separate: true, all: TIGHT, feedback: true, root: { "elk.algorithm": "rectpacking" } },
  "separate-wrap": { separate: true, all: { ...TIGHT, ...WRAP } },
  // as a circuit board's parts sit by the pin of the chip they serve: each anchor with its satellites as
  // one tight block (a valve with the controller commanding only it above it, a stock with the sensors
  // reading only it above it), the blocks laid out as the parts were
  anchors: { separate: true, feedback: true, anchors: true, all: TIGHT },
  "anchors-mid": { separate: true, feedback: true, anchors: true, all: MID },
  "anchors-rect": { separate: true, feedback: true, anchors: true, all: TIGHT, root: { "elk.algorithm": "rectpacking" } },
  "anchors-wrap-all": { separate: true, feedback: true, anchors: true, all: { ...TIGHT, ...WRAP } },
  "anchors-wrap": { separate: true, feedback: true, anchors: true, all: TIGHT, hullsRoot: WRAP, wrapOver: WRAP_OVER, align: true },
  "anchors-wrap-unaligned": { separate: true, feedback: true, anchors: true, all: TIGHT, hullsRoot: WRAP, wrapOver: WRAP_OVER },
  // ELK's other algorithms, each open system on its own
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
  Object.assign(graph.layoutOptions, p.all || {}, top, hulls.length && g.edges.length <= WRAP_LINES ? p.hullsRoot || {} : {});
  for (const h of hulls) Object.assign(h.layoutOptions, p.all || {});
  for (const id of p.wrap || []) {                // the chains a first layout found too long, wrapped into rows
    const n = id === "root" ? graph : hulls.find((h) => h.id === id);
    if (n) Object.assign(n.layoutOptions, WRAP, { "elk.aspectRatio": "2" });
  }
  if (p.feedback) reverseCommands(graph, g);
  const groups = p.anchors ? anchorGroups(graph, g) : 0;
  if (p.separate && (hulls.length || groups)) {
    graph.layoutOptions["elk.hierarchyHandling"] = "SEPARATE_CHILDREN";
    proxyEdges(graph);
  }
  return graph;
}

/* each anchor and its satellites made one block (an ELK node holding them, laid out on its own, the
   satellite above its anchor); flatten() (diagram.js) lays the blocks open again */
function anchorGroups(graph, g) {
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
  graph.dropped = dropped;                             // (put back after the layout, straight, for libavoid to route)
}

/* the layout of layoutGraph's ELK graph, with the settings asked for (?layout=), in ELK's answer's shape */
async function runLayout(graph, g, name = LAYOUT) {
  return runLayoutWith(graph, g, ELK_PRESETS[name], name);
}
async function runLayoutWith(graph, g, preset, name = "") {
  let p = preset;
  const plain = p ? JSON.parse(JSON.stringify(graph)) : null;
  let lay;
  const keep = (gr) => { const out = elkPreset(gr, g, p); state.dropped = out.dropped || []; state.reversed = new Set(out.edges.concat(out.dropped || []).filter((e) => e.reversed).map((e) => e.id)); return out; };
  const state = { dropped: [], reversed: new Set() };        // (ELK's answer does not carry what is not its own)
  try { lay = await elk.layout(p ? keep(graph) : graph); }
  catch (e) {                                     // ELK's wrapping fails on some graphs: the preset without it, else as given
    console.warn(`ELK failed with ${name}: again without wrapping`, e);
    const q = p && { ...p, wrap: [], all: { ...(p.all || {}), "elk.layered.wrapping.strategy": "OFF" }, root: { ...(p.root || {}), "elk.layered.wrapping.strategy": "OFF" } };
    try { lay = await elk.layout(((p = q), keep(JSON.parse(JSON.stringify(plain))))); }
    catch (e2) { state.dropped = []; state.reversed = new Set(); lay = await elk.layout(plain); }
  }
  if (p?.wrapOver && !p.wrap && g.edges.length <= WRAP_LINES) {    // one chain far wider than tall (a drawn system's, an open one's)
    const long = [], chain = (n) => oneChain(n, g) && n.width > WRAP_WIDE && n.width / n.height > p.wrapOver;
    if (!lay.children.some((c) => c.id.startsWith("hull:")) && chain(lay)) long.push("root");
    const walk = (n) => { for (const c of n.children || []) if (c.id.startsWith("hull:")) {
      if (!(c.children || []).some((k) => k.id.startsWith("hull:")) && chain(c)) long.push(c.id);
      walk(c);
    } };
    walk(lay);
    if (long.length) return runLayoutWith(plain, g, { ...p, wrap: long });
  }
  unreverse(lay, state.reversed);
  restoreDropped(lay, state.dropped);
  if (p?.align) alignBlocks(lay, g);
  if (p?.overlap) unoverlap(lay);
  return lay;
}

/* ELK centres a block as a whole, so the part a pipe runs through can sit off the pipe's line, and what
   the pipe joins with it: left to right, each block and each loose part on a pipe is slid up or down
   until it lines up with what the pipe comes from (or, first in the row, goes to), by a jog's height at
   most and where nothing is in the way */
function alignBlocks(lay, g) {
  const pipes = g.edges.filter((e) => e.kind === "pipe");
  const visit = (n) => {
    const kids = n.children || [];
    const where = {};                                  // each part's sibling here, and its centre in n's coordinates
    for (const c of kids) {
      if (c.id.startsWith("grp:")) for (const k of c.children || []) where[k.id] = { c, y: () => c.y + k.y + k.height / 2 };
      else if (!c.id.startsWith("hull:")) where[c.id] = { c, y: () => c.y + c.height / 2 };
    }
    const foot = (c) => {                              // a sibling's box, with the labels of what it holds (a valve's
      const parts = c.id.startsWith("grp:") ? (c.children || []).map((k) => [k, k.x, k.y]) : [[c, 0, 0]];   // above too: it may turn)
      const xs = [0, c.width], ys = [0, c.height];
      for (const [k, kx, ky] of parts) for (const l of k.labels || []) {
        const flips = k.id.startsWith("flow:");
        xs.push(kx + l.x, kx + l.x + l.width); ys.push(ky + l.y + l.height, flips ? ky - l.height - 4 : ky);
      }
      return { x: c.x + Math.min(...xs), y: c.y + Math.min(...ys), w: Math.max(...xs) - Math.min(...xs), h: Math.max(...ys) - Math.min(...ys) };
    };
    // clouds last, each to its valve: a valve lines up with its stock, never with its cloud
    const cloud = (c) => c.id.startsWith("cloud:");
    const items = kids.filter((c) => !c.id.startsWith("hull:")).sort((a, b) => cloud(a) - cloud(b) || a.x - b.x);
    const done = new Set();
    for (const b of items) {
      const mine = new Set(b.id.startsWith("grp:") ? (b.children || []).map((k) => k.id) : [b.id]);
      const ends = pipes.flatMap((e) => (mine.has(e.source) && where[e.target]?.c !== b && where[e.target] ? [[e.source, e.target]]
        : mine.has(e.target) && where[e.source]?.c !== b && where[e.source] ? [[e.target, e.source]] : []))
        .filter(([, o]) => cloud(b) || !o.startsWith("cloud:"))
        // only a pipe that can run straight: from the left into it, or out of it to the right, clear of it
        .filter(([m, o]) => { const q = where[o].c, into = pipes.some((e) => e.source === o && e.target === m);
          return into ? q.x + q.width < b.x : q.x > b.x + b.width; });
      const pick = ends.find(([, o]) => done.has(where[o].c)) || ends[0];
      done.add(b);
      if (!pick) continue;
      const dy = Math.round(where[pick[1]].y() - where[pick[0]].y());
      if (!dy || Math.abs(dy) > 24) continue;            // (a jog: a bigger move undoes what ELK arranged)
      const f = foot(b), moved = { ...f, y: f.y + dy };
      const hit = kids.some((o) => o !== b && !o.id.startsWith("hull:") && (() => { const q = foot(o);
        return moved.x < q.x + q.w + 12 && q.x < moved.x + moved.w + 12 && moved.y < q.y + q.h + 12 && q.y < moved.y + moved.h + 12; })());
      const fits = moved.y >= 0;
      if (!hit && fits) b.y += dy;
    }
  };
  visit(lay);                                          // (the top only: inside an open system lines are many and close)
}

/* whether what a node holds (its parts, through anchor blocks) is one connected whole: wrapping splits
   each connected piece into rows of its own, so it is asked for only of one */
function oneChain(n, g) {
  const ids = new Set();
  const walk = (x) => { for (const c of x.children || []) { if (c.id.startsWith("grp:")) walk(c); else if (!c.id.startsWith("hull:")) ids.add(c.id); } };
  walk(n);
  const parent = Object.fromEntries([...ids].map((x) => [x, x]));
  const root = (x) => (parent[x] === x ? x : (parent[x] = root(parent[x])));
  for (const e of g.edges) if (ids.has(e.source) && ids.has(e.target)) parent[root(e.source)] = root(e.target);
  return ids.size > 1 && new Set([...ids].map(root)).size === 1;
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
