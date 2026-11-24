/* a graph of one named kind (SPEC §4e, A graph): the chart family that draws nodes and edges. The layout is never in
   the answer: ELK works it out in a Web Worker (graph-layout.js), layered for every kind but impact (radial); a
   sequence diagram's fixed axes are not drawn here. One layout is kept for each set of nodes and edges, so a refresh
   that changes only values moves no node. What a node or an edge holds is said on hover; one that holds others says
   how many; an unhealthy one is marked; an edge only declared (never seen) is dashed, one whose wait is met is muted,
   and the critical path is heavy. When a route through two edges is not evidence (paths_real false), it says so */
"use strict";

(() => {
  const F = plotFrame, N = () => panelNumbers;
  const ALGORITHM = { process: "layered", conformance: "layered", dependency: "layered", wait_for: "layered",
                      service: "layered", lineage: "layered", impact: "radial" };
  const NODE_W = 112, NODE_H = 30, KEPT = 16, LABEL = 15;
  const laid = new Map();                    // a structure's key: its layout (a promise), the latest few
  const by = { worker: 0, page: 0 };         // where each layout was worked out
  const GIVE_UP_MS = 10000;
  let offThread;

  function inWorker(graph) {
    if (offThread === undefined) {
      try { offThread = new ELK({ workerFactory: () => new Worker("/static/graph-layout.js") }); } catch { offThread = null; }
    }
    if (!offThread) return Promise.reject(new Error("no layout worker"));
    const late = new Promise((_, no) => setTimeout(() => no(new Error("the layout worker did not answer")), GIVE_UP_MS));
    return Promise.race([offThread.layout(graph), late]).then((lay) => { by.worker++; return lay; });
  }
  /* the layout of r's structure; on the page's own thread only when no worker can lay it out (a panel's 40 nodes) */
  function layoutOf(r) {
    const n = r.nodes, e = r.edges, key = JSON.stringify([r.kind, n.id, e.source, e.target]);
    if (!laid.has(key)) {
      const at = new Map(n.id.map((id, i) => [id, `n${i}`]));
      const graph = { id: "root", layoutOptions: { "elk.algorithm": ALGORITHM[r.kind] || "layered", "elk.direction": "RIGHT",
                                                   "elk.spacing.nodeNode": "16", "elk.layered.spacing.nodeNodeBetweenLayers": "34" },
                      children: n.id.map((_, i) => ({ id: `n${i}`, width: NODE_W, height: NODE_H })),
                      edges: e.id.map((_, i) => ({ id: `e${i}`, sources: [at.get(e.source[i])], targets: [at.get(e.target[i])] })) };
      laid.set(key, inWorker(graph).catch(() => elk.layout(graph).then((lay) => { by.page++; return lay; })));
      while (laid.size > KEPT) laid.delete(laid.keys().next().value);
    }
    return laid.get(key);
  }

  const short = (t) => (String(t).length > LABEL ? `${String(t).slice(0, LABEL - 1)}…` : String(t));
  function words(r, part, i) {
    const x = r[part], label = (id) => r.nodes.label[r.nodes.id.indexOf(id)] ?? id;
    const out = [part === "nodes" ? x.label[i] : `${label(x.source[i])} → ${label(x.target[i])} (${x.relation[i]}, ${x.evidence[i]})`];
    if ((x.holds?.[i] || 1) > 1) out.push(`holds ${x.holds[i]}`);
    if (x.n?.[i] != null) out.push(`n ${x.n[i]}`);
    for (const f of x.fields || []) {
      if (f.values[i] == null) continue;
      const who = x.worst?.[i]?.[f.name];
      out.push(`${f.name} ${N().formatValue(f.values[i], N().parseUnit(f.unit))}${who ? ` (the worst, ${who})` : ""}`);
    }
    if (part === "edges" && x.last_seen) out.push(x.last_seen[i] == null ? "not seen in this window" : `last seen ${F.whenText(x.last_seen[i])}`);
    return out.join(" · ");
  }
  const marked = (x, name, i) => (x.fields || []).some((f) => f.name === name && f.values[i] > 0);

  function drawGraph(target, first, config, opts) {
    const root = h("div", { class: "graph-panel", role: "img", "aria-label": opts.label || "Graph" });
    target.append(root);
    let result = first, alive = true, model = { nodes: 0, edges: 0, by, at: {} };
    async function render() {
      const r = result, lay = await layoutOf(r);
      if (!alive || r !== result) return;
      const n = r.nodes, e = r.edges, at = {};
      lay.children.forEach((c, i) => { at[n.id[i]] = [c.x, c.y]; });
      const svg = s("svg", { class: "graph-svg", viewBox: `-4 -4 ${(lay.width || NODE_W) + 8} ${(lay.height || NODE_H) + 8}`, preserveAspectRatio: "xMidYMid meet" },
        s("defs", {}, s("marker", { id: "graph-arrow", viewBox: "0 0 8 8", refX: 7, refY: 4, markerWidth: 7, markerHeight: 7, orient: "auto-start-reverse" },
          s("path", { d: "M0,0 L8,4 L0,8 z", class: "graph-arrow" }))));
      const mid = (id) => [at[id][0] + NODE_W / 2, at[id][1] + NODE_H / 2];
      (lay.edges || []).forEach((le, i) => {
        const sec = le.sections?.[0];
        const pts = sec ? [sec.startPoint, ...(sec.bendPoints || []), sec.endPoint].map((p) => [p.x, p.y]) : [mid(e.source[i]), mid(e.target[i])];
        const cls = ["graph-edge", e.evidence[i] === "declared" && r.kind !== "dependency" ? "is-declared" : "", e.relation[i] === "met" ? "is-met" : "",
                     marked(e, "critical", i) ? "is-critical" : ""].filter(Boolean).join(" ");
        const g = s("g", { class: cls, "data-id": e.id[i], "data-holds": e.holds?.[i] || 1, onpointerenter: () => opts.readout?.(words(r, "edges", i)) },
          s("path", { d: `M${pts.map((p) => p.join(",")).join(" L")}`, "marker-end": "url(#graph-arrow)" }), s("title", {}, words(r, "edges", i)));
        if ((e.holds?.[i] || 1) > 1) { const [x, y] = pts[Math.floor(pts.length / 2)]; g.append(s("text", { x, y: y - 3, class: "graph-holds" }, `×${e.holds[i]}`)); }
        svg.append(g);
      });
      n.id.forEach((id, i) => {
        const holds = n.holds?.[i] || 1, [x, y] = at[id];
        const cls = ["graph-node", n.health?.[i] === "unhealthy" ? "is-unhealthy" : "", marked(n, "critical", i) ? "is-critical" : "",
                     holds > 1 ? "is-group" : ""].filter(Boolean).join(" ");
        svg.append(s("g", { class: cls, "data-id": id, "data-holds": holds, transform: `translate(${x},${y})`,
                            onpointerenter: () => opts.readout?.(words(r, "nodes", i)) },
          s("rect", { width: NODE_W, height: NODE_H, rx: holds > 1 ? 9 : 3 }),
          s("text", { x: 6, y: NODE_H / 2 + 4 }, short(n.label[i]) + (holds > 1 ? ` (${holds})` : "")), s("title", {}, words(r, "nodes", i))));
      });
      root.replaceChildren(svg);
      const notes = [];
      if (!r.semantics?.paths_real) notes.push({ text: "A route through two lines is not evidence that anything took it" });
      if (e.evidence.includes("declared") && r.kind !== "dependency") notes.push({ text: "dashed: declared, not seen in this window", mark: F.svgLine({ "stroke-dasharray": "3 2" }) });
      if (e.relation.includes("met")) notes.push({ text: "muted: what it waited on is finished", mark: F.svgLine({ opacity: 0.4 }) });
      if (n.id.some((_, i) => marked(n, "critical", i))) notes.push({ text: "heavy: the critical path", mark: F.svgLine({ "stroke-width": 3 }) });
      F.legend(opts.legend, [], notes);
      model = { nodes: n.id.length, edges: e.id.length, by: { ...by }, at, notes: notes.map((x) => x.text) };
      frame.paints++;
    }
    const frame = { paints: 0 };
    const go = () => render().catch((err) => {
      if (!alive) return;
      root.replaceChildren(h("p", { class: "panel-message-text" }, `The graph could not be laid out: ${err.message}`));
      frame.paints++;
    });
    go();
    return { update(next) { result = next; go(); }, destroy() { alive = false; root.remove(); }, model: () => model, frame };
  }

  registerPlotForm("graph", { label: "Graph", group: "structure", needs: { text: "a graph" }, draw: drawGraph,
    shapes: { graph: {} }, reshape: "ask for a graph: {\"source\": \"graph\", \"diagram\": \"dependency\"}",
    check: (r) => (r.kind === "sequence" ? "A sequence diagram is drawn on fixed axes, which this panel does not draw: show it as a Table." : ""),
    options: [] });
})();
