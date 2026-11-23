/* rows over time as a heatmap, each cell shaded by its row's value (docs/proposals/charts.md): refs, a kind's states or
   goals, an off stretch hatched. A figure with an accessible name and its numbers as a table, coloured only from the
   page's tokens (tok). The dashboard's own chart forms, a heatmap of counts among them, are plots-*.js */
"use strict";

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
