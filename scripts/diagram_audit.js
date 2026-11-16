// the measuring diagram_audit.py does, run in the page: what it returns is printed
(() => {
  const lay = S.layout, g = S.graph, byId = Object.fromEntries(g.nodes.map(n => [n.id, n])), eById = Object.fromEntries(g.edges.map(e => [e.id, e]));
  const pts = le => { const s = (le.sections||[])[0]; return s ? [s.startPoint, ...(s.bendPoints||[]), s.endPoint] : []; };
  const segs = le => { const p = pts(le); return p.slice(1).map((b, i) => [p[i], b]); };
  const hits = (a, b, r) => { // an axis-parallel segment through a rect (shrunk by 3)
    const x0 = Math.min(a.x, b.x), x1 = Math.max(a.x, b.x), y0 = Math.min(a.y, b.y), y1 = Math.max(a.y, b.y);
    return x1 > r.x + 3 && x0 < r.x + r.width - 3 && y1 > r.y + 3 && y0 < r.y + r.height - 3; };
  const out = { through: [], overlap: [], detour: [] };
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
    if (ea.kind === eb.kind && ((ea.source === eb.source && (ea.sourcePort || "") === (eb.sourcePort || "")) ||
                                (ea.target === eb.target && (ea.targetPort || "") === (eb.targetPort || "")))) continue; // a net
    let ov = 0;
    if (Math.abs(a.y - b.y) < 1 && Math.abs(c.y - d.y) < 1 && Math.abs(a.y - c.y) < 3) ov = Math.min(Math.max(a.x,b.x), Math.max(c.x,d.x)) - Math.max(Math.min(a.x,b.x), Math.min(c.x,d.x));
    if (Math.abs(a.x - b.x) < 1 && Math.abs(c.x - d.x) < 1 && Math.abs(a.x - c.x) < 3) ov = Math.min(Math.max(a.y,b.y), Math.max(c.y,d.y)) - Math.max(Math.min(a.y,b.y), Math.min(c.y,d.y));
    const k = [ia, ib].sort().join(" & ");
    if (ov > 20 && !seen.has(k)) { seen.add(k); out.overlap.push(`${k}: ${Math.round(ov)}px`); }
  }
  return out;
})
