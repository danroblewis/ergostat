/* lines that share a point, put in order by where they go: libavoid spreads the lines leaving one
   point side by side, but in an order of its own, and one that turns off early may then cross the
   others. Here the lines of each shared point that leave the same way and then turn the same way (a
   comb) take their lanes and turning places again, the line going furthest turning furthest and on
   the outside, so that none crosses another. A comb is changed only if that leaves fewer crossings
   among its lines and nothing worse with any other line or part.
   Then any two lines from one place (or to one place) that still cross trade ways where they cross:
   each keeps its own end, the two now meet there and part again. They carry the same thing from the
   same place, so which way is which does not matter, and every other line, part and crossing stays
   as it was. */
"use strict";

function untangle(lay, groups, rects, endsOf) {
  const byLe = Object.fromEntries(lay.edges.map((le) => [le.id, le]));
  const pts = (le) => { const s = (le.sections || [])[0]; return s ? [s.startPoint, ...(s.bendPoints || []), s.endPoint] : []; };
  const put = (le, p) => { le.sections = [{ startPoint: p[0], bendPoints: p.slice(1, -1), endPoint: p[p.length - 1] }]; };
  const segs = (p) => p.slice(1).map((b, i) => [p[i], b]);
  const cross = (pa, pb) => {                            // how many times two lines cross (not at their ends)
    let n = 0;
    const hv = (p, q, r, s) => Math.abs(p.y - q.y) < 1 && Math.abs(r.x - s.x) < 1 &&
      r.x > Math.min(p.x, q.x) + 2 && r.x < Math.max(p.x, q.x) - 2 && p.y > Math.min(r.y, s.y) + 2 && p.y < Math.max(r.y, s.y) - 2;
    for (const [a, b] of segs(pa)) for (const [c, d] of segs(pb)) if (hv(a, b, c, d) || hv(c, d, a, b)) n++;
    return n;
  };
  const along = (a, b) => {                              // how long two lines run on top of each other
    let n = 0;
    for (const [p, q] of segs(a)) for (const [r, s] of segs(b)) {
      if (Math.abs(p.y - q.y) < 1 && Math.abs(r.y - s.y) < 1 && Math.abs(p.y - r.y) < 3)
        n += Math.max(0, Math.min(Math.max(p.x, q.x), Math.max(r.x, s.x)) - Math.max(Math.min(p.x, q.x), Math.min(r.x, s.x)));
      if (Math.abs(p.x - q.x) < 1 && Math.abs(r.x - s.x) < 1 && Math.abs(p.x - r.x) < 3)
        n += Math.max(0, Math.min(Math.max(p.y, q.y), Math.max(r.y, s.y)) - Math.max(Math.min(p.y, q.y), Math.min(r.y, s.y)));
    }
    return n;
  };
  const through = (p, own) => segs(p).filter(([a, b]) => rects.some((r) => !own.includes(r.id) &&
    Math.max(a.x, b.x) > r.x + 3 && Math.min(a.x, b.x) < r.x + r.width - 3 && Math.max(a.y, b.y) > r.y + 3 && Math.min(a.y, b.y) < r.y + r.height - 3)).length;

  for (const g of groups) {
    const lines = g.ids.map((id) => byLe[id]).filter((le) => le && pts(le).length >= 2);
    // each line from the shared point outwards (a group of arriving lines is read backwards)
    const out = (le) => (g.end === "s" ? pts(le) : pts(le).slice().reverse()).map((p) => ({ x: p.x, y: p.y }));
    const back = (p) => (g.end === "s" ? p : p.slice().reverse());
    const dirOf = (a, b) => (Math.abs(a.x - b.x) < 0.5 ? (b.y < a.y ? "up" : "down") : (b.x < a.x ? "left" : "right"));
    const combs = {};
    for (const le of lines) {
      const p = out(le);
      if (p.length < 3) continue;                        // a straight line: nothing to order
      const key = dirOf(p[0], p[1]) + "|" + dirOf(p[1], p[2]);
      (combs[key] ||= []).push({ le, p });
    }
    for (const [key, comb] of Object.entries(combs)) {
      if (comb.length < 2) continue;
      const [d0, d1] = key.split("|");
      const vert = d0 === "up" || d0 === "down";
      const A = vert ? "y" : "x", L = vert ? "x" : "y";  // A: along the way out; L: across it (the lanes)
      const sgnA = d0 === "up" || d0 === "left" ? -1 : 1, sgnT = d1 === "up" || d1 === "left" ? -1 : 1;
      // where each goes: how far out it ends up (the end of its third piece, else of its second)
      const far = (p) => sgnA * (p[Math.min(3, p.length - 1)][A] - p[0][A]);
      const lanes = comb.map((c) => c.p[0][L]).sort((a, b) => (a - b) * sgnT);     // the lanes away from the turn first
      const depths = comb.map((c) => c.p[1][A]).sort((a, b) => (b - a) * sgnA);   // the furthest out first
      // how far each reaches the way it turns: the one reaching least takes the lane away from the turn
      const reach = (p) => sgnT * (p[2][L] - p[0][L]);
      const orders = [
        (a, b) => far(b.p) - far(a.p),
        (a, b) => reach(a.p) - reach(b.p),
        (a, b) => reach(a.p) - reach(b.p) || far(b.p) - far(a.p),
        (a, b) => far(b.p) - far(a.p) || reach(a.p) - reach(b.p),
      ];
      const before = comb.map((c) => back(c.p));
      // keep an order only if it is better among them and no worse with anything else; the best of those tried
      const others = lay.edges.filter((le) => !comb.some((c) => c.le === le)).map((le) => pts(le));
      const score = (ps, les) => {
        let inside = 0, outside = 0, thr = 0, ov = 0;
        for (let i = 0; i < ps.length; i++) {
          for (let j = i + 1; j < ps.length; j++) inside += cross(ps[i], ps[j]);
          for (const op of others) { outside += cross(ps[i], op); ov += along(ps[i], op) > 20 ? 1 : 0; }
          thr += through(ps[i], endsOf[les[i].id] || []);
        }
        return { inside, outside, thr, ov };
      };
      const s0 = score(before, comb.map((c) => c.le));
      let best = null;
      for (const by of orders) {
        const after = comb.slice().sort(by).map((c, i) => {
          const p = c.p.map((q) => ({ ...q }));
          p[0][L] = lanes[i]; p[1][L] = lanes[i]; p[1][A] = depths[i]; p[2][A] = depths[i];
          return { c, p: back(p) };
        });
        const s1 = score(after.map((a) => a.p), after.map((a) => a.c.le));
        if (s1.inside < s0.inside && s1.outside <= s0.outside && s1.thr <= s0.thr && s1.ov <= s0.ov &&
            (!best || s1.inside < best.s.inside || (s1.inside === best.s.inside && s1.outside < best.s.outside))) best = { s: s1, after };
      }
      if (best) for (const a of best.after) put(a.c.le, a.p);
    }
  }
}

/* lines of one net that cross: they trade their ways from their shared end to where they cross */
function uncross(lay, g) {
  const edge = Object.fromEntries(g.edges.map((e) => [e.id, e]));
  const kind = Object.fromEntries(g.nodes.map((n) => [n.id, n.kind]));
  const valveish = (id) => kind[id] === "valve" || kind[id] === "disturbance";
  const pts = (le) => { const s = (le.sections || [])[0]; return s ? [s.startPoint, ...(s.bendPoints || []), s.endPoint] : []; };
  const put = (le, p) => {
    const r = p.filter((q, i) => i === 0 || Math.abs(q.x - p[i - 1].x) + Math.abs(q.y - p[i - 1].y) > 0.5)
      .filter((q, i, a) => i === 0 || i === a.length - 1 ||
        !((Math.abs(a[i - 1].x - q.x) < 0.5 && Math.abs(q.x - a[i + 1].x) < 0.5) || (Math.abs(a[i - 1].y - q.y) < 0.5 && Math.abs(q.y - a[i + 1].y) < 0.5)));
    le.sections = [{ startPoint: r[0], bendPoints: r.slice(1, -1), endPoint: r[r.length - 1] }];
  };
  const len = (p) => p.slice(1).reduce((s, q, i) => s + Math.abs(q.x - p[i].x) + Math.abs(q.y - p[i].y), 0);
  const detour = (p) => len(p) > 1.6 * (Math.abs(p[0].x - p[p.length - 1].x) + Math.abs(p[0].y - p[p.length - 1].y)) + 120;
  // the first place (from the start) where two lines cross: [index of the piece in a, in b, the point]
  const firstCross = (a, b) => {
    let best = null;
    for (let i = 1; i < a.length; i++) for (let j = 1; j < b.length; j++) {
      const [p, q, r, s] = [a[i - 1], a[i], b[j - 1], b[j]];
      let x = null;
      const hv = (p, q, r, s) => Math.abs(p.y - q.y) < 1 && Math.abs(r.x - s.x) < 1 &&
        r.x > Math.min(p.x, q.x) + 2 && r.x < Math.max(p.x, q.x) - 2 && p.y > Math.min(r.y, s.y) + 2 && p.y < Math.max(r.y, s.y) - 2;
      if (hv(p, q, r, s)) x = { x: r.x, y: p.y };
      else if (hv(r, s, p, q)) x = { x: p.x, y: r.y };
      if (!x) continue;
      const d = len([...a.slice(0, i), x]);
      if (!best || d < best[3]) best = [i, j, x, d];
    }
    return best;
  };
  // nets: lines that leave (or reach) one part with one kind, one port, or a valve's stem
  const nets = {};
  for (const le of lay.edges) {
    const e = edge[le.id];
    if (!e || le.cut) continue;
    for (const w of ["s", "t"]) {
      const id = w === "s" ? e.source : e.target, port = w === "s" ? e.sourcePort : e.targetPort;
      const key = port ? `${w}|port|${port}` : valveish(id) && e.kind !== "pipe" ? `${w}|${id}|stem` : `${w}|${id}|${e.kind}`;
      (nets[key] ||= { w, les: [] }).les.push(le);
    }
  }
  // (a trade in one net can make a crossing in another: until none is left anywhere, or a bound)
  for (let pass = 0, any = true; pass < 20 && any; pass++) {
    any = false;
    for (const { w, les } of Object.values(nets)) {
    if (les.length < 2) continue;
    const way = (le) => (w === "s" ? pts(le) : pts(le).slice().reverse()).map((p) => ({ x: p.x, y: p.y }));
    for (let round = 0; round < 50; round++) {          // each trade removes a crossing among them: until none is left
      let traded = false;
      for (let i = 0; i < les.length && !traded; i++) for (let j = i + 1; j < les.length && !traded; j++) {
        const a = way(les[i]), b = way(les[j]), c = firstCross(a, b);
        if (!c) continue;
        const [ia, jb, x] = c;
        const a2 = [...b.slice(0, jb), x, ...a.slice(ia)], b2 = [...a.slice(0, ia), x, ...b.slice(jb)];
        const back = (p) => (w === "s" ? p : p.slice().reverse());
        if (detour(a2) || detour(b2)) continue;
        put(les[i], back(a2)); put(les[j], back(b2));
        traded = any = true;
      }
      if (!traded) break;
    }
    }
  }
}
