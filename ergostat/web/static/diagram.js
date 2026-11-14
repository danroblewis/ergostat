/* the control and wiring diagrams: shapes, ELK layout, drawing, pan and zoom, the side panel */
"use strict";
/* ------------------------------------------------------------------ the diagram */

const SIZE = { stock: [168, 84], valve: [40, 40], disturbance: [40, 40], cloud: [54, 36], sensor: [44, 44], controller: [200, 92], agent: [210, 92] };
const CH = 6.7;   // px per character, for label sizes

function labelLines(n) {
  if (n.kind === "valve") return [n.label, `${n.position != null ? "open " + fmt(n.position) + " · " : ""}${n.rateText}${n.mode && n.mode !== "auto" ? " · " + n.mode : ""}`, n.agent ? "§badge" : null].filter(Boolean);
  if (n.kind === "disturbance") return [n.label, `${n.rateText}${n.estimated ? " (est.)" : ""}`];
  if (n.kind === "sensor") return [n.label, n.reading != null ? `reads ${n.reading}` : "no reading", n.agent ? "§badge" : null].filter(Boolean);
  return [];
}
function badgeText(a) { return a ? `${a.kind} · ${a.name}${a.when ? " · " + a.when : ""}` : ""; }
function textWidth(t) { return t.length * CH; }

function sig(g) {
  return JSON.stringify([g.kind, g.nodes.map((n) => n.id).sort(), g.edges.map((e) => e.id).sort()]);
}

async function layoutGraph(g, aspect) {
  const ORDER = { cloud: 0, disturbance: 1, stock: 2, valve: 3, sensor: 5, controller: 6, agent: 2 };
  const rank = (n) => (n.kind === "cloud" ? (n.id.endsWith(":out") ? 4 : 0) : ORDER[n.kind] ?? 3);
  const nodesInOrder = [...g.nodes].sort((a, b) => rank(a) - rank(b));
  const children = nodesInOrder.map((n) => {
    let [w, hgt] = SIZE[n.kind] || [60, 40];
    if (n.kind === "stock") w = Math.max(w, textWidth(n.label) + 34);
    if (n.kind === "controller") w = Math.max(w, textWidth(n.label) + 110, textWidth("holds " + n.setpoint) + 60);
    const lines = labelLines(n);
    const node = { id: n.id, width: w, height: hgt, layoutOptions: {} };
    if (lines.length) {
      const lw = Math.max(...lines.map((l) => l === "§badge" ? textWidth(badgeText(n.agent)) + 18 : textWidth(l))) + 8;
      node.labels = [{ id: n.id + ":label", text: lines.join("\n"), width: lw, height: lines.length * 16 + 4 }];
      node.layoutOptions["elk.nodeLabels.placement"] = "OUTSIDE V_BOTTOM H_CENTER";
    }
    if (n.kind === "valve" || n.kind === "disturbance") {
      node.layoutOptions["elk.portConstraints"] = "FIXED_SIDE";
      node.ports = [
        { id: n.id + ":in", width: 1, height: 1, layoutOptions: { "elk.port.side": "WEST" } },
        { id: n.id + ":out", width: 1, height: 1, layoutOptions: { "elk.port.side": "EAST" } },
        { id: n.id + ":ctl", width: 1, height: 1, layoutOptions: { "elk.port.side": "NORTH" } },
      ];
    }
    return node;
  });
  const flowNode = new Set(g.nodes.filter((n) => n.kind === "valve" || n.kind === "disturbance").map((n) => n.id));
  const edges = g.edges.map((e) => {
    let src = e.source, dst = e.target;
    if (e.kind === "pipe") {
      if (flowNode.has(dst)) dst = dst + ":in";
      if (flowNode.has(src)) src = src + ":out";
    } else if (flowNode.has(dst)) dst = dst + ":ctl";
    else if (flowNode.has(src)) src = src + ":ctl";
    const out = { id: e.id, sources: [src], targets: [dst], layoutOptions: {} };
    if (e.kind === "pipe") { out.layoutOptions["elk.layered.priority.straightness"] = "20"; out.layoutOptions["elk.layered.priority.direction"] = "20"; out.layoutOptions["elk.layered.priority.shortness"] = "10"; }
    if (e.kind === "wire" && e.via && e.via.length) {
      const t = e.via.slice(0, 2).join(", ") + (e.via.length > 2 ? ` +${e.via.length - 2}` : "");
      out.labels = [{ id: e.id + ":l", text: t, width: textWidth(t) + 6, height: 14 }];
    }
    return out;
  });
  const graph = {
    id: "root", children, edges,
    layoutOptions: {
      "elk.algorithm": "layered", "elk.direction": g.kind === "wiring" ? "DOWN" : "RIGHT", "elk.edgeRouting": "ORTHOGONAL",
      "elk.layered.spacing.nodeNodeBetweenLayers": "64", "elk.spacing.nodeNode": "36", "elk.spacing.edgeNode": "18",
      "elk.spacing.edgeEdge": "12", "elk.layered.spacing.edgeNodeBetweenLayers": "18",
      "elk.layered.nodePlacement.strategy": "NETWORK_SIMPLEX", "elk.layered.crossingMinimization.semiInteractive": "false",
      "elk.layered.considerModelOrder.strategy": "NODES_AND_EDGES", "elk.separateConnectedComponents": "true",
      "elk.spacing.componentComponent": "70", "elk.spacing.labelNode": "6", "elk.edgeLabels.placement": "CENTER",
      "elk.layered.cycleBreaking.strategy": "GREEDY", "elk.aspectRatio": String(aspect || 1.6),
      "elk.layered.wrapping.strategy": S.wrap ? "MULTI_EDGE" : "OFF", "elk.layered.wrapping.additionalEdgeSpacing": "20",
      "elk.layered.wrapping.correctionFactor": "1.2", "elk.padding": "[top=40,left=40,bottom=40,right=40]",
    },
  };
  return elk.layout(graph);
}

/* node shapes, drawn with their top-left at 0,0 */
function badge(a, x, y) {
  if (!a) return null;
  const t = badgeText(a), w = textWidth(t) + 14;
  return s("g", { class: "badge", transform: `translate(${x - w / 2},${y})` },
    s("rect", { width: w, height: 16, rx: 8, fill: rungColor(a.rung) }),
    s("text", { x: w / 2, y: 11.5, "text-anchor": "middle" }, t));
}

function drawStock(n, w, hgt) {
  const g = s("g");
  const pts = n.points || [];
  const sp = S.graph?.loops ? Object.values(S.graph.loops).find((l) => l.stock === n.label) : null;
  let top = Math.max(...pts.map((p) => p[1]), n.value ?? 0, 1);
  let spv = null;
  if (sp) { const m = /(-?\d+(\.\d+)?)/.exec(sp.setpoint); if (m) { spv = +m[1]; top = Math.max(top, spv * 1.25); } }
  const frac = n.value == null ? 0 : Math.max(0, Math.min(1, n.value / top));
  const T = 24, H = hgt - T - 2;                       // the tank: below the title
  const tone = sp ? ({ off: "var(--bad)", holding: "var(--ok)", open: "var(--warn)" }[sp.status] || "var(--accent)") : "var(--accent)";
  g.append(s("rect", { class: "hit", width: w, height: hgt, rx: 3, fill: "var(--stock)", stroke: "var(--stock-line)", "stroke-width": 2,
                       "stroke-dasharray": n.outside ? "5 4" : null }));
  g.append(s("line", { x1: 0, x2: w, y1: T, y2: T, stroke: "var(--line)", "stroke-width": 1 }));
  g.append(s("rect", { x: 2, y: T + H * (1 - frac), width: w - 4, height: H * frac, fill: tone, opacity: 0.14 }));
  if (spv != null) {
    const y = T + H * (1 - Math.min(1, spv / top));
    g.append(s("line", { x1: 2, x2: w - 2, y1: y, y2: y, stroke: tone, "stroke-width": 1.2, "stroke-dasharray": "3 3", opacity: 0.9 }));
  }
  if (pts.length > 1) {
    const vs = pts.map((p) => p[1]), lo = Math.min(...vs), hi = Math.max(...vs) || 1;
    const d = vs.map((v, i) => `${i ? "L" : "M"}${10 + (i / (vs.length - 1)) * (w - 20)},${hgt - 8 - ((v - lo) / ((hi - lo) || 1)) * 16}`).join("");
    g.append(s("path", { d, fill: "none", stroke: tone, "stroke-width": 1.4, opacity: 0.8 }));
  }
  g.append(s("text", { x: 10, y: 17, class: "t-label" }, n.label));
  g.append(s("text", { x: 10, y: 50, class: "t-value" }, n.valueText, s("tspan", { class: "t-unit", dx: 4 }, n.unit || "")));
  return g;
}

function drawValve(n, w, hgt) {
  const g = s("g");
  const c = "var(--valve)";
  const m = n.mode || "auto";
  g.append(s("rect", { class: "hit", x: -2, y: -2, width: w + 4, height: hgt + 4, rx: 6, fill: "transparent", stroke: "transparent" }));
  g.append(s("path", { d: `M4,8 L${w / 2},${hgt / 2} L4,${hgt - 8} Z M${w - 4},8 L${w / 2},${hgt / 2} L${w - 4},${hgt - 8} Z`,
                       fill: m === "manual" ? "var(--panel)" : c, stroke: c, "stroke-width": 2, "stroke-linejoin": "round" }));
  if (m === "advise") g.append(s("path", { d: `M${w - 4},8 L${w / 2},${hgt / 2} L${w - 4},${hgt - 8} Z`, fill: "var(--panel)", stroke: c, "stroke-width": 2 }));
  g.append(s("line", { x1: w / 2, y1: hgt / 2, x2: w / 2, y2: 0, stroke: c, "stroke-width": 2 }));
  g.append(s("rect", { x: w / 2 - 7, y: -3, width: 14, height: 5, rx: 1.5, fill: c }));
  return g;
}

function drawDisturbance(n, w, hgt) {
  const g = s("g");
  g.append(s("path", { class: "hit", d: `M${w / 2},2 L${w - 2},${hgt / 2} L${w / 2},${hgt - 2} L2,${hgt / 2} Z`, fill: "var(--panel)", stroke: "var(--dist)", "stroke-width": 2 }));
  g.append(s("path", { d: `M${w * 0.25},${hgt / 2} q${w * 0.0625},-6 ${w * 0.125},0 t${w * 0.125},0 t${w * 0.125},0 t${w * 0.125},0`, fill: "none", stroke: "var(--dist)", "stroke-width": 2, "stroke-linecap": "round" }));
  return g;
}

function drawCloud(n, w, hgt) {
  const d = `M${w * 0.22},${hgt * 0.82} C${w * 0.02},${hgt * 0.82} ${w * 0.02},${hgt * 0.42} ${w * 0.22},${hgt * 0.45}
             C${w * 0.22},${hgt * 0.12} ${w * 0.55},${hgt * 0.08} ${w * 0.6},${hgt * 0.32}
             C${w * 0.7},${hgt * 0.12} ${w * 0.95},${hgt * 0.22} ${w * 0.86},${hgt * 0.5}
             C${w * 1.02},${hgt * 0.56} ${w * 0.98},${hgt * 0.84} ${w * 0.8},${hgt * 0.82} Z`;
  return s("g", {}, s("path", { class: "hit", d, fill: "var(--cloud)", stroke: "var(--muted)", "stroke-width": 1.4 }));
}

function drawSensor(n, w, hgt) {
  const r = w / 2;
  return s("g", {},
    s("circle", { class: "hit", cx: r, cy: r, r: r - 1, fill: "var(--sensor)", stroke: "var(--sensor-line)", "stroke-width": 2 }),
    s("path", { d: `M${r - 12},${r + 6} A13,13 0 0 1 ${r + 12},${r + 6}`, fill: "none", stroke: "var(--sensor-line)", "stroke-width": 2, "stroke-linecap": "round" }),
    s("line", { x1: r, y1: r + 6, x2: r + 7, y2: r - 4, stroke: "var(--sensor-line)", "stroke-width": 2.2, "stroke-linecap": "round" }),
    s("circle", { cx: r, cy: r + 6, r: 2.4, fill: "var(--sensor-line)" }));
}

function drawController(n, w, hgt) {
  const st = n.status || "unknown";
  const tone = { off: "var(--bad)", holding: "var(--ok)", open: "var(--warn)" }[st] || "var(--unknown)";
  const g = s("g");
  g.append(s("rect", { class: "hit", width: w, height: hgt, rx: 10, fill: "var(--ctl)", stroke: "var(--ctl-line)", "stroke-width": 2 }));
  g.append(s("circle", { cx: 20, cy: 22, r: 9, fill: "var(--panel)", stroke: "var(--ctl-line)", "stroke-width": 1.6 }));
  g.append(s("path", { d: "M14,22 h12 M20,16 v12", stroke: "var(--ctl-line)", "stroke-width": 1.4 }));
  g.append(s("text", { x: 36, y: 20, class: "t-label" }, n.label));
  g.append(s("text", { x: 36, y: 36, class: "t-sub" }, "holds " + n.setpoint));
  if (n.decision) {
    const room = Math.floor((w - 24) / 6.2);
    const t = n.decision.length > room ? n.decision.slice(0, room - 1) + "…" : n.decision;
    g.append(s("text", { x: 12, y: 56, class: "t-sub", "font-style": "italic" }, s("title", {}, n.decision), "“" + t + "”"));
  }
  g.append(s("circle", { cx: w - 14, cy: 16, r: 5, fill: tone }));
  g.append(s("text", { x: w - 24, y: 20, class: "t-sub", "text-anchor": "end", fill: tone }, st));
  const b = badge(n.agent, w / 2, hgt - 24);
  if (b) g.append(b);
  return g;
}

function drawAgent(n, w, hgt) {
  const g = s("g");
  g.append(s("rect", { class: "hit", width: w, height: hgt, rx: 10, fill: "var(--panel)", stroke: n.failing ? "var(--bad)" : "var(--line)", "stroke-width": 2 }));
  g.append(s("rect", { width: 6, height: hgt, rx: 3, fill: rungColor(n.rung) }));
  g.append(s("text", { x: 16, y: 20, class: "t-label" }, n.label));
  g.append(s("text", { x: w - 10, y: 20, class: "t-sub", "text-anchor": "end" }, `rung ${n.rung} · ${n.agentKind}`));
  const when = n.schedule || "";
  g.append(s("text", { x: 16, y: 38, class: "t-sub" }, when + (n.runs ? ` · ${n.runs} runs` : "")));
  (n.roles || []).slice(0, 3).forEach((r, i) => g.append(s("text", { x: 16, y: 56 + i * 14, class: "t-sub" }, `${r.kind} ${r.name}`)));
  return g;
}

const DRAW = { stock: drawStock, valve: drawValve, disturbance: drawDisturbance, cloud: drawCloud, sensor: drawSensor, controller: drawController, agent: drawAgent };

function roundedPath(pts, r = 8) {
  if (pts.length < 2) return "";
  let d = `M${pts[0].x},${pts[0].y}`;
  for (let i = 1; i < pts.length - 1; i++) {
    const p0 = pts[i - 1], p1 = pts[i], p2 = pts[i + 1];
    const d1 = Math.hypot(p1.x - p0.x, p1.y - p0.y), d2 = Math.hypot(p2.x - p1.x, p2.y - p1.y);
    const rr = Math.min(r, d1 / 2, d2 / 2);
    const a = { x: p1.x - ((p1.x - p0.x) / d1) * rr, y: p1.y - ((p1.y - p0.y) / d1) * rr };
    const b = { x: p1.x + ((p2.x - p1.x) / d2) * rr, y: p1.y + ((p2.y - p1.y) / d2) * rr };
    d += ` L${a.x},${a.y} Q${p1.x},${p1.y} ${b.x},${b.y}`;
  }
  const last = pts[pts.length - 1];
  return d + ` L${last.x},${last.y}`;
}

function edgePoints(e) {
  const sec = (e.sections || [])[0];
  if (!sec) return [];
  return [sec.startPoint, ...(sec.bendPoints || []), sec.endPoint];
}

function arrowHead(pts, cls, size = 7) {
  const a = pts[pts.length - 2], b = pts[pts.length - 1];
  const ang = Math.atan2(b.y - a.y, b.x - a.x);
  const p = (t) => `${b.x - size * Math.cos(ang + t)},${b.y - size * Math.sin(ang + t)}`;
  return s("path", { d: `M${p(-0.45)} L${b.x},${b.y} L${p(0.45)} Z`, class: cls });
}

function drawGraph(svg, g, lay) {
  const byId = Object.fromEntries(g.nodes.map((n) => [n.id, n]));
  const edgeById = Object.fromEntries(g.edges.map((e) => [e.id, e]));
  const vp = s("g", { id: "viewport" });
  // systems as hulls behind everything (overlapping freely)
  if (g.kind === "control" && S.showHulls) {
    const hulls = s("g", { class: "sys-hull" });
    const taken = [];                                   // label boxes already placed, so overlapping hulls never stack names
    (S.status?.systems || []).forEach((name, si) => {
      const hue = (210 + si * 137.5) % 360;          // the golden angle: neighbours never share a colour
      const boxes = lay.children.filter((c) => (byId[c.id]?.systems || []).includes(name)).map((c) => {
        const ls = c.labels || [];      // a node's box, with its labels outside it
        const xs = [c.x, c.x + c.width, ...ls.flatMap((l) => [c.x + l.x, c.x + l.x + l.width])];
        const ys = [c.y, c.y + c.height, ...ls.flatMap((l) => [c.y + l.y, c.y + l.y + l.height])];
        return { x: Math.min(...xs), y: Math.min(...ys), width: Math.max(...xs) - Math.min(...xs), height: Math.max(...ys) - Math.min(...ys) };
      });
      if (!boxes.length) return;
      const x0 = Math.min(...boxes.map((b) => b.x)) - 22, y0 = Math.min(...boxes.map((b) => b.y)) - 34;
      const x1 = Math.max(...boxes.map((b) => b.x + b.width)) + 22, y1 = Math.max(...boxes.map((b) => b.y + b.height)) + 22;
      const lw = name.length * 8 + 10;
      let lx = x0 + 12;
      while (taken.some((t) => Math.abs(t.y - y0) < 14 && lx < t.x + t.w && lx + lw > t.x)) lx += 12;
      for (const t of taken) if (Math.abs(t.y - y0) < 14 && lx < t.x + t.w && lx + lw > t.x) lx = t.x + t.w + 12;
      taken.push({ x: lx, y: y0, w: lw });
      hulls.append(s("rect", { x: x0, y: y0, width: x1 - x0, height: y1 - y0, rx: 16,
                               style: `fill:hsla(${hue},70%,50%,.05);stroke:hsla(${hue},60%,45%,.45)` }),
                   s("text", { x: lx, y: y0 + 18, style: `fill:hsl(${hue},55%,42%)` }, name));
    });
    vp.append(hulls);
  }
  const edgesG = s("g");
  for (const le of lay.edges) {
    const e = edgeById[le.id];
    const pts = edgePoints(le);
    if (pts.length < 2) continue;
    const d = roundedPath(pts, e.kind === "pipe" ? 10 : 7);
    const flowN = byId[e.kind === "pipe" ? (byId[e.source]?.kind === "valve" || byId[e.source]?.kind === "disturbance" ? e.source : e.target) : ""];
    const dist = flowN && flowN.kind === "disturbance";
    const loopSt = (e.loops || []).map((k) => g.loops[k]?.status).find(Boolean);
    const cls = ["edge", e.kind, dist ? "dist" : "", loopSt ? "loop-" + loopSt : ""].join(" ");
    const eg = s("g", { class: cls, "data-id": e.id, "data-loops": (e.loops || []).join(" "), "data-nodes": `${e.source} ${e.target}` });
    if (e.kind === "pipe") {
      eg.append(s("path", { d, class: "pipe-out" }), s("path", { d, class: "pipe-in" }));
      if (flowN && flowN.rate > 0) eg.append(s("path", { d, class: "flowing", stroke: dist ? "var(--dist)" : "var(--accent)" }));
      if (e.arrow) { const ah = arrowHead(pts, "head", 12); ah.style.fill = dist ? "var(--dist)" : "var(--pipe)"; eg.append(ah); }
    } else {
      eg.append(s("path", { d, class: "info" }));
      const ah = arrowHead(pts, "head", e.kind === "wire" ? 9 : 7);
      ah.style.fill = loopSt ? `var(--${loopSt === "holding" ? "ok" : loopSt === "off" ? "bad" : "warn"})`
                             : (e.kind === "action" ? "var(--ctl-line)" : e.kind === "wire" ? "var(--accent)" : "var(--info)");
      eg.append(ah);
      for (const l of le.labels || []) eg.append(s("text", { class: "elabel", x: l.x + 3, y: l.y + 11 }, l.text));
    }
    edgesG.append(eg);
  }
  const nodesG = s("g");
  for (const ln of lay.children) {
    const n = byId[ln.id];
    const ng = s("g", { class: `node k-${n.kind}`, transform: `translate(${ln.x},${ln.y})`, "data-id": n.id,
                        onclick: (ev) => { ev.stopPropagation(); if (n.kind !== "cloud") openNode(n); } });
    ng.append((DRAW[n.kind] || drawCloud)(n, ln.width, ln.height));
    for (const lb of ln.labels || []) {
      const lines = lb.text.split("\n");
      lines.forEach((t, i) => {
        const cx = lb.x + lb.width / 2, y = lb.y + 13 + i * 16;
        if (t === "§badge") { const b = badge(n.agent, cx, y - 11); if (b) ng.append(b); return; }
        ng.append(s("text", { x: cx, y, "text-anchor": "middle", class: i === 0 ? "t-label" : "t-sub" }, t));
      });
    }
    nodesG.append(ng);
  }
  vp.append(edgesG, nodesG);
  svg.replaceChildren(vp);
  applyView(svg);
  if (S.hl) highlightLoop(S.hl);
}

/* a standalone copy of the diagram: every computed style written inline, framed to the layout */

function applyView(svg) {
  const vp = svg.querySelector("#viewport");
  if (vp) vp.setAttribute("transform", `translate(${S.view.x},${S.view.y}) scale(${S.view.k})`);
}

function fit(svg, lay, legible = false) {
  const r = svg.getBoundingClientRect();
  if (!lay || !r.width) return;
  // the "fit" button shows everything; the first view keeps labels legible, and a bigger system is panned
  const whole = Math.min(1.25, (r.width - 40) / lay.width, (r.height - 90) / lay.height);
  const k = legible ? Math.max(0.45, whole) : Math.max(0.08, whole);
  const fitsW = lay.width * k <= r.width - 20, fitsH = lay.height * k <= r.height - 70;
  S.view = { k, x: fitsW ? (r.width - lay.width * k) / 2 : 20, y: fitsH ? Math.max(56, (r.height - lay.height * k) / 2 + 20) : 60 };
  applyView(svg);
}

function panZoom(svg) {
  let drag = null;
  svg.addEventListener("wheel", (ev) => {
    ev.preventDefault();
    const r = svg.getBoundingClientRect();
    const mx = ev.clientX - r.left, my = ev.clientY - r.top;
    const f = Math.exp(-ev.deltaY * (ev.ctrlKey ? 0.01 : 0.0015));
    const k = Math.max(0.15, Math.min(4, S.view.k * f));
    S.view.x = mx - ((mx - S.view.x) * k) / S.view.k;
    S.view.y = my - ((my - S.view.y) * k) / S.view.k;
    S.view.k = k;
    applyView(svg);
  }, { passive: false });
  svg.addEventListener("pointerdown", (ev) => {
    if (ev.target.closest(".node")) return;
    drag = { x: ev.clientX, y: ev.clientY, vx: S.view.x, vy: S.view.y };
    svg.classList.add("dragging");
    svg.setPointerCapture(ev.pointerId);
  });
  svg.addEventListener("pointermove", (ev) => {
    if (!drag) return;
    S.view.x = drag.vx + ev.clientX - drag.x;
    S.view.y = drag.vy + ev.clientY - drag.y;
    applyView(svg);
  });
  const end = () => { drag = null; svg.classList.remove("dragging"); };
  svg.addEventListener("pointerup", end);
  svg.addEventListener("pointercancel", end);
  svg.addEventListener("click", (ev) => { if (!ev.target.closest(".node")) { closeDetail(); } });
}

function highlightLoop(name) {
  S.hl = name;
  const svg = $("svg.canvas");
  if (!svg) return;
  const lp = name && S.graph?.loops?.[name];
  const members = new Set(lp ? lp.nodes : []);
  for (const n of svg.querySelectorAll(".node")) n.classList.toggle("dim", !!lp && !members.has(n.dataset.id));
  for (const e of svg.querySelectorAll(".edge")) {
    const [a, b] = (e.dataset.nodes || "").split(" ");
    e.classList.toggle("dim", !!lp && !(members.has(a) && members.has(b)));
  }
  for (const r of document.querySelectorAll(".looprow")) r.classList.toggle("hl", r.dataset.loop === name);
}

function highlightAgents(names) {
  const svg = $("svg.canvas");
  if (!svg) return;
  const ids = new Set((names || []).map((n) => "agent:" + n));
  for (const n of svg.querySelectorAll(".node")) n.classList.toggle("dim", !!names && !ids.has(n.dataset.id));
  for (const e of svg.querySelectorAll(".edge")) {
    const [a, b] = (e.dataset.nodes || "").split(" ");
    e.classList.toggle("dim", !!names && !(ids.has(a) && ids.has(b)));
  }
}

function legend(view) {
  if (view === "blocks") {
    const row = (sym, text) => [h("span", { class: "sym" }, sym), h("span", {}, text)];
    return h("div", { class: "legend" },
      row("r", "the setpoint: what the loop holds"),
      row("Σ", "compares: r − ym, with signs at each input"),
      row("e", "the error: how far off it is"),
      row("C", "the controller, and the agent filling it"),
      row("u", "its output: how far the actuator (valve) is opened"),
      row("d", "a disturbance joining at the plant"),
      row("y", "the plant's output: the stock"),
      row("H", "the sensor; ym is what it reads"));
  }
  if (view === "wiring") {
    return h("div", { class: "legend" },
      h("span", { html: '<svg width="26" height="16"><rect x="2" y="2" width="22" height="12" rx="3" fill="var(--panel)" stroke="var(--line)" stroke-width="2"/><rect x="2" y="2" width="4" height="12" rx="2" fill="var(--r4)"/></svg>' }), "an agent, coloured by its rung",
      h("span", { html: '<svg width="26" height="16"><path d="M2 8 H20" stroke="var(--accent)" stroke-width="2"/><path d="M18 4 L24 8 L18 12 Z" fill="var(--accent)"/></svg>' }), "its output reaches another agent");
  }
  const row = (svgTxt, text) => [h("span", { html: `<svg width="26" height="18">${svgTxt}</svg>` }), h("span", {}, text)];
  return h("div", { class: "legend" },
    row('<rect x="2" y="2" width="22" height="14" rx="2" fill="var(--stock)" stroke="var(--stock-line)" stroke-width="2"/>', "stock: what accumulates"),
    row('<path d="M1 9 H25" stroke="var(--pipe)" stroke-width="7"/><path d="M1 9 H25" stroke="var(--pipe-in)" stroke-width="3"/>', "flow: moves a stock"),
    row('<path d="M5 3 L13 9 L5 15 Z M21 3 L13 9 L21 15 Z" fill="var(--valve)"/>', "valve: where an agent acts"),
    row('<path d="M13 2 L22 9 L13 16 L4 9 Z" fill="var(--panel)" stroke="var(--dist)" stroke-width="1.8"/>', "disturbance: nothing controls it"),
    row('<circle cx="13" cy="9" r="7" fill="var(--sensor)" stroke="var(--sensor-line)" stroke-width="1.8"/>', "sensor: measures"),
    row('<rect x="2" y="2" width="22" height="14" rx="4" fill="var(--ctl)" stroke="var(--ctl-line)" stroke-width="1.8"/>', "controller: decides, to hold a setpoint"),
    row('<path d="M1 9 H25" stroke="var(--ok)" stroke-width="2"/>', "a loop holding (red: off, amber: open)"));
}

async function pageDiagram(main, q) {
  const view = q.get("view") || "control";
  const system = q.get("system") || "";
  const around = q.get("around") || "";
  S.showHulls = !system && !around;
  const wrap = h("div", { class: "canvas-wrap" });
  const svg = s("svg", { class: "canvas" });
  const sysSel = h("select", { onchange: (ev) => go({ system: ev.target.value, around: "" }) }, h("option", { value: "" }, "everything"));
  for (const name of S.status?.systems || []) sysSel.append(h("option", { value: name, selected: name === system ? "" : null }, name));
  function go(over) {
    const p = new URLSearchParams({ view, system, around, ...over });
    for (const [k, v] of [...p]) if (!v) p.delete(k);
    location.hash = "#/diagram?" + p.toString();
  }
  const toolbar = h("div", { class: "toolbar" },
    h("span", { class: "muted" }, "system"), sysSel,
    h("span", { class: "seg" },
      h("button", { class: view === "control" ? "on" : "", onclick: () => go({ view: "control" }) }, "control"),
      h("button", { class: view === "blocks" ? "on" : "", title: "each loop as a classic feedback block diagram", onclick: () => go({ view: "blocks" }) }, "blocks"),
      h("button", { class: view === "wiring" ? "on" : "", onclick: () => go({ view: "wiring" }) }, "wiring")),
    h("button", { class: S.wrap ? "on" : "", title: "fold a long chain into rows",
                  onclick: () => { S.wrap = !S.wrap; S.graphSig = ""; S.fitted = false; route(); } }, "wrap"),
    around ? h("span", { class: "pill" }, "around " + around, " ", h("a", { href: "#", onclick: (ev) => { ev.preventDefault(); go({ around: "" }); } }, "×")) : null);
  const zoom = h("div", { class: "zoom" },
    h("button", { onclick: () => fit(svg, S.layout) }, "fit"),
    h("button", { title: "save the diagram as an SVG file", onclick: () => exportSvg(svg, `${S.status?.name || "ergostat"}-${system || "all"}-${view}.svg`) }, "save SVG"),
    h("button", { onclick: () => { S.view.k *= 1.2; applyView(svg); } }, "+"),
    h("button", { onclick: () => { S.view.k /= 1.2; applyView(svg); } }, "−"));
  wrap.append(svg, toolbar, zoom);
  S.legendEl = legend(view);   // blocks, wiring and control each read differently
  const side = h("div", { class: "side" });
  main.append(h("div", { class: "diagram" }, wrap, side));
  panZoom(svg);
  S.graphSig = ""; S.fitted = false;

  async function tick() {
    let g;
    try { g = await api("graph", { view: view === "blocks" ? "control" : view, system, around }); } catch (e) { return; }
    S.graph = g;
    if (view === "blocks") {
      wrap.querySelector(".empty")?.remove();
      if (!Object.keys(g.loops || {}).length) {
        svg.replaceChildren();
        wrap.append(h("div", { class: "empty" }, "no loops to draw"));
      } else {
        S.layout = drawBlocks(svg, g);
        if (!S.fitted) { fit(svg, S.layout, true); S.fitted = true; }
      }
      renderSide(side, g, "blocks");
      return;
    }
    if (!g.nodes.length) {
      svg.replaceChildren();
      wrap.querySelector(".empty")?.remove();
      wrap.append(h("div", { class: "empty" }, view === "wiring" ? "no agents fill roles here yet" : "nothing to draw: the model is empty"));
      renderSide(side, g, view);
      return;
    }
    wrap.querySelector(".empty")?.remove();
    const sg = sig(g);
    if (sg !== S.graphSig) {
      const r = svg.getBoundingClientRect();
      S.layout = await layoutGraph(g, r.width && r.height ? r.width / Math.max(r.height - 80, 200) : 1.6);
      S.graphSig = sg;
    } else {
      // same structure: keep positions, redraw with new values (label texts may change length slightly)
    }
    drawGraph(svg, g, S.layout);
    if (!S.fitted) { fit(svg, S.layout, true); S.fitted = true; }
    renderSide(side, g, view);
  }
  await tick();
  S.timer = setInterval(tick, 2500);
}

function renderSide(side, g, view) {
  const st = S.status || { attention: [], loops: {} };
  const all = g.attention || st.attention;           // from the same snapshot as the diagram beside it
  const problems = all.filter((a) => a.level !== "hint"), hints = all.filter((a) => a.level === "hint");
  side.replaceChildren();
  side.append(h("h3", {}, "needs attention"));
  const att = h("div", { class: "att" });
  if (!problems.length) att.append(h("div", { class: "ok" }, "nothing needs you"));
  const MAX = 6;
  for (const a of problems.slice(0, MAX)) att.append(h("div", { class: a.level }, h("b", {}, a.what), " ", a.says));
  if (problems.length > MAX) att.append(h("div", { class: "more" }, `and ${problems.length - MAX} more: see Loops and Residuals`));
  side.append(att);
  if (hints.length) {
    const d = h("details", { class: "suggest" }, h("summary", {}, `suggestions (${hints.length}): cheaper agents could fill some roles`));
    for (const a of hints) d.append(h("div", { class: "hint" }, h("b", {}, a.what), " ", a.says));
    side.append(d);
  }
  const loops = Object.entries(g.loops || {});
  if (view === "control" || view === "blocks") {
    side.append(h("h3", {}, `loops (${loops.length})`));
    if (!loops.length) side.append(h("div", { class: "muted" }, "no loops in view"));
    for (const [name, lp] of loops) {
      const full = st.loops[name] || {};
      side.append(h("div", { class: "looprow", "data-loop": name,
                              onmouseenter: () => highlightLoop(name), onmouseleave: () => highlightLoop(null),
                              onclick: () => openLoop(name) },
        h("b", {}, name), statusEl(lp.status),
        h("div", { class: "sub" }, `${lp.stock} ${fmt(full.value)} · setpoint ${lp.setpoint}`)));
    }
  } else {
    if (g.cycles?.length) {
      side.append(h("h3", {}, `cycles among the agents (${g.cycles.length})`));
      for (const cy of g.cycles) {
        side.append(h("div", { class: "looprow", onmouseenter: () => highlightAgents(cy.agents), onmouseleave: () => highlightAgents(null) },
          h("b", {}, cy.agents.concat(cy.agents[0]).join(" → ")),
          cy.loop ? h("span", { class: "status s-holding" }, "loop " + cy.loop) : h("span", { class: "status s-open" }, "undeclared"),
          h("div", { class: "sub" }, cy.loop ? "a declared loop accounts for it" : "something runs in a circle that no loop declares")));
      }
    }
    side.append(h("h3", {}, "agents"));
    for (const n of g.nodes) side.append(h("div", { class: "looprow", onclick: () => openAgent(n.label) },
      h("b", {}, n.label), h("span", { class: "pill" }, `rung ${n.rung}`), h("div", { class: "sub" }, n.agentKind)));
  }
  if (st.changes?.length) {
    const last = st.changes[st.changes.length - 1];
    const n = (c) => c.added.length + c.removed.length + c.changed.length;
    const d = h("details", { class: "changes" }, h("summary", {}, `the model was edited ${ago(last.time)}`,
      h("span", { class: "muted" }, ` (${n(last)} part${n(last) === 1 ? "" : "s"}${st.changes.length > 1 ? `, ${st.changes.length} edits` : ""})`)));
    for (const c of st.changes.slice().reverse()) {
      const what = [...c.added.map((x) => "+" + x), ...c.removed.map((x) => "−" + x), ...c.changed.map((x) => "~" + x)];
      d.append(h("div", { class: "change" }, h("span", { class: "muted num" }, ago(c.time)), " ", what.join("  ")));
    }
    side.append(h("h3", {}, "the model"), d);
  }
  side.append(h("h3", {}, "how to read it"), S.legendEl || legend(view));
  side.append(h("h3", {}, "window"), h("div", { class: "muted" }, `rates and changes over the last ${S.since}`));
}

