/* the system dynamics view: the stock-and-flow diagram as Sterman's Business Dynamics, Vensim and
   Stella draw it, by Vensim's rule: levels in boxes, rates with bowtie valves, every other variable
   unadorned (its name alone). The graph comes drawn from the model already (ergostat/dynamics.py):
   stocks, flows with their valves, clouds, auxiliaries, each
   goal as a desired level and a gap, a decision where a rule reads several things and moves several,
   and connectors with their polarity. This file draws its parts, its connectors (thin curved arrows,
   + or − at the head), its loop markers (R, B or ? in a circular arrow, inside each loop), its legend
   and its panels. Black on white (or its dark equivalent); colour only for what is pointed at. */
"use strict";

const SD_SIZE = { valve: [40, 40], disturbance: [40, 40], cloud: [46, 30] };
const SD_STOCK_H = 44;
const MINUS = "−";
const sdSign = (p) => (p === "+" ? "+" : p === "-" ? MINUS : null);

function sdValue(n) {                                   // a stock's or an auxiliary's value, small, with its unit
  if (n.role === "desired" || n.role === "gap") return n.valueText || "–";
  if (n.role === "decision") return "";
  const v = n.valueText && n.valueText !== "?" ? n.valueText : "–";
  return n.unit ? `${v} ${n.unit}` : v;
}
function sdSize(n) {
  if (n.kind === "stock") return [Math.max(96, textWidth(n.label) * 1.05 + 28, textWidth(sdValue(n)) + 28), SD_STOCK_H];
  if (n.kind === "auxiliary") {                         // its name is the part: as wide as that, with its value under it
    const lines = sdAuxLines(n);
    return [Math.max(...lines.map((t) => textWidth(t) * (t === lines[0] ? 1.02 : 0.92))) + 10, 6 + lines.length * 14];
  }
  return SD_SIZE[n.kind] || [40, 40];
}
/* the lines written beside a part (under a valve or a converter): its name, then its value */
function sdLabelLines(n) {
  if (n.kind === "valve" || n.kind === "disturbance") return [n.label, n.rate == null ? "–" : n.rateText];
  return [];
}
function sdAuxLines(n) {
  if (n.role === "decision") return [n.label];
  return [n.label, sdValue(n), n.exogenous ? "(exogenous)" : null].filter(Boolean);
}
function sdLabel(ng, n, t, i, cx, y) {
  if (i === 0) return ng.append(s("text", { x: cx, y, "text-anchor": "middle", class: "t-label sd-name" }, t));
  ng.append(s("text", { x: cx, y, "text-anchor": "middle", class: "t-sub sd-value live" }, t));
}

/* parts, drawn with their top-left at 0,0 */
function sdStock(n, w, hgt) {
  const g = s("g");
  // its name and its value now, small and muted; its history is in its panel (no gauge, no sparkline)
  g.append(s("rect", { class: "hit sd-stock", width: w, height: hgt, "stroke-dasharray": n.outside ? "5 4" : null }));
  g.append(s("text", { x: w / 2, y: 19, "text-anchor": "middle", class: "t-label sd-name" }, n.label));
  g.append(s("text", { x: w / 2, y: 34, "text-anchor": "middle", class: "t-sub sd-value live" }, sdValue(n)));
  return g;
}
/* an auxiliary, unadorned as Vensim draws it: its name alone (its value under it, muted) */
function sdAux(n, w, hgt) {
  const g = s("g");
  g.append(s("rect", { class: "hit sd-aux", width: w, height: hgt, rx: 3 }), s("title", {}, sdTitle(n)));
  sdAuxLines(n).forEach((t, i) => g.append(s("text", { x: w / 2, y: 14 + i * 14, "text-anchor": "middle",
    class: i === 0 ? "t-label sd-name" : t === "(exogenous)" ? "t-sub sd-exo" : "t-sub sd-value" + (n.role === "desired" ? "" : " live") }, t)));
  return g;
}
function sdTitle(n) {
  if (n.role === "desired") return `desired ${n.of}: the goal's setpoint, ${n.valueText}`;
  if (n.role === "gap") return `${n.of} gap: desired ${n.of} − ${n.of}`;
  if (n.role === "decision") return `${n.label}: a decision, from what it reads to what it moves`;
  return n.exogenous ? `${n.label}: an exogenous input` : `${n.label}: an auxiliary`;
}
function sdValve(n, w, hgt, ln) {
  const t = turnTransform(ln?.turn, w, hgt);          // turned with its pipe (valves.js)
  const g = s("g", t ? { transform: t } : {});
  g.append(s("rect", { class: "hit", x: -2, y: -2, width: w + 4, height: hgt + 4, rx: 6, fill: "transparent", stroke: "transparent" }));
  const pipe = `M0,${hgt / 2} H${w}`;                  // the pipe runs on through the valve
  g.append(s("path", { d: pipe, class: "sd-pipe-out" }), s("path", { d: pipe, class: "sd-pipe-in" }));
  g.append(s("path", { class: "sd-valve", d: `M6,9 L${w / 2},${hgt / 2} L6,${hgt - 9} Z M${w - 6},9 L${w / 2},${hgt / 2} L${w - 6},${hgt - 9} Z` }));
  return g;
}
function sdCloud(n, w, hgt) {
  const d = `M${w * 0.22},${hgt * 0.82} C${w * 0.02},${hgt * 0.82} ${w * 0.02},${hgt * 0.42} ${w * 0.22},${hgt * 0.45}
             C${w * 0.22},${hgt * 0.12} ${w * 0.55},${hgt * 0.08} ${w * 0.6},${hgt * 0.32}
             C${w * 0.7},${hgt * 0.12} ${w * 0.95},${hgt * 0.22} ${w * 0.86},${hgt * 0.5}
             C${w * 1.02},${hgt * 0.56} ${w * 0.98},${hgt * 0.84} ${w * 0.8},${hgt * 0.82} Z`;
  return s("g", {}, s("path", { class: "hit sd-cloud", d }));
}
/* a system closed: a module (Stella) or a view (Vensim): its name, and its ports, what crosses its edge */
function sdSystem(n, w, hgt) {
  const g = s("g");
  g.append(s("rect", { class: "hit sd-module", width: w, height: hgt, rx: 8 }));
  g.append(s("text", { x: 16, y: 24, class: "t-label sys-title" }, n.label));
  const inside = (S.graph?.causalLoops || []).filter((c) => c.nodes.includes(n.id) && sdVisible(c, S.graph).length < 2).length;
  g.append(s("text", { x: 16, y: 42, class: "t-sub" }, inside ? `${inside} feedback loop${inside > 1 ? "s" : ""} inside or through it` : "a module: open it to see its structure"));
  const btn = (x, label, title, fn) => s("g", { class: "sys-btn", transform: `translate(${x},10)`, onclick: (ev) => { ev.stopPropagation(); fn(); } },
    s("title", {}, title), s("rect", { width: textWidth(label) + 14, height: 20, rx: 5 }), s("text", { x: 7, y: 14 }, label));
  const into = "⤓ into", open = "▸ open";
  g.append(btn(w - textWidth(into) - 24, into, "draw this system alone, with what it reaches outside at its edge", () => S.drill?.(n.label)));
  g.append(btn(w - textWidth(into) - textWidth(open) - 46, open, "open it here: its parts in place of the box", () => S.toggleSystem?.(n.label)));
  const at = { west: 0, east: 0 };
  for (const p of n.ports || []) {
    const side = p.at || (p.side === "in" ? "west" : "east");
    const y = sysTop(n) + (at[side]++) * SYS_ROW;
    const left = side === "west";
    g.append(s("rect", { x: left ? -4 : w - 4, y: y - 4, width: 8, height: 8, class: "sd-port" }));
    g.append(s("text", { x: left ? 12 : w - 12, y: y + 4, class: "t-sub", "text-anchor": left ? "start" : "end" },
      s("title", {}, `${p.side === "in" ? "in" : "out"}: ${sdKindWord(p.kind)} ${p.label}`),
      p.label, p.value ? s("tspan", { class: "live", dx: 6, opacity: 0.75 }, p.value) : null));
  }
  return g;
}
/* a part outside the system drawn alone: as Vensim's shadow variable, its name in angle brackets */
function sdTerminal(n, w, hgt) {
  const g = s("g");
  g.append(s("rect", { class: "hit", width: w, height: hgt, rx: 4, fill: "transparent", stroke: "transparent" }));
  g.append(s("text", { x: w / 2, y: hgt / 2 + 4, "text-anchor": "middle", class: "t-sub sd-shadow" }, `<${n.label}>`,
    s("title", {}, `${n.label}: outside this system${n.in ? `, in ${n.in}` : ""} (click to go there)`)));
  return g;
}
const SD_DRAW = { stock: sdStock, auxiliary: sdAux, valve: sdValve, disturbance: sdValve, cloud: sdCloud, system: sdSystem, terminal: sdTerminal };
function sdKindWord(k) { return { valve: "flow", disturbance: "flow", stock: "stock", auxiliary: "auxiliary", cloud: "cloud" }[k] || k || ""; }

/* ------------------------------------------------------------------ connectors */

/* a connector's curve along its routed way: through each bend smoothly (the bends as the control
   points of a chain of quadratic curves, joined where they meet halfway), or, routed straight, bowed a
   little, as Vensim draws its arcs. It never cuts through a part: if the smooth curve would, its
   corners are only rounded */
function sdCurve(pts, blocked) {
  const n = pts.length;
  const hits = (segs) => blocked && segs.some((sg) => {           // sampled every few pixels along it
    const a = sg(0), b = sg(0.5), c = sg(1), n = Math.max(12, Math.ceil((Math.hypot(b.x - a.x, b.y - a.y) + Math.hypot(c.x - b.x, c.y - b.y)) / 4));
    for (let i = 1; i < n; i++) { const p = sg(i / n); if (blocked(p)) return true; }
    return false;
  });
  const q = (a, c, b) => (t) => ({ x: (1 - t) * (1 - t) * a.x + 2 * (1 - t) * t * c.x + t * t * b.x,
                                   y: (1 - t) * (1 - t) * a.y + 2 * (1 - t) * t * c.y + t * t * b.y });
  if (n === 2) {
    const [a, b] = pts, L = Math.hypot(b.x - a.x, b.y - a.y);
    const bow = L > 60 ? Math.min(0.1 * L, 18) : 0;
    for (const k of bow ? [1, -1] : []) {
      const c = { x: (a.x + b.x) / 2 - ((b.y - a.y) / L) * bow * k, y: (a.y + b.y) / 2 + ((b.x - a.x) / L) * bow * k };
      if (!hits([q(a, c, b)])) return { d: `M${a.x},${a.y} Q${c.x},${c.y} ${b.x},${b.y}`, tail: c, tip: b, mid: q(a, c, b)(0.5) };
    }
    return { d: `M${a.x},${a.y} L${b.x},${b.y}`, tail: a, tip: b, mid: { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 } };
  }
  const m = (a, b) => ({ x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 });
  let d = `M${pts[0].x},${pts[0].y}`, from = pts[0];
  const segs = [];
  for (let i = 1; i < n - 1; i++) {
    const to = i === n - 2 ? pts[n - 1] : m(pts[i], pts[i + 1]);
    d += ` Q${pts[i].x},${pts[i].y} ${to.x},${to.y}`;
    segs.push(q(from, pts[i], to));
    from = to;
  }
  if (!hits(segs)) return { d, tail: pts[n - 2], tip: pts[n - 1], mid: segs[Math.floor(segs.length / 2)](0.5) };
  return { d: roundedPath(pts, 6), tail: pts[n - 2], tip: pts[n - 1], mid: pts[Math.floor(n / 2)] };   // (its corners only eased)
}

/* what a connector may not cut through: every part but its two ends (and clouds), a little inside */
function sdBlocked(lay, e) {
  const own = new Set([e.source, e.target]);
  const kids = (lay.children || []).filter((c) => !own.has(c.id) && !c.id.startsWith("cloud:"));
  return (p) => kids.some((c) => p.x > c.x + 3 && p.x < c.x + c.width - 3 && p.y > c.y + 3 && p.y < c.y + c.height - 3);
}

/* a line's drawing: a flow's double pipe with its hollow head (and one at its start too, a biflow's),
   or a connector, thin and curved, its arrowhead and its polarity at the head */
function sdEdgeContent(e, pts, lay) {
  const out = [];
  if (e.kind === "pipe") {
    const two = e.twoWay && !e.arrow;                  // a biflow: its first pipe ends in a head at its start too
    let body = e.arrow ? shortened(pts, 14) : pts;
    if (two) body = shortened(body.slice().reverse(), 14).reverse();
    const bd = roundedPath(body, 10);
    out.push(s("path", { d: bd, class: "pipe-out" }), s("path", { d: bd, class: "pipe-in" }));
    if (e.arrow) out.push(sdPipeHead(pts, "pipe-head"));
    if (two) out.push(sdPipeHead(pts.slice().reverse(), "pipe-tail"));
    return out;
  }
  const c = sdCurve(pts, sdBlocked(lay, e));
  out.push(s("path", { d: c.d, class: "info sd-connector" }));
  const head = arrowHead([c.tail, c.tip], "head sd-head", 7);
  out.push(head);
  const sign = sdSign(e.polarity);
  if (sign) {
    const L = Math.hypot(c.tip.x - c.tail.x, c.tip.y - c.tail.y) || 1;
    const ux = (c.tip.x - c.tail.x) / L, uy = (c.tip.y - c.tail.y) / L;
    // beside the head; where another sign is already, on its other side or further back
    const taken = (S.sdSigns ||= []);
    const at = [[14, 9], [14, -9], [26, 9], [26, -9], [38, 9]].map(([b, o]) => ({ x: c.tip.x - ux * b - uy * o, y: c.tip.y - uy * b + ux * o }));
    const p = at.find((q2) => !taken.some((t) => Math.hypot(t.x - q2.x, t.y - q2.y) < 12)) || at[0];
    taken.push(p);
    out.push(s("text", { x: p.x, y: p.y + 4.5, "text-anchor": "middle", class: "polarity", "paint-order": "stroke" }, sign));
  }
  return out;
}
function sdPipeHead(pts, cls) {                         // a flow's head: hollow, as wide as the pipe and more, at its very end
  const a = pts[pts.length - 2], b = pts[pts.length - 1];
  const ang = Math.atan2(b.y - a.y, b.x - a.x), L = 15, Wd = 9;
  const bx = b.x - L * Math.cos(ang), by = b.y - L * Math.sin(ang);
  const px = -Math.sin(ang) * Wd, py = Math.cos(ang) * Wd;
  return s("path", { class: cls, d: `M${bx + px},${by + py} L${b.x},${b.y} L${bx - px},${by - py} Z`,
                     style: "fill:var(--sd-paper);stroke:var(--sd-ink);stroke-width:1.6;stroke-linejoin:round" });
}

/* ------------------------------------------------------------------ loop markers */

/* each feedback loop's marker, as Sterman draws them: its polarity and number (R1, B2; ? when a sign
   along it is not known) in a circular arrow turning the way the loop runs, its name under it, placed
   inside the loop: as near the middle of its parts as is clear of every part, label and other marker */
function sdLoopMarkers(g, lay) {
  const box = Object.fromEntries(lay.children.map((c) => [c.id, c]));
  const taken = [];
  for (const c of lay.children) {
    const xs = [c.x, c.x + c.width], ys = [c.y, c.y + c.height];
    for (const l of c.labels || []) { xs.push(c.x + l.x, c.x + l.x + l.width); ys.push(c.y + l.y, c.y + l.y + l.height); }
    taken.push({ x: Math.min(...xs), y: Math.min(...ys), x1: Math.max(...xs), y1: Math.max(...ys) });
  }
  for (const h of lay.containers || []) taken.push({ x: h.x, y: h.y, x1: h.x + h.width, y1: h.y + 32 });   // an outline's handle
  const pipes = new Set(g.edges.filter((e) => e.kind === "pipe").map((e) => e.id));
  for (const le of lay.edges) {                         // and off the pipes: a marker on a flow reads as part of it
    if (!pipes.has(le.id)) continue;
    const p = edgePoints(le);
    for (let i = 1; i < p.length; i++) taken.push({ x: Math.min(p[i - 1].x, p[i].x) - 5, y: Math.min(p[i - 1].y, p[i].y) - 5,
                                                    x1: Math.max(p[i - 1].x, p[i].x) + 5, y1: Math.max(p[i - 1].y, p[i].y) + 5 });
  }
  const free = (r) => !taken.some((t) => r.x < t.x1 + 4 && t.x < r.x1 + 4 && r.y < t.y1 + 4 && t.y < r.y1 + 4);
  const out = s("g", { class: "loop-markers" });
  const placed = {};
  for (const { rep, loops } of sdLoopGroups(g, box)) {
    const ids = rep.nodes.filter((id) => box[id]);
    const at = ids.map((id) => ({ x: box[id].x + box[id].width / 2, y: box[id].y + box[id].height / 2 }));
    const uniq = sdVisible(rep, g, box).map((id) => ({ x: box[id].x + box[id].width / 2, y: box[id].y + box[id].height / 2 }));
    const cx = uniq.reduce((a, p) => a + p.x, 0) / uniq.length, cy = uniq.reduce((a, p) => a + p.y, 0) / uniq.length;
    let area = 0;                                        // which way it runs, on the screen (y down: > 0 is clockwise)
    for (let i = 0; i < at.length; i++) { const p = at[i], q2 = at[(i + 1) % at.length]; area += p.x * q2.y - q2.x * p.y; }
    // its name under it (shortened in the middle: its end tells it from its twins); one whose polarity is
    // not known only its number, its name on hover and in the list, so the loops that are known stand out
    const name = !rep.polarity ? "" : rep.name.length > 26 ? rep.name.slice(0, 11) + "…" + rep.name.slice(-13) : rep.name;
    const more = loops.length > 1 ? ` +${loops.length - 1}` : "";
    const w = Math.max(28 + (more ? 22 : 0), textWidth(name) * 0.92 + 6), hgt = name ? 40 : 28;
    const rect = (x, y) => ({ x: x - w / 2, y: y - 14, x1: x + w / 2, y1: y - 14 + hgt });
    let spot = null;
    for (let r = 0; r <= 640 && !spot; r += 10) {
      const k = Math.max(1, Math.round((2 * Math.PI * r) / 16));
      for (let i = 0; i < k; i++) {
        const a = (i / k) * 2 * Math.PI, x = cx + r * Math.cos(a), y = cy + r * Math.sin(a);
        if (free(rect(x, y))) { spot = { x, y }; break; }
      }
    }
    spot ||= { x: cx, y: cy };
    taken.push(rect(spot.x, spot.y));
    for (const c of loops) placed[c.name] = spot;
    out.append(sdMarker(rep, spot.x, spot.y, area >= 0, name, loops));
  }
  lay.markers = placed;
  return out;
}
/* a loop's parts drawn here as themselves (not folded into a closed system, nor outside it) */
function sdVisible(c, g, box) {
  const kind = Object.fromEntries(g.nodes.map((n) => [n.id, n.kind]));
  return [...new Set(c.nodes.filter((id) => (box ? box[id] : kind[id]) && !["system", "terminal"].includes(kind[id])))];
}
/* the loops that show here (two of their parts drawn as themselves), one marker for those drawn alike
   (the same parts here: they differ only where they run inside a closed system or outside this one),
   the best known of them first */
function sdLoopGroups(g, box = null) {
  const groups = new Map();
  for (const c of g.causalLoops || []) {
    const v = sdVisible(c, g, box);
    if (v.length < 2) continue;
    const key = v.slice().sort().join("|");
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(c);
  }
  const rank = (c) => [c.polarity ? 0 : 1, c.nodes.length, c.name];
  return [...groups.values()].map((loops) => {
    loops.sort((a, b) => { const x = rank(a), y = rank(b); return x[0] - y[0] || x[1] - y[1] || (x[2] > y[2]) - (x[2] < y[2]); });
    return { rep: loops[0], loops };
  });
}
function sdMarker(c, x, y, clockwise, name, loops = [c]) {
  const r = 11, start = clockwise ? -60 : -120, end = clockwise ? 240 : -60;   // a gap at the top, the head at its end
  const P = (deg) => [r * Math.cos((deg * Math.PI) / 180), r * Math.sin((deg * Math.PI) / 180)];
  const [x0, y0] = P(start), [x1, y1] = P(end), rad = (end * Math.PI) / 180;
  const dx = clockwise ? -Math.sin(rad) : Math.sin(rad), dy = clockwise ? Math.cos(rad) : -Math.cos(rad);   // the way it turns, at the end
  const tip = [x1 + dx * 4.5, y1 + dy * 4.5], base = [x1 - dx * 2, y1 - dy * 2], px = -dy * 4, py = dx * 4;
  const words = { R: "reinforcing", B: "balancing" }[c.polarity] || "polarity not known: a sign along it is not known";
  const label = c.label || (c.polarity || "?");
  const g = s("g", { class: `loop-marker pol-${c.polarity || "unknown"}`, "data-loop": c.name, "data-loops": loops.map((x2) => x2.name).join(" "),
                     "data-act": "loop", transform: `translate(${x},${y})`,
                     onclick: (ev) => { ev.stopPropagation(); sdHighlight(c.name); openCausal(c.name); },
                     onpointerenter: () => { if (!S.dragging) sdHover(c.name); }, onpointerleave: () => sdHover(null) },
    s("title", {}, `${label} ${c.name}: ${words} (click: its parts, and what it is)` +
      (loops.length > 1 ? `\nand ${loops.length - 1} more drawn alike here: ${loops.slice(1).map((x2) => `${x2.label} ${x2.name}`).join(", ")}` : "")),
    s("circle", { class: "marker-hit", r: r + 4 }),
    s("path", { class: "marker-arc", d: `M${x0},${y0} A${r},${r} 0 1 ${clockwise ? 1 : 0} ${x1},${y1}` }),
    s("path", { class: "marker-head", d: `M${tip[0]},${tip[1]} L${base[0] + px},${base[1] + py} L${base[0] - px},${base[1] - py} Z` }),
    s("text", { class: "marker-letter", y: 3.8, "text-anchor": "middle", style: label.length > 2 ? "font-size:8.5px" : null }, label),
    loops.length > 1 ? s("text", { class: "marker-more", x: r + 3, y: 4, "text-anchor": "start" }, `+${loops.length - 1}`) : null,
    name ? s("text", { class: "marker-name", y: r + 13, "text-anchor": "middle" }, name) : null);
  return g;
}

/* a loop pointed at or chosen: its parts and its links lit, the rest faded */
function sdHover(name) { sdApply(name || S.hlCausal); }
function sdHighlight(name) { S.hlCausal = name; sdApply(name); }
function sdApply(name) {
  const svg = $("svg.canvas");
  if (!svg) return;
  const c = name && (S.graph?.causalLoops || []).find((x) => x.name === name);
  const members = new Set(c ? c.nodes : []);
  svg.classList.toggle("loop-hl", !!c);
  for (const n of svg.querySelectorAll(".node")) { n.classList.toggle("dim", !!c && !members.has(n.dataset.id)); n.classList.toggle("in-loop", !!c && members.has(n.dataset.id)); }
  for (const e of svg.querySelectorAll(".edge")) {
    const ge = S.edgeById?.[e.dataset.id], on = !!c && (ge?.causal || []).includes(name);
    e.classList.toggle("dim", !!c && !on);
    e.classList.toggle("in-loop", on);
  }
  for (const m of svg.querySelectorAll(".loop-marker")) {
    const mine = !!name && (m.dataset.loops || "").split(" ").includes(name);
    m.classList.toggle("on", mine); m.classList.toggle("dim", !!c && !mine);
  }
  for (const r of document.querySelectorAll(".looprow")) r.classList.toggle("hl", r.dataset.loop === name);
}

/* ------------------------------------------------------------------ the side panel, the legend */

function sdLoopList(side, g) {
  const order = { R: 0, B: 1 };
  const all = sdLoopGroups(g).flatMap((x) => x.loops)
    .sort((a, b) => (order[a.polarity] ?? 2) - (order[b.polarity] ?? 2) || (parseInt(a.label.slice(1)) - parseInt(b.label.slice(1))));
  side.append(h("h3", {}, `feedback loops (${all.length})`));
  if (!all.length) side.append(h("div", { class: "muted" }, "no feedback loops drawn here"));
  const counts = ["R", "B", null].map((p) => [p, all.filter((c) => (c.polarity || null) === p).length]).filter(([, n]) => n);
  if (counts.length) side.append(h("div", { class: "muted small" }, counts.map(([p, n]) => `${n} ${{ R: "reinforcing", B: "balancing" }[p] || "of unknown polarity"}`).join(", ")));
  for (const c of all) {
    side.append(h("div", { class: "looprow", "data-loop": c.name, onmouseenter: () => sdHover(c.name), onmouseleave: () => sdHover(null),
                           onclick: () => { sdHighlight(c.name); openCausal(c.name); } },
      h("div", {}, h("span", { class: `loop-tag pol-${c.polarity || "unknown"}` }, c.label), " ", h("b", {}, c.name)),
      h("div", { class: "sub" }, `${{ R: "reinforcing", B: "balancing" }[c.polarity] || "polarity not known"} · ${new Set(c.nodes).size} parts`)));
  }
}

const SD_LEGEND = {
  stock: '<rect x="3" y="3" width="20" height="12" fill="var(--sd-paper)" stroke="var(--sd-ink)" stroke-width="1.4"/>',
  flow: '<path d="M0 9 H21" stroke="var(--sd-ink)" stroke-width="7"/><path d="M0 9 H21" stroke="var(--sd-paper)" stroke-width="3.6"/><path d="M8 3 L13 9 L8 15 Z M18 3 L13 9 L18 15 Z" fill="var(--sd-paper)" stroke="var(--sd-ink)" stroke-width="1.2"/><path d="M21 4 L26 9 L21 14 Z" fill="var(--sd-paper)" stroke="var(--sd-ink)" stroke-width="1.2"/>',
  biflow: '<path d="M5 9 H21" stroke="var(--sd-ink)" stroke-width="7"/><path d="M5 9 H21" stroke="var(--sd-paper)" stroke-width="3.6"/><path d="M5 4 L0 9 L5 14 Z M21 4 L26 9 L21 14 Z" fill="var(--sd-paper)" stroke="var(--sd-ink)" stroke-width="1.2"/>',
  cloud: '<path d="M6 14 C1 14 1 8 6 8 C6 3 13 2 14 6 C17 3 23 5 21 9 C25 10 24 15 20 14 Z" fill="var(--sd-paper)" stroke="var(--sd-ink)" stroke-width="1.1"/>',
  aux: '<text x="13" y="13" font-size="10" text-anchor="middle" fill="var(--sd-ink)">name</text>',
  exo: '<text x="13" y="9" font-size="9" text-anchor="middle" fill="var(--sd-ink)">name</text><text x="13" y="17" font-size="6.5" font-style="italic" text-anchor="middle" fill="var(--sd-muted)">(exog.)</text>',
  plus: '<path d="M1 14 Q12 2 22 9" fill="none" stroke="var(--sd-ink)" stroke-width="1.1"/><path d="M25 11 L18 10 L21 5 Z" fill="var(--sd-ink)"/><text x="15" y="18" font-size="10" font-weight="700" fill="var(--sd-ink)">+</text>',
  minus: '<path d="M1 14 Q12 2 22 9" fill="none" stroke="var(--sd-ink)" stroke-width="1.1"/><path d="M25 11 L18 10 L21 5 Z" fill="var(--sd-ink)"/><text x="15" y="18" font-size="11" font-weight="700" fill="var(--sd-ink)">−</text>',
  plain: '<path d="M1 14 Q12 2 22 9" fill="none" stroke="var(--sd-ink)" stroke-width="1.1"/><path d="M25 11 L18 10 L21 5 Z" fill="var(--sd-ink)"/>',
  loopR: '<path d="M17.5 3.2 A7 7 0 1 1 8.5 3.2" fill="none" stroke="var(--sd-ink)" stroke-width="1.2"/><path d="M6 1.5 L10.5 3 L7 6.5 Z" fill="var(--sd-ink)"/><text x="13" y="12.5" font-size="8" font-weight="700" text-anchor="middle" fill="var(--sd-ink)">R</text>',
  loopB: '<path d="M17.5 3.2 A7 7 0 1 1 8.5 3.2" fill="none" stroke="var(--sd-ink)" stroke-width="1.2"/><path d="M6 1.5 L10.5 3 L7 6.5 Z" fill="var(--sd-ink)"/><text x="13" y="12.5" font-size="8" font-weight="700" text-anchor="middle" fill="var(--sd-ink)">B</text>',
  loopQ: '<path d="M17.5 3.2 A7 7 0 1 1 8.5 3.2" fill="none" stroke="var(--sd-muted)" stroke-width="1.2"/><path d="M6 1.5 L10.5 3 L7 6.5 Z" fill="var(--sd-muted)"/><text x="13" y="12.5" font-size="8" font-weight="700" text-anchor="middle" fill="var(--sd-muted)">?</text>',
  module: '<rect x="2" y="2" width="22" height="14" rx="3" fill="var(--sd-paper)" stroke="var(--sd-ink)" stroke-width="1.3"/><rect x="0" y="6" width="4" height="4" fill="var(--sd-paper)" stroke="var(--sd-ink)"/>',
  shadow: '<text x="13" y="13" font-size="10" text-anchor="middle" fill="var(--sd-muted)">&lt;x&gt;</text>',
};
function sdLegend() {
  const g = S.graph || { nodes: [], edges: [] };
  const has = (f) => g.nodes.some(f);
  const row = (key, text) => [h("span", { html: `<svg width="26" height="18">${SD_LEGEND[key]}</svg>` }), h("span", {}, text)];
  const pols = new Set((g.causalLoops || []).map((c) => c.polarity || "?"));
  return h("div", { class: "legend sd-legend" },
    row("stock", "stock (level): what accumulates; it changes only by its flows"),
    row("flow", "flow (rate): a pipe with its valve, into or out of a stock; the head shows which way"),
    g.edges.some((e) => e.twoWay) && row("biflow", "biflow: a flow that may run either way"),
    has((n) => n.kind === "cloud") && row("cloud", "source or sink: outside the model's boundary"),
    has((n) => n.kind === "auxiliary") && row("aux", "auxiliary: a name alone, worked out at each moment from what points into it (no memory)"),
    has((n) => n.exogenous) && row("exo", "exogenous input: from outside the model, nothing in it drives it (marked under its name)"),
    has((n) => n.role === "gap") && row("aux", "desired level and gap: a goal, as goal-seeking structure (gap = desired − actual)"),
    has((n) => n.role === "decision") && row("aux", "decision: what a rule reads, joined to the flows it sets"),
    row("plus", "connector, +: the cause rises, the effect rises above what it would have been"),
    row("minus", "connector, −: the cause rises, the effect falls below what it would have been"),
    g.edges.some((e) => e.kind === "connector" && !e.polarity) && row("plain", "connector, no sign: the polarity is not known"),
    pols.has("R") && row("loopR", "reinforcing loop: a change comes back amplified"),
    pols.has("B") && row("loopB", "balancing loop: a change comes back opposed (goal seeking)"),
    pols.has("?") && row("loopQ", "loop whose polarity is not known: a sign along it is not known"),
    has((n) => n.kind === "system") && row("module", "module: a system closed; its ports are what crosses its edge (▸ opens it, ⤓ draws it alone)"),
    has((n) => n.kind === "terminal") && row("shadow", "shadow variable: a part outside this system (click to go there)"));
}
/* the same, in one row under a saved picture */
function sdExportItems() {
  const g = S.graph || { nodes: [], edges: [] };
  return [["stock", "stock"], ["flow", "flow"], g.edges.some((e) => e.twoWay) && ["biflow", "biflow"], ["cloud", "source / sink"],
          ["aux", "auxiliary"], g.nodes.some((n) => n.exogenous) && ["exo", "exogenous"], ["plus", "connector +"], ["minus", "connector −"],
          ["loopR", "reinforcing"], ["loopB", "balancing"], ["loopQ", "polarity not known"]].filter(Boolean);
}

/* ------------------------------------------------------------------ panels */

const SD_WHAT = {
  stock: ["Stock", "a level: what accumulates. It changes only by its flows, filling by its inflows and draining by its outflows, and keeps its value when they stop."],
  auxiliary: ["Auxiliary", "a converter: worked out at each moment from the parts that point into it, with no memory of its own (here it is measured, so no equation is written)."],
  exogenous: ["Exogenous input", "an auxiliary from outside the model's boundary: nothing in the model drives it, and it drives what it points into."],
  desired: ["Desired level", "the goal, drawn as system dynamics draws goal-seeking structure: the level wanted, compared with the actual one in the gap."],
  gap: ["Gap", "the discrepancy: the desired level less the actual one. It drives the flow that closes it, so the stock is pulled toward its goal: a balancing loop."],
  decision: ["Decision", "a decision rule: what it reads (the connectors into it) decides the flows it sets (the connectors out of it). What it does with each reading is its own, so those links have no sign."],
  flow: ["Flow", "a rate: what moves into or out of a stock per hour, along its pipe. Its valve is where the rate is set; the connectors into it are what it depends on. A cloud at an end is outside the model's boundary."],
  pipe: ["Flow", "the pipe a flow runs along, from the stock it drains to the stock it fills (or a cloud: outside the model's boundary). Only flows change stocks."],
  connector: ["Connector", "an information link: the cause at its tail changes the effect at its head. Nothing moves along it. Its sign is its polarity: + when the effect moves the same way as the cause, − when the opposite way."],
  loop: ["Feedback loop", "a closed chain of cause and effect. Reinforcing (R): the product of its signs is +, so a change comes back amplified (growth or collapse). Balancing (B): the product is −, so a change comes back opposed (goal seeking). ?: a sign along it is not known."],
  system: ["Module", "a system drawn closed, as Stella draws a module: its ports are what crosses its edge. Open it to see its stocks, flows and loops."],
};
function sdWhat(kind) { const w = SD_WHAT[kind]; return w ? h("p", { class: "what" }, h("b", {}, w[0]), ": ", w[1]) : null; }
function sdNodeKind(n) {
  if (n.kind === "valve" || n.kind === "disturbance") return "flow";
  if (n.kind === "auxiliary") return n.role || (n.exogenous ? "exogenous" : "auxiliary");
  return n.kind;
}
function sdGraphLinks() {                              // each drawn part's panel, by id; a part in a closed system: its port's
  const g = S.graph || { nodes: [] };
  const byId = Object.fromEntries(g.nodes.map((n) => [n.id, n]));
  for (const box of g.nodes) for (const p of box.ports || []) {
    if (byId[p.part]) continue;
    const name = p.part.split(":").slice(1).join(":");
    byId[p.part] = { id: p.part, kind: p.kind, label: (p.kind === "valve" || p.kind === "disturbance") ? name : p.label, value: p.value, sd: true,
                     ...((p.kind === "valve" || p.kind === "disturbance") ? { flow: name } : {}),
                     ...(p.part.startsWith("gap:") ? { role: "gap" } : p.part.startsWith("desired:") ? { role: "desired" } : p.part.startsWith("decision:") ? { role: "decision" } : {}) };
  }
  const link = (id) => {
    const n = byId[id];
    if (n && n.kind !== "cloud" && n.kind !== "terminal") return h("a", { href: "#", onclick: (ev) => { ev.preventDefault(); openNode(n); } }, n.label);
    if (id.startsWith("cloud:")) return h("span", { class: "muted" }, "outside the model");
    if (n && n.kind === "terminal") return h("a", { href: "#", onclick: (ev) => { ev.preventDefault(); S.drill?.(n.in || ""); } }, n.label);
    return h("span", {}, id.split(":").slice(1).join(":"));
  };
  return { byId, link };
}
function loopsOf(pred) {
  return (S.graph?.causalLoops || []).filter(pred).map((c) => h("a", { href: "#", class: "loop-link", onclick: (ev) => { ev.preventDefault(); sdHighlight(c.name); openCausal(c.name); } },
    `${c.label} ${c.name}`));
}
function loopsPara(list) {
  if (!list.length) return h("p", { class: "muted" }, "in no feedback loop drawn here");
  const shown = list.slice(0, 12);
  return h("p", {}, `in ${list.length} feedback loop${list.length > 1 ? "s" : ""}: `, shown.flatMap((x, i) => [i ? ", " : "", x]), list.length > 12 ? ` and ${list.length - 12} more` : "");
}

async function openNodeSD(n) {
  const { byId, link } = sdGraphLinks();
  const g = S.graph || { edges: [] };
  const into = g.edges.filter((e) => e.kind === "connector" && original(e.target, e.targetPort) === n.id);
  const outof = g.edges.filter((e) => e.kind === "connector" && original(e.source, e.sourcePort) === n.id);
  const causes = into.map((e) => h("span", {}, link(original(e.source, e.sourcePort)), ` (${sdSign(e.polarity) || "?"})`));
  const effects = outof.map((e) => h("span", {}, link(original(e.target, e.targetPort)), ` (${sdSign(e.polarity) || "?"})`));
  const join = (xs) => (xs.length ? h("span", {}, xs.flatMap((x, i) => [i ? ", " : "", x])) : null);
  const kind = sdNodeKind(n);
  const rows = [];
  let chart = null;
  if (n.role === "desired" || n.role === "gap" || n.role === "decision") {
    rows.push(["goal", n.goal ? `${n.goal}: ${n.of} ${n.setpoint.replace("<=", "≤").replace(">=", "≥")}` : null],
              ["now", n.role === "gap" ? (n.valueText || "not known yet") : n.role === "desired" ? n.valueText : null],
              ["description", n.description]);
  } else if (n.kind === "valve" || n.kind === "disturbance") {
    let d = null;
    try { d = await api(`part/${n.kind === "disturbance" ? "disturbance" : "flow"}/${encodeURIComponent(n.flow || n.label)}`); } catch (err) { d = null; }
    const m = d?.model || {}, now = d?.now || {};
    rows.push(["description", m.description || n.description], ["from", m.source || "a source outside the model"], ["to", m.target || "a sink outside the model"],
              ["rate now", now.rate != null ? `${fmt(now.rate)}/h` : n.rateText], ["how it is known", now.how || n.how],
              ["runs", (m.two_way ?? n.twoWay) ? "either way (a biflow)" : "one way"]);
    if (now.points?.length > 1) chart = sparkSvg(now.points, 380, 70);
  } else {
    let d = null;
    try { d = await api(`part/stock/${encodeURIComponent(n.label)}`); } catch (err) { d = null; }
    const m = d?.model || {}, now = d?.now || {};
    rows.push(["description", m.description || n.description], ["now", `${fmt(now.value ?? n.value)} ${m.unit || n.unit || ""}`],
              ["measured", now.at ? ago(now.at) : null]);
    if (n.kind === "stock") rows.push(["inflow", now.inflow != null ? `${fmt(now.inflow)}/h` : null], ["outflow", now.outflow != null ? `${fmt(now.outflow)}/h` : null]);
    for (const gl of n.goals || []) rows.push(["goal", `${gl.name}: ${gl.setpoint.replace("<=", "≤").replace(">=", "≥")}${gl.acted ? "" : " (nothing in the model acts on it: no feedback)"}`]);
    if (now.points?.length > 1) chart = sparkSvg(now.points, 380, 70);
  }
  rows.push(["depends on", join(causes)], ["drives", join(effects)]);
  const id = n.id;
  showDetail(h("div", { class: "kind" }, (SD_WHAT[kind] || [kind])[0].toLowerCase() + " · system dynamics"), h("h2", {}, n.label), sdWhat(kind),
    h("h3", {}, "how it is now"), dl(rows), chart,
    loopsPara(loopsOf((c) => c.nodes.includes(id))),
    n.kind === "stock" || n.kind === "valve" || n.kind === "disturbance" || (n.kind === "auxiliary" && !n.role)
      ? h("p", {}, h("a", { href: `#/diagram?view=dynamics&around=${n.kind === "stock" || n.kind === "auxiliary" ? "stock" : "flow"}/${encodeURIComponent(n.flow || n.label)}` }, "draw what is around it")) : null);
  void byId;
}

function sdOpenSystem(n) {
  const side = (d) => (n.ports || []).filter((p) => p.side === d);
  const list = (ps, none) => ps.length ? h("table", {}, ps.map((p) => h("tr", {}, h("td", {}, p.label), h("td", { class: "muted" }, sdKindWord(p.kind)),
    h("td", { class: "num" }, p.value || "")))) : h("p", { class: "muted" }, none);
  const inside = (S.graph?.causalLoops || []).filter((c) => c.nodes.includes(n.id) && sdVisible(c, S.graph).length < 2);
  showDetail(h("div", { class: "kind" }, "module · system dynamics"), h("h2", {}, n.label), sdWhat("system"),
    n.description ? h("p", { class: "muted" }, n.description) : null,
    h("h3", {}, "in: what reaches it from outside"), list(side("in"), "nothing outside reaches in (here)"),
    h("h3", {}, "out: what it reaches outside"), list(side("out"), "nothing outside depends on it (here)"),
    inside.length ? h("p", {}, `${inside.length} feedback loop${inside.length > 1 ? "s" : ""} inside it or through it, not drawn here: open it to see them`) : null,
    loopsPara(loopsOf((c) => c.nodes.includes(n.id) && !inside.includes(c))),
    h("p", {}, h("button", { onclick: () => S.toggleSystem?.(n.label) }, "▸ open it here"), " ",
               h("button", { onclick: () => S.drill?.(n.label) }, "⤓ draw it alone")));
}

async function openEdgeSD(e) {
  const { byId, link } = sdGraphLinks();
  const src = original(e.source, e.sourcePort), dst = original(e.target, e.targetPort);
  const nameOf = (id) => byId[id]?.label ?? id.split(":").slice(1).join(":");
  const crossing = [e.sourcePort && `leaves the module ${e.source.slice(7)} at its port ${nameOf(src)}`,
                    e.targetPort && `enters the module ${e.target.slice(7)} at its port ${nameOf(dst)}`].filter(Boolean);
  const inLoops = loopsPara(loopsOf((c) => (e.causal || []).includes(c.name)));
  if (e.kind === "pipe") {
    let d = null;
    try { d = await api(`part/flow/${encodeURIComponent(e.flow)}`); } catch (err) { d = null; }
    const m = d?.model || {}, now = d?.now || {};
    const valve = Object.values(byId).find((n) => (n.kind === "valve" || n.kind === "disturbance") && (n.flow === e.flow));
    showDetail(h("div", { class: "kind" }, "flow · system dynamics"),
      h("h2", {}, e.flow, h("span", { class: "muted" }, ` (${m.source || "outside"} → ${m.target || "outside"})`)), sdWhat("pipe"),
      h("h3", {}, "how it is now"),
      dl([["flow", valve ? link(valve.id) : e.flow], ["from", m.source || "a source outside the model"], ["to", m.target || "a sink outside the model"],
          ["rate now", now.rate != null ? `${fmt(now.rate)}/h` : valve?.rateText], ["runs", (m.two_way ?? e.twoWay) ? "either way (a biflow)" : "one way"]]),
      crossing.length ? h("p", {}, crossing.join("; ") + ".") : null, inLoops);
  } else {
    const sign = sdSign(e.polarity);
    const what = sign === "+" ? `When ${nameOf(src)} rises, ${nameOf(dst)} rises above what it would otherwise have been (and falls below it when ${nameOf(src)} falls).`
      : sign === MINUS ? `When ${nameOf(src)} rises, ${nameOf(dst)} falls below what it would otherwise have been (and rises above it when ${nameOf(src)} falls).`
      : `${nameOf(dst)} depends on ${nameOf(src)}, but which way is not known` + ((e.rules || []).length ? `: what ${e.rules.join(", ")} does with it is its own.` : ": the model does not sign it.");
    showDetail(h("div", { class: "kind" }, "connector · system dynamics"), h("h2", {}, nameOf(src), " → ", nameOf(dst)), sdWhat("connector"),
      h("p", { class: "muted" }, what),
      h("h3", {}, "how it is now"),
      dl([["cause", link(src)], ["effect", link(dst)], ["polarity", sign ? `${sign} (${sign === "+" ? "same way" : "opposite way"})` : "not known"],
          ["decided by", (e.rules || []).length ? e.rules.join(" → ") : null]]),
      crossing.length ? h("p", {}, crossing.join("; ") + ".") : null, inLoops);
  }
  S.selKey = linkKey(e);
  trace(S.selKey);
}

/* a feedback loop: its polarity, its parts in order, and each link's sign */
function openCausal(name) {
  const c = (S.graph?.causalLoops || []).find((x) => x.name === name);
  if (!c) return;
  const { link, byId } = sdGraphLinks();
  const word = { R: "reinforcing", B: "balancing" }[c.polarity] || "polarity not known";
  const part = (p) => {
    const [k, nm] = [p.split(".")[0], p.split(".").slice(1).join(".")];
    const id = k === "flow" ? `flow:${nm}` : k === "stock" || k === "auxiliary" ? `stock:${nm}` : k === "goal" ? `gap:${nm}` : `decision:${nm}`;
    if (byId[id]) return link(id);
    return h("span", { class: "muted" }, k === "block" ? `rule ${nm}` : k === "goal" ? `goal ${nm}` : nm);
  };
  const unknown = (c.links || []).filter((x) => !x.polarity);
  const minus = (c.links || []).filter((x) => x.polarity === "-").length;
  showDetail(h("div", { class: "kind" }, `feedback loop · ${word}`), h("h2", {}, h("span", { class: `loop-tag pol-${c.polarity || "unknown"}` }, c.label), " ", c.name), sdWhat("loop"),
    h("p", {}, c.polarity ? `${minus} negative link${minus === 1 ? "" : "s"} around it: ${minus % 2 ? "an odd number, so it balances" : "an even number, so it reinforces"}.`
                          : `${unknown.length} link${unknown.length === 1 ? "" : "s"} along it ${unknown.length === 1 ? "has" : "have"} no known sign, so whether it reinforces or balances is not known.`),
    h("h3", {}, "around the loop"),
    h("table", { class: "parts" }, (c.links || []).map((x) => h("tr", {}, h("td", {}, part(x.source)), h("td", { class: "muted" }, "→"), h("td", {}, part(x.target)),
      h("td", { class: "num" }, sdSign(x.polarity) || "?")))),
    c.goals?.length ? h("p", { class: "muted" }, `It seeks the goal${c.goals.length > 1 ? "s" : ""} ${c.goals.join(", ")}.`) : null,
    (() => {                                            // the loops drawn alike here share its marker
      const grp = sdLoopGroups(S.graph).find((x) => x.loops.includes(c));
      const others = grp ? grp.loops.filter((x) => x !== c) : [];
      return others.length ? h("p", { class: "muted" }, "Drawn alike here (they differ only inside a closed system or outside this one): ",
        others.flatMap((x, i) => [i ? ", " : "", h("a", { href: "#", onclick: (ev) => { ev.preventDefault(); sdHighlight(x.name); openCausal(x.name); } }, `${x.label} ${x.name}`)])) : null;
    })());
}

/* the legend under a saved picture: the system dynamics symbols in rows, colours resolved (a var()
   would not survive the file) */
function sdExportLegend(width) {
  const css = (v) => getComputedStyle(document.body).getPropertyValue(v).trim();
  const resolve = (t) => t.replace(/var\((--[\w-]+)\)/g, (_, v) => css(v) || "#000");
  const g = s("g", { style: `font-size:11px;fill:${css("--sd-muted") || "#666"}` });
  let cx = 0, cy = 0;
  for (const [key, text] of sdExportItems()) {
    const need = 30 + text.length * 6.2;
    if (cx > 0 && cx + need > width) { cx = 0; cy += 22; }
    const ic = s("g", { transform: `translate(${cx},${cy - 12})` });
    ic.innerHTML = resolve(SD_LEGEND[key]);
    g.append(ic, s("text", { x: cx + 30, y: cy + 1 }, text));
    cx += need + 18;
  }
  return { g, h: cy + 22 };
}

/* after routing, in the system dynamics view: two connectors that are no net (not from one part or into
   one) never run along one another; where the router left them on one track, an inner stretch of one
   is moved beside it (orthogonal still: the stretches either side of it lengthen or shorten) */
function sdSeparate(lay, g) {
  const edge = Object.fromEntries(g.edges.map((e) => [e.id, e]));
  const lines = lay.edges.filter((le) => edge[le.id] && edge[le.id].kind !== "pipe" && (le.sections || []).length);
  const pts = (le) => { const sc = le.sections[0]; return [sc.startPoint, ...(sc.bendPoints || []), sc.endPoint]; };
  // an end stretch may move too, but for a short stub at its part: a point 10px out, twice (a jog, if it moves)
  for (const le of lines) {
    const sc = le.sections[0], bp = (sc.bendPoints ||= []);
    const stub = (from, to) => { const L = Math.hypot(to.x - from.x, to.y - from.y);
      return L > 30 ? { x: from.x + ((to.x - from.x) / L) * 10, y: from.y + ((to.y - from.y) / L) * 10 } : null; };
    const first = stub(sc.startPoint, bp[0] || sc.endPoint), last = stub(sc.endPoint, bp[bp.length - 1] || sc.startPoint);
    if (first) bp.unshift({ ...first }, { ...first });
    if (last) bp.push({ ...last }, { ...last });
  }
  const net = (a, b) => (a.sourcePort && a.sourcePort === b.sourcePort) || (a.targetPort && a.targetPort === b.targetPort) ||
    (a.source === b.source && !a.sourcePort && !b.sourcePort) || (a.target === b.target && !a.targetPort && !b.targetPort);   // (as the audit says)
  const along = (a, b, c, d) => {                       // how far two axis-parallel stretches run on one track
    if (Math.abs(a.y - b.y) < 1 && Math.abs(c.y - d.y) < 1 && Math.abs(a.y - c.y) < 3)
      return Math.min(Math.max(a.x, b.x), Math.max(c.x, d.x)) - Math.max(Math.min(a.x, b.x), Math.min(c.x, d.x));
    if (Math.abs(a.x - b.x) < 1 && Math.abs(c.x - d.x) < 1 && Math.abs(a.x - c.x) < 3)
      return Math.min(Math.max(a.y, b.y), Math.max(c.y, d.y)) - Math.max(Math.min(a.y, b.y), Math.min(c.y, d.y));
    return 0;
  };
  const kids = lay.children || [];
  // (across a line of its own net it may go: uncross trades their ways after, untangle.js)
  const clash = (le, a, b) => lines.some((o) => o !== le && !net(edge[o.id], edge[le.id]) &&
      pts(o).slice(1).some((q, j) => along(a, b, pts(o)[j], q) > 4)) ||
    kids.some((c) => c.id !== edge[le.id].source && c.id !== edge[le.id].target &&
      Math.max(a.x, b.x) > c.x && Math.min(a.x, b.x) < c.x + c.width && Math.max(a.y, b.y) > c.y && Math.min(a.y, b.y) < c.y + c.height);
  for (let pass = 0; pass < 3; pass++) {
    let moved = false;
    for (const le of lines) {
      const p = pts(le);
      for (let i = 1; i < p.length - 2; i++) {             // inner stretches only: the ends stay on their parts
        const a = p[i], b = p[i + 1];
        if (!lines.some((o) => o !== le && !net(edge[o.id], edge[le.id]) && pts(o).slice(1).some((q, j) => along(a, b, pts(o)[j], q) > 4))) continue;
        const vertical = Math.abs(a.x - b.x) < 1;
        for (const d of [6, -6, 12, -12, 18, -18, 24, -24, 32, -32, 44, -44, 60, -60, 80, -80]) {
          const a2 = vertical ? { x: a.x + d, y: a.y } : { x: a.x, y: a.y + d }, b2 = vertical ? { x: b.x + d, y: b.y } : { x: b.x, y: b.y + d };
          if (clash(le, a2, b2) || clash(le, p[i - 1], a2) || clash(le, b2, p[i + 2])) continue;
          Object.assign(a, a2); Object.assign(b, b2);
          moved = true;
          break;
        }
      }
    }
    if (!moved) break;
  }
  for (const le of lines) {                              // the stubs that did not move: taken out again
    const sc = le.sections[0], all = [sc.startPoint, ...sc.bendPoints, sc.endPoint];
    const keep = all.filter((p, i) => i === 0 || i === all.length - 1 || !(Math.abs(p.x - all[i - 1].x) < 0.5 && Math.abs(p.y - all[i - 1].y) < 0.5));
    const lean = keep.filter((p, i) => i === 0 || i === keep.length - 1 ||
      !((Math.abs(keep[i - 1].x - p.x) < 0.5 && Math.abs(p.x - keep[i + 1].x) < 0.5) || (Math.abs(keep[i - 1].y - p.y) < 0.5 && Math.abs(p.y - keep[i + 1].y) < 0.5)));
    sc.bendPoints = lean.slice(1, -1);
  }
}
