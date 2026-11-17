/* the control view: the whole control system as one block diagram, as the textbooks draw it (Ogata;
   Franklin, Powell & Emami-Naeini; Åström & Murray), and as Simulink draws hierarchy. The server works
   out the diagram (blockdiagram.py): blocks, summing junctions, the processes, the sensors on the
   feedback paths, the signals between them. Here it is laid out (ELK places it, left to right, each
   sensor between what it reads and where its reading goes so that the feedback runs beneath), its
   lines routed around every part (libavoid, through avoid.js's worker), and drawn in one ink: plain
   rectangles with a function inside, circles for summing junctions with a sign at each input, dots
   where a signal is taken off, bold lines with a slash and a count for vectors. Colour only on what is
   pointed at or chosen. */
"use strict";

const BD = { FS: 13, SUB: 10, CH: 7.2, CHS: 6.0, SUM: 24, PORT: 18, PAD: 14 };
const MATHML = "http://www.w3.org/1998/Math/MathML";

/* ---- sizes: each part as big as its function and its ports need */
function bdTextW(t, small = false) { return (t || "").length * (small ? BD.CHS : BD.CH); }
function bdSymW(fn) {                                   // C_tuner(z): the symbol, its subscript, its argument
  if (!fn) return 0;
  if (fn.name) return bdTextW(fn.name) + 8;
  return (fn.sym ? 10 : 0) + (fn.sub ? bdTextW(fn.sub, true) + 2 : 0) + (fn.arg ? 22 : 0);
}
function bdFrac(expr) {                                 // "1/s", "Kᵢ T z/(z − 1)": a fraction drawn stacked
  const m = /^([^/]+)\/\(?([^()/]+)\)?$/.exec(expr || "");
  return m && expr.length <= 16 ? [m[1].trim(), m[2].trim()] : null;
}
function bdSize(n) {
  if (n.kind === "sum") return [BD.SUM, BD.SUM];
  if (n.kind === "mux" || n.kind === "demux") return [7, Math.max(34, (n.n || 2) * 18)];
  if (n.kind === "input" || n.kind === "output") return [Math.max(26, bdSymW(n.fn) + 10), 22];
  if (n.kind === "port") return [Math.max(40, bdSymW(n.fn) + 22), 22];
  if (n.kind === "sampler") return [36, 24];
  const fn = n.fn || {};
  const sideN = Math.max(n.ins.length, n.outs.length);
  let w = Math.max(84, bdSymW(fn) + 28), hgt = 46;
  const frac = fn.frac || bdFrac(fn.expr);   // a process the model declares: its numbers over its lag
  if (fn.name) {                                       // a nonlinear block: its name, its kind, a sketch of it
    w = Math.max(w, bdTextW(fn.name) + 28 + (fn.sketch ? 40 : 0));
    hgt = 46;
  } else if (frac) { w = Math.max(w, bdTextW(frac[0]) + 28, bdTextW(frac[1]) + 28); hgt = 64; }
  else if (fn.expr) { w = Math.max(w, bdTextW(fn.expr, true) + 24); hgt = 54; }
  if (n.role === "subsystem") { w += 18; hgt = Math.max(hgt, 54); }
  return [Math.round(w), Math.max(hgt, (sideN + 1) * BD.PORT)];
}
function bdFrameTitle(f) { return 30; }

/* ---- the layout: ELK places the parts and the frames (open systems, the inner loops of cascades) */
function bdPortPos(n, w, hgt) {                        // the ports of the parts that are drawn by hand: where they are
  const at = {};
  if (n.kind === "sum") {
    const c = w / 2, r = w / 2;
    const bySide = { W: [], N: [], S: [], E: [] };
    for (const p of [...n.ins, ...n.outs]) bySide[p.side].push(p);
    for (const [side, ps] of Object.entries(bySide)) ps.forEach((p, i) => {
      const off = ps.length > 1 ? (i - (ps.length - 1) / 2) * 0.7 : 0;      // more than one on a side: apart on the circle
      const ang = { W: Math.PI, E: 0, N: -Math.PI / 2, S: Math.PI / 2 }[side] + off;
      at[p.id] = { x: c + r * Math.cos(ang), y: c + r * Math.sin(ang), side };
    });
    return at;
  }
  if (["mux", "demux", "input", "output", "port", "sampler"].includes(n.kind)) {
    const place = (ps, x, side) => ps.forEach((p, i) => { at[p.id] = { x, y: ((i + 1) * hgt) / (ps.length + 1), side }; });
    place(n.ins, 0, "W");
    place(n.outs, w, "E");
    return at;
  }
  return null;                                          // a block: ELK spreads its ports on their sides
}

function bdElkGraph(g) {
  const SIDE = { W: "WEST", E: "EAST", N: "NORTH", S: "SOUTH" };
  const elkNodes = {}, roots = [];
  const frames = Object.fromEntries((g.frames || []).map((f) => [f.id, f]));
  for (const f of g.frames || []) {
    elkNodes[f.id] = { id: f.id, children: [], layoutOptions: {
      "elk.padding": `[top=${bdFrameTitle(f) + 8},left=${BD.PAD},bottom=${BD.PAD},right=${BD.PAD}]` } };
  }
  const rank = bdOrder(g);
  const nodes = [...g.nodes].sort((a, b) => rank[a.id] - rank[b.id]);
  for (const n of nodes) {
    const [w, hgt] = bdSize(n);
    const fixed = bdPortPos(n, w, hgt);
    const node = { id: n.id, width: w, height: hgt, layoutOptions: { "elk.portConstraints": fixed ? "FIXED_POS" : "FIXED_SIDE" } };
    if (!fixed) node.layoutOptions["elk.nodeSize.constraints"] = "[PORTS, MINIMUM_SIZE]";
    if (!fixed) node.layoutOptions["elk.nodeSize.minimum"] = `(${w}, ${hgt})`;
    node.ports = [...n.ins, ...n.outs].map((p) => {
      const q = { id: p.id, width: 1, height: 1, layoutOptions: { "elk.port.side": SIDE[p.side] } };
      if (fixed) { q.x = fixed[p.id].x - 0.5; q.y = fixed[p.id].y - 0.5; }
      return q;
    });
    elkNodes[n.id] = node;
  }
  // a frame comes where the first part in it does: ELK takes the order its children are given in
  const fr = { ...rank };
  const lift = (id, r) => { for (let f = frames[id] ? id : byIdN[id]?.parent; f && frames[f]; f = frames[f].parent) fr[f] = Math.min(fr[f] ?? Infinity, r); };
  const byIdN = Object.fromEntries(g.nodes.map((n) => [n.id, n]));
  for (const n of g.nodes) lift(n.id, rank[n.id]);
  const items = [...g.nodes.map((n) => [n.id, n.parent]), ...(g.frames || []).map((f) => [f.id, f.parent])]
    .sort((a, b) => (fr[a[0]] ?? Infinity) - (fr[b[0]] ?? Infinity));
  for (const [id, parent] of items) (parent && elkNodes[parent] ? elkNodes[parent].children : roots).push(elkNodes[id]);
  // a sensor sits on the feedback path: given to the layering between where its reading goes and what it
  // reads (its lines reversed), it is placed beneath the forward path, not after it
  const byId = Object.fromEntries(g.nodes.map((n) => [n.id, n]));
  const back = (e) => e.feedback || byId[e.source]?.role === "sensor" || byId[e.target]?.role === "sensor";
  const edges = g.edges.map((e) => (back(e) ? { id: e.id, sources: [e.targetPort], targets: [e.sourcePort], reversed: true }
                                            : { id: e.id, sources: [e.sourcePort], targets: [e.targetPort] }));
  return { id: "root", children: roots, edges, layoutOptions: {
    "elk.algorithm": "layered", "elk.direction": "RIGHT", "elk.hierarchyHandling": "INCLUDE_CHILDREN",
    "elk.edgeRouting": "ORTHOGONAL", "elk.layered.spacing.nodeNodeBetweenLayers": "46", "elk.spacing.nodeNode": "30",
    "elk.spacing.edgeNode": "16", "elk.spacing.edgeEdge": "10", "elk.layered.spacing.edgeNodeBetweenLayers": "14",
    "elk.spacing.componentComponent": "40", "elk.padding": "[top=20,left=20,bottom=20,right=20]",
    "elk.layered.considerModelOrder.strategy": "NODES_AND_EDGES", "elk.separateConnectedComponents": "true",
    "elk.layered.cycleBreaking.strategy": "MODEL_ORDER",
    "elk.layered.nodePlacement.strategy": "BRANDES_KOEPF", "elk.layered.nodePlacement.bk.fixedAlignment": "BALANCED",
    "elk.spacing.portPort": "14" } };
}

/* the order the parts are given to ELK, which breaks cycles by it: each loop from its reference along its
   forward path (r, Σ, C, the actuator, the process, y), and each sensor just after where its reading goes,
   so that only the feedback (a sensor's lines, and a process output read back) runs against it */
function bdOrder(g) {
  const byId = Object.fromEntries(g.nodes.map((n) => [n.id, n]));
  const sensor = (id) => byId[id]?.role === "sensor";
  const next = {};
  for (const e of g.edges) if (!e.feedback && !sensor(e.source) && !sensor(e.target)) (next[e.source] ||= []).push(e.target);
  const out = [], seen = new Set();
  const visit = (id) => {
    if (seen.has(id) || !byId[id] || sensor(id)) return;
    seen.add(id);
    out.push(id);
    for (const e of g.edges) if (e.source === id && sensor(e.target)) continue;
    for (const t of next[id] || []) visit(t);
  };
  const starts = [...g.nodes.filter((n) => n.role === "reference"), ...g.nodes.filter((n) => n.kind === "port" && n.port_of === "in"),
                  ...g.nodes.filter((n) => n.role === "disturbance"), ...g.nodes.filter((n) => n.role === "subsystem"), ...g.nodes];
  for (const n of starts) visit(n.id);
  const rank = {};
  out.forEach((id, i) => { rank[id] = i * 2; });
  // a loop reached first through another loop's actuator (queues in series) would put its comparator after
  // its own process: its forward path, from the comparator to the process it reads back, is moved in front
  const prev = {};
  for (const [a, ts] of Object.entries(next)) for (const b of ts) (prev[b] ||= []).push(a);
  const reach = (from, by) => { const seen = new Set([from]), todo = [from];
    while (todo.length) for (const y of by[todo.pop()] || []) if (!seen.has(y)) { seen.add(y); todo.push(y); }
    return seen; };
  for (const e of g.edges) {
    const S0 = e.source, T = e.target;
    if (!e.feedback || rank[S0] == null || rank[T] == null || rank[T] < rank[S0]) continue;
    const back = reach(S0, prev), path = [], seen = new Set();
    const walk = (id) => { if (seen.has(id) || id === S0 || !back.has(id)) return; seen.add(id); path.push(id); for (const t of next[id] || []) walk(t); };
    walk(T);
    const refs = (prev[T] || []).filter((x) => !(prev[x] || []).length && !seen.has(x));
    const moved = [...refs, ...path];
    moved.forEach((id, i) => { rank[id] = rank[S0] - 1 + (i + 1) / (moved.length + 2); });
  }
  for (const n of g.nodes.filter((x) => sensor(x.id))) {     // just after the first part its reading goes to
    const to = g.edges.filter((e) => e.source === n.id).map((e) => rank[e.target]).filter((x) => x != null);
    rank[n.id] = (to.length ? Math.min(...to) : out.length * 2) + 1;
  }
  return rank;
}

async function bdLayout(g) {
  await avoidLoad();
  const graph = bdElkGraph(g);
  let lay;
  try { lay = await elk.layout(graph); }
  catch (e) {
    console.warn("ELK failed on the block diagram: again flat", e);
    lay = await elk.layout({ ...graph, layoutOptions: { ...graph.layoutOptions, "elk.hierarchyHandling": "SEPARATE_CHILDREN" } });
  }
  // flat: every part in the diagram's own coordinates, the frames as outlines, outermost first
  const children = [], containers = [], abs = { root: { x: 0, y: 0 } }, ports = {};
  const frames = new Set((g.frames || []).map((f) => f.id));
  const walk = (node, ox, oy, depth, within) => {
    for (const c of node.children || []) {
      const x = ox + c.x, y = oy + c.y;
      abs[c.id] = { x, y };
      if (frames.has(c.id)) {
        containers.push({ id: c.id, name: c.id, x, y, width: c.width, height: c.height, depth });
        walk(c, x, y, depth + 1, [...within, c.id]);
      } else {
        children.push({ id: c.id, x, y, width: c.width, height: c.height, within });
        const gn = g.nodes.find((n) => n.id === c.id);
        if (gn) gn.systems = within;
        for (const p of c.ports || []) ports[p.id] = { x: x + p.x + (p.width || 0) / 2, y: y + p.y + (p.height || 0) / 2, node: c.id };
      }
    }
  };
  walk(lay, 0, 0, 0, []);
  const edges = [];
  const collect = (node) => { for (const e of node.edges || []) edges.push(e); for (const c of node.children || []) collect(c); };
  collect(lay);
  for (const e of edges) {
    const o = abs[e.container] || abs.root;
    for (const sec of e.sections || []) for (const p of [sec.startPoint, sec.endPoint, ...(sec.bendPoints || [])]) { p.x += o.x; p.y += o.y; }
    if (e.reversed) {
      [e.sources, e.targets] = [e.targets, e.sources];
      for (const s of e.sections || []) { [s.startPoint, s.endPoint] = [s.endPoint, s.startPoint]; s.bendPoints = (s.bendPoints || []).slice().reverse(); }
    }
  }
  const size = bdWrapRows(g, { children, containers, ports, edges }, lay.width, lay.height);
  // the side each port is on, after ELK placed them
  const byId = Object.fromEntries(g.nodes.map((n) => [n.id, n]));
  const box = Object.fromEntries(children.map((c) => [c.id, c]));
  for (const [pid, p] of Object.entries(ports)) {
    const c = box[p.node], n = byId[p.node];
    const decl = [...(n?.ins || []), ...(n?.outs || [])].find((q) => q.id === pid);
    p.side = decl?.side || "W";
    if (n?.kind === "block") {                                            // on the edge of its side, exactly
      if (p.side === "W") p.x = c.x; else if (p.side === "E") p.x = c.x + c.width;
      else if (p.side === "N") p.y = c.y; else p.y = c.y + c.height;
    } else {
      const fx = bdPortPos(n, c.width, c.height)?.[pid];
      if (fx) { p.x = c.x + fx.x; p.y = c.y + fx.y; }
    }
  }
  const out = { children, containers, edges, ports, width: size[0], height: size[1], routing: false };
  for (const e of out.edges) {                         // until libavoid's lines come: ELK's, ending on the ports
    const ge = g.edges.find((x) => x.id === e.id);
    const a = ports[ge?.sourcePort], b = ports[ge?.targetPort];
    if (!a || !b) continue;
    const s = e.sections?.[0];
    if (!s) e.sections = [{ startPoint: { x: a.x, y: a.y }, endPoint: { x: b.x, y: b.y }, bendPoints: [] }];
  }
  return out;
}

/* a drawing far wider than the screen (several systems open, side by side): its top-level pieces (each
   open system's frame, each closed one's block, with what lies above or below it) wrapped into rows, in
   their order left to right, so that it keeps near the screen's shape, as the dynamics view wraps its open
   systems (layouts.js). A line within a piece moves with it; a line between pieces is drawn straight until
   libavoid routes it. */
const BD_WRAP_OVER = 3;           // wider than tall by more than this many times the screen's shape: wrapped
const BD_ROW_GAP = 60;
function bdWrapRows(g, lay, W, H) {
  if (S.bdNoWrap) return [W, H];                        // (the Guide's frames: small, framed to fit, never wrapped)
  const svg = typeof document !== "undefined" && document.querySelector("svg.canvas");
  const r = svg?.getBoundingClientRect?.();
  const screen = r && r.width && r.height ? r.width / Math.max(r.height - 80, 200) : 1.6;
  if (!(W / H > BD_WRAP_OVER * screen)) return [W, H];
  // the pieces: each top-level frame or part, and those whose spans left to right overlap taken together
  const topOf = {};
  for (const c of lay.children) topOf[c.id] = c.within?.[0] || c.id;
  const rect = {};
  for (const c of [...lay.children.filter((x) => !x.within?.length), ...lay.containers.filter((f) => f.depth === 0)])
    rect[c.id] = { x: c.x, y: c.y, w: c.width, h: c.height };
  const cols = [];
  for (const [id, b] of Object.entries(rect).sort((a, b) => a[1].x - b[1].x)) {
    const last = cols[cols.length - 1];
    if (last && b.x < last.x1 - 2) { last.ids.push(id); last.x1 = Math.max(last.x1, b.x + b.w); last.y0 = Math.min(last.y0, b.y); last.y1 = Math.max(last.y1, b.y + b.h); }
    else cols.push({ ids: [id], x0: b.x, x1: b.x + b.w, y0: b.y, y1: b.y + b.h });
  }
  if (cols.length < 2) return [W, H];
  // how many rows: the number whose drawing comes nearest the screen's shape
  const pack = (maxW) => {
    const rows = [[]];
    let x = 0;
    for (const c of cols) {
      const w = c.x1 - c.x0;
      if (rows[rows.length - 1].length && x + w > maxW) { rows.push([]); x = 0; }
      rows[rows.length - 1].push(c);
      x += w + 46;
    }
    const width = Math.max(...rows.map((row) => row.reduce((s0, c) => s0 + c.x1 - c.x0 + 46, -46)));
    const height = rows.reduce((s0, row) => s0 + Math.max(...row.map((c) => c.y1 - c.y0)) + BD_ROW_GAP, -BD_ROW_GAP);
    return { rows, width, height };
  };
  let best = null;
  for (let k = 1; k <= cols.length; k++) {
    const p = pack(W / k);
    const off = Math.abs(Math.log((p.width / p.height) / screen));
    if (!best || off < best.off - 1e-9) best = { ...p, off };
  }
  if (best.rows.length < 2) return [W, H];
  // each piece's shift
  const shift = {};
  let y = 20;
  for (const row of best.rows) {
    let x = 20;
    const top = Math.min(...row.map((c) => c.y0)), hgt = Math.max(...row.map((c) => c.y1 - c.y0));
    for (const c of row) { for (const id of c.ids) shift[id] = { dx: x - c.x0, dy: y - top }; x += c.x1 - c.x0 + 46; }
    y += hgt + BD_ROW_GAP;
  }
  const mv = (o, d) => { o.x += d.dx; o.y += d.dy; };
  const idOfTop = (nid) => topOf[nid];
  for (const c of lay.children) mv(c, shift[idOfTop(c.id)] || { dx: 0, dy: 0 });
  for (const f of lay.containers) { let t = f.id; const n = g.frames?.find((x) => x.id === f.id); let p = n?.parent;
    while (p) { t = p; p = g.frames.find((x) => x.id === p)?.parent; } mv(f, shift[t] || { dx: 0, dy: 0 }); }
  for (const p of Object.values(lay.ports)) mv(p, shift[idOfTop(p.node)] || { dx: 0, dy: 0 });
  const ends = Object.fromEntries(g.edges.map((e) => [e.id, e]));
  for (const e of lay.edges) {
    const ge = ends[e.id];
    const a = ge && idOfTop(ge.source), b = ge && idOfTop(ge.target);
    if (a && a === b) { for (const sec of e.sections || []) for (const q of [sec.startPoint, sec.endPoint, ...(sec.bendPoints || [])]) mv(q, shift[a] || { dx: 0, dy: 0 }); }
    else e.sections = [];                       // between pieces: drawn port to port (bdLayout) until routed
  }
  return [best.width + 40, best.height + 40];
}

/* ---- the lines, routed by libavoid around every part (avoid.js's router, in its worker) */
function bdAvoidSpec(lay, g) {
  const DIR = { W: "left", E: "right", N: "up", S: "down" };
  const shapes = [], pinOf = {};
  const fanout = {};
  for (const e of g.edges) fanout[e.sourcePort] = (fanout[e.sourcePort] || 0) + 1;
  for (const c of lay.children) {
    const pins = [];
    let i = 0;
    for (const [pid, p] of Object.entries(lay.ports)) {
      if (p.node !== c.id) continue;
      const cls = 100 + i++;
      pinOf[pid] = cls;
      const x = Math.max(0, Math.min(c.width, p.x - c.x)), y = Math.max(0, Math.min(c.height, p.y - c.y));
      pins.push({ cls, x, y, dir: DIR[p.side], shared: (fanout[pid] || 0) > 1, abs: true });
    }
    shapes.push({ id: c.id, x: c.x, y: c.y, w: c.width, h: c.height, pins, labels: [] });
  }
  for (const f of lay.containers) {                    // a frame's title is in the way; its outline is not
    const fr = (g.frames || []).find((x) => x.id === f.id);
    const tw = Math.min(f.width - 8, bdSymW(fr?.fn) + bdTextW(fr?.label || "", true) + 60);
    shapes.push({ id: f.id + ":title", x: f.x + 4, y: f.y + 4, w: tw, h: 22, pins: [], labels: [] });
  }
  const conns = [];
  for (const e of g.edges) {
    const sp = pinOf[e.sourcePort], tp = pinOf[e.targetPort];
    if (sp == null || tp == null) continue;
    conns.push({ id: e.id, s: lay.ports[e.sourcePort].node, sp, t: lay.ports[e.targetPort].node, tp });
  }
  // a crossing costs less than in the other view: a block diagram crosses a line rather than go far round
  return { shapes, conns, crossingPenalty: Math.min(60, CROSSING_PENALTY(conns.length)), nudgeCommon: true };
}

/* the lines of one signal leave its port as one line, and part where they turn (a take-off point): libavoid
   sets them side by side from a shared point, so each first stretch is put back on the port's own line */
function bdJoinNets(lay, g, byLe) {
  const nets = {};
  for (const e of g.edges) (nets[e.sourcePort] ||= []).push(e);
  for (const [port, es] of Object.entries(nets)) {
    const at = lay.ports[port];
    if (!at || es.length < 2) continue;
    for (const e of es) {
      const sec = byLe[e.id]?.sections?.[0];
      if (!sec) continue;
      const pts = [sec.startPoint, ...(sec.bendPoints || []), sec.endPoint];
      if (pts.length < 3) continue;                     // straight to its end: it is on the port's line already
      const [a, b] = pts, was = [{ ...a }, { ...b }];
      if (Math.abs(a.y - b.y) < 0.5 && Math.abs(a.y - at.y) < 16) { a.y = at.y; b.y = at.y; a.x = at.x; }
      else if (Math.abs(a.x - b.x) < 0.5 && Math.abs(a.x - at.x) < 16) { a.x = at.x; b.x = at.x; a.y = at.y; }
      else continue;
      // not onto another signal's line, nor its next stretch through a part
      const mine = [[a, b], [b, pts[2]]];
      const clash = g.edges.some((o) => o.sourcePort !== port && byLe[o.id] && bdPts(byLe[o.id]).slice(1).some((q, i, arr) => {
        const r = i ? arr[i - 1] : bdPts(byLe[o.id])[0];
        return mine.some(([m, n]) => bdAlong(m, n, r, q) > 4);
      })) || lay.children.some((c) => c.id !== e.source && c.id !== e.target && mine.some(([m, n]) =>
        Math.max(m.x, n.x) > c.x + 2 && Math.min(m.x, n.x) < c.x + c.width - 2 && Math.max(m.y, n.y) > c.y + 2 && Math.min(m.y, n.y) < c.y + c.height - 2));
      if (clash) { Object.assign(a, was[0]); Object.assign(b, was[1]); }
    }
  }
}

/* two signals' lines on top of each other (libavoid now and then leaves a pair in one channel): the
   stretch of one moved aside, its neighbours stretched to meet it, where that hits nothing */
function bdSeparate(lay, g, byLe) {
  const netOf = Object.fromEntries(g.edges.map((e) => [e.id, e.sourcePort]));
  const ends = Object.fromEntries(g.edges.map((e) => [e.id, [e.source, e.target]]));
  const lines = () => lay.edges.filter((le) => netOf[le.id]).map((le) => ({ le, pts: bdPts(le) }));
  const hitsPart = (m, n, id) => lay.children.some((c) => !ends[id].includes(c.id) &&
    Math.max(m.x, n.x) > c.x + 2 && Math.min(m.x, n.x) < c.x + c.width - 2 && Math.max(m.y, n.y) > c.y + 2 && Math.min(m.y, n.y) < c.y + c.height - 2);
  for (let pass = 0; pass < 40; pass++) {
    const all = lines();
    let fixed = false;
    outer: for (const A of all) for (let i = 1; i < A.pts.length - 2; i++) {      // an inner stretch: both its ends bend
      const [m, n] = [A.pts[i], A.pts[i + 1]];
      const clash = (pm, pn, skipNet) => all.some((B) => netOf[B.le.id] !== skipNet &&
        B.pts.slice(1).some((q, k) => bdAlong(pm, pn, B.pts[k], q) > 4));
      if (!clash(m, n, netOf[A.le.id])) continue;
      const horiz = Math.abs(m.y - n.y) < 1;
      for (const d of [7, -7, 14, -14, 21, -21, 28, -28]) {
        const pts = A.pts.map((q) => ({ ...q }));
        if (horiz) { pts[i].y += d; pts[i + 1].y += d; } else { pts[i].x += d; pts[i + 1].x += d; }
        const segs = [[pts[i - 1], pts[i]], [pts[i], pts[i + 1]], [pts[i + 1], pts[i + 2]]];
        if (segs.some(([a, b]) => hitsPart(a, b, A.le.id) || clash(a, b, netOf[A.le.id]))) continue;
        A.le.sections = [{ startPoint: pts[0], bendPoints: pts.slice(1, -1), endPoint: pts[pts.length - 1] }];
        fixed = true;
        break outer;
      }
    }
    if (!fixed) break;
  }
}

/* two lines of one signal that cross: they carry the same thing from the same port, so each takes the
   other's way up to where they cross, and its own from there: they meet there instead of crossing */
function bdTrade(lay, g, byLe) {
  const nets = {};
  for (const e of g.edges) if (byLe[e.id]) (nets[e.sourcePort] ||= []).push(byLe[e.id]);
  const cut = (pts, i, X) => [...pts.slice(0, i + 1), X];       // up to X, which lies on its stretch i
  for (const les of Object.values(nets)) for (let pass = 0; pass < 10; pass++) {
    let any = false;
    for (let a = 0; a < les.length && !any; a++) for (let b = a + 1; b < les.length && !any; b++) {
      const A = bdPts(les[a]), B = bdPts(les[b]);
      for (let i = 0; i < A.length - 1 && !any; i++) for (let k = 0; k < B.length - 1 && !any; k++) {
        const [p, q, r, s0] = [A[i], A[i + 1], B[k], B[k + 1]];
        const hv = (p1, q1, r1, s1) => Math.abs(p1.y - q1.y) < 1 && Math.abs(r1.x - s1.x) < 1 &&
          r1.x > Math.min(p1.x, q1.x) + 2 && r1.x < Math.max(p1.x, q1.x) - 2 && p1.y > Math.min(r1.y, s1.y) + 2 && p1.y < Math.max(r1.y, s1.y) - 2;
        let X = null;
        if (hv(p, q, r, s0)) X = { x: r.x, y: p.y };
        else if (hv(r, s0, p, q)) X = { x: p.x, y: r.y };
        if (!X) continue;
        const nA = [...cut(B, k, X), ...A.slice(i + 1)], nB = [...cut(A, i, X), ...B.slice(k + 1)];
        const put = (le, pts) => setRoute(le, pts);
        put(les[a], nA); put(les[b], nB);
        any = true;
      }
    }
    if (!any) break;
  }
}

/* no line runs along a frame's edge (it would read as a bus on the frame): a stretch on an edge is moved off
   it, inward or outward, its neighbours stretched to meet it, where that hits no part and no other line */
const BD_FRAME_GAP = 10;
function bdOnFrame(m, n, f) {
  const horiz = Math.abs(m.y - n.y) < 1, vert = Math.abs(m.x - n.x) < 1;
  const overlap = (a0, a1, b0, b1) => Math.min(Math.max(a0, a1), b1) - Math.max(Math.min(a0, a1), b0);
  if (horiz && (Math.abs(m.y - f.y) < BD_FRAME_GAP || Math.abs(m.y - f.y - f.height) < BD_FRAME_GAP)) return overlap(m.x, n.x, f.x, f.x + f.width) > 8;
  if (vert && (Math.abs(m.x - f.x) < BD_FRAME_GAP || Math.abs(m.x - f.x - f.width) < BD_FRAME_GAP)) return overlap(m.y, n.y, f.y, f.y + f.height) > 8;
  return false;
}
function bdOffFrames(lay, g, byLe) {
  const frames = lay.containers || [];
  if (!frames.length) return;
  const netOf = Object.fromEntries(g.edges.map((e) => [e.id, e.sourcePort]));
  const ends = Object.fromEntries(g.edges.map((e) => [e.id, [e.source, e.target]]));
  const hitsPart = (m, n, id) => lay.children.some((c) => !ends[id].includes(c.id) &&
    Math.max(m.x, n.x) > c.x + 2 && Math.min(m.x, n.x) < c.x + c.width - 2 && Math.max(m.y, n.y) > c.y + 2 && Math.min(m.y, n.y) < c.y + c.height - 2);
  for (let pass = 0; pass < 60; pass++) {
    const all = lay.edges.filter((le) => netOf[le.id]).map((le) => ({ le, pts: bdPts(le) }));
    const clash = (pm, pn, net) => all.some((B) => netOf[B.le.id] !== net && B.pts.slice(1).some((q, k) => bdAlong(pm, pn, B.pts[k], q) > 4));
    let fixed = false;
    outer: for (const A of all) for (let i = 1; i < A.pts.length - 2; i++) {        // an inner stretch: both its ends bend
      const [m, n] = [A.pts[i], A.pts[i + 1]];
      if (!frames.some((f) => bdOnFrame(m, n, f))) continue;
      const horiz = Math.abs(m.y - n.y) < 1;
      const f = frames.find((x) => bdOnFrame(m, n, x));
      const edge = horiz ? [f.y, f.y + f.height].sort((a, b) => Math.abs(a - m.y) - Math.abs(b - m.y))[0]
                         : [f.x, f.x + f.width].sort((a, b) => Math.abs(a - m.x) - Math.abs(b - m.x))[0];
      const at = horiz ? m.y : m.x;
      for (const to of [edge + 14, edge - 14, edge + 20, edge - 20, edge + 28, edge - 28, edge + 36, edge - 36]) {
        const d = to - at;
        const pts = A.pts.map((q) => ({ ...q }));
        if (horiz) { pts[i].y += d; pts[i + 1].y += d; } else { pts[i].x += d; pts[i + 1].x += d; }
        const segs = [[pts[i - 1], pts[i]], [pts[i], pts[i + 1]], [pts[i + 1], pts[i + 2]]];
        if (segs.some(([a, b]) => hitsPart(a, b, A.le.id) || clash(a, b, netOf[A.le.id]) || frames.some((f) => bdOnFrame(a, b, f)))) continue;
        A.le.sections = [{ startPoint: pts[0], bendPoints: pts.slice(1, -1), endPoint: pts[pts.length - 1] }];
        fixed = true;
        break outer;
      }
    }
    if (!fixed) break;
  }
}

/* where the lines cross the frame of an open system: Simulink's ports, a mark on the edge with the signal's name */
function bdFrameCrossings(lay, g, byLe) {
  const frames = (lay.containers || []).filter((c) => (g.frames || []).find((f) => f.id === c.id)?.frame === "system");
  const out = [];
  const nets = {};
  for (const e of g.edges) (nets[e.sourcePort] ||= []).push(e);
  for (const es of Object.values(nets)) {
    const seen = [];
    for (const e of es) {
      const pts = byLe[e.id] ? bdPts(byLe[e.id]) : [];
      for (let i = 1; i < pts.length; i++) {
        const a = pts[i - 1], b = pts[i];
        for (const f of frames) {
          const hits = [];
          if (Math.abs(a.y - b.y) < 1) {                  // across a left or right edge
            for (const [x, side] of [[f.x, "W"], [f.x + f.width, "E"]])
              if (x > Math.min(a.x, b.x) + 0.5 && x < Math.max(a.x, b.x) - 0.5 && a.y > f.y && a.y < f.y + f.height)
                hits.push({ x, y: a.y, side, horiz: true, into: (b.x - a.x) * (side === "W" ? 1 : -1) > 0 });
          } else if (Math.abs(a.x - b.x) < 1) {           // across the top or the bottom
            for (const [y, side] of [[f.y, "N"], [f.y + f.height, "S"]])
              if (y > Math.min(a.y, b.y) + 0.5 && y < Math.max(a.y, b.y) - 0.5 && a.x > f.x && a.x < f.x + f.width)
                hits.push({ x: a.x, y, side, horiz: false, into: (b.y - a.y) * (side === "N" ? 1 : -1) > 0 });
          }
          for (const hp of hits) {
            if (seen.some((q) => Math.abs(q.x - hp.x) < 2 && Math.abs(q.y - hp.y) < 2)) continue;
            seen.push(hp);
            out.push({ ...hp, frame: f, edge: e });
          }
        }
      }
    }
  }
  return out;
}

function bdAlong(p, q, r, s0) {                     // how far two straight stretches run on top of each other
  if (Math.abs(p.y - q.y) < 1 && Math.abs(r.y - s0.y) < 1 && Math.abs(p.y - r.y) < 3)
    return Math.min(Math.max(p.x, q.x), Math.max(r.x, s0.x)) - Math.max(Math.min(p.x, q.x), Math.min(r.x, s0.x));
  if (Math.abs(p.x - q.x) < 1 && Math.abs(r.x - s0.x) < 1 && Math.abs(p.x - r.x) < 3)
    return Math.min(Math.max(p.y, q.y), Math.max(r.y, s0.y)) - Math.max(Math.min(p.y, q.y), Math.min(r.y, s0.y));
  return 0;
}

function bdRoute(lay, g) {
  if (!AV.mode) { lay.whenRouted = Promise.resolve(); return; }
  const spec = bdAvoidSpec(lay, g), seq = ++AV.seq;
  const done = (m) => {
    if (m && !m.skipped) {
      const byLe = Object.fromEntries(lay.edges.map((le) => [le.id, le]));
      for (const [id, pts] of Object.entries(m.routes)) if (byLe[id]) setRoute(byLe[id], pts.map(([x, y]) => ({ x, y })));
      bdJoinNets(lay, g, byLe);
      const groups = {};
      for (const e of g.edges) (groups[e.sourcePort] ||= { end: "s", ids: [] }).ids.push(e.id);
      try {                                             // lines of one signal that cross trade ways (untangle.js)
        untangle(lay, Object.values(groups).filter((x) => x.ids.length > 1), lay.children,
                 Object.fromEntries(g.edges.map((e) => [e.id, [e.source, e.target]])));
      } catch (err) { /* as they were */ }
      bdSeparate(lay, g, byLe);
      bdTrade(lay, g, byLe);
      bdOffFrames(lay, g, byLe);
      AV.ms = m.ms; AV.invalid = m.invalid;
    }
    lay.routing = false;
  };
  lay.routing = true;
  if (AV.mode === "page") { done(AV.core.route(spec)); lay.whenRouted = Promise.resolve(); return; }
  lay.whenRouted = new Promise((resolve) => {
    AV.waiting[`routed:${seq}:`] = (m) => { done(m); resolve(); };
    AV.worker.postMessage({ type: "route", seq, spec });
  });
}

/* ---- drawing, in one ink */
function bdSym(parent, x, y, fn, { size = BD.FS, anchor = "middle", bold = false, cls = "bd-sym" } = {}) {
  // an italic symbol, its subscript (upright: it is a name), its argument
  const t = s("text", { x, y, class: cls, "text-anchor": anchor, "font-size": size });
  if (fn.sym) t.append(s("tspan", { class: "bd-mi" + (bold || fn.bold ? " bd-bold" : "") }, fn.sym));
  if (fn.sub) t.append(s("tspan", { class: "bd-subs", "baseline-shift": "sub", "font-size": size * 0.74 }, fn.sub));
  if (fn.arg) t.append(s("tspan", { "font-size": size }, "("), s("tspan", { class: "bd-mi", "font-size": size }, fn.arg), s("tspan", { "font-size": size }, ")"));
  parent.append(t);
  return t;
}
function bdSketch(kind, x, y) {                        // a static nonlinearity, as the textbooks sketch it
  const g = s("g", { class: "bd-sketch", transform: `translate(${x},${y})` });
  g.append(s("path", { d: "M0,12 H28 M14,0 V24", class: "bd-axis" }));
  if (kind === "relay") g.append(s("path", { d: "M2,18 H16 V5 H26 M8,18 V5 H16", class: "bd-curve" }));
  else if (kind === "saturation") g.append(s("path", { d: "M2,20 H8 L20,4 H26", class: "bd-curve" }));
  else if (kind === "zoh") g.append(s("path", { d: "M2,20 H8 V15 H14 V9 H20 V5 H26", class: "bd-curve" }));
  else if (kind === "deadzone") g.append(s("path", { d: "M2,22 L9,12 H19 L26,2", class: "bd-curve" }));
  else g.append(s("path", { d: "M2,20 C8,20 10,6 16,8 S22,4 26,3", class: "bd-curve" }));
  return g;
}

function bdNode(n, c) {
  const w = c.width, hgt = c.height;
  const g = s("g", { class: `node bd-node bd-${n.kind} bd-${n.role || n.kind}`, transform: `translate(${c.x},${c.y})`,
                     "data-id": n.id, "data-fn": bdFnText(n) });
  g.append(s("title", {}, (n.says || "").replace(/\s+$/, "")));
  const fn = n.fn || {};
  if (n.kind === "sum") {
    g.append(s("circle", { class: "hit bd-line bd-fill", cx: w / 2, cy: hgt / 2, r: w / 2 }));     // (clicked anywhere inside)
  } else if (n.kind === "mux" || n.kind === "demux") {
    g.append(s("rect", { class: "hit bd-bar", width: w, height: hgt }));
  } else if (n.kind === "input" || n.kind === "output") {
    g.append(s("rect", { class: "hit bd-ghost", width: w, height: hgt }));
    bdSym(g, n.kind === "input" ? w - 4 : 4, hgt / 2 + 4, fn, { anchor: n.kind === "input" ? "end" : "start" });
    if (fn.value) g.append(s("text", { x: n.kind === "input" ? w - 4 : 4, y: hgt + 10, class: "bd-note", "text-anchor": n.kind === "input" ? "end" : "start" }, fn.value));
  } else if (n.kind === "sampler") {                    // the sampler: a switch closed once every T (A/D)
    const y = hgt / 2;
    g.append(s("rect", { class: "hit bd-ghost", width: w, height: hgt }),
             s("path", { class: "bd-line", d: `M0,${y} H9 M27,${y} H${w} M9,${y} L25,${y - 9}` }),
             s("circle", { class: "bd-dot", cx: 9, cy: y, r: 1.8 }), s("circle", { class: "bd-dot", cx: 27, cy: y, r: 1.8 }),
             s("text", { x: w / 2, y: y + 11, class: "bd-note", "text-anchor": "middle" }, "T"));
  } else if (n.kind === "port") {                       // Simulink's In and Out: a rounded port, at the edge of a system drawn alone
    g.append(s("rect", { class: "hit bd-line bd-fill", width: w, height: hgt, rx: hgt / 2 }));
    bdSym(g, w / 2, hgt / 2 + 4, fn, { size: 12 });
    if (n.in) g.append(s("text", { x: n.port_of === "in" ? 0 : w, y: -5, class: "bd-note", "text-anchor": n.port_of === "in" ? "start" : "end" }, n.port_of === "in" ? "from " + n.in : "to " + n.in));
  } else {
    g.append(s("rect", { class: "hit bd-line bd-fill", width: w, height: hgt }));
    if (fn.name) {
      const sk = fn.sketch ? 38 : 0;
      if (fn.sketch) g.append(bdSketch(fn.sketch, 9, hgt / 2 - 12));
      // its name only: who fills it (a program, an AI agent, a person) and how often is the side panel's
      g.append(s("text", { x: sk + (w - sk) / 2, y: hgt / 2 + 4, class: "bd-name", "text-anchor": "middle" }, fn.name));
    } else {
      const frac = fn.frac || bdFrac(fn.expr);   // a process the model declares: its numbers over its lag
      const top = frac ? hgt / 2 - 12 : fn.expr ? hgt / 2 - 2 : hgt / 2 + 5;
      bdSym(g, w / 2, top, fn);
      if (frac) {
        const fw = Math.max(bdTextW(frac[0]), bdTextW(frac[1])) + 6;
        g.append(bdPower(s("text", { x: w / 2, y: hgt / 2 + 6, class: "bd-expr", "text-anchor": "middle" }), frac[0]),
                 s("path", { d: `M${w / 2 - fw / 2},${hgt / 2 + 10} H${w / 2 + fw / 2}`, class: "bd-line" }),
                 s("text", { x: w / 2, y: hgt / 2 + 23, class: "bd-expr", "text-anchor": "middle" }, frac[1]));
      } else if (fn.expr) g.append(richSvg(s("text", { x: w / 2, y: hgt / 2 + 14, class: "bd-note", "text-anchor": "middle" }), fn.expr));   // K_p: K with a subscript p
      if (n.role === "subsystem") {                      // a system closed into one block: opened here with its +
        const b = s("g", { class: "bd-toggle", "data-act": "open", transform: `translate(${w - 15},3)` },
                    s("title", {}, `open ${n.label} here`), s("rect", { width: 12, height: 12 }), s("path", { d: "M3,6 H9 M6,3 V9" }));
        b.addEventListener("click", (ev) => { ev.stopPropagation(); S.toggleSystem?.(n.label); });
        g.append(b);
      }
    }
  }
  return g;
}
function bdPower(textEl, text) {                       // "0.2 e^(−20s)": the exponent raised, as the textbooks write a delay
  const m = /^(.*)\^\((.*)\)$/.exec(String(text || ""));
  if (!m) { textEl.textContent = text; return textEl; }
  textEl.append(s("tspan", {}, m[1]), s("tspan", { dy: -6, "font-size": "75%" }, m[2]));
  return textEl;
}
function bdFnText(n) {                                  // what is inside the block, as text (for the tests and a tooltip)
  const fn = n.fn || {};
  if (n.kind === "sampler") return `sampler, T = ${fn.T || "?"}`;
  if (fn.name) return `${fn.name} (${fn.kind})`;
  if (fn.sym) return `${fn.sym}${fn.sub ? "_" + fn.sub : ""}${fn.arg ? `(${fn.arg})` : ""}${fn.expr ? " = " + fn.expr : ""}`;
  return n.kind;
}

function bdPts(le) { const s0 = (le.sections || [])[0]; return s0 ? [s0.startPoint, ...(s0.bendPoints || []), s0.endPoint] : []; }

function bdLabelSpot(pts, taken, w, hgt, boxes, lines = []) {     // where a signal's name goes: beside a straight stretch, clear of the rest
  const segs = pts.slice(1).map((b, i) => [pts[i], b]);
  const cuts = (r) => lines.some(([a, b]) => Math.max(a.x, b.x) > r.x && Math.min(a.x, b.x) < r.x + r.w &&
                                             Math.max(a.y, b.y) > r.y && Math.min(a.y, b.y) < r.y + r.h);
  const free = (r) => !taken.some((q) => r.x < q.x + q.w && q.x < r.x + r.w && r.y < q.y + q.h && q.y < r.y + r.h) &&
                      !boxes.some((q) => r.x < q.x + q.width && q.x < r.x + r.w && r.y < q.y + q.height && q.y < r.y + r.h) && !cuts(r);
  const tries = [];
  segs.forEach(([a, b], i) => {
    const len = Math.abs(a.x - b.x) + Math.abs(a.y - b.y);
    if (Math.abs(a.y - b.y) < 1 && len >= w + 6) {
      const x0 = Math.min(a.x, b.x), x1 = Math.max(a.x, b.x);
      for (const f of [0.5, 0.3, 0.7, 0.15, 0.85]) {
        const cx = x0 + (x1 - x0) * f;
        if (cx - w / 2 < x0 + 2 || cx + w / 2 > x1 - 2) continue;
        tries.push({ x: cx - w / 2, y: a.y - hgt - 3, w, h: hgt, i, len }, { x: cx - w / 2, y: a.y + 3, w, h: hgt, i, len });
      }
    } else if (Math.abs(a.x - b.x) < 1 && len >= hgt + 8) {
      const cy = (a.y + b.y) / 2;
      tries.push({ x: a.x + 4, y: cy - hgt / 2, w, h: hgt, i, len }, { x: a.x - w - 4, y: cy - hgt / 2, w, h: hgt, i, len });
    }
  });
  tries.sort((p, q) => p.i - q.i);                       // near where the signal leaves
  return tries.find(free) || null;
}

function bdDraw(svg, g, lay) {
  svg.classList.add("bd");
  const vp = s("g", { id: "viewport" });
  const byId = Object.fromEntries(g.nodes.map((n) => [n.id, n]));
  const box = Object.fromEntries(lay.children.map((c) => [c.id, c]));
  const frames = Object.fromEntries((g.frames || []).map((f) => [f.id, f]));
  // frames: open systems (a thin outline, its function as its title) and cascades' inner loops (dashed)
  for (const c of [...lay.containers].sort((a, b) => a.depth - b.depth)) {
    const f = frames[c.id];
    if (!f) continue;
    const fg = s("g", { class: `sys-hull hull bd-frame bd-frame-${f.frame}`, "data-hull": c.id });
    fg.append(s("rect", { x: c.x, y: c.y, width: c.width, height: c.height }));
    const t = bdSym(fg, c.x + 10, c.y + 19, f.fn || {}, { anchor: "start", size: 13 });
    t.append(s("tspan", { class: "bd-frame-name", dx: 8 }, f.frame === "cascade" ? `inner loop of ${f.label}` : f.label));
    fg.append(s("title", {}, f.says || ""));
    if (f.frame === "system") {
      const name = f.label;
      const b = s("g", { class: "bd-toggle", "data-act": "close", transform: `translate(${c.x + c.width - 18},${c.y + 6})` },
                  s("title", {}, `close ${name} into one block`), s("rect", { width: 12, height: 12, class: "hull-grip" }), s("path", { d: "M3,6 H9" }));
      b.addEventListener("click", (ev) => { ev.stopPropagation(); S.toggleSystem?.(name); });
      fg.append(b);
    }
    fg.addEventListener("click", (ev) => {
      if (ev.target.closest(".bd-toggle")) return;
      ev.stopPropagation();
      if (ev.shiftKey || ev.metaKey) { chooseShape(c.id, "toggle"); return; }     // (what it is chosen: interact.js)
      chooseShape(c.id); openBlock(f);
    });
    vp.append(fg);
  }
  // the lines: each signal from its port, an arrowhead where it arrives, a dot where it is taken off
  const edgesG = s("g", { class: "bd-edges" }), labelsG = s("g", { class: "bd-labels" });
  const byLe = Object.fromEntries(lay.edges.map((le) => [le.id, le]));
  const taken = [];
  const nets = {};
  for (const e of g.edges) (nets[e.sourcePort] ||= []).push(e);
  S.edgeById = {};
  for (const f of lay.containers) taken.push({ x: f.x, y: f.y, w: Math.min(f.width, 260), h: 28 });   // the frames' titles
  for (const e of g.edges) {
    const le = byLe[e.id];
    const pts = le ? bdPts(le) : [];
    if (pts.length < 2) continue;
    const vec = (e.signal?.n || 0) > 1;
    const eg = s("g", { class: `edge bd-edge${vec ? " bd-vec" : ""}`, "data-id": e.id, "data-nodes": `${e.source} ${e.target}`, "data-net": e.sourcePort });
    const d = pts.map((p, i) => `${i ? "L" : "M"}${p.x},${p.y}`).join("");
    const tip = pts[pts.length - 1], prev = pts[pts.length - 2];
    const ang = Math.atan2(tip.y - prev.y, tip.x - prev.x), L = vec ? 10 : 8;
    const back = { x: tip.x - Math.cos(ang) * (L - 1), y: tip.y - Math.sin(ang) * (L - 1) };
    const short = [...pts.slice(0, -1), back].map((p, i) => `${i ? "L" : "M"}${p.x},${p.y}`).join("");
    eg.append(s("path", { d, class: "bd-hit" }), s("path", { d: short, class: "bd-wire" }),
              s("path", { class: "bd-head", d: `M${tip.x},${tip.y} L${tip.x - L * Math.cos(ang - 0.38)},${tip.y - L * Math.sin(ang - 0.38)} L${tip.x - L * Math.cos(ang + 0.38)},${tip.y - L * Math.sin(ang + 0.38)} Z` }));
    eg.append(s("title", {}, bdSignalWords(e)));
    eg.addEventListener("mouseenter", () => bdTrace(svg, { net: e.sourcePort }));
    eg.addEventListener("mouseleave", () => bdTrace(svg, S.bdSel || null));
    eg.addEventListener("click", (ev) => { ev.stopPropagation(); S.bdSel = { net: e.sourcePort }; bdTrace(svg, S.bdSel); openSignal(e); });
    if (vec) {                                          // a vector: a slash across it, and how many signals
      const [a, b] = pts.slice(1).map((q, i) => [pts[i], q]).sort((x, y) => (Math.abs(y[0].x - y[1].x) + Math.abs(y[0].y - y[1].y)) - (Math.abs(x[0].x - x[1].x) + Math.abs(x[0].y - x[1].y)))[0];
      const mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2, horiz = Math.abs(a.y - b.y) < 1;
      eg.append(s("path", { class: "bd-slash", d: horiz ? `M${mx - 4},${my + 6} L${mx + 4},${my - 6}` : `M${mx - 6},${my + 4} L${mx + 6},${my - 4}` }),
                s("text", { class: "bd-count", x: mx + (horiz ? 0 : 9), y: my + (horiz ? 17 : 4), "text-anchor": horiz ? "middle" : "start" }, String(e.signal.n)));
      taken.push({ x: mx - 8, y: my - 8, w: 16, h: 30 });
    }
    edgesG.append(eg);
  }
  // take-off points: where the lines of one signal part
  const dots = s("g", { class: "bd-dots" });
  for (const [port, es] of Object.entries(nets)) {
    if (es.length < 2) continue;
    const routes = es.map((e) => (byLe[e.id] ? bdPts(byLe[e.id]) : [])).filter((p) => p.length > 1);
    for (const p of bdTakeoffs(routes)) dots.append(s("circle", { cx: p.x, cy: p.y, r: 3.2, class: "bd-dot" }));
  }
  // port marks where lines cross an open system's frame, each named
  const marks = s("g", { class: "bd-portmarks" });
  const crossings = bdFrameCrossings(lay, g, byLe);
  for (const c of crossings) taken.push({ x: c.x - 6, y: c.y - 6, w: 12, h: 12 });
  for (const f of lay.containers) taken.push({ x: f.x + f.width - 22, y: f.y, w: 22, h: 22 });      // its close button
  const edgeSegs = lay.edges.flatMap((le) => { const q = bdPts(le); return q.slice(1).map((b, i) => [q[i], b]); });
  for (const c of crossings) {
    const sg = c.edge.signal || {};
    const mk = s("g", { class: "bd-portmark-g", "data-net": c.edge.sourcePort, "data-frame": c.frame.id });
    mk.append(s("rect", { class: "bd-portmark", x: c.x - 4.5, y: c.y - 4.5, width: 9, height: 9, rx: 2 }),
              s("title", {}, `${c.into ? "In" : "Out"} port of ${c.frame.id.split(":").slice(1).join(":")}: ${bdSignalWords(c.edge)}`));
    marks.append(mk);
    if (!sg.sym) continue;
    const w = 10 + (sg.sub ? bdTextW(sg.sub, true) * 0.82 : 0), hgt = 13;
    const out = c.side === "W" || c.side === "N" ? -1 : 1;             // outside the frame first, then inside
    const tries = c.horiz
      ? [[c.x + (out < 0 ? -w - 6 : 6), c.y - hgt - 2], [c.x + (out < 0 ? 6 : -w - 6), c.y - hgt - 2],
         [c.x + (out < 0 ? -w - 6 : 6), c.y + 3], [c.x + (out < 0 ? 6 : -w - 6), c.y + 3]]
      : [[c.x + 6, c.y + (out < 0 ? -hgt - 6 : 6)], [c.x - w - 6, c.y + (out < 0 ? -hgt - 6 : 6)],
         [c.x + 6, c.y + (out < 0 ? 6 : -hgt - 6)], [c.x - w - 6, c.y + (out < 0 ? 6 : -hgt - 6)]];
    const onEdge = (r) => (lay.containers || []).some((f) =>
      ((r.y < f.y && r.y + r.h > f.y) || (r.y < f.y + f.height && r.y + r.h > f.y + f.height)) && r.x < f.x + f.width && r.x + r.w > f.x ||
      ((r.x < f.x && r.x + r.w > f.x) || (r.x < f.x + f.width && r.x + r.w > f.x + f.width)) && r.y < f.y + f.height && r.y + r.h > f.y);
    const free = (r) => !taken.some((q) => r.x < q.x + q.w && q.x < r.x + r.w && r.y < q.y + q.h && q.y < r.y + r.h) &&
      !lay.children.some((q) => r.x < q.x + q.width && q.x < r.x + r.w && r.y < q.y + q.height && q.y < r.y + r.h) && !onEdge(r) &&
      !edgeSegs.some(([a, b]) => Math.max(a.x, b.x) > r.x && Math.min(a.x, b.x) < r.x + r.w && Math.max(a.y, b.y) > r.y && Math.min(a.y, b.y) < r.y + r.h);
    for (const k of [1, 2, 3]) {                                         // stacked further out, when crowded
      const o = k * (hgt + 2);
      tries.push(...(c.horiz ? [[c.x + (out < 0 ? -w - 6 : 6), c.y - hgt - 2 - o], [c.x + (out < 0 ? -w - 6 : 6), c.y + 3 + o]]
                             : [[c.x + 6, c.y + (out < 0 ? -hgt - 6 - o : 6 + o)], [c.x - w - 6, c.y + (out < 0 ? -hgt - 6 - o : 6 + o)]]));
    }
    const spot = tries.map(([x, y]) => ({ x, y, w, h: hgt })).find(free);
    if (!spot) continue;
    taken.push(spot);
    const t = bdSym(mk, spot.x + 1, spot.y + 9, { sym: sg.sym, sub: sg.sub, bold: (sg.n || 0) > 1 }, { size: 11, anchor: "start", cls: "bd-sig bd-portname" });
    t.setAttribute("data-net", c.edge.sourcePort);
  }
  // the signs at each summing junction's inputs
  for (const n of g.nodes.filter((x) => x.kind === "sum")) {
    const c = box[n.id];
    if (!c) continue;
    for (const p of n.ins) {
      const at = lay.ports[p.id];
      if (!at || !p.sign) continue;
      const off = { W: [-8, -6], N: [7, -4], S: [7, 13], E: [8, -6] }[p.side] || [0, 0];
      labelsG.append(s("text", { x: at.x + off[0], y: at.y + off[1], class: "bd-sign", "text-anchor": "middle", "data-sum": n.id }, p.sign));
      taken.push({ x: at.x + off[0] - 5, y: at.y + off[1] - 10, w: 10, h: 12 });
    }
  }
  // each signal's name, once, near where it leaves
  const boxes = lay.children;
  for (const [port, es] of Object.entries(nets)) {
    const e = es[0], sg = e.signal || {};
    if (!sg.sym) continue;
    const src = byId[e.source];
    if (src?.kind === "input" || (src?.kind === "port")) continue;     // an input says its name itself
    if (es.some((x) => byId[x.target]?.kind === "output")) continue;    // as does an output it reaches
    const w = 10 + (sg.sub ? bdTextW(sg.sub, true) * 0.82 : 0), hgt = 14;
    const pts = byLe[e.id] ? bdPts(byLe[e.id]) : [];
    const others = g.edges.filter((x) => x.sourcePort !== port && byLe[x.id]).flatMap((x) => { const q = bdPts(byLe[x.id]); return q.slice(1).map((b, i) => [q[i], b]); });
    const spot = bdLabelSpot(pts, taken, w, hgt, boxes, others) || bdLabelSpot(pts, taken, w, hgt, boxes);
    if (!spot) continue;
    taken.push(spot);
    const t = bdSym(labelsG, spot.x + 1, spot.y + 9, { sym: sg.sym, sub: sg.sub, bold: (sg.n || 0) > 1 }, { size: 12, anchor: "start", cls: "bd-sig" });
    t.setAttribute("data-net", port);
  }
  const nodesG = s("g", { class: "bd-nodes" });
  for (const n of g.nodes) {
    const c = box[n.id];
    if (!c) continue;
    const el = bdNode(n, c);
    el.addEventListener("mouseenter", () => bdTrace(svg, { node: n.id }));
    el.addEventListener("mouseleave", () => bdTrace(svg, S.bdSel || null));
    el.addEventListener("click", (ev) => {
      ev.stopPropagation();
      if (ev.shiftKey || ev.metaKey) { chooseShape(n.id, "toggle"); return; }     // (what it is chosen: interact.js)
      S.bdSel = { node: n.id }; bdTrace(svg, S.bdSel); chooseShape(n.id); openBlock(n);
    });
    nodesG.append(el);
  }
  vp.append(edgesG, nodesG, dots, marks, labelsG);
  svg.replaceChildren(vp);
  applyView(svg);
  if (S.bdSel) bdTrace(svg, S.bdSel);
  if (typeof markInteraction === "function" && svg.matches("svg.canvas")) markInteraction(svg);   // the parts chosen, lit
}

function bdTakeoffs(routes) {                         // the points where lines that leave one port together part
  const on = (p, pts) => pts.slice(1).some((b, i) => { const a = pts[i];
    return Math.abs(a.x - b.x) < 0.5 ? Math.abs(p.x - a.x) < 0.6 && p.y >= Math.min(a.y, b.y) - 0.6 && p.y <= Math.max(a.y, b.y) + 0.6
      : Math.abs(p.y - a.y) < 0.6 && p.x >= Math.min(a.x, b.x) - 0.6 && p.x <= Math.max(a.x, b.x) + 0.6; });
  const walk = (pts, step = 1) => { const out = []; for (let i = 1; i < pts.length; i++) { const a = pts[i - 1], b = pts[i];
    const n = Math.max(1, Math.round((Math.abs(a.x - b.x) + Math.abs(a.y - b.y)) / step));
    for (let k = 0; k < n; k++) out.push({ x: a.x + ((b.x - a.x) * k) / n, y: a.y + ((b.y - a.y) * k) / n }); }
    out.push(pts[pts.length - 1]); return out; };
  const found = [];
  for (let i = 0; i < routes.length; i++) for (let j = i + 1; j < routes.length; j++) {
    const a = walk(routes[i]);
    let last = null;
    for (const p of a) { if (on(p, routes[j])) last = p; else break; }
    if (last && !found.some((q) => Math.abs(q.x - last.x) < 2 && Math.abs(q.y - last.y) < 2)) found.push(last);
  }
  return found;
}

function bdTrace(svg, sel) {                          // what is pointed at, or chosen, lit; nothing else changes
  for (const x of svg.querySelectorAll(".bd-lit")) x.classList.remove("bd-lit");
  if (!sel) return;
  if (sel.node) {
    svg.querySelector(`.node[data-id="${CSS.escape(sel.node)}"]`)?.classList.add("bd-lit");
    for (const e of svg.querySelectorAll(".bd-edge")) if (e.dataset.nodes.split(" ").includes(sel.node)) e.classList.add("bd-lit");
  }
  if (sel.net) for (const e of svg.querySelectorAll(`[data-net="${CSS.escape(sel.net)}"]`)) e.classList.add("bd-lit");
}

function bdSignalWords(e) {
  const sg = e.signal || {};
  const what = { reference: "the reference input", error: "the error, e = r − y_m", measured: "the measured output, through its sensor H",
                 sampled: "a sampled signal, one value every T", command: "a command",
                 control: "a control signal (what a block moves or sets)", output: "a process output", disturbance: "a disturbance",
                 vector: `a vector of ${sg.n} signals` }[sg.what] || "a signal";
  return `${sg.sym || ""}${sg.sub ? "_" + sg.sub : ""}: ${what}${e.keys ? " (" + e.keys.map((k) => k.split(".").slice(1).join(".")).join(", ") + ")" : ""}`;
}

/* ---- the side panel: a block's definition, as MathML */
function mathml(tree, display = true) {
  const build = (x) => {
    if (typeof x === "string" || typeof x === "number") return document.createTextNode(String(x));
    const [tag, ...rest] = x;
    const el = document.createElementNS(MATHML, tag);
    let kids = rest;
    if (rest.length && rest[0] && typeof rest[0] === "object" && !Array.isArray(rest[0])) {
      for (const [k, v] of Object.entries(rest[0])) el.setAttribute(k, v);
      kids = rest.slice(1);
    }
    for (const k of kids) if (k != null) el.append(build(k));
    return el;
  };
  const m = document.createElementNS(MATHML, "math");
  if (display) m.setAttribute("display", "block");
  m.append(build(tree));
  return m;
}

function openBlock(n) {
  const fn = n.fn || {};
  const kinds = { controller: "controller", actuator: "actuator", process: "process", sensor: "sensor (feedback path)",
                  subsystem: "subsystem", comparator: "summing junction", "process-sum": "summing junction", reference: "reference input",
                  disturbance: "disturbance input", output: "output", "in-port": "In port", "out-port": "Out port",
                  sampler: "sampler (A/D)", hold: "zero-order hold (D/A)", junction: "summing junction" };
  const kind = n.kind === "frame" ? (n.frame === "cascade" ? "inner loop (cascade)" : "subsystem, open") :
    n.kind === "mux" ? "mux" : n.kind === "demux" ? "demux" : kinds[n.role] || n.kind;
  const title = fn.sym ? mathml(["mrow", fn.sub ? ["msub", ["mi", fn.sym], ["mtext", fn.sub]] : ["mi", fn.sym],
                                  ...(fn.arg ? [["mo", "("], ["mi", fn.arg], ["mo", ")"]] : [])], false) : (fn.name || n.label);
  const defs = (n.math || []).map((m) => h("div", { class: "bd-math" }, mathml(m)));
  const rows = (n.rows || []).filter(([, v]) => v != null && v !== "");
  const kids = [h("div", { class: "kind" }, kind), h("h2", {}, title)];
  // a loop's comparator, controller or process output: its scope first (charts.js)
  if (["comparator", "controller", "output"].includes(n.role)) for (const l of (n.loops || []).filter((x) => S.status?.loops?.[x])) {
    if ((n.loops || []).length > 1) kids.push(h("div", { class: "strip-title" }, h("b", {}, l)));
    kids.push(loopScope(l));
  }
  if (n.says) kids.push(h("p", { class: "what" }, rich(op(n.says))));
  if (defs.length) kids.push(h("h3", {}, fn.linear === false || fn.name ? "What it computes" : "Its function"), ...defs);
  if (rows.length) kids.push(h("h3", {}, "In the model"), dl(rows.map(([k, v]) => [k, typeof v === "string" ? rich(op(v)) : v])));
  // the loop it is the process of, identified (control.js); a controller's law with that process, and its tuning
  if (n.role === "process") for (const l of n.y_of || []) kids.push(controlBox(l, "process"));
  if (n.role === "controller" && n.id?.startsWith("blk:")) for (const l of (n.loops || []).filter((x) => S.status?.loops?.[x]))
    kids.push(controlBox(l, "controller", { block: n.id.slice(4) }));
  const loops = n.loops || [];
  if (loops.length) kids.push(h("h3", {}, `In the loop${loops.length > 1 ? "s" : ""} of`),
    h("p", {}, ...loops.flatMap((l, i) => [i ? ", " : "", h("a", { href: "#", onclick: (ev) => { ev.preventDefault(); openLoop(l); } }, l)])));
  const sysName = n.role === "subsystem" ? n.label : n.kind === "frame" && n.frame === "system" ? n.label : null;
  if (sysName) kids.push(h("div", { class: "actions" }, h("button", { onclick: () => S.toggleSystem?.(sysName) }, n.role === "subsystem" ? "Open it here" : "Close it into one block"),
    h("button", { onclick: () => S.drill?.(sysName) }, "Draw it alone")));
  if (n.kind === "port" && n.in != null) kids.push(h("div", { class: "actions" }, h("button", { onclick: () => S.drill?.(n.in || "") }, `Go to ${n.in || "the top level"}`)));
  showDetail(...kids);
}

function openSignal(e) {
  const sg = e.signal || {};
  const byId = Object.fromEntries((S.graph?.nodes || []).map((n) => [n.id, n]));
  const name = (id) => { const n = byId[id]; return n ? h("a", { href: "#", onclick: (ev) => { ev.preventDefault(); openBlock(n); } }, bdFnText(n)) : id; };
  const title = mathml(sg.sub ? ["msub", sg.n > 1 ? ["mi", { mathvariant: "bold" }, sg.sym] : ["mi", sg.sym], ["mtext", sg.sub]] : ["mi", sg.sym || "?"], false);
  showDetail(h("div", { class: "kind" }, "Signal"), h("h2", {}, title), h("p", { class: "what" }, rich(bdSignalWords(e))),
    dl([["from", name(e.source)], ["to", name(e.target)], ["sign", e.sign || null],
        ["carries", e.keys ? e.keys.map((k) => k.split(".").slice(1).join(".")).join(", ") : (e.key || "").split(".").slice(1).join(".")],
        ["measured", e.note ? rich(e.note) : null]]));
}

/* ---- the page: laid out again only when what is drawn changes */
function bdSig(g) {
  return JSON.stringify([g.nodes.map((n) => [n.id, n.parent, n.ins.map((p) => p.id), n.outs.map((p) => p.id), bdFnText(n)]),
                         g.edges.map((e) => e.id), (g.frames || []).map((f) => [f.id, f.parent])]);
}
async function drawBlocksView(svg, g) {
  const sg = bdSig(g);
  if (sg === S.graphSig && S.layout) {                 // the same diagram: its parts keep their places and frames
    const within = Object.fromEntries(S.layout.children.map((c) => [c.id, c.within]));
    for (const n of g.nodes) n.systems = within[n.id] || [];
    return S.layout;
  }
  const lay = await bdLayout(g);
  S.graphSig = sg;
  S.layout = lay;
  bdDraw(svg, g, lay);
  bdRoute(lay, g);
  lay.whenRouted.then(() => { if (S.layout === lay && !S.pressed) bdDraw(svg, S.graph, lay); });
  return lay;
}

function blocksLegend() {
  const row = (svgTxt, text) => [h("span", { html: `<svg width="30" height="20">${svgTxt}</svg>` }), h("span", {}, text)];
  const ink = 'stroke="currentColor" fill="none" stroke-width="1.3"';
  return h("div", { class: "legend bd-legend" },
    row(`<rect x="2" y="3" width="26" height="14" ${ink}/><text x="15" y="14" font-size="9" text-anchor="middle" font-style="italic" fill="currentColor">P</text>`,
        "a block, its function inside: C a controller, P a process, H a sensor with dynamics of its own (a unity sensor is the feedback wire itself), Q a subsystem; C(z) runs every T, (s) is continuous; Q without (s) holds sampled or nonlinear parts; click it for its definition"),
    row(`<path d="M0,10 H8 M22,10 H30 M8,10 L20,3" ${ink}/><circle cx="8" cy="10" r="1.6" fill="currentColor"/><circle cx="22" cy="10" r="1.6" fill="currentColor"/>`,
        "a sampler (T): where a continuous signal enters a discrete controller C(z)"),
    row(`<rect x="2" y="3" width="26" height="14" ${ink}/><path d="M6,15 H10 V12 H14 V9 H18 V6 H24" ${ink}/>`,
        "a zero-order hold (ZOH): where C(z) drives the continuous process, each value held for one period"),
    row(`<rect x="3" y="4" width="24" height="12" rx="6" ${ink}/>`, "an In or Out port: a signal crossing the edge of a system drawn alone"),
    row(`<path d="M15,0 V20" stroke="currentColor" stroke-width="0.8"/><path d="M2,10 H28" ${ink}/><rect x="11" y="6" width="8" height="8" rx="2" ${ink} fill="var(--bg, #fff)"/>`,
        "a port mark: where a signal crosses the frame of an open system, named"),
    row(`<rect x="2" y="3" width="26" height="14" ${ink}/><path d="M6,13 H12 V6 H18" ${ink}/>`, "not linear (an on-off controller: a relay; a program, an AI agent, a person): named, with a sketch where there is a standard one (relay, saturation, dead zone); no transfer function is claimed"),
    row(`<circle cx="15" cy="10" r="7" ${ink}/><text x="5" y="8" font-size="9" fill="currentColor">+</text><text x="19" y="21" font-size="9" fill="currentColor">−</text>`, "a summing junction, with the sign of each input"),
    row(`<path d="M2,10 H26" ${ink}/><circle cx="12" cy="10" r="2.6" fill="currentColor"/>`, "a take-off point: one signal, to several places"),
    row(`<path d="M2,10 H26" stroke="currentColor" stroke-width="2.6"/><path d="M12,15 L18,5" ${ink}/>`, "a vector of signals (bold, a slash and how many); a thin bar gathers or splits one (mux, demux)"),
    row(`<rect x="2" y="2" width="26" height="16" ${ink} stroke-dasharray="3 2"/>`, "an inner loop: a cascade's, given its setpoint by the outer loop"),
    h("span", { class: "sym" }, "r e u y d"), h("span", {}, "reference (its value), error (r − y", h("sub", {}, "m"), "), control signal, output (y", h("sub", {}, "m"), " measured through H), disturbance; subscripts name the loop or the part; k a sample"));
}
