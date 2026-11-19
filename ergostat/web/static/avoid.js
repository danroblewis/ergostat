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
    const out = {};
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
      for (const [id, [cr, f]] of Object.entries(fc)) {
        if (!cr.hasValidRoute()) continue;
        const p = cr.displayRoute().map((q) => [q.x, q.y]);
        const on = (a, b) => Math.abs((b[0] - a[0]) * (f.y - a[1]) - (b[1] - a[1]) * (f.x - a[0])) < 2 * Math.hypot(b[0] - a[0], b[1] - a[1]) &&
          f.x >= Math.min(a[0], b[0]) - 1.5 && f.x <= Math.max(a[0], b[0]) + 1.5 && f.y >= Math.min(a[1], b[1]) - 1.5 && f.y <= Math.max(a[1], b[1]) + 1.5;
        const cand = [];
        for (let i = 0; i + 1 < p.length; i++) if (on(p[i], p[i + 1])) cand.push(i);
        if (!cand.length) continue;
        const len = (i) => Math.hypot(p[i + 1][0] - p[i][0], p[i + 1][1] - p[i][1]);
        const i = cand.find((j) => j === 0 || j === p.length - 2) ?? cand.reduce((a, b) => (len(b) > len(a) ? b : a));
        const dx = p[i + 1][0] - p[i][0], dy = p[i + 1][1] - p[i][1];
        if (Math.abs(dx) < 0.5 && Math.abs(dy) < 0.5) continue;
        out[id] = Math.abs(dx) >= Math.abs(dy) ? (dx > 0 ? "right" : "left") : (dy > 0 ? "down" : "up");
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
      return { routes: take(), ms, invalid, turns };
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
const PIPE_ALONG = [0.15, 0.25, 0.35, 0.45, 0.5, 0.55, 0.65, 0.75, 0.85];   // where pipes may meet a stock's sides
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
        if (fx > 0.08 && fx < 0.92 && (vy < c.y || vy > c.y + c.height)) at(PIN.PIPE, fx, vy < c.y ? 0 : 1, vy < c.y ? "up" : "down");
        else if (fy > 0.12 && fy < 0.88 && (vx < c.x || vx > c.x + c.width)) at(PIN.PIPE, vx < c.x ? 0 : 1, fy, vx < c.x ? "left" : "right");
      }
      // the rest: each net (lines of one kind, all leaving or all arriving) its own point on each side, shared by
      // its lines; single lines points of their own, one line each, enough of them for all
      const sides = k === "stock" ? ["up", "down"] : ["up", "down", "left", "right"];
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
    if (cin && cout) flows.push({ id: c.id, s: cin.s, sp: cin.sp, t: cout.t, tp: cout.tp, x: c.x + c.width / 2, y: c.y + c.height / 2 });
  }
  // (in the dynamics view a flow's pipe reads best short and straight: a crossing there costs less than a long way round)
  return { shapes, conns, flows, crossingPenalty: sd ? Math.min(80, CROSSING_PENALTY(conns.length)) : CROSSING_PENALTY(conns.length), nudgeCommon: true };
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
      AV.turns = m.turns;                                 // (the tests read them)
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
      if (g.kind === "dynamics") { sdSeparate(lay, g); uncross(lay, g); }   // (dynamics.js)
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
    const slides = (id, y) => { const c = box[id]; return ["stock", "cloud"].includes(kind[id]) && c && y > c.y + 4 && y < c.y + c.height - 4; };
    if (slides(e.target, s.y)) { sec.endPoint = { x: t.x, y: s.y }; sec.bendPoints = []; }
    else if (slides(e.source, t.y)) { sec.startPoint = { x: s.x, y: t.y }; sec.bendPoints = []; }
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
