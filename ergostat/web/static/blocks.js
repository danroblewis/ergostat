/* the block view */
"use strict";
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
    // H is the sensor on the stock itself; one on a disturbance is feedforward, not feedback
    const sensors = lp.nodes.filter((id) => id.startsWith("sensor:")).map((id) => byId[id]).filter(Boolean)
                      .sort((a, b) => (a.measures === lp.stock ? 0 : 1) - (b.measures === lp.stock ? 0 : 1));
    const valves = lp.nodes.filter((id) => id.startsWith("flow:")).map((id) => byId[id]).filter(Boolean);
    // to a loop, any inflow it does not drive is a disturbance: declared ones, and other agents' valves
    const mine = new Set(valves.map((v) => v.id));
    // ...and any outflow it does not drive, which enters the plant's junction with −
    const dists = [
      ...g.edges.filter((e) => e.kind === "pipe" && e.target === stock.id && !mine.has(e.source)
                               && ["disturbance", "valve"].includes(byId[e.source]?.kind)).map((e) => ({ ...byId[e.source], sign: "+" })),
      ...g.edges.filter((e) => e.kind === "pipe" && e.source === stock.id && !mine.has(e.target)
                               && ["disturbance", "valve"].includes(byId[e.target]?.kind)).map((e) => ({ ...byId[e.target], sign: "−" })),
    ];
    const drains = valves.length && g.edges.some((e) => e.kind === "pipe" && e.source === stock.id && e.target === valves[0].id);
    // feedforward: a sensor the controller reads that measures a disturbance, not the stock
    const ff = g.edges.filter((e) => e.kind === "signal" && e.target === ctl.id).map((e) => byId[e.source])
                      .filter((x) => x && x.measures !== lp.stock && dists.some((d) => d.flow === x.measures));
    const chain = (stock.systems?.length ? stock.systems : ctl.systems || []);             // innermost first
    rows.push({ name, lp, ctl, stock, sensors, valves, dists, drains, ff, system: chain[0] || "", path: [...chain].reverse() });
  }
  // the loops of one system together, systems in the order they first appear: the columns read by system
  const order = [...new Set(rows.map((r) => r.system))];
  return rows.map((r, i) => [order.indexOf(r.system), i, r]).sort((a, b) => a[0] - b[0] || a[1] - b[1]).map((x) => x[2]);
}

function drawBlocks(svg, g) {
  const rows = blockLayout(g);
  const vp = s("g", { id: "viewport" });
  svg.replaceChildren(vp);                                // in the page from the start, so text can be measured
  // widths from the longest text in any row, so every row lines up and nothing overflows
  const tw = (t) => (t || "").length * 6.4 + 28;
  const cw = Math.max(190, ...rows.map((r) => Math.max(tw(r.ctl.label) + 10, tw("C · " + badgeText(r.ctl.agent)))));
  const vw = Math.max(160, ...rows.map((r) => Math.max(tw(r.valves[0]?.label), tw(badgeText(r.valves[0]?.agent)), tw("actuator · " + (r.valves[0]?.rateText || "") + (r.valves[0]?.max ? ` · ≤ ${r.valves[0].max} a run` : "")))));
  const sw = Math.max(160, ...rows.map((r) => Math.max(tw(r.stock.label), tw(`plant ∫ · ${r.stock.valueText} ${r.stock.unit || ""}`))));
  const hw = Math.max(160, ...rows.map((r) => Math.max(tw(r.sensors[0]?.label), tw(`H · reads ${r.sensors[0]?.reading ?? "?"} · every ${r.sensors[0]?.agent?.when || ""}`))));
  const spText = (lp) => lp.setpoint.replace("<=", "≤").replace(">=", "≥").replace("==", "=").trim() + (lp.band || "");
  const rw = Math.max(...rows.map((r) => ("r: " + spText(r.lp)).length * 7.6));      // r's label clears the junction's + sign
  const X = { r: 30, sum: Math.max(130, 30 + rw + 46) };
  X.ctl = X.sum + 92; X.valve = X.ctl + cw + 50; X.dsum = X.valve + vw + 50; X.stock = X.dsum + 50; X.out = X.stock + sw + 60;
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
  const label = (x, y, t, cls = "t-sub", anchor = "middle", full = null) =>
    s("text", { x, y, class: cls, "text-anchor": anchor }, full ? s("title", {}, full) : null, t);
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
  if (!rows.length) { svg.replaceChildren(); return null; }
  // each system's loops together, in an outline titled with where the system sits; a column holds
  // whole systems where it can, and is about as tall as the others
  const GAP = 46, colW = X.out + 130;
  const groups = [];
  for (const r of rows) {
    const last = groups[groups.length - 1];
    if (last && last.system === r.system) last.rows.push(r); else groups.push({ system: r.system, path: r.path, rows: [r] });
  }
  const total = rows.length * RH + groups.length * GAP, cols = Math.min(4, Math.max(1, Math.round(total / 1400))), target = total / cols;
  const place = new Map();
  let col = 0, y = 30, frames = [];
  for (const gr of groups) {
    const hgt = gr.rows.length * RH + GAP;
    if (y > 30 && y + hgt > target + RH && col < cols - 1) { col += 1; y = 30; }
    if (gr.system) frames.push({ x: col * colW, y, w: X.out + 100, h: hgt - 12, path: gr.path });
    y += gr.system ? GAP : 10;
    for (const r of gr.rows) { place.set(r, { y0: y + 10, dx: col * colW }); y += RH; }
  }
  const tall = Math.max(...[...place.values()].map((p) => p.y0)) + RH;
  for (const f of frames) {
    vp.append(s("rect", { x: f.x - 4, y: f.y, width: f.w, height: f.h, rx: 16, class: "block-system" }),
              s("text", { x: f.x + 12, y: f.y + 24, class: "t-label block-system-title" }, f.path.join(" › ").toUpperCase()));
  }
  rows.forEach((row) => {
    const { y0, dx } = place.get(row), cy = y0 + 50;
    const st = row.lp.status || "unknown";
    const tone = { off: "var(--bad)", holding: "var(--ok)", open: "var(--warn)" }[st] || "var(--unknown)";
    const loopG = s("g", { class: "block-loop", "data-loop": row.name, transform: dx ? `translate(${dx},0)` : null });
    loopG.append(s("rect", { x: 6, y: y0 - 30, width: X.out + 70, height: RH - 20, rx: 14, fill: "none", stroke: "var(--line)", "stroke-dasharray": "4 4" }));
    const nx = 18;                                          // its system is the outline around it
    loopG.append(label(nx, y0 - 10, row.name, "t-label", "start"), label(nx + row.name.length * 7.4 + 10, y0 - 10, st, "t-sub", "start"));
    loopG.lastChild.style.fill = tone;
    const sp = spText(row.lp);
    const open = row.lp.openLoop;
    if (open) {
      // an open loop: time drives the controller; nothing is compared, nothing fed back
      loopG.append(label(X.r, cy - 8, `t: ${row.ctl.agent?.schedule || row.ctl.agent?.when || "its schedule"}`, "t-sub", "start"));
      loopG.append(...line([[X.r, cy], [X.ctl, cy]], "", "var(--ink)"));
    } else {
      // r and the summing junction
      loopG.append(label(X.r, cy - 8, "r: " + sp, "t-sub", "start"));
      loopG.append(...line([[X.r, cy], [X.sum - 14, cy]], "", "var(--ink)"));
      loopG.append(sum(X.sum, cy, [[-24, -16, "+"], [-16, 32, "−"]]));
      // e into the controller
      loopG.append(...line([[X.sum + 14, cy], [X.ctl, cy]], "", tone));
      const err = row.lp.error;
      const eLab = label((X.sum + X.ctl) / 2 + 6, cy - 8, err != null ? `e = ${fmt(err)}` : "e");
      eLab.style.fill = tone;                                    // coloured by the loop's status, not by e's sign
      loopG.append(eLab);
    }
    loopG.append(box(X.ctl, cy - 36, cw, 72, row.ctl.label, "C · " + (row.ctl.agent ? badgeText(row.ctl.agent) : "unfilled"),
                     "var(--ctl)", "var(--ctl-line)", row.ctl,
                     row.ctl.decision ? label(cw / 2, 60, "“" + (row.ctl.decision.length > cw / 6.4 - 4 ? row.ctl.decision.slice(0, Math.floor(cw / 6.4) - 5) + "…" : row.ctl.decision) + "”", "t-sub", "middle", row.ctl.decision) : null));
    // u into the valve(s)
    const v = row.valves[0];
    loopG.append(...line([[X.ctl + cw, cy], [X.valve, cy]], "", "var(--ctl-line)"));
    loopG.append(label((X.ctl + cw + X.valve) / 2, cy - 8, v?.position != null ? `u = ${fmt(v.position)}` : "u"));
    loopG.append(box(X.valve, cy - 36, vw, 72, v ? v.label : "no valve", v ? `actuator · ${v.rateText}${v.max ? ` · ≤ ${fmt(v.max)} a run` : ""}` : "",
                     "var(--panel)", v ? "var(--valve)" : "var(--warn)", v,
                     v?.agent ? label(vw / 2, 60, badgeText(v.agent)) : null));
    // the disturbance joins at the plant's input
    if (row.dists.length || row.drains) {
      // the plant's input: the actuator's flow (− when it drains the stock) and any disturbance (+)
      loopG.append(...line([[X.valve + vw, cy], [X.dsum - 14, cy]], "", "var(--pipe)"));
      loopG.append(sum(X.dsum, cy, [[-22, -16, row.drains ? "−" : "+"], [18, -20, row.dists.length ? (new Set(row.dists.map((d) => d.sign)).size > 1 ? "±" : row.dists[0].sign) : ""]]));
    }
    if (row.dists.length) {
      const d = row.dists[0];
      const more = row.dists.length > 1 ? ` (+${row.dists.length - 1} more)` : "";
      // another loop's actuator is known and measured: say whose it is (the loops are in series)
      const fromLoop = d.kind === "valve" ? Object.entries(g.loops).find(([, l]) => l.nodes.includes(d.id))?.[0] : null;
      const who = fromLoop ? ` · loop ${fromLoop}'s actuator` : d.kind === "valve" && d.agent ? ` · moved by ${d.agent.name}` : "";
      // d, a disturbance: a flow into (or out of) the stock that this loop does not command
      loopG.append(...line([[X.dsum, cy - (row.ff.length ? 78 : 70)], [X.dsum, cy - 14]], "", "var(--dist)"));
      const dl = label(X.dsum + 8, cy - 34, "d", "t-label", "start");
      dl.style.fill = "var(--dist)";
      const name = d.flow || d.label;
      const why = `a disturbance to this loop: flow ${name} ${d.sign === "−" ? "drains" : "fills"} ${row.stock.label}, and this loop does not command it` +
                  (fromLoop ? ` (loop ${fromLoop} does)` : d.agent ? ` (${d.agent.name} moves it)` : " (nothing in the model moves it)");
      const dt = label(X.dsum - 8, cy - 58, `d: ${name} ${d.rateText}${d.estimated ? " (est.)" : ""}${who}${more}`, "t-sub", "end", why);
      dt.style.fill = "var(--dist)";
      loopG.append(dl, dt);
      if (row.ff.length) {
        // the controller also measures d itself: feedforward, acting before d shows in the error
        const f = row.ff[0], fy = cy - 78, fx = X.ctl + cw / 2;
        loopG.append(...line([[X.dsum, fy], [fx, fy], [fx, cy - 36]], "", "var(--dist)", true));
        loopG.append(label((fx + X.dsum) / 2, fy - 6, `feedforward: ${f.label} reads ${f.reading ?? "?"} now (d: the window's average)`, "t-sub"));
      }
    }
    if (row.dists.length || row.drains) loopG.append(...line([[X.dsum + 14, cy], [X.stock, cy]], "", "var(--pipe)"));
    else loopG.append(...line([[X.valve + vw, cy], [X.stock, cy]], "", "var(--pipe)"));
    // the plant: the stock
    loopG.append(box(X.stock, cy - 36, sw, 72, row.stock.label, `plant ∫ · ${row.stock.valueText} ${row.stock.unit || ""}`,
                     "var(--stock)", "var(--stock-line)", row.stock));
    // y out, and the feedback path through the sensor
    loopG.append(...line([[X.stock + sw, cy], [X.out + 40, cy]], "", tone));
    loopG.append(label(X.out + 20, cy - 8, "y"));
    const se = row.sensors[0];
    const fy = cy + 90, sw2 = hw, sx = (X.sum + X.out) / 2 - hw / 2;
    loopG.append(...line([[X.out, cy], [X.out, fy], [sx + sw2, fy]], "", tone, true));
    loopG.append(box(sx, fy - 30, sw2, 60, se ? se.label : "no sensor",
                     se ? `H · reads ${se.reading ?? "?"}${se.agent?.when ? " · every " + se.agent.when.replace(/^on .*/, "event") : ""}` : "",
                     "var(--sensor)", se ? "var(--sensor-line)" : "var(--warn)", se));
    if (open) {
      // watched against the setpoint, to judge the loop; not fed back to the controller
      loopG.append(line([[sx, fy], [X.r + 4, fy]], "", tone, true)[0],      // ends in a bar: it goes nowhere
                   s("path", { d: `M${X.r + 4},${fy - 6} v12`, stroke: tone, "stroke-width": 2 }));
      loopG.append(label(X.r + 10, fy - 8, `ym, watched against r: ${sp} (not fed back)`, "t-sub", "start"));
    } else {
      loopG.append(...line([[sx, fy], [X.sum, fy], [X.sum, cy + 14]], "", tone, true));
      loopG.append(label((X.sum + sx) / 2, fy - 8, "ym"));
    }
    vp.append(loopG);
  });
  svg.replaceChildren(vp);
  applyView(svg);
  return { width: cols * colW - 20, height: tall + 20 };
}

