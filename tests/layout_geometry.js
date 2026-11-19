// the drawn geometry of the diagram on the page, for the layout rules (tests/layout_rules.py): every part's
// box and its labels' boxes, every line's points, the open systems' outlines (frames), the canvas, in the
// diagram's own coordinates. What the rules read is only this, so a run's geometry can be saved and judged again
(() => {
  const lay = S.layout, g = S.graph;
  if (!lay || !g) return null;
  const byId = Object.fromEntries(g.nodes.map((n) => [n.id, n]));
  const eById = Object.fromEntries(g.edges.map((e) => [e.id, e]));
  const r2 = (v) => Math.round(v * 10) / 10;
  const nodes = [];
  for (const c of lay.children) {
    const n = byId[c.id];
    if (!n) continue;
    nodes.push({
      id: c.id, kind: n.kind || "", role: n.role || "", label: n.label || "",
      x: r2(c.x), y: r2(c.y), w: r2(c.width), h: r2(c.height),
      labels: (c.labels || []).map((l) => [r2(c.x + l.x), r2(c.y + l.y), r2(l.width), r2(l.height)]),
      systems: n.systems || [], turn: c.turn || null, pinned: !!(S.pins || {})[c.id],
    });
  }
  const edges = [];
  for (const le of lay.edges) {
    const e = eById[le.id];
    const s0 = (le.sections || [])[0];
    if (!e || !s0) continue;
    edges.push({
      id: le.id, kind: e.kind || "", source: e.source, target: e.target,
      sourcePort: e.sourcePort || null, targetPort: e.targetPort || null,
      pts: [s0.startPoint, ...(s0.bendPoints || []), s0.endPoint].map((p) => [r2(p.x), r2(p.y)]),
      labels: (le.labels || []).map((l) => [r2(l.x), r2(l.y), r2(l.width), r2(l.height)]),
    });
  }
  const frames = (lay.containers || []).map((c) => ({ id: c.id || c.name, name: c.name || c.id, x: r2(c.x), y: r2(c.y), w: r2(c.width), h: r2(c.height), depth: c.depth || 0 }));
  const cv = document.querySelector("svg.canvas")?.getBoundingClientRect() || { width: 1300, height: 800 };
  // where the diagram's coordinates are on the screen (for crops of a screenshot)
  const v = S.view || { k: 1, x: 0, y: 0 };
  // every word drawn, as drawn (whatever placed it), and every loop marker: each with what it belongs to
  const box = (el) => { const b = el.getBoundingClientRect();
    return [r2((b.left - cv.left - v.x) / v.k), r2((b.top - cv.top - v.y) / v.k), r2(b.width / v.k), r2(b.height / v.k)]; };
  const texts = [], markers = [];
  for (const t of document.querySelectorAll("svg.canvas #viewport text")) {
    if (!(t.textContent || "").trim() || getComputedStyle(t).display === "none" || t.closest("[display=none]")) continue;
    const b = box(t);
    if (b[2] <= 0 || b[3] <= 0) continue;
    const node = t.closest("g.node"), edge = t.closest("g.edge"), mk = t.closest("g.loop-marker"), hull = t.closest("g.hull, g.sys-hull");
    texts.push({ box: b, text: t.textContent.trim().slice(0, 40), node: node?.dataset.id || null, edge: edge?.dataset.id || null,
                 marker: mk?.dataset.loop || null, hull: hull ? (hull.dataset.hull || "hull") : null, cls: t.getAttribute("class") || "" });
  }
  for (const m of document.querySelectorAll("svg.canvas #viewport g.loop-marker")) {
    const c = m.querySelector("path.marker-arc") || m.querySelector("circle.marker-hit");
    if (c) markers.push({ loop: m.dataset.loop, box: box(c) });
  }
  return { view: g.kind, nodes, edges, frames, texts, markers, canvas: [Math.round(cv.left || 0), Math.round(cv.top || 0), Math.round(cv.width), Math.round(cv.height)],
           zoom: [v.k, v.x, v.y], routed: !lay.routing, invalid: (typeof AV !== "undefined" && AV.invalid) || 0 };
})()
