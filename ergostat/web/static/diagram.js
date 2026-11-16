/* the control and wiring diagrams: shapes, ELK layout, drawing, pan and zoom, the side panel */
"use strict";
/* ------------------------------------------------------------------ the diagram */

const SIZE = { terminal: [120, 34], stock: [168, 84], valve: [40, 40], disturbance: [40, 40], cloud: [54, 36], sensor: [44, 44], controller: [200, 92], agent: [210, 92] };
const CH = 6.7;   // px per character, for label sizes
const OPEN_LOOP = "open loop: acts on its schedule, reads nothing";

function labelLines(n) {
  if (n.kind === "valve") return [n.label, `${n.position != null ? "open " + fmt(n.position) + " · " : ""}${n.rateText}${n.max ? ` · ≤ ${fmt(n.max)} a run` : ""}${n.mode && n.mode !== "auto" ? " · " + n.mode : ""}`, n.agent ? "§badge" : null].filter(Boolean);
  if (n.kind === "disturbance") return [n.label, `${n.rateText}${n.estimated ? " (est.)" : ""}`, n.agent ? "§badge" : null].filter(Boolean);
  if (n.kind === "sensor") return [n.label, n.reading != null ? `reads ${n.reading}` : "no reading", n.agent ? "§badge" : null].filter(Boolean);
  return [];
}
function badgeText(a) { return a ? `${a.kind} · ${a.name}${a.when ? " · " + a.when : ""}` : ""; }
function textWidth(t) { return t.length * CH; }

function sig(g) {
  // what the layout depends on: the parts, the wires, and how many label lines each part has
  return JSON.stringify([g.kind, g.nodes.map((n) => `${n.id}:${labelLines(n).length}:${n.agent?.name || ""}:${(n.ports || []).map((p) => p.id).join(",")}`).sort(),
                         g.edges.map((e) => e.id).sort()]);
}

/* the pipes that join one loop to the next (a valve's flow from one stock into another): left out of
   a wrapped layout, so each loop's chain is laid out on its own and the chains are packed in rows */
function couplings(g) {
  const byId = Object.fromEntries(g.nodes.map((n) => [n.id, n]));
  const fromStock = new Set(g.edges.filter((e) => e.kind === "pipe" && e.source.startsWith("stock:")).map((e) => e.target));
  return g.edges.filter((e) => e.kind === "pipe" && fromStock.has(e.source) && e.target.startsWith("stock:")
                               && byId[e.source]?.kind === "valve" && !byId[e.target]?.outside);
}

/* which side of a system box each port is on: the side facing what it joins (worked out after a
   first layout), else inputs left and outputs right */
function portSides(g) {
  for (const n of g.nodes) if (n.kind === "system") for (const p of n.ports) p.at = S.portAt?.[p.id] || (p.side === "in" ? "west" : "east");
}
function wantedSides(lay, g) {
  const box = Object.fromEntries(lay.children.map((c) => [c.id, c]));
  const want = {};
  for (const n of g.nodes) {
    if (n.kind !== "system" || !box[n.id]) continue;
    const b = box[n.id], mid = b.x + b.width / 2;
    for (const p of n.ports) {
      const peers = g.edges.filter((e) => e.sourcePort === p.id || e.targetPort === p.id).map((e) => box[e.sourcePort === p.id ? e.target : e.source]).filter(Boolean);
      if (!peers.length) continue;
      const cx = peers.reduce((a, c) => a + c.x + c.width / 2, 0) / peers.length;
      want[p.id] = cx < mid ? "west" : "east";
    }
  }
  return want;
}

async function layoutGraph(g, aspect, cut = false, again = false) {
  portSides(g);
  const ORDER = { cloud: 0, terminal: 0, disturbance: 1, stock: 2, valve: 3, system: 3, sensor: 5, controller: 6, agent: 2 };
  const rank = (n) => (n.kind === "cloud" ? (n.id.endsWith(":out") ? 4 : 0) : ORDER[n.kind] ?? 3);
  const nodesInOrder = [...g.nodes].sort((a, b) => rank(a) - rank(b));
  const byIdNodes = Object.fromEntries(g.nodes.map((n) => [n.id, n]));
  const children = nodesInOrder.map((n) => {
    let [w, hgt] = SIZE[n.kind] || [60, 40];
    if (n.kind === "stock") {                         // the title, and the value beside the setpoint, all fit
      const lp = Object.values(g.loops || {}).find((l) => l.stock === n.label);
      w = Math.max(w, textWidth(n.label) + 34, (n.valueText || "").length * 14 + textWidth(n.unit || "") + textWidth(lp ? lp.setpoint : "") + 44);
    }
    if (n.kind === "agent") w = Math.max(w, textWidth(n.label) * 1.15 + textWidth(`rung ${n.rung} · ${n.agentKind}`) + 56,
                                         ...(n.roles || []).map((r) => textWidth(`${r.kind} ${r.name}`) + 40));   // the name and its rung, apart
    if (n.kind === "controller") w = Math.max(w, textWidth(n.label) * 1.12 + 120, textWidth("holds " + n.setpoint) + 60,   // the title is bold
                                              n.openLoop ? textWidth(OPEN_LOOP) + 30 : 0);
    if (n.kind === "system") [w, hgt] = systemSize(n);
    if (n.kind === "terminal") w = Math.max(textWidth(n.label + (n.valueText ? "  " + n.valueText : "")), textWidth(n.in ? "in " + n.in : "")) + 34;
    const lines = labelLines(n);
    const node = { id: n.id, width: w, height: hgt, layoutOptions: {} };
    if (n.kind === "system") {                        // its ports where their names are written: inputs left, outputs right
      node.layoutOptions["elk.portConstraints"] = "FIXED_POS";
      const row = { west: 0, east: 0 };
      node.ports = n.ports.map((p) => ({ id: p.id, width: 8, height: 8, x: p.at === "west" ? -4 : w - 4, y: SYS_TOP + (row[p.at]++) * SYS_ROW - 4,
                                         layoutOptions: { "elk.port.side": p.at === "west" ? "WEST" : "EAST" } }));
    }
    if (lines.length) {
      const lw = Math.max(...lines.map((l) => l === "§badge" ? textWidth(badgeText(n.agent)) + 18 : textWidth(l))) + 8;
      node.labels = [{ id: n.id + ":label", text: lines.join("\n"), width: lw, height: lines.length * 16 + 4 }];
      node.layoutOptions["elk.nodeLabels.placement"] = "OUTSIDE V_BOTTOM H_CENTER";
    }
    if (n.kind === "valve" || n.kind === "disturbance") {
      node.layoutOptions["elk.portConstraints"] = "FIXED_SIDE";
      node.ports = [
        { id: n.id + ":in", width: 1, height: 1, layoutOptions: { "elk.port.side": "WEST" } },
        { id: n.id + ":out", width: 1, height: 1, layoutOptions: { "elk.port.side": "EAST" } },
        { id: n.id + ":ctl", width: 1, height: 1, layoutOptions: { "elk.port.side": "NORTH" } },
        { id: n.id + ":sense", width: 1, height: 1, layoutOptions: { "elk.port.side": "NORTH" } },   // its sensor reads here, apart from the command
      ];
    }
    return node;
  });
  const flowNode = new Set(g.nodes.filter((n) => n.kind === "valve" || n.kind === "disturbance").map((n) => n.id));
  const cuts = cut && !g.nodes.some((n) => (n.systems || []).length && g.tree) ? couplings(g) : [];
  const cutIds = new Set(cuts.map((e) => e.id));
  const edges = g.edges.filter((e) => !cutIds.has(e.id)).map((e) => {
    let src = e.sourcePort || e.source, dst = e.targetPort || e.target;
    if (e.sourcePort || e.targetPort) {
      if (!e.targetPort && flowNode.has(dst)) dst = dst + (e.kind === "pipe" ? ":in" : ":ctl");
      if (!e.sourcePort && flowNode.has(src)) src = src + (e.kind === "pipe" ? ":out" : ":ctl");
    } else if (e.kind === "pipe") {
      if (flowNode.has(dst)) dst = dst + ":in";
      if (flowNode.has(src)) src = src + ":out";
    } else if (flowNode.has(dst)) dst = dst + ":ctl";
    else if (flowNode.has(src)) src = src + (e.kind === "measure" ? ":sense" : ":ctl");
    const out = { id: e.id, sources: [src], targets: [dst], layoutOptions: {} };
    if (e.kind === "pipe") { out.layoutOptions["elk.layered.priority.straightness"] = "20"; out.layoutOptions["elk.layered.priority.direction"] = "20"; out.layoutOptions["elk.layered.priority.shortness"] = "10"; }
    if (e.kind === "wire" && e.via && e.via.length) {
      const t = e.via.slice(0, 2).join(", ") + (e.via.length > 2 ? ` +${e.via.length - 2}` : "");
      out.labels = [{ id: e.id + ":l", text: t, width: textWidth(t) + 6, height: 14 }];
    }
    return out;
  });
  // an open system is laid out as one container, its parts together, nested as the systems nest
  const open = new Set(g.tree ? g.nodes.flatMap((n) => n.systems || []) : []);
  let roots = children;
  if (open.size) {
    const cont = {};
    const box = (name) => (cont[name] ||= { id: "hull:" + name, children: [], layoutOptions: { "elk.padding": "[top=44,left=26,bottom=26,right=26]" } });
    const parentOf = (name) => { let x = g.tree[name]?.within; while (x && !open.has(x)) x = g.tree[x]?.within; return x || null; };
    for (const name of open) box(name);
    roots = [];
    for (const c of children) {
      const inner = (byIdNodes[c.id]?.systems || [])[0];
      (inner ? cont[inner].children : roots).push(c);
    }
    for (const name of open) { const p = parentOf(name); (p ? cont[p].children : roots).push(cont[name]); }
  }
  const graph = {
    id: "root", children: roots, edges,
    layoutOptions: {
      ...(open.size ? { "elk.hierarchyHandling": "INCLUDE_CHILDREN" } : {}),
      "elk.layered.mergeEdges": "true",
      "elk.algorithm": "layered", "elk.direction": g.kind === "wiring" ? "DOWN" : "RIGHT", "elk.edgeRouting": "ORTHOGONAL",
      "elk.layered.spacing.nodeNodeBetweenLayers": "64", "elk.spacing.nodeNode": "36", "elk.spacing.edgeNode": "18",
      "elk.spacing.edgeEdge": "12", "elk.layered.spacing.edgeNodeBetweenLayers": "18",
      "elk.layered.nodePlacement.strategy": "NETWORK_SIMPLEX", "elk.layered.crossingMinimization.semiInteractive": "false",
      "elk.layered.considerModelOrder.strategy": "NODES_AND_EDGES", "elk.separateConnectedComponents": "true",
      "elk.spacing.componentComponent": "70", "elk.spacing.labelNode": "6", "elk.edgeLabels.placement": "CENTER",
      "elk.layered.cycleBreaking.strategy": "GREEDY", "elk.aspectRatio": String(aspect || 1.6),
      "elk.padding": "[top=40,left=40,bottom=40,right=40]",
    },
  };
  const lay = await elk.layout(graph);
  if (open.size) flatten(lay);
  if (!again && g.nodes.some((n) => n.kind === "system")) {     // ports facing away from what they join: turn them, lay out again
    const want = wantedSides(lay, g);
    if (Object.entries(want).some(([id, at]) => g.nodes.some((n) => n.ports?.some((p) => p.id === id && p.at !== at)))) {
      S.portAt = { ...(S.portAt || {}), ...want };
      return layoutGraph(g, aspect, cut, true);
    }
  }
  if (g.kind !== "wiring") reroute(lay, g);
  if (cuts.length) {
    restack(lay, g);
    routeCuts(lay, cuts);
  }
  return lay;
}

/* lines routed again, on a grid, around the parts and the other lines but straight through the
   outlines of systems: the layout itself must take a line into a system from the side its layers
   run (the left), which sends lines the long way round. Only lines that cross a system's edge, or
   that the layout sent far round, are routed again; pipes and lines into a system box's ports keep
   their places at either end */
const GRID = 8;
function reroute(lay, g) {
  const edgeOf = Object.fromEntries(g.edges.map((e) => [e.id, e]));
  const nodeOf = Object.fromEntries(g.nodes.map((n) => [n.id, n]));
  const box = Object.fromEntries(lay.children.map((c) => [c.id, c]));
  const pts = (le) => { const sec = (le.sections || [])[0]; return sec ? [sec.startPoint, ...(sec.bendPoints || []), sec.endPoint] : []; };
  const len = (ps) => ps.slice(1).reduce((a, p, i) => a + Math.abs(p.x - ps[i].x) + Math.abs(p.y - ps[i].y), 0);
  const inner = (id) => (nodeOf[id]?.systems || [])[0] || (id.startsWith("system:") ? "box:" + id : null);
  const todo = lay.edges.filter((le) => {
    const e = edgeOf[le.id], p = pts(le);
    if (!e || le.cut || p.length < 2) return false;
    const crosses = inner(e.source) !== inner(e.target) || e.sourcePort || e.targetPort;
    const far = len(p) > 1.5 * (Math.abs(p[0].x - p[p.length - 1].x) + Math.abs(p[0].y - p[p.length - 1].y)) + 80;
    return crosses || far;
  });
  // a line drawn on top of another (not a net: lines sharing an end and kind may share their way there)
  const segsOf = (le) => { const q = pts(le); return q.slice(1).map((b, i) => [q[i], b]); };
  const net = (a, b) => a.kind === b.kind && ((a.source === b.source && (a.sourcePort || "") === (b.sourcePort || "")) ||
                                              (a.target === b.target && (a.targetPort || "") === (b.targetPort || "")));
  const along = ([a, b], [c, d]) => {
    if (Math.abs(a.y - b.y) < 1 && Math.abs(c.y - d.y) < 1 && Math.abs(a.y - c.y) < 3)
      return Math.min(Math.max(a.x, b.x), Math.max(c.x, d.x)) - Math.max(Math.min(a.x, b.x), Math.min(c.x, d.x));
    if (Math.abs(a.x - b.x) < 1 && Math.abs(c.x - d.x) < 1 && Math.abs(a.x - c.x) < 3)
      return Math.min(Math.max(a.y, b.y), Math.max(c.y, d.y)) - Math.max(Math.min(a.y, b.y), Math.min(c.y, d.y));
    return 0;
  };
  const chosen = new Set(todo.map((le) => le.id));
  const drawn = lay.edges.filter((le) => edgeOf[le.id] && !le.cut);
  for (let i = 0; i < drawn.length; i++) for (let j = i + 1; j < drawn.length; j++) {
    const A = drawn[i], B = drawn[j], ea = edgeOf[A.id], eb = edgeOf[B.id];
    if (chosen.has(A.id) || chosen.has(B.id) || net(ea, eb)) continue;
    if (!segsOf(A).some((s) => segsOf(B).some((t) => along(s, t) > 16))) continue;
    const pick = ea.kind === "pipe" && eb.kind !== "pipe" ? B : eb.kind === "pipe" && ea.kind !== "pipe" ? A : B;   // a pipe keeps its way
    chosen.add(pick.id); todo.push(pick);
  }
  if (!todo.length) return;
  // the grid: every part (with its labels) is in the way; the lines already drawn are costly to run along or cross
  const rects = lay.children.map((c) => {
    const ls = c.labels || [];
    const xs = [c.x, c.x + c.width, ...ls.flatMap((l) => [c.x + l.x, c.x + l.x + l.width])];
    const ys = [c.y, c.y + c.height, ...ls.flatMap((l) => [c.y + l.y, c.y + l.y + l.height])];
    return { id: c.id, x0: Math.min(...xs), y0: Math.min(...ys), x1: Math.max(...xs), y1: Math.max(...ys) };
  });
  const X0 = Math.min(...rects.map((r) => r.x0)) - 120, Y0 = Math.min(...rects.map((r) => r.y0)) - 120;
  const W = Math.ceil((Math.max(...rects.map((r) => r.x1)) + 120 - X0) / GRID), H = Math.ceil((Math.max(...rects.map((r) => r.y1)) + 120 - Y0) / GRID);
  const cx = (x) => Math.max(0, Math.min(W - 1, Math.round((x - X0) / GRID))), cy = (y) => Math.max(0, Math.min(H - 1, Math.round((y - Y0) / GRID)));
  const owner = new Int32Array(W * H).fill(-1);           // which part (by index) a cell is inside, with a margin
  const soft = new Uint8Array(W * H);                      // a part's labels: crossed only to save a long way round
  rects.forEach((r, i) => {
    const c = lay.children[i];
    for (let y = cy(r.y0 - 4); y <= cy(r.y1 + 4); y++) for (let x = cx(r.x0 - 4); x <= cx(r.x1 + 4); x++) soft[y * W + x] = 1;
    for (let y = cy(c.y - 6); y <= cy(c.y + c.height + 6); y++) for (let x = cx(c.x - 6); x <= cx(c.x + c.width + 6); x++) owner[y * W + x] = i;
  });
  const runH = new Uint8Array(W * H), runV = new Uint8Array(W * H);   // cells lines run through, across and down
  const mark = (ps, thick = false) => {
    for (let i = 1; i < ps.length; i++) {
      const a = ps[i - 1], b = ps[i];
      for (const k of thick ? [-1, 0, 1] : [0]) {
        if (Math.abs(a.y - b.y) < 1) { const y = cy(a.y) + k; if (y < 0 || y >= H) continue; for (let x = Math.min(cx(a.x), cx(b.x)); x <= Math.max(cx(a.x), cx(b.x)); x++) runH[y * W + x] = 1; }
        else { const x = cx(a.x) + k; if (x < 0 || x >= W) continue; for (let y = Math.min(cy(a.y), cy(b.y)); y <= Math.max(cy(a.y), cy(b.y)); y++) runV[y * W + x] = 1; }
      }
    }
  };
  const redo = new Set(todo.map((le) => le.id));
  for (const le of lay.edges) if (!redo.has(le.id)) mark(pts(le), edgeOf[le.id]?.kind === "pipe");
  const idx = Object.fromEntries(rects.map((r, i) => [r.id, i]));
  const DX = [1, 0, -1, 0], DY = [0, 1, 0, -1];             // right, down, left, up
  // shorter, and longer later: the routes that matter most are found first
  todo.sort((a, b) => len(pts(a)) - len(pts(b)));
  for (const le of todo) {
    const e = edgeOf[le.id], p = pts(le);
    const si = idx[e.source], ti = idx[e.target];
    const fixedStart = !!e.sourcePort || nodeOf[e.source]?.kind === "valve" || nodeOf[e.source]?.kind === "disturbance";
    const fixedEnd = !!e.targetPort || nodeOf[e.target]?.kind === "valve" || nodeOf[e.target]?.kind === "disturbance";
    const stub = new Set();                                    // the straight way out of (and into) a port is always open
    const free = (c, x, y) => x >= 0 && y >= 0 && x < W && y < H && (owner[c] === -1 || owner[c] === si || owner[c] === ti || stub.has(c));
    // where it may start: its fixed point, or anywhere round the edge of the part it leaves
    const starts = [];
    const ring = (r, inward) => {                              // the cells just outside a part, each with the way out of it
      const out = [];
      const x0 = cx(r.x0) - 1, x1 = cx(r.x1) + 1, y0 = cy(r.y0) - 1, y1 = cy(r.y1) + 1;
      for (let x = x0 + 1; x < x1; x++) { out.push([x, y0, inward ? 1 : 3]); out.push([x, y1, inward ? 3 : 1]); }
      for (let y = y0 + 1; y < y1; y++) { out.push([x0, y, inward ? 0 : 2]); out.push([x1, y, inward ? 2 : 0]); }
      return out;
    };
    const sr = rects[si], tr = rects[ti];
    if (!sr || !tr) continue;
    const dirOf = (a, b) => (Math.abs(a.x - b.x) > Math.abs(a.y - b.y) ? (b.x > a.x ? 0 : 2) : (b.y > a.y ? 1 : 3));
    const n = p.length;
    const d0 = dirOf(p[0], p[1]), dn = dirOf(p[n - 2], p[n - 1]);
    for (let k = 0; k <= 2; k++) {
      if (fixedStart) stub.add((cy(p[0].y) + DY[d0] * k) * W + cx(p[0].x) + DX[d0] * k);
      if (fixedEnd) stub.add((cy(p[n - 1].y) - DY[dn] * k) * W + cx(p[n - 1].x) - DX[dn] * k);
    }
    // a fixed end (a port) is left, or reached, two cells straight out from it
    if (fixedStart) starts.push([cx(p[0].x) + DX[d0] * 2, cy(p[0].y) + DY[d0] * 2, d0]);
    else starts.push(...ring(sr, false));
    const goals = new Map();                                   // cell → the way it must be going to arrive
    if (fixedEnd) goals.set((cy(p[n - 1].y) - DY[dn] * 2) * W + cx(p[n - 1].x) - DX[dn] * 2, dn);
    else for (const [x, y, d] of ring(tr, true)) goals.set(y * W + x, d);
    // A*, the state a cell and the way in; a bend, running along a line and crossing one all cost
    const N = W * H * 4, dist = new Float32Array(N).fill(Infinity), prev = new Int32Array(N).fill(-1);
    const heap = [];
    const push = (f, s) => { heap.push([f, s]); let i = heap.length - 1; while (i > 0) { const j = (i - 1) >> 1; if (heap[j][0] <= heap[i][0]) break; [heap[i], heap[j]] = [heap[j], heap[i]]; i = j; } };
    const pop = () => { const top = heap[0], last = heap.pop(); if (heap.length) { heap[0] = last; let i = 0; for (;;) { const l = 2 * i + 1, r = l + 1; let m = i;
      if (l < heap.length && heap[l][0] < heap[m][0]) m = l; if (r < heap.length && heap[r][0] < heap[m][0]) m = r; if (m === i) break; [heap[i], heap[m]] = [heap[m], heap[i]]; i = m; } } return top; };
    const gx = cx(p[p.length - 1].x), gy = cy(p[p.length - 1].y);
    const hcost = (x, y) => Math.abs(x - gx) + Math.abs(y - gy);
    for (const [x, y, d] of starts) {
      if (x < 0 || y < 0 || x >= W || y >= H) continue;
      const st = (y * W + x) * 4 + d;
      dist[st] = 0; push(hcost(x, y), st);
    }
    let found = -1, steps = 0;
    while (heap.length && steps++ < 400000) {
      const [, st] = pop();
      const c = st >> 2, d = st & 3, x = c % W, y = (c - x) / W;
      if (goals.has(c) && goals.get(c) === d) { found = st; break; }
      for (let nd = 0; nd < 4; nd++) {
        if (nd === (d + 2) % 4) continue;
        const nx = x + DX[nd], ny = y + DY[nd], nc = ny * W + nx;
        if (!free(nc, nx, ny)) continue;
        if (!fixedEnd && owner[nc] !== -1 && owner[nc] === ti && !goals.has(nc)) continue;   // into its target only where it arrives
        if (owner[nc] !== -1 && owner[nc] === si && owner[c] !== si) continue; // never back into where it started
        const along = nd % 2 === 0 ? runH[nc] : runV[nc], across = nd % 2 === 0 ? runV[nc] : runH[nc];
        const cost = dist[st] + 1 + (nd !== d ? 6 : 0) + along * 30 + across * 3 + (owner[nc] === -1 && soft[nc] ? 10 : 0);
        const ns = nc * 4 + nd;
        if (cost < dist[ns]) { dist[ns] = cost; prev[ns] = st; push(cost + hcost(nx, ny), ns); }
      }
    }
    if (found < 0) { mark(p); continue; }                       // no way round: keep the layout's line
    const states = [];
    for (let st = found; st >= 0; st = prev[st]) states.push(st);
    states.reverse();
    const cells = states.map((st) => st >> 2);
    let route = cells.map((c) => ({ x: X0 + (c % W) * GRID, y: Y0 + Math.floor(c / W) * GRID }));
    const sb = box[e.source], tb = box[e.target];
    const a = route[0], z = route[route.length - 1];
    const firstDir = states[0] & 3;                            // the way out of the part it leaves
    // its ends on the parts themselves: the ports where it has them, else the side of the part it leaves and reaches
    const leave = (q, b, d) => (d === 0 ? { x: b.x + b.width, y: q.y } : d === 2 ? { x: b.x, y: q.y } : d === 1 ? { x: q.x, y: b.y + b.height } : { x: q.x, y: b.y });
    const reach = (q, b, d) => (d === 0 ? { x: b.x, y: q.y } : d === 2 ? { x: b.x + b.width, y: q.y } : d === 1 ? { x: q.x, y: b.y } : { x: q.x, y: b.y + b.height });
    const head = fixedStart ? [p[0], d0 % 2 === 0 ? { x: a.x, y: p[0].y } : { x: p[0].x, y: a.y }] : [leave(a, sb, firstDir)];
    const lastDir = found & 3;
    const tail = fixedEnd ? [dn % 2 === 0 ? { x: z.x, y: p[n - 1].y } : { x: p[n - 1].x, y: z.y }, p[n - 1]] : [reach(z, tb, lastDir)];
    route = [...head, ...route, ...tail];
    route = route.filter((q, i) => {                          // only the corners
      if (i === 0 || i === route.length - 1) return true;
      const a = route[i - 1], b = route[i + 1];
      return !((Math.abs(a.x - q.x) < 0.5 && Math.abs(q.x - b.x) < 0.5) || (Math.abs(a.y - q.y) < 0.5 && Math.abs(q.y - b.y) < 0.5));
    });
    le.sections = [{ startPoint: route[0], bendPoints: route.slice(1, -1), endPoint: route[route.length - 1] }];
    le.junctionPoints = [];
    mark(route, e.kind === "pipe");
  }
}

/* a nested layout made flat again: every part and edge in the diagram's own coordinates, and the
   open systems as outlines (lay.containers), outermost first */
function flatten(lay) {
  const abs = { root: { x: 0, y: 0 } }, leaves = [], containers = [];
  const walk = (node, ox, oy, depth) => {
    for (const c of node.children || []) {
      const x = ox + c.x, y = oy + c.y;
      abs[c.id] = { x, y };
      if (c.id.startsWith("hull:")) {
        containers.push({ id: c.id, name: c.id.slice(5), x, y, width: c.width, height: c.height, depth });
        walk(c, x, y, depth + 1);
      } else leaves.push({ ...c, x, y });
    }
  };
  walk(lay, 0, 0, 0);
  const edges = [];
  const collect = (node) => { for (const e of node.edges || []) edges.push(e); for (const c of node.children || []) collect(c); };
  collect(lay);
  for (const e of edges) {
    const o = abs[e.container] || abs.root;
    for (const sec of e.sections || []) for (const p of [sec.startPoint, sec.endPoint, ...(sec.bendPoints || [])]) { p.x += o.x; p.y += o.y; }
    for (const l of e.labels || []) { l.x += o.x; l.y += o.y; }
    for (const p of e.junctionPoints || []) { p.x += o.x; p.y += o.y; }
  }
  lay.children = leaves;
  lay.edges = edges;
  lay.containers = containers;
}

/* a wrapped layout's chains, one per row, in the model's order (upstream first), each left aligned */
function restack(lay, g) {
  const order = Object.fromEntries(g.nodes.map((n, i) => [n.id, i]));
  const parent = Object.fromEntries(lay.children.map((c) => [c.id, c.id]));
  const root = (x) => (parent[x] === x ? x : (parent[x] = root(parent[x])));
  const owner = (p) => (p in parent ? p : p.startsWith("system:") ? "system:" + p.split(":")[1] : p.replace(/:(in|out|ctl|sense)$/, ""));   // a port's node
  for (const e of lay.edges) {
    const a = owner(e.sources[0]), b = owner(e.targets[0]);
    if (a in parent && b in parent) parent[root(a)] = root(b);
  }
  const comps = {};
  for (const c of lay.children) (comps[root(c.id)] ||= []).push(c);
  const groups = Object.values(comps).map((cs) => {
    const x0 = Math.min(...cs.map((c) => c.x)), y0 = Math.min(...cs.map((c) => c.y - (c.labels?.length ? 0 : 0)));
    const y1 = Math.max(...cs.map((c) => c.y + c.height + Math.max(0, ...(c.labels || []).map((l) => l.y + l.height - c.height))));
    // a stock's place in the model orders the rows; clouds and the like come with their chain
    const first = Math.min(...cs.map((c) => (c.id.startsWith("stock:") ? order[c.id] : 1e9)), ...cs.map((c) => order[c.id] ?? 1e9));
    return { cs, x0, y0, h: y1 - y0, first, ids: new Set(cs.map((c) => c.id)) };
  }).sort((a, b) => a.first - b.first);
  let y = 40, width = 0;
  for (const gr of groups) {
    const dx = 40 - gr.x0, dy = y - gr.y0;
    for (const c of gr.cs) { c.x += dx; c.y += dy; width = Math.max(width, c.x + c.width); }
    for (const e of lay.edges) {
      if (!gr.ids.has(owner(e.sources[0]))) continue;
      for (const sec of e.sections || []) for (const p of [sec.startPoint, sec.endPoint, ...(sec.bendPoints || [])]) { p.x += dx; p.y += dy; }
      for (const l of e.labels || []) { l.x += dx; l.y += dy; }
    }
    y += gr.h + 70;                                   // room between rows for the pipe that joins them
  }
  lay.width = width + 40;
  lay.height = y - 30;
}

/* each coupling pipe drawn by hand: out of the valve, down into the gap above the next row, across,
   and into the stock from its left, so the rows read as one chain */
function routeCuts(lay, cuts) {
  const box = Object.fromEntries(lay.children.map((c) => [c.id, c]));
  for (const e of cuts) {
    const a = box[e.source], b = box[e.target];
    if (!a || !b) continue;
    const sx = a.x + a.width, sy = a.y + a.height / 2, tx = b.x, ty = b.y + b.height / 2;
    // the gap: just above the highest thing in the target's row, or below the source's when the target is above
    const row = lay.children.filter((c) => Math.abs(c.y + c.height / 2 - ty) < 160);
    const gapY = ty > sy ? Math.min(...row.map((c) => c.y)) - 26 : Math.max(...lay.children.filter((c) => Math.abs(c.y + c.height / 2 - sy) < 160).map((c) => c.y + c.height)) + 26;
    const turn = Math.max(sx + 18, ...(a.labels || []).map((l) => a.x + l.x + l.width + 12));   // clear of the valve's labels
    const pts = sy === ty ? [] : [{ x: turn, y: sy }, { x: turn, y: gapY }, { x: tx - 14, y: gapY }, { x: tx - 14, y: ty }];   // inside the outline
    lay.width = Math.max(lay.width, turn + 30);
    lay.edges.push({ id: e.id, sections: [{ startPoint: { x: sx, y: sy }, bendPoints: pts, endPoint: { x: tx, y: ty } }], cut: true });
  }
}

/* node shapes, drawn with their top-left at 0,0 */
function badge(a, x, y) {
  if (!a) return null;
  const t = badgeText(a), w = textWidth(t) + 24;
  return s("g", { class: "badge", transform: `translate(${x - w / 2},${y})` }, s("title", {}, `${a.kind} · ${a.name} · ${a.schedule || a.when || "runs by hand"}`),
    s("rect", { width: w, height: 16, rx: 8, fill: "var(--panel)", stroke: "var(--line)", "stroke-width": 1 }),
    rungDot(a.rung, 9, 8),
    s("text", { x: w / 2 + 5, y: 11.5, "text-anchor": "middle" }, t));
}

function drawStock(n, w, hgt) {
  const g = s("g");
  const pts = n.points || [];
  const sp = S.graph?.loops ? Object.values(S.graph.loops).find((l) => l.stock === n.label) : null;
  let top = Math.max(...pts.map((p) => p[1]), n.value ?? 0, 1);
  let spv = null;
  if (sp) { const m = /(-?\d+(\.\d+)?)/.exec(sp.setpoint); if (m) { spv = +m[1]; top = Math.max(top, spv * 1.25); } }
  const frac = n.value == null ? 0 : Math.max(0, Math.min(1, n.value / top));
  const T = 24, H = hgt - T - 2;                       // the tank: below the title
  const tone = sp ? ({ off: "var(--bad)", holding: "var(--ok)", open: "var(--warn)" }[sp.status] || "var(--accent)") : "var(--accent)";
  g.append(s("rect", { class: "hit", width: w, height: hgt, rx: 3, fill: "var(--stock)", stroke: "var(--stock-line)", "stroke-width": 2,
                       "stroke-dasharray": n.outside ? "5 4" : null }));
  g.append(s("line", { x1: 0, x2: w, y1: T, y2: T, stroke: "var(--line)", "stroke-width": 1 }));
  g.append(s("rect", { x: 2, y: T + H * (1 - frac), width: w - 4, height: H * frac, fill: tone, opacity: 0.14, class: "live" }));
  // a meter under the title: the level against the scale, and a tick where the setpoint is
  const mx = 10, mw = w - 20, my = T + 5;
  g.append(s("rect", { x: mx, y: my, width: mw, height: 4, rx: 2, fill: "var(--line)", class: "live" }));
  g.append(s("rect", { x: mx, y: my, width: mw * frac, height: 4, rx: 2, fill: tone, class: "live" }));
  if (spv != null) {
    const sx = mx + mw * Math.max(0, Math.min(1, spv / top));
    g.append(s("line", { x1: sx, x2: sx, y1: my - 3, y2: my + 7, stroke: "var(--ink)", "stroke-width": 1.6, class: "live" }, s("title", {}, "setpoint")));
    const sp_ = sp.setpoint.replace("<=", "≤").replace(">=", "≥").replace("==", "=").trim();
    g.append(s("text", { x: w - 10, y: 50, class: "t-sub sp-text", "text-anchor": "end" }, sp_));
  }
  if (pts.length > 1) {
    // the trend on one scale with its setpoint, drawn dashed: how far off it ran, not only its shape
    const vs = pts.map((p) => p[1]);
    const lo = Math.min(...vs, spv ?? Infinity), hi = Math.max(...vs, spv ?? -Infinity);
    const yOf = (v) => hgt - 8 - ((v - lo) / ((hi - lo) || 1)) * 16;
    if (spv != null) g.append(s("line", { x1: 10, x2: w - 10, y1: yOf(spv), y2: yOf(spv), stroke: "var(--ink)", "stroke-width": 0.8,
                                          "stroke-dasharray": "3 3", opacity: 0.55, class: "live" }, s("title", {}, "setpoint")));
    const d = vs.map((v, i) => `${i ? "L" : "M"}${10 + (i / (vs.length - 1)) * (w - 20)},${yOf(v)}`).join("");
    g.append(s("path", { d, fill: "none", stroke: tone, "stroke-width": 1.4, opacity: 0.8, class: "live" }));
  }
  g.append(s("text", { x: 10, y: 17, class: "t-label" }, n.label));
  g.append(s("text", { x: 10, y: 50, class: "t-value live" }, n.valueText, s("tspan", { class: "t-unit", dx: 4 }, n.unit || "")));
  return g;
}

function drawValve(n, w, hgt) {
  const g = s("g");
  const c = "var(--valve)";
  const m = n.mode || "auto";
  g.append(s("rect", { class: "hit", x: -2, y: -2, width: w + 4, height: hgt + 4, rx: 6, fill: "transparent", stroke: "transparent" }));
  g.append(s("path", { d: `M4,8 L${w / 2},${hgt / 2} L4,${hgt - 8} Z M${w - 4},8 L${w / 2},${hgt / 2} L${w - 4},${hgt - 8} Z`,
                       fill: m === "manual" ? "var(--panel)" : c, stroke: c, "stroke-width": 2, "stroke-linejoin": "round" }));
  if (m === "advise") g.append(s("path", { d: `M${w - 4},8 L${w / 2},${hgt / 2} L${w - 4},${hgt - 8} Z`, fill: "var(--panel)", stroke: c, "stroke-width": 2 }));
  g.append(s("line", { x1: w / 2, y1: hgt / 2, x2: w / 2, y2: 0, stroke: c, "stroke-width": 2 }));
  g.append(s("rect", { x: w / 2 - 7, y: -3, width: 14, height: 5, rx: 1.5, fill: c }));
  return g;
}

function drawDisturbance(n, w, hgt) {
  const g = s("g");
  g.append(s("path", { class: "hit", d: `M${w / 2},2 L${w - 2},${hgt / 2} L${w / 2},${hgt - 2} L2,${hgt / 2} Z`, fill: "var(--panel)", stroke: "var(--dist)", "stroke-width": 2 }));
  g.append(s("path", { d: `M${w * 0.25},${hgt / 2} q${w * 0.0625},-6 ${w * 0.125},0 t${w * 0.125},0 t${w * 0.125},0 t${w * 0.125},0`, fill: "none", stroke: "var(--dist)", "stroke-width": 2, "stroke-linecap": "round" }));
  return g;
}

function drawCloud(n, w, hgt) {
  const d = `M${w * 0.22},${hgt * 0.82} C${w * 0.02},${hgt * 0.82} ${w * 0.02},${hgt * 0.42} ${w * 0.22},${hgt * 0.45}
             C${w * 0.22},${hgt * 0.12} ${w * 0.55},${hgt * 0.08} ${w * 0.6},${hgt * 0.32}
             C${w * 0.7},${hgt * 0.12} ${w * 0.95},${hgt * 0.22} ${w * 0.86},${hgt * 0.5}
             C${w * 1.02},${hgt * 0.56} ${w * 0.98},${hgt * 0.84} ${w * 0.8},${hgt * 0.82} Z`;
  return s("g", {}, s("path", { class: "hit", d, fill: "var(--cloud)", stroke: "var(--muted)", "stroke-width": 1.4 }));
}

function drawSensor(n, w, hgt) {
  const r = w / 2;
  return s("g", {},
    s("circle", { class: "hit", cx: r, cy: r, r: r - 1, fill: "var(--sensor)", stroke: "var(--sensor-line)", "stroke-width": 2 }),
    s("path", { d: `M${r - 12},${r + 6} A13,13 0 0 1 ${r + 12},${r + 6}`, fill: "none", stroke: "var(--sensor-line)", "stroke-width": 2, "stroke-linecap": "round" }),
    s("line", { x1: r, y1: r + 6, x2: r + 7, y2: r - 4, stroke: "var(--sensor-line)", "stroke-width": 2.2, "stroke-linecap": "round" }),
    s("circle", { cx: r, cy: r + 6, r: 2.4, fill: "var(--sensor-line)" }));
}

function drawController(n, w, hgt) {
  const st = n.status || "unknown";
  const tone = { off: "var(--bad)", holding: "var(--ok)", open: "var(--warn)" }[st] || "var(--unknown)";
  const g = s("g");
  g.append(s("rect", { class: "hit", width: w, height: hgt, rx: 10, fill: "var(--ctl)", stroke: "var(--ctl-line)", "stroke-width": 2 }));
  // its summing point: the setpoint in (+), the reading in (−), the error out; a clock for an open loop, which reads nothing
  g.append(s("circle", { cx: 20, cy: 22, r: 9, fill: "var(--panel)", stroke: "var(--ctl-line)", "stroke-width": 1.6 },
             s("title", {}, n.openLoop ? "an open loop: it acts on its schedule and reads nothing" : "its summing point: e = r − y, the setpoint less the reading")));
  if (n.openLoop) g.append(s("path", { d: "M20,22 v-6 M20,22 l4,3", stroke: "var(--ctl-line)", "stroke-width": 1.4, "stroke-linecap": "round" }));
  else g.append(s("text", { x: 20, y: 26, "text-anchor": "middle", class: "sigma" }, "Σ"),
                s("text", { x: 8, y: 13, "text-anchor": "middle", class: "sign" }, "+"),
                s("text", { x: 8, y: 37, "text-anchor": "middle", class: "sign" }, "−"));
  g.append(s("text", { x: 36, y: 20, class: "t-label" }, n.label));
  g.append(s("text", { x: 36, y: 36, class: "t-sub" }, "holds " + n.setpoint));
  if (n.decision) {
    const when = n.decisionAt ? " · " + ago(n.decisionAt) : "";
    const room = Math.floor((w - 24) / 6.2) - when.length;
    const t = n.decision.length > room ? n.decision.slice(0, room - 1) + "…" : n.decision;
    g.append(s("text", { x: 12, y: 56, class: "t-sub live", "font-style": "italic" }, s("title", {}, "last decision: " + n.decision),
                         "“" + t + "”", s("tspan", { "font-style": "normal" }, when)));
  } else if (n.openLoop) {
    g.append(s("text", { x: 12, y: 56, class: "t-sub" }, OPEN_LOOP));
  }
  g.append(s("circle", { cx: w - 14, cy: 16, r: 5, fill: tone, class: "live" }));
  g.append(s("text", { x: w - 24, y: 20, class: "t-sub live", "text-anchor": "end", fill: tone }, st));
  const b = badge(n.agent, w / 2, hgt - 24);
  if (b) g.append(b);
  return g;
}

function drawAgent(n, w, hgt) {
  const g = s("g");
  g.append(s("rect", { class: "hit", width: w, height: hgt, rx: 10, fill: "var(--panel)", stroke: n.failing ? "var(--bad)" : "var(--line)", "stroke-width": 2 }));
  g.append(s("rect", { width: 6, height: hgt, rx: 3, fill: rungColor(n.rung) }));
  g.append(s("text", { x: 16, y: 20, class: "t-label" }, n.label));
  g.append(s("text", { x: w - 26, y: 20, class: "t-sub", "text-anchor": "end" }, `rung ${n.rung} · ${n.agentKind}`));
  g.append(rungDot(n.rung, w - 14, 16, 6.5));
  const when = n.schedule || "";
  g.append(s("text", { x: 16, y: 38, class: "t-sub" }, when, n.runs ? s("tspan", { class: "live" }, ` · ${n.runs} runs`) : null));
  [...(n.roles || []).map((r) => `${r.kind} ${r.name}`), ...(n.loads || []).map((d) => `the load: ${d}`)].slice(0, 3)
    .forEach((t, i) => g.append(s("text", { x: 16, y: 56 + i * 14, class: "t-sub" }, t)));
  return g;
}

/* each kind of line has one colour, whatever it is part of: what it is, not how it is doing */
const LINE_COLOR = { measure: "var(--sensor-line)", signal: "var(--sensor-line)", action: "var(--ctl-line)", influence: "var(--dist)", wire: "var(--accent)" };

/* a system drawn as one part: its name, how its loops are doing, and its ports (what crosses its edge) */
const SYS_TOP = 70, SYS_ROW = 20;
function systemSize(n) {
  const side = (d) => n.ports.filter((p) => (p.at || (p.side === "in" ? "west" : "east")) === (d === "in" ? "west" : "east"));
  const lw = (ps) => Math.max(0, ...ps.map((p) => textWidth(p.label + (p.value ? "  " + p.value : ""))));
  const w = Math.max(240, textWidth(n.label) * 1.25 + 150, lw(side("in")) + lw(side("out")) + 60);
  return [w, Math.max(96, SYS_TOP + Math.max(side("in").length, side("out").length) * SYS_ROW + 6 + (n.inner?.length ? 16 : 0))];
}
function loopsText(n) {
  const l = n.loops || {}, total = Object.values(l).reduce((a, b) => a + b, 0);
  if (!total) return "no loops";
  return `${total} loop${total > 1 ? "s" : ""}: ` + ["holding", "off", "open", "unknown"].filter((k) => l[k]).map((k) => `${l[k]} ${k}`).join(", ");
}
function drawSystem(n, w, hgt) {
  const tone = { off: "var(--bad)", holding: "var(--ok)", open: "var(--warn)" }[n.status] || "var(--unknown)";
  const g = s("g");
  g.append(s("rect", { class: "hit", width: w, height: hgt, rx: 12, fill: "var(--panel)", stroke: "var(--system-line)", "stroke-width": 2 }));
  g.append(s("rect", { x: 4, y: 4, width: w - 8, height: hgt - 8, rx: 9, fill: "var(--system)", stroke: "var(--system-line)", "stroke-width": 1, "stroke-dasharray": "3 3" }));
  g.append(s("text", { x: 16, y: 24, class: "t-label sys-title" }, n.label));
  g.append(s("circle", { cx: 16 + textWidth(n.label) * 1.25 + 12, cy: 19, r: 5, fill: tone, class: "live" }, s("title", {}, loopsText(n))));
  g.append(s("text", { x: 16, y: 42, class: "t-sub live" }, loopsText(n) + (n.subsystems?.length ? ` · ${n.subsystems.length} inside` : "")));
  const btn = (x, label, title, fn) => s("g", { class: "sys-btn", transform: `translate(${x},10)`, onclick: (ev) => { ev.stopPropagation(); fn(); } },
    s("title", {}, title), s("rect", { width: textWidth(label) + 14, height: 20, rx: 5 }), s("text", { x: 7, y: 14 }, label));
  const into = "⤓ into", open = "▸ open";
  g.append(btn(w - textWidth(into) - 24, into, "draw this system alone, with what it reaches outside at its edge", () => S.drill?.(n.label)));
  g.append(btn(w - textWidth(into) - textWidth(open) - 46, open, "open it here: its parts in place of the box", () => S.toggleSystem?.(n.label)));
  if (n.inner?.length) g.append(s("text", { x: 16, y: hgt - 10, class: "t-sub" }, s("title", {}, "given a setpoint from outside, it holds it, and what it holds is read back out: an outer loop can treat it as one block"),
                                  `inner loop: holds ${n.inner.join(", ")} for an outer one`));
  const at = { west: 0, east: 0 };
  for (const p of n.ports || []) {
    const side = p.at || (p.side === "in" ? "west" : "east");
    const y = SYS_TOP + (at[side]++) * SYS_ROW;
    const left = side === "west";
    g.append(s("rect", { x: left ? -4 : w - 4, y: y - 4, width: 8, height: 8, rx: 2, fill: "var(--panel)", stroke: "var(--system-line)", "stroke-width": 1.5 }));
    const px = left ? 0 : w, inward = (p.side === "in") === left;    // which way it carries, across the edge
    g.append(s("path", { d: inward ? `M${px - 2.5},${y - 2.5} L${px + 2},${y} L${px - 2.5},${y + 2.5} Z` : `M${px + 2.5},${y - 2.5} L${px - 2},${y} L${px + 2.5},${y + 2.5} Z`,
                         fill: "var(--system-line)" }));
    g.append(s("text", { x: left ? 12 : w - 12, y: y + 4, class: "t-sub", "text-anchor": left ? "start" : "end" }, s("title", {}, `${p.side === "in" ? "in" : "out"}: ${p.kind} ${p.label}`),
      p.label, p.value ? s("tspan", { class: "live", dx: 6, opacity: 0.75 }, p.value) : null));
  }
  return g;
}
function drawTerminal(n, w, hgt) {
  const g = s("g");
  g.append(s("rect", { class: "hit", width: w, height: hgt, rx: hgt / 2, fill: "var(--bg)", stroke: "var(--system-line)", "stroke-width": 1.5, "stroke-dasharray": "4 3" }));
  g.append(s("text", { x: 14, y: n.in ? 14 : hgt / 2 + 4, class: "t-sub" }, n.label, n.valueText ? s("tspan", { class: "live", dx: 6, opacity: 0.75 }, n.valueText) : null));
  if (n.in) g.append(s("text", { x: 14, y: 27, class: "t-sub", opacity: 0.7 }, `in ${n.in}`));
  return g;
}

const DRAW = { system: drawSystem, terminal: drawTerminal, stock: drawStock, valve: drawValve, disturbance: drawDisturbance, cloud: drawCloud, sensor: drawSensor, controller: drawController, agent: drawAgent };

function roundedPath(pts, r = 8) {
  if (pts.length < 2) return "";
  let d = `M${pts[0].x},${pts[0].y}`;
  for (let i = 1; i < pts.length - 1; i++) {
    const p0 = pts[i - 1], p1 = pts[i], p2 = pts[i + 1];
    const d1 = Math.hypot(p1.x - p0.x, p1.y - p0.y), d2 = Math.hypot(p2.x - p1.x, p2.y - p1.y);
    const rr = Math.min(r, d1 / 2, d2 / 2);
    const a = { x: p1.x - ((p1.x - p0.x) / d1) * rr, y: p1.y - ((p1.y - p0.y) / d1) * rr };
    const b = { x: p1.x + ((p2.x - p1.x) / d2) * rr, y: p1.y + ((p2.y - p1.y) / d2) * rr };
    d += ` L${a.x},${a.y} Q${p1.x},${p1.y} ${b.x},${b.y}`;
  }
  const last = pts[pts.length - 1];
  return d + ` L${last.x},${last.y}`;
}

function edgePoints(e) {
  const sec = (e.sections || [])[0];
  if (!sec) return [];
  return [sec.startPoint, ...(sec.bendPoints || []), sec.endPoint];
}

function arrowHead(pts, cls, size = 7) {
  const a = pts[pts.length - 2], b = pts[pts.length - 1];
  const ang = Math.atan2(b.y - a.y, b.x - a.x);
  const p = (t) => `${b.x - size * Math.cos(ang + t)},${b.y - size * Math.sin(ang + t)}`;
  return s("path", { d: `M${p(-0.45)} L${b.x},${b.y} L${p(0.45)} Z`, class: cls });
}

function drawGraph(svg, g, lay) {
  portSides(g);
  const byId = Object.fromEntries(g.nodes.map((n) => [n.id, n]));
  const edgeById = Object.fromEntries(g.edges.map((e) => [e.id, e]));
  S.edgeById = edgeById;
  const vp = s("g", { id: "viewport" });
  // systems as hulls behind everything (overlapping freely)
  if (g.kind === "control" && lay.containers?.length) {      // open systems: laid out as containers, drawn as outlines
    const hulls = s("g", { class: "sys-hull" });
    const names = Object.keys(g.tree || {}).sort();
    for (const c of lay.containers) {
      const hue = (210 + names.indexOf(c.name) * 137.5) % 360;
      hulls.append(s("rect", { x: c.x, y: c.y, width: c.width, height: c.height, rx: 16, style: `fill:hsla(${hue},70%,50%,.05);stroke:hsla(${hue},60%,45%,.45)` }),
        s("text", { x: c.x + 14, y: c.y + 22, class: "sys-hull-label", "data-act": "close", style: `fill:hsl(${hue},55%,42%)`, onclick: (ev) => { ev.stopPropagation(); S.toggleSystem?.(c.name); } },
          s("title", {}, `${c.name}: click to close it into one box`), "▾ " + c.name),
        s("text", { x: c.x + 14 + textWidth("▾ " + c.name) * 1.15 + 10, y: c.y + 22, class: "sys-hull-label", "data-act": "into", style: `fill:hsl(${hue},55%,42%)`,
                    onclick: (ev) => { ev.stopPropagation(); S.drill?.(c.name); } }, s("title", {}, "draw it alone"), "⤓"));
    }
    vp.append(hulls);
  } else if (g.kind === "control" && S.showHulls && !g.tree) {
    const hulls = s("g", { class: "sys-hull" });
    const taken = [];                                   // label boxes already placed, so overlapping hulls never stack names
    // a system that contains another is padded more, so nested outlines nest visibly, labels apart
    const memberIds = {};
    for (const name of S.status?.systems || []) memberIds[name] = new Set(lay.children.filter((c) => (byId[c.id]?.systems || []).includes(name)).map((c) => c.id));
    const inside = (o, name) => o !== name && memberIds[o].size && memberIds[o].size < memberIds[name].size &&
                                [...memberIds[o]].every((x) => memberIds[name].has(x));
    const depths = {};          // the longest chain of systems inside this one, not how many there are
    const depth = (name) => (depths[name] ??= Math.max(0, ...Object.keys(memberIds).filter((o) => inside(o, name)).map((o) => 1 + depth(o))));
    const ext = { x0: 0, y0: 0, x1: 0, y1: 0 };
    (S.status?.systems || []).forEach((name, si) => {
      const pad = 22 + 16 * depth(name);
      const hue = (210 + si * 137.5) % 360;          // the golden angle: neighbours never share a colour
      const members = lay.children.filter((c) => (byId[c.id]?.systems || []).includes(name));
      if (!members.length) return;
      const boxOf = (c) => {
        const ls = c.labels || [];      // a node's box, with its labels outside it
        const xs = [c.x, c.x + c.width, ...ls.flatMap((l) => [c.x + l.x, c.x + l.x + l.width])];
        const ys = [c.y, c.y + c.height, ...ls.flatMap((l) => [c.y + l.y, c.y + l.y + l.height])];
        return { x: Math.min(...xs), y: Math.min(...ys), x1: Math.max(...xs), y1: Math.max(...ys) };
      };
      // one outline per connected group of the system's parts, so an outline never encloses parts
      // outside the system just because they lie between two of its parts
      const ids = new Set(members.map((c) => c.id));
      const parent = Object.fromEntries(members.map((c) => [c.id, c.id]));
      const root = (x) => (parent[x] === x ? x : (parent[x] = root(parent[x])));
      for (const e of g.edges) if (ids.has(e.source) && ids.has(e.target)) parent[root(e.source)] = root(e.target);
      const groups = {};
      for (const c of members) (groups[root(c.id)] ||= []).push(boxOf(c));
      // one outline around all of it when that encloses nothing outside the system; else one per group
      const all = Object.values(groups).flat();
      const R = { x: Math.min(...all.map((b) => b.x)), y: Math.min(...all.map((b) => b.y)),
                  x1: Math.max(...all.map((b) => b.x1)), y1: Math.max(...all.map((b) => b.y1)) };
      const intrudes = lay.children.some((c) => !ids.has(c.id) && byId[c.id]?.kind !== "cloud" &&   // against the outline as drawn
        c.x < R.x1 + pad && c.x + c.width > R.x - pad && c.y < R.y1 + pad && c.y + c.height > R.y - pad - 12);
      const sets = intrudes ? Object.values(groups) : [all];
      sets.sort((a, b) => b.length - a.length).forEach((bs) => {
        const x0 = Math.min(...bs.map((b) => b.x)) - pad, y0 = Math.min(...bs.map((b) => b.y)) - pad - 12;
        const x1 = Math.max(...bs.map((b) => b.x1)) + pad, y1 = Math.max(...bs.map((b) => b.y1)) + pad;
        const lw = name.length * 8 + 10;
        let lx = x0 + 12;
        for (let i = 0; i < 20 && taken.some((t) => Math.abs(t.y - y0) < 14 && lx < t.x + t.w && lx + lw > t.x); i++) {
          const t = taken.find((t) => Math.abs(t.y - y0) < 14 && lx < t.x + t.w && lx + lw > t.x);
          lx = t.x + t.w + 12;
        }
        taken.push({ x: lx, y: y0, w: lw });
        ext.x0 = Math.min(ext.x0, x0); ext.y0 = Math.min(ext.y0, y0); ext.x1 = Math.max(ext.x1, x1); ext.y1 = Math.max(ext.y1, y1);
        hulls.append(s("rect", { x: x0, y: y0, width: x1 - x0, height: y1 - y0, rx: 16,
                                 style: `fill:hsla(${hue},70%,50%,.05);stroke:hsla(${hue},60%,45%,.45)` }),
                     s("text", { x: lx, y: y0 + 18, class: "sys-hull-label", style: `fill:hsl(${hue},55%,42%)`,
                                 onclick: (ev) => { ev.stopPropagation(); S.toggleSystem?.(name); } },
                       s("title", {}, `${name}: click to close it into one box`), name + (S.graph?.tree ? " ▾" : "")));
      });
    });
    vp.append(hulls);
    // the outlines reach past the laid-out nodes: count them in the size that fit and export use
    lay.base ||= { width: lay.width, height: lay.height };
    lay.ox = Math.min(0, ext.x0); lay.oy = Math.min(0, ext.y0);
    lay.width = Math.max(lay.base.width, ext.x1) - lay.ox; lay.height = Math.max(lay.base.height, ext.y1) - lay.oy;
  }
  const edgesG = s("g");
  for (const le of lay.edges) {
    const e = edgeById[le.id];
    const pts = edgePoints(le);
    if (pts.length < 2) continue;
    const d = roundedPath(pts, e.kind === "pipe" ? 10 : 7);
    const flowN = byId[e.kind === "pipe" ? (byId[e.source]?.kind === "valve" || byId[e.source]?.kind === "disturbance" ? e.source : e.target) : ""];
    const dist = flowN && flowN.kind === "disturbance";
    const loopSt = (e.loops || []).map((k) => g.loops[k]?.status).find(Boolean);
    const cls = ["edge", e.kind, dist ? "dist" : "", loopSt ? "loop-" + loopSt : ""].join(" ");
    const eg = s("g", { class: cls, "data-id": e.id, "data-loops": (e.loops || []).join(" "), "data-nodes": `${e.source} ${e.target}`,
                        "data-link": linkKey(e),
                        onpointerenter: () => { if (!S.dragging) hoverEdge(e); }, onpointerleave: () => hoverEdge(null) });
    if (e.kind === "pipe") {
      eg.append(s("path", { d, class: "pipe-out" }), s("path", { d, class: "pipe-in" }));
      if (flowN && flowN.rate > 0) eg.append(s("path", { d, class: "flowing", stroke: dist ? "var(--dist)" : "var(--accent)" }));
      if (e.arrow) { const ah = arrowHead(pts, "head", 12); ah.style.fill = dist ? "var(--dist)" : "var(--pipe)"; eg.append(ah); }
    } else {
      eg.append(s("path", { d, class: "info" }));
      const ah = arrowHead(pts, "head", e.kind === "wire" ? 9 : 7);
      ah.style.fill = LINE_COLOR[e.kind] || "var(--info)";
      eg.append(ah);
      if ((le.labels || []).length) {
        // on the edge itself: the middle of its longest segment, with a halo to read over the line
        let best = [pts[0], pts[1]], len = -1;
        for (let i = 1; i < pts.length; i++) {
          const d2 = Math.hypot(pts[i].x - pts[i - 1].x, pts[i].y - pts[i - 1].y);
          if (d2 > len) { len = d2; best = [pts[i - 1], pts[i]]; }
        }
        const mx = (best[0].x + best[1].x) / 2, my = (best[0].y + best[1].y) / 2;
        const vertical = Math.abs(best[0].x - best[1].x) < 1;
        // an edge with a twin running the other way between the same agents puts its label on the other side
        // (the side by where the two lines actually run: the left one's label left, the lower one's below)
        const tw = lay.edges.find((o) => edgeById[o.id]?.source === e.target && edgeById[o.id]?.target === e.source);
        let left = false;
        if (tw) {
          const tp = edgePoints(tw), tx = tp.reduce((a, p) => a + p.x, 0) / tp.length, ty = tp.reduce((a, p) => a + p.y, 0) / tp.length;
          const ex = pts.reduce((a, p) => a + p.x, 0) / pts.length, ey = pts.reduce((a, p) => a + p.y, 0) / pts.length;
          left = vertical ? ex < tx || (ex === tx && e.source > e.target) : ey > ty || (ey === ty && e.source > e.target);
        }
        eg.append(s("text", { class: "elabel", x: vertical ? (left ? mx - 6 : mx + 6) : mx, y: vertical ? my + 4 : (left ? my + 14 : my - 6),
                              "text-anchor": vertical ? (left ? "end" : "start") : "middle", "paint-order": "stroke",
                              stroke: "var(--bg)", "stroke-width": 4, "stroke-linejoin": "round" }, le.labels[0].text));
      }
    }
    const onLine = (j) => pts.slice(1).some((p, i) => { const a = pts[i];     // a split point must be on the line itself
      return Math.min(a.x, p.x) - 1 <= j.x && j.x <= Math.max(a.x, p.x) + 1 && Math.min(a.y, p.y) - 1 <= j.y && j.y <= Math.max(a.y, p.y) + 1; });
    for (const j of (le.junctionPoints || []).filter(onLine)) eg.append(s("circle", { cx: j.x, cy: j.y, r: 3.2, class: "junction", fill: LINE_COLOR[e.kind] || "var(--pipe)" }));
    eg.append(s("path", { d, class: "edge-hit" }));    // a wide, invisible line: easy to point at
    edgesG.append(eg);
  }
  const nodesG = s("g");
  for (const ln of lay.children) {
    const n = byId[ln.id];
    const ng = s("g", { class: `node k-${n.kind}`, transform: `translate(${ln.x},${ln.y})`, "data-id": n.id,
                        // pressed and let go over the same part, even if it was drawn again in between, is a click
                        onpointerdown: (ev) => { if (!ev.target.closest(".sys-btn")) S.downOn = n.id; },
                        ondblclick: (ev) => { if (n.kind === "system") { ev.stopPropagation(); S.toggleSystem?.(n.label); } } });
    ng.append((DRAW[n.kind] || drawCloud)(n, ln.width, ln.height));
    for (const lb of ln.labels || []) {
      // the text from this tick's data, not the layout's: positions are kept, readings move on
      const fresh = labelLines(n);
      const lines = fresh.length ? fresh : lb.text.split("\n");
      lines.forEach((t, i) => {
        const cx = lb.x + lb.width / 2, y = lb.y + 13 + i * 16;
        if (t === "§badge") { const b = badge(n.agent, cx, y - 11); if (b) ng.append(b); return; }
        if (i === 0) { ng.append(s("text", { x: cx, y, "text-anchor": "middle", class: "t-label" }, t)); return; }
        // a reading or a measured rate changes minute to minute (live); a valve's mode and a declared
        // rate are the design, and stay in the design picture
        const keep = (part) => ["manual", "advise"].includes(part) || part.startsWith("≤ ") || (n.kind === "disturbance" && n.how === "declared");
        const bits = t.split(" · ");
        // a separator goes with the part before it, so a hidden part takes its dot along
        ng.append(s("text", { x: cx, y, "text-anchor": "middle", class: "t-sub" },
          bits.map((b, k) => s("tspan", { class: keep(b) ? null : "live" }, b + (k < bits.length - 1 ? " · " : "")))));
      });
    }
    nodesG.append(ng);
  }
  vp.append(edgesG, nodesG);
  svg.replaceChildren(vp);
  applyView(svg);
  if (S.hl) highlightLoop(S.hl);
  if (S.hoverKey || S.selKey) trace(S.hoverKey || S.selKey);   // a redraw keeps the line being followed
}

/* a standalone copy of the diagram: every computed style written inline, framed to the layout */

function applyView(svg) {
  const vp = svg.querySelector("#viewport");
  if (vp) vp.setAttribute("transform", `translate(${S.view.x},${S.view.y}) scale(${S.view.k})`);
  // whether some of the diagram lies beyond the edge, after a drag or a zoom too
  const hint = document.getElementById("panhint"), lay = S.layout, r = svg.getBoundingClientRect();
  if (hint && lay && r.width) {
    const k = S.view.k, x0 = S.view.x + (lay.ox || 0) * k, y0 = S.view.y + (lay.oy || 0) * k;
    hint.hidden = x0 >= -2 && y0 >= -2 && x0 + lay.width * k <= r.width + 2 && y0 + lay.height * k <= r.height + 2;
  }
}

function fit(svg, lay, legible = false) {
  const r = svg.getBoundingClientRect();
  if (!lay || !r.width) return;
  // the "fit" button shows everything; the first view keeps labels legible, and a bigger system is panned
  const whole = Math.min(1.25, (r.width - 40) / lay.width, (r.height - 90) / lay.height);
  // the first view keeps 11px text at 9px or more on screen; a wider system is panned from its left
  const k = legible ? (whole >= 0.7 ? whole : 0.8) : Math.max(0.08, whole);   // nearly whole at 0.7: show it whole
  const fitsW = lay.width * k <= r.width - 20, fitsH = lay.height * k <= r.height - 120;   // the toolbars: 56 above, 50 below
  const ox = (lay.ox || 0) * k, oy = (lay.oy || 0) * k;
  S.view = { k, x: (fitsW ? (r.width - lay.width * k) / 2 : 20) - ox, y: (fitsH ? Math.max(56, (r.height - lay.height * k) / 2 + 20) : 60) - oy };
  applyView(svg);
}

function panZoom(svg) {
  let drag = null;
  svg.addEventListener("wheel", (ev) => {
    ev.preventDefault();
    const r = svg.getBoundingClientRect();
    const mx = ev.clientX - r.left, my = ev.clientY - r.top;
    const f = Math.exp(-ev.deltaY * (ev.ctrlKey ? 0.01 : 0.0015));
    const k = Math.max(0.15, Math.min(4, S.view.k * f));
    S.view.x = mx - ((mx - S.view.x) * k) / S.view.k;
    S.view.y = my - ((my - S.view.y) * k) / S.view.k;
    S.view.k = k;
    applyView(svg);
  }, { passive: false });
  svg.addEventListener("pointerdown", () => { S.pressed = true; }, true);      // held: no redraw until it is let go
  window.addEventListener("pointerup", () => { S.pressed = false; }, true);
  svg.addEventListener("pointerup", (ev) => {
    const was = S.downOn;
    S.downOn = null;
    const under = document.elementFromPoint(ev.clientX, ev.clientY)?.closest(".node");
    if (!was || !under || under.dataset.id !== was || ev.target.closest?.(".sys-btn")) return;
    const n = S.graph?.nodes.find((x) => x.id === was);
    if (!n || n.kind === "cloud") return;
    if (n.kind === "terminal") S.drill?.(n.in || ""); else openNode(n);
  });
  window.addEventListener("pointercancel", () => { S.pressed = false; }, true);
  svg.addEventListener("pointerdown", (ev) => {
    if (ev.target.closest(".node") || ev.target.closest("[data-act]")) return;   // a part, or a control drawn on the canvas
    ev.preventDefault();                                   // a drag pans; it never starts selecting text
    drag = { x: ev.clientX, y: ev.clientY, vx: S.view.x, vy: S.view.y };
    S.dragged = false;
    svg.classList.add("dragging");
    svg.setPointerCapture(ev.pointerId);
  });
  svg.addEventListener("pointermove", (ev) => {
    if (!drag) return;
    if (Math.hypot(ev.clientX - drag.x, ev.clientY - drag.y) > 4) { S.dragged = true; S.dragging = true; hoverEdge(null); }
    S.view.x = drag.vx + ev.clientX - drag.x;
    S.view.y = drag.vy + ev.clientY - drag.y;
    applyView(svg);
  });
  const end = () => { drag = null; S.dragging = false; svg.classList.remove("dragging"); };
  svg.addEventListener("pointerup", end);
  svg.addEventListener("pointercancel", end);
  svg.addEventListener("click", (ev) => {
    if (ev.target.closest(".node") || ev.target.closest("[data-act]") || S.dragged) return;   // a drag pans; it is not a click
    const under = document.elementFromPoint(ev.clientX, ev.clientY)?.closest(".edge");   // the pan holds the pointer: ask what is there
    const e = under && S.edgeById?.[under.dataset.id];
    if (e) openEdge(e); else closeDetail();
  });
}

/* one line, traced: the line pointed at and every other piece of the same connection (both pipes
   of a flow, a wire cut by a system's edge) are lit, with the parts at their ends; the other lines
   at those parts stay half lit, so where each one goes can be followed; the rest fades */
function original(id, port) {                          // the part a folded line really ends at
  if (port) return port.replace(/^system:[^:]+:(in|out):/, "");
  return id.startsWith("term:") ? id.slice(5) : id;
}
function linkKey(e) {
  if (e.kind === "pipe" && e.flow) return "flow:" + e.flow;
  return `${e.kind}:${original(e.source, e.sourcePort)}>${original(e.target, e.targetPort)}`;
}
function hoverEdge(e) {                               // pointing at a line traces it; leaving it, the chosen one (if any) stays
  S.hoverKey = e ? linkKey(e) : null;
  trace(S.hoverKey || S.selKey);
}
function trace(key) {
  const svg = $("svg.canvas");
  if (!svg) return;
  if (!key) { svg.classList.remove("tracing"); for (const x of svg.querySelectorAll(".lit,.near")) x.classList.remove("lit", "near"); return; }
  const lit = [...svg.querySelectorAll(".edge")].filter((x) => x.dataset.link === key);
  const ends = new Set(lit.flatMap((x) => (x.dataset.nodes || "").split(" ")));
  svg.classList.add("tracing");
  for (const x of svg.querySelectorAll(".edge")) {
    const [a, b] = (x.dataset.nodes || "").split(" ");
    x.classList.toggle("lit", x.dataset.link === key);
    x.classList.toggle("near", x.dataset.link !== key && (ends.has(a) || ends.has(b)));
  }
  for (const n of svg.querySelectorAll(".node")) n.classList.toggle("lit", ends.has(n.dataset.id));
}

function highlightLoop(name) {
  S.hl = name;
  const svg = $("svg.canvas");
  if (!svg) return;
  svg.classList.toggle("loop-hl", !!name);            // its lines take its health's colour while it is pointed at
  const lp = name && S.graph?.loops?.[name];
  const members = new Set(lp ? lp.nodes : []);
  for (const n of svg.querySelectorAll(".node")) n.classList.toggle("dim", !!lp && !members.has(n.dataset.id));
  for (const e of svg.querySelectorAll(".edge")) {
    const [a, b] = (e.dataset.nodes || "").split(" ");
    e.classList.toggle("dim", !!lp && !(members.has(a) && members.has(b)));
  }
  for (const r of document.querySelectorAll(".looprow")) r.classList.toggle("hl", r.dataset.loop === name);
}

function highlightAgents(names) {
  const svg = $("svg.canvas");
  if (!svg) return;
  const ids = new Set((names || []).map((n) => "agent:" + n));
  for (const n of svg.querySelectorAll(".node")) n.classList.toggle("dim", !!names && !ids.has(n.dataset.id));
  for (const e of svg.querySelectorAll(".edge")) {
    const [a, b] = (e.dataset.nodes || "").split(" ");
    e.classList.toggle("dim", !!names && !(ids.has(a) && ids.has(b)));
  }
}

function legend(view) {
  if (view === "blocks") {
    const row = (sym, text) => [h("span", { class: "sym" }, sym), h("span", {}, text)];
    return h("div", { class: "legend" },
      row("r", "the setpoint: what the loop holds"),
      row("Σ", "compares: r − ym, with signs at each input"),
      row("e", "the error: how far off it is"),
      row("C", "the controller, and the agent filling it"),
      row("u", "its output: how far the actuator (valve) is opened"),
      row("d", "a disturbance joining at the plant"),
      row("y", "the plant's output: the stock"),
      row("H", "the sensor; ym is what it reads"),
      row("ff", "feedforward: the controller also measures d"));
  }
  if (view === "wiring") {
    return h("div", { class: "legend" },
      h("span", { html: '<svg width="26" height="16"><rect x="2" y="2" width="22" height="12" rx="3" fill="var(--panel)" stroke="var(--line)" stroke-width="2"/><rect x="2" y="2" width="4" height="12" rx="2" fill="var(--r4)"/></svg>' }), "an agent, coloured by its rung",
      h("span", { html: '<svg width="26" height="16"><path d="M2 8 H20" stroke="var(--accent)" stroke-width="2"/><path d="M18 4 L24 8 L18 12 Z" fill="var(--accent)"/></svg>' }), "its output reaches another agent");
  }
  const row = (svgTxt, text) => [h("span", { html: `<svg width="26" height="18">${svgTxt}</svg>` }), h("span", {}, text)];
  return h("div", { class: "legend" },
    row('<rect x="2" y="2" width="22" height="14" rx="2" fill="var(--stock)" stroke="var(--stock-line)" stroke-width="2"/>', "stock: what accumulates"),
    row('<rect x="2" y="7" width="22" height="4" rx="2" fill="var(--line)"/><rect x="2" y="7" width="12" height="4" rx="2" fill="var(--ok)"/><line x1="18" x2="18" y1="4" y2="14" stroke="var(--ink)" stroke-width="1.6"/>', "its level, and the setpoint's tick"),
    row('<path d="M1 9 H25" stroke="var(--pipe)" stroke-width="7"/><path d="M1 9 H25" stroke="var(--pipe-in)" stroke-width="3"/>', "flow: moves a stock"),
    row('<path d="M5 3 L13 9 L5 15 Z M21 3 L13 9 L21 15 Z" fill="var(--valve)"/>', "valve: where an agent acts"),
    row('<path d="M13 2 L22 9 L13 16 L4 9 Z" fill="var(--panel)" stroke="var(--dist)" stroke-width="1.8"/>', "disturbance: nothing controls it"),
    row('<circle cx="13" cy="9" r="7" fill="var(--sensor)" stroke="var(--sensor-line)" stroke-width="1.8"/>', "sensor: measures"),
    row('<rect x="2" y="2" width="22" height="14" rx="4" fill="var(--ctl)" stroke="var(--ctl-line)" stroke-width="1.8"/>', "controller: decides, to hold a setpoint; Σ is where it compares: e = r − y"),
    Object.values(S.graph?.loops || {}).some((l) => l.openLoop) &&
      row('<circle cx="13" cy="9" r="7" fill="var(--panel)" stroke="var(--ctl-line)" stroke-width="1.6"/><path d="M13,9 v-5 M13,9 l3,2" stroke="var(--ctl-line)" stroke-width="1.4" stroke-linecap="round"/>', "with a clock: an open loop (acts on time, reads nothing)"),
    (S.graph?.nodes || []).some((n) => n.kind === "system") &&
      row('<rect x="2" y="2" width="22" height="14" rx="4" fill="var(--panel)" stroke="var(--system-line)" stroke-width="1.8"/><rect x="0" y="6" width="4" height="4" fill="var(--panel)" stroke="var(--system-line)"/>', "a system as one part: its ports are what crosses its edge (▸ opens it, ⤓ draws it alone)"),
    (S.graph?.nodes || []).some((n) => n.kind === "terminal") &&
      row('<rect x="2" y="3" width="22" height="12" rx="6" fill="var(--bg)" stroke="var(--system-line)" stroke-dasharray="3 2"/>', "outside this system: what its edge reaches (click to go there)"),
    row('<path d="M1 9 H20" stroke="var(--sensor-line)" stroke-width="1.6" stroke-dasharray="4 3"/><path d="M18 5 L25 9 L18 13 Z" fill="var(--sensor-line)"/>', "measurement: a sensor reads"),
    row('<path d="M1 9 H20" stroke="var(--sensor-line)" stroke-width="1.6"/><path d="M18 5 L25 9 L18 13 Z" fill="var(--sensor-line)"/>', "feedback: the reading goes to the controller"),
    row('<path d="M1 9 H20" stroke="var(--ctl-line)" stroke-width="1.8"/><path d="M18 5 L25 9 L18 13 Z" fill="var(--ctl-line)"/>', "control action: the controller opens a valve"),
    (S.graph?.edges || []).some((e) => e.kind === "influence") &&
      row('<path d="M1 9 H20" stroke="var(--dist)" stroke-width="1.6" stroke-dasharray="7 4"/><path d="M18 5 L25 9 L18 13 Z" fill="var(--dist)"/>', "influence: a flow's rate follows this (driven-by)"),
    row('<circle cx="13" cy="9" r="5" fill="var(--ok)"/>', "a loop's health, on its controller and stock: green holding, red off, amber open. Point at a loop in the list and its lines take that colour"),
    row('<circle cx="13" cy="9" r="4.5" fill="var(--r4)"/>', "the agent filling a part, its dot by kind:"),
    h("span", {}), h("span", { class: "kinds" }, RUNG_NAMES.map((k, i) => h("span", {}, h("i", { style: `background:${rungColor(i)}` }, RUNG_LETTER[i]), k))));
}

async function pageDiagram(main, q) {
  const view = q.get("view") || "control";
  const system = q.get("system") || "";
  const around = q.get("around") || "";
  const openQ = q.has("open") ? q.get("open") : null;          // the systems opened; absent: the server's default
  S.showHulls = !around;
  const wrap = h("div", { class: "canvas-wrap" });
  const svg = s("svg", { class: "canvas" });
  const sysSel = h("select", { onchange: (ev) => go({ system: ev.target.value, around: "" }) }, h("option", { value: "" }, "everything"));
  for (const name of S.status?.systems || []) sysSel.append(h("option", { value: name, selected: name === system ? "" : null }, name));
  function go(over) {
    const p = new URLSearchParams({ view, system, around, ...(openQ != null ? { open: openQ } : {}), ...over });
    for (const [k, v] of [...p]) if (!v) p.delete(k);
    location.hash = "#/diagram?" + p.toString();
  }
  S.toggleSystem = (name) => {                     // open a box in place, or close an outline back into one
    const now = new Set(S.graph?.open || []);
    if (now.has(name)) { now.delete(name); for (const [k, v] of Object.entries(S.graph?.tree || {})) if (v.within === name) now.delete(k); }
    else now.add(name);
    S.graphSig = "";
    go({ open: [...now].join(",") || "-" });
  };
  S.drill = (name) => { S.graphSig = ""; S.fitted = false; go({ system: name, open: "" }); };
  const crumbs = h("span", { class: "crumbs" });
  const wrapBtn = h("button", { class: S.wrap ? "on" : "", title: "fold a chain of loops into rows, at the pipes between loops",
                               onclick: () => { S.wrap = !wrapBtn.classList.contains("on"); S.graphSig = ""; S.fitted = false; route(); } }, "wrap");
  const toolbar = h("div", { class: "toolbar" },
    h("span", { class: "muted" }, "system"), sysSel,
    h("span", { class: "seg" },
      h("button", { class: view === "control" ? "on" : "", onclick: () => go({ view: "control" }) }, "control"),
      h("button", { class: view === "blocks" ? "on" : "", title: "each loop as a classic feedback block diagram", onclick: () => go({ view: "blocks" }) }, "blocks"),
      h("button", { class: view === "wiring" ? "on" : "", onclick: () => go({ view: "wiring" }) }, "wiring")),
    wrapBtn,
    h("button", { title: "open every system: all their parts", onclick: () => { S.graphSig = ""; go({ open: "*" }); } }, "open all"),
    h("button", { title: "close every system into a box", onclick: () => { S.graphSig = ""; go({ open: "-" }); } }, "close all"),
    crumbs,
    around ? h("span", { class: "pill" }, "around " + around, " ", h("a", { href: "#", onclick: (ev) => { ev.preventDefault(); go({ around: "" }); } }, "×")) : null);
  const zoom = h("div", { class: "zoom" },
    h("span", { id: "panhint", class: "muted panhint", hidden: true, title: "drag to pan, or fit to see it whole" }, "more beyond the edge"),
    h("button", { onclick: () => fit(svg, S.layout) }, "fit"),
    h("button", { title: "save the diagram as an SVG file", onclick: () => exportSvg(svg, `${S.status?.name || "ergostat"}-${system || "all"}-${view}.svg`) }, "save SVG"),
    h("button", { title: "save the parts and how they connect, without live values or status: for a design document",
                  onclick: () => exportSvg(svg, `${S.status?.name || "ergostat"}-${system || "all"}-${view}-design.svg`, true) }, "design SVG"),
    h("button", { title: "save the diagram as a PNG picture, at twice the size", onclick: () => exportPng(svg, `${S.status?.name || "ergostat"}-${system || "all"}-${view}.svg`) }, "PNG"),
    h("button", { onclick: () => { S.view.k *= 1.2; applyView(svg); } }, "+"),
    h("button", { onclick: () => { S.view.k /= 1.2; applyView(svg); } }, "−"));
  wrap.append(svg, toolbar, zoom);
  S.legendEl = legend(view);   // blocks, wiring and control each read differently
  const side = h("div", { class: "side" });
  main.append(h("div", { class: "diagram" }, wrap, side));
  panZoom(svg);
  S.graphSig = ""; S.fitted = false;
  wrap.append(h("div", { class: "empty loading" }, "loading…"));
  let fails = 0;

  async function tick() {
    let g;
    try { g = await api("graph", { view: view === "blocks" ? "control" : view, system, around, ...(openQ != null && view !== "wiring" ? { open: openQ } : {}) }); fails = 0; }
    catch (e) {
      if (++fails >= 3) { wrap.querySelector(".empty")?.remove(); wrap.append(h("div", { class: "empty" }, SNAP ? "this view is not in the snapshot: the whole system and each system are" : "the server is not answering: is ergostat still running?")); }
      return;
    }
    wrap.querySelector(".loading")?.remove();
    S.graph = g;
    if (g.tree && !sysSel.dataset.tree) {            // the picker as the tree it is: each system under the one it is within
      sysSel.dataset.tree = "1";
      const kids = (p) => Object.keys(g.tree).filter((x) => (g.tree[x].within || null) === p).sort();
      const opts = [h("option", { value: "" }, "everything")];
      const add = (p, depth) => { for (const x of kids(p)) { opts.push(h("option", { value: x, selected: x === system ? "" : null }, "\u00a0\u00a0".repeat(depth) + x)); add(x, depth + 1); } };
      add(null, 0);
      sysSel.replaceChildren(...opts);
    }
    if (g.tree && system) {                          // where this system sits: each level up, one click away
      const up = []; let x = system;
      while (x) { up.unshift(x); x = g.tree[x]?.within; }
      crumbs.replaceChildren(h("a", { href: "#", onclick: (ev) => { ev.preventDefault(); S.drill(""); } }, "everything"),
        ...up.flatMap((x, i) => [" › ", i < up.length - 1 ? h("a", { href: "#", onclick: (ev) => { ev.preventDefault(); S.drill(x); } }, x) : h("b", {}, x)]));
    } else crumbs.replaceChildren();
    if (view === "blocks") {
      wrap.querySelector(".empty")?.remove();
      const drawn = Object.keys(g.loops || {}).length ? drawBlocks(svg, g) : null;
      if (!drawn) {
        svg.replaceChildren();
        wrap.append(h("div", { class: "empty" }, "no whole loops to draw here"));
      } else {
        S.layout = drawn;
        if (!S.fitted) { fit(svg, S.layout, true); S.fitted = true; }
      }
      renderSide(side, g, "blocks");
      return;
    }
    if (!g.nodes.length) {
      svg.replaceChildren();
      wrap.querySelector(".empty")?.remove();
      wrap.append(h("div", { class: "empty" }, view === "wiring" ? "no agents fill roles here yet" : "nothing to draw: the model is empty"));
      renderSide(side, g, view);
      return;
    }
    wrap.querySelector(".empty")?.remove();
    const sg = sig(g);
    if (sg !== S.graphSig) {
      const r = svg.getBoundingClientRect();
      const aspect = r.width && r.height ? r.width / Math.max(r.height - 80, 200) : 1.6;
      const asp = g.kind === "wiring" ? aspect * 2.5 : aspect;      // wiring: pack the components side by side
      // a chain of loops far wider than the window is folded at the pipes between loops, unless told not to
      let lay = await layoutGraph(g, asp, S.wrap === true && g.kind === "control");
      S.wrapAuto = false;
      if (S.wrap == null && g.kind === "control" && couplings(g).length && lay.width / lay.height > 2 * asp) {
        lay = await layoutGraph(g, asp, true);
        S.wrapAuto = true;
      }
      S.layout = lay;
      wrapBtn.classList.toggle("on", S.wrap === true || (S.wrap == null && S.wrapAuto));
      S.graphSig = sg;
    } else {
      // same structure: keep positions, redraw with new values (label texts may change length slightly)
    }
    if (S.pressed) return;                             // mid-click: a redraw now would swallow it; the next tick draws
    drawGraph(svg, g, S.layout);
    if (!S.fitted) { fit(svg, S.layout, true); S.fitted = true; }
    renderSide(side, g, view);
  }
  await tick();
  S.timer = setInterval(tick, 2500);
}

function renderSide(side, g, view) {
  const st = S.status || { attention: [], loops: {} };
  const all = g.attention || st.attention;           // from the same snapshot as the diagram beside it
  const problems = all.filter((a) => a.level !== "hint"), hints = all.filter((a) => a.level === "hint");
  side.replaceChildren();
  if (S.status && !S.status.running && !S.at && !SNAP) {
    const last = Math.max(0, ...Object.values(g.loops || {}).map((l) => (S.status.loops[l.controller || ""] || {}).last_read || 0),
                          ...Object.values(S.status.loops || {}).map((l) => l.last_read || 0));
    side.append(h("div", { class: "att" }, h("div", { class: "warn" }, h("b", {}, "not running: "),
      last ? `these are the last readings, from ${ago(last)}; nothing is measuring now` : "nothing has been measured")));
  }
  side.append(h("h3", {}, "needs attention"));
  const att = h("div", { class: "att" });
  if (!problems.length) att.append(h("div", { class: "ok" }, "nothing needs you"));
  const MAX = 6;
  // a command the CLI would suggest becomes a link to the same view here
  const linked = (says) => {
    const m = /ergostat event --type (\S+?)\)?$/.exec(says);
    return m ? [says.slice(0, m.index), h("a", { href: `#/record?type=${encodeURIComponent(m[1])}` }, `the record of ${m[1]}`), says.endsWith(")") ? ")" : ""] : says;
  };
  for (const a of problems.slice(0, MAX)) att.append(h("div", { class: a.level }, h("b", {}, a.what), " ", linked(a.says)));
  if (problems.length > MAX) att.append(h("div", { class: "more" }, `and ${problems.length - MAX} more: see Loops and Residuals`));
  side.append(att);
  if (hints.length) {
    // open when a loop is off: then the suggestions are the diagnosis, not an aside
    // (the moment drawn, not now; and once the reader opens or closes them, as they left them)
    const anyOff = Object.values(g.loops || {}).some((l) => l.status === "off");
    const open = S.suggestOpen ?? anyOff;
    const d = h("details", { class: "suggest", open: open ? "" : null },
                h("summary", { onclick: () => { S.suggestOpen = !d.open; } }, `suggestions (${hints.length})`));   // the reader's own choice
    for (const a of hints) {
      const loop = /^loop (\S+)/.exec(a.says)?.[1];
      d.append(h("div", { class: "hint" }, h("b", {}, a.what), " ", a.says, " ",
        loop ? h("a", { href: "#", onclick: (ev) => { ev.preventDefault(); openLoop(loop); } }, "the evidence") : null));
    }
    side.append(d);
  }
  const loops = Object.entries(g.loops || {});
  if (view === "control" || view === "blocks") {
    side.append(h("h3", {}, `loops (${loops.length})`));
    if (!loops.length) side.append(h("div", { class: "muted" }, "no loops in view"));
    for (const [name, lp] of loops) {
      const full = lp;                                   // the diagram's own snapshot
      side.append(h("div", { class: "looprow", "data-loop": name,
                              onmouseenter: () => highlightLoop(name), onmouseleave: () => highlightLoop(null),
                              onclick: () => openLoop(name) },
        h("b", {}, name), statusEl(lp.status),
        h("div", { class: "sub" }, `${lp.stock} ${fmt(full.value)} · setpoint ${lp.setpoint}${full.band || ""}`)));
    }
  } else {
    if (g.cycles?.length) {
      side.append(h("h3", {}, `cycles among the agents (${g.cycles.length})`));
      for (const cy of g.cycles) {
        side.append(h("div", { class: "looprow", onmouseenter: () => highlightAgents(cy.agents), onmouseleave: () => highlightAgents(null) },
          h("b", {}, cy.agents.concat(cy.agents[0]).join(" → ")),
          cy.loop ? null : h("span", { class: "status s-open" }, "undeclared"),
          h("div", { class: "sub" }, cy.loop ? `the loop ${cy.loop} accounts for it` : "something runs in a circle that no loop declares")));
      }
    }
    side.append(h("h3", {}, `agents in this view (${g.nodes.length})`));
    for (const n of g.nodes) side.append(h("div", { class: "looprow", onclick: () => openAgent(n.label) },
      h("b", {}, n.label), h("span", { class: "pill" }, `rung ${n.rung}`), h("div", { class: "sub" }, n.agentKind)));
  }
  if (st.changes?.length) {
    const last = st.changes[st.changes.length - 1];
    const n = (c) => c.added.length + c.removed.length + c.changed.length;
    const d = h("details", { class: "changes" }, h("summary", {}, `the model was edited ${ago(last.time)}`,
      h("span", { class: "muted" }, ` (${n(last)} part${n(last) === 1 ? "" : "s"}${st.changes.length > 1 ? `, ${st.changes.length} edits` : ""})`)));
    for (const c of st.changes.slice().reverse()) {
      const what = [...c.added.map((x) => "+" + x), ...c.removed.map((x) => "−" + x), ...c.changed.map((x) => "~" + x)];
      d.append(h("div", { class: "change" }, h("span", { class: "muted num" }, ago(c.time)), " ", what.join("  ")));
    }
    side.append(h("h3", {}, "the model"), d);
  }
  side.append(h("h3", {}, "how to read it"), legend(view));
  side.append(h("h3", {}, "window"), h("div", { class: "muted" }, `rates and changes over the last ${S.since}`));
}

