/* where parts end up after the layout: a stock's flows to and from clouds stood upright where there is
   room (below it for a drain, above it for an inflow), then what the owner dragged put back where it was
   put (a part, or an open system with everything in it), what that would sit on moved out of its way,
   and open systems' outlines drawn round their parts again, never one over another */
"use strict";

/* a part's box with its labels, wherever they are */
function partBox(k) {
  const ls = k.labels || [];
  return { x0: Math.min(k.x, ...ls.map((l) => k.x + l.x)), y0: Math.min(k.y, ...ls.map((l) => k.y + l.y)),
           x1: Math.max(k.x + k.width, ...ls.map((l) => k.x + l.x + l.width)), y1: Math.max(k.y + k.height, ...ls.map((l) => k.y + l.y + l.height)) };
}
const meets = (a, b, m = 0) => a.x0 < b.x1 + m && b.x0 < a.x1 + m && a.y0 < b.y1 + m && b.y0 < a.y1 + m;
const PAD = { top: 44, side: 26 };
const padOf = (g) => (g?.kind === "blocks" ? { top: bdFrameTitle() + 8, side: BD.PAD }   // (a block diagram's frames: blocks.js)
  : g?.kind === "process" ? { top: PM.PAD + PM.TITLE, side: PM.PAD } : PAD);              // (a kind's frame in the process map: process.js)

/* the open system (or, in the block diagram, the frame) a system or frame is drawn in: the block
   diagram's frames are "frame:<system>" and "casc:<goal>", each with its parent frame (blocks.js) */
function frameParent(g, name) {
  if (g?.kind !== "blocks") return g?.tree?.[name]?.within;
  const f = (g.frames || []).find((x) => x.id === name);
  if (f) return f.parent || null;
  const sys = name.startsWith("frame:") && g.tree?.[name.slice(6)];      // a system closed here: the frame it would be in
  return sys?.within ? "frame:" + sys.within : null;
}
/* the open system name is within (its own or further in) */
function within(g, inner, outer) {
  for (let x = frameParent(g, inner); x; x = frameParent(g, x)) if (x === outer) return true;
  return false;
}

/* the block diagram's ports (blocks.js) where their parts are now: each kept as an offset from its part */
function followPorts(lay) {
  if (!lay.ports) return;
  const box = Object.fromEntries(lay.children.map((c) => [c.id, c]));
  for (const p of Object.values(lay.ports)) { const c = box[p.node]; if (c && p.dx != null) { p.x = c.x + p.dx; p.y = c.y + p.dy; } }
}

/* every open system's outline round its parts and the systems open inside it (and its frame, the box
   the layout gave it, wherever it has been moved: an outline only grows), the innermost first */
function regrowOutlines(lay, g) {
  if (!lay.containers?.length) return;
  const byId = Object.fromEntries(g.nodes.map((n) => [n.id, n]));
  const PAD = padOf(g);
  const sorted = [...lay.containers].sort((a, b) => b.depth - a.depth);
  for (const c of sorted) {
    const parts = lay.children.filter((k) => (byId[k.id]?.systems || []).includes(c.name));
    const inner = sorted.filter((o) => o.depth > c.depth && frameParent(g, o.name) === c.name);
    const boxes = [...parts.map(partBox), ...inner.map((o) => ({ x0: o.x, y0: o.y, x1: o.x + o.width, y1: o.y + o.height }))];
    if (c.bx != null) boxes.push({ x0: c.bx + PAD.side, y0: c.by + PAD.top, x1: c.bx + c.w0 - PAD.side, y1: c.by + c.h0 - PAD.side });   // its frame
    if (!boxes.length) continue;
    const x0 = Math.min(...boxes.map((b) => b.x0)) - PAD.side, y0 = Math.min(...boxes.map((b) => b.y0)) - PAD.top;
    Object.assign(c, { x: x0, y: y0, width: Math.max(...boxes.map((b) => b.x1)) + PAD.side - x0, height: Math.max(...boxes.map((b) => b.y1)) + PAD.side - y0 });
  }
}

/* whether, drawn round their parts again, no open system's outline lies over another (beside it, not
   inside it) or over a part not in it */
function outlinesClear(lay, g) {
  if (!lay.containers?.length) return true;
  const keep = lay.containers.map((c) => ({ ...c }));
  regrowOutlines(lay, g);
  const byId = Object.fromEntries(g.nodes.map((n) => [n.id, n]));
  const rect = (o) => ({ x0: o.x, y0: o.y, x1: o.x + o.width, y1: o.y + o.height });
  const nested = (a, b) => a.name === b.name || within(g, a.name, b.name) || within(g, b.name, a.name);
  const clear = lay.containers.every((a) => lay.containers.every((b) => nested(a, b) || !meets(rect(a), rect(b), 8)) &&
    lay.children.every((k) => (byId[k.id]?.systems || []).includes(a.name) || !meets(partBox(k), rect(a), 2)));
  lay.containers.forEach((c, i) => Object.assign(c, keep[i]));
  return clear;
}

/* the drawing's size again, from what is in it */
function refit(lay) {
  const bs = [...lay.children.map(partBox), ...(lay.containers || []).map((c) => ({ x0: c.x, y0: c.y, x1: c.x + c.width, y1: c.y + c.height }))];
  lay.ox = Math.min(0, ...bs.map((b) => b.x0 - 40)); lay.oy = Math.min(0, ...bs.map((b) => b.y0 - 40));   // (what was put left or above)
  lay.width = Math.max(...bs.map((b) => b.x1)) + 40 - lay.ox;
  lay.height = Math.max(...bs.map((b) => b.y1)) + 40 - lay.oy;
}

/* parts put down by hand, and no new layout: what they would sit on moved out of their way (as for pins),
   the outlines drawn round their parts again, the valves facing their pipes, the drawing's size; the
   lines are routed again by the caller */
function settle(lay, g, placed) {
  applyPins(lay, g, placed);
  orientValves(lay, g);
  refit(lay);
}

/* the whole layout moved so that one system (opened or closed just now) lies where it lay before:
   the view does not jump, and what was put stays put */
function anchorOf(lay, g, name) {                    // a system's open outline (or frame), else its box
  const c = (lay.containers || []).find((o) => o.name === name || o.name === "frame:" + name);
  return c || lay.children.find((k) => g.nodes.find((n) => n.id === k.id && (n.kind === "system" || n.role === "subsystem") && n.label === name));
}
function anchorLayout(lay, g, anchor) {
  if (!anchor) return false;
  const at = anchorOf(lay, g, anchor.name);
  if (!at) return false;
  const dx = anchor.x - at.x, dy = anchor.y - at.y;
  if (!dx && !dy) return true;
  for (const k of lay.children) { k.x += dx; k.y += dy; }
  for (const o of lay.containers || []) { o.x += dx; o.y += dy; }
  for (const le of lay.edges) for (const sec of le.sections || []) for (const p of [sec.startPoint, sec.endPoint, ...(sec.bendPoints || [])]) { p.x += dx; p.y += dy; }
  for (const le of lay.edges) for (const l of le.labels || []) { l.x += dx; l.y += dy; }
  followPorts(lay);
  refit(lay);
  return true;
}

/* a flow between a cloud and a stock and nothing else: the stock, its cloud, and whether it drains it */
function drainOf(g, v) {
  const pipes = g.edges.filter((e) => e.kind === "pipe" && (e.source === v || e.target === v));
  if (pipes.length !== 2) return null;
  const kind = Object.fromEntries(g.nodes.map((n) => [n.id, n.kind]));
  const other = pipes.map((e) => (e.source === v ? e.target : e.source));
  const cloud = other.find((x) => kind[x] === "cloud"), stock = other.find((x) => kind[x] === "stock");
  return cloud && stock ? { stock, cloud, out: pipes.some((e) => e.source === v && e.target === cloud) } : null;
}

/* a drain stood upright under its stock (its valve below it, its cloud below that), an inflow over it:
   it reads as falling out of the stock, or into it. Only where that room is free, inside the stock's
   own outline, and the drawing still fits the screen about as well; the chain of stocks keeps running
   left to right */
const UPRIGHT_GAP = 34, UPRIGHT_KEEP = 0.95;
function standUpright(lay, g) {
  const byId = Object.fromEntries(g.nodes.map((n) => [n.id, n]));
  const box = Object.fromEntries(lay.children.map((c) => [c.id, c]));
  const home = (id) => (byId[id]?.systems || [])[0] || null;
  const r = document.querySelector("svg.canvas")?.getBoundingClientRect();
  const [cw, ch] = r?.width ? [r.width - 40, r.height - 90] : [1260, 810];
  const fit = () => {                                  // the zoom at which all of it fits the canvas (1: full size)
    const bs = [...lay.children.map(partBox), ...(lay.containers || []).map((o) => ({ x0: o.x, y0: o.y, x1: o.x + o.width, y1: o.y + o.height }))];
    return Math.min(1, cw / (Math.max(...bs.map((b) => b.x1)) - Math.min(...bs.map((b) => b.x0))), ch / (Math.max(...bs.map((b) => b.y1)) - Math.min(...bs.map((b) => b.y0))));
  };
  const stood = [];
  for (const n of g.nodes) {
    if (n.kind !== "valve" && n.kind !== "disturbance") continue;
    const d = drainOf(g, n.id), v = box[n.id], c = d && box[d.cloud], st = d && box[d.stock];
    if (!d || !v || !c || !st || S.pins?.[n.id] || S.pins?.[d.cloud] || home(n.id) !== home(d.stock)) continue;
    const cx = st.x + st.width / 2, sb = partBox(st);
    const vy = d.out ? sb.y1 + UPRIGHT_GAP : st.y - UPRIGHT_GAP - v.height;
    const cy = d.out ? vy + v.height + UPRIGHT_GAP : vy - UPRIGHT_GAP - c.height;
    const lw = Math.max(0, ...(v.labels || []).map((l) => l.width)) + 8;     // its name beside it once turned: one side free
    const span = { y0: d.out ? sb.y1 + 4 : Math.min(vy, cy) - 6, y1: d.out ? Math.max(vy + v.height, cy + c.height) + 6 : st.y - 4 };
    const half = Math.max(v.width, c.width) / 2;
    const others = lay.children.filter((k) => k !== v && k !== c && k !== st);
    const mine = home(d.stock);
    const free = (room) => !others.some((k) => meets(room, partBox(k), 12)) &&
      !(lay.containers || []).some((o) => o.name !== mine && !within(g, mine, o.name) && meets(room, { x0: o.x, y0: o.y, x1: o.x + o.width, y1: o.y + o.height }, 8));
    if (![{ ...span, x0: cx - half, x1: cx + v.width / 2 + lw }, { ...span, x0: cx - v.width / 2 - lw, x1: cx + half }].some(free)) continue;
    const before = fit(), was = [v.x, v.y, c.x, c.y];
    Object.assign(v, { x: cx - v.width / 2, y: vy }); Object.assign(c, { x: cx - c.width / 2, y: cy });
    if (fit() < before * UPRIGHT_KEEP || !outlinesClear(lay, g)) { [v.x, v.y, c.x, c.y] = was; continue; }   // it would not fit the
                                                                                    // screen as well, or its outline would grow over another
    stood.push(n.id);
    for (const le of lay.edges) {                      // ELK's lines straight to where they are now, until libavoid's
      const e = g.edges.find((x) => x.id === le.id), sec = (le.sections || [])[0];
      if (!e || !sec || ![e.source, e.target].some((x) => x === n.id || x === d.cloud)) continue;
      const at = (id) => { const b = box[id]; return { x: b.x + b.width / 2, y: b.y + b.height / 2 }; };
      le.sections = [{ startPoint: at(e.source), endPoint: at(e.target), bendPoints: [] }];
    }
  }
  if (stood.length) { regrowOutlines(lay, g); refit(lay); }
  return stood;
}

/* a pin: where the owner put a part, or a system (its closed box and its open outline share one,
   "hull:<name>"), kept from the corner of the frame of the open system it is drawn in ({in, x, y}), or
   in the diagram's own coordinates ({x, y}): so what is inside a system keeps its place in it when
   the system moves, closes or opens, and a new layout never places what was put */
function pinId(id, node) {
  if (node?.kind === "system") return "hull:" + node.label;
  return node?.role === "subsystem" ? "hull:frame:" + node.label : id;     // (the block diagram's: its block and its frame)
}
function pinAt(lay, p) {                               // where a pin puts it now (null: its frame is not drawn here)
  if (!p) return null;
  if (!p.in) return { x: p.x, y: p.y };
  const f = (lay.containers || []).find((c) => c.name === p.in);
  return f && f.bx != null ? { x: f.bx + p.x, y: f.by + p.y } : null;
}
function pinFor(lay, g, name, x, y) {                  // a pin for something put at x, y: in the frame of the open system it is in
  const byId = Object.fromEntries(g.nodes.map((n) => [n.id, n]));
  const frame = name.startsWith("hull:") ? frameParent(g, name.slice(5)) : (byId[name]?.systems || [])[0];
  const f = frame && (lay.containers || []).find((c) => c.name === frame);
  return f && f.bx != null ? { in: frame, x: Math.round(x - f.bx), y: Math.round(y - f.by) } : { x: Math.round(x), y: Math.round(y) };
}

/* parts the owner dragged stay where they were put (pinned): an open system dragged by its outline
   (its pin, its frame's corner) takes everything in it along; then each pinned part goes
   to its place, what they would sit on is moved down out of their way, the outlines grow to hold their
   parts again, and an outline over another (or over a part not in it) moves what it would cover below
   it. Every line touching a moved part is routed anew. The pins are kept in this browser, per project,
   view and what is open */
function applyPins(lay, g, placed = null) {        // (placed: parts the owner has just put down, already where they go)
  const moved = new Set(), delta = {}, fixed = new Set();
  const pins = S.pins || {};
  const kids = lay.children;
  const byId = Object.fromEntries(g.nodes.map((n) => [n.id, n]));
  const shift = (c, x, y) => {
    const d = delta[c.id] || { x: 0, y: 0 };
    delta[c.id] = { x: d.x + x - c.x, y: d.y + y - c.y };
    c.x = x; c.y = y; moved.add(c.id);
  };
  const members = (name) => kids.filter((k) => (byId[k.id]?.systems || []).includes(name));
  const moveSystem = (c, dx, dy) => {                  // a system, everything in it and the systems inside it
    for (const k of members(c.name)) shift(k, k.x + dx, k.y + dy);
    for (const o of lay.containers) if (o === c || within(g, o.name, c.name)) { o.x += dx; o.y += dy; o.bx += dx; o.by += dy; }
  };
  const hulls = [...(lay.containers || [])].sort((a, b) => a.depth - b.depth);
  for (const c of hulls) if (c.bx == null) { c.bx = c.x; c.by = c.y; c.w0 = c.width; c.h0 = c.height; }   // each open system's frame:
                                                       // its pinned parts are kept from it, and its outline is drawn round it at least
  if (placed) {                                        // put down by hand: they stay, and so does all that is pinned
    for (const id of placed) { moved.add(id); fixed.add(id); }
    for (const c of hulls) if (pins["hull:" + c.name]) for (const k of members(c.name)) fixed.add(k.id);
    for (const c of kids) if (pins[pinId(c.id, byId[c.id])]) fixed.add(c.id);
  } else {
    for (const c of hulls) {                           // (the outermost first: one inside goes with it, then to its own pin)
      const t = pinAt(lay, pins["hull:" + c.name]);
      if (!t) continue;
      moveSystem(c, t.x - c.bx, t.y - c.by);
      for (const k of members(c.name)) fixed.add(k.id);
    }
    for (const c of kids) {
      const t = pinAt(lay, pins[pinId(c.id, byId[c.id])]);
      if (t) { shift(c, t.x, t.y); fixed.add(c.id); }
    }
  }
  if (!moved.size) return moved;
  const over = (a, b, m = 16) => a.x < b.x + b.width + m && b.x < a.x + a.width + m && a.y < b.y + b.height + m && b.y < a.y + a.height + m;
  for (let pass = 0; pass < 4; pass++) {                // what a pinned (or moved) part sits on is moved down, out of its way
    let any = false;
    for (const a of kids) {
      if (!moved.has(a.id)) continue;
      for (const b of kids) {
        if (b === a || fixed.has(b.id) || !over(a, b)) continue;
        shift(b, b.x, a.y + a.height + 28);
        any = true;
      }
    }
    if (!any) break;
  }
  regrowOutlines(lay, g);
  for (let pass = 0; pass < 6 && lay.containers?.length; pass++) {   // an outline over another, or over a part not in it
    let any = false;
    const rect = (o) => ({ x0: o.x, y0: o.y, x1: o.x + o.width, y1: o.y + o.height });
    for (const a of hulls) for (const b of hulls) {
      if (a === b || within(g, a.name, b.name) || within(g, b.name, a.name) || frameParent(g, a.name) !== frameParent(g, b.name)) continue;
      if (!meets(rect(a), rect(b), 16)) continue;
      // the one not put there by the owner (or the lower one) goes below the other
      const [stay, go] = pins["hull:" + b.name] && !pins["hull:" + a.name] ? [b, a] : pins["hull:" + a.name] || a.y <= b.y ? [a, b] : [b, a];
      if (pins["hull:" + go.name]) continue;
      moveSystem(go, 0, stay.y + stay.height + 24 - go.y);
      any = true;
    }
    for (const h of hulls) {                           // an outline not put there by the owner over a part that was: it gives way
      if (pins["hull:" + h.name]) continue;
      const level = hulls.find((o) => o.name === frameParent(g, h.name))?.name ?? null;
      const k = kids.find((k) => fixed.has(k.id) && !(byId[k.id]?.systems || []).includes(h.name) &&
                                 ((byId[k.id]?.systems || [])[0] ?? null) === level && meets(partBox(k), rect(h), 12));
      if (k) { moveSystem(h, 0, partBox(k).y1 + 28 - h.y); any = true; }
    }
    for (const h of hulls) {
      if (!pins["hull:" + h.name]) continue;
      const level = hulls.find((o) => o.name === frameParent(g, h.name))?.name ?? null;   // the outline it is drawn in
      for (const k of kids) {                           // (a part of another system goes with its system, above)
        if (fixed.has(k.id) || ((byId[k.id]?.systems || [])[0] ?? null) !== level || !meets(partBox(k), rect(h), 12)) continue;
        shift(k, k.x, h.y + h.height + 28);
        any = true;
      }
    }
    if (!any) break;
    regrowOutlines(lay, g);
  }
  for (const le of lay.edges) {                         // each line's ends go with the parts they belong to
    const e = (g.edges.find((x) => x.id === le.id)) || {};
    const sec = (le.sections || [])[0];
    if (!sec) continue;
    const ds = delta[e.source], dt = delta[e.target];
    if (ds) { sec.startPoint = { x: sec.startPoint.x + ds.x, y: sec.startPoint.y + ds.y }; }
    if (dt) { sec.endPoint = { x: sec.endPoint.x + dt.x, y: sec.endPoint.y + dt.y }; }
    if (ds || dt) sec.bendPoints = [];
  }
  followPorts(lay);
  refit(lay);
  return moved;
}
