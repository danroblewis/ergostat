/* a flow between one stock and a cloud is that stock's satellite (docs/layout-rules.md: flow-excursion,
   valve-between-ends, cloud-by-valve). Its valve and its cloud are left out of ELK's layout: the stock is given to
   ELK as a box big enough to hold them on the side they belong (a drain below it, or right of it; an inflow above
   it, or left of it), and the links into or out of the valve are left out of ELK's layout, so they never pull the
   valve (or its stock) away from its pipe: they are routed to it wherever it sits. After the layout the stock goes back to its size inside that box, and the valve
   and the cloud are put in the room kept for them: the valve on a short straight pipe out of the stock, the cloud
   just beyond. The router then turns the valve to its pipe (avoid.js) */
"use strict";

const SAT_GAP = 34;                                     // stock to valve, valve to cloud (as seatCloudFlows')

/* which flows are satellites, and on which side of their stock: {valve: {stock, cloud, out, side}} */
function satellitePlan(g) {
  const byId = Object.fromEntries(g.nodes.map((n) => [n.id, n]));
  const home = (id) => (byId[id]?.systems || [])[0] || null;
  const pipes = g.edges.filter((e) => e.kind === "pipe");
  const flowNode = (id) => ["valve", "disturbance"].includes(byId[id]?.kind);
  // a stock's flows to or from other stocks (or systems): the sides they leave free
  const chained = (st, out) => pipes.some((e) => (out ? e.source === st : e.target === st) && flowNode(out ? e.target : e.source) &&
    pipes.some((f) => (out ? f.source === e.target : f.target === e.source) && !["cloud"].includes(byId[out ? f.target : f.source]?.kind)));
  const plan = {}, taken = {};
  for (const n of g.nodes) {
    if (!flowNode(n.id) || S.pins?.[n.id]) continue;
    const d = drainOf(g, n.id);                         // (places.js)
    if (!d || S.pins?.[d.cloud] || S.pins?.[d.stock] || home(n.id) !== home(d.stock) || home(d.cloud) !== home(d.stock)) continue;
    const sides = d.out ? ["down", ...(chained(d.stock, true) ? [] : ["right"])] : ["up", ...(chained(d.stock, false) ? [] : ["left"])];
    const used = (taken[d.stock] ||= new Set());
    const side = sides.find((s) => !used.has(s));
    if (!side) continue;                                // (more than the sides hold: ELK places the rest)
    used.add(side);
    plan[n.id] = { ...d, side };
  }
  return plan;
}

/* the ELK graph's children and edges with the satellites taken out and their stocks grown to hold them; returns
   what placeSatellites needs to put them back */
function reserveSatellites(children, edges, plan, g) {
  const seeking = new Set(g.edges.filter((e) => e.goalSeeking).map((e) => e.id));
  const node = Object.fromEntries(children.map((c) => [c.id, c]));
  const kept = {};                                       // stock -> {w, h, dx, dy, sats: [{valve, cloud, side, out}]}
  const removed = {};
  for (const [v, p] of Object.entries(plan)) {
    const st = node[p.stock], vn = node[v], cn = node[p.cloud];
    if (!st || !vn || !cn) continue;
    const k = (kept[p.stock] ||= { w: st.width, h: st.height, sats: [] });
    k.sats.push({ ...p, valve: v });
    removed[v] = vn; removed[p.cloud] = cn;
  }
  for (const [sid, k] of Object.entries(kept)) {
    const st = node[sid];
    const rs = [[-k.w / 2, -k.h / 2, k.w / 2, k.h / 2]];
    for (const s of k.sats) for (const r of satelliteBoxes(k, s, removed[s.valve], removed[s.cloud])) rs.push(r);
    const x0 = Math.min(...rs.map((r) => r[0])), y0 = Math.min(...rs.map((r) => r[1]));
    const x1 = Math.max(...rs.map((r) => r[2])), y1 = Math.max(...rs.map((r) => r[3]));
    k.dx = -k.w / 2 - x0; k.dy = -k.h / 2 - y0;          // the stock's corner inside the box kept
    st.width = x1 - x0; st.height = y1 - y0;
    // its pipes to and from other stocks meet the box level with the stock itself, not the box's middle: what
    // they join lines up with the stock
    st.layoutOptions = { ...(st.layoutOptions || {}), "elk.portConstraints": "FIXED_POS" };
    st.ports = [{ id: sid + ":in", width: 1, height: 1, x: 0, y: k.dy + k.h / 2, layoutOptions: { "elk.port.side": "WEST" } },
                { id: sid + ":out", width: 1, height: 1, x: st.width - 1, y: k.dy + k.h / 2, layoutOptions: { "elk.port.side": "EAST" } }];
  }
  const out = children.filter((c) => !removed[c.id]);
  const owner = (end) => end.replace(/:(in|out|ctl|sense)$/, "");
  const stockOf = Object.fromEntries(Object.entries(plan).filter(([v]) => removed[v]).flatMap(([v, p]) => [[v, p.stock], [p.cloud, p.stock]]));
  const keptEdges = [], dropped = [];
  const pipe = (e) => (e.layoutOptions || {})["elk.layered.priority.straightness"] === "100";
  for (const e of edges) {
    const s = owner(e.sources[0]), t = owner(e.targets[0]);
    if (!stockOf[s] && !stockOf[t]) {
      if (pipe(e) && kept[e.targets[0]]) e.targets = [e.targets[0] + ":in"];      // (a reserved stock's own ports)
      if (pipe(e) && kept[e.sources[0]]) e.sources = [e.sources[0] + ":out"];
      keptEdges.push(e);
      continue;
    }
    dropped.push(e.id);                                  // the pipes, and the links into or out of the valve: left out of
    // the layout (a link travels to its valve wherever it sits); but a goal's gap that drives the valve is given to
    // ELK as driving its stock, so the goal is laid out by the stock it holds, not adrift
    if (seeking.has(e.id) && !stockOf[s] !== !stockOf[t])
      keptEdges.push({ ...e, id: "sat:" + e.id, sources: [stockOf[s] || e.sources[0]], targets: [stockOf[t] || e.targets[0]], labels: undefined });
  }
  return { children: out, edges: keptEdges, kept, removed, dropped };
}

/* the boxes a satellite takes, round its stock's centre (its valve with its name, its cloud with its own) */
function satelliteBoxes(k, s, vn, cn) {
  const at = satellitePlaces(k, s, vn, cn);
  const box = (n, p) => {
    const rs = [[p.x - n.width / 2, p.y - n.height / 2, p.x + n.width / 2, p.y + n.height / 2]];
    for (const l of p.labels || []) rs.push([p.x - n.width / 2 + l.x, p.y - n.height / 2 + l.y, p.x - n.width / 2 + l.x + l.width, p.y - n.height / 2 + l.y + l.height]);
    return rs;
  };
  return [...box(vn, at.valve), ...box(cn, at.cloud)].map((r) => [r[0] - 6, r[1] - 6, r[2] + 6, r[3] + 6]);
}

/* where a satellite's valve and cloud go (their centres), round its stock's centre, with their labels (relative
   to each part's corner): a level valve's name under it, an upright one's beside it (right of it, its stem left),
   a cloud's words beyond it */
function satellitePlaces(k, s, vn, cn) {
  const dir = { down: [0, 1], up: [0, -1], right: [1, 0], left: [-1, 0] }[s.side];
  const level = dir[1] === 0;
  const reach = level ? k.w / 2 : k.h / 2;
  const vd = reach + SAT_GAP + (level ? vn.width : vn.height) / 2;
  const cd = vd + (level ? vn.width : vn.height) / 2 + SAT_GAP + (level ? cn.width : cn.height) / 2;
  const v = { x: dir[0] * vd, y: dir[1] * vd }, c = { x: dir[0] * cd, y: dir[1] * cd };
  const vl = (vn.labels || []).map((l) => ({ ...l }));
  if (vl.length) {
    const w = Math.max(...vl.map((l) => l.width)), h = vl.reduce((a, l) => a + l.height, 0);
    let y = level ? vn.height + 4 : (vn.height - h) / 2;
    for (const l of vl) { l.x = level ? (vn.width - w) / 2 + (w - l.width) / 2 : vn.width + 6; l.y = y; y += l.height; }
  }
  const cl = (cn.labels || []).map((l) => ({ ...l }));
  for (const l of cl) {                                  // beyond the cloud, away from the pipe
    if (s.side === "up") { l.x = (cn.width - l.width) / 2; l.y = -l.height - 2; }
    else if (s.side === "down") { l.x = (cn.width - l.width) / 2; l.y = cn.height + 2; }
    else if (s.side === "left") { l.x = -l.width - 4; l.y = (cn.height - l.height) / 2; }
    else { l.x = cn.width + 4; l.y = (cn.height - l.height) / 2; }
  }
  v.labels = vl; c.labels = cl;
  return { valve: v, cloud: c };
}

/* after the layout (flattened): each stock back to its size in the box kept for it, and its satellites put in the
   room kept, their lines straight until libavoid's */
function placeSatellites(lay, res) {
  if (!res || !Object.keys(res.kept).length) return;
  const box = Object.fromEntries(lay.children.map((c) => [c.id, c]));
  const at = (c) => ({ x: c.x + c.width / 2, y: c.y + c.height / 2 });
  for (const [sid, k] of Object.entries(res.kept)) {
    const st = box[sid];
    if (!st) continue;
    st.x += k.dx; st.y += k.dy; st.width = k.w; st.height = k.h;
    delete st.ports;
    const m = at(st);
    for (const s of k.sats) {
      const vn = res.removed[s.valve], cn = res.removed[s.cloud];
      const p = satellitePlaces(k, s, vn, cn);
      for (const [n, q] of [[vn, p.valve], [cn, p.cloud]]) {
        const leaf = { ...n, x: m.x + q.x - n.width / 2, y: m.y + q.y - n.height / 2, labels: q.labels, satellite: true };
        lay.children.push(leaf);
        box[leaf.id] = leaf;
      }
    }
  }
  lay.satellites = new Set(Object.values(res.kept).flatMap((k) => k.sats.map((s) => s.valve)));
  // the lines left out (and the links given to the stock instead) as straight lines between the parts, for now
  lay.edges = lay.edges.filter((e) => !e.id.startsWith("sat:"));
  const ends = res.ends || {};
  for (const id of res.dropped) {
    const [s, t] = ends[id] || [];
    if (!box[s] || !box[t]) continue;
    lay.edges.push({ id, sources: [s], targets: [t], container: "root", sections: [{ startPoint: at(box[s]), endPoint: at(box[t]), bendPoints: [] }] });
  }
}

/* a valve between two stocks (or a stock and a system) that the layout left outside the span of its two ends
   (pulled off by the goal stacked over it, laid out as one block with it): moved, with that goal, to the free place
   between its ends that makes its pipe shortest, level with one of them where it can be
   (docs/layout-rules.md: valve-between-ends, flow-excursion) */
const BETWEEN_SLACK = 30;
function centreValves(lay, g) {
  const byId = Object.fromEntries(g.nodes.map((n) => [n.id, n]));
  const box = Object.fromEntries(lay.children.map((c) => [c.id, c]));
  const home = (id) => (byId[id]?.systems || [])[0] || null;
  const mid = (c) => ({ x: c.x + c.width / 2, y: c.y + c.height / 2 });
  const moved = [];
  for (const n of g.nodes) {
    if (!["valve", "disturbance"].includes(n.kind) || S.pins?.[n.id] || lay.satellites?.has(n.id)) continue;
    const pin = g.edges.find((e) => e.kind === "pipe" && e.target === n.id), pout = g.edges.find((e) => e.kind === "pipe" && e.source === n.id);
    const v = box[n.id], A = pin && box[pin.source], B = pout && box[pout.target];
    if (!v || !A || !B || byId[A.id]?.kind === "cloud" || byId[B.id]?.kind === "cloud") continue;
    const a = mid(A), b = mid(B), m = mid(v);
    const span = { x0: Math.min(a.x, b.x) - BETWEEN_SLACK, x1: Math.max(a.x, b.x) + BETWEEN_SLACK, y0: Math.min(a.y, b.y) - BETWEEN_SLACK, y1: Math.max(a.y, b.y) + BETWEEN_SLACK };
    if (m.x >= span.x0 && m.x <= span.x1 && m.y >= span.y0 && m.y <= span.y1) continue;
    // the goal over it, that drives only it (and the desired level that feeds only that gap): it goes along
    const group = [v];
    const drive = g.edges.filter((e) => e.goalSeeking && e.target === n.id);
    const gap = drive.length === 1 && box[drive[0].source];
    if (gap && !S.pins?.[gap.id] && !g.edges.some((e) => e.goalSeeking && e.source === gap.id && e.target !== n.id)) {
      group.push(gap);
      const want = g.edges.filter((e) => e.goalSeeking && e.target === gap.id).map((e) => box[e.source])
        .find((d) => d && byId[d.id]?.role === "desired" && !S.pins?.[d.id] && g.edges.filter((e) => e.source === d.id).length === 1);
      if (want) group.push(want);
    }
    const ra = partBox(A), rb = partBox(B);
    const cands = [];
    const xs = ra.x1 < rb.x0 ? (ra.x1 + rb.x0) / 2 : rb.x1 < ra.x0 ? (rb.x1 + ra.x0) / 2 : null;
    const ys = ra.y1 < rb.y0 ? (ra.y1 + rb.y0) / 2 : rb.y1 < ra.y0 ? (rb.y1 + ra.y0) / 2 : null;
    if (xs != null) for (const y of [a.y, b.y, (a.y + b.y) / 2]) cands.push({ x: xs, y });
    if (ys != null) for (const x of [a.x, b.x, (a.x + b.x) / 2]) cands.push({ x, y: ys });
    // (a flow back up a chain: in a lane under or over it, between its two stocks)
    if (xs != null) for (let k = 0; k < 6; k++)
      cands.push({ x: xs, y: Math.max(ra.y1, rb.y1) + 40 + 36 * k }, { x: xs, y: Math.min(ra.y0, rb.y0) - 40 - 36 * k });
    // (one between stocks one over the other: in a lane beside them, between their rows)
    if (ys != null) for (let k = 0; k < 6; k++)
      cands.push({ x: Math.max(ra.x1, rb.x1) + 40 + 36 * k, y: ys }, { x: Math.min(ra.x0, rb.x0) - 40 - 36 * k, y: ys });
    const cost = (p) => Math.abs(p.x - a.x) + Math.abs(p.y - a.y) + Math.abs(b.x - p.x) + Math.abs(b.y - p.y) +
      (Math.abs(p.y - a.y) < 1 || Math.abs(p.y - b.y) < 1 || Math.abs(p.x - a.x) < 1 || Math.abs(p.x - b.x) < 1 ? 0 : 60);
    cands.sort((p, q) => cost(p) - cost(q));
    const mine = home(n.id);
    // with its goal where there is room for both, else alone (a link from its goal travels the farther)
    for (const p of [...cands.map((q) => [q, group]), ...(group.length > 1 ? cands.map((q) => [q, [v]]) : [])].map(([q, grp]) => ({ ...q, grp }))) {
      const group = p.grp, others = lay.children.filter((k) => !group.includes(k)), was = group.map((c) => [c.x, c.y]);
      const dx = p.x - m.x, dy = p.y - m.y;
      const rooms = group.map((c) => { const r = partBox(c); return { x0: r.x0 + dx, y0: r.y0 + dy, x1: r.x1 + dx, y1: r.y1 + dy }; });
      if (rooms.some((r) => others.some((k) => meets(r, partBox(k), 12)))) continue;
      if (rooms.some((r) => (lay.containers || []).some((o) => o.name !== mine && !within(g, mine, o.name) &&
        meets(r, { x0: o.x, y0: o.y, x1: o.x + o.width, y1: o.y + o.height }, 8)))) continue;
      for (const c of group) { c.x += dx; c.y += dy; }
      if (!outlinesClear(lay, g)) { group.forEach((c, i) => { [c.x, c.y] = was[i]; }); continue; }
      moved.push(n.id);
      const ids = new Set(group.map((c) => c.id));
      for (const le of lay.edges) {                    // ELK's lines straight to where they are now, until libavoid's
        const e = g.edges.find((q) => q.id === le.id);
        if (!e || !(ids.has(e.source) || ids.has(e.target)) || !box[e.source] || !box[e.target]) continue;
        le.sections = [{ startPoint: mid(box[e.source]), endPoint: mid(box[e.target]), bendPoints: [] }];
        le.cut = false;                                // (one drawn by hand between wrapped rows: routed now, from where it is)
      }
      break;
    }
  }
  if (moved.length) { regrowOutlines(lay, g); refit(lay); }
  return moved;
}
