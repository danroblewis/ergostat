/* the diagram's lines, routed by libavoid (Adaptagrams' connector router, as WebAssembly: static/libavoid/):
   ELK places the parts and draws its own lines at once; libavoid then routes every line around the
   parts, orthogonally, with few bends and crossings, in a Web Worker so the page never waits for it,
   and its lines replace ELK's when they are ready. Each line attaches where its part allows: a valve's
   pipes at its sides and its information at its stem (on top, or below for a valve turned over), a
   system box's ports where they are, a stock's pipes on its sides and its information top and bottom,
   any other part on any side. Lines that share an end share one point there and their way from it
   until they part, so lines from one point never cross each other; any other two never share a point.
   The outlines of open systems are not in the way. When a part is dragged, only what it touches is
   routed again. A snapshot (opened from a file, where a worker cannot load) carries libavoid in
   itself and routes on the page. */
"use strict";

const AV = { mode: null, loading: null, core: null, worker: null, seq: 0, waiting: {}, routed: null, moving: null };

/* the router, the same in the worker and on the page: given parts, pins and lines, their routes; then,
   for a part moved, the routes that changed. Self-contained: the worker gets it as source text */
function avoidCore(A) {
  const D = A.ConnDirFlag, dirs = { up: D.ConnDirUp, down: D.ConnDirDown, left: D.ConnDirLeft, right: D.ConnDirRight };
  let router = null, shapes = {}, labels = {}, conns = {}, pos = {};
  const dirty = new Set();
  const take = () => {
    const out = {};
    for (const id of dirty) out[id] = conns[id].displayRoute().map((p) => [p.x, p.y]);
    dirty.clear();
    return out;
  };
  const setUp = (r, spec) => {
    const P = A.RoutingParameter, O = A.RoutingOption;
    r.setRoutingParameter(P.shapeBufferDistance, 5);
    r.setRoutingParameter(P.idealNudgingDistance, 7);
    r.setRoutingParameter(P.segmentPenalty, 60);
    r.setRoutingParameter(P.crossingPenalty, spec.crossingPenalty);
    r.setRoutingParameter(P.fixedSharedPathPenalty, 0);
    r.setRoutingParameter(P.portDirectionPenalty, 100);
  };
  /* the first pass: each flow from end to end through its valve's middle as a point (no valve in the way, no
     other line), and the way it runs there: where its valve faces. At a corner on the valve, the stretch that
     reaches an end straight (else the longer) */
  const firstPass = (spec) => {
    const out = {}, slides = {};
    out.__slides = slides;
    let r1 = null;
    try {
      r1 = new A.Router(A.RouterFlag.OrthogonalRouting);
      setUp(r1, { ...spec, crossingPenalty: 0 });
      const sh = {};
      for (const s of spec.shapes) {
        if (s.valve) continue;
        const x = r1.addShape({ x: s.x, y: s.y, width: s.w, height: s.h });
        sh[s.id] = x;
        for (const p of s.pins1 || s.pins) {
          const pin = x.addPin({ classId: p.cls, x: p.x, y: p.y, proportional: !p.abs, directions: dirs[p.dir] });
          if (p.shared) pin.setExclusive(false);
        }
        for (const l of s.labels || []) r1.addShape({ x: l.x, y: l.y, width: l.w, height: l.h });
      }
      const fc = {};
      for (const f of spec.flows) {
        if (!sh[f.s] || !sh[f.t]) continue;
        const cr = r1.addConnector({ shape: sh[f.s], pin: f.sp }, { shape: sh[f.t], pin: f.tp });
        cr.setRoutingCheckpoints([{ x: f.x, y: f.y, arrival: D.ConnDirAll, departure: D.ConnDirAll }]);
        fc[f.id] = [cr, f];
      }
      r1.processTransaction();
      // the way it runs through the point; and whether it turns there (a corner on the valve)
      const way = (cr, f) => {
        if (!cr.hasValidRoute()) return null;
        const p = cr.displayRoute().map((q) => [q.x, q.y]);
        const dist = (a, b) => {                        // (the router's nudging may move a stretch a few pixels off the point)
          const L2 = (b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2, t = L2 ? Math.max(0, Math.min(1, ((f.x - a[0]) * (b[0] - a[0]) + (f.y - a[1]) * (b[1] - a[1])) / L2)) : 0;
          return Math.hypot(f.x - (a[0] + t * (b[0] - a[0])), f.y - (a[1] + t * (b[1] - a[1])));
        };
        let near = Infinity;
        for (let i = 0; i + 1 < p.length; i++) near = Math.min(near, dist(p[i], p[i + 1]));
        const on = (a, b) => near <= 8 && dist(a, b) <= near + 1.5;
        const cand = [];
        for (let i = 0; i + 1 < p.length; i++) if (on(p[i], p[i + 1])) cand.push(i);
        if (!cand.length) return null;
        const len = (i) => Math.hypot(p[i + 1][0] - p[i][0], p[i + 1][1] - p[i][1]);
        const i = cand.find((j) => j === 0 || j === p.length - 2) ?? cand.reduce((a, b) => (len(b) > len(a) ? b : a));
        const dx = p[i + 1][0] - p[i][0], dy = p[i + 1][1] - p[i][1];
        if (Math.abs(dx) < 0.5 && Math.abs(dy) < 0.5) return null;
        const dir = Math.abs(dx) >= Math.abs(dy) ? (dx > 0 ? "right" : "left") : (dy > 0 ? "down" : "up");
        const level = (j) => Math.abs(p[j + 1][1] - p[j][1]) < 0.5;
        // a corner just past the point (a stub out of the valve, then a turn): how far to slide along the stretch, away
        // from it, for room for the valve's half and a stub, where the stretch is long enough
        let slide = 0;
        const a = p[i], b = p[i + 1], len_ = len(i), along = Math.hypot(f.x - a[0], f.y - a[1]), need = 48;
        const cornerA = i > 0, cornerB = i + 1 < p.length - 1;
        if (cornerA && along < need && len_ - need >= need) slide = need - along;
        else if (cornerB && len_ - along < need && along - (len_ - need) >= 0 && len_ >= 2 * need) slide = -(need - (len_ - along));
        const ux = len_ ? (b[0] - a[0]) / len_ : 0, uy = len_ ? (b[1] - a[1]) / len_ : 0;
        return { dir, corner: cand.length > 1 && cand.some((j) => level(j) !== level(i)), dx: ux * slide, dy: uy * slide };
      };
      // a flow that turns on its valve: routed again straight through it, on the axis of its stretch there, so its
      // turn moves off the valve (a corner on a valve is a stub out of it whichever way it faces)
      const across = (D.ConnDirLeft | D.ConnDirRight) || 12, upDown = (D.ConnDirUp | D.ConnDirDown) || 3;
      // (each axis tried: the one with fewer corners, then the shorter way, is kept)
      const cost = (cr) => { if (!cr.hasValidRoute()) return Infinity;
        const p = cr.displayRoute().map((q) => [q.x, q.y]);
        let len = 0; for (let i = 1; i < p.length; i++) len += Math.abs(p[i][0] - p[i - 1][0]) + Math.abs(p[i][1] - p[i - 1][1]);
        return (p.length - 2) * 10000 + len; };
      // (all of them at once: one routing for each axis, and one for the choices)
      const corners = Object.values(fc).filter(([cr, f]) => way(cr, f)?.corner);
      if (corners.length) {
        const costs = corners.map(() => ({}));
        for (const ax of [across, upDown]) {
          for (const [cr, f] of corners) cr.setRoutingCheckpoints([{ x: f.x, y: f.y, arrival: ax, departure: ax }]);
          r1.processTransaction();
          corners.forEach(([cr], i) => { costs[i][ax] = cost(cr); });
        }
        let again = false;
        corners.forEach(([cr, f], i) => {
          const best = Math.min(costs[i][across], costs[i][upDown]);
          if (best === Infinity) { cr.setRoutingCheckpoints([{ x: f.x, y: f.y, arrival: D.ConnDirAll, departure: D.ConnDirAll }]); again = true; }
          else if (costs[i][across] < costs[i][upDown]) { cr.setRoutingCheckpoints([{ x: f.x, y: f.y, arrival: across, departure: across }]); again = true; }
        });
        if (again) r1.processTransaction();
      }
      for (const [id, [cr, f]] of Object.entries(fc)) {
        const w = way(cr, f);
        if (!w) continue;
        // (a valve faces either way along its axis: the way toward the far end, where that is clear)
        const level = w.dir === "left" || w.dir === "right";
        const d = level ? (f.tx ?? f.x) - f.x : (f.ty ?? f.y) - f.y;
        out[id] = Math.abs(d) > 20 ? (level ? (d < 0 ? "left" : "right") : (d < 0 ? "up" : "down")) : w.dir;
        if (!f.pinned && Math.abs(w.dx) + Math.abs(w.dy) > 1) {      // (slid along its stretch, where it lies on nothing; never one put by hand)
          const me = spec.shapes.find((x) => x.id === id);
          const r = me && { x0: me.x + w.dx - 4, y0: me.y + w.dy - 4, x1: me.x + me.w + w.dx + 4, y1: me.y + me.h + w.dy + 4 };
          const clear = r && !spec.shapes.some((x) => x !== me && [{ x: x.x, y: x.y, w: x.w, h: x.h }, ...(x.labels || [])]
            .some((b) => b.x < r.x1 && r.x0 < b.x + b.w && b.y < r.y1 && r.y0 < b.y + b.h));
          if (clear) slides[id] = [Math.round(w.dx), Math.round(w.dy)];
        }
      }
    } catch (e) { /* no first pass: each valve as it was turned */ }
    try { r1?.delete(); } catch (e) { /* gone */ }
    return out;
  };
  return {
    route(spec) {
      if (router) { try { router.delete(); } catch (e) { /* gone */ } }
      router = new A.Router(A.RouterFlag.OrthogonalRouting);
      shapes = {}; labels = {}; conns = {}; pos = {}; dirty.clear();
      const P = A.RoutingParameter, O = A.RoutingOption;
      router.setRoutingParameter(P.shapeBufferDistance, 5);
      router.setRoutingParameter(P.idealNudgingDistance, 7);
      router.setRoutingParameter(P.segmentPenalty, 60);
      router.setRoutingParameter(P.crossingPenalty, spec.crossingPenalty);
      router.setRoutingParameter(P.fixedSharedPathPenalty, 0);
      router.setRoutingParameter(P.portDirectionPenalty, 100);
      router.setRoutingOption(O.nudgeOrthogonalSegmentsConnectedToShapes, true);
      router.setRoutingOption(O.nudgeSharedPathsWithCommonEndPoint, !!spec.nudgeCommon);   // lines from one point share their way
      router.setRoutingOption(O.penaliseOrthogonalSharedPathsAtConnEnds, true);
      router.setRoutingOption(O.performUnifyingNudgingPreprocessingStep, true);
      const turns = (spec.flows || []).length ? firstPass(spec) : {};
      const slides = turns.__slides || {};
      delete turns.__slides;
      for (const s of spec.shapes) if (slides[s.id]) {   // a valve slid along its pipe, off the corner by it (and its name)
        const [dx, dy] = slides[s.id];
        s.x += dx; s.y += dy;
        for (const l of s.labels || []) { l.x += dx; l.y += dy; }
        for (const k of Object.values(s.labelsBy || {})) for (const l of k) { l.x += dx; l.y += dy; }
      }
      for (const s of spec.shapes) {
        if (s.pinsBy && turns[s.id]) { s.pins = s.pinsBy[turns[s.id]]; if (s.labelsBy) s.labels = s.labelsBy[turns[s.id]]; }
        const sh = router.addShape({ x: s.x, y: s.y, width: s.w, height: s.h });
        shapes[s.id] = sh; pos[s.id] = { x: s.x, y: s.y };
        for (const p of s.pins) {
          const pin = sh.addPin({ classId: p.cls, x: p.x, y: p.y, proportional: !p.abs, directions: dirs[p.dir] });
          if (p.shared) pin.setExclusive(false);
        }
        labels[s.id] = (s.labels || []).map((l) => router.addShape({ x: l.x, y: l.y, width: l.w, height: l.h }));
      }
      for (const c of spec.conns) {
        const cr = router.addConnector({ shape: shapes[c.s], pin: c.sp }, { shape: shapes[c.t], pin: c.tp });
        conns[c.id] = cr;
        cr.setCallback(() => dirty.add(c.id));
      }
      const t0 = performance.now();
      router.processTransaction();
      const ms = performance.now() - t0;
      const invalid = Object.values(conns).filter((c) => !c.hasValidRoute()).length;
      return { routes: take(), ms, invalid, turns, slides };
    },
    moveMany(list) {                                    // several parts moved together (an open system dragged): one routing
      if (!router) return {};
      for (const [id, x, y] of list) {
        if (!shapes[id]) continue;
        const dx = x - pos[id].x, dy = y - pos[id].y;
        if (!dx && !dy) continue;
        pos[id] = { x, y };
        router.moveShape(shapes[id], dx, dy);
        for (const l of labels[id]) router.moveShape(l, dx, dy);
      }
      router.processTransaction();
      return take();
    },
    move(id, x, y) {
      if (!router || !shapes[id]) return {};
      const dx = x - pos[id].x, dy = y - pos[id].y;
      if (!dx && !dy) return {};
      pos[id] = { x, y };
      router.moveShape(shapes[id], dx, dy);
      for (const l of labels[id]) router.moveShape(l, dx, dy);
      router.processTransaction();
      return take();
    },
  };
}

function avoidUrls() {                                  // where libavoid is: the static files, or a snapshot's own bytes
  if (window.LIBAVOID) {
    const blob = (b64, type) => URL.createObjectURL(new Blob([Uint8Array.from(atob(b64), (ch) => ch.charCodeAt(0))], { type }));
    return { js: blob(window.LIBAVOID.js, "text/javascript"), wasm: blob(window.LIBAVOID.wasm, "application/wasm"), worker: false };
  }
  const base = new URL("/static/libavoid/", location.href);
  let v = {};                                           // their versions (the server's meta tag): an update is a new address
  try { v = JSON.parse(document.querySelector('meta[name="ergostat-assets"]')?.content || "{}"); } catch (e) { /* none */ }
  const at = (name) => { const u = new URL(name, base); if (v[`libavoid/${name}`]) u.searchParams.set("v", v[`libavoid/${name}`]); return u.href; };
  return { js: at("libavoid.js"), wasm: at("libavoid.wasm"), worker: true };
}

function avoidWorker(u) {                               // the router in a worker: resolves to it, or null if it cannot start
  return new Promise((resolve) => {
    let w;
    try {
      // (libavoid-js is built for the page only and refuses a worker: it is shown the page it looks for)
      const src = `globalThis.window = globalThis;
globalThis.WorkerGlobalScope = undefined;
const { AvoidLib } = await import(${JSON.stringify(u.js)});
const avoidCore = ${avoidCore.toString()};
let core = null;
const queue = [];
function drain() {
  if (!core || !queue.length) return;
  let last = -1;
  queue.forEach((m, i) => { if (m.type === "route") last = i; });
  const msgs = queue.splice(0);
  for (const m of msgs.slice(0, Math.max(0, last))) if (m.type === "route") postMessage({ type: "routed", seq: m.seq, skipped: true });
  const todo = msgs.slice(Math.max(0, last));
  const moves = {};
  for (const m of todo) {
    if (m.type === "route") postMessage({ type: "routed", seq: m.seq, ...core.route(m.spec) });
    else if (m.type === "moveMany") postMessage({ type: "moved", seq: m.seq, n: m.n, routes: core.moveMany(m.list) });
    else {                                             // a part moved again before the last was routed: only where it is now
      if (moves[m.id]) postMessage({ type: "moved", seq: moves[m.id].seq, n: moves[m.id].n, routes: {} });
      moves[m.id] = m;
    }
  }
  for (const m of Object.values(moves)) postMessage({ type: "moved", seq: m.seq, n: m.n, routes: core.move(m.id, m.x, m.y) });
}
onmessage = (ev) => { queue.push(ev.data); setTimeout(drain, 0); };
AvoidLib.load(${JSON.stringify(u.wasm)}).then(() => { core = avoidCore(AvoidLib.getInstance()); postMessage({ type: "ready" }); drain(); },
  (e) => postMessage({ type: "failed", error: String(e) }));`;
      w = new Worker(URL.createObjectURL(new Blob([src], { type: "text/javascript" })), { type: "module" });
    } catch (e) {
      resolve(null);
      return;
    }
    const give = setTimeout(() => { w.terminate(); resolve(null); }, 15000);
    w.onerror = () => { clearTimeout(give); w.terminate(); resolve(null); };
    w.onmessage = (ev) => {
      const m = ev.data;
      if (m.type === "ready") { clearTimeout(give); w.onmessage = avoidHeard; resolve(w); }
      else if (m.type === "failed") { clearTimeout(give); w.terminate(); resolve(null); }
    };
  });
}

function avoidHeard(ev) {                               // the worker's answers
  const m = ev.data, wait = AV.waiting[`${m.type}:${m.seq}:${m.n ?? ""}`];
  if (!wait) return;
  delete AV.waiting[`${m.type}:${m.seq}:${m.n ?? ""}`];
  wait(m);
}

function avoidLoad() {                                  // once: the worker, else libavoid on the page, else nothing (ELK's lines)
  if (AV.loading) return AV.loading;
  AV.loading = (async () => {
    const u = avoidUrls();
    if (u.worker) {
      AV.worker = await avoidWorker(u);
      if (AV.worker) { AV.mode = "worker"; return AV.mode; }
    }
    try {
      const m = await import(u.js);
      await m.AvoidLib.load(u.wasm);
      AV.core = avoidCore(m.AvoidLib.getInstance());
      AV.mode = "page";
    } catch (e) {
      console.warn("libavoid did not load: the lines are the layout's", e);
    }
    return AV.mode;
  })();
  return AV.loading;
}

const PIN = { IN: 3, OUT: 4, STEM: 5, TELL: 6, PIPE: 7, ANY: 8, NET: 1000, PORT: 100 };   // pin classes (NET + i: a part's i-th net)
const PIPE_ALONG = [0.15, 0.3, 0.5, 0.7, 0.85];   // where pipes may meet a stock's sides: apart enough (9px on a 44px stock) for a track each
const CROSSING_PENALTY = (lines) => (lines <= 100 ? 200 : lines <= 600 ? 50 : 20);   // a crossing costs; less where there are
                                                                                      // many lines: its search is most of the time

/* what libavoid is given: every part, with the points its lines may attach at, and every line, by which
   part and which kind of point each end takes */
function avoidSpec(lay, g) {
  const byId = Object.fromEntries(g.nodes.map((n) => [n.id, n]));
  const edgeOf = Object.fromEntries(g.edges.map((e) => [e.id, e]));
  const box = Object.fromEntries(lay.children.filter((c) => byId[c.id]).map((c) => [c.id, c]));
  const lines = lay.edges.filter((le) => !le.cut && edgeOf[le.id] && box[edgeOf[le.id].source] && box[edgeOf[le.id].target]);
  const special = (id) => ["valve", "disturbance", "cloud"].includes(byId[id].kind);
  // the system dynamics view (dynamics.js): every connector reaches its part at a point of its own, as
  // its connectors do in Vensim and Stella, never merged into one line; a valve's on its stem, while few
  const sd = g.kind === "dynamics";
  const infoAt = {};
  const arrive = {};
  for (const le of lines) {
    const e = edgeOf[le.id];
    if (e.kind === "pipe") continue;
    for (const id of [e.source, e.target]) infoAt[id] = (infoAt[id] || 0) + 1;
    arrive[e.target] = (arrive[e.target] || 0) + 1;
  }
  const ownStem = (id) => sd && (infoAt[id] || 0) <= 6 && (arrive[id] || 0) <= 5;
  // a part's own ends (not at a port, a valve or a cloud, nor a pipe at a stock): by which way and kind
  const ends = {};
  for (const le of lines) {
    const e = edgeOf[le.id];
    for (const w of ["s", "t"]) {
      const id = w === "s" ? e.source : e.target;
      if ((w === "s" ? e.sourcePort : e.targetPort) || special(id) || (e.kind === "pipe" && byId[id].kind === "stock")) continue;
      ((ends[id] ||= {})[`${w}|${e.kind}`] ||= []).push(le.id);
    }
  }
  // stocks and clouds a valve turned upright joins: their pipes may meet them on top and below too
  // (and a stock whose valve stands over or under it, level or not: its pipe meets the side that faces the valve)
  const faces = (o, v) => { const m = { x: v.x + v.width / 2, y: v.y + v.height / 2 };
    return m.x > o.x && m.x < o.x + o.width && (m.y < o.y || m.y > o.y + o.height); };
  const upright = new Set(lines.map((le) => edgeOf[le.id]).filter((e) => e.kind === "pipe").flatMap((e) => {
    const v = ["up", "down"].includes(box[e.source]?.turn?.flow) ? e.target : ["up", "down"].includes(box[e.target]?.turn?.flow) ? e.source : null;
    if (v) return [v];
    const [o, vv] = box[e.source]?.turn ? [box[e.target], box[e.source]] : box[e.target]?.turn ? [box[e.source], box[e.target]] : [];
    return o && vv && ["stock", "cloud"].includes(byId[o.id]?.kind) && faces(o, vv) ? [o.id] : [];
  }));
  const alignedValves = {};                              // stock -> the valves its pipes join
  for (const le of lines) {
    const e = edgeOf[le.id];
    if (e.kind !== "pipe") continue;
    for (const [st, v] of [[e.source, e.target], [e.target, e.source]])
      if (byId[st].kind === "stock" && ["valve", "disturbance"].includes(byId[v].kind)) (alignedValves[st] ||= []).push(box[v]);
  }
  // the sides of a stock its links may leave or reach it by: every side no pipe meets (so a link leaves by the side
  // facing its target), else its top or bottom where no satellite's pipe meets it (a flow to or from a cloud stood
  // beside it), else its top and bottom as before (docs/layout-rules.md: a link never runs along a pipe)
  const pipeSides = {};
  for (const le of lines) {
    const e = edgeOf[le.id];
    if (e.kind !== "pipe") continue;
    for (const [st, v] of [[e.source, e.target], [e.target, e.source]]) {
      const a = box[st], b = box[v];
      if (!a || !b || byId[st].kind !== "stock") continue;
      const m = { x: b.x + b.width / 2, y: b.y + b.height / 2 };
      const side = m.x > a.x && m.x < a.x + a.width ? (m.y < a.y ? "up" : "down") : m.y > a.y && m.y < a.y + a.height ? (m.x < a.x ? "left" : "right")
        : Math.abs(m.x - (a.x + a.width / 2)) > Math.abs(m.y - (a.y + a.height / 2)) ? (m.x < a.x ? "left" : "right") : (m.y < a.y ? "up" : "down");
      ((pipeSides[st] ||= {})[side] ||= []).push(drainOf(g, v) ? "satellite" : "pipe");
    }
  }
  const linkSides = (c) => {
    const used = pipeSides[c.id] || {}, sat = (d) => (used[d] || []).includes("satellite");
    if (!sat("up") && !sat("down")) return ["up", "down"];    // (as before: more points cost the router time)
    const free = ["up", "down", "left", "right"].filter((d) => !used[d]), level = ["up", "down"].filter((d) => !sat(d));
    return free.length ? free : level.length ? level : ["up", "down"];
  };
  const pinOf = {};                                      // `${line}|${s or t}` -> pin class
  const pinsBy = {}, labelsBy = {};                      // a valve's pins (and its name) for each way it may face
  const shapes = [];
  for (const c of Object.values(box)) {
    const n = byId[c.id], k = n.kind, pins = [];
    const at = (cls, x, y, dir, shared, abs) => pins.push({ cls, x, y, dir, shared: !!shared, abs: !!abs });
    if (k === "valve" || k === "disturbance") {
      // its pins for each way it may face (the router turns it to its pipe: avoidCore), and as it faces now
      const stems = c.stems || { level: "up", vertical: "left" };
      const pinsFor = (flow) => {
        const t = { flow, stem: ["up", "down"].includes(flow) ? stems.vertical : stems.level }, out = [];
        const put = (cls, d, f, shared) => { const [x, y] = sidePoint(d, f, 1, 1); out.push({ cls, x, y, dir: d, shared: !!shared, abs: false }); };
        put(PIN.IN, SIDE_OF[t.flow], 0.5, true);
        put(PIN.OUT, t.flow, 0.5, true);
        // its stem: what drives it comes in at one point, what it tells leaves at another
        if (ownStem(c.id)) {                                  // (the system dynamics view: each arrival its own point)
          for (const f of [0.15, 0.25, 0.35, 0.45, 0.55]) put(PIN.ANY, t.stem, f, false);
          put(PIN.TELL, t.stem, 0.72, true);
        } else { put(PIN.STEM, t.stem, 0.4, true); put(PIN.TELL, t.stem, 0.6, true); }
        return out;
      };
      const t = c.turn || { flow: "right", stem: "up" };      // which way it faces (valves.js)
      pins.push(...pinsFor(t.flow));
      pinsBy[c.id] = Object.fromEntries(["right", "left", "up", "down"].map((f) => [f, pinsFor(f)]));
      // and its name where it goes when it faces each way (valves.js placeLabels: away from its stem)
      const ls = c.labels || [];
      if (ls.length) {
        const w = Math.max(...ls.map((l) => l.width)), h = ls.reduce((a, l) => a + l.height, 0);
        labelsBy[c.id] = Object.fromEntries(["right", "left", "up", "down"].map((f) => {
          const vertical = f === "up" || f === "down", stem = vertical ? stems.vertical : stems.level;
          const away = { up: "down", down: "up", left: "right", right: "left" }[stem];
          const [x, y] = { down: [(c.width - w) / 2, c.height + 4], up: [(c.width - w) / 2, -h - 4], left: [-w - 6, (c.height - h) / 2],
                           right: [c.width + 6, (c.height - h) / 2] }[away];
          return [f, [{ x: c.x + x, y: c.y + y, w: Math.max(1, w), h: Math.max(1, h) }]];
        }));
      }
    } else if (k === "cloud") {                              // a pipe meets a cloud at its side (or top and bottom, by an upright valve)
      for (const d of upright.has(c.id) ? ["left", "right", "up", "down"] : ["left", "right"]) at(PIN.PIPE, ...sidePoint(d, 0.5, 1, 1), d, true);
    } else {
      if (k === "system") (n.ports || []).forEach((p, i) => {
        const lp = (c.ports || []).find((q) => q.id === p.id);
        const west = (p.at || (p.side === "in" ? "west" : "east")) === "west";
        if (lp) at(PIN.PORT + i, west ? 0 : c.width, lp.y + (lp.height || 0) / 2, west ? "left" : "right", true, true);
      });
      if (k === "stock") for (const f of PIPE_ALONG) { at(PIN.PIPE, 0, f, "left"); at(PIN.PIPE, 1, f, "right"); }
      // a stock an upright valve joins takes that pipe at the middle of its top or bottom, where the valve stands
      // (libavoid finds no way for a line whose point lies on another's: its information points keep off the middle)
      if (k === "stock" && upright.has(c.id)) { at(PIN.PIPE, 0.5, 0, "up"); at(PIN.PIPE, 0.5, 1, "down"); }
      // and, wherever a valve joined to it faces one of its sides (put there by hand, a pixel off the middle), a point
      // in line with that valve, so its pipe runs straight into the valve instead of jogging to the nearest fixed point
      if (k === "stock") for (const v of alignedValves[c.id] || []) {
        const vx = v.x + v.width / 2, vy = v.y + v.height / 2, fx = (vx - c.x) / c.width, fy = (vy - c.y) / c.height;
        // (never on a point already there: two pins in one place are two pipes on one track)
        const taken = (d, f, len) => pins.some((p) => p.cls === PIN.PIPE && p.dir === d && Math.abs((d === "up" || d === "down" ? p.x : p.y) - f) * len < 7);
        if (fx > 0.08 && fx < 0.92 && (vy < c.y || vy > c.y + c.height)) { const d = vy < c.y ? "up" : "down"; if (!taken(d, fx, c.width)) at(PIN.PIPE, fx, d === "up" ? 0 : 1, d); }
        else if (fy > 0.12 && fy < 0.88 && (vx < c.x || vx > c.x + c.width)) { const d = vx < c.x ? "left" : "right"; if (!taken(d, fy, c.height)) at(PIN.PIPE, d === "left" ? 0 : 1, fy, d); }
      }
      // the rest: each net (lines of one kind, all leaving or all arriving) its own point on each side, shared by
      // its lines; single lines points of their own, one line each, enough of them for all
      const sides = k === "stock" ? linkSides(c) : ["up", "down", "left", "right"];
      const groups = Object.entries(ends[c.id] || {});
      // (what arrives, in the system dynamics view: one point each, while few; what leaves shares one)
      const own = (key) => ownStem(c.id) && key[0] === "t";
      const nets = groups.filter(([key, x]) => x.length > 1 && !own(key));
      const singles = groups.reduce((a, [key, x]) => a + (x.length === 1 || own(key) ? x.length : 0), 0);
      // (a part whose arrivals each take a point of their own has a few on every side to choose from)
      const slots = nets.length + (ownStem(c.id) ? Math.min(singles, 4) : Math.ceil(singles / sides.length));
      const place = (cls, i, shared) => {
        const f0 = (i + 1) / (slots + 1), f = upright.has(c.id) ? (f0 <= 0.5 ? f0 * 0.75 : 0.25 + f0 * 0.75) : f0;
        for (const d of sides) at(cls, d === "left" ? 0 : d === "right" ? 1 : f, d === "up" ? 0 : d === "down" ? 1 : f, d, shared);
      };
      nets.forEach(([key, ids], i) => {
        place(PIN.NET + i, i, true);
        for (const id of ids) pinOf[`${id}|${key[0]}`] = PIN.NET + i;
      });
      for (let i = nets.length; i < slots; i++) place(PIN.ANY, i, false);
    }
    // (the first pass, where flows are routed with their valves as points: a stock's and a cloud's pipes may meet
    // any side)
    const pins1 = k === "stock" ? [...pins.filter((p) => p.cls !== PIN.PIPE), ...["left", "right", "up", "down"].flatMap((d) => PIPE_ALONG.map((f) => {
      const [x, y] = sidePoint(d, f, 1, 1); return { cls: PIN.PIPE, x, y, dir: d, shared: false, abs: false }; }))]
      : k === "cloud" ? ["left", "right", "up", "down"].map((d) => { const [x, y] = sidePoint(d, 0.5, 1, 1); return { cls: PIN.PIPE, x, y, dir: d, shared: true, abs: false }; })
      : null;
    shapes.push({ id: c.id, x: c.x, y: c.y, w: c.width, h: c.height, pins, ...(pinsBy[c.id] ? { pinsBy: pinsBy[c.id], labelsBy: labelsBy[c.id], valve: true } : {}), ...(pins1 ? { pins1 } : {}),
                  labels: (c.labels || []).map((l) => ({ x: c.x + l.x, y: c.y + l.y, w: Math.max(1, l.width), h: Math.max(1, l.height) })) });
  }
  const pinAt = (e, w) => {
    const id = w === "s" ? e.source : e.target, port = w === "s" ? e.sourcePort : e.targetPort, k = byId[id].kind;
    if (port) { const i = (byId[id].ports || []).findIndex((p) => p.id === port); return i < 0 ? null : PIN.PORT + i; }
    if (k === "valve" || k === "disturbance") return e.kind === "pipe" ? (w === "s" ? PIN.OUT : PIN.IN) : w === "t" ? (ownStem(id) ? PIN.ANY : PIN.STEM) : PIN.TELL;
    if (k === "cloud" || (e.kind === "pipe" && k === "stock")) return PIN.PIPE;
    return pinOf[`${e.id}|${w}`] ?? PIN.ANY;
  };
  const conns = [];
  for (const le of lines) {
    const e = edgeOf[le.id], sp = pinAt(e, "s"), tp = pinAt(e, "t");
    if (sp != null && tp != null) conns.push({ id: le.id, s: e.source, sp, t: e.target, tp });
  }
  // each flow whole, from its one end to its other through its valve's middle (a point: it may face any way), for
  // the first pass: the way it takes there turns the valve (docs/layout-rules.md: valve-orientation-mismatch)
  const flows = [];
  for (const c of Object.values(box)) {
    if (!pinsBy[c.id] || S.pins?.["turn:" + c.id]) continue;
    const cin = conns.find((x) => x.t === c.id && edgeOf[x.id].kind === "pipe"), cout = conns.find((x) => x.s === c.id && edgeOf[x.id].kind === "pipe");
    if (!cin || !cout) continue;
    const far = box[cout.t] && { x: box[cout.t].x + box[cout.t].width / 2, y: box[cout.t].y + box[cout.t].height / 2 };
    flows.push({ id: c.id, s: cin.s, sp: cin.sp, t: cout.t, tp: cout.tp, x: c.x + c.width / 2, y: c.y + c.height / 2,
                                  tx: far?.x, ty: far?.y, pinned: !!S.pins?.[c.id] || !!c.slid });   // (slid once a layout: no drift)
  }
  // (in the dynamics view a flow's pipe reads best short and straight: a crossing there costs less than a long way round)
  return { shapes, conns, flows, crossingPenalty: sd ? Math.min(80, CROSSING_PENALTY(conns.length) * (conns.length > 150 ? 0.6 : 1)) : CROSSING_PENALTY(conns.length), nudgeCommon: true };
}

/* the lines routed: in the worker (the page keeps ELK's lines meanwhile and redraws when they come), or on
   the page. lay.routing is true until then; lay.whenRouted resolves when it is done (or given up) */
function avoidStart(lay, g) {
  if (!AV.mode) return;
  const spec = avoidSpec(lay, g), seq = ++AV.seq;
  const byKind = Object.fromEntries(g.nodes.map((n) => [n.id, n.kind]));
  const done = (m) => {
    if (m && !m.skipped) {
      const byLe = Object.fromEntries(lay.edges.map((le) => [le.id, le]));
      for (const [id, [dx, dy]] of Object.entries(m.slides || {})) {   // (the router slid it along its pipe)
        const c = lay.children.find((k) => k.id === id);
        if (c) { c.x += dx; c.y += dy; c.slid = true; }
      }
      if (m.turns) turnValves(lay, g, m.turns);           // each valve facing the way its flow runs through it (valves.js)
      for (const [id, pts] of Object.entries(m.routes)) setRoute(byLe[id], pts.map(([x, y]) => ({ x, y })));
      straightenPipes(lay, g);
      // the lines that share a point (every pin but a part's own single ones), put in order
      const groups = {};
      for (const c of spec.conns) for (const [w, id, pin] of [["s", c.s, c.sp], ["t", c.t, c.tp]])
        if (pin !== PIN.ANY && !(pin === PIN.PIPE && byKind[id] === "stock")) (groups[`${w}|${id}|${pin}`] ||= { end: w, ids: [] }).ids.push(c.id);
      untangle(lay, Object.values(groups).filter((x) => x.ids.length > 1), lay.children,
               Object.fromEntries(spec.conns.map((c) => [c.id, [c.s, c.t]])));
      uncross(lay, g);
      if (g.kind === "dynamics") { sdSeparate(lay, g); uncross(lay, g); sdAroundSatellites(lay, g); }   // (dynamics.js)
      unjog(lay, g);                                     // (last: the lines are where they stay)
      AV.ms = m.ms; AV.invalid = m.invalid;               // (how long it took, and lines it found no way for: the tests read them)
      AV.routed = { lay, seq };
    }
    lay.routing = false;
  };
  lay.routing = true;
  if (AV.mode === "page") { done(AV.core.route(spec)); lay.whenRouted = Promise.resolve(); return; }
  lay.whenRouted = new Promise((resolve) => {
    AV.waiting[`routed:${seq}:`] = (m) => {
      done(m);
      if (!m.skipped && lay === S.layout) S.redraw?.();
      resolve();
    };
  });
  AV.worker.postMessage({ type: "route", seq, spec });
}

/* a pipe with a small jog where its stock (or cloud) could take it straight: its end slides along that side */
function straightenPipes(lay, g) {
  const box = Object.fromEntries(lay.children.map((c) => [c.id, c]));
  const kind = Object.fromEntries(g.nodes.map((n) => [n.id, n.kind]));
  const edge = Object.fromEntries(g.edges.map((e) => [e.id, e]));
  for (const le of lay.edges) {
    const e = edge[le.id], sec = (le.sections || [])[0];
    if (!e || e.kind !== "pipe" || !sec || (sec.bendPoints || []).length !== 2) continue;
    const [s, b1, b2, t] = [sec.startPoint, ...sec.bendPoints, sec.endPoint];
    const flat = Math.abs(s.y - b1.y) < 0.5 && Math.abs(b2.y - t.y) < 0.5 && Math.abs(b1.x - b2.x) < 0.5 && Math.abs(b1.y - b2.y) <= 30;
    if (!flat) continue;
    // (and never next to another pipe's end on that part: two pipes on one track)
    const crowded = (id, x, y) => lay.edges.some((o) => o !== le && edge[o.id]?.kind === "pipe" && (o.sections || [])[0] &&
      [[edge[o.id].source, o.sections[0].startPoint], [edge[o.id].target, o.sections[0].endPoint]].some(([pid, q]) => pid === id && Math.abs(q.x - x) < 2 && Math.abs(q.y - y) < 7));
    const slides = (id, y, x) => { const c = box[id]; return ["stock", "cloud"].includes(kind[id]) && c && y > c.y + 4 && y < c.y + c.height - 4 && !crowded(id, x, y); };
    if (slides(e.target, s.y, t.x)) { sec.endPoint = { x: t.x, y: s.y }; sec.bendPoints = []; }
    else if (slides(e.source, t.y, s.x)) { sec.startPoint = { x: s.x, y: t.y }; sec.bendPoints = []; }
  }
}

/* a pipe's small jogs (the router's nudging, a few pixels across) taken out where the stretch after one can run on in
   line with the stretch before it: clear of every part, and on no other line's track */
const JOG = 12;
function unjog(lay, g) {
  const edge = Object.fromEntries(g.edges.map((e) => [e.id, e]));
  const pts = (le) => { const sc = le.sections[0]; return [sc.startPoint, ...(sc.bendPoints || []), sc.endPoint]; };
  const lines = lay.edges.filter((le) => (le.sections || []).length);
  const clear = (le, a, b) => {
    const x0 = Math.min(a.x, b.x), x1 = Math.max(a.x, b.x), y0 = Math.min(a.y, b.y), y1 = Math.max(a.y, b.y);
    if (lay.children.some((c) => c.id !== edge[le.id].source && c.id !== edge[le.id].target &&
        x1 > c.x + 2 && x0 < c.x + c.width - 2 && y1 > c.y + 2 && y0 < c.y + c.height - 2)) return false;
    const mine = edge[le.id], net = (o) => { const x = edge[o.id];     // (a pipe into, or out of, the same part: one net, one track)
      return x && x.kind === mine.kind && (x.target === mine.target || x.source === mine.source); };
    return !lines.some((o) => o !== le && !net(o) && pts(o).slice(1).some((q, j) => { const p0 = pts(o)[j];
      if (Math.abs(a.y - b.y) < 0.5 && Math.abs(p0.y - q.y) < 0.5 && Math.abs(a.y - p0.y) < 4) return Math.min(x1, Math.max(p0.x, q.x)) - Math.max(x0, Math.min(p0.x, q.x)) > 4;
      if (Math.abs(a.x - b.x) < 0.5 && Math.abs(p0.x - q.x) < 0.5 && Math.abs(a.x - p0.x) < 4) return Math.min(y1, Math.max(p0.y, q.y)) - Math.max(y0, Math.min(p0.y, q.y)) > 4;
      return false; }));
  };
  for (const le of lines) {
    if (edge[le.id]?.kind !== "pipe") continue;
    let p = pts(le), changed = false;
    for (let i = 1; i + 2 < p.length; i++) {          // p[i] -> p[i+1] a jog between two stretches running the same way
      const a = p[i - 1], b = p[i], c = p[i + 1], d = p[i + 2];
      const level = Math.abs(a.y - b.y) < 0.5 && Math.abs(c.y - d.y) < 0.5 && Math.abs(b.x - c.x) < 0.5;
      const upright = Math.abs(a.x - b.x) < 0.5 && Math.abs(c.x - d.x) < 0.5 && Math.abs(b.y - c.y) < 0.5;
      const jog = level ? Math.abs(c.y - b.y) : upright ? Math.abs(c.x - b.x) : 0;
      if (!jog || jog > JOG) continue;
      if (i + 2 === p.length - 1) {                    // (the last stretch ends on its part: the one before goes onto its line)
        if (i - 1 === 0) continue;
        const a2 = level ? { x: a.x, y: c.y } : { x: c.x, y: a.y }, b2 = level ? { x: b.x, y: c.y } : { x: c.x, y: b.y };
        if (!clear(le, a2, b2) || !clear(le, p[i - 2], a2)) continue;
        p = [...p.slice(0, i - 1), a2, b2, d];        // (b2 and c are one point now: the jog gone)
        p = p.filter((q, j) => j === 0 || Math.abs(q.x - p[j - 1].x) + Math.abs(q.y - p[j - 1].y) > 0.5);
        changed = true;
        break;
      }
      const d2 = level ? { x: d.x, y: b.y } : { x: b.x, y: d.y };
      const e = p[i + 3];
      if (!clear(le, b, d2) || (e && !clear(le, d2, level ? { x: e.x, y: e.y } : { x: e.x, y: e.y }))) continue;
      if (e && ((level && Math.abs(e.x - d.x) > 0.5) || (upright && Math.abs(e.y - d.y) > 0.5))) continue;   // (the next must turn)
      p = [...p.slice(0, i + 1), d2, ...p.slice(i + 3)];
      changed = true;
      i--;
    }
    if (changed) le.sections = [{ startPoint: p[0], bendPoints: p.slice(1, -1), endPoint: p[p.length - 1] }];
  }
}

function setRoute(le, pts) {                            // a route from libavoid as the edge's one section, only its corners
  const r = [];
  for (const p of pts) {
    const q = { x: p.x, y: p.y }, a = r[r.length - 1], b = r[r.length - 2];
    if (a && Math.abs(a.x - q.x) + Math.abs(a.y - q.y) < 0.5) continue;
    if (a && b && ((Math.abs(b.x - a.x) < 0.5 && Math.abs(a.x - q.x) < 0.5) || (Math.abs(b.y - a.y) < 0.5 && Math.abs(a.y - q.y) < 0.5))) r.pop();
    r.push(q);
  }
  if (r.length < 2) return;
  le.sections = [{ startPoint: r[0], bendPoints: r.slice(1, -1), endPoint: r[r.length - 1] }];
  le.junctionPoints = [];
  le.stale = false;                                   // (its own way now: no longer grey)
}

/* parts dragged together (an open system): moved in one routing; resolves to the ids of the lines that changed
   (null when the lines are not libavoid's). Where only some lines are libavoid's (the Process view's: r.keep), the
   others keep their way unless they touch what moves */
function avoidMoveMany(list) {
  const r = AV.routed;
  if (!r || r.lay !== S.layout) return null;
  const byId = Object.fromEntries(r.lay.children.map((k) => [k.id, k]));
  for (const [id, x, y] of list) if (byId[id]) { byId[id].x = x; byId[id].y = y; }
  const moving = new Set(list.map(([id]) => id));
  const apply = (routes) => {
    if (r.lay !== S.layout) return [];
    const byLe = Object.fromEntries(r.lay.edges.map((le) => [le.id, le])), out = [];
    for (const [eid, pts] of Object.entries(routes)) {
      if (!byLe[eid] || (r.keep && !r.keep(byLe[eid], moving))) continue;
      setRoute(byLe[eid], pts.map(([px, py]) => ({ x: px, y: py })));
      out.push(eid);
    }
    return out;
  };
  if (AV.mode === "page") return Promise.resolve(apply(AV.core.moveMany(list)));
  const n = (AV.moving = (AV.moving || 0) + 1);
  return new Promise((resolve) => {
    AV.waiting[`moved:${r.seq}:${n}`] = (m) => resolve(apply(m.routes));
    AV.worker.postMessage({ type: "moveMany", seq: r.seq, n, list });
  });
}

/* a part dragged: its shape (and its labels) moved, and only the lines that touches routed again; resolves to
   the ids of the lines whose way changed (null when the lines are not libavoid's: they wait for the drop) */
function avoidMove(id, x, y) {
  const r = AV.routed;
  if (!r || r.lay !== S.layout) return null;
  const c = r.lay.children.find((k) => k.id === id);
  if (!c) return null;
  c.x = x; c.y = y;
  const apply = (routes) => {
    if (r.lay !== S.layout) return [];
    const byLe = Object.fromEntries(r.lay.edges.map((le) => [le.id, le]));
    for (const [eid, pts] of Object.entries(routes)) setRoute(byLe[eid], pts.map(([px, py]) => ({ x: px, y: py })));
    return Object.keys(routes);
  };
  if (AV.mode === "page") return Promise.resolve(apply(AV.core.move(id, x, y)));
  const n = (AV.moving = (AV.moving || 0) + 1);
  return new Promise((resolve) => {
    AV.waiting[`moved:${r.seq}:${n}`] = (m) => resolve(apply(m.routes));
    AV.worker.postMessage({ type: "move", seq: r.seq, n, id, x, y });
  });
}
