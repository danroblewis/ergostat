// the measuring diagram_audit.py does, run in the page: what it returns is printed
(() => {
  const lay = S.layout, g = S.graph, byId = Object.fromEntries(g.nodes.map(n => [n.id, n])), eById = Object.fromEntries(g.edges.map(e => [e.id, e]));
  const pts = le => { const s = (le.sections||[])[0]; return s ? [s.startPoint, ...(s.bendPoints||[]), s.endPoint] : []; };
  const segs = le => { const p = pts(le); return p.slice(1).map((b, i) => [p[i], b]); };
  const hits = (a, b, r) => { // an axis-parallel segment through a rect (shrunk by 3)
    const x0 = Math.min(a.x, b.x), x1 = Math.max(a.x, b.x), y0 = Math.min(a.y, b.y), y1 = Math.max(a.y, b.y);
    return x1 > r.x + 3 && x0 < r.x + r.width - 3 && y1 > r.y + 3 && y0 < r.y + r.height - 3; };
  const out = { through: [], overlap: [], detour: [] };
  // a net: lines leaving or reaching one point (one port, or one part, of one kind) together
  const valveish = (id) => ["valve", "disturbance"].includes(byId[id]?.kind);
  const info = (e) => e.kind !== "pipe";
  const isNet = (ea, eb) => (ea.sourcePort && ea.sourcePort === eb.sourcePort) || (ea.targetPort && ea.targetPort === eb.targetPort) ||
    (ea.kind === eb.kind && ((ea.source === eb.source && !ea.sourcePort && !eb.sourcePort) || (ea.target === eb.target && !ea.targetPort && !eb.targetPort))) ||
    (info(ea) && info(eb) && ((ea.source === eb.source && valveish(ea.source)) || (ea.target === eb.target && valveish(ea.target))));   // one point on a valve
  const owners = (id) => { const e = eById[id]; return [e.source, e.target]; };
  for (const le of lay.edges) {
    const e = eById[le.id]; if (!e) continue;
    for (const [a, b] of segs(le)) for (const c of lay.children) {
      if (owners(le.id).includes(c.id) || byId[c.id]?.kind === "cloud") continue;
      if (hits(a, b, c)) { out.through.push(`${e.kind} ${le.id} through ${c.id}`); break; }
    }
    const p = pts(le), L = p.slice(1).reduce((s, q, i) => s + Math.abs(q.x - p[i].x) + Math.abs(q.y - p[i].y), 0);
    const M = Math.abs(p[0].x - p[p.length-1].x) + Math.abs(p[0].y - p[p.length-1].y);
    if (L > 1.6 * M + 120) out.detour.push(`${e.kind} ${le.id}: ${Math.round(L)} for ${Math.round(M)}`);
  }
  const all = lay.edges.flatMap(le => segs(le).map(s => [le.id, s]));
  const seen = new Set();
  for (let i = 0; i < all.length; i++) for (let j = i + 1; j < all.length; j++) {
    const [ia, [a, b]] = all[i], [ib, [c, d]] = all[j];
    if (ia === ib) continue;
    const ea = eById[ia], eb = eById[ib];
    if (isNet(ea, eb)) continue; // a net
    let ov = 0;
    if (Math.abs(a.y - b.y) < 1 && Math.abs(c.y - d.y) < 1 && Math.abs(a.y - c.y) < 3) ov = Math.min(Math.max(a.x,b.x), Math.max(c.x,d.x)) - Math.max(Math.min(a.x,b.x), Math.min(c.x,d.x));
    if (Math.abs(a.x - b.x) < 1 && Math.abs(c.x - d.x) < 1 && Math.abs(a.x - c.x) < 3) ov = Math.min(Math.max(a.y,b.y), Math.max(c.y,d.y)) - Math.max(Math.min(a.y,b.y), Math.min(c.y,d.y));
    const k = [ia, ib].sort().join(" & ");
    if (ov > 20 && !seen.has(k)) { seen.add(k); out.overlap.push(`${k}: ${Math.round(ov)}px`); }
  }
  // crossings: a horizontal piece of one line through a vertical piece of another (not at their ends,
  // not lines that share a part); and those between lines of one net, which should never happen
  const ends = (id) => { const e = eById[id]; return new Set([e.source, e.target]); };
  out.crossings = 0; out.netCrossings = [];
  const counted = new Set();
  for (let i = 0; i < all.length; i++) for (let j = i + 1; j < all.length; j++) {
    const [ia, [a, b]] = all[i], [ib, [c, d]] = all[j];
    if (ia === ib) continue;
    const ea = eById[ia], eb = eById[ib];
    const hv = (p, q, r, s) => Math.abs(p.y - q.y) < 1 && Math.abs(r.x - s.x) < 1 &&
      r.x > Math.min(p.x, q.x) + 2 && r.x < Math.max(p.x, q.x) - 2 && p.y > Math.min(r.y, s.y) + 2 && p.y < Math.max(r.y, s.y) - 2;
    if (!(hv(a, b, c, d) || hv(c, d, a, b))) continue;
    const shared = [...ends(ia)].some((x) => ends(ib).has(x));
    if (isNet(ea, eb)) { out.netCrossings.push(`${ia} & ${ib}`); continue; }
    if (!shared) { out.crossings++; counted.add(ia); counted.add(ib); }
  }
  // bends: the corners in each line; pipes should have as few as can be
  out.pipeBends = 0; out.infoBends = 0; out.mostPipeBends = [0, ""];
  for (const le of lay.edges) {
    const e = eById[le.id]; if (!e) continue;
    const n = Math.max(0, pts(le).length - 2);
    if (e.kind === "pipe") { out.pipeBends += n; if (n > out.mostPipeBends[0]) out.mostPipeBends = [n, le.id]; }
    else out.infoBends += n;
  }
  // parts on top of each other, and open systems' outlines over parts not in them or over each other
  // (one inside the other is nesting): a layout that packs must still keep them apart
  out.partOverlap = [];
  const meet = (a, b, m = 2) => a.x + m < b.x + b.width && b.x + m < a.x + a.width && a.y + m < b.y + b.height && b.y + m < a.y + a.height;
  const inside = (a, b) => a.x >= b.x - 1 && a.y >= b.y - 1 && a.x + a.width <= b.x + b.width + 1 && a.y + a.height <= b.y + b.height + 1;
  const kids = lay.children;
  for (let i = 0; i < kids.length; i++) for (let j = i + 1; j < kids.length; j++)
    if (meet(kids[i], kids[j])) out.partOverlap.push(`${kids[i].id} on ${kids[j].id}`);
  const hulls = lay.containers || [];
  for (const h of hulls) {
    for (const c of kids) if (!(byId[c.id]?.systems || []).includes(h.name) && meet(c, h)) out.partOverlap.push(`${c.id} on the outline of ${h.name}`);
    for (const o of hulls) if (o !== h && o.name < h.name && meet(o, h) && !inside(o, h) && !inside(h, o)) out.partOverlap.push(`outlines of ${o.name} and ${h.name}`);
  }
  // compactness: the drawing's extent (parts, their labels, open systems' outlines, lines), how much of
  // it the parts fill, and the zoom at which all of it fits the canvas (1 or more: it is read at full size)
  const ext = { x0: Infinity, y0: Infinity, x1: -Infinity, y1: -Infinity };
  const grow = (x0, y0, x1, y1) => { ext.x0 = Math.min(ext.x0, x0); ext.y0 = Math.min(ext.y0, y0); ext.x1 = Math.max(ext.x1, x1); ext.y1 = Math.max(ext.y1, y1); };
  let filled = 0;
  for (const c of lay.children) {
    grow(c.x, c.y, c.x + c.width, c.y + c.height);
    filled += c.width * c.height;
    for (const l of c.labels || []) { grow(c.x + l.x, c.y + l.y, c.x + l.x + l.width, c.y + l.y + l.height); filled += l.width * l.height; }
  }
  for (const c of lay.containers || []) grow(c.x, c.y, c.x + c.width, c.y + c.height);
  for (const le of lay.edges) for (const p of pts(le)) grow(p.x, p.y, p.x, p.y);
  const W = Math.max(1, ext.x1 - ext.x0), H = Math.max(1, ext.y1 - ext.y0);
  const r = document.querySelector("svg.canvas")?.getBoundingClientRect() || { width: 1300, height: 900 };
  out.size = { width: Math.round(W), height: Math.round(H), aspect: +(W / H).toFixed(2), fill: +(filled / (W * H)).toFixed(3),
               empty: +(1 - filled / (W * H)).toFixed(3), fit: +Math.min((r.width - 40) / W, (r.height - 90) / H).toFixed(3),
               parts: lay.children.length };
  return out;
})
