/* which way each valve (and disturbance) faces, decided on the finished layout (after pins): its pipe
   runs the way what it joins lies (left to right, right to left, or, when what flows in and out of it
   lies above and below, turned a quarter, top to bottom or bottom to top), and its stem, where its
   information lines attach (its command in, what it tells out), points to the side where most of what
   they join lies. The layout carries it (c.turn on the laid-out part): the drawing turns the glyph,
   libavoid's pins are put on those sides (avoid.js), and its name and rate move to a free side. */
"use strict";

const TURN_VEC = { right: [1, 0], left: [-1, 0], down: [0, 1], up: [0, -1] };
const SIDE_OF = { right: "left", left: "right", down: "up", up: "down" };   // where a flow going this way comes in

/* a point on a part's side (up, down, left, right), at fraction f along it, in the part's own coordinates */
function sidePoint(side, f, w, h) {
  return side === "left" ? [0, f * h] : side === "right" ? [w, f * h] : side === "up" ? [f * w, 0] : [f * w, h];
}

function orientValves(lay, g) {
  const box = Object.fromEntries(lay.children.map((c) => [c.id, c]));
  const mid = (c) => ({ x: c.x + c.width / 2, y: c.y + c.height / 2 });
  const turned = [];
  // a cloud's words (where the flow comes from, or goes on to) beyond it, away from its valve: never on its pipe
  for (const e of g.edges.filter((x) => x.kind === "pipe")) {
    const [cl, v] = box[e.source]?.labels?.length && e.source.startsWith("cloud:") ? [box[e.source], box[e.target]]
      : box[e.target]?.labels?.length && e.target.startsWith("cloud:") ? [box[e.target], box[e.source]] : [];
    if (!cl || !v) continue;
    const a = mid(cl), b = mid(v), dx = b.x - a.x, dy = b.y - a.y;
    for (const l of cl.labels) {
      if (Math.abs(dy) >= Math.abs(dx)) { l.x = (cl.width - l.width) / 2; l.y = dy > 0 ? -l.height - 2 : cl.height + 2; }
      else { l.y = (cl.height - l.height) / 2; l.x = dx > 0 ? -l.width - 4 : cl.width + 4; }
    }
  }
  for (const n of g.nodes) {
    if (n.kind !== "valve" && n.kind !== "disturbance") continue;
    const c = box[n.id];
    if (!c) continue;
    const me = mid(c);
    // its pipes (not one a wrapped layout draws by hand between rows): turned upright when each end it has
    // lies above or below it, or, at an elbow, when the end in line with it does (below)
    const cut = new Set(lay.edges.filter((le) => le.cut).map((le) => le.id));
    const pin = g.edges.find((e) => e.kind === "pipe" && e.target === n.id && !cut.has(e.id));
    const pout = g.edges.find((e) => e.kind === "pipe" && e.source === n.id && !cut.has(e.id));
    const a = pin && box[pin.source] ? mid(box[pin.source]) : null, b = pout && box[pout.target] ? mid(box[pout.target]) : null;
    const upright = (p, q) => Math.abs(q.y - p.y) > Math.abs(q.x - p.x) * 1.2 && Math.abs(q.y - p.y) > c.height;
    const ends = [a && [a, me], b && [me, b]].filter(Boolean);
    let vertical = ends.length > 0 && ends.every(([p, q]) => upright(p, q)) && (!a || !b || Math.sign(me.y - a.y) === Math.sign(b.y - me.y));
    let dy = (b || me).y - (a || me).y;
    // an elbow (one end beside it, the other above or below): the end in line with it sets its axis, so the pipe
    // to that end runs straight through it and the turn is on the way to the other (a valve put over its stock
    // stands upright on it, docs/layout-rules.md: valve-orientation-mismatch)
    const inLine = [pin && box[pin.source] && [box[pin.source], -1], pout && box[pout.target] && [box[pout.target], 1]].filter(Boolean)
      .map(([o, way]) => {
        const stacked = o.x < me.x && me.x < o.x + o.width, beside = o.y < me.y && me.y < o.y + o.height;
        if (stacked === beside) return null;
        const m = mid(o);
        return { way, upright: stacked, off: stacked ? Math.abs(m.x - me.x) : Math.abs(m.y - me.y), d: stacked ? m.y - me.y : m.x - me.x };
      }).filter(Boolean).sort((p, q) => p.off - q.off);
    let inLineEnd = null;
    if (inLine.length && Math.abs(inLine[0].d) > c.height && !(inLine.length > 1 && inLine[1].upright !== inLine[0].upright && inLine[1].off < inLine[0].off + 1)) {
      vertical = inLine[0].upright;
      inLineEnd = inLine[0];
      if (vertical) dy = inLine[0].way * inLine[0].d;  // (the flow runs toward its out end, away from its in end)
    }
    // level: right to left only when what flows in lies right of it and what it flows to does not (a
    // flow back, with the valve between its ends); a valve beyond both ends stays as it reads, left to right
    const back = a ? a.x > me.x + 2 && (!b || b.x < me.x - 2) : b && b.x < me.x - 2;
    let flow = vertical ? (dy > 0 ? "down" : "up") : back ? "left" : "right";
    if (inLineEnd && !vertical)                              // (level by the end in line with it: toward it if it is where the flow goes)
      flow = (inLineEnd.way === 1) === (inLineEnd.d < 0) ? "left" : "right";
    const peers = g.edges.filter((e) => e.kind !== "pipe" && (e.target === n.id || e.source === n.id))
      .map((e) => box[e.target === n.id ? e.source : e.target]).filter(Boolean).map(mid);
    const most = (f) => peers.length > 0 && peers.filter(f).length > peers.length / 2;
    const stem = vertical ? (most((q) => q.x > me.x + 10) ? "right" : "left") : (most((q) => q.y > me.y + 10) ? "down" : "up");
    c.turn = { flow, stem };
    c.stems = { level: most((q) => q.y > me.y + 10) ? "down" : "up", vertical: most((q) => q.x > me.x + 10) ? "right" : "left" };
    n.flip = !vertical && stem === "down";
    placeLabels(c, lay.children, stem, vertical);             // (as laid out too: it may have been turned before)
    if (flow === "right" && stem === "up") continue;           // as laid out
    turned.push(n.id);
    for (const p of c.ports || []) {                          // ELK's ports, where the pins now are
      const side = /:(ctl|sense)$/.test(p.id) ? stem : /:in$/.test(p.id) ? SIDE_OF[flow] : /:out$/.test(p.id) ? flow : null;
      if (side) [p.x, p.y] = sidePoint(side, 0.5, c.width, c.height);
    }
    for (const le of lay.edges) {                             // ELK's lines end there, until libavoid's come
      const e = g.edges.find((x) => x.id === le.id), sec = (le.sections || [])[0];
      if (!e || !sec || le.cut || (e.source !== n.id && e.target !== n.id)) continue;
      const side = e.kind !== "pipe" ? stem : e.target === n.id ? SIDE_OF[flow] : flow;
      const [px, py] = sidePoint(side, 0.5, c.width, c.height);
      if (e.source === n.id) sec.startPoint = { x: c.x + px, y: c.y + py };
      if (e.target === n.id) sec.endPoint = { x: c.x + px, y: c.y + py };
      sec.bendPoints = [];
    }
  }
  return turned;
}

/* a turned valve's name and rate: on the side away from its stem (below or above a level one, beside
   an upright one), or the first other side where they lie on nothing */
function placeLabels(c, kids, stem, vertical) {
  const ls = c.labels || [];
  if (!ls.length) return;
  const w = Math.max(...ls.map((l) => l.width)), h = ls.reduce((s, l) => s + l.height, 0);
  const at = {
    down: [(c.width - w) / 2, c.height + 4], up: [(c.width - w) / 2, -h - 4],
    left: [-w - 6, (c.height - h) / 2], right: [c.width + 6, (c.height - h) / 2],
  };
  const away = { up: "down", down: "up", left: "right", right: "left" }[stem];
  // (beside a level one is on its pipe, as above or below an upright one is: an upright one's name goes on
  // either side of it, the side away from its stem first)
  const order = vertical ? [away, stem] : [away];
  const free = (x, y) => !kids.some((o) => o !== c && c.x + x < o.x + o.width && o.x < c.x + x + w && c.y + y < o.y + o.height && o.y < c.y + y + h);
  const side = order.find((s) => free(...at[s])) || away;
  let y = at[side][1];
  for (const l of ls) { l.x = at[side][0] + (w - l.width) / 2; l.y = y; y += l.height; }
}

/* the glyph turned: drawn stem up, flowing right, then mapped so its flow and its stem point the ways asked */
function turnTransform(turn, w, h) {
  if (!turn || (turn.flow === "right" && turn.stem === "up")) return null;
  const [a, b] = TURN_VEC[turn.flow], [sx, sy] = TURN_VEC[turn.stem], c = -sx, d = -sy;
  const cx = w / 2, cy = h / 2;
  return `matrix(${a},${b},${c},${d},${cx - (a * cx + c * cy)},${cy - (b * cx + d * cy)})`;
}

/* the ways the router found each flow running through its valve (avoid.js: its first pass, the valve a point):
   each valve turned to match, its stem where most of its links are, its name moved to a free side */
function turnValves(lay, g, flows) {
  const box = Object.fromEntries(lay.children.map((c) => [c.id, c]));
  const byId = Object.fromEntries(g.nodes.map((n) => [n.id, n]));
  for (const [id, flow] of Object.entries(flows)) {
    const c = box[id];
    if (!c || !c.turn || c.turn.flow === flow) continue;
    const vertical = flow === "up" || flow === "down";
    const stem = vertical ? c.stems?.vertical || "left" : c.stems?.level || "up";
    c.turn = { flow, stem };
    if (byId[id]) byId[id].flip = !vertical && stem === "down";
    placeLabels(c, lay.children, stem, vertical);
    for (const p of c.ports || []) {
      const side = /:(ctl|sense)$/.test(p.id) ? stem : /:in$/.test(p.id) ? SIDE_OF[flow] : /:out$/.test(p.id) ? flow : null;
      if (side) [p.x, p.y] = sidePoint(side, 0.5, c.width, c.height);
    }
  }
}
