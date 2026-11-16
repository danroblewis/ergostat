/* the diagram's lines, routed by libavoid (Adaptagrams' connector router, as WebAssembly: static/libavoid/):
   ELK places the parts; libavoid routes every line around them, orthogonally, with fewest bends and
   crossings, lines that share a stretch nudged apart, and each line attached where its part allows:
   a valve's pipes at its sides and its information at its stem (on top, or below for a valve turned
   over), a system box's ports where they are, any other part anywhere along its edges. The outlines
   of open systems are not in the way: a line crosses into a system wherever is shortest. When a part
   moves, only what it touches is routed again. A snapshot carries libavoid in itself; if it cannot load
   at all, the lines are ELK's. */
"use strict";

const AV = { lib: null, loading: null, state: null };

function avoidLoad() {                                  // once; resolves to the module, or null when it cannot load
  if (AV.lib || AV.loading) return AV.loading || Promise.resolve(AV.lib);
  AV.loading = (async () => {
    try {
      let js, wasm;
      if (window.LIBAVOID) {                            // a snapshot carries it: from its bytes
        const blob = (b64, type) => URL.createObjectURL(new Blob([Uint8Array.from(atob(b64), (ch) => ch.charCodeAt(0))], { type }));
        js = blob(window.LIBAVOID.js, "text/javascript"); wasm = blob(window.LIBAVOID.wasm, "application/wasm");
      } else {
        const base = new URL("/static/libavoid/", location.href);
        js = new URL("libavoid.js", base).href; wasm = new URL("libavoid.wasm", base).href;
      }
      const m = await import(js);
      await m.AvoidLib.load(wasm);
      AV.lib = m.AvoidLib.getInstance();
    } catch (e) {
      console.warn("libavoid did not load: the lines are the layout's", e);
      AV.lib = null;
    }
    return AV.lib;
  })();
  return AV.loading;
}

const PIN = { ANY: 1, PIPE: 2, IN: 3, OUT: 4, STEM: 5, TELL: 6, NET: 7, PORT: 100 };   // NET: a net leaving; + 1: arriving   // pin classes; a box's ports are PORT + their index
const PIPE_ALONG = [0.15, 0.25, 0.35, 0.45, 0.5, 0.55, 0.65, 0.75, 0.85];   // where pipes may meet a stock's sides
const ROUTE_UP_TO = 700;         // lines: above this many, ELK's lines (libavoid took 5 s for a thousand; budget 2.5 s)
const CROSSINGS_UP_TO = 60;      // lines: above this many, crossings cost nothing (libavoid's crossing search grows too slow)

function avoidRoute(lay, g) {
  const A = AV.lib;
  if (AV.state) { try { AV.state.router.delete(); } catch (e) { /* already gone */ } AV.state = null; }
  if (!A || lay.edges.length > ROUTE_UP_TO) return false;
  const D = A.ConnDirFlag;
  const router = new A.Router(A.RouterFlag.OrthogonalRouting);
  const P = A.RoutingParameter, O = A.RoutingOption;
  router.setRoutingParameter(P.shapeBufferDistance, 8);
  router.setRoutingParameter(P.idealNudgingDistance, 7);
  router.setRoutingParameter(P.segmentPenalty, 60);       // each bend costs: few corners
  // crossing another line costs more than a long way round, when there are few enough lines to afford it: with the
  // penalty, libavoid's search for crossings is most of its time (2.8 s for the 73 lines of a whole example)
  router.setRoutingParameter(P.crossingPenalty, lay.edges.length <= CROSSINGS_UP_TO ? 200 : 0);
  router.setRoutingParameter(P.fixedSharedPathPenalty, 0);
  router.setRoutingParameter(P.portDirectionPenalty, 100);
  router.setRoutingOption(O.nudgeOrthogonalSegmentsConnectedToShapes, true);
  router.setRoutingOption(O.nudgeSharedPathsWithCommonEndPoint, true);    // lines from one point run side by side, not on top
  router.setRoutingOption(O.penaliseOrthogonalSharedPathsAtConnEnds, true);
  router.setRoutingOption(O.performUnifyingNudgingPreprocessingStep, true);

  const byId = Object.fromEntries(g.nodes.map((n) => [n.id, n]));
  const shapes = {}, labels = {};
  const pin = (sh, cls, x, y, dirs, exclusive) => {
    const p = sh.addPin({ classId: cls, x, y, directions: dirs });
    if (exclusive === false) p.setExclusive(false);
    return p;
  };
  for (const c of lay.children) {
    const n = byId[c.id];
    if (!n) continue;
    const sh = router.addShape({ x: c.x, y: c.y, width: c.width, height: c.height });
    shapes[c.id] = sh;
    const k = n.kind;
    if (k === "valve" || k === "disturbance") {
      pin(sh, PIN.IN, 0, 0.5, D.ConnDirLeft, false);
      pin(sh, PIN.OUT, 1, 0.5, D.ConnDirRight, false);
      // its stem: the command comes in at one point, what it tells (its sensor, what it drives) leaves at another
      pin(sh, PIN.STEM, 0.4, n.flip ? 1 : 0, n.flip ? D.ConnDirDown : D.ConnDirUp, false);
      pin(sh, PIN.TELL, 0.6, n.flip ? 1 : 0, n.flip ? D.ConnDirDown : D.ConnDirUp, false);
    } else if (k === "system") {
      (n.ports || []).forEach((p, i) => {
        const lp = (c.ports || []).find((q) => q.id === p.id);
        if (!lp) return;
        const west = (p.at || (p.side === "in" ? "west" : "east")) === "west";
        const sp = sh.addPin({ classId: PIN.PORT + i, x: west ? 0 : c.width, y: lp.y + (lp.height || 0) / 2, proportional: false,
                               directions: west ? D.ConnDirLeft : D.ConnDirRight });
        sp.setExclusive(false);
      });
    } else if (k === "cloud") {
      pin(sh, PIN.PIPE, 0, 0.5, D.ConnDirLeft, false);
      pin(sh, PIN.PIPE, 1, 0.5, D.ConnDirRight, false);
    } else {
      if (k === "stock") {                               // pipes meet a stock at its sides, as in stock-and-flow, each its own
        for (const f of PIPE_ALONG) {                 // place, in line with its valve if it can (no jog)
          pin(sh, PIN.PIPE, 0, f, D.ConnDirLeft);
          pin(sh, PIN.PIPE, 1, f, D.ConnDirRight);
        }
      }
      // information at the middle of each side (a stock's: top and bottom, its sides are its pipes'). More points
      // would spread the lines, but each costs: five a side made the router five times slower
      pin(sh, PIN.ANY, 0.5, 0, D.ConnDirUp);
      pin(sh, PIN.ANY, 0.5, 1, D.ConnDirDown);
      if (k !== "stock") {
        pin(sh, PIN.ANY, 0, 0.5, D.ConnDirLeft);
        pin(sh, PIN.ANY, 1, 0.5, D.ConnDirRight);
      }
      // each of those takes one line; more than that share a point beside it, at a cost (without these, the next has
      // no way at all; and not on the same point: two pins in one place leave libavoid with no route)
      for (const [x, y, d] of [[0.42, 0, D.ConnDirUp], [0.42, 1, D.ConnDirDown], ...(k === "stock" ? [] : [[0, 0.42, D.ConnDirLeft], [1, 0.42, D.ConnDirRight]])])
        pin(sh, PIN.ANY, x, y, d, false).setConnectionCost(40);
      // a net (several lines of one kind leaving it, or reaching it): they share one point, the leaving and the
      // arriving each their own, and libavoid's nudging keeps them side by side
      for (const [o, f] of [[0, 0.58], [1, 0.7]])
        for (const [x, y, d] of [[f, 0, D.ConnDirUp], [f, 1, D.ConnDirDown], ...(k === "stock" ? [] : [[0, f, D.ConnDirLeft], [1, f, D.ConnDirRight]])])
          pin(sh, PIN.NET + o, x, y, d, false);
    }
    for (const l of c.labels || []) {                    // a part's labels are in the way too
      labels[c.id] ||= [];
      labels[c.id].push(router.addShape({ x: c.x + l.x, y: c.y + l.y, width: Math.max(1, l.width), height: Math.max(1, l.height) }));
    }
  }

  const edgeOf = Object.fromEntries(g.edges.map((e) => [e.id, e]));
  const portClass = (nodeId, portId) => {
    const n = byId[nodeId];
    const i = (n?.ports || []).findIndex((p) => p.id === portId);
    return i < 0 ? null : PIN.PORT + i;
  };
  const fan = {};                                        // how many lines of each kind leave (s) or reach (t) each part
  for (const e of g.edges) for (const w of ["s", "t"]) {
    if (e.kind === "pipe" || (w === "s" ? e.sourcePort : e.targetPort)) continue;
    const key = `${w}|${w === "s" ? e.source : e.target}|${e.kind}`;
    fan[key] = (fan[key] || 0) + 1;
  }
  const end = (e, which) => {                           // where a line attaches at one end
    const id = which === "s" ? e.source : e.target;
    const sh = shapes[id];
    if (!sh) return null;
    const port = which === "s" ? e.sourcePort : e.targetPort;
    if (port) { const cls = portClass(id, port); return cls ? { shape: sh, pin: cls } : null; }
    const k = byId[id]?.kind;
    if (k === "valve" || k === "disturbance") {
      if (e.kind !== "pipe") return { shape: sh, pin: which === "t" ? PIN.STEM : PIN.TELL };
      return { shape: sh, pin: which === "s" ? PIN.OUT : PIN.IN };
    }
    if (k === "cloud") return { shape: sh, pin: PIN.PIPE };
    if (e.kind === "pipe" && k === "stock") return { shape: sh, pin: PIN.PIPE };
    return { shape: sh, pin: (fan[`${which}|${id}|${e.kind}`] || 0) > 1 ? PIN.NET + (which === "s" ? 0 : 1) : PIN.ANY };
  };
  const conns = {}, dirty = new Set(), byLe = {};
  for (const le of lay.edges) {
    const e = edgeOf[le.id];
    if (!e || le.cut) continue;
    const s = end(e, "s"), t = end(e, "t");
    if (!s || !t) continue;
    const cr = router.addConnector(s, t);
    conns[le.id] = cr;
    byLe[le.id] = le;
    cr.setCallback(() => dirty.add(le.id));
  }
  const compose = () => {                               // the lines libavoid routed again: their new ways
    for (const id of dirty) setRoute(byLe[id], conns[id].displayRoute());
    const out = [...dirty];
    dirty.clear();
    return out;
  };
  const t0 = performance.now();
  router.processTransaction();
  AV.ms = performance.now() - t0;                       // (how long it took: the rendering tests read it)
  compose();
  straightenPipes(lay, g);
  AV.state = { router, shapes, labels, conns, lay, compose };
  return true;
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
}

/* a part dragged: its shape (and its labels) moved, and only the lines that touches routed again: the ids
   of the lines whose way changed, or null when there is no router (the lines then wait for the drop) */
function avoidMove(id, x, y) {
  const st = AV.state;
  if (!st || !st.shapes[id] || st.lay !== S.layout) return null;
  const c = st.lay.children.find((k) => k.id === id);
  if (!c) return null;
  const dx = x - c.x, dy = y - c.y;
  if (!dx && !dy) return [];
  c.x = x; c.y = y;
  st.router.moveShape(st.shapes[id], dx, dy);
  for (const l of st.labels[id] || []) st.router.moveShape(l, dx, dy);
  st.router.processTransaction();
  return st.compose();
}
