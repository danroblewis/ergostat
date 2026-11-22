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
  if (n.role === "desired") return n.valueText || "–";
  if (n.bare) return "";                                // (the Guide's frames: structure only, no readings)
  if (n.role === "gap") return n.valueText || "–";
  if (n.role === "decision") return "";
  const v = n.valueText && n.valueText !== "?" ? n.valueText : "–";
  return n.unit ? `${v} ${n.unit}` : v;
}
const sdNoUnit = (n) => n.kind === "stock" && !n.bare && !(n.unit || "").trim();   // check's no-unit: 'unit ?', muted
function sdSize(n) {
  if (n.kind === "stock") return [Math.max(96, textWidth(n.label) * 1.05 + 28, textWidth(sdValue(n) + (sdNoUnit(n) ? " unit ?" : "")) + 28), SD_STOCK_H];
  if (n.kind === "auxiliary") {                         // its name is the part: as wide as that, with its value under it
    const lines = sdAuxLines(n);
    return [Math.max(...lines.map((t) => textWidth(t) * (t === lines[0] ? 1.02 : 0.92))) + 10, 6 + lines.length * 14];
  }
  return SD_SIZE[n.kind] || [40, 40];
}
/* the lines written beside a part (under a valve or a converter): its name, then its value */
function sdLabelLines(n) {
  if (n.kind === "valve" || n.kind === "disturbance") return n.bare ? [n.label] : [n.label, n.rate == null ? "–" : n.rateText];
  if (n.kind === "cloud" && n.beyond) return [`<${n.beyond}>`];      // where the flow goes on to, beyond this system
  if (n.kind === "cloud" && n.from) return [`from ${n.from}`];        // an inflow from outside: where it comes from, where the model knows it
  return [];
}
function sdAuxLines(n) {
  if (n.role === "decision") return [n.label];
  return [n.label, sdValue(n), n.exogenous ? "(exogenous)" : null].filter(Boolean);
}
function sdLabel(ng, n, t, i, cx, y) {
  if (n.kind === "cloud") return ng.append(s("text", { x: cx, y, "text-anchor": "middle", class: "t-sub sd-shadow" }, t));
  if (i === 0) return ng.append(s("text", { x: cx, y, "text-anchor": "middle", class: "t-label sd-name" }, t));
  ng.append(s("text", { x: cx, y, "text-anchor": "middle", class: "t-sub sd-value live" }, t));
}

/* parts, drawn with their top-left at 0,0 */
function sdStock(n, w, hgt) {
  const g = s("g");
  // its name and its value now, small and muted; its history is in its panel (no gauge, no sparkline)
  g.append(s("rect", { class: "hit sd-stock", width: w, height: hgt, "stroke-dasharray": n.outside ? "5 4" : null }));
  const v = sdValue(n);
  g.append(s("text", { x: w / 2, y: v ? 19 : hgt / 2 + 4, "text-anchor": "middle", class: "t-label sd-name" }, n.label));
  if (v) g.append(s("text", { x: w / 2, y: 34, "text-anchor": "middle", class: "t-sub sd-value live" }, v,
    sdNoUnit(n) ? s("tspan", { class: "sd-nounit" }, " unit ?") : null));
  return g;
}
/* an auxiliary, unadorned as Vensim draws it: its name alone (its value under it, muted) */
function sdAux(n, w, hgt) {
  const g = s("g");
  g.append(s("rect", { class: "hit sd-aux", width: w, height: hgt, rx: 3 }));
  sdAuxLines(n).forEach((t, i) => g.append(s("text", { x: w / 2, y: 14 + i * 14, "text-anchor": "middle",
    class: i === 0 ? "t-label sd-name" : t === "(exogenous)" ? "t-sub sd-exo" : "t-sub sd-value" + (n.role === "desired" ? "" : " live") }, t)));
  return g;
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
function sdCloud(n, w, hgt) {                           // (a cloud a flow leaves the view by: the part beyond named under it)
  const d = `M${w * 0.22},${hgt * 0.82} C${w * 0.02},${hgt * 0.82} ${w * 0.02},${hgt * 0.42} ${w * 0.22},${hgt * 0.45}
             C${w * 0.22},${hgt * 0.12} ${w * 0.55},${hgt * 0.08} ${w * 0.6},${hgt * 0.32}
             C${w * 0.7},${hgt * 0.12} ${w * 0.95},${hgt * 0.22} ${w * 0.86},${hgt * 0.5}
             C${w * 1.02},${hgt * 0.56} ${w * 0.98},${hgt * 0.84} ${w * 0.8},${hgt * 0.82} Z`;
  return s("g", {}, s("path", { class: "hit sd-cloud", d }));
}
/* a system closed: a module (Stella) or a view (Vensim): its name, and its ports, what crosses its edge */
function sdSystem(n, w, hgt) {
  const g = s("g", n.remote ? { class: `sys-remote remote-${n.remote.state}` } : {});
  g.append(s("rect", { class: "hit sd-module", width: w, height: hgt, rx: 8, ...(n.remote ? { "stroke-dasharray": "9 5" } : {}) }));
  g.append(s("text", { x: 16, y: 24, class: "t-label sys-title" }, n.label));
  const inside = sdInside(S.graph, n.id).length;
  g.append(s("text", { x: 16, y: 42, class: "t-sub" + (n.remote ? " live" : "") }, n.remote ? n.remote.says   // run by another ergostat, read here
    : inside ? `${inside} feedback loop${inside > 1 ? "s" : ""} inside` : "a module: open it to see its structure"));
  const btn = (x, label, title, fn) => s("g", { class: "sys-btn", transform: `translate(${x},10)`, onclick: (ev) => { ev.stopPropagation(); fn(); } },
    s("rect", { width: textWidth(label) + 14, height: 20, rx: 4 }), s("text", { x: 7, y: 14 }, label));
  const into = "Into", open = "Open";
  g.append(btn(w - textWidth(into) - 24, into, "Draw this system alone, with what it reaches outside at its edge", () => S.drill?.(n.label)));
  g.append(btn(w - textWidth(into) - textWidth(open) - 46, open, "Open it here: its parts in place of the box", () => S.toggleSystem?.(n.label)));
  const at = { west: 0, east: 0 }, sg = S.graph || { nodes: [], edges: [] }, kept = sdFlowLinks(sg);
  // (Flows only hides a port none of whose lines it keeps)
  const flowing = new Set(sg.edges.filter((e) => kept.has(e.id)).flatMap((e) => [e.sourcePort, e.targetPort]));
  for (const p of n.ports || []) {
    const side = p.at || (p.side === "in" ? "west" : "east");
    const twin = sysTwin(n, p);
    const y = sysTop(n) + (at[side]++) * SYS_ROW;
    if (twin && p.side === "in") continue;               // (named once, on its twin's row: ⇄; its line meets the edge beside it)
    p.both = !!twin;
    const left = side === "west";
    // a named connection point (as Stella's module connectors): no square, the line meets the edge at its name
    const cls = "t-sub sd-port-name" + (flowing.has(p.id) || (twin && flowing.has(twin.id)) ? " flow-port" : "");
    g.append(s("text", { x: left ? 8 : w - 8, y: y + 4, class: cls, "text-anchor": left ? "start" : "end", "data-part": p.part, "data-side": side },
      p.both ? "⇄ " : "", p.label, p.value ? s("tspan", { class: "live", dx: 6, opacity: 0.75 }, p.value) : null));
  }
  return g;
}
/* a part drawn elsewhere: as Vensim's shadow variable, its name in angle brackets, an input only (nothing
   points into it); what this system drives outside it ends at a stub naming it */
function sdTerminal(n, w, hgt) {
  const g = s("g");
  g.append(s("rect", { class: "hit", width: w, height: hgt, rx: 4, fill: "transparent", stroke: "transparent" }));
  const stub = n.role === "stub";
  g.append(s("text", { x: stub ? 2 : w / 2, y: hgt / 2 + 4, "text-anchor": stub ? "start" : "middle", class: "t-sub sd-shadow" },
    stub ? n.label : `<${n.label}>`));
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

/* what a drawing's geometry alone decides (where each loop marker goes, each connector's curve), kept on its
   layout until the drawing moves (a new layout, its lines routed, a part dragged): the searches for them
   were most of a redraw's time, and the page redraws every few seconds with new values in the same places.
   Worked out once for each draw (S.drawN: diagram.js) */
function sdMemo(lay) {
  if (lay.memo && lay.memoDraw === S.drawN) return lay.memo;
  const geo = [lay.children.map((c) => `${c.id}:${c.x},${c.y},${c.width},${c.height}:${(c.labels || []).map((l) => `${l.x},${l.y},${l.width},${l.height}`).join(";")}`).join("|"),
               (lay.containers || []).map((h) => `${h.x},${h.y},${h.width},${h.height}`).join("|"),
               lay.edges.map((le) => `${le.id}:${edgePoints(le).map((q) => `${q.x},${q.y}`).join(" ")}`).join("|")].join("#");
  if (!lay.memo || lay.memo.geo !== geo) lay.memo = { geo, spots: {}, curves: {} };
  lay.memoDraw = S.drawN;
  return lay.memo;
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
  const memo = sdMemo(lay), ck = `${e.source}>${e.target}:${pts.map((q) => `${q.x},${q.y}`).join(" ")}`;
  const c = memo.curves[ck] ||= sdCurve(pts, sdBlocked(lay, e));
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

/* each feedback loop's marker, as Sterman draws them: its polarity and number (R1, B2) in a circular arrow
   turning the way the loop runs, its name under it, placed inside the loop as drawn: as near the
   centroid of the polygon its lines make as is inside that polygon and clear of every part, label, pipe
   and other marker. Only loops whose polarity is known are marked: the others are listed beside the
   diagram (one entry, "+N of unknown polarity"), never drawn */
function sdLoopMarkers(g, lay) {
  const box = Object.fromEntries(lay.children.map((c) => [c.id, c]));
  const taken = [];
  for (const c of lay.children) {
    const xs = [c.x, c.x + c.width], ys = [c.y, c.y + c.height];
    for (const l of c.labels || []) { xs.push(c.x + l.x, c.x + l.x + l.width); ys.push(c.y + l.y, c.y + l.y + l.height); }
    taken.push({ x: Math.min(...xs), y: Math.min(...ys), x1: Math.max(...xs), y1: Math.max(...ys) });
  }
  for (const h of lay.containers || []) taken.push({ x: h.x, y: h.y, x1: h.x + h.width, y1: h.y + 32 });   // an outline's handle
  const pipes = new Set(g.edges.filter((e) => e.kind === "pipe").map((e) => e.id)), lines = [], pipeLines = [];
  for (const le of lay.edges) {                         // and off the lines: a marker on a line reads as part of it
    const p = edgePoints(le);
    for (let i = 1; i < p.length; i++) (pipes.has(le.id) ? pipeLines : lines).push({ x: Math.min(p[i - 1].x, p[i].x) - 4, y: Math.min(p[i - 1].y, p[i].y) - 4,
                                                    x1: Math.max(p[i - 1].x, p[i].x) + 4, y1: Math.max(p[i - 1].y, p[i].y) + 4 });
  }
  const hit = (xs, r) => xs.some((t) => r.x < t.x1 + 3 && t.x < r.x1 + 3 && r.y < t.y1 + 3 && t.y < r.y1 + 3);
  // clear of everything; else (still inside its loop) across a connector; else across a pipe (its ground hides
  // the line under it); never on a part, a label or another marker
  const free = (r, tier) => !hit(taken, r) && (tier >= 1 || !hit(lines, r)) && (tier >= 2 || !hit(pipeLines, r));
  const out = s("g", { class: "loop-markers" });
  const placed = {};
  const memo = sdMemo(lay);
  for (const { rep, loops } of sdLoopGroups(g, box)) {
    const { poly, members } = sdPolygon(rep, g, box);
    if (poly.length < 2) continue;
    const cx = poly.reduce((a, p) => a + p.x, 0) / poly.length, cy = poly.reduce((a, p) => a + p.y, 0) / poly.length;
    let area = 0;                                        // which way it runs, on the screen (y down: > 0 is clockwise)
    for (let i = 0; i < poly.length; i++) { const p = poly[i], q2 = poly[(i + 1) % poly.length]; area += p.x * q2.y - q2.x * p.y; }
    const label = rep.label || rep.polarity;
    const r = sdMarkerRadius(label), lines = sdNameLines(rep.name);
    const more = loops.length > 1 ? 22 : 0;
    const w = Math.max(2 * r + 8 + more, ...lines.map((t) => textWidth(t) * 0.92 + 6)), hgt = 2 * r + 6 + lines.length * 13;
    const rect = (x, y) => ({ x: x - w / 2, y: y - r - 3, x1: x + w / 2, y1: y - r - 3 + hgt });
    const inside = poly.length >= 3 && Math.abs(area) > 400 ? (x, y) => sdInPolygon(x, y, poly) : () => true;
    const reach = Math.max(80, ...poly.map((p) => Math.hypot(p.x - cx, p.y - cy)));
    const mk = `${loops.map((c) => c.name).join("|")}#${label}#${lines.join("/")}#${poly.map((q) => `${q.x},${q.y}`).join(" ")}`;
    let spot = memo.spots[mk] || null;
    const ring = (x, y) => ({ x: x - r - 4, y: y - r - 4, x1: x + r + 4, y1: y + r + 4 });
    for (const tier of spot ? [] : [0, 1, 2, 3, 5, 4]) {            // inside and clear; across a connector; across a pipe; its circle alone
                                                                      // clear; inside at all (a loop's marker is in it); near it
      for (let rr = 0; rr <= reach && !spot; rr += 8) {
        const k = Math.max(1, Math.round((2 * Math.PI * rr) / 14));
        for (let i = 0; i < k; i++) {
          const ang = (i / k) * 2 * Math.PI, x = cx + rr * Math.cos(ang), y = cy + rr * Math.sin(ang);
          const ok = tier === 5 || (tier === 4 ? free(rect(x, y), 0) : tier === 3 ? !hit(taken, ring(x, y)) : free(rect(x, y), tier));
          if ((tier === 4 || inside(x, y)) && ok) { spot = { x, y }; break; }
        }
      }
      if (spot) break;
    }
    spot ||= { x: cx, y: cy };
    memo.spots[mk] = spot;
    taken.push(rect(spot.x, spot.y));
    for (const c of loops) placed[c.name] = spot;
    const m = sdMarker(rep, spot.x, spot.y, area >= 0, lines, loops);
    m.dataset.members = JSON.stringify(members);
    out.append(m);
  }
  lay.markers = placed;
  return out;
}
function sdMarkerRadius(label) { return Math.max(12, label.length * 3.7 + 4.5); }     // the label at its own size, the circle around it
function sdNameLines(name) {                            // a loop's name under its marker: two lines at most, at full size
  const words = name.split(" "), lines = [""];
  for (const wd of words) {
    const cur = lines[lines.length - 1];
    if (cur && (cur + " " + wd).length > 24) lines.push(wd); else lines[lines.length - 1] = cur ? cur + " " + wd : wd;
  }
  if (lines.length > 2) lines.splice(1, lines.length - 1, lines.slice(1).join(" ").slice(0, 22) + "…");
  return lines;
}
/* a loop as drawn: the corners of the lines that make it (the drawn ends of each of its links, a shadow
   where a link comes in from elsewhere), and the parts they are */
function sdPolygon(c, g, box) {
  const ns = c.nodes, poly = [], members = [];
  const centre = (id) => (box[id] ? { x: box[id].x + box[id].width / 2, y: box[id].y + box[id].height / 2 } : null);
  const add = (id) => { const p = centre(id); if (p && members[members.length - 1] !== id) { poly.push(p); members.push(id); } };
  for (let i = 0; i < ns.length; i++) {
    const a = ns[i], b = ns[(i + 1) % ns.length];
    const e = g.edges.find((x) => (x.from ?? x.source) === a && (x.to ?? x.target) === b) ||
              g.edges.find((x) => x.kind === "pipe" && (x.from ?? x.source) === b && (x.to ?? x.target) === a);
    if (e && box[e.source] && box[e.target]) {
      const [s0, t0] = (e.from ?? e.source) === a ? [e.source, e.target] : [e.target, e.source];
      add(s0); add(t0);
    } else add(a);
  }
  if (members.length > 1 && members[0] === members[members.length - 1]) { poly.pop(); members.pop(); }
  return { poly, members };
}
function sdInPolygon(x, y, poly) {
  let inside = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const a = poly[i], b = poly[j];
    if ((a.y > y) !== (b.y > y) && x < ((b.x - a.x) * (y - a.y)) / (b.y - a.y) + a.x) inside = !inside;
  }
  return inside;
}
/* while parts are dragged: each marker moves by how far its loop's parts moved, on average; one inside an
   open system dragged by its name goes with it whole (on drop the markers are placed again, from where the
   parts are) */
function sdMarkersFollow(svg, ids, dx, dy, system) {
  const moved = new Set(ids);
  const hull = system && (S.layout?.containers || []).find((o) => o.name === system);
  for (const m of svg.querySelectorAll(".loop-marker")) {
    const x = +m.dataset.x, y = +m.dataset.y;
    const mine = JSON.parse(m.dataset.members || "[]");
    const share = hull && x > hull.x && x < hull.x + hull.width && y > hull.y && y < hull.y + hull.height ? 1
      : mine.length ? mine.filter((id) => moved.has(id)).length / mine.length : 0;
    if (share) m.setAttribute("transform", `translate(${x + dx * share},${y + dy * share})`);
  }
}
/* a loop's parts drawn here as themselves (not folded into a closed system, nor outside it) */
function sdVisible(c, g, box) {
  const kind = Object.fromEntries(g.nodes.map((n) => [n.id, n.kind]));
  return [...new Set(c.nodes.filter((id) => (box ? box[id] : kind[id]) && !["system", "terminal"].includes(kind[id])))];
}
/* the loops inside a closed system: through it, with fewer than two parts drawn here */
function sdInside(g, id) {
  return (g?.causalLoops || []).filter((c) => c.nodes.includes(id) && sdVisible(c, g).length < 2);
}
/* the loops that show here (two of their parts drawn as themselves), one marker for those drawn alike
   (the same parts here: they differ only where they run inside a closed system or outside this one),
   the shortest first; of known polarity only, unless `all` */
function sdLoopGroups(g, box = null, all = false) {
  const groups = new Map();
  for (const c of g.causalLoops || []) {
    if (!c.polarity && !all) continue;
    const v = sdVisible(c, g, box);
    if (v.length < 2) continue;
    const key = (c.polarity || "?") + v.slice().sort().join("|");
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(c);
  }
  const rank = (c) => [c.nodes.length, c.name];
  return [...groups.values()].map((loops) => {
    loops.sort((a, b) => { const x = rank(a), y = rank(b); return x[0] - y[0] || (x[1] > y[1]) - (x[1] < y[1]); });
    return { rep: loops[0], loops };
  });
}
function sdMarker(c, x, y, clockwise, lines, loops = [c]) {
  const label = c.label || (c.polarity || "?");
  const r = sdMarkerRadius(label), start = clockwise ? -60 : -120, end = clockwise ? 240 : -60;   // a gap at the top, the head at its end
  const P = (deg) => [r * Math.cos((deg * Math.PI) / 180), r * Math.sin((deg * Math.PI) / 180)];
  const [x0, y0] = P(start), [x1, y1] = P(end), rad = (end * Math.PI) / 180;
  const dx = clockwise ? -Math.sin(rad) : Math.sin(rad), dy = clockwise ? Math.cos(rad) : -Math.cos(rad);   // the way it turns, at the end
  const tip = [x1 + dx * 6, y1 + dy * 6], base = [x1 - dx * 2, y1 - dy * 2], px = -dy * 5, py = dx * 5;   // a clear arrowhead
  const g = s("g", { class: `loop-marker pol-${c.polarity || "unknown"}`, "data-loop": c.name, "data-loops": loops.map((x2) => x2.name).join("|"),
                     "data-act": "loop", "data-x": x, "data-y": y, transform: `translate(${x},${y})`,
                     onclick: (ev) => { ev.stopPropagation(); sdToggle(c.name, loops); },
                     onpointerenter: () => { if (!S.dragging) sdHover(c.name); }, onpointerleave: () => sdHover(null) },
    s("circle", { class: "marker-hit", r: r + 4 }),
    s("path", { class: "marker-arc", d: `M${x0},${y0} A${r},${r} 0 1 ${clockwise ? 1 : 0} ${x1},${y1}` }),
    s("path", { class: "marker-head", d: `M${tip[0]},${tip[1]} L${base[0] + px},${base[1] + py} L${base[0] - px},${base[1] - py} Z` }),
    s("text", { class: "marker-letter", y: 4, "text-anchor": "middle" }, label),
    loops.length > 1 ? s("text", { class: "marker-more", x: r + 4, y: 4, "text-anchor": "start" }, `+${loops.length - 1}`) : null,
    ...lines.map((t, i) => s("text", { class: "marker-name", y: r + 14 + i * 13, "text-anchor": "middle" }, t)));
  return g;
}

/* a loop pointed at or chosen: its parts and its links lit, the rest faded */
function sdHover(name) { sdApply(name || S.hlCausal); }
function sdHighlight(name) { S.hlCausal = name || null; sdApply(name); }
/* a loop's marker (or its row) clicked: the loop lit and its panel open; clicked again, both let go (as the
   background, Escape and the panel's close do: closeDetail) */
function sdToggle(name, loops = []) {
  if (S.hlCausal && (S.hlCausal === name || loops.some((x) => x.name === S.hlCausal))) { closeDetail(); choose([]); return; }
  sdHighlight(name); choose(S.graph?.corr?.loops?.[name] || []); openCausal(name);     // its members chosen, in both views
}
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
    const mine = !!name && (m.dataset.loops || "").split("|").includes(name);
    m.classList.toggle("on", mine); m.classList.toggle("dim", !!c && !mine);
  }
  for (const r of document.querySelectorAll(".looprow")) r.classList.toggle("hl", r.dataset.loop === name);
}

/* ------------------------------------------------------------------ the side panel, the legend */

function sdLoopList(side, g) {
  const order = { R: 0, B: 1 };
  const num = (c) => parseInt(c.label.slice(1)) || 0;
  const sort = (xs) => xs.sort((a, b) => (order[a.polarity] ?? 2) - (order[b.polarity] ?? 2) || num(a) - num(b));
  const known = sort(sdLoopGroups(g).flatMap((x) => x.loops));
  const unknown = sort(sdLoopGroups(g, null, true).flatMap((x) => x.loops).filter((c) => !c.polarity));
  const modules = g.nodes.filter((n) => n.kind === "system").map((n) => [n, sdInside(g, n.id)]).filter(([, xs]) => xs.length);
  const every = new Set([...known, ...unknown, ...modules.flatMap(([, xs]) => xs)].map((c) => c.name));   // (one loop may run through two modules)
  side.append(h("h3", {}, "Feedback loops", h("span", { class: "muted" }, ` ${every.size}`)));
  const row = (c) => h("div", { class: "looprow", "data-loop": c.name, onmouseenter: () => sdHover(c.name), onmouseleave: () => sdHover(null),
                                onclick: () => sdToggle(c.name) },
    h("div", {}, h("span", { class: `loop-tag pol-${c.polarity || "unknown"}` }, c.label), h("span", {}, c.name)),
    h("div", { class: "sub" }, `${{ R: "Reinforcing", B: "Balancing" }[c.polarity] || "Polarity not known"}, ${new Set(c.nodes).size} parts`));
  if (!known.length && !unknown.length && !modules.length) side.append(h("div", { class: "muted" }, "No feedback loops drawn here."));
  const counts = ["R", "B"].map((p) => [p, known.filter((c) => c.polarity === p).length]).filter(([, n]) => n);
  if (counts.length) side.append(h("div", { class: "note" }, counts.map(([p, n], i) => `${n} ${{ R: i ? "reinforcing" : "Reinforcing", B: i ? "balancing" : "Balancing" }[p]}`).join(", ")));
  for (const c of known) side.append(row(c));
  if (unknown.length) {                                 // not on the canvas: a sign along each is not known
    const d = h("details", { class: "sd-unknown" }, h("summary", {}, `+${unknown.length} of unknown polarity`),
      h("div", { class: "note" }, "A link along each has no sign, so they are not marked on the diagram. ergostat check names them."));
    for (const c of unknown) d.append(row(c));
    side.append(d);
  }
  for (const [n, xs] of modules)                        // as many as the module's own caption says
    side.append(h("div", { class: "looprow sd-inside", onclick: () => S.toggleSystem?.(n.label) },
      h("div", {}, h("b", {}, n.label), `: ${xs.length} feedback loop${xs.length > 1 ? "s" : ""} inside`),
      h("div", { class: "sub" }, "Open it to see them")));
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
  module: '<rect x="2" y="2" width="22" height="14" rx="3" fill="var(--sd-paper)" stroke="var(--sd-ink)" stroke-width="1.3"/>',
  sector: '<rect x="1" y="1" width="24" height="16" rx="3" fill="var(--sd-hull)"/><text x="3" y="7" font-size="5" fill="var(--sd-muted)">NAME</text>',
  stub: '<path d="M1 9 H17" stroke="var(--sd-ink)" stroke-width="1.1"/><path d="M20 9 L14 6 L14 12 Z" fill="var(--sd-ink)"/><text x="21" y="12" font-size="8" fill="var(--sd-muted)">x</text>',
  shadow: '<text x="13" y="13" font-size="10" text-anchor="middle" fill="var(--sd-muted)">&lt;x&gt;</text>',
  nounit: '<text x="13" y="13" font-size="8" text-anchor="middle" fill="var(--sd-muted)">unit ?</text>',
};
function sdLegend() {
  const g = S.graph || { nodes: [], edges: [] };
  const has = (f) => g.nodes.some(f);
  const row = (key, text) => [h("span", { html: `<svg width="26" height="18">${SD_LEGEND[key]}</svg>` }), h("span", {}, text)];
  const pols = new Set((g.causalLoops || []).map((c) => c.polarity || "?"));
  return h("div", { class: "legend sd-legend" },
    row("stock", "stock (level): what accumulates; it changes only by its flows"),
    has(sdNoUnit) && row("nounit", "unit ?: the stock's value has no unit; the model says none (ergostat check: no-unit)"),
    row("flow", "flow (rate): a pipe with its valve, into or out of a stock; the head shows which way"),
    g.edges.some((e) => e.twoWay) && row("biflow", "biflow: a flow that may run either way"),
    has((n) => n.kind === "cloud") && row("cloud", "source or sink: outside the model's boundary"),
    has((n) => n.kind === "auxiliary") && row("aux", "auxiliary: a name alone, worked out at each moment from what points into it (no memory)"),
    has((n) => n.exogenous) && row("exo", "exogenous input: from outside the model, nothing in it drives it (marked under its name)"),
    has((n) => n.role === "desired") && row("aux", "desired level: the level wanted (desired backlog = 0)"),
    has((n) => n.role === "gap" && n.excess) && row("aux", "excess: actual − desired, for a level kept down; it drives the flow that brings it down (+)"),
    has((n) => n.role === "gap" && !n.excess) && row("aux", "gap: desired − actual, for a level kept up or held; it drives the flow that closes it"),
    has((n) => n.role === "decision") && row("aux", "decision: what it reads, joined to the flows it sets"),
    row("plus", "connector, +: the cause rises, the effect rises above what it would have been"),
    row("minus", "connector, −: the cause rises, the effect falls below what it would have been"),
    g.edges.some((e) => e.kind === "connector" && !e.polarity) && row("plain", "connector, no sign: the polarity is not known"),
    pols.has("R") && row("loopR", "reinforcing loop: a change comes back amplified"),
    pols.has("B") && row("loopB", "balancing loop: a change comes back opposed (it seeks a desired level)"),
    has((n) => n.kind === "system") && row("module", "module: a system closed; its connection points are what crosses its edge (Open draws its parts in place; Into draws it alone)"),
    (g.open || []).length > 0 && g.nodes.some((n) => (n.systems || []).length) && row("sector", "sector: a system open, its parts on a tinted ground, its name at the top left (drag it by its name)"),
    has((n) => n.kind === "terminal" && n.role !== "stub") && row("shadow", "shadow variable: a part drawn elsewhere, an input here (click to go there)"),
    has((n) => n.role === "stub") && row("stub", "a connector out of this system: it ends at the name of what it drives"),
    has((n) => n.kind === "cloud" && n.beyond) && row("cloud", "cloud named <x>: the flow goes on to x, outside this system"),
    has((n) => n.kind === "cloud" && n.from) && row("cloud", "cloud named from x: an inflow from outside the model, coming from x (the outside system its sensor reads, or what drives it)"));
}
/* the lines Flows only keeps, by the model: the pipes, and each link across a system's edge (at a port, a shadow or
   a stub) whose tail is a flow (its rate crosses); a link from a stock or an auxiliary carries information only */
const SD_FLOW_LINKS = new WeakMap();                      // (once a graph: each poll brings a new one)
function sdFlowLinks(g) {
  if (SD_FLOW_LINKS.has(g)) return SD_FLOW_LINKS.get(g);
  const byId = Object.fromEntries(g.nodes.map((n) => [n.id, n])), flowy = (k) => k === "valve" || k === "disturbance";
  const out = new Set(g.edges.filter((e) => {
    const src = byId[e.source], dst = byId[e.target];
    const tail = e.sourcePort ? (src?.ports || []).find((p) => p.id === e.sourcePort)?.kind : src?.role === "shadow" ? src.of : src?.kind;
    return e.kind === "pipe" || ((e.sourcePort || e.targetPort || src?.kind === "terminal" || dst?.kind === "terminal") && flowy(tail));
  }).map((e) => e.id));
  SD_FLOW_LINKS.set(g, out);
  return out;
}
/* the same, in one row under a saved picture */
function sdExportItems() {
  const g = S.graph || { nodes: [], edges: [] };
  if (document.body.classList.contains("flows-only")) {      // only what it shows: no auxiliary, no loop, no information link
    const kept = g.edges.filter((e) => sdFlowLinks(g).has(e.id)), has = (k) => g.nodes.some((n) => n.kind === k);
    return [has("stock") && ["stock", "stock"], kept.some((e) => e.kind === "pipe") && ["flow", "flow"], kept.some((e) => e.twoWay) && ["biflow", "biflow"],
            has("cloud") && ["cloud", "source / sink"], kept.some((e) => e.kind !== "pipe" && e.polarity === "+") && ["plus", "connector +"],
            kept.some((e) => e.kind !== "pipe" && e.polarity === "-") && ["minus", "connector −"]].filter(Boolean);
  }
  return [["stock", "stock"], ["flow", "flow"], g.edges.some((e) => e.twoWay) && ["biflow", "biflow"], ["cloud", "source / sink"],
          ["aux", "auxiliary"], g.nodes.some((n) => n.exogenous) && ["exo", "exogenous"], ["plus", "connector +"], ["minus", "connector −"],
          ["loopR", "reinforcing"], ["loopB", "balancing"]].filter(Boolean);
}

/* ------------------------------------------------------------------ panels */

/* a flow of a stock, whose rate-unit: its inflow or outflow total is shown in (S.status.rate_units: a stock's own
   rate-unit: is given to each of its flows that sets none) */
function sdStockFlow(stock, way) {
  const ends = (S.graph?.edges || []).filter((e) => e.kind === "pipe" && (way === "in" ? e.target === `stock:${stock}` : e.source === `stock:${stock}`));
  return ends.map((e) => e.flow).find((f) => rateOver(f)) || null;
}
const SD_WHAT = {
  stock: ["Stock", "a level: what accumulates. It changes only by its flows, filling by its inflows and draining by its outflows, and keeps its value when they stop."],
  auxiliary: ["Auxiliary", "a converter: worked out at each moment from the parts that point into it, with no memory of its own: by its equation where the model writes one, else measured."],
  exogenous: ["Exogenous input", "an auxiliary from outside the model's boundary: nothing in the model drives it, and it drives what it points into."],
  desired: ["Desired level", "the level wanted, compared with the actual one in the gap (or the excess). The flow it drives pulls the actual level toward it: a balancing loop."],
  gap: ["Gap", "the discrepancy: the desired level less the actual one. It drives the flow that closes it, so the level is pulled toward the desired one: a balancing loop."],
  excess: ["Excess", "the discrepancy for a level kept down: the actual level less the desired one. It drives the flow that brings it down (+), so the level is pulled back to the desired one: a balancing loop."],
  decision: ["Decision", "what it reads (the connectors into it) decides the flows it sets (the connectors out of it). A link into it is signed where the model says which way it acts."],
  flow: ["Valve", "where a flow's rate is set: how much moves along its pipe in a time (shown per minute, hour or day, whichever reads best; kept per hour). The connectors into it are its inputs, what the rate depends on; its equation says how. A connector acts at once, so a cause that acts over time reaches a valve through a stock."],
  pipe: ["Flow", "what moves, along its pipe, from the stock it drains to the stock it fills (or a cloud: outside the model's boundary). Only flows change stocks; its valve sets how fast."],
  connector: ["Connector", "an information link: the cause at its tail changes the effect at its head. Nothing moves along it. Its sign is its polarity: + when the effect moves the same way as the cause, − when the opposite way."],
  loop: ["Feedback loop", "a closed chain of cause and effect. Reinforcing (R): the product of its signs is +, so a change comes back amplified (growth or collapse). Balancing (B): the product is −, so a change comes back opposed (it seeks a desired level). ?: a sign along it is not known, so it is listed beside the diagram and not marked on it."],
  system: ["Module", "a system drawn closed, as Stella draws a module: its connection points are what crosses its edge. Open it to see its stocks, flows and loops."],
  shadow: ["Shadow variable", "a part drawn elsewhere (in another system, or outside this one), shown here where it is an input. Nothing here points into it."],
  stub: ["Connector out", "what this part drives outside the system drawn here: the connector ends at its name."],
};
function sdWhat(kind) {
  const w = SD_WHAT[kind];
  return w ? h("details", { class: "what" }, h("summary", {}, `What is ${/^[AEIOU]/.test(w[0]) ? "an" : "a"} ${w[0].toLowerCase()}?`), h("p", {}, w[1][0].toUpperCase() + w[1].slice(1))) : null;
}
function sdNodeKind(n) {
  if (n.kind === "valve" || n.kind === "disturbance") return "flow";
  if (n.kind === "auxiliary") return n.role === "gap" && n.excess ? "excess" : n.role || (n.exogenous ? "exogenous" : "auxiliary");
  if (n.kind === "terminal") return n.role === "stub" ? "stub" : "shadow";
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
  if (!list.length) return h("p", { class: "muted" }, "In no feedback loop drawn here.");
  const shown = list.slice(0, 12);
  return h("p", {}, `In ${list.length} feedback loop${list.length > 1 ? "s" : ""}: `, shown.flatMap((x, i) => [i ? ", " : "", x]), list.length > 12 ? ` and ${list.length - 12} more` : "");
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
  let chart = null, numbers = null, found = null, items = null, counts = [];
  if (n.role === "desired" || n.role === "gap" || n.role === "decision") {
    rows.push(["desired level", n.goal ? `desired ${n.of} = ${n.desired ?? n.valueText}` : null],
              [n.excess ? "excess" : "gap", n.role === "gap" ? `${n.excess ? `${n.of} − desired ${n.of}` : `desired ${n.of} − ${n.of}`}, now ${n.valueText || "not known yet"}` : null],
              ["switching", n.switching || null],
              ["description", n.description]);
  } else if (n.kind === "valve" || n.kind === "disturbance") {        // the valve: the rate, its inputs and its equation
    let d = null;
    try { d = await api(`part/${n.kind === "disturbance" ? "disturbance" : "flow"}/${encodeURIComponent(n.flow || n.label)}`); } catch (err) { d = null; }
    const m = d?.model || {}, now = d?.now || {};
    rows.push(["rate, over the window", now.rate != null ? rateText(now.rate, d?.unit, n.flow || n.label) : n.rateText],
              ["how it is known", now.how || n.how],
              ["inputs", join(causes) || h("span", { class: "muted" }, "none drawn: nothing in the model points into it")],
              ["equation", d?.numbers?.equation_tree ? null : n.equation || d?.equation || "not known"]);
    if (d?.inferred) rows.push(inferredRow(d.inferred));
    const flow = n.flow || n.label;
    showDetail(h("div", { class: "kind" }, "Valve"), h("h2", {}, flow), ...countsLines(d), h("p", { class: "muted" }, `the rate of ${flow}`),
      causesStrip(`flow.${flow}`), !m.source && !d?.numbers?.equation_tree ? inputWhatif(flow) : null, dl(rows), findingsNote(d), itemsSection(d?.items), equationSection(flow, d?.numbers, { said: d?.equation || n.equation }), loopsPara(loopsOf((c) => c.nodes.includes(n.id))),
      h("p", {}, h("a", { href: `/diagram?view=dynamics&around=flow/${encodeURIComponent(flow)}` }, "Draw what is around it")),
      sdWhat("flow"));
    return;
  } else {
    let d = null;
    try { d = await api(`part/stock/${encodeURIComponent(n.label)}`); } catch (err) { d = null; }
    const m = d?.model || {}, now = d?.now || {};
    rows.push(["description", m.description || n.description], ...(d?.inferred ? [inferredRow(d.inferred)] : []),
              ["now", `${fmt(now.value ?? n.value)} ${m.unit || n.unit || ""}`],
              ["measured", now.at ? ago(now.at) : null]);
    if (n.kind === "stock") rows.push(["inflow", now.inflow != null ? rateText(now.inflow, "", sdStockFlow(n.label, "in")) : null],
                                      ["outflow", now.outflow != null ? rateText(now.outflow, "", sdStockFlow(n.label, "out")) : null]);
    for (const gl of n.goals || []) rows.push(["desired level", `desired ${n.label} = ${gl.desired ?? gl.setpoint}${gl.acted ? "" : " (nothing in the model acts on its gap: no feedback closes it)"}`]);
    if (n.kind === "auxiliary") numbers = equationSection(n.label, d?.numbers, { exogenous: n.exogenous });
    found = findingsNote(d);
    counts = countsLines(d);                              // what it counts, first (itemsets.js)
    items = itemsSection(d?.items);                       // what is in it (itemsets.js)
  }
  const ref = partRef(n);                                // behaviour over time first: it, and what drives it (charts.js)
  if (ref) chart = causesStrip(ref);
  rows.push(["depends on", join(causes)], ["drives", join(effects)]);
  const id = n.id;
  if (n.kind === "terminal") rows.unshift(["drawn in", n.in || "the model"]);
  showDetail(h("div", { class: "kind" }, (SD_WHAT[kind] || [kind])[0]), h("h2", {}, n.label), ...counts,
    chart, dl(rows), found, items, numbers,
    loopsPara(loopsOf((c) => c.nodes.includes(id))),
    n.kind === "stock" || n.kind === "valve" || n.kind === "disturbance" || (n.kind === "auxiliary" && !n.role)
      ? h("p", {}, h("a", { href: `/diagram?view=dynamics&around=${n.kind === "stock" || n.kind === "auxiliary" ? "stock" : "flow"}/${encodeURIComponent(n.flow || n.label)}` }, "Draw what is around it")) : null,
    sdWhat(kind));
  void byId;
}

/* a system's stocks that are candidates to aggregate into one delay, over the window (aggregation.py, from the loop
   dominance the page asks for anyway): an `aggregate` row for each group, none when there is none or no answer */
function sdAggregate(system) {
  const box = h("div", { class: "aggregate" });
  api("dominance", { points: CHART_POINTS }).then((d) => {
    const mine = (d?.aggregate || []).filter((g) => g.system === system);
    if (mine.length) box.replaceChildren(dl(mine.map((g) => ["aggregate", g.said])));
  }).catch(() => {});
  return box;
}

function sdOpenSystem(n) {
  const side = (d) => (n.ports || []).filter((p) => p.side === d);
  const list = (ps, none) => ps.length ? h("table", {}, ps.map((p) => h("tr", {}, h("td", {}, p.label), h("td", { class: "muted" }, sdKindWord(p.kind)),
    h("td", { class: "num" }, p.value || "")))) : h("p", { class: "muted" }, none);
  const inside = (S.graph?.causalLoops || []).filter((c) => c.nodes.includes(n.id) && sdVisible(c, S.graph).length < 2);
  showDetail(h("div", { class: "kind" }, n.remote ? "Module, remote" : "Module"), h("h2", {}, n.label),
    moduleCharts(n),
    n.description ? h("p", { class: "muted" }, n.description) : null,
    remoteNote(n.remote), remoteMeasures(n), n.size ? dl([["size", n.size]]) : null, sdAggregate(n.label),
    h("h3", {}, "In, from outside"), list(side("in"), "Nothing outside reaches in here."),
    h("h3", {}, "Out, to outside"), list(side("out"), "Nothing outside depends on it here."),
    inside.length ? h("p", {}, `${inside.length} feedback loop${inside.length > 1 ? "s" : ""} inside it or through it, not drawn here: open it to see them`) : null,
    loopsPara(loopsOf((c) => c.nodes.includes(n.id) && !inside.includes(c))),
    h("div", { class: "actions" }, h("button", { onclick: () => S.toggleSystem?.(n.label) }, "Open it here"),
               h("button", { onclick: () => S.drill?.(n.label) }, "Draw it alone")),
    sdWhat("system"));
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
    const unit = d?.unit || m.unit || "";
    showDetail(h("div", { class: "kind" }, "Flow"),
      h("h2", {}, e.flow, h("span", { class: "muted" }, ` ${m.source || "outside"} \u2192 ${m.target || "outside"}`)),   // (the pipe, not its valve: they share a name)
      causesStrip(`flow.${e.flow}`),
      dl([["what moves", [unit, m.description].filter(Boolean).join(": ") || "not said (no unit or description)"],
          ["from", m.source ? link(`stock:${m.source}`) : "a source outside the model"], ["to", m.target ? link(`stock:${m.target}`) : "a sink outside the model"],
          ["its valve", valve ? link(valve.id) : e.flow], ["rate, over the window", now.rate != null ? rateText(now.rate, d?.unit, e.flow) : valve?.rateText],
          ["runs", (m.two_way ?? e.twoWay) ? "either way (a biflow)" : "one way"]]),
      crossing.length ? h("p", {}, crossing.join("; ") + ".") : null, inLoops, sdWhat("pipe"));
  } else {
    const sign = sdSign(e.polarity);
    const what = sign === "+" ? `When ${nameOf(src)} rises, ${nameOf(dst)} rises above what it would otherwise have been (and falls below it when ${nameOf(src)} falls).`
      : sign === MINUS ? `When ${nameOf(src)} rises, ${nameOf(dst)} falls below what it would otherwise have been (and rises above it when ${nameOf(src)} falls).`
      : `${nameOf(dst)} depends on ${nameOf(src)}, but which way is not known: the model does not sign it (ergostat check names it).`;
    showDetail(h("div", { class: "kind" }, "Connector"), h("h2", {}, nameOf(src), " \u2192 ", nameOf(dst)),
      h("p", { class: "muted" }, what),
      dl([["cause", link(src)], ["effect", link(dst)], ["polarity", sign ? `${sign} (${sign === "+" ? "same way" : "opposite way"})` : "not known"],
          ["through the decision of", (e.rules || []).length ? e.rules.join(" → ") : null]]),
      crossing.length ? h("p", {}, crossing.join("; ") + ".") : null, inLoops, sdWhat("connector"));
  }
  S.selKey = linkKey(e);
  trace(S.selKey);
}

/* a feedback loop: its label and name, its polarity, its parts in order as drawn here, and the sign of each
   line between them as drawn (a module where it runs inside a closed system, a shadow where it leaves) */
function openCausal(name) {
  const c = (S.graph?.causalLoops || []).find((x) => x.name === name);
  if (!c) return;
  const { link, byId } = sdGraphLinks();
  const word = { R: "reinforcing", B: "balancing" }[c.polarity] || "polarity not known";
  const g = S.graph;
  const part = (id) => {
    const n = byId[id];
    if (n?.kind === "system") return h("span", {}, "module ", link(id));
    if (n?.kind === "terminal") return h("span", { class: "muted" }, `<${n.label}>`);
    return n ? link(id) : h("span", { class: "muted" }, id.split(":").slice(1).join(":"));
  };
  const sign = (a, b) => {                              // the drawn line from a to b: a connector's sign, a pipe's way
    const e = g.edges.find((x) => (x.from ?? x.source) === a && (x.to ?? x.target) === b);
    if (e && e.kind === "connector") return sdSign(e.polarity) || "?";
    if (e && e.kind === "pipe") return "+";                // a flow fills the stock it runs into
    const back = g.edges.find((x) => x.kind === "pipe" && (x.from ?? x.source) === b && (x.to ?? x.target) === a);
    return back ? MINUS : "";                               // a stock drains by its outflow
  };
  const ns = c.nodes, rows = ns.map((a, i) => [a, ns[(i + 1) % ns.length]]).filter(([a, b]) => a !== b);
  const signs = rows.map(([a, b]) => sign(a, b));
  const minus = signs.filter((x) => x === MINUS).length, unknown = signs.filter((x) => x === "?").length;
  showDetail(h("div", { class: "kind" }, `Feedback loop, ${word}`),
    h("h2", {}, h("span", { class: `loop-tag pol-${c.polarity || "unknown"}` }, c.label)), h("div", { class: "subtitle" }, c.name),
    h("p", {}, c.polarity && (!rows.length || signs.some((x) => x === "")) ? `${word[0].toUpperCase()}${word.slice(1)} by the signs of its links in the model; not all of them are drawn in this view (open its system to see them).`
      : c.polarity ? `${minus} negative link${minus === 1 ? "" : "s"} around it as drawn: ${minus % 2 ? "an odd number, so it balances" : "an even number, so it reinforces"}.`
                          : `${unknown || "a"} link${unknown === 1 ? "" : "s"} along it ${unknown === 1 ? "has" : "have"} no known sign, so whether it reinforces or balances is not known.`),
    h("h3", {}, "Around the loop"),
    h("table", { class: "parts" }, rows.map(([a, b], i) => h("tr", {}, h("td", {}, part(a)), h("td", { class: "muted" }, "→"), h("td", {}, part(b)),
      h("td", { class: "num" }, signs[i])))),
    h("h3", {}, "When it drives the behaviour"), loopDominance(c.name),
    (() => {                                            // the loops drawn alike here share its marker
      const grp = sdLoopGroups(S.graph, null, true).find((x) => x.loops.includes(c));
      const others = grp ? grp.loops.filter((x) => x !== c) : [];
      return others.length ? h("p", { class: "muted" }, "Drawn alike here (they differ only inside a closed system or outside this one): ",
        others.flatMap((x, i) => [i ? ", " : "", h("a", { href: "#", onclick: (ev) => { ev.preventDefault(); sdHighlight(x.name); openCausal(x.name); } }, `${x.label} ${x.name}`)])) : null;
    })(), sdWhat("loop"));
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
   one) never run along one another, nor a connector along a pipe; where the router left them on one track,
   an inner stretch of the connector is moved beside it (orthogonal still: the stretches either side of it lengthen or shorten) */
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
  // a pipe never moves, and a connector never runs along one either (it would read as part of the flow)
  const pipes = lay.edges.filter((le) => edge[le.id]?.kind === "pipe" && (le.sections || []).length);
  const onPipe = (a, b) => pipes.some((o) => pts(o).slice(1).some((q, j) => along(a, b, pts(o)[j], q) > 4));
  // (across a line of its own net it may go: uncross trades their ways after, untangle.js)
  const clash = (le, a, b) => onPipe(a, b) || lines.some((o) => o !== le && !net(edge[o.id], edge[le.id]) &&
      pts(o).slice(1).some((q, j) => along(a, b, pts(o)[j], q) > 4)) ||
    kids.some((c) => c.id !== edge[le.id].source && c.id !== edge[le.id].target &&
      Math.max(a.x, b.x) > c.x && Math.min(a.x, b.x) < c.x + c.width && Math.max(a.y, b.y) > c.y && Math.min(a.y, b.y) < c.y + c.height);
  for (let pass = 0; pass < 3; pass++) {
    let moved = false;
    for (const le of lines) {
      const p = pts(le);
      for (let i = 1; i < p.length - 2; i++) {             // inner stretches only: the ends stay on their parts
        const a = p[i], b = p[i + 1];
        if (!onPipe(a, b) && !lines.some((o) => o !== le && !net(edge[o.id], edge[le.id]) && pts(o).slice(1).some((q, j) => along(a, b, pts(o)[j], q) > 4))) continue;
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

/* after routing: a link that crosses a satellite's pipe (a flow between a stock and a cloud, stood beside the stock:
   satellites.js) is moved past the far end of it, beyond the cloud, where it lies on no part and along no line: a
   satellite reads as one short piece of its stock, with nothing drawn through it (docs/layout-rules.md) */
function sdAroundSatellites(lay, g) {
  const edge = Object.fromEntries(g.edges.map((e) => [e.id, e]));
  const box = Object.fromEntries(lay.children.map((c) => [c.id, c]));
  const pts = (le) => { const sc = le.sections[0]; return [sc.startPoint, ...(sc.bendPoints || []), sc.endPoint]; };
  const cols = [];                                      // each satellite's column: from its stock's edge to past its cloud
  for (const n of g.nodes) {                            // (laid out as satellites, or seated beside their stock after)
    const v = n.id, d = (n.kind === "valve" || n.kind === "disturbance") && drainOf(g, v), a = box[v], c = d && box[d.cloud], st = d && box[d.stock];
    if (!a || !c || !st) continue;
    const gap = Math.max(a.x - st.x - st.width, st.x - a.x - a.width, a.y - st.y - st.height, st.y - a.y - a.height);
    if (gap > 90) continue;
    const xs = [a.x, a.x + a.width, c.x, c.x + c.width], ys = [a.y, a.y + a.height, c.y, c.y + c.height];
    const upright = a.x + a.width / 2 > st.x && a.x + a.width / 2 < st.x + st.width;
    if (upright) ys.push(a.y > st.y ? st.y + st.height : st.y); else xs.push(a.x > st.x ? st.x + st.width : st.x);
    cols.push({ ids: new Set([v, d.cloud, d.stock]), upright, x0: Math.min(...xs) - 4, x1: Math.max(...xs) + 4, y0: Math.min(...ys), y1: Math.max(...ys) });
  }
  const lines = lay.edges.filter((le) => edge[le.id] && (le.sections || []).length);
  const onPart = (a, b, mine) => lay.children.some((k) => !mine.has(k.id) &&
    Math.max(a.x, b.x) > k.x - 4 && Math.min(a.x, b.x) < k.x + k.width + 4 && Math.max(a.y, b.y) > k.y - 4 && Math.min(a.y, b.y) < k.y + k.height + 4);
  const along = (le, a, b) => lines.some((o) => o !== le && pts(o).slice(1).some((q, j) => { const p = pts(o)[j];
    if (Math.abs(a.y - b.y) < 0.5 && Math.abs(p.y - q.y) < 0.5 && Math.abs(a.y - p.y) < 4) return Math.min(Math.max(a.x, b.x), Math.max(p.x, q.x)) - Math.max(Math.min(a.x, b.x), Math.min(p.x, q.x)) > 4;
    if (Math.abs(a.x - b.x) < 0.5 && Math.abs(p.x - q.x) < 0.5 && Math.abs(a.x - p.x) < 4) return Math.min(Math.max(a.y, b.y), Math.max(p.y, q.y)) - Math.max(Math.min(a.y, b.y), Math.min(p.y, q.y)) > 4;
    return false; }));
  // (as the audit measures them: scripts/diagram_audit.js)
  const short = (q) => { let L = 0; for (let j = 1; j < q.length; j++) L += Math.abs(q[j].x - q[j - 1].x) + Math.abs(q[j].y - q[j - 1].y);
    return L <= 1.6 * (Math.abs(q[0].x - q[q.length - 1].x) + Math.abs(q[0].y - q[q.length - 1].y)) + 120; };
  const cross = (a, b, c, d) => { const o = (p, q, r) => (q.x - p.x) * (r.y - p.y) - (q.y - p.y) * (r.x - p.x);
    return o(a, b, c) * o(a, b, d) < -1 && o(c, d, a) * o(c, d, b) < -1; };
  const netCross = (le, q) => { const e = edge[le.id];
    return lines.some((o) => { const f = edge[o.id];
      if (o === le || f.kind === "pipe" || (f.source !== e.source && f.target !== e.target)) return false;
      const r = pts(o);
      return q.slice(1).some((b, j) => r.slice(1).some((d, k) => cross(q[j], b, r[k], d))); }); };
  for (const le of lines) {
    const e = edge[le.id];
    if (e.kind === "pipe") continue;
    let p = pts(le);
    // (an end stretch across one: a stub at its part, so the rest of the stretch can move)
    const stub = (q, r) => { const L = Math.hypot(r.x - q.x, r.y - q.y); return { x: q.x + ((r.x - q.x) / L) * 12, y: q.y + ((r.y - q.y) / L) * 12 }; };
    const across = (a, b) => cols.some((k) => !k.ids.has(e.source) && !k.ids.has(e.target) && (Math.abs(a.y - b.y) < 0.5
      ? !k.upright ? false : a.y > k.y0 && a.y < k.y1 && Math.min(a.x, b.x) < k.x0 && Math.max(a.x, b.x) > k.x1
      : k.upright ? false : a.x > k.x0 && a.x < k.x1 && Math.min(a.y, b.y) < k.y0 && Math.max(a.y, b.y) > k.y1));
    if (p.length >= 2 && across(p[0], p[1]) && Math.hypot(p[1].x - p[0].x, p[1].y - p[0].y) > 40) { const q = stub(p[0], p[1]); p.splice(1, 0, q, { ...q }); }
    const n = p.length;
    if (n >= 2 && across(p[n - 2], p[n - 1]) && Math.hypot(p[n - 1].x - p[n - 2].x, p[n - 1].y - p[n - 2].y) > 40) { const q = stub(p[n - 1], p[n - 2]); p.splice(n - 1, 0, { ...q }, q); }
    le.sections = [{ startPoint: p[0], bendPoints: p.slice(1, -1), endPoint: p[p.length - 1] }];
    p = pts(le);
    for (let i = 1; i + 2 < p.length; i++) {             // inner stretches only: the ends stay on their parts
      const a = p[i], b = p[i + 1], level = Math.abs(a.y - b.y) < 0.5;
      for (const k of cols) {
        if (k.ids.has(e.source) || k.ids.has(e.target) || k.upright !== level) continue;
        const crosses = level ? a.y > k.y0 && a.y < k.y1 && Math.min(a.x, b.x) < k.x0 && Math.max(a.x, b.x) > k.x1
                              : a.x > k.x0 && a.x < k.x1 && Math.min(a.y, b.y) < k.y0 && Math.max(a.y, b.y) > k.y1;
        if (!crosses) continue;
        for (const to of level ? [k.y1 + 10, k.y0 - 10] : [k.x1 + 10, k.x0 - 10]) {
          const a2 = level ? { x: a.x, y: to } : { x: to, y: a.y }, b2 = level ? { x: b.x, y: to } : { x: to, y: b.y };
          const mine = new Set([e.source, e.target]);
          if ([[p[i - 1], a2], [a2, b2], [b2, p[i + 2]]].some(([q, r]) => onPart(q, r, mine) || along(le, q, r))) continue;
          const moved = p.map((q, j) => (j === i ? a2 : j === i + 1 ? b2 : q));
          if (!short(moved) || netCross(le, moved)) continue;     // (never a detour, nor across a line of its own net)
          Object.assign(a, a2); Object.assign(b, b2);
          break;
        }
      }
    }
    const q = pts(le).filter((r, j, all) => j === 0 || Math.abs(r.x - all[j - 1].x) + Math.abs(r.y - all[j - 1].y) > 0.5);
    const lean = q.filter((r, j) => j === 0 || j === q.length - 1 ||        // (stubs that did not move: taken out again)
      !((Math.abs(q[j - 1].x - r.x) < 0.5 && Math.abs(r.x - q[j + 1].x) < 0.5) || (Math.abs(q[j - 1].y - r.y) < 0.5 && Math.abs(r.y - q[j + 1].y) < 0.5)));
    le.sections = [{ startPoint: lean[0], bendPoints: lean.slice(1, -1), endPoint: lean[lean.length - 1] }];
  }
}
