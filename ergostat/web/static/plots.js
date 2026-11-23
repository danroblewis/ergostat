/* three more chart forms beside charts.js's (docs/proposals/charts.md): several series on one time axis, one measure
   against another (a phase plot), and rows over time as a heatmap. Each is a figure with an accessible name and its
   numbers as a table, coloured only from the page's tokens (tok), usable on its own until a panel registers it */
"use strict";

const PLOT_DASHES = [[], [6, 3], [2, 3], [8, 3, 2, 3], [1, 3]];       // line styles, as well as colour, tell series apart
const plotHue = (i) => tok(`--g${i % 10}`);
const HEAT_RAMP = ["--fill", "--line", "--line-strong", "--fan-50", "--muted", "--ink-2", "--ink"];   // sequential, both themes
const canvasFont = () => `${parseFloat(tok("--canvas-sm")) * devicePixelRatio}px ${tok("--font")}`;

/* the plot named for a screen reader, its head, a key, and the same numbers as a table (folded) */
function plotFigure(cls, label, head, plotEl, key, columns, rows) {
  plotEl.setAttribute("role", "img"); plotEl.setAttribute("aria-label", label);
  const table = h("table", {}, h("caption", { class: "muted" }, label), h("thead", {}, h("tr", {}, columns.map((c) => h("th", { scope: "col" }, c)))),
    h("tbody", {}, rows.map((r) => h("tr", {}, r.map((c, i) => (i ? h("td", {}, c) : h("th", { scope: "row" }, c)))))));
  return h("figure", { class: `chart plot-fig ${cls}`, "aria-label": label }, head, plotEl, key,
    h("details", { class: "plot-data small" }, h("summary", { class: "muted" }, "As a table"), table));
}
const cell = (v, unit = "") => (v == null ? "–" : `${fmt(v)}${unit ? " " + unit : ""}`);
const atOrLast = (vs, i) => (i == null ? before(vs, vs.length - 1) : vs[i]);

/* the pairs of two series on one time base (api/series: one times for every ref): bucket i of x with bucket i of y,
   in time order, only where both were measured */
function alignPairs(times, xs, ys) {
  const out = [];
  for (let i = 0; i < times.length; i++) if (xs[i] != null && ys[i] != null && Number.isFinite(xs[i]) && Number.isFinite(ys[i])) out.push([times[i], xs[i], ys[i]]);
  return out;
}

/* ---------------------------------------------------------------- several series, one time axis */

/* every rate in one unit (the one that reads best for the largest); each line named at its end, in its own hue and
   dash; the cursor's moment gives every series' value, above the plot */
function multiChart({ times, series, since = times[0], until = times[times.length - 1], group = chartGroup("multi"), height = 120, title = "" }) {
  const all = series.filter((s) => s.per).flatMap((s) => s.values).filter((v) => v != null && Number.isFinite(v));
  const ru = rateUnit(all.length ? Math.max(...all.map(Math.abs)) : null), k = RATE_PER_HOUR[ru];
  const list = series.map((s) => ({ name: s.name, unit: s.per ? `${s.unit || ""}${RATE_SUFFIX[ru]}` : s.unit || "",
                                    values: s.per ? s.values.map((v) => (v == null ? v : v * k)) : s.values }));
  const vals = list.map((s) => h("span", { class: "n" }));
  const show = (i) => list.forEach((s, j) => setText(vals[j], cell(atOrLast(s.values, i), s.unit)));
  const chips = list.map((s, j) => h("span", { class: "plot-chip" }, h("span", { class: "sw", style: `border-color:var(--g${j % 10});border-top-style:${["solid", "dashed", "dotted", "dashed", "dotted"][j % 5]}` }), s.name, " ", vals[j]));
  show(null);
  const head = h("div", { class: "chart-head" }, h("span", { class: "chart-name" }, title || list.map((s) => s.name).join(", ")), h("span", { class: "plot-vals" }, chips));
  const plotEl = h("div", { class: "chart-plot" });
  const label = `${list.map((s) => s.name).join(", ")} over time, ${[...new Set(list.map((s) => s.unit).filter(Boolean))].join(", ") || "on one axis"}`;
  mountPlot(plotEl, (width) => {
    const o = baseOpts({ width, height, group, since, until, xAxis: true,
      hooks: { draw: [endLabels(list)], setCursor: [(u) => show(u.cursor.idx)] } });
    o.series = [{}, ...list.map((s, j) => inkLine({ stroke: plotHue(j), dash: PLOT_DASHES[j % PLOT_DASHES.length], width: 1.5 }))];
    o.cursor.points.show = (u) => dataPoint(u, 1);                    // a mark on every line, not only the first
    return new uPlot(o, [times, ...list.map((s) => s.values)], plotEl);
  });
  return plotFigure("plot-multi", label, head, plotEl, null, ["time", ...list.map((s) => `${s.name}${s.unit ? ` (${s.unit})` : ""}`)],
    times.map((t, i) => [clockS(t), ...list.map((s) => cell(s.values[i]))]));
}
/* each line's name at its last value, inside the plot's right edge, pushed apart so none covers another */
function endLabels(list) {
  return (u) => {
    const { left, top, width, height } = u.bbox, gap = 12 * devicePixelRatio;
    const at = list.map((s, j) => ({ j, text: s.name, y: (() => { const v = before(s.values, s.values.length - 1); return v == null ? null : u.valToPos(v, "y", true); })() }))
      .filter((a) => a.y != null).sort((a, b) => a.y - b.y);
    for (let i = 1; i < at.length; i++) at[i].y = Math.max(at[i].y, at[i - 1].y + gap);
    const ctx = u.ctx;
    ctx.save(); ctx.font = canvasFont(); ctx.textAlign = "right"; ctx.textBaseline = "bottom"; ctx.lineWidth = 3 * devicePixelRatio; ctx.strokeStyle = tok("--bg");
    for (const a of at) {
      const y = Math.min(Math.max(a.y - 2 * devicePixelRatio, top + gap), top + height);
      ctx.fillStyle = plotHue(a.j); ctx.strokeText(a.text, left + width - 4 * devicePixelRatio, y); ctx.fillText(a.text, left + width - 4 * devicePixelRatio, y);
    }
    ctx.restore();
  };
}

/* ---------------------------------------------------------------- one measure against another */

/* x and y (api/series entries on the same buckets): joined in time order, a tick on the path showing its direction,
   the start an open point and the latest a filled one; each axis named with its unit; a goal's desired level dashed */
function phasePlot({ x, y, times, height = 220, title = "" }) {
  const pts = alignPairs(times, x.values, y.values);
  const un = (s) => (s.per ? `${s.unit || ""}/h` : s.unit || "");
  const axisName = (s) => `${s.name}${un(s) ? ` (${un(s)})` : ""}`;
  const val = h("span", { class: "chart-val" });
  const say = (p) => setText(val, p ? `${cell(p[1], un(x))}, ${cell(p[2], un(y))} at ${clockS(p[0])}` : "–");
  say(pts[pts.length - 1]);
  const head = h("div", { class: "chart-head" }, h("span", { class: "chart-name" }, title || `${y.name} against ${x.name}`), h("span", { class: "muted" }, "in time order"), val);
  const plotEl = h("div", { class: "chart-plot" });
  const label = `${y.name} against ${x.name}: ${pts.length} moments joined in time order, the latest marked`;
  const dx = x.goal?.value ?? null, dy = y.goal?.value ?? null;
  if (pts.length) mountPlot(plotEl, (width) => {
    const range = (k, d) => padRange(Math.min(...pts.map((p) => p[k]), d ?? Infinity), Math.max(...pts.map((p) => p[k]), d ?? -Infinity));
    const o = baseOpts({ width, height, group: chartGroup("phase"), since: 0, until: 1, xAxis: true, hooks: { draw: [phasePath(pts, dx, dy)] } });
    const axisFont = `${tok("--canvas-sm")} ${tok("--font")}`;
    o.scales = { x: { time: false, auto: false, range: () => range(1, dx) }, y: { auto: false, range: () => range(2, dy) } };
    o.axes[0] = { ...o.axes[1], side: 2, size: 34, label: axisName(x), labelSize: 14, labelFont: axisFont, labelGap: 0 };
    o.axes[1] = { ...o.axes[1], size: 56, label: axisName(y), labelSize: 14, labelFont: axisFont, labelGap: 0 };
    o.cursor = { show: false }; o.hooks.setCursor = [];
    o.series = [{}, { paths: () => null, points: { show: false } }];
    const u = new uPlot(o, [range(1, dx), [null, null]], plotEl);
    u.over.addEventListener("mousemove", (ev) => {                    // the nearest moment, said in the head
      const d = (p) => Math.hypot(u.valToPos(p[1], "x") - ev.offsetX, u.valToPos(p[2], "y") - ev.offsetY);
      say(pts.reduce((b, p) => (d(p) < d(b) ? p : b)));
    });
    u.over.addEventListener("mouseleave", () => say(pts[pts.length - 1]));
    return u;
  });
  else plotEl.append(h("div", { class: "muted small" }, "No moment with both measured in the window."));
  const key = h("div", { class: "plot-key" }, h("span", {}, "○ first, ● latest"), dx != null || dy != null ? h("span", {}, "dashed: the desired level") : null);
  return plotFigure("plot-phase", label, head, plotEl, key, ["time", axisName(x), axisName(y)], pts.map((p) => [clockS(p[0]), cell(p[1]), cell(p[2])]));
}
function phasePath(pts, dx, dy) {
  return (u) => {
    const ctx = u.ctx, { left, top, width, height } = u.bbox, r = devicePixelRatio;
    const P = pts.map((p) => [u.valToPos(p[1], "x", true), u.valToPos(p[2], "y", true)]);
    ctx.save(); ctx.beginPath(); ctx.rect(left, top, width, height); ctx.clip();
    ctx.strokeStyle = tok("--muted"); ctx.lineWidth = r; ctx.setLineDash([4 * r, 3 * r]);
    if (dx != null) { const X = u.valToPos(dx, "x", true); ctx.beginPath(); ctx.moveTo(X, top); ctx.lineTo(X, top + height); ctx.stroke(); }
    if (dy != null) { const Y = u.valToPos(dy, "y", true); ctx.beginPath(); ctx.moveTo(left, Y); ctx.lineTo(left + width, Y); ctx.stroke(); }
    ctx.setLineDash([]); ctx.strokeStyle = tok("--ink"); ctx.lineWidth = 1.5 * r;
    ctx.beginPath(); P.forEach(([a, b], i) => (i ? ctx.lineTo(a, b) : ctx.moveTo(a, b))); ctx.stroke();
    ctx.fillStyle = tok("--ink");
    const every = Math.max(1, Math.ceil(P.length / 12));               // a direction tick on about twelve of the steps
    for (let i = 1; i < P.length; i += every) {
      const [a0, b0] = P[i - 1], [a1, b1] = P[i], len = Math.hypot(a1 - a0, b1 - b0);
      if (len < 8 * r) continue;
      const ang = Math.atan2(b1 - b0, a1 - a0), mx = (a0 + a1) / 2, my = (b0 + b1) / 2, s = 4 * r;
      ctx.beginPath(); ctx.moveTo(mx + s * Math.cos(ang), my + s * Math.sin(ang));
      ctx.lineTo(mx + s * Math.cos(ang + 2.5), my + s * Math.sin(ang + 2.5)); ctx.lineTo(mx + s * Math.cos(ang - 2.5), my + s * Math.sin(ang - 2.5)); ctx.fill();
    }
    const dot = ([a, b], filled) => { ctx.beginPath(); ctx.arc(a, b, 3.5 * r, 0, 2 * Math.PI); ctx.fillStyle = tok(filled ? "--ink" : "--bg"); ctx.fill(); ctx.stroke(); };
    if (P.length) { dot(P[0], P.length === 1); dot(P[P.length - 1], true); }
    ctx.restore();
  };
}

/* ---------------------------------------------------------------- rows over time */

/* rows (refs, a kind's states, goals) by the window's buckets, each cell one step of a sequential ramp; blank where
   nothing was read; a stretch off (the whole map's, or a row's own) hatched in red. With own, each row is scaled to
   its own lowest and highest in the window, and the key says so; the cursor gives the cell's value */
function heatmap({ rows, times, since = null, until = null, own = false, unit = "", off = [], group = chartGroup("heat"), title = "" }) {
  const n = rows.length, w = times.length > 1 ? times[1] - times[0] : 1;
  since = since ?? times[0] - w / 2; until = until ?? times[times.length - 1] + w / 2;
  const span = (vs) => { const f = vs.filter((v) => v != null && Number.isFinite(v)); return f.length ? [Math.min(...f), Math.max(...f)] : [0, 0]; };
  const shared = [Math.min(0, ...rows.map((r) => span(r.values)[0])), Math.max(...rows.map((r) => span(r.values)[1]))];
  const ranges = rows.map((r) => (own ? span(r.values) : shared));
  const step = (v, [lo, hi]) => (hi > lo ? Math.min(HEAT_RAMP.length - 1, Math.floor(((v - lo) / (hi - lo)) * HEAT_RAMP.length)) : 0);
  const val = h("span", { class: "chart-val" }), unitOf = (r) => r.unit ?? unit;
  const say = (r, i) => setText(val, r == null || i == null ? "" : `${rows[r].name} at ${clockS(times[i])}: ${cell(rows[r].values[i], unitOf(rows[r]))}${offAt(r, times[i]) ? ", off" : ""}`);
  const offAt = (r, t) => [...off, ...(rows[r].off || [])].some(([a, b]) => t >= a && t <= b);
  const head = h("div", { class: "chart-head" }, h("span", { class: "chart-name" }, title || "Over time"), val);
  const plotEl = h("div", { class: "chart-plot" });
  const label = `${title || "Heatmap"}: ${n} rows (${rows.map((r) => r.name).join(", ")}) by ${times.length} time buckets`;
  const nameW = Math.min(140, 16 + 6.5 * Math.max(0, ...rows.map((r) => String(r.name).length)));
  mountPlot(plotEl, (width) => {
    const o = baseOpts({ width, height: n * 16 + 28, group, since, until, xAxis: true, yRange: () => [0, n],
      hooks: { drawClear: [heatCells(rows, times, w, ranges, step, off)],
               setCursor: [(u) => { const i = u.cursor.idx, v = u.cursor.top == null || u.cursor.top < 0 ? null : u.posToVal(u.cursor.top, "y");
                                    say(v == null ? null : Math.min(n - 1, Math.max(0, n - 1 - Math.floor(v))), i); }] } });
    o.axes[1] = { ...o.axes[1], size: nameW, grid: { show: false }, splits: () => rows.map((_, r) => n - r - 0.5), values: (u, vs) => vs.map((v) => rows[Math.round(n - 0.5 - v)]?.name ?? "") };
    o.series = [{}, { paths: () => null, points: { show: false } }];
    o.cursor.points = { show: false }; o.cursor.y = true;
    return new uPlot(o, [times, times.map(() => 0)], plotEl);
  });
  const anyOff = off.length || rows.some((r) => r.off?.length);
  const key = h("div", { class: "plot-key" }, own ? "each row from its own lowest" : cell(shared[0], unit), h("span", { class: "ramp" }, HEAT_RAMP.map((t) => h("span", { style: `background:var(${t})` }))),
    own ? "to its own highest in the window" : cell(shared[1], unit), h("span", { class: "muted" }, "; blank: nothing read"),
    anyOff ? [h("span", { class: "hatch" }), "off"] : null);
  return plotFigure("plot-heat", label, head, plotEl, key, ["time", ...rows.map((r) => r.name)],
    times.map((t, i) => [clockS(t), ...rows.map((r) => cell(r.values[i]))]));
}
function heatCells(rows, times, w, ranges, step, off) {
  return (u) => {
    const ctx = u.ctx, { left, top, width, height } = u.bbox, n = rows.length, r = devicePixelRatio;
    const X = (t) => u.valToPos(t, "x", true), Y = (v) => u.valToPos(v, "y", true);
    ctx.save(); ctx.beginPath(); ctx.rect(left, top, width, height); ctx.clip();
    const fills = HEAT_RAMP.map(tok);
    rows.forEach((row, k) => {
      const y0 = Y(n - k), y1 = Y(n - k - 1);
      times.forEach((t, i) => {
        const v = row.values[i];
        if (v == null || !Number.isFinite(v)) return;
        ctx.fillStyle = fills[step(v, ranges[k])];
        ctx.fillRect(X(t - w / 2), y0, Math.max(r, X(t + w / 2) - X(t - w / 2)), Math.max(r, y1 - y0 - r));
      });
      for (const [a, b] of [...off, ...(row.off || [])]) hatch(ctx, X(a), y0, X(b) - X(a), y1 - y0, r);
    });
    ctx.restore();
  };
}
/* off: red hatching over the cells and a red edge along their top, so it reads without colour too */
function hatch(ctx, x, y, w, hh, r) {
  if (!(w > 0)) w = r;
  ctx.save(); ctx.beginPath(); ctx.rect(x, y, w, hh); ctx.clip();
  ctx.strokeStyle = tok("--bad"); ctx.lineWidth = r;
  ctx.beginPath();
  for (let d = -hh; d < w; d += 5 * r) { ctx.moveTo(x + d, y + hh); ctx.lineTo(x + d + hh, y); }
  ctx.stroke(); ctx.fillStyle = tok("--bad"); ctx.fillRect(x, y, w, 2 * r);
  ctx.restore();
}
/* a heatmap's rows from the API: refs (api/series, each on its own range), a kind's states (api/items-flow counts,
   on one scale), goals (api/loop-scope each: how far off, its off stretches hatched, each on its own range) */
const heatOfSeries = (d) => ({ times: d.times, since: d.since, until: d.until, own: true,
  rows: d.series.map((s) => ({ name: s.name, values: s.values, unit: s.per ? `${s.unit || ""}/h` : s.unit || "" })) });
const heatOfStates = (d) => ({ times: d.times, since: d.since, until: d.until, unit: "items", title: d.kind,
  rows: d.states.map((st) => ({ name: st, values: d.counts[st] })) });
const heatOfGoals = (list) => ({ times: list[0].times, since: list[0].since, until: list[0].until, own: true, title: "how far off",
  rows: list.map((d) => ({ name: d.goal, unit: d.unit, off: d.off, values: d.e.map((v) => (v == null ? v : Math.abs(v))) })) });
