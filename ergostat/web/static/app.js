/* ergostat's page: draws the system with ELK's layered layout and shows what the CLI shows. */
"use strict";

const $ = (s, el = document) => el.querySelector(s);
const NS = "http://www.w3.org/2000/svg";
const elk = new ELK();
const S = { since: "1h", route: "", graphSig: "", layout: null, view: { x: 0, y: 0, k: 1 }, fitted: false,
            timer: null, status: null, sel: null, hl: null };

function h(tag, attrs = {}, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === "class") el.className = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "html") el.innerHTML = v;
    else el.setAttribute(k, v);
  }
  for (const kid of kids.flat(Infinity)) if (kid != null && kid !== false) el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  return el;
}
function s(tag, attrs = {}, ...kids) {
  const el = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs || {})) if (v != null && v !== false) {
    if (k.startsWith("on")) el.addEventListener(k.slice(2), v); else el.setAttribute(k, v);
  }
  for (const kid of kids.flat(Infinity)) if (kid != null && kid !== false) el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  return el;
}
const fmt = (x) => x == null ? "?" : (typeof x === "number" ? (Number.isInteger(x) ? String(x) : (Math.abs(x) < 100 ? x.toPrecision(3).replace(/\.?0+$/, "") : x.toFixed(0))) : String(x));
function ago(t) {
  if (!t) return "never";
  const d = Date.now() / 1000 - t;
  if (d < 60) return `${Math.max(0, Math.round(d))}s ago`;
  if (d < 3600) return `${Math.round(d / 60)}m ago`;
  if (d < 86400) return `${Math.round(d / 3600)}h ago`;
  return `${Math.round(d / 86400)}d ago`;
}
const RUNG_NAMES = ["person", "ai", "narrow-ai", "decision", "program", "rule"];
const RUNG_HINT = ["the most general agent", "a universal AI agent", "an AI agent with one job", "a short model call with fixed answers",
                   "deterministic code", "a threshold or a table", "the work designed out"];
const rungColor = (r) => `var(--r${r})`;
const statusEl = (st) => h("span", { class: `status s-${st || "unknown"}` }, st || "?");

async function api(path, params = {}) {
  const q = new URLSearchParams({ since: S.since, ...(S.at ? { at: String(S.at) } : {}), ...params });
  const r = await fetch(`/api/${path}?${q}`);
  if (!r.ok) throw new Error(`${path}: ${r.status}`);
  return r.json();
}

/* ------------------------------------------------------------------ header and routing */

async function refreshHeader() {
  try {
    const st = await api("status");
    S.status = st;
    $("#project").textContent = st.name;
    const off = Object.values(st.loops).filter((l) => l.status === "off").length;
    const run = $("#running");
    run.className = "pill " + (st.running ? (off ? "bad" : "ok") : "unknown");
    run.textContent = st.running ? (off ? `${off} loop${off > 1 ? "s" : ""} off` : "running") : "not running";
    document.title = `${st.name} · ergostat`;
    S.first = st.first;
  } catch (e) { /* the server may be restarting */ }
}

function parseRoute() {
  const [path, query] = (location.hash.slice(1) || "/diagram").split("?");
  return { path, q: new URLSearchParams(query || "") };
}

async function route() {
  const { path, q } = parseRoute();
  for (const a of document.querySelectorAll("#nav a")) a.classList.toggle("on", a.getAttribute("href") === "#" + path.split("/").slice(0, 2).join("/"));
  clearInterval(S.timer);
  closeDetail();
  const main = $("#main");
  main.replaceChildren();
  const pages = { "/diagram": pageDiagram, "/loops": pageLoops, "/agents": pageAgents, "/parts": pageParts, "/record": pageRecord,
                  "/residuals": pageResiduals, "/check": pageCheck, "/guide": pageGuide };
  if (path.startsWith("/item/")) return pageItem(main, decodeURIComponent(path.slice(6)));
  return (pages[path] || pageDiagram)(main, q);
}

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
const STYLE_PROPS = ["fill", "stroke", "stroke-width", "stroke-dasharray", "stroke-linecap", "stroke-linejoin", "opacity",
                     "font-family", "font-size", "font-weight", "letter-spacing", "text-transform", "text-anchor"];
function exportSvg(svg, name) {
  if (!S.layout) return;
  const clone = svg.cloneNode(true);
  const src = svg.querySelectorAll("*"), dst = clone.querySelectorAll("*");
  src.forEach((el, i) => {
    const cs = getComputedStyle(el);
    const style = STYLE_PROPS.map((p) => `${p}:${cs.getPropertyValue(p)}`).join(";");
    dst[i].setAttribute("style", style + (dst[i].getAttribute("style") ? ";" + dst[i].getAttribute("style") : ""));
    dst[i].classList?.remove("dim");
  });
  for (const f of clone.querySelectorAll(".flowing")) f.remove();          // the animation does not survive a file
  clone.querySelector("#viewport").setAttribute("transform", "");
  const pad = 20, w = S.layout.width + pad * 2, hgt = S.layout.height + pad * 2;
  clone.setAttribute("viewBox", `${-pad} ${-pad} ${w} ${hgt}`);
  clone.setAttribute("width", w);
  clone.setAttribute("height", hgt);
  clone.setAttribute("xmlns", NS);
  clone.removeAttribute("class");
  const bg = getComputedStyle(document.body).backgroundColor;
  clone.insertBefore(s("rect", { x: -pad, y: -pad, width: w, height: hgt, fill: bg }), clone.firstChild);
  const blob = new Blob([new XMLSerializer().serializeToString(clone)], { type: "image/svg+xml" });
  const a = h("a", { href: URL.createObjectURL(blob), download: name });
  document.body.append(a);
  a.click();
  setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
}

/* ---- the block view: one classic negative-feedback loop per row
   r ──▶(Σ)──e──▶[ controller ]──u──▶[ valve ]──▶(+)──▶[ stock ]──y──▶
          ▲−                                       ▲ d                │
          └──────────────ym──────[ sensor ]◀──────────────────────────┘          */
function blockLayout(g) {
  const byId = Object.fromEntries(g.nodes.map((n) => [n.id, n]));
  const rows = [];
  for (const [name, lp] of Object.entries(g.loops)) {
    const ctl = byId[`controller:${name}`];
    const stock = byId[`stock:${lp.stock}`];
    if (!ctl || !stock) continue;
    const sensors = lp.nodes.filter((id) => id.startsWith("sensor:")).map((id) => byId[id]).filter(Boolean);
    const valves = lp.nodes.filter((id) => id.startsWith("flow:")).map((id) => byId[id]).filter(Boolean);
    const dists = g.edges.filter((e) => e.kind === "pipe" && e.target === stock.id && byId[e.source]?.kind === "disturbance")
                        .map((e) => byId[e.source]);
    rows.push({ name, lp, ctl, stock, sensors, valves, dists });
  }
  return rows;
}

function drawBlocks(svg, g) {
  const rows = blockLayout(g);
  const vp = s("g", { id: "viewport" });
  // widths from the longest text in any row, so every row lines up and nothing overflows
  const tw = (t) => (t || "").length * 6.4 + 28;
  const cw = Math.max(190, ...rows.map((r) => Math.max(tw(r.ctl.label) + 10, tw("C · " + badgeText(r.ctl.agent)))));
  const vw = Math.max(160, ...rows.map((r) => Math.max(tw(r.valves[0]?.label), tw(badgeText(r.valves[0]?.agent)), tw("actuator · " + (r.valves[0]?.rateText || "")))));
  const sw = Math.max(160, ...rows.map((r) => Math.max(tw(r.stock.label), tw(`plant · ${r.stock.valueText} ${r.stock.unit || ""}`))));
  const hw = Math.max(160, ...rows.map((r) => Math.max(tw(r.sensors[0]?.label), tw(`H · reads ${r.sensors[0]?.reading ?? "?"}`))));
  const X = { r: 30, sum: 130 };
  X.ctl = X.sum + 70; X.valve = X.ctl + cw + 50; X.dsum = X.valve + vw + 50; X.stock = X.dsum + 50; X.out = X.stock + sw + 60;
  const RH = 210;
  const line = (pts, cls, color, dashed) => {
    const d = pts.map((p, i) => `${i ? "L" : "M"}${p[0]},${p[1]}`).join("");
    const el = s("path", { d, fill: "none", stroke: color, "stroke-width": 1.8, "stroke-dasharray": dashed ? "5 4" : null, class: cls });
    const [a, b] = [pts[pts.length - 2], pts[pts.length - 1]];
    const ang = Math.atan2(b[1] - a[1], b[0] - a[0]);
    const head = s("path", { d: `M${b[0] - 8 * Math.cos(ang - 0.45)},${b[1] - 8 * Math.sin(ang - 0.45)} L${b[0]},${b[1]} L${b[0] - 8 * Math.cos(ang + 0.45)},${b[1] - 8 * Math.sin(ang + 0.45)} Z` });
    head.style.fill = color;
    return [el, head];
  };
  const label = (x, y, t, cls = "t-sub", anchor = "middle") => s("text", { x, y, class: cls, "text-anchor": anchor }, t);
  const box = (x, y, w, hgt, title, sub, fill, stroke, n, extra) => {
    const gg = s("g", { class: "node", transform: `translate(${x},${y})`, "data-id": n?.id || "",
                        onclick: (ev) => { ev.stopPropagation(); if (n) openNode(n); } });
    gg.append(s("rect", { class: "hit", width: w, height: hgt, rx: 8, fill, stroke, "stroke-width": 2 }));
    gg.append(label(w / 2, 22, title, "t-label"));
    if (sub) gg.append(label(w / 2, 40, sub));
    if (extra) gg.append(extra);
    return gg;
  };
  const sum = (cx, cy, signs) => {
    const gg = s("g");
    gg.append(s("circle", { cx, cy, r: 14, fill: "var(--panel)", stroke: "var(--ink)", "stroke-width": 1.8 }));
    gg.append(s("path", { d: `M${cx - 10},${cy - 10} L${cx + 10},${cy + 10} M${cx + 10},${cy - 10} L${cx - 10},${cy + 10}`, stroke: "var(--ink)", "stroke-width": 1.2 }));
    for (const [dx, dy, t] of signs) gg.append(label(cx + dx, cy + dy, t, "t-label"));
    return gg;
  };
  rows.forEach((row, i) => {
    const y0 = i * RH + 40, cy = y0 + 50;
    const st = row.lp.status || "unknown";
    const tone = { off: "var(--bad)", holding: "var(--ok)", open: "var(--warn)" }[st] || "var(--unknown)";
    const loopG = s("g", { class: "block-loop", "data-loop": row.name });
    loopG.append(s("rect", { x: 6, y: y0 - 30, width: X.out + 70, height: RH - 20, rx: 14, fill: "none", stroke: "var(--line)", "stroke-dasharray": "4 4" }));
    loopG.append(label(18, y0 - 10, row.name, "t-label", "start"), label(18 + row.name.length * 7.4 + 10, y0 - 10, st, "t-sub", "start"));
    loopG.lastChild.style.fill = tone;
    const sp = row.lp.setpoint.replace("<=", "≤").replace(">=", "≥").replace("==", "=").trim();
    // r and the summing junction
    loopG.append(label(X.r, cy - 8, "r: " + sp, "t-sub", "start"));
    loopG.append(...line([[X.r, cy], [X.sum - 14, cy]], "", "var(--ink)"));
    loopG.append(sum(X.sum, cy, [[-24, -16, "+"], [-16, 32, "−"]]));
    // e into the controller
    loopG.append(...line([[X.sum + 14, cy], [X.ctl, cy]], "", tone));
    const err = row.lp.error;
    loopG.append(label((X.sum + X.ctl) / 2 + 6, cy - 8, err != null ? `e = ${fmt(err)}` : "e"));
    loopG.append(box(X.ctl, cy - 36, cw, 72, row.ctl.label, "C · " + (row.ctl.agent ? badgeText(row.ctl.agent) : "unfilled"),
                     "var(--ctl)", "var(--ctl-line)", row.ctl,
                     row.ctl.decision ? label(cw / 2, 60, "“" + (row.ctl.decision.length > cw / 6.4 - 4 ? row.ctl.decision.slice(0, Math.floor(cw / 6.4) - 5) + "…" : row.ctl.decision) + "”") : null));
    // u into the valve(s)
    const v = row.valves[0];
    loopG.append(...line([[X.ctl + cw, cy], [X.valve, cy]], "", "var(--ctl-line)"));
    loopG.append(label((X.ctl + cw + X.valve) / 2, cy - 8, v?.position != null ? `u = ${fmt(v.position)}` : "u"));
    loopG.append(box(X.valve, cy - 36, vw, 72, v ? v.label : "no valve", v ? `actuator · ${v.rateText}` : "",
                     "var(--panel)", v ? "var(--valve)" : "var(--warn)", v,
                     v?.agent ? label(vw / 2, 60, badgeText(v.agent)) : null));
    // the disturbance joins at the plant's input
    if (row.dists.length) {
      loopG.append(...line([[X.valve + vw, cy], [X.dsum - 14, cy]], "", "var(--pipe)"));
      loopG.append(sum(X.dsum, cy, [[-22, -16, "+"], [18, -20, "+"]]));
      const d = row.dists[0];
      loopG.append(...line([[X.dsum, cy - 70], [X.dsum, cy - 14]], "", "var(--dist)"));
      loopG.append(label(X.dsum + 8, cy - 74, `d: ${d.label} ${d.rateText}${d.estimated ? " (est.)" : ""}`, "t-sub", "start"));
      loopG.append(...line([[X.dsum + 14, cy], [X.stock, cy]], "", "var(--pipe)"));
    } else {
      loopG.append(...line([[X.valve + vw, cy], [X.stock, cy]], "", "var(--pipe)"));
    }
    // the plant: the stock
    loopG.append(box(X.stock, cy - 36, sw, 72, row.stock.label, `plant · ${row.stock.valueText} ${row.stock.unit || ""}`,
                     "var(--stock)", "var(--stock-line)", row.stock));
    // y out, and the feedback path through the sensor
    loopG.append(...line([[X.stock + sw, cy], [X.out + 40, cy]], "", tone));
    loopG.append(label(X.out + 20, cy - 8, "y"));
    const se = row.sensors[0];
    const fy = cy + 90, sw2 = hw, sx = (X.sum + X.out) / 2 - hw / 2;
    loopG.append(...line([[X.out, cy], [X.out, fy], [sx + sw2, fy]], "", tone, true));
    loopG.append(box(sx, fy - 30, sw2, 60, se ? se.label : "no sensor", se ? `H · reads ${se.reading ?? "?"}` : "",
                     "var(--sensor)", se ? "var(--sensor-line)" : "var(--warn)", se));
    loopG.append(...line([[sx, fy], [X.sum, fy], [X.sum, cy + 14]], "", tone, true));
    loopG.append(label((X.sum + sx) / 2, fy - 8, "ym"));
    vp.append(loopG);
  });
  svg.replaceChildren(vp);
  applyView(svg);
  return { width: X.out + 90, height: rows.length * RH + 30 };
}

function applyView(svg) {
  const vp = svg.querySelector("#viewport");
  if (vp) vp.setAttribute("transform", `translate(${S.view.x},${S.view.y}) scale(${S.view.k})`);
}

function fit(svg, lay) {
  const r = svg.getBoundingClientRect();
  if (!lay || !r.width) return;
  // fit, but never so small that the labels cannot be read: a wider system is panned
  const k = Math.max(0.62, Math.min(1.25, Math.min((r.width - 40) / lay.width, (r.height - 90) / lay.height)));
  const x = lay.width * k < r.width ? (r.width - lay.width * k) / 2 : 20;
  S.view = { k, x, y: Math.max(56, (r.height - lay.height * k) / 2 + 20) };
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
        if (!S.fitted) { fit(svg, S.layout); S.fitted = true; }
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
    if (!S.fitted) { fit(svg, S.layout); S.fitted = true; }
    renderSide(side, g, view);
  }
  await tick();
  S.timer = setInterval(tick, 2500);
}

function renderSide(side, g, view) {
  const st = S.status || { attention: [], loops: {} };
  side.replaceChildren();
  side.append(h("h3", {}, "needs attention"));
  const att = h("div", { class: "att" });
  if (!st.attention.length) att.append(h("div", { class: "ok" }, "nothing needs you"));
  const MAX = 6;
  for (const a of st.attention.slice(0, MAX)) att.append(h("div", { class: a.level }, h("b", {}, a.what), " ", a.says));
  if (st.attention.length > MAX) att.append(h("div", { class: "more" }, `and ${st.attention.length - MAX} more: see Loops and Residuals`));
  side.append(att);
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
    side.append(h("h3", {}, "agents"));
    for (const n of g.nodes) side.append(h("div", { class: "looprow", onclick: () => openAgent(n.label) },
      h("b", {}, n.label), h("span", { class: "pill" }, `rung ${n.rung}`), h("div", { class: "sub" }, n.agentKind)));
  }
  if (st.changes?.length) {
    side.append(h("h3", {}, "the model changed"));
    for (const c of st.changes.slice().reverse()) {
      const what = [...c.added.map((x) => "+" + x), ...c.removed.map((x) => "−" + x), ...c.changed.map((x) => "~" + x)];
      side.append(h("div", { class: "change" }, h("span", { class: "muted num" }, ago(c.time)), " ", what.join("  ")));
    }
  }
  side.append(h("h3", {}, "how to read it"), S.legendEl || legend(view));
  side.append(h("h3", {}, "window"), h("div", { class: "muted" }, `rates and changes over the last ${S.since}`));
}

/* ------------------------------------------------------------------ details */

function closeDetail() { const d = $("#detail"); d.hidden = true; d.replaceChildren(); for (const n of document.querySelectorAll(".node.sel")) n.classList.remove("sel"); }
function showDetail(...kids) {
  const d = $("#detail");
  d.replaceChildren(h("button", { class: "close", onclick: closeDetail }, "close"), ...kids);
  d.hidden = false;
}
function dl(pairs) { return h("dl", {}, pairs.filter(([, v]) => v != null && v !== "").flatMap(([k, v]) => [h("dt", {}, k), h("dd", {}, v)])); }
function agentLink(a) { return a ? h("a", { href: "#", onclick: (ev) => { ev.preventDefault(); openAgent(a.name); } }, `${a.name} (rung ${a.rung} ${a.kind})`) : h("span", { class: "muted" }, "unfilled"); }

async function openNode(n) {
  for (const x of document.querySelectorAll(".node.sel")) x.classList.remove("sel");
  document.querySelector(`.node[data-id="${CSS.escape(n.id)}"]`)?.classList.add("sel");
  if (n.kind === "agent") return openAgent(n.label);
  const [kind, name] = n.kind === "valve" ? ["valve", n.label] : n.kind === "disturbance" ? ["disturbance", n.flow] : n.id.split(":");
  if (kind === "controller") return openLoop(name);
  const d = await api(`part/${kind}/${encodeURIComponent(name)}`);
  const m = d.model, now = d.now || {};
  const rows = [["description", m.description]];
  if (kind === "stock") rows.push(["now", `${fmt(now.value)} ${m.unit}`], ["measured", now.at ? `${ago(now.at)} by ${now.sensor}` : "never"],
                                  ["in", `${fmt(now.inflow)}/h`], ["out", `${fmt(now.outflow)}/h`]);
  if (kind === "disturbance") rows.push(["pushes", m.target ? `into ${m.target}` : `out of ${m.source}`], ["rate", `${fmt(now.rate)}/h`], ["how we know", now.how]);
  if (kind === "valve") rows.push(["acts on", m.flow], ["mode", m.mode], ["filled by", agentLink(d.agent)], ["rate", `${fmt(now.flow?.rate)}/h`]);
  if (kind === "sensor") rows.push(["measures", m.measures], ["filled by", agentLink(d.agent)], ["readings", String((now.readings || []).length)]);
  const kids = [h("div", { class: "kind" }, kind), h("h2", {}, name), dl(rows)];
  if (kind === "stock" && now.points?.length > 1) kids.push(sparkSvg(now.points, 380, 70));
  if (kind === "sensor" && now.readings?.length > 1) kids.push(sparkSvg(now.readings, 380, 70));
  if (kind === "valve") {
    kids.push(h("h3", {}, "recent openings"));
    kids.push(eventsTable(now.openings || [], true));
  }
  kids.push(h("p", {}, h("a", { href: `#/diagram?around=${kind}/${encodeURIComponent(name)}` }, "draw what is around it")));
  showDetail(...kids);
}

async function openLoop(name) {
  let lp;
  try { lp = await api(`loops/${encodeURIComponent(name)}`); } catch (e) { return; }
  const kids = [h("div", { class: "kind" }, "loop"), h("h2", {}, name, " ", statusEl(lp.status)),
    dl([["holds", `${lp.stock} ${lp.setpoint}` + (lp.tolerance ? ` (± ${lp.tolerance})` : "")], ["now", fmt(lp.value)],
        ["error", lp.error ? fmt(lp.error) : "0"], ["sensors", lp.sensors.join(", ") || "none"], ["valves", lp.valves.join(", ") || "none"],
        ["moves", lp.flows.join(", ") || "none"], ["last reading", ago(lp.last_read)],
        ["last decision", lp.last_decision ? `${ago(lp.last_decision.time)}: ${lp.last_decision.data.decision}` : "none"],
        ["last opening", ago(lp.last_opening)], ["cycled", lp.observed ? "yes, in this window" : "not in this window"]])];
  if ((lp.points || []).length > 1) kids.push(trendChart(lp, 400, 170));
  for (const g of lp.gaps || []) kids.push(h("div", { class: "att" }, h("div", {}, h("b", {}, "cannot close: "), g)));
  for (const hint of lp.hints || []) kids.push(h("div", { class: "att" }, h("div", { class: "hint" }, h("b", {}, "hint: "), hint.says)));
  if (lp.crossings?.length) {
    kids.push(h("h3", {}, "crossings"));
    kids.push(h("table", {}, lp.crossings.slice().reverse().map((e) => h("tr", {},
      h("td", { class: "num nowrap" }, new Date(e.time * 1000).toLocaleTimeString([], { hour12: false })),
      h("td", {}, statusEl(e.type.split(".")[1])), h("td", { class: "num" }, fmt(e.data.value))))));
  }
  if (lp.decisions?.count) {
    kids.push(h("h3", {}, `decisions (${lp.decisions.count})`));
    kids.push(h("table", {}, lp.decisions.kinds.slice(0, 6).map(([w, n]) => h("tr", {}, h("td", { class: "num" }, n), h("td", {}, w)))));
  }
  kids.push(h("p", {}, h("a", { href: `#/diagram?around=loop/${encodeURIComponent(name)}` }, "draw this loop alone")));
  showDetail(...kids);
}

async function openAgent(name) {
  const a = await api(`agents/${encodeURIComponent(name)}`);
  const kids = [h("div", { class: "kind" }, `agent · rung ${a.rung} ${a.kind}`), h("h2", {}, name),
    dl([["description", a.agent.description], ["command", a.agent.command ? h("code", {}, a.agent.command) : null],
        ["runs", a.schedule || "not run by ergostat"],
        ["fills", (a.roles || []).map((r) => `${r.kind} ${r.name}`).join(", ") || "nothing"],
        ["in window", `${a.runs} runs, ${a.failed} failed`]])];
  kids.push(h("h3", {}, "recent runs"));
  kids.push(h("table", {}, h("tr", {}, h("th", {}, "when"), h("th", {}, "result"), h("th", {}, "said")),
    (a.recent || []).slice(-10).reverse().map((e) => h("tr", {}, h("td", {}, ago(e.time)),
      h("td", {}, e.type === "agent.failed" ? h("span", { class: "s-off" }, e.data.note || "failed") : "ok"),
      h("td", { class: "muted" }, `${e.data.readings || 0} readings, ${e.data.openings || 0} openings, ${e.data.decisions || 0} decisions`)))));
  if (a.log?.length) kids.push(h("h3", {}, "end of its log"), h("pre", {}, a.log.slice(-15).join("\n")));
  showDetail(...kids);
}

/* a loop's trend: the stock over the window, the setpoint with its tolerance band, the stretches
   when the loop was off shaded, and a tick on the time axis for each valve opening */
function trendChart(lp, w, hgt) {
  const pad = { l: 36, r: 8, t: 10, b: 22 };
  const t0 = Math.max(lp.since, lp.points[0][0]), t1 = lp.until;
  const vs = lp.points.map((p) => p[1]);
  const spv = setpointOf(lp.setpoint), tol = lp.tolerance || 0;
  let lo = Math.min(...vs, spv ?? Infinity), hi = Math.max(...vs, spv ?? -Infinity);
  if (spv != null) { lo = Math.min(lo, spv - tol); hi = Math.max(hi, spv + tol); }
  const span = (hi - lo) || 1; lo -= span * 0.08; hi += span * 0.08;
  const x = (t) => pad.l + ((t - t0) / ((t1 - t0) || 1)) * (w - pad.l - pad.r);
  const y = (v) => pad.t + (1 - (v - lo) / (hi - lo)) * (hgt - pad.t - pad.b);
  const out = s("svg", { width: w, height: hgt, class: "trend" });
  // off stretches, from the crossings
  const cr = (lp.crossings || []).slice().sort((a, b) => a.time - b.time);
  let offFrom = null;
  for (const c of cr) {
    if (c.type === "loop.off") offFrom = c.time;
    if (c.type === "loop.holding" && offFrom != null) { out.append(s("rect", { x: x(offFrom), y: pad.t, width: Math.max(1, x(c.time) - x(offFrom)), height: hgt - pad.t - pad.b, fill: "var(--bad)", opacity: 0.08 })); offFrom = null; }
  }
  if (offFrom != null) out.append(s("rect", { x: x(offFrom), y: pad.t, width: Math.max(1, x(t1) - x(offFrom)), height: hgt - pad.t - pad.b, fill: "var(--bad)", opacity: 0.08 }));
  if (spv != null) {
    if (tol) out.append(s("rect", { x: pad.l, y: y(spv + tol), width: w - pad.l - pad.r, height: Math.max(1, y(spv - tol) - y(spv + tol)), fill: "var(--ok)", opacity: 0.08 }));
    out.append(s("line", { x1: pad.l, x2: w - pad.r, y1: y(spv), y2: y(spv), stroke: "var(--ok)", "stroke-dasharray": "4 3", "stroke-width": 1.2 }));
    out.append(s("text", { x: pad.l + 4, y: y(spv) - 4, fill: "var(--ok)", "font-size": 10.5, "paint-order": "stroke",
                           stroke: "var(--panel)", "stroke-width": 3 }, "setpoint " + lp.setpoint));
  }
  const d = lp.points.map((p, i) => `${i ? "L" : "M"}${x(p[0])},${y(p[1])}`).join("");
  out.append(s("path", { d, fill: "none", stroke: "var(--accent)", "stroke-width": 1.8 }));
  for (const o of lp.openings || []) out.append(s("line", { x1: x(o.time), x2: x(o.time), y1: hgt - pad.b, y2: hgt - pad.b + 6, stroke: "var(--ctl-line)", "stroke-width": 1.4 }, s("title", {}, `${o.valve} opened: ${o.amount}`)));
  out.append(s("line", { x1: pad.l, x2: w - pad.r, y1: hgt - pad.b, y2: hgt - pad.b, stroke: "var(--line)" }));
  const lab = (t, xx, yy, anchor = "start") => s("text", { x: xx, y: yy, "text-anchor": anchor, fill: "var(--muted)", "font-size": 10.5 }, t);
  out.append(lab(fmt(hi - span * 0.08), 0, pad.t + 8), lab(fmt(lo + span * 0.08), 0, hgt - pad.b));
  const tl = (t) => new Date(t * 1000).toLocaleTimeString([], { hour12: false, hour: "2-digit", minute: "2-digit" });
  out.append(lab(tl(t0), pad.l, hgt - 4), lab(tl(t1), w - pad.r, hgt - 4, "end"), lab("valve openings ▮", (w + pad.l) / 2, hgt - 4, "middle"));
  return out;
}

function sparkSvg(points, w, hgt, setpoint = null) {
  const vs = points.map((p) => p[1]);
  let lo = Math.min(...vs), hi = Math.max(...vs);
  if (setpoint != null) { lo = Math.min(lo, setpoint); hi = Math.max(hi, setpoint); }
  const small = hgt < 50, pad = small ? 3 : 6, left = small ? 2 : 34;
  const y = (v) => hgt - pad - ((v - lo) / ((hi - lo) || 1)) * (hgt - 2 * pad);
  const d = vs.map((v, i) => `${i ? "L" : "M"}${left + (i / (vs.length - 1)) * (w - left - 4)},${y(v)}`).join("");
  const out = s("svg", { width: w, height: hgt, class: "spark" });
  if (setpoint != null) out.append(s("line", { x1: left, x2: w - 2, y1: y(setpoint), y2: y(setpoint), stroke: "var(--muted)", "stroke-dasharray": "3 3", "stroke-width": 1 }));
  out.append(s("path", { d, fill: "none", stroke: "var(--accent)", "stroke-width": small ? 1.6 : 2 }));
  if (!small) out.append(s("text", { x: 0, y: 12, fill: "var(--muted)", "font-size": 11 }, fmt(hi)), s("text", { x: 0, y: hgt - 2, fill: "var(--muted)", "font-size": 11 }, fmt(lo)));
  return out;
}
const setpointOf = (sp) => { const m = /(-?\d+(\.\d+)?)/.exec(sp || ""); return m ? +m[1] : null; };

function eventsTable(evs, compact) {
  return h("table", {}, h("tr", {}, h("th", {}, "when"), h("th", {}, "type"), compact ? null : h("th", {}, "item"), h("th", {}, "source"), h("th", {}, "data")),
    evs.slice().reverse().map((e) => h("tr", {}, h("td", { class: "num nowrap" }, new Date(e.time * 1000).toLocaleTimeString([], { hour12: false })),
      h("td", { class: "nowrap" }, e.type),
      compact ? null : h("td", { class: "nowrap" }, e.item ? h("a", { href: `#/item/${encodeURIComponent(e.item)}` }, e.item) : "–"),
      h("td", { class: "muted nowrap" }, e.source || "–"), h("td", { class: "mono muted" }, JSON.stringify(e.data).slice(0, 110)))));
}

/* ------------------------------------------------------------------ the other pages */

function page(main, title, lede) {
  const p = h("div", { class: "page" }, h("h1", {}, title), lede ? h("p", { class: "lede" }, lede) : null);
  main.append(p);
  return p;
}

async function pageLoops(main) {
  const p = page(main, "Loops", "Each controller that holds a stock is a loop. Holding: within its setpoint. Off: outside it. Open: it cannot close (a sensor or valve is missing). Unknown: no reading yet.");
  const box = h("div");
  p.append(box);
  async function tick() {
    const [loops, stocks] = [await api("loops"), await api("graph")];
    const pts = Object.fromEntries(stocks.nodes.filter((n) => n.kind === "stock").map((n) => [n.label, n.points]));
    box.replaceChildren(h("table", {}, h("tr", {}, ["loop", "status", "holds", "now", "setpoint", "error", "trend", "cycled"].map((x) => h("th", {}, x))),
      Object.entries(loops).map(([n, lp]) => h("tr", { class: "click", onclick: () => openLoop(n) },
        h("td", {}, h("b", {}, n)), h("td", {}, statusEl(lp.status)), h("td", {}, lp.stock), h("td", { class: "num" }, fmt(lp.value)),
        h("td", { class: "num" }, lp.setpoint), h("td", { class: "num" }, lp.error ? fmt(lp.error) : ""),
        h("td", {}, (pts[lp.stock] || []).length > 1 ? sparkSvg(pts[lp.stock], 150, 30, setpointOf(lp.setpoint)) : ""), h("td", {}, lp.observed ? "yes" : h("span", { class: "muted" }, "no"))))));
  }
  await tick();
  S.timer = setInterval(tick, 3000);
}

async function pageAgents(main) {
  const p = page(main, "Agents", "Agents fill roles: sensors, controllers and valves. The ladder runs from the most general agent to none at all; every role is expected to move right.");
  const box = h("div", { class: "ladder" });
  p.append(box);
  async function tick() {
    const agents = await api("agents");
    box.replaceChildren();
    const cols = [...RUNG_NAMES, "retired"];
    cols.forEach((k, i) => {
      const col = h("div", { class: "rung" }, h("h4", {}, h("span", { style: `color:${rungColor(i)}` }, "● "), `${i} ${k}`), h("div", { class: "hint" }, RUNG_HINT[i]));
      for (const [name, a] of Object.entries(agents).filter(([, a]) => a.rung === i)) {
        col.append(h("div", { class: "card" + (a.failing ? " failing" : ""), onclick: () => openAgent(name) },
          h("b", {}, name),
          h("div", { class: "muted" }, a.runs_itself ? `${a.runs} runs · ${a.running_since ? "running for " + ago(a.running_since).replace(" ago", "") : (a.last ? ago(a.last.time) : "never ran")}` : (a.kind === "person" ? "a person" : "not run here")),
          h("div", { class: "roles" }, (a.roles || []).map((r) => `${r.kind} ${r.name}`).join(" · ") || "no roles")));
      }
      box.append(col);
    });
  }
  await tick();
  S.timer = setInterval(tick, 3000);
}

async function pageParts(main, q) {
  const p = page(main, "Parts", "Every part of the model, one kind at a time, with what it holds or does now. Click a row for its detail.");
  const kinds = ["system", "stock", "flow", "valve", "sensor", "controller", "disturbance"];
  const on = q.get("kind") || "stock";
  p.append(h("div", { class: "seg tabs" }, kinds.map((k) => h("button", { class: k === on ? "on" : "", onclick: () => { location.hash = `#/parts?kind=${k}`; } }, k + "s"))));
  const box = h("div", { style: "margin-top:14px" });
  p.append(box);
  const badgeEl = (a) => a ? h("span", { class: "rungpill", style: `background:${rungColor(a.rung)}` }, `${a.kind} · ${a.name}`) : h("span", { class: "s-open status" }, "unfilled");
  const rowsFor = {
    system: (x) => [h("b", {}, x.name), x.description, String(x.parts), x.loops.join(", ") || "–", x.off.length ? h("span", { class: "s-off status" }, x.off.join(", ")) : "0"],
    stock: (x) => [h("b", {}, x.name), h("span", { class: "num" }, `${fmt(x.value)} ${x.unit}`), x.points.length > 1 ? sparkSvg(x.points, 130, 26) : "",
                   x.sensor || h("span", { class: "s-open status" }, "unmeasured"), h("span", { class: "num" }, `${fmt(x.inflow)}/h in · ${fmt(x.outflow)}/h out`)],
    flow: (x) => [h("b", {}, x.name), x.from || "outside", x.to || "outside", h("span", { class: "num" }, `${fmt(x.rate)}/h`), h("span", { class: "muted" }, x.how)],
    disturbance: (x) => [h("b", {}, x.name), x.from || "outside", x.to || "outside", h("span", { class: "num" }, `${fmt(x.rate)}/h`), h("span", { class: "muted" }, x.how)],
    valve: (x) => [h("b", {}, x.name), x.flow, x.mode, badgeEl(x.agent), h("span", { class: "num" }, `${fmt(x.rate)}/h`), ago(x.last)],
    sensor: (x) => [h("b", {}, x.name), x.measures, badgeEl(x.agent), h("span", { class: "num" }, fmt(x.reading)), ago(x.at)],
    controller: (x) => [h("b", {}, x.name), `${x.holds} ${x.setpoint}`, statusEl(x.status), badgeEl(x.agent)],
  };
  const heads = { system: ["system", "description", "parts", "loops", "off"], stock: ["stock", "now", "trend", "measured by", "flows"],
                  flow: ["flow", "from", "to", "rate", "how we know"], disturbance: ["disturbance", "from", "to", "rate", "how we know"],
                  valve: ["valve", "flow", "mode", "filled by", "rate", "last opened"], sensor: ["sensor", "measures", "filled by", "reading", "read"],
                  controller: ["controller", "holds", "status", "filled by"] };
  const open = (x) => on === "system" ? (location.hash = `#/diagram?system=${encodeURIComponent(x.name)}`)
                    : on === "controller" ? openLoop(x.name)
                    : openNode({ id: `${on === "valve" ? "valve" : on}:${x.name}`, kind: on, label: x.name, flow: x.name });
  async function tick() {
    const all = await api("parts");
    const rows = all[on] || [];
    box.replaceChildren(rows.length ? h("table", {}, h("tr", {}, heads[on].map((x) => h("th", {}, x))),
      rows.map((x) => h("tr", { class: "click", onclick: () => open(x) }, rowsFor[on](x).map((c) => h("td", {}, c)))))
      : h("p", { class: "muted" }, `no ${on}s`));
  }
  await tick();
  S.timer = setInterval(tick, 3000);
}

async function pageRecord(main, q) {
  const p = page(main, "Record", "Events as they happen, newest first; items are events folded by id.");
  const filt = h("input", { placeholder: "type, e.g. valve.* or loop.off", value: q.get("type") || "" });
  const runs = h("input", { type: "checkbox" });
  const box = h("div");
  const items = h("div");
  p.append(h("div", { style: "display:flex;gap:12px;align-items:center" }, filt, h("button", { onclick: () => tick(true) }, "filter"),
                h("label", { class: "muted" }, runs, " show runs (agent.started, agent.ran)")), h("h2", {}, "events"), box, h("h2", {}, "items"), items);
  runs.addEventListener("change", () => tick());
  async function tick() {
    let evs = await api("events", { n: runs.checked ? 60 : 300, ...(filt.value ? { type: filt.value } : {}) });
    if (!runs.checked && !filt.value) evs = evs.filter((e) => !["agent.started", "agent.ran"].includes(e.type)).slice(-60);
    box.replaceChildren(eventsTable(evs, false));
    const its = await api("items");
    items.replaceChildren(h("table", {}, h("tr", {}, ["item", "events", "latest", "last"].map((x) => h("th", {}, x))),
      its.slice(0, 40).map((i) => h("tr", { class: "click", onclick: () => { location.hash = `#/item/${encodeURIComponent(i.item)}`; } },
        h("td", {}, h("b", {}, i.item)), h("td", { class: "num" }, i.n), h("td", {}, i.latest), h("td", {}, ago(i.last))))));
  }
  await tick();
  S.timer = setInterval(tick, 3000);
}

async function pageItem(main, name) {
  const p = page(main, name, "An item: every event about one id, folded.");
  const d = await api(`items/${encodeURIComponent(name)}`);
  p.append(h("h2", {}, "fields"), dl(Object.entries(d.fields).map(([k, v]) => [k, typeof v === "object" ? JSON.stringify(v) : String(v)])),
           h("h2", {}, `events (${d.events.length})`), eventsTable(d.events, true));
}

async function pageResiduals(main) {
  const p = page(main, "Residuals", "For each stock: how much its readings changed in the window, how much its known flows explain, and the rest. A disturbance nothing measures is estimated from the rest; anything left is unexplained, and worth a look.");
  const r = await api("residuals");
  p.append(h("table", {}, h("tr", {}, ["stock", "changed", "explained", "unexplained", ""].map((x) => h("th", {}, x))),
    Object.entries(r).map(([k, v]) => h("tr", {}, h("td", {}, h("b", {}, k)), h("td", { class: "num" }, fmt(v.change)), h("td", { class: "num" }, fmt(v.explained)),
      h("td", { class: "num" }, fmt(v.unexplained)),
      h("td", {}, v.significant ? h("span", { class: "s-open status" }, "unexplained") : (v.absorbed_by.length ? `estimated as ${v.absorbed_by.join(", ")}` : h("span", { class: "s-holding status" }, "explained")))))));
  if (!Object.keys(r).length) p.append(h("p", { class: "muted" }, "no stock has two readings in this window yet"));
}

async function pageGuide(main) {
  const p = page(main, "Guide", "ergostat keeps work going. It treats the work around you as a factory, and runs it as a control system. Here is how to read yours.");
  const [parts, agents] = [await api("parts"), await api("agents")];
  const code = (t) => h("code", {}, t);
  const ex = (list, f, n = 2) => list.slice(0, n).map((x, i) => [i ? ", " : "", f(x)]);
  const sec = (title, ...kids) => p.append(h("section", { class: "guide" }, h("h2", {}, title), ...kids));
  const stock = parts.stock[0], loop = parts.controller[0];
  sec("Work is a flow, not a list",
    h("p", {}, "Work is change in the world over time. ergostat does not track tasks; it watches what accumulates and what moves it. ",
      "What accumulates is a ", h("b", {}, "stock"), ": ", ex(parts.stock, (x) => [code(x.name), ` (${fmt(x.value)} ${x.unit})`]) , ". ",
      "What moves a stock is a ", h("b", {}, "flow"), ", drawn as a pipe. A flow nothing controls is a ", h("b", {}, "disturbance"), ": ",
      parts.disturbance.length ? ex(parts.disturbance, (x) => code(x.name)) : "you have none declared", "."));
  sec("Three roles keep it steady",
    h("p", {}, "A ", h("b", {}, "sensor"), " measures (", ex(parts.sensor, (x) => code(x.name)), "). ",
      "A ", h("b", {}, "controller"), " decides, to hold a stock at a setpoint (", ex(parts.controller, (x) => [code(x.name), ` holds ${x.holds} ${x.setpoint}`]), "). ",
      "A ", h("b", {}, "valve"), " acts on a flow (", ex(parts.valve, (x) => code(x.name)), "). Nothing changes the world except through a valve."),
    loop ? h("p", {}, "Together they make a ", h("b", {}, "loop"), ": ", code(loop.name), " measures ", code(loop.holds),
      ", compares it with its setpoint, and opens a valve when it is off. Its status now: ", statusEl(loop.status), ". ",
      h("a", { href: "#/diagram?view=blocks" }, "See it as a block diagram"), ".") : null);
  const byRung = {};
  for (const [n, a] of Object.entries(agents)) (byRung[a.rung] ||= []).push(n);
  sec("Agents fill the roles, and move down the ladder",
    h("p", {}, "An ", h("b", {}, "agent"), " is whatever acts on your behalf: a person, an AI agent, a decision, a program, a rule. ",
      "One agent can fill several roles. Every agent is held to the same discipline: measured, bounded, and acting only through the valves you grant."),
    h("p", {}, "The ladder runs from the most general agent to none at all. Yours: ",
      [0, 1, 2, 3, 4, 5].filter((r) => byRung[r]).map((r, i) => [i ? "; " : "", h("b", {}, RUNG_NAMES[r]), " ", byRung[r].join(", ")]), ". ",
      "Every role is expected to move down: start with an AI agent, then a narrower one, a decision, a program, a rule, and finally design the work out. ",
      h("a", { href: "#/agents" }, "See the ladder"), "."));
  sec("When the model does not explain it",
    h("p", {}, "A ", h("b", {}, "residual"), " is what a stock did that its known flows do not explain. An unmeasured disturbance is estimated from it; anything left over is worth a look: ",
      "it is either a disturbance you have not named, or the plant behaving differently than you think. ", h("a", { href: "#/residuals" }, "Your residuals"), "."));
  sec("Reading the diagram", legend("control"), h("p", {}, "Systems are outlines around parts that belong together; they may overlap. ",
    "The wiring view shows the agents and how each one's output reaches another. The slider in the header shows any past moment."));
  if (!stock) p.append(h("p", { class: "muted" }, "Your model is empty: describe your system with ergostat chat, or start from ergostat check --example."));
}

async function pageCheck(main) {
  const p = page(main, "Check", "Is the model whole? References that do not resolve are errors; loops that cannot close and parts nothing fills are warnings.");
  const st = await api("status");
  const list = h("div", { class: "att" });
  if (!st.check.length) list.append(h("div", { class: "ok" }, "the model is whole"));
  for (const c of st.check) list.append(h("div", { class: c.level === "error" ? "bad" : "" }, h("b", {}, c.level), " ", c.message));
  p.append(list, h("h2", {}, "counts"), dl(Object.entries(st.counts).map(([k, v]) => [k, String(v)])));
}

/* ------------------------------------------------------------------ start */

$("#since").addEventListener("change", (ev) => { S.since = ev.target.value; S.graphSig = ""; route(); });

/* the time slider: the right end is now (live); anywhere else is that moment, over the window before it */
const WINDOWS = { "10m": 600, "1h": 3600, "6h": 21600, "1d": 86400, "7d": 604800 };
function sliderSpan() {
  const now = Date.now() / 1000;
  const lo = Math.max(now - WINDOWS[S.since] * 3, S.first || now - WINDOWS[S.since]);
  return [lo, now];
}
function showAt() {
  const label = $("#atlabel"), live = $("#live");
  if (!S.at) { label.textContent = "live"; live.hidden = true; $("#at").value = 1000; return; }
  const d = new Date(S.at * 1000);
  label.textContent = "as of " + d.toLocaleTimeString([], { hour12: false }) + ` (${ago(S.at)})`;
  live.hidden = false;
}
$("#at").addEventListener("input", (ev) => {
  const [lo, hi] = sliderSpan();
  const v = +ev.target.value;
  S.at = v >= 998 ? null : lo + (hi - lo) * (v / 1000);
  showAt();
});
$("#at").addEventListener("change", () => { refreshHeader(); route(); });
$("#live").addEventListener("click", () => { S.at = null; showAt(); refreshHeader(); route(); });
window.addEventListener("hashchange", route);
document.addEventListener("keydown", (ev) => { if (ev.key === "Escape") closeDetail(); });
(async () => {
  await refreshHeader();
  setInterval(refreshHeader, 3000);
  route();
})();
