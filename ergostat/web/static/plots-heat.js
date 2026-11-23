/* a heatmap: X (time or a number) by a binned Y, each cell shaded by how many points fell in it, or a histogram's
   buckets over time (the latency heatmap), with its scale labelled in a margin beside the plot */
"use strict";

(() => {
  const F = plotFrame, M = plotMath, N = () => panelNumbers;
  const SCALE_W = 58;

  function cellsOf(series, xr, yr, xBins, yBins) {
    const xEdges = M.edgesOver(xr.min, xr.max, xBins), yEdges = M.edgesOver(yr.min, yr.max, yBins);
    const counts = Array.from({ length: xBins }, () => new Array(yBins).fill(0));
    for (const one of series) one.xs.forEach((x, i) => {
      const y = one.values[i];
      if (x == null || y == null || x < xr.min || x > xr.max || y < yr.min || y > yr.max) return;
      const cx = Math.min(xBins - 1, Math.floor((x - xr.min) / (xr.max - xr.min) * xBins));
      const cy = Math.min(yBins - 1, Math.floor((y - yr.min) / (yr.max - yr.min) * yBins));
      counts[cx][cy]++;
    });
    return { xEdges, yEdges, counts };
  }
  /* a histogram's buckets over time (Prometheus's _bucket by le): a column a time, a row a bucket. Each row is the same
     height and labelled by its bounds, so no value is placed inside a bucket as if it were known there (G22); a time
     with no count is a gap, never a zero */
  function bucketsOf(result) {
    const { times, counts } = result.over_time, edges = result.x.edges, step = result.step || 60;
    const xEdges = [...times, times[times.length - 1] + step], yEdges = edges.map((_, i) => i);
    const unit = N().parseUnit(result.x.unit || "");
    return { xEdges, yEdges, counts: counts.map((c) => c || []), xr: { min: xEdges[0], max: xEdges[xEdges.length - 1], log: false },
             yr: { min: 0, max: edges.length - 1, log: false }, yTicks: { major: yEdges, minor: [], words: edges.map((e) => N().formatValue(e, unit)) },
             names: { xKind: "time", xUnit: null, xTitle: "Time", yTitle: F.titled(result.x.label, unit) } };
  }
  const seat = (edges, v) => { const i = edges.findIndex((e) => e > v); return Math.max(0, Math.min(edges.length - 2, (i < 0 ? edges.length : i) - 1)); };
  /* where a count sits on the ramp, 0 to 1. A log scale is log(1 + count), so a cell of one is still on it */
  const placer = (top, log) => (log ? (c) => Math.log1p(c) / Math.log1p(top || 1) : (c) => c / (top || 1));

  /* sequential runs from a wash of the hue to the hue; diverging runs through the paper at the average occupied cell */
  function ramp(palette, centre) {
    const bg = F.ink("--bg"), hi = F.ink("--g0"), lo = F.ink("--g1");
    if (palette === "diverging") return (t) => (t >= centre ? F.mix(hi, bg, (t - centre) / ((1 - centre) || 1)) : F.mix(lo, bg, (centre - t) / (centre || 1)));
    return (t) => F.mix(hi, bg, 0.1 + 0.9 * t);
  }

  function drawHeatmap(target, first, config, opts) {
    const o = opts.options, d = config.display || {};
    return F.view(target, first, opts, (result, off) => {
      const buckets = result.over_time ? bucketsOf(result) : null;
      let xr, yr, cells;
      if (buckets) ({ xr, yr } = cells = buckets);
      else {
        const shown = result.series.filter((x) => !off.has(x.key));
        const xs = shown.flatMap((x) => x.xs), ys = shown.flatMap((x) => x.values);
        const pairs = shown.flatMap((x) => x.xs.map((v, i) => (v != null && x.values[i] != null ? x.values[i] : null))).filter((v) => v != null);
        xr = F.range(xs, { ...d.x, log: false }, { pad: 0 }); yr = F.range(ys, { ...d.y, log: false }, { pad: 0 });
        const yBins = o.y_bins === "auto" || o.y_bins == null ? Math.max(6, Math.min(24, M.autoBins(pairs))) : Math.max(1, Math.round(+o.y_bins));
        cells = cellsOf(shown, xr, yr, Math.max(1, Math.min(48, new Set(xs.filter((v) => v != null)).size)), yBins);
      }
      const { xEdges, yEdges, counts } = cells;
      const flat = counts.flat(), top = Math.max(0, ...flat), log = o.scale === "log";
      const at = placer(top, log);
      const occupied = flat.filter((c) => c > 0);
      const mean = occupied.length ? occupied.reduce((a, b) => a + b, 0) / occupied.length : 0;
      const centre = o.palette === "diverging" ? Math.max(0.05, Math.min(0.95, at(mean))) : 0;
      const n = buckets ? buckets.names : F.names(result, config, opts.unit);
      let plot = null;
      const paint = (ctx, w, ht) => {
        const colour = ramp(o.palette, centre);
        plot = F.cartesian(ctx, w, ht, { xr, yr, xKind: n.xKind, xUnit: n.xUnit, yUnit: opts.unit, xTitle: n.xTitle, yTitle: n.yTitle, right: SCALE_W,
                                         yTicks: buckets?.yTicks });
        const { box, X, Y } = plot;
        F.clipTo(ctx, box, () => counts.forEach((col, cx) => col.forEach((c, cy) => {
          if (!c && o.empty !== "zero") return;
          const x0 = Math.floor(X.at(xEdges[cx])), x1 = Math.ceil(X.at(xEdges[cx + 1])), y0 = Math.ceil(Y.at(yEdges[cy])), y1 = Math.floor(Y.at(yEdges[cy + 1]));
          ctx.fillStyle = colour(at(c));
          ctx.fillRect(x0, y1, x1 - x0, y0 - y1);
        })));
        plot.finish();
        const barX = box.right + 8, barW = 10;
        for (let p = 0; p < box.height; p++) { ctx.fillStyle = colour(1 - p / box.height); ctx.fillRect(barX, box.top + p, barW, 1.5); }
        ctx.strokeStyle = F.ink("--line-strong");
        ctx.strokeRect(barX + 0.5, box.top + 0.5, barW - 1, box.height - 1);
        ctx.font = F.font(); ctx.fillStyle = F.ink("--muted"); ctx.textAlign = "left"; ctx.textBaseline = "middle";
        const labels = log ? [0, ...M.logTicks(1, Math.max(top, 1)).major.filter((v) => v < top), top]
          : [...M.linearTicks(0, top || 1, Math.max(2, Math.floor(box.height / 40))).filter((v) => v < top * 0.94), top];
        const whole = [...new Set(labels.map((v) => Math.round(v)))];
        for (const v of whole) {
          const y = box.bottom - at(v) * box.height;
          ctx.fillText(String(v), barX + barW + 4, Math.max(box.top + 5, Math.min(box.bottom - 5, y)));
        }
        ctx.save();
        ctx.translate(w - 5, (box.top + box.bottom) / 2);
        ctx.rotate(-Math.PI / 2);
        ctx.textAlign = "center";
        ctx.fillText(`${buckets ? "In each bucket" : "Count"}${log ? " (log)" : ""}`, 0, 0);
        ctx.restore();
      };
      const pick = (x, y) => {
        if (!plot) return null;
        const { box, X, Y } = plot;
        if (x < box.left || x > box.right || y < box.top || y > box.bottom) return null;
        const cx = seat(xEdges, X.inv(x)), cy = seat(yEdges, Y.inv(y));
        const xWord = n.xKind === "time" ? `${F.whenText(xEdges[cx])} to ${F.whenText(xEdges[cx + 1])}`
          : `${N().formatValue(xEdges[cx], n.xUnit)} to ${N().formatValue(xEdges[cx + 1], n.xUnit)}`;
        const yWord = (i) => (buckets ? buckets.yTicks.words[i] : N().formatValue(yEdges[i], opts.unit));
        return { lines: [[x, box.top, x, box.bottom], [box.left, y, box.right, y]],
                 text: `${xWord}; ${yWord(cy)} to ${yWord(cy + 1)}: ${counts[cx][cy] ?? "no count"}` };
      };
      const notes = o.palette === "diverging" ? [{ text: `paper is the average occupied cell (${mean.toFixed(1)})` }] : [];
      return { paint, pick, notes, entries: result.series.length > 1 ? result.series.map((x) => ({ key: x.key, name: x.name, colour: x.colour, off: off.has(x.key) })) : [],
               model: { counts, xEdges, yEdges, top, total: flat.reduce((a, b) => a + b, 0), centre, at: [0, 1, top].map(at) } };
    });
  }

  registerPlotForm("heatmap", { label: "Heatmap", group: "distribution",
    needs: { x: ["time", "query", "field"], text: "points to count across X and Y" }, draw: drawHeatmap,
    shapes: { points: {}, distribution: { form: ["bins"], over_time: true } },
    reshape: "plot one numeric field of the items against another, or ask for a histogram's buckets by le", options: [
      { key: "y_bins", label: "Y bins", type: "number", min: 2, max: 60, step: 1, default: "auto", auto: true },
      { key: "scale", label: "Colour scale", type: "choice", choices: ["linear", "log"], default: "linear" },
      { key: "palette", label: "Palette", type: "choice", choices: ["sequential", "diverging"], default: "sequential" },
      { key: "empty", label: "Empty cells", type: "choice", choices: ["blank", "zero"], default: "blank" },
    ] });
})();
