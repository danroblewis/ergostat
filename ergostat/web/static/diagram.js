/* the diagrams: shapes, ELK layout, drawing, pan and zoom, the side panel (the Blocks view: blocks.js; the Process view: process.js) */
"use strict";
/* ------------------------------------------------------------------ the diagram */

const SIZE = { terminal: [120, 34], auxiliary: [140, 62], stock: [168, 84], valve: [40, 40], disturbance: [40, 40], cloud: [54, 36], sensor: [44, 44], controller: [200, 92], agent: [210, 92] };
const CH = 6.7;   // px per character, for label sizes
const OPEN_LOOP = "open loop: acts on its schedule, reads nothing";
const WRAP_GAIN = 1.25;      // a chain far wider than tall is wrapped into rows only when they fit the window this much better

function labelLines(n) {
  if (n.sd) return sdLabelLines(n);                    // the system dynamics view's (dynamics.js)
  if (n.kind === "valve") return [n.label, `${n.position != null ? "open " + fmt(n.position) + " · " : ""}${n.rateText}${n.max ? ` · ≤ ${fmt(n.max)} a run` : ""}${n.mode && n.mode !== "auto" ? " · " + n.mode : ""}`, n.agent ? "§badge" : null].filter(Boolean);
  if (n.kind === "disturbance") return [n.label, `${n.rateText}${n.estimated ? " (est.)" : ""}`, n.agent ? "§badge" : null].filter(Boolean);
  if (n.kind === "sensor") return [n.label, n.reading != null ? `reads ${n.reading}` : "no reading", n.agent ? "§badge" : null].filter(Boolean);
  if (n.kind === "auxiliary") return [n.label, n.agent ? "§badge" : null].filter(Boolean);
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
/* what a first layout tells the second: which side of a system box each port belongs on (facing
   what it joins), the order of ports down a side (by where what they join lies, so lines between
   two boxes do not cross), and which valves turn their stem down (what commands or reads them is
   below) */
function portSides(g) {
  for (const n of g.nodes) {
    if (n.kind === "system") {
      for (const p of n.ports) p.at = S.portAt?.[p.id] || (p.side === "in" ? "west" : "east");
      n.ports.sort((a, b) => (a.at > b.at) - (a.at < b.at) || (S.portRank?.[a.id] ?? 1e9) - (S.portRank?.[b.id] ?? 1e9) || (a.label > b.label) - (a.label < b.label));
    }
  }
}
function wanted(lay, g) {
  const box = Object.fromEntries(lay.children.map((c) => [c.id, c]));
  const at = (id) => { const b = box[id]; return b ? { x: b.x + b.width / 2, y: b.y + b.height / 2 } : null; };
  const portAt = {};                                  // each laid-out port's place, in the diagram's coordinates
  for (const c of lay.children) for (const p of c.ports || []) portAt[p.id] = { x: c.x + p.x + (p.width || 0) / 2, y: c.y + p.y + (p.height || 0) / 2 };
  const other = (e, mine) => (e.sourcePort === mine ? (e.targetPort && portAt[e.targetPort]) || at(e.target)
                                                    : (e.sourcePort && portAt[e.sourcePort]) || at(e.source));
  const sides = {}, ranks = {};
  for (const n of g.nodes) {
    if (n.kind === "system" && box[n.id]) {
      const b = box[n.id], mid = b.x + b.width / 2;
      for (const p of n.ports) {
        const peers = g.edges.filter((e) => e.sourcePort === p.id || e.targetPort === p.id).map((e) => other(e, p.id)).filter(Boolean);
        if (!peers.length) continue;
        const cx = peers.reduce((a, c) => a + c.x, 0) / peers.length, cy = peers.reduce((a, c) => a + c.y, 0) / peers.length;
        sides[p.id] = cx < mid ? "west" : "east";
        ranks[p.id] = Math.round(cy);
      }
    }
  }
  return { sides, ranks };
}

/* (opts.dry: laid out and placed, not routed: a layout tried to be compared; opts.plain: no satellites' room kept) */
async function layoutGraph(g, aspect, cut = false, again = 0, opts = {}) {
  if (again === 0 && !opts.dry) { await avoidLoad(); S.layouts = (S.layouts || 0) + 1; }   // (how many: the tests count them)
  portSides(g);
  const ORDER = { cloud: 0, terminal: 0, disturbance: 1, stock: 2, valve: 3, system: 3, auxiliary: 4, sensor: 5, controller: 6, agent: 2 };
  const rank = (n) => (n.kind === "cloud" ? (n.id.endsWith(":out") ? 4 : 0) : ORDER[n.kind] ?? 3);
  const nodesInOrder = [...g.nodes].sort((a, b) => rank(a) - rank(b));
  const byIdNodes = Object.fromEntries(g.nodes.map((n) => [n.id, n]));
  const children = nodesInOrder.map((n) => {
    let [w, hgt] = SIZE[n.kind] || [60, 40];
    if (n.kind === "stock") {                         // the title, and the value beside the setpoint, all fit
      const lp = Object.values(g.loops || {}).find((l) => l.stock === n.label);
      w = Math.max(w, textWidth(n.label) + 34, (n.valueText || "").length * 14 + textWidth(n.unit || "") + textWidth(lp ? lp.setpoint : "") + 44);
    }
    if (n.kind === "agent") w = Math.max(w, textWidth(n.label) * 1.15 + textWidth(`${n.agentKind}`) + 56,
                                         ...(n.roles || []).map((r) => textWidth(`${r.kind} ${r.name}`) + 40));   // the name and its rung, apart
    if (n.kind === "controller") w = Math.max(w, textWidth(n.label) * 1.12 + 120, textWidth("holds " + n.setpoint) + 60,   // the title is bold
                                              n.openLoop ? textWidth(OPEN_LOOP) + 30 : 0);
    if (n.kind === "system") [w, hgt] = systemSize(n);
    if (n.kind === "terminal") w = Math.max(textWidth(n.label + (n.valueText ? "  " + n.valueText : "")), textWidth(n.in ? "in " + n.in : "")) + 34;
    if (n.sd) [w, hgt] = sdSize(n);                   // the system dynamics view's parts (dynamics.js)
    else if (g.kind === "dynamics" && n.kind === "terminal") [w, hgt] = [textWidth(`<${n.label}>`) + 20, 24];
    const lines = labelLines(n);
    const node = { id: n.id, width: w, height: hgt, layoutOptions: {} };
    if (n.kind === "system") {                        // its ports where their names are written: inputs left, outputs right
      node.layoutOptions["elk.portConstraints"] = "FIXED_POS";
      const row = { west: 0, east: 0 };
      node.ports = n.ports.map((p) => ({ id: p.id, width: 8, height: 8, x: p.at === "west" ? -4 : w - 4, y: sysTop(n) + (row[p.at]++) * SYS_ROW - 4,
                                         layoutOptions: { "elk.port.side": p.at === "west" ? "WEST" : "EAST" } }));
    }
    if (lines.length) {
      const lw = Math.max(...lines.map((l) => l === "§badge" ? textWidth(badgeText(n.agent)) + 18 : textWidth(l))) + 8;
      node.labels = [{ id: n.id + ":label", text: lines.join("\n"), width: lw, height: lines.length * 16 + 4 }];
      node.layoutOptions["elk.nodeLabels.placement"] = "OUTSIDE V_BOTTOM H_CENTER";   // (a valve turned after has them moved: valves.js)
    }
    if (n.kind === "valve" || n.kind === "disturbance") {
      node.layoutOptions["elk.portConstraints"] = "FIXED_SIDE";
      node.ports = [
        { id: n.id + ":in", width: 1, height: 1, layoutOptions: { "elk.port.side": "WEST" } },
        { id: n.id + ":out", width: 1, height: 1, layoutOptions: { "elk.port.side": "EAST" } },
        { id: n.id + ":ctl", width: 1, height: 1, layoutOptions: { "elk.port.side": "NORTH" } },     // laid out stem up, then turned
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
      if (!e.sourcePort && flowNode.has(src)) src = src + (e.kind === "pipe" ? ":out" : ":sense");
    } else if (e.kind === "pipe") {
      if (flowNode.has(dst)) dst = dst + ":in";
      if (flowNode.has(src)) src = src + ":out";
    } else {                                            // information: into a flow at its stem, out of one beside it
      if (flowNode.has(dst)) dst = dst + ":ctl";
      if (flowNode.has(src)) src = src + ":sense";      // what leaves a flow (read, or driving another) leaves apart from its command
    }
    const out = { id: e.id, sources: [src], targets: [dst], layoutOptions: {} };
    if (e.kind === "pipe") { out.layoutOptions["elk.layered.priority.straightness"] = "100"; out.layoutOptions["elk.layered.priority.direction"] = "20"; out.layoutOptions["elk.layered.priority.shortness"] = "10"; }   // a flow is laid out straight first
    if (e.kind === "wire" && e.via && e.via.length) {
      const t = e.via.slice(0, 2).join(", ") + (e.via.length > 2 ? ` +${e.via.length - 2}` : "");
      out.labels = [{ id: e.id + ":l", text: t, width: textWidth(t) + 6, height: 14 }];
    }
    return out;
  });
  // flows between one stock and a cloud: left out, their room kept on their stock (satellites.js)
  const sat = ELK_PRESETS[LAYOUT]?.upright && !opts.plain ? reserveSatellites(children, edges, satellitePlan(g), g) : null;
  if (sat) sat.ends = Object.fromEntries(g.edges.map((e) => [e.id, [e.source, e.target]]));
  const elkChildren = sat ? sat.children : children, elkEdges = sat ? sat.edges : edges;
  // an open system is laid out as one container, its parts together, nested as the systems nest
  const open = new Set(g.tree ? g.nodes.flatMap((n) => n.systems || []) : []);
  let roots = elkChildren;
  if (open.size) {
    const cont = {};
    const box = (name) => (cont[name] ||= { id: "hull:" + name, children: [], layoutOptions: {
      "elk.padding": "[top=44,left=26,bottom=26,right=26]",
      "elk.layered.spacing.nodeNodeBetweenLayers": "120", "elk.spacing.nodeNode": "56", "elk.spacing.edgeNode": "28" } });
    const parentOf = (name) => { let x = g.tree[name]?.within; while (x && !open.has(x)) x = g.tree[x]?.within; return x || null; };
    for (const name of open) box(name);
    roots = [];
    for (const c of elkChildren) {
      const inner = (byIdNodes[c.id]?.systems || [])[0];
      (inner ? cont[inner].children : roots).push(c);
    }
    for (const name of open) { const p = parentOf(name); (p ? cont[p].children : roots).push(cont[name]); }
  }
  // a closed system linked to nothing, beside an open one: left out of ELK's layout, which would give it a row of its
  // own, and put where there is room after (places.js packLoose)
  const linked = new Set(g.edges.flatMap((e) => [e.source, e.target]));
  const loose = open.size ? roots.filter((c) => byIdNodes[c.id]?.kind === "system" && !linked.has(c.id)) : [];
  if (loose.length && loose.length < roots.length) roots = roots.filter((c) => !loose.includes(c));
  const roomy = g.nodes.some((n) => n.kind === "system" || (n.systems || []).length);
  const graph = {
    id: "root", children: roots, edges: elkEdges,
    layoutOptions: {
      ...(open.size ? { "elk.hierarchyHandling": "INCLUDE_CHILDREN" } : {}),
      "elk.layered.mergeEdges": "true",
      "elk.algorithm": "layered", "elk.direction": "RIGHT", "elk.edgeRouting": "ORTHOGONAL",
      // with systems in it, wider lanes between parts: lines between boxes run straight instead of hooking round
      "elk.layered.spacing.nodeNodeBetweenLayers": roomy ? "120" : "64", "elk.spacing.nodeNode": roomy ? "56" : "36",
      "elk.spacing.edgeNode": roomy ? "28" : "18",
      "elk.spacing.edgeEdge": "12", "elk.layered.spacing.edgeNodeBetweenLayers": "18",
      "elk.layered.nodePlacement.strategy": "NETWORK_SIMPLEX", "elk.layered.crossingMinimization.semiInteractive": "false",
      "elk.layered.considerModelOrder.strategy": "NODES_AND_EDGES", "elk.separateConnectedComponents": "true",
      "elk.spacing.componentComponent": "70", "elk.spacing.labelNode": "6", "elk.edgeLabels.placement": "CENTER",
      "elk.layered.cycleBreaking.strategy": "GREEDY", "elk.aspectRatio": String(aspect || 1.6),
      "elk.padding": "[top=40,left=40,bottom=40,right=40]",
    },
  };
  const lay = await runLayout(graph, g);
  if (open.size || lay.children.some((c) => c.children?.length)) flatten(lay);   // (or blocks laid out together: layouts.js)
  placeSatellites(lay, sat);                             // the satellites put back in the room kept (satellites.js)
  if (loose.length && !roots.some((c) => loose.includes(c))) packLoose(lay, loose);
  if (again < 2) {                      // ports facing away from what they join, valves facing away: turn them, lay out again
    const w = wanted(lay, g);
    const ports = g.nodes.flatMap((n) => n.ports || []);
    const moved = ports.some((p) => (w.sides[p.id] && p.at !== w.sides[p.id]) || (w.ranks[p.id] != null && S.portRank?.[p.id] == null));
    if (moved) {
      S.portAt = { ...(S.portAt || {}), ...w.sides };
      S.portRank = { ...(S.portRank || {}), ...w.ranks };
      return layoutGraph(g, aspect, cut, again + 1, opts);   // (a turn can move parts: at most twice)
    }
  }
  if (cuts.length) {                                     // rows first: the router works on the parts where they end up
    restack(lay, g);
    routeCuts(lay, cuts);
  }
  if (anchorLayout(lay, g, S.anchor)) S.anchored = true;   // a system opened or closed stays where it was (places.js)
  if (ELK_PRESETS[LAYOUT]?.upright) {
    seatCloudFlows(lay, g);                              // flows to or from a cloud beside their stock, upright where there is room (places.js)
    S.centred = centreValves(lay, g);                    // a valve between two stocks put between them (satellites.js)
  }
  // the satellites' room kept only where the drawing still fits the screen about as well as without it (it may make a
  // row of stocks taller, or wider)
  if (sat && Object.keys(sat.kept).length && !opts.plain && again === 0) {
    const plain = await layoutGraph(g, aspect, cut, 0, { ...opts, plain: true, dry: true });
    if (screenFit(plain) > SAT_KEEP * screenFit(lay)) return finishLayout(plain, g, opts);
  }
  return finishLayout(lay, g, opts);
}
const SAT_KEEP = 1.1;
function screenFit(lay) {                                 // the zoom at which the drawing fits the canvas (1 at most)
  const r = document.querySelector("svg.canvas")?.getBoundingClientRect();
  const [cw, ch] = r?.width ? [r.width - 40, r.height - 90] : [1260, 810];
  return Math.min(1, cw / Math.max(1, lay.width), ch / Math.max(1, lay.height));
}
function finishLayout(lay, g, opts) {
  if (!lay.finished) {
    lay.finished = true;
    applyPins(lay, g);
    orientValves(lay, g);                                // valves face their pipes and their links (valves.js)
  }
  if (!opts.dry) avoidStart(lay, g);                     // every line, by libavoid (avoid.js): ELK's until it is done
  return lay;
}

/* the pins (places.js): kept in this browser, per project, view and what is open */
function pinKey() { return S.pinKey || ""; }
function loadPins() {
  try { return JSON.parse(localStorage.getItem(pinKey()) || "{}"); } catch (e) { return {}; }
}
function savePins() {
  try { if (Object.keys(S.pins || {}).length) localStorage.setItem(pinKey(), JSON.stringify(S.pins)); else localStorage.removeItem(pinKey()); }
  catch (e) { /* not remembered: they last this visit */ }
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
      } else if (c.id.startsWith("grp:")) walk(c, x, y, depth);   // a block laid out together (layouts.js): not drawn
      else leaves.push({ ...c, x, y });
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
  lay.rows = [];                                      // where each row is: the pipes between them run in the gaps
  for (const gr of groups) {
    const dx = 40 - gr.x0, dy = y - gr.y0;
    lay.rows.push({ y0: y, y1: y + gr.h, ids: gr.ids });
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
    // the gap: the middle of the space above the target's row, or below the source's when the target is above
    const rowOf = (id) => (lay.rows || []).find((r) => r.ids.has(id));
    const rt = rowOf(e.target), rs = rowOf(e.source);
    const turn = Math.max(sx + 18, ...(a.labels || []).map((l) => a.x + l.x + l.width + 12));   // clear of the valve's labels
    let gapY = ty > sy ? (rt ? rt.y0 - 35 : b.y - 26) : (rs ? rs.y1 + 35 : a.y + a.height + 26);
    if (rt && rt === rs) {                             // one row (a controller joins them): a free band between the two ends
      const x0 = Math.min(tx - 14, turn) - 6, x1 = Math.max(tx - 14, turn) + 6;
      const labelled = lay.children.flatMap((c) => [c, ...(c.labels || []).map((l) => ({ x: c.x + l.x, y: c.y + l.y, width: l.width, height: l.height }))]);
      const [lo, hi] = [Math.min(sy, ty), Math.max(sy, ty)];
      const band = (boxes) => {                        // clear of the parts and their labels, else of the parts
        for (let y = hi - 26; y > lo + 10; y -= 4) if (!boxes.some((c) => c.x < x1 && c.x + c.width > x0 && c.y - 8 < y && c.y + c.height + 8 > y)) return y;
        return null;
      };
      gapY = band(labelled) ?? band(lay.children) ?? gapY;
    }
    const pts = sy === ty ? [] : [{ x: turn, y: sy }, { x: turn, y: gapY }, { x: tx - 14, y: gapY }, { x: tx - 14, y: ty }];   // inside the outline
    lay.width = Math.max(lay.width, turn + 30);
    lay.edges.push({ id: e.id, sections: [{ startPoint: { x: sx, y: sy }, bendPoints: pts, endPoint: { x: tx, y: ty } }], cut: true });
  }
}

/* node shapes, drawn with their top-left at 0,0 */
function badge(a, x, y) {
  if (!a) return null;
  const t = badgeText(a), w = textWidth(t) + 24;
  return s("g", { class: "badge", transform: `translate(${x - w / 2},${y})` }, s("rect", { width: w, height: 16, rx: 8, fill: "var(--panel)", stroke: "var(--line)", "stroke-width": 1 }),
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
    g.append(s("line", { x1: sx, x2: sx, y1: my - 3, y2: my + 7, stroke: "var(--ink)", "stroke-width": 1.6, class: "live" }));
    const sp_ = sp.setpoint.replace("<=", "≤").replace(">=", "≥").replace("==", "=").trim();
    g.append(s("text", { x: w - 10, y: 50, class: "t-sub sp-text", "text-anchor": "end" }, sp_));
  }
  if (pts.length > 1) {
    // the trend on one scale with its setpoint, drawn dashed: how far off it ran, not only its shape
    const vs = pts.map((p) => p[1]);
    const lo = Math.min(...vs, spv ?? Infinity), hi = Math.max(...vs, spv ?? -Infinity);
    const yOf = (v) => hgt - 8 - ((v - lo) / ((hi - lo) || 1)) * 16;
    if (spv != null) g.append(s("line", { x1: 10, x2: w - 10, y1: yOf(spv), y2: yOf(spv), stroke: "var(--ink)", "stroke-width": 0.8,
                                          "stroke-dasharray": "3 3", opacity: 0.55, class: "live" }));
    const d = vs.map((v, i) => `${i ? "L" : "M"}${10 + (i / (vs.length - 1)) * (w - 20)},${yOf(v)}`).join("");
    g.append(s("path", { d, fill: "none", stroke: tone, "stroke-width": 1.4, opacity: 0.8, class: "live" }));
  }
  g.append(s("text", { x: 10, y: 17, class: "t-label" }, n.label));
  g.append(s("text", { x: 10, y: 50, class: "t-value live" }, n.valueText, s("tspan", { class: "t-unit", dx: 4 }, n.unit || "")));
  return g;
}

/* a variable: what is measured or set but does not accumulate (system dynamics' auxiliary, drawn
   as one): its value inside, its loop's health on its rim, the block that sets it on its badge */
function drawVariable(n, w, hgt) {
  const sp = S.graph?.loops ? Object.values(S.graph.loops).find((l) => l.stock === n.label) : null;
  const tone = sp ? ({ off: "var(--bad)", holding: "var(--ok)", open: "var(--warn)" }[sp.status] || "var(--line)") : "var(--stock-line)";
  const g = s("g");
  g.append(s("ellipse", { class: "hit", cx: w / 2, cy: hgt / 2, rx: w / 2 - 1, ry: hgt / 2 - 1, fill: "var(--stock)", stroke: tone, "stroke-width": sp ? 2.4 : 1.6 }));
  g.append(s("text", { x: w / 2, y: 26, "text-anchor": "middle", class: "t-value live" }, n.valueText,
             s("tspan", { class: "t-unit", dx: 4 }, n.unit || "")));
  if (sp) g.append(s("text", { x: w / 2, y: hgt - 6, "text-anchor": "middle", class: "t-sub" },
                     sp.setpoint.replace("<=", "≤").replace(">=", "≥").replace("==", "=").trim()));
  if ((n.points || []).length > 1) {                     // its trend over the window, inside it, as a stock's is
    const t = sparkSvg(n.points, w * 0.56, 14, sp ? setpointOf(sp.setpoint) : null);
    t.setAttribute("x", w * 0.22); t.setAttribute("y", 31); t.classList.add("live");
    g.append(t);
  }
  return g;
}

function drawValve(n, w, hgt, ln) {
  const t = turnTransform(ln?.turn, w, hgt);          // turned to face its pipe and its links (valves.js)
  const g = s("g", t ? { transform: t } : {});
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

function drawDisturbance(n, w, hgt, ln) {
  const t = turnTransform(ln?.turn, w, hgt);
  const g = s("g", t ? { transform: t } : {});
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
  g.append(s("circle", { cx: 20, cy: 22, r: 9, fill: "var(--panel)", stroke: "var(--ctl-line)", "stroke-width": 1.6 }));
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
    g.append(s("text", { x: 12, y: 56, class: "t-sub live", "font-style": "italic" }, "“" + t + "”", s("tspan", { "font-style": "normal" }, when)));
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
  g.append(s("text", { x: 16, y: 20, class: "t-label" }, n.label));
  g.append(s("text", { x: w - 26, y: 20, class: "t-sub", "text-anchor": "end" }, `${n.agentKind}`));
  g.append(rungDot(n.rung, w - 14, 16, 6.5));
  const when = n.schedule || "";
  g.append(s("text", { x: 16, y: 38, class: "t-sub" }, when, n.runs ? s("tspan", { class: "live" }, ` · ${n.runs} runs`) : null));
  [...(n.roles || []).map((r) => `${r.kind} ${r.name}`), ...(n.loads || []).map((d) => `the load: ${d}`)].slice(0, 3)
    .forEach((t, i) => g.append(s("text", { x: 16, y: 56 + i * 14, class: "t-sub" }, t)));
  return g;
}

/* each kind of line has one colour, whatever it is part of: what it is, not how it is doing */
const LINE_COLOR = { measure: "var(--sensor-line)", signal: "var(--sensor-line)", action: "var(--ctl-line)", influence: "var(--dist)" };

/* a port's twin: the same part crossing the other way on the same side, named once with it (the dynamics view's
   ⇄); none in the control view */
function sysTwin(n, p) {
  if (S.graph?.kind !== "dynamics") return null;
  const side = (q) => q.at || (q.side === "in" ? "west" : "east");
  return (n.ports || []).find((q) => q !== p && q.part === p.part && side(q) === side(p)) || null;
}
/* a system drawn as one part: its name, how its loops are doing, and its ports (what crosses its edge) */
const SYS_TOP = 70, SYS_ROW = 20, MEAS_ROW = 24;
const sysTop = (n) => SYS_TOP + (n.measures?.length || 0) * MEAS_ROW;     // its ports start below its measures
function systemSize(n) {
  const side = (d) => n.ports.filter((p) => (p.at || (p.side === "in" ? "west" : "east")) === (d === "in" ? "west" : "east"));
  const lw = (ps) => Math.max(0, ...ps.map((p) => textWidth(p.label + (p.value ? "  " + p.value : ""))));
  const mw = Math.max(0, ...(n.measures || []).map((m) => textWidth(m.label) + textWidth(`${m.value} ${m.unit}`) + textWidth(m.setpoint || "") + 150));
  const w = Math.max(240, textWidth(n.label) * 1.25 + 150, lw(side("in")) + lw(side("out")) + 60, mw,
                    n.remote ? textWidth(n.remote.says) + 40 : 0);
  return [w, Math.max(96, sysTop(n) + Math.max(side("in").length, side("out").length) * SYS_ROW + 6 + (n.inner?.length ? 16 : 0))];
}
function loopsText(n) {
  const l = n.loops || {}, total = Object.values(l).reduce((a, b) => a + b, 0);
  if (!total) return "no loops";
  return `${total} loop${total > 1 ? "s" : ""}: ` + ["holding", "off", "stale", "open", "unknown"].filter((k) => l[k]).map((k) => `${l[k]} ${k}`).join(", ");
}
function drawSystem(n, w, hgt) {
  const tone = { off: "var(--bad)", holding: "var(--ok)", open: "var(--warn)" }[n.status] || "var(--unknown)";
  const g = s("g", n.remote ? { class: `sys-remote remote-${n.remote.state}` } : {});
  // a remote system (run by another ergostat, read here): its outline dashed, and where it runs said under its name
  g.append(s("rect", { class: "hit", width: w, height: hgt, rx: 12, fill: "var(--panel)", stroke: "var(--system-line)", "stroke-width": 2,
                       ...(n.remote ? { "stroke-dasharray": "9 5" } : {}) }));
  g.append(s("rect", { x: 4, y: 4, width: w - 8, height: hgt - 8, rx: 9, fill: "var(--system)", stroke: "var(--system-line)", "stroke-width": 1, "stroke-dasharray": "3 3" }));
  g.append(s("text", { x: 16, y: 24, class: "t-label sys-title" }, n.label));
  g.append(s("circle", { cx: 16 + textWidth(n.label) * 1.25 + 12, cy: 19, r: 5, fill: tone, class: "live" }));
  g.append(s("text", { x: 16, y: 42, class: "t-sub live" }, n.remote ? n.remote.says
    : loopsText(n) + (n.subsystems?.length ? ` · ${n.subsystems.length} inside` : "")));
  // its measures, as a control panel: each one's health, value, setpoint and trend (click: the part itself)
  (n.measures || []).forEach((m, i) => {
    const y = 52 + i * MEAS_ROW;
    const mt = { off: "var(--bad)", holding: "var(--ok)", open: "var(--warn)" }[m.status] || "var(--unknown)";
    const row = s("g", { class: "measure-row", transform: `translate(0,${y})`, "data-act": "measure",
                         onclick: (ev) => { ev.stopPropagation(); openNode({ id: m.part, kind: m.part.startsWith("flow:") ? "disturbance" : "stock", label: m.label, flow: m.label }); } },
      s("rect", { x: 8, y: 0, width: w - 16, height: MEAS_ROW - 3, rx: 5, class: "measure-bg" }),
      m.goal ? s("circle", { cx: 18, cy: 10.5, r: 4, fill: mt, class: "live" }) : null,
      s("text", { x: 28, y: 15, class: "t-sub" }, m.label),
      s("text", { x: w - 112, y: 15, class: "t-label live", "text-anchor": "end" }, m.value, s("tspan", { class: "t-unit", dx: 3 }, m.unit || ""),
        m.setpoint ? s("tspan", { class: "t-sub", dx: 6 }, m.setpoint.replace("<=", "≤").replace(">=", "≥").replace("==", "=")) : null));
    if ((m.points || []).length > 1) {
      const sp = sparkSvg(m.points, 92, 18, setpointOf(m.setpoint));
      sp.setAttribute("x", w - 104); sp.setAttribute("y", 1);
      row.append(sp);
    }
    g.append(row);
  });
  const btn = (x, label, title, fn) => s("g", { class: "sys-btn", transform: `translate(${x},10)`, onclick: (ev) => { ev.stopPropagation(); fn(); } },
    s("rect", { width: textWidth(label) + 14, height: 20, rx: 4 }), s("text", { x: 7, y: 14 }, label));
  const into = "Into", open = "Open";
  g.append(btn(w - textWidth(into) - 24, into, "Draw this system alone, with what it reaches outside at its edge", () => S.drill?.(n.label)));
  g.append(btn(w - textWidth(into) - textWidth(open) - 46, open, "Open it here: its parts in place of the box", () => S.toggleSystem?.(n.label)));
  if (n.inner?.length) g.append(s("text", { x: 16, y: hgt - 10, class: "t-sub" }, `inner loop: holds ${n.inner.join(", ")} for an outer one`));
  const at = { west: 0, east: 0 };
  for (const p of n.ports || []) {
    const side = p.at || (p.side === "in" ? "west" : "east");
    const y = sysTop(n) + (at[side]++) * SYS_ROW;
    const left = side === "west";
    g.append(s("rect", { x: left ? -4 : w - 4, y: y - 4, width: 8, height: 8, rx: 2, fill: "var(--panel)", stroke: "var(--system-line)", "stroke-width": 1.5 }));
    const px = left ? 0 : w, inward = (p.side === "in") === left;    // which way it carries, across the edge
    g.append(s("path", { d: inward ? `M${px - 2.5},${y - 2.5} L${px + 2},${y} L${px - 2.5},${y + 2.5} Z` : `M${px + 2.5},${y - 2.5} L${px - 2},${y} L${px + 2.5},${y + 2.5} Z`,
                         fill: "var(--system-line)" }));
    g.append(s("text", { x: left ? 12 : w - 12, y: y + 4, class: "t-sub", "text-anchor": left ? "start" : "end" }, p.label, p.value ? s("tspan", { class: "live", dx: 6, opacity: 0.75 }, p.value) : null));
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

const DRAW = { system: drawSystem, terminal: drawTerminal, auxiliary: drawVariable, stock: drawStock, valve: drawValve, disturbance: drawDisturbance, cloud: drawCloud, sensor: drawSensor, controller: drawController, agent: drawAgent };

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

/* the pin on a part (or a system) put by hand: clicked, it is let go, and the layout places it again */
function pinMark(pid, x, y, title = "pinned here: click to let the layout place it again", kind = "system") {
  return s("g", { class: `pin k-${kind}`,"data-act": "unpin", "data-id": pid, transform: `translate(${x},${y})`,
                  onclick: (ev) => { ev.stopPropagation(); delete S.pins[pid]; savePins(); S.relayout?.(); } },
    s("circle", { r: 7 }), s("path", { d: "M-2.5,-3 h5 l-1,3 h2 l-3.5,3 v3 M0,3 v3" }));
}

function redrawLine(svg, id) {                         // a line's new way, while a part is dragged: its paths and its head
  const le = S.layout?.edges.find((x) => x.id === id), e = S.graph?.edges.find((x) => x.id === id);
  const eg = svg.querySelector(`.edge[data-id="${CSS.escape(id)}"]`);
  if (!le || !e || !eg) return;
  const pts = edgePoints(le);
  if (pts.length < 2) return;
  if (S.graph.kind === "blocks") { eg.replaceChildren(...bdEdgeContent(e, pts).els); return; }   // (blocks.js)
  if (S.graph.kind === "process") { eg.replaceChildren(...pmEdgeContent(e, le, pts)); return; }    // (process.js)
  if (S.graph.kind === "dynamics") {                  // drawn again whole: its curve depends on where the parts are
    eg.replaceChildren(...sdEdgeContent(e, pts, S.layout), s("path", { d: roundedPath(pts, 7), class: "edge-hit" }));
    return;
  }
  const d = roundedPath(pts, e.kind === "pipe" ? 10 : 7), body = roundedPath(e.kind === "pipe" && e.arrow ? shortened(pts, 14) : pts, 10);
  for (const p of eg.querySelectorAll("path")) {
    if (p.classList.contains("pipe-out") || p.classList.contains("pipe-in") || p.classList.contains("flowing")) p.setAttribute("d", body);
    else if (p.classList.contains("info") || p.classList.contains("edge-hit")) p.setAttribute("d", d);
    else {                                              // a head: drawn again at the new end
      const fill = p.getAttribute("fill") || p.style.fill;
      const head = e.kind === "pipe" ? pipeHead(pts, fill) : arrowHead(pts, "head", 7);
      if (e.kind !== "pipe") head.style.setProperty("--head", p.style.getPropertyValue("--head"));
      p.replaceWith(head);
    }
  }
  for (const j of eg.querySelectorAll("circle.junction, text.elabel")) j.remove();
}

function shortened(pts, by) {                        // the same line, its last stretch cut back by `by`
  const out = pts.map((p) => ({ ...p }));
  const a = out[out.length - 2], b = out[out.length - 1], len = Math.hypot(b.x - a.x, b.y - a.y);
  if (len > by + 1) { b.x -= ((b.x - a.x) / len) * by; b.y -= ((b.y - a.y) / len) * by; }
  return out;
}
function pipeHead(pts, fill) {                        // a flow's arrowhead: as wide as the pipe and more, at its very end
  const a = pts[pts.length - 2], b = pts[pts.length - 1];
  const ang = Math.atan2(b.y - a.y, b.x - a.x), L = 15, Wd = 9;
  const bx = b.x - L * Math.cos(ang), by = b.y - L * Math.sin(ang);
  const px = -Math.sin(ang) * Wd, py = Math.cos(ang) * Wd;
  return s("path", { class: "pipe-head", d: `M${bx + px},${by + py} L${b.x},${b.y} L${bx - px},${by - py} Z`,
                     style: `fill:${fill};stroke:var(--bg);stroke-width:1` });    // style: .edge path's fill:none would hide it
}

function arrowHead(pts, cls, size = 7) {
  const a = pts[pts.length - 2], b = pts[pts.length - 1];
  const ang = Math.atan2(b.y - a.y, b.x - a.x);
  const p = (t) => `${b.x - size * Math.cos(ang + t)},${b.y - size * Math.sin(ang + t)}`;
  return s("path", { d: `M${p(-0.45)} L${b.x},${b.y} L${p(0.45)} Z`, class: cls });
}

function drawGraph(svg, g, lay) {
  S.drawN = (S.drawN || 0) + 1;                        // (what the geometry alone decides is kept across draws: dynamics.js)
  squareLines(lay, g);                                 // no line drawn across: a stand-in is drawn square, greyed (interact.js)
  portSides(g);
  const byId = Object.fromEntries(g.nodes.map((n) => [n.id, n]));
  const edgeById = Object.fromEntries(g.edges.map((e) => [e.id, e]));
  S.edgeById = edgeById;
  const vp = s("g", { id: "viewport" });
  // systems as hulls behind everything (overlapping freely)
  const hullPins = [];                                     // (drawn on top, with the parts' pins)
  const sd = g.kind === "dynamics";                         // the system dynamics view: monochrome (dynamics.js)
  const hueOf = () => (sd ? "fill:var(--sd-hull);stroke:none" : "fill:none;stroke:var(--system-line)");
  const inkOf = () => (sd ? "fill:var(--sd-ink)" : "fill:var(--muted)");
  if ((g.kind === "control" || sd) && lay.containers?.length) {      // open systems: laid out as containers, drawn as outlines
    const hulls = s("g", { class: "sys-hull" });
    const names = Object.keys(g.tree || {}).sort();
    for (const c of lay.containers) {
      const hue = (210 + names.indexOf(c.name) * 137.5) % 360;
      const hg = s("g", { class: "hull", "data-hull": c.name });
      hulls.append(hg);
      // its top is a handle: dragged, the system moves with everything in it, and stays there (places.js)
      const grip = s("rect", { class: "hull-grip", "data-act": "hull-drag", x: c.x, y: c.y, width: c.width, height: 32, rx: 16,
                               onpointerdown: (ev) => { if (ev.button) return; ev.stopPropagation(); S.hullDrag = { name: c.name, x0: ev.clientX, y0: ev.clientY, cx: c.x, cy: c.y, moved: false }; } });
      hg.append(s("rect", { x: c.x, y: c.y, width: c.width, height: c.height, rx: 16, style: hueOf(hue, 0.45) }), grip,
        s("text", { x: c.x + 14, y: c.y + 22, class: "sys-hull-label", "data-act": "close", style: inkOf(hue), onclick: (ev) => { ev.stopPropagation(); S.toggleSystem?.(c.name); } },
          "▾ " + c.name + (g.tree?.[c.name]?.remote ? " (remote)" : "")),
        s("text", { x: c.x + 14 + textWidth("▾ " + c.name + (g.tree?.[c.name]?.remote ? " (remote)" : "")) * 1.15 + 10, y: c.y + 22, class: "sys-hull-label", "data-act": "into", style: inkOf(hue),
                    onclick: (ev) => { ev.stopPropagation(); S.drill?.(c.name); } }, "⤓"));
      if (S.pins?.["hull:" + c.name]) hullPins.push(pinMark("hull:" + c.name, c.x + c.width - 14, c.y + 4, "moved here: click to let the layout place it again"));
    }
    vp.append(hulls);
  } else if ((g.kind === "control" || sd) && S.showHulls && !g.tree) {
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
        hulls.append(s("rect", { x: x0, y: y0, width: x1 - x0, height: y1 - y0, rx: 16, style: hueOf(hue, 0.45) }),
                     s("text", { x: lx, y: y0 + 18, class: "sys-hull-label", style: inkOf(hue),
                                 onclick: (ev) => { ev.stopPropagation(); S.toggleSystem?.(name); } },
                       name + (S.graph?.tree ? " ▾" : "")));
      });
    });
    vp.append(hulls);
    // the outlines reach past the laid-out nodes: count them in the size that fit and export use
    lay.base ||= { width: lay.width, height: lay.height };
    lay.ox = Math.min(0, ext.x0); lay.oy = Math.min(0, ext.y0);
    lay.width = Math.max(lay.base.width, ext.x1) - lay.ox; lay.height = Math.max(lay.base.height, ext.y1) - lay.oy;
  }
  const edgesG = s("g");
  S.sdSigns = [];                                         // (the polarities placed so far: dynamics.js)
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
    if (sd) eg.append(...sdEdgeContent(e, pts, lay));    // the system dynamics view's pipes and connectors (dynamics.js)
    else if (e.kind === "pipe") {
      // the pipe stops short of its end, and the head, wider than the pipe, fills the rest: its point is the end
      const body = e.arrow ? shortened(pts, 14) : pts, bd = roundedPath(body, 10);
      eg.append(s("path", { d: bd, class: "pipe-out" }), s("path", { d: bd, class: "pipe-in" }));
      if (flowN && flowN.rate > 0) eg.append(s("path", { d: bd, class: "flowing", stroke: dist ? "var(--dist)" : "var(--accent)" }));
      if (e.arrow) eg.append(pipeHead(pts, dist ? "var(--dist)" : "var(--pipe)"));
    } else {
      eg.append(s("path", { d, class: "info" }));
      const ah = arrowHead(pts, "head", 7);
      ah.style.setProperty("--head", LINE_COLOR[e.kind] || "var(--info)");
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
    for (const j of sd ? [] : (le.junctionPoints || []).filter(onLine)) eg.append(s("circle", { cx: j.x, cy: j.y, r: 3.2, class: "junction", fill: LINE_COLOR[e.kind] || "var(--pipe)" }));
    eg.append(s("path", { d, class: "edge-hit" }));    // a wide, invisible line: easy to point at
    edgesG.append(eg);
  }
  const nodesG = s("g"), pinsG = s("g", { class: "pins" });   // pins on top of everything: always there to click
  for (const ln of lay.children) {
    const n = byId[ln.id];
    const ng = s("g", { class: `node k-${n.kind}`, transform: `translate(${ln.x},${ln.y})`, "data-id": n.id,
                        "data-turn": ln.turn ? `${ln.turn.flow} ${ln.turn.stem}` : null,
                        // pressed and let go over the same part, even if it was drawn again in between, is a click
                        onpointerdown: (ev) => {      // pressed and let go over the same part, even if drawn again between, is a click
                          if (ev.target.closest(".sys-btn") || ev.target.closest("[data-act]")) return;
                          partDown(ev, n);                // a drag, or a click (interact.js)
                        },
                        ondblclick: (ev) => { if (n.kind === "system") { ev.stopPropagation(); S.toggleSystem?.(n.label); } } });
    ng.append(((sd && SD_DRAW[n.kind]) || DRAW[n.kind] || drawCloud)(n, ln.width, ln.height, ln));
    const pid = pinId(n.id, n);                       // (a system's box and its open outline share one)
    if (S.pins?.[pid]) pinsG.append(pinMark(pid, ln.x + ln.width - 4, ln.y - 6, undefined, n.kind));   // (its kind: hidden with it, flows only)
    for (const lb of ln.labels || []) {
      // the text from this tick's data, not the layout's: positions are kept, readings move on
      const fresh = labelLines(n);
      const lines = fresh.length ? fresh : lb.text.split("\n");
      lines.forEach((t, i) => {
        const cx = lb.x + lb.width / 2, y = lb.y + 13 + i * 16;
        if (n.sd) { sdLabel(ng, n, t, i, cx, y); return; }
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
  pinsG.append(...hullPins);
  vp.append(edgesG, nodesG, ...(sd ? [sdLoopMarkers(g, lay)] : []), pinsG);
  svg.replaceChildren(vp);
  svg.classList.toggle("sd", sd);
  applyView(svg);
  if (S.hl) highlightLoop(S.hl);
  if (sd && S.hlCausal) sdApply(S.hlCausal);
  if (S.hoverKey || S.selKey) trace(S.hoverKey || S.selKey);   // a redraw keeps the line being followed
  markInteraction(svg);                                // the chosen parts, the lines waiting for libavoid
  markProposed(svg, g);                                // a proposal drawn: its new and changed parts (every redraw)
}

/* a standalone copy of the diagram: every computed style written inline, framed to the layout */

/* the side panel, hidden by clicking the diagram's background (and shown again the same way);
   remembered in this browser */
function sideHidden() {
  try { return localStorage.getItem("ergostat.side") === "hidden"; } catch (e) { return false; }
}
function toggleSide() {
  const d = document.querySelector(".diagram");
  if (!d) return;
  if (document.body.classList.contains("split-on")) { d.classList.toggle("side-shown"); return; }   // split: over the pane (split.js)
  const hide = !d.classList.contains("side-hidden");
  d.classList.toggle("side-hidden", hide);
  try { localStorage.setItem("ergostat.side", hide ? "hidden" : "shown"); } catch (e) { /* not remembered */ }
}

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
  svg.addEventListener("wheel", (ev) => {      // like a map: scroll pans; Command+scroll or a pinch (Ctrl+wheel) zooms at the pointer
    ev.preventDefault();
    const r = svg.getBoundingClientRect();
    const unit = ev.deltaMode === 1 ? 16 : ev.deltaMode === 2 ? r.height : 1;   // lines or pages, as pixels
    const dx = ev.deltaX * unit, dy = ev.deltaY * unit;
    if (!ev.ctrlKey && !ev.metaKey) { S.view.x -= dx; S.view.y -= dy; applyView(svg); return; }
    const mx = ev.clientX - r.left, my = ev.clientY - r.top;
    const f = Math.exp(-dy * (ev.ctrlKey ? 0.01 : 0.003));      // a pinch sends small deltas; Command+scroll larger ones
    const k = Math.max(0.15, Math.min(4, S.view.k * f));
    S.view.x = mx - ((mx - S.view.x) * k) / S.view.k;
    S.view.y = my - ((my - S.view.y) * k) / S.view.k;
    S.view.k = k;
    applyView(svg);
  }, { passive: false });
  svg.addEventListener("pointerdown", () => { S.pressed = true; }, true);      // held: no redraw until it is let go
  interactions(svg);                                   // parts and systems dragged, parts chosen (interact.js)
  window.addEventListener("pointerup", () => { S.pressed = false; }, true);
  svg.addEventListener("pointerup", (ev) => {
    const was = S.downOn;
    S.downOn = null;
    const under = document.elementFromPoint(ev.clientX, ev.clientY)?.closest(".node");
    if (!was || !under || under.dataset.id !== was || ev.target.closest?.(".sys-btn")) return;
    const n = S.graph?.nodes.find((x) => x.id === was);
    if (!n || (n.kind === "cloud" && !n.beyond)) return;
    const orig = n.orig && S.graph.nodes.find((x) => x.id === n.orig);    // a shadow of a part drawn here too: that part's panel
    if (orig) { chooseShape(n.id); openNode(orig); }               // (what it is chosen: interact.js)
    else if (n.kind === "terminal" || n.kind === "cloud") S.drill?.(n.in || ""); else { chooseShape(n.id); openNode(n); }
  });
  window.addEventListener("pointercancel", () => { S.pressed = false; }, true);
  svg.addEventListener("pointerdown", (ev) => {
    if (ev.target.closest(".node") || ev.target.closest("[data-act]")) return;   // a part, or a control drawn on the canvas
    if (ev.shiftKey || ev.metaKey) return;               // with Shift or Command it draws a box to choose with (interact.js)
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
    if (e) openEdge(e);
    else if (!$("#detail")?.hidden) closeDetail();       // the background: first it closes what is open,
    else if (S.hlCausal) sdHighlight(null);              // (or lets go of a loop still lit)
    else toggleSide();                                   // then it hides the side panel, or brings it back
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

function legend(view) {
  if (view === "dynamics") return sdLegend();
  if (view === "blocks") return blocksLegend();
  if (view === "process") return processLegend();          // (process.js)
  const row = (svgTxt, text) => [h("span", { html: `<svg width="26" height="18">${svgTxt}</svg>` }), h("span", {}, text)];
  return h("div", { class: "legend" },
    row('<rect x="2" y="2" width="22" height="14" rx="2" fill="var(--stock)" stroke="var(--stock-line)" stroke-width="2"/>', "stock: what accumulates"),
    row('<rect x="2" y="7" width="22" height="4" rx="2" fill="var(--line)"/><rect x="2" y="7" width="12" height="4" rx="2" fill="var(--ok)"/><line x1="18" x2="18" y1="4" y2="14" stroke="var(--ink)" stroke-width="1.6"/>', "its level, and the setpoint's tick"),
    row('<path d="M1 9 H25" stroke="var(--pipe)" stroke-width="7"/><path d="M1 9 H25" stroke="var(--pipe-in)" stroke-width="3"/>', "flow: moves a stock"),
    row('<path d="M5 3 L13 9 L5 15 Z M21 3 L13 9 L21 15 Z" fill="var(--valve)"/>', "valve: where an agent acts"),
    row('<path d="M13 2 L22 9 L13 16 L4 9 Z" fill="var(--panel)" stroke="var(--dist)" stroke-width="1.8"/>', "disturbance: nothing controls it"),
    (S.graph?.nodes || []).some((n) => n.kind === "auxiliary") &&
      row('<ellipse cx="13" cy="9" rx="11" ry="7" fill="var(--stock)" stroke="var(--stock-line)" stroke-width="1.6"/>', "auxiliary: no memory, determined at each moment by others (a score, a ratio)"),
    row('<circle cx="13" cy="9" r="7" fill="var(--sensor)" stroke="var(--sensor-line)" stroke-width="1.8"/>', "sensor: measures"),
    row('<rect x="2" y="2" width="22" height="14" rx="4" fill="var(--ctl)" stroke="var(--ctl-line)" stroke-width="1.8"/>', "controller: decides, to hold a setpoint; Σ is where it compares: e = r − y"),
    Object.values(S.graph?.loops || {}).some((l) => l.openLoop) &&
      row('<circle cx="13" cy="9" r="7" fill="var(--panel)" stroke="var(--ctl-line)" stroke-width="1.6"/><path d="M13,9 v-5 M13,9 l3,2" stroke="var(--ctl-line)" stroke-width="1.4" stroke-linecap="round"/>', "with a clock: an open loop (acts on time, reads nothing)"),
    (S.graph?.nodes || []).some((n) => n.kind === "system") &&
      row('<rect x="2" y="2" width="22" height="14" rx="4" fill="var(--panel)" stroke="var(--system-line)" stroke-width="1.8"/><rect x="0" y="6" width="4" height="4" fill="var(--panel)" stroke="var(--system-line)"/>', "a system as one part: its ports are what crosses its edge (Open draws its parts in place; Into draws it alone)"),
    (S.graph?.nodes || []).some((n) => n.kind === "terminal") &&
      row('<rect x="2" y="3" width="22" height="12" rx="6" fill="var(--bg)" stroke="var(--system-line)" stroke-dasharray="3 2"/>', "outside this system: what its edge reaches (click to go there)"),
    row('<path d="M1 9 H20" stroke="var(--sensor-line)" stroke-width="1.6" stroke-dasharray="4 3"/><path d="M18 5 L25 9 L18 13 Z" fill="var(--sensor-line)"/>', "information link, measurement: a sensor reads"),
    row('<path d="M1 9 H20" stroke="var(--sensor-line)" stroke-width="1.6"/><path d="M18 5 L25 9 L18 13 Z" fill="var(--sensor-line)"/>', "information link, feedback: the reading goes to the controller"),
    row('<path d="M1 9 H20" stroke="var(--ctl-line)" stroke-width="1.8"/><path d="M18 5 L25 9 L18 13 Z" fill="var(--ctl-line)"/>', "information link, control action: the controller opens a valve"),
    (S.graph?.edges || []).some((e) => e.kind === "influence") &&
      row('<path d="M1 9 H20" stroke="var(--dist)" stroke-width="1.6" stroke-dasharray="7 4"/><path d="M18 5 L25 9 L18 13 Z" fill="var(--dist)"/>', "information link, influence: a flow's rate follows this (driven-by)"),
    row('<path d="M1 9 H25" stroke="var(--bad)" stroke-width="2"/>', "a loop off: its lines in red when pointed at in the list (amber: open)"),
    h("span", { class: "sym" }, "H A P"), h("span", { class: "kinds" }, RUNG_NAMES.map((k, i) => h("span", {}, `${RUNG_LETTER[i]} ${k}`))));
}

async function pageDiagram(main, q) {
  // the system dynamics view is the first; "control", its old name, still reaches it
  if (q.get("view") === "wiring") {                             // the wiring the process map replaced: its address reaches it
    q.set("view", "process");
    replaceRoute("/diagram?" + q.toString());
  }
  const view = !q.get("view") || q.get("view") === "control" ? "dynamics" : q.get("view");
  // the Process view's own: which kinds, states or events, the paths slider; counts or times (the page's)
  const pq = { kinds: q.get("kinds") || "", by: q.get("by") || "", paths: q.get("paths") || "", show: q.get("show") || "" };
  S.pmShow = pq.show;
  const system = q.get("system") || "";
  const around = q.get("around") || "";
  const openQ = q.has("open") ? q.get("open") : null;          // the systems opened; absent: the server's default
  const proposal = view !== "process" ? q.get("proposal") || "" : "";   // a change waiting, drawn as it would leave the model
  S.portAt = {}; S.portRank = {};                                 // a new view: ports face what they join here
  S.pinKey = `ergostat.pins.${S.status?.name || ""}.${view}.${system}.${around}`;   // (whatever is open: kept from systems' frames)
  S.pins = loadPins();
  S.showHulls = !around;
  const wrap = h("div", { class: "canvas-wrap" });
  const svg = s("svg", { class: "canvas" });
  const sysSel = h("select", { title: "The system drawn", "aria-label": "System", onchange: (ev) => go({ system: ev.target.value, around: "" }) }, h("option", { value: "" }, "Everything"));
  for (const name of S.status?.systems || []) sysSel.append(h("option", { value: name, selected: name === system ? "" : null }, name));
  function go(over) {
    const to = over.view || view;
    const p = new URLSearchParams({ view, system, around, ...(openQ != null ? { open: openQ } : {}), ...(to === "process" ? pq : {}),
                                    ...(proposal && to !== "process" ? { proposal } : {}), ...over });
    for (const [k, v] of [...p]) if (!v) p.delete(k);
    navigate("/diagram?" + p.toString());
  }
  S.toggleSystem = (name) => {                     // open a box in place, or close an outline back into one
    rememberAnchor(name);                          // it stays where it is on the screen (interact.js)
    const now = new Set(S.graph?.open || []);
    if (now.has(name)) { now.delete(name); for (const [k, v] of Object.entries(S.graph?.tree || {})) if (v.within === name) now.delete(k); }
    else now.add(name);
    S.graphSig = "";
    go({ open: [...now].join(",") || "-" });
  };
  S.drill = (name) => { S.graphSig = ""; S.fitted = false; go({ system: name, open: "" }); };
  const crumbs = h("span", { class: "crumbs" });
  const file = (suffix = "") => `${S.status?.name || "ergostat"}-${system || "all"}-${view}${suffix}.svg`;
  const wrapOn = () => S.wrap === true || (S.wrap == null && S.wrapAuto);
  const loopsOn = () => !document.body.classList.contains("no-loops");   // the loop markers, hidden or shown (remembered)
  const unpinAll = { label: "Unpin all parts", hint: "drag a part to pin it", onclick: () => { S.pins = {}; savePins(); S.relayout?.(); } };
  const more = menu("\u22ef", () => [
    view !== "blocks" && view !== "process" ? { label: "Wrap loops into rows", checked: wrapOn(), hint: "at the pipes between loops",
      onclick: () => { S.wrap = !wrapOn(); S.graphSig = ""; S.fitted = false; route(); } } : null,
    view === "dynamics" ? { label: "Show loop markers", checked: loopsOn(), hint: "R and B, inside each loop",
      onclick: () => { const on = !loopsOn(); document.body.classList.toggle("no-loops", !on);
                       try { localStorage.setItem("ergostat.loops", on ? "1" : "0"); } catch (e) { /* not remembered */ } } } : null,
    view === "dynamics" ? { label: "Flows only", checked: document.body.classList.contains("flows-only"), hint: "the pipes, their stocks and clouds",
      onclick: () => { const on = document.body.classList.toggle("flows-only");     // a class, not a re-layout: nothing moves
                       try { localStorage.setItem("ergostat.flowsOnly", on ? "1" : "0"); } catch (e) { /* not remembered */ } } } : null,
    view !== "process" ? { label: "Colour by correspondence", checked: CORR.on, hint: "or hold C",
      onclick: () => corrSet(!CORR.on) } : null,
    ...(view === "process" ? [...pmKindItems(), { sep: true }, unpinAll] : [
      { label: "Open all systems", onclick: () => { S.graphSig = ""; go({ open: "*" }); } },
      { label: "Close all systems", onclick: () => { S.graphSig = ""; go({ open: "-" }); } },
      { sep: true },
      unpinAll]),
  ], { cls: "dots", title: view === "process" ? "More: which kinds of item, unpin" : "More: wrap, open or close every system, unpin" });
  function pmKindItems() {                         // the kinds drawn: the system's by default, any of them by choice
    const g = S.graph?.kind === "process" ? S.graph : null;
    if (!g) return [];
    const now = new Set(g.kinds.map((k) => k.name));
    const toggle = (name) => {
      const next = (g.offered || []).map((k) => k.name).filter((k) => (k === name ? !now.has(k) : now.has(k)));
      const same = next.length === (g.default || []).length && next.every((k) => (g.default || []).includes(k));
      S.graphSig = ""; S.fitted = false;
      go({ kinds: same ? "" : next.join(",") || name });
    };
    return [h("div", { class: "menu-label" }, "Kinds of item"),
      ...(g.offered || []).map((k) => ({ label: k.name, checked: now.has(k.name), hint: k.system || "", onclick: () => toggle(k.name) })),
      pq.kinds ? { label: "The system's kinds", hint: "as at first", onclick: () => { S.graphSig = ""; S.fitted = false; go({ kinds: "" }); } } : null];
  }
  // the Process view's controls, in the view bar: states or events, counts or times, the paths slider
  const pmBar = view !== "process" ? [] : (() => {
    const by = pq.by || "", show = S.pmShow || "counts";
    const paths = h("input", { type: "range", min: 0, max: 100, step: 5, value: pq.paths || 0, class: "pm-paths", "aria-label": "Paths shown",
                               title: "Hide lines rarer than this share of their kind's most frequent" });
    const pathsWord = h("span", { class: "muted small pm-paths-word" }, `paths ≥ ${pq.paths || 0}%`);
    paths.addEventListener("input", () => { pathsWord.textContent = `paths ≥ ${paths.value}%`; });
    paths.addEventListener("change", () => { S.fitted = false; go({ paths: paths.value === "0" ? "" : paths.value }); });
    const seg = (label, items) => h("span", { class: "seg", role: "group", "aria-label": label }, ...items.map(([on, text, title, fn]) =>
      h("button", { class: on ? "on" : "", title, onclick: fn }, text)));
    const isBy = (x) => (by || S.graph?.by) === x;
    const bySeg = seg("Nodes", [[isBy("states"), "States", "Nodes are the states items entered (where the kind declares states)", () => { S.fitted = false; go({ by: "states" }); }],
                                [isBy("events"), "Events", "Nodes are the event types about items", () => { S.fitted = false; go({ by: "events" }); }]]);
    bySeg.dataset.pm = "by";
    const showSeg = seg("Numbers", [[show !== "times", "Counts", "Each line: how many times", () => { S.pmShow = pq.show = ""; S.graphSig = ""; go({ show: "" }); }],
                                    [show === "times", "Times", "Each line: the median time between its ends", () => { S.pmShow = pq.show = "times"; S.graphSig = ""; go({ show: "times" }); }]]);
    return [h("span", { class: "sep" }), bySeg, h("span", { class: "sep" }), showSeg, h("span", { class: "sep" }), paths, pathsWord];
  })();
  const toolbar = h("div", { class: "toolbar" },
    h("span", { class: "seg", role: "group", "aria-label": "View" },
      h("button", { class: view === "dynamics" ? "on" : "", title: "The stock-and-flow diagram, as system dynamics draws it",
                    onclick: () => go({ view: "dynamics" }) }, "Dynamics"),
      h("button", { class: view === "blocks" ? "on" : "", title: "The control system as a block diagram", onclick: () => go({ view: "blocks" }) }, "Blocks"),
      h("button", { class: view === "process" ? "on" : "", title: "The process map: how items really moved, from the record (a directly-follows graph per kind)",
                    onclick: () => go({ view: "process" }) }, "Process")),
    h("span", { class: "sep" }),
    sysSel, crumbs, ...pmBar,
    around ? h("span", { class: "around" }, "around ", h("b", {}, around), " ", h("button", { class: "ghost", title: "Draw everything again", "aria-label": "Clear", onclick: () => go({ around: "" }) }, "\u00d7")) : null,
    more);
  const zoom = h("div", { class: "zoom" },
    h("span", { id: "panhint", class: "panhint", hidden: true, title: "Drag to pan, or fit to see it whole" }, "More beyond the edge"),
    h("button", { class: "z", title: "Zoom out", onclick: () => { S.view.k /= 1.2; applyView(svg); } }, "\u2212"),
    h("button", { title: "Show it whole", onclick: () => fit(svg, S.layout) }, "Fit"),
    h("button", { class: "z", title: "Zoom in", onclick: () => { S.view.k *= 1.2; applyView(svg); } }, "+"),
    h("span", { class: "sep" }),
    menu("Export", [
      { label: "SVG", hint: "as drawn", onclick: () => exportSvg(svg, file()) },
      { label: "Design SVG", hint: "no live values", onclick: () => exportSvg(svg, file("-design"), true) },
      { label: "PNG", hint: "twice the size", onclick: () => exportPng(svg, file()) },
    ], { right: true, up: true, title: "Save the diagram as a file" }));
  wrap.append(svg, toolbar, zoom);
  if (typeof splitGrips === "function") splitGrips(wrap);         // a second pane, dragged in from an edge (split.js)
  S.legendEl = legend(view);   // blocks, process and dynamics each read differently
  const side = h("div", { class: "side" });
  const shell = h("div", { class: "diagram" + (sideHidden() ? " side-hidden" : "") }, wrap, side);
  main.append(shell);
  panZoom(svg);
  S.graphSig = ""; S.fitted = false;
  wrap.append(h("div", { class: "empty loading" }, "Loading\u2026"));
  let fails = 0;

  async function tick() {
    let g;
    // the blocks view draws every loop, each in its system's outline: it asks for everything opened
    const openArg = openQ != null && view !== "process" ? { open: openQ } : {};
    S.graphQ = { system, around, ...openArg };      // (the other view's answer is asked the same: interact.js)
    const pmArg = view !== "process" ? {} : Object.fromEntries(["kinds", "by", "paths"].filter((k) => pq[k]).map((k) => [k, pq[k]]));
    const ask = { view, system, around, ...openArg, ...pmArg, ...(proposal ? { proposal } : {}) }, key = JSON.stringify(ask);
    if (!SNAP) ask.have = (S.held?.key === key && S.held.hash) || "-";   // the structure it holds: then only the values come
    const t0 = performance.now();
    try { g = await api("graph", ask); fails = 0; }
    catch (e) {
      if (++fails >= 3) { wrap.querySelector(".empty")?.remove(); wrap.append(h("div", { class: "empty" }, SNAP ? "This view is not in the snapshot; the whole system and each system are." : "The server is not answering. Is ergostat still running?")); }
      return;
    }
    // the next ask: every 2.5s, later when an answer is slow (four times as long as it took, at most a minute)
    const next = Math.min(60000, Math.max(2500, 4 * (performance.now() - t0)));
    if (g.same) {
      if (S.held?.key !== key || S.held.hash !== g.same) { S.held = null; return { wait: 0 }; }   // (not the one held: ask whole)
      g = withValues(S.held.base, g);
    } else if (g.structure) {
      S.held = { key, hash: g.structure };
      delete g.structure;
      S.held.base = structuredClone(g);
    }
    await show(g);
    return { wait: next };
  }
  async function show(g) {
    wrap.querySelector(".loading")?.remove();
    S.graph = g;
    proposedBanner(wrap, g, proposal, go);
    if (g.tree && !sysSel.dataset.tree) {            // the picker as the tree it is: each system under the one it is within
      sysSel.dataset.tree = "1";
      const kids = (p) => Object.keys(g.tree).filter((x) => (g.tree[x].within || null) === p).sort();
      const opts = [h("option", { value: "" }, "Everything")];
      const add = (p, depth) => { for (const x of kids(p)) { opts.push(h("option", { value: x, selected: x === system ? "" : null }, "\u00a0\u00a0".repeat(depth) + x)); add(x, depth + 1); } };
      add(null, 0);
      sysSel.replaceChildren(...opts);
    }
    if (g.tree && system) {                          // where this system sits: each level up, one click away
      const up = []; let x = system;
      while (x) { up.unshift(x); x = g.tree[x]?.within; }
      patch(crumbs, h("a", { href: "#", onclick: (ev) => { ev.preventDefault(); S.drill(""); } }, "Everything"),
        ...up.flatMap((x, i) => [" › ", i < up.length - 1 ? h("a", { href: "#", onclick: (ev) => { ev.preventDefault(); S.drill(x); } }, x) : h("b", {}, x)]));
    } else patch(crumbs);
    if (view === "process") {
      wrap.querySelector(".empty")?.remove();
      if (!g.nodes.length) {
        svg.replaceChildren();
        S.layout = null; S.graphSig = "";
        wrap.append(h("div", { class: "empty" }, !g.kinds.length ? "No kinds of item here: the process map draws how items moved."
          : `Nothing on the record in the window for ${g.kinds.map((k) => k.name).join(", ")}.`));
      } else if (!S.pressed) {
        await drawProcessView(svg, g);
        if (!S.fitted) { fit(svg, S.layout, true); S.fitted = true; }
      }
      for (const b of toolbar.querySelectorAll('[data-pm="by"] button')) b.classList.toggle("on", b.textContent.toLowerCase() === g.by);
      renderSide(side, g, "process");
      return;
    }
    if (view === "blocks") {
      wrap.querySelector(".empty")?.remove();
      if (!g.nodes.length) {
        svg.replaceChildren();
        wrap.append(h("div", { class: "empty" }, "No control system here: no goal, and no block that acts."));
      } else if (!S.pressed) {
        await drawBlocksView(svg, g);
        if (S.anchor && S.anchored) S.fitted = true;  // a system just opened or closed: the view stays as it was
        S.anchor = null; S.anchored = false;
        if (!S.fitted) { fit(svg, S.layout, true); S.fitted = true; }
      }
      renderSide(side, g, "blocks");
      if (typeof toolArrived === "function") toolArrived();    // a model tool asked for from the Model page (review.js)
      return;
    }
    if (!g.nodes.length) {
      svg.replaceChildren();
      wrap.querySelector(".empty")?.remove();
      wrap.append(h("div", { class: "empty" }, "Nothing to draw: the model is empty."));
      renderSide(side, g, view);
      return;
    }
    wrap.querySelector(".empty")?.remove();
    const sg = sig(g);
    if (sg !== S.graphSig) {
      const r = svg.getBoundingClientRect();
      const aspect = r.width && r.height ? r.width / Math.max(r.height - 80, 200) : 1.6;
      const asp = aspect;
      // a chain of loops far wider than the window is folded at the pipes between loops, unless told not to
      let lay = await layoutGraph(g, asp, S.wrap === true && (g.kind === "control" || g.kind === "dynamics"));
      S.wrapAuto = false;
      // (kept only when it fits the window clearly better: a chain wrapped reads worse than one row that fits about as well)
      const fitOf = (l) => Math.min((r.width - 40) / l.width, (r.height - 90) / l.height);
      if (S.wrap == null && (g.kind === "control" || g.kind === "dynamics") && couplings(g).length && lay.width / lay.height > 2 * asp) {
        const rows = await layoutGraph(g, asp, true, 0, { dry: true });     // (tried: routed only if kept)
        if (fitOf(rows) >= WRAP_GAIN * fitOf(lay)) { lay = rows; S.wrapAuto = true; avoidStart(lay, g); }
      }
      S.layout = lay;
      S.graphSig = sg;
    } else {
      // same structure: keep positions, redraw with new values (label texts may change length slightly)
    }
    if (S.anchor && S.anchored) S.fitted = true;      // a system just opened or closed: the view stays as it was
    S.anchor = null; S.anchored = false;
    if (S.pressed) return;                             // mid-click: a redraw now would swallow it; the next tick draws
    drawGraph(svg, g, S.layout);
    if (!S.fitted) { fit(svg, S.layout, true); S.fitted = true; }
    renderSide(side, g, view);
    if (typeof toolArrived === "function") toolArrived();
  }
  S.relayout = () => { S.graphSig = ""; return tick(); };      // after a part is pinned or unpinned
  S.redrawSide = () => { if (S.graph) renderSide(side, S.graph, view); };       // the parts chosen changed (charts.js)
  S.redraw = () => { if (!S.pressed && !S.nodeDrag && !S.hullDrag && S.layout) (S.graph?.kind === "process" ? pmDraw : drawGraph)(svg, S.graph, S.layout); };   // libavoid's lines came
  const first = await tick();
  S.timer = poll(tick, 2500, shell, first);
}

/* a change waiting, drawn as it would leave the model (/api/graph?proposal=ID): the shapes of the parts it adds dashed
   and tinted, those it changes or renames dashed, and what it takes away named in a banner, with the way back to the
   model as it is */
function markProposed(svg, g) {
  const pr = g?.proposed, corr = g?.corr?.parts;
  if (!pr || !corr) return;
  const mark = (refs, cls) => {
    for (const r of refs || []) for (const id of corr[r] || []) for (const el of svg.querySelectorAll(`[data-id="${CSS.escape(id)}"]`)) el.classList.add(cls);
  };
  mark(pr.changed, "proposed-changed");
  mark(pr.added, "proposed-new");
}
function proposedBanner(wrap, g, proposal, go) {
  wrap.querySelector(".proposed-banner")?.remove();
  if (!proposal) return;
  const pr = g?.proposed;
  const names = (xs) => (xs || []).map((r) => r.split(".").slice(1).join(".")).join(", ");
  wrap.append(h("div", { class: "proposed-banner", role: "status" },
    g?.error ? h("span", { class: "s-open" }, g.error)
      : h("span", {}, h("b", {}, "Proposed, not written: "), pr?.title || proposal,
          h("span", { class: "muted small" }, ` — new parts dashed and tinted (${(pr?.added || []).length}), changed or renamed dashed (${(pr?.changed || []).length})`),
          (pr?.removed || []).length ? h("div", { class: "small" }, h("span", { class: "muted" }, "taken away: "), names(pr.removed)) : null,
          (pr?.renamed || []).length ? h("div", { class: "small" }, h("span", { class: "muted" }, "renamed: "), pr.renamed.map((x) => x.split(" → ").map((r) => r.split(".").slice(1).join(".")).join(" → ")).join(", ")) : null),
    " ", h("button", { class: "ghost", onclick: () => { S.graphSig = ""; S.fitted = false; go({ proposal: "" }); } }, "The model as it is")));
}

/* an answer of values only (graph_poll.py) put into a copy of the whole answer the page holds: every part (each object
   below the top), walked in the order the server walked it (keys sorted; not into a value), given its values: the
   answer a whole one would have been */
function withValues(base, v) {
  const g = structuredClone(base), keys = new Set(v.keys), top = new Set(v.top), vals = v.values;
  let i = 0, j = 0;
  const walk = (x, root) => {
    if (Array.isArray(x)) { for (const y of x) walk(y, false); return; }
    if (!x || typeof x !== "object") return;
    if (!root) {
      const mine = j < vals.length && vals[j][0] === i ? vals[j++][1] : null;
      i++;
      for (const k of Object.keys(x)) if (keys.has(k) && !(mine && k in mine)) delete x[k];
      if (mine) Object.assign(x, mine);
    }
    for (const k of Object.keys(x).sort()) if (!(root ? top : keys).has(k)) walk(x[k], false);
  };
  walk(g, true);
  for (const k of top) if (k in v) g[k] = v[k];
  return g;
}

/* the legend: open the first time, then as the reader left it (remembered in this browser) */
function legendOpen() { try { return localStorage.getItem("ergostat.legend") !== "closed"; } catch (e) { return true; } }
function legendBox(view) {
  const d = h("details", { class: "legend-box", open: legendOpen() ? "" : null }, h("summary", {}, "How to read it"), legend(view));
  d.addEventListener("toggle", () => { try { localStorage.setItem("ergostat.legend", d.open ? "open" : "closed"); } catch (e) { /* not remembered */ } });
  try { if (!localStorage.getItem("ergostat.legend")) localStorage.setItem("ergostat.legend", "closed"); } catch (e) { /* not remembered */ }
  return d;
}

/* what waits on the owner (SPEC §12o), answered where it is listed: an event from the owner, as everywhere */
function inboxAnswer(a) {
  if (SNAP || S.at) return null;
  const said = h("span", { class: "note", "aria-live": "polite" });
  const n = a.answer.includes("done") ? h("input", { type: "number", min: "0", step: "any", placeholder: "how many", "aria-label": "How much was done" }) : null;
  const go = (verb) => h("button", { class: verb === "deny" ? "ghost" : "", "data-verb": verb, onclick: async () => {
    for (const b of row.querySelectorAll("button")) b.disabled = true;
    try { said.textContent = ` ${(await apiPost(`inbox/${encodeURIComponent(a.what)}/${verb}`, n?.value ? { n: n.value } : {})).said}`; refreshHeader(); }
    catch (e) { said.textContent = ` ${e.message}`; for (const b of row.querySelectorAll("button")) b.disabled = false; }
  } }, { approve: "Approve", deny: "Deny", done: "Done" }[verb]);
  const row = h("div", { class: "row inbox-act" }, n, ...a.answer.map(go), said);
  return row;
}

function renderSide(side, g, view) {
  const st = S.status || { attention: [], loops: {} };
  const all = g.attention || st.attention;           // from the same snapshot as the diagram beside it
  const problems = all.filter((a) => a.level !== "hint"), hints = all.filter((a) => a.level === "hint");
  // built aside and patched in: a refresh touches only what changed, and what is open or scrolled stays so
  const out = side, panel = h("div");
  side = panel;
  if (S.status && !S.status.running && !S.at && !SNAP) {
    const last = Math.max(0, ...Object.values(g.loops || {}).map((l) => (S.status.loops[l.controller || ""] || {}).last_read || 0),
                          ...Object.values(S.status.loops || {}).map((l) => l.last_read || 0));
    side.append(h("div", { class: "att" }, h("div", {}, h("b", { class: "lvl-warn" }, "Not running. "),
      last ? `These are the last readings, from ${ago(last)}.` : "Nothing has been measured.")));
  }
  const charts = view === "dynamics" ? sideCharts(out) : null;      // charts.js: the parts chosen, at the top
  if (charts && S.sel?.size) side.append(live(charts));
  side.append(h("h3", {}, "Needs attention", problems.length ? h("span", { class: "muted" }, ` ${problems.length}`) : null));
  const att = h("div", { class: "att" });
  if (!problems.length) att.append(h("div", { class: "none" }, "Nothing needs attention."));
  const MAX = 6;
  // a command the CLI would suggest becomes a link to the same view here
  const linked = (says) => {
    const m = /ergostat event --type (\S+?)\)?$/.exec(says);
    return m ? [op(says.slice(0, m.index)), h("a", { href: `/record?type=${encodeURIComponent(m[1])}` }, `the record of ${m[1]}`), says.endsWith(")") ? ")" : ""] : op(says);
  };
  for (const a of problems.slice(0, MAX)) {
    const what = h("b", { class: a.level === "bad" ? "lvl-bad" : "lvl-warn" }, a.what);   // an item's: a link to its page
    const href = a.link || (a.item ? `/item/${encodeURIComponent(a.item)}` : null);
    att.append(h("div", a.answer ? { "data-inbox": a.what } : {}, href ? h("a", { href, class: "plain" }, what) : what, " ",
      linked(a.answer ? a.says.replace(/\. ergostat inbox .*$/, "") : a.says), a.answer ? inboxAnswer(a) : null));
  }
  if (problems.length > MAX) att.append(h("div", { class: "more" }, `${problems.length - MAX} more on `, h("a", { href: "/loops" }, "Loops"), " and ", h("a", { href: "/model" }, "Model"), "."));
  side.append(att);
  if (hints.length) {
    // open when a loop is off: then the suggestions are the diagnosis, not an aside
    // (the moment drawn, not now; and once the reader opens or closes them, as they left them)
    const anyOff = Object.values(g.loops || {}).some((l) => l.status === "off");
    const open = S.suggestOpen ?? anyOff;
    const d = h("details", { class: "suggest", open: open ? "" : null },
                h("summary", { onclick: (ev) => { S.suggestOpen = !ev.currentTarget.parentElement.open; } }, `Suggestions (${hints.length})`));   // the reader's own choice
    for (const a of hints) {
      const loop = /^loop (\S+)/.exec(a.says)?.[1];
      d.append(h("div", { class: "hint" }, h("b", {}, a.what), " ", op(a.says), " ",
        loop ? h("a", { href: "#", onclick: (ev) => { ev.preventDefault(); openLoop(loop); } }, "Evidence") : null));
    }
    side.append(d);
  }
  if (charts && !S.sel?.size) side.append(live(charts));               // or the ones charted last
  const loops = Object.entries(g.loops || {});
  if (view === "dynamics") sdLoopList(side, g);
  else if (view === "control" || view === "blocks") {
    side.append(h("h3", {}, "Loops", h("span", { class: "muted" }, ` ${loops.length}`)));
    if (!loops.length) side.append(h("div", { class: "muted" }, "No loops in view."));
    const rank = { off: 0, open: 1, unknown: 2, holding: 3 };       // the ones that need someone first
    for (const [name, lp] of loops.sort((a, b) => (rank[a[1].status] ?? 2) - (rank[b[1].status] ?? 2))) {
      side.append(h("div", { class: "looprow", "data-loop": name,
                              onmouseenter: () => highlightLoop(name), onmouseleave: () => highlightLoop(null),
                              onclick: () => { choose(g.corr?.loops?.[name] || []); openLoop(name); } },
        h("b", {}, name), exceptional(lp.status) ? statusEl(lp.status) : h("span"),
        h("div", { class: "sub" }, `${lp.stock} ${fmt(lp.value)}, setpoint ${op(lp.setpoint)}${lp.band || ""}`)));
    }
  } else if (view === "process") pmSide(side, g);          // (process.js)
  if (st.changes?.length) {
    const last = st.changes[st.changes.length - 1];
    const n = (c) => c.added.length + c.removed.length + c.changed.length;
    const d = h("details", { class: "changes" }, h("summary", {}, `Edited ${ago(last.time)}`,
      h("span", { class: "muted" }, `, ${n(last)} part${n(last) === 1 ? "" : "s"}${st.changes.length > 1 ? `, ${st.changes.length} edits` : ""}`)));
    for (const c of st.changes.slice().reverse()) {
      const what = [...c.added.map((x) => "+" + x), ...c.removed.map((x) => "\u2212" + x), ...c.changed.map((x) => "~" + x)];
      d.append(h("div", { class: "change" }, h("span", { class: "muted" }, ago(c.time)), " ", h("span", { class: "what" }, what.join("  "))));
    }
    side.append(h("h3", {}, "The model"), d);
  }
  side.append(legendBox(view));
  patch(out, [...panel.childNodes]);
}

try { if (localStorage.getItem("ergostat.loops") === "0") document.body.classList.add("no-loops"); } catch (e) { /* shown */ }
try { if (localStorage.getItem("ergostat.flowsOnly") === "1") document.body.classList.add("flows-only"); } catch (e) { /* all shown */ }
