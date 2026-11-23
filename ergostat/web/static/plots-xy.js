/* the forms that draw points against a numeric or time X: a line whose X the time plot cannot draw, a scatter, and a
   phase portrait, whose order in time is the point of it */
"use strict";

(() => {
  const F = plotFrame, N = () => panelNumbers;
  const num = (v) => (v == null ? "–" : Math.abs(v) >= 1000 || (v !== 0 && Math.abs(v) < 0.01) ? v.toPrecision(3) : String(+v.toFixed(3)));

  /* monotone cubic through the points (Fritsch and Carlson): it never overshoots, so a smoothed line invents no peak */
  function smooth(pts) {
    if (pts.length < 3) return pts;
    const n = pts.length, d = [], m = new Array(n).fill(0);
    for (let i = 0; i < n - 1; i++) d.push((pts[i + 1][1] - pts[i][1]) / ((pts[i + 1][0] - pts[i][0]) || 1));
    m[0] = d[0]; m[n - 1] = d[n - 2];
    for (let i = 1; i < n - 1; i++) m[i] = d[i - 1] * d[i] <= 0 ? 0 : (d[i - 1] + d[i]) / 2;
    for (let i = 0; i < n - 1; i++) {
      if (d[i] === 0) { m[i] = 0; m[i + 1] = 0; continue; }
      const a = m[i] / d[i], b = m[i + 1] / d[i], r = a * a + b * b;
      if (r > 9) { const k = 3 / Math.sqrt(r); m[i] = k * a * d[i]; m[i + 1] = k * b * d[i]; }
    }
    const out = [];
    for (let i = 0; i < n - 1; i++) {
      const [x0, y0] = pts[i], [x1, y1] = pts[i + 1], w = x1 - x0;
      for (let k = 0; k < 8; k++) {
        const t = k / 8, t2 = t * t, t3 = t2 * t;
        out.push([x0 + w * t, (2 * t3 - 3 * t2 + 1) * y0 + (t3 - 2 * t2 + t) * w * m[i] + (-2 * t3 + 3 * t2) * y1 + (t3 - t2) * w * m[i + 1]]);
      }
    }
    out.push(pts[n - 1]);
    return out;
  }
  /* the drawn outline of a run of points in a style, as a polyline, so stroke and fill always agree */
  function trace(pts, style) {
    if (style === "smooth") return smooth(pts);
    if (!style.startsWith("step-")) return pts;
    const out = [pts[0]];
    for (let i = 1; i < pts.length; i++) {
      const [x0, y0] = pts[i - 1], [x1, y1] = pts[i];
      if (style === "step-after") out.push([x1, y0]);
      else if (style === "step-before") out.push([x0, y1]);
      else { const mid = (x0 + x1) / 2; out.push([mid, y0], [mid, y1]); }
      out.push([x1, y1]);
    }
    return out;
  }
  const polyline = (ctx, pts) => { pts.forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y))); };
  const runsOf = (rows) => {
    const runs = [];
    let cur = null;
    for (const r of rows) { if (r == null) { cur = null; continue; } if (!cur) runs.push(cur = []); cur.push(r); }
    return runs;
  };

  /* every series on the union of their Xs, so stacking adds values at the same X */
  function aligned(series) {
    const xs = [...new Set(series.flatMap((x) => x.xs.filter((v) => v != null)))].sort((a, b) => a - b);
    const at = new Map(xs.map((x, i) => [x, i]));
    const rows = series.map((x) => {
      const row = new Array(xs.length).fill(null);
      x.xs.forEach((v, i) => { if (v != null && x.values[i] != null) row[at.get(v)] = x.values[i]; });
      return row;
    });
    return { xs, rows };
  }

  function drawLine(target, first, config, opts) {
    const o = opts.options, d = config.display || {};
    return F.view(target, first, opts, (result, off) => {
      const shown = result.series.filter((x) => !off.has(x.key));
      const { xs, rows: raw } = aligned(shown);
      let rows = raw.map((r) => r.map((v) => (v == null && o.nulls === "zero" ? 0 : v)));
      const stacking = o.stack !== "none", percent = o.stack === "percent";
      if (percent) {
        const totals = xs.map((_, i) => rows.reduce((a, r) => a + Math.abs(r[i] ?? 0), 0));
        rows = rows.map((r) => r.map((v, i) => (v == null ? null : totals[i] ? v / totals[i] * 100 : 0)));
      }
      const lower = rows.map((r) => r.map(() => 0));
      if (stacking) {
        const run = xs.map(() => 0);
        rows = rows.map((r, k) => r.map((v, i) => { lower[k][i] = run[i]; if (v == null) return null; run[i] += v; return run[i]; }));
      }
      const n = F.names(result, config, percent ? N().parseUnit("%") : opts.unit);
      const yUnit = percent ? N().parseUnit("%") : opts.unit;
      const xr = F.range(xs, d.x, { pad: 0 });
      const yr = percent ? { min: 0, max: 100, log: false } : F.range(rows.flat(), d.y, { zero: o.fill !== "none" || stacking });
      const model = { xs, rows };
      let hits = [], plot = null;
      const paint = (ctx, w, ht) => {
        plot = F.cartesian(ctx, w, ht, { xr, yr, xKind: n.xKind, xUnit: n.xUnit, yUnit, xTitle: n.xTitle, yTitle: n.yTitle });
        const { box, X, Y } = plot;
        hits = [];
        F.clipTo(ctx, box, () => shown.forEach((one, k) => {
          const pixel = (v, i) => (v == null || (yr.log && v <= 0) || (xr.log && xs[i] <= 0) ? null : [X.at(xs[i]), Y.at(v)]);
          const present = rows[k].map(pixel);
          const runs = o.nulls === "connect" ? [present.filter(Boolean)] : runsOf(present);
          for (const run of runs) {
            if (!run.length) continue;
            const top = trace(run, o.style);
            if (o.fill !== "none") {
              ctx.beginPath(); polyline(ctx, top);
              if (stacking) {
                const under = run.map(([x]) => { const i = present.findIndex((p) => p && p[0] === x); return [x, Y.at(lower[k][i])]; });
                polyline2(ctx, trace(under, o.style).reverse());
              } else { ctx.lineTo(top[top.length - 1][0], Y.at(Math.max(yr.min, 0))); ctx.lineTo(top[0][0], Y.at(Math.max(yr.min, 0))); }
              ctx.closePath();
              if (o.fill === "gradient") {
                const g = ctx.createLinearGradient(0, box.top, 0, box.bottom);
                g.addColorStop(0, F.alpha(one.colour, 0.55)); g.addColorStop(1, F.alpha(one.colour, 0.04));
                ctx.fillStyle = g;
              } else ctx.fillStyle = F.alpha(one.colour, stacking ? 0.65 : 0.18);
              ctx.fill();
            }
            ctx.beginPath(); polyline(ctx, top);
            ctx.strokeStyle = one.colour; ctx.lineWidth = o.width ?? 1.5; ctx.lineJoin = "round"; ctx.stroke();
            if (o.points === "always" || (o.points === "auto" && run.length <= 24)) {
              ctx.fillStyle = one.colour;
              for (const [x, y] of run) { ctx.beginPath(); ctx.arc(x, y, 2.5, 0, 7); ctx.fill(); }
            }
          }
          rows[k].forEach((v, i) => { const p = present[i]; if (p) hits.push({ px: p[0], py: p[1], x: xs[i], y: raw[k][i], one }); });
        }));
        plot.finish();
      };
      const polyline2 = (ctx, pts) => pts.forEach(([x, y]) => ctx.lineTo(x, y));
      const pick = (x, y) => {
        const p = F.nearest(hits, x, y, 60);
        if (!p || !plot) return null;
        const xText = n.xKind === "time" ? F.whenText(p.x) : N().formatValue(p.x, n.xUnit);
        return { lines: [[p.px, plot.box.top, p.px, plot.box.bottom]], marks: [{ x: p.px, y: p.py, colour: p.one.colour }],
                 text: `${xText}  ${p.one.name} ${N().formatValue(p.y, opts.unit)}` };
      };
      return { paint, pick, model, entries: result.series.map((x) => ({ key: x.key, name: x.name, colour: x.colour, off: off.has(x.key) })) };
    });
  }

  /* a bubble's AREA is proportional to its value, the reading the eye makes */
  function radii(values, fixed) {
    const known = plotMath.finite(values).map(Math.abs);
    if (!known.length) return values.map(() => fixed);
    const top = Math.max(...known) || 1;
    return values.map((v) => (v == null ? 2 : Math.max(2, 14 * Math.sqrt(Math.abs(v) / top))));
  }
  
  function drawScatter(target, first, config, opts) {
    const o = opts.options, d = config.display || {};
    return F.view(target, first, opts, (result, off) => {
      const shown = result.series.filter((x) => !off.has(x.key));
      const n = F.names(result, config, opts.unit);
      const usable = (x, y) => x != null && y != null && (!d.x?.log || x > 0) && (!d.y?.log || y > 0);
      const allX = shown.flatMap((x) => x.xs), allY = shown.flatMap((x) => x.values);
      const room = typeof o.size === "string" && !/^\d/.test(o.size) ? 0.12 : 0.05;       // a bubble is not cut by the frame
      const xr = F.range(allX, d.x, { pad: room }), yr = F.range(allY, d.y, { pad: room });
      const bySize = typeof o.size === "string" && !/^\d/.test(o.size) && shown.some((x) => x.sizes) ? o.size : null;
      const fixed = bySize ? 4 : +o.size || 4;
      const groupBy = o.color_by && o.color_by !== "series" && shown.some((x) => x.colors) ? o.color_by : null;
      const groups = new Map();
      if (groupBy) for (const one of shown) for (const g of one.colors || []) if (!groups.has(g)) groups.set(g, groups.size);
      const groupInk = (g) => F.ink(`--g${[0, 1, 5, 9, 4, 2, 6, 7][groups.get(g) % 8]}`);
      const fits = o.trend === "linear" ? shown.map((one) => ({ one, fit: plotMath.linearFit(one.xs, one.values) })) : [];
      let hits = [], plot = null;
      const paint = (ctx, w, ht) => {
        plot = F.cartesian(ctx, w, ht, { xr, yr, xKind: n.xKind, xUnit: n.xUnit, yUnit: opts.unit, xTitle: n.xTitle, yTitle: n.yTitle });
        const { box, X, Y } = plot;
        hits = [];
        F.clipTo(ctx, box, () => {
          for (const one of shown) {
            const sizes = bySize ? one.sizes : null, rs = sizes ? radii(sizes, fixed) : null, tags = groupBy ? one.colors : null;
            ctx.globalAlpha = o.opacity ?? 0.7;
            one.xs.forEach((x, i) => {
              const y = one.values[i];
              if (!usable(x, y)) return;
              const px = X.at(x), py = Y.at(y), r = rs ? rs[i] : fixed;
              ctx.fillStyle = tags ? groupInk(tags[i]) : one.colour;
              ctx.beginPath(); ctx.arc(px, py, r, 0, 7); ctx.fill();
              hits.push({ px, py, x, y, one, i, size: sizes?.[i] });
            });
            ctx.globalAlpha = 1;
          }
          for (const { one, fit } of fits) {
            if (!fit) continue;
            ctx.strokeStyle = one.colour; ctx.lineWidth = 1.5; ctx.setLineDash([6, 4]);
            ctx.beginPath();
            for (let k = 0; k <= 40; k++) {
              const x = X.inv(box.left + box.width * k / 40), y = fit.slope * x + fit.intercept;
              if (Y.log && y <= 0) continue;
              if (k) ctx.lineTo(X.at(x), Y.at(y)); else ctx.moveTo(X.at(x), Y.at(y));
            }
            ctx.stroke(); ctx.setLineDash([]);
          }
        });
        plot.finish();
      };
      const pick = (x, y) => {
        const p = F.nearest(hits, x, y, 30);
        if (!p) return null;
        const xText = n.xKind === "time" ? F.whenText(p.x) : N().formatValue(p.x, n.xUnit);
        const id = p.one.ids?.[p.i];
        return { marks: [{ x: p.px, y: p.py, colour: p.one.colour }],
                 text: `${id ? `${id}  ` : ""}${xText}, ${N().formatValue(p.y, opts.unit)}${p.size != null ? `, ${bySize} ${num(p.size)}` : ""}` };
      };
      const notes = fits.filter((x) => x.fit).map(({ one, fit }) => ({ mark: F.svgLine({ "stroke-dasharray": "4 2" }),
        text: `${shown.length > 1 ? `${one.name}: ` : ""}least squares, slope ${num(fit.slope)}, R² ${fit.r2.toFixed(2)}` }));
      if (bySize) notes.push({ mark: F.svgDot({}), text: `area shows ${bySize}` });
      const entries = groupBy ? [...groups.keys()].map((g) => ({ key: `g:${g}`, name: String(g), colour: groupInk(g) }))
        : result.series.map((x) => ({ key: x.key, name: x.name, colour: x.colour, off: off.has(x.key) }));
      return { paint, pick, entries, notes, model: { fits: fits.map((x) => x.fit), bySize, groups: [...groups.keys()] } };
    });
  }

  /* a chevron at the middle of each stretch of screen length, pointing the way time runs */
  function chevrons(ctx, pts, colour, every = 64) {
    let walked = every / 2, count = 0;
    ctx.strokeStyle = colour; ctx.lineWidth = 1.5; ctx.lineJoin = "round"; ctx.lineCap = "round";
    for (let i = 1; i < pts.length; i++) {
      const [x0, y0] = pts[i - 1], [x1, y1] = pts[i], len = Math.hypot(x1 - x0, y1 - y0);
      if (!len) continue;
      while (walked <= len) {
        const t = walked / len, x = x0 + (x1 - x0) * t, y = y0 + (y1 - y0) * t, a = Math.atan2(y1 - y0, x1 - x0), r = 5.5;
        ctx.beginPath();
        ctx.moveTo(x - r * Math.cos(a - 0.5), y - r * Math.sin(a - 0.5));
        ctx.lineTo(x, y);
        ctx.lineTo(x - r * Math.cos(a + 0.5), y - r * Math.sin(a + 0.5));
        ctx.stroke();
        count++;
        walked += every;
      }
      walked -= len;
    }
    ctx.lineCap = "butt";
    return count;
  }

  function drawPhase(target, first, config, opts) {
    const o = opts.options, d = config.display || {};
    return F.view(target, first, opts, (result, off) => {
      const shown = result.series.filter((x) => !off.has(x.key));
      const n = F.names(result, config, opts.unit);
      const ordered = shown.map((one) => {
        const idx = one.xs.map((_, i) => i);
        if (one.times) idx.sort((a, b) => one.times[a] - one.times[b]);
        return { one, order: idx };
      });
      const xr = F.range(shown.flatMap((x) => x.xs), d.x), yr = F.range(shown.flatMap((x) => x.values), d.y);
      const model = { order: ordered.map((x) => x.order), marks: 0, start: null, end: null };
      let hits = [];
      const paint = (ctx, w, ht) => {
        const plot = F.cartesian(ctx, w, ht, { xr, yr, xUnit: n.xUnit, yUnit: opts.unit, xTitle: n.xTitle, yTitle: n.yTitle });
        const { box, X, Y } = plot;
        hits = [];
        model.marks = 0;
        F.clipTo(ctx, box, () => {
          for (const { one, order } of ordered) {
            const pts = order.map((i) => (one.xs[i] == null || one.values[i] == null || (X.log && one.xs[i] <= 0) || (Y.log && one.values[i] <= 0)
              ? null : { px: X.at(one.xs[i]), py: Y.at(one.values[i]), x: one.xs[i], y: one.values[i], t: one.times?.[i], one }));
            const known = pts.filter(Boolean), total = Math.max(1, pts.length - 1);
            hits.push(...known);
            ctx.lineCap = "round";
            for (let k = 1; k < pts.length; k++) {
              if (!pts[k] || !pts[k - 1]) continue;
              const age = o.fade === "off" ? 1 : k / total;
              ctx.strokeStyle = F.alpha(one.colour, o.fade === "off" ? 0.9 : 0.16 + 0.84 * age ** 1.6);
              ctx.lineWidth = o.fade === "off" ? 1.5 : 1 + 1.25 * age;
              F.line(ctx, pts[k - 1].px, pts[k - 1].py, pts[k].px, pts[k].py);
            }
            ctx.lineCap = "butt";
            if (o.direction !== "off") for (const run of runsOf(pts)) model.marks += chevrons(ctx, run.map((p) => [p.px, p.py]), one.colour);
            if (o.markers !== "off" && known.length) {
              const a = known[0], z = known[known.length - 1];
              ctx.lineWidth = 2; ctx.strokeStyle = one.colour; ctx.fillStyle = F.ink("--bg");
              ctx.beginPath(); ctx.arc(a.px, a.py, 4.5, 0, 7); ctx.fill(); ctx.stroke();
              ctx.fillStyle = one.colour;
              ctx.beginPath(); ctx.arc(z.px, z.py, 5, 0, 7); ctx.fill();
              ctx.strokeStyle = F.ink("--bg"); ctx.lineWidth = 1.5;
              ctx.beginPath(); ctx.arc(z.px, z.py, 5, 0, 7); ctx.stroke();
              model.start = { x: a.x, y: a.y, px: a.px, py: a.py }; model.end = { x: z.x, y: z.y, px: z.px, py: z.py };
            }
          }
        });
        plot.finish();
      };
      const pick = (x, y) => {
        const p = F.nearest(hits, x, y, 30);
        if (!p) return null;
        return { marks: [{ x: p.px, y: p.py, colour: p.one.colour }],
                 text: `${p.t ? `${F.whenText(p.t)}  ` : ""}${N().formatValue(p.x, n.xUnit)}, ${N().formatValue(p.y, opts.unit)}` };
      };
      const firstKnown = (one, order, dir) => { const l = dir > 0 ? order : [...order].reverse(); const i = l.find((j) => one.xs[j] != null && one.values[j] != null); return one.times?.[i]; };
      const notes = [];
      if (o.markers !== "off" && ordered.length === 1) {
        const { one, order } = ordered[0];
        notes.push({ mark: F.svgDot({ fill: "none" }), text: `start ${F.whenText(firstKnown(one, order, 1)) || "(first point)"}` });
        notes.push({ mark: F.svgDot({}), text: `end ${F.whenText(firstKnown(one, order, -1)) || "(last point)"}` });
      } else if (o.markers !== "off") notes.push({ mark: F.svgDot({ fill: "none" }), text: "open: start, filled: end" });
      if (o.direction !== "off") notes.push({ mark: (m) => m.append(s("path", { d: "M5 1 L11 5 L5 9", fill: "none", stroke: "currentColor", "stroke-width": 1.5 })), text: "direction of time" });
      if (o.fade !== "off") notes.push({ mark: F.svgLine({}), text: "stronger is more recent" });
      return { paint, pick, model, notes, entries: result.series.map((x) => ({ key: x.key, name: x.name, colour: x.colour, off: off.has(x.key) })) };
    });
  }

  registerPlotForm("line", { draw: drawLine });
  registerPlotForm("scatter", { label: "Scatter", group: "relationship", needs: { x: ["field", "query", "time"], text: "two measures, or two fields of each item" }, draw: drawScatter,
    /* a bubble's size and a point's colour come from the items, so they are asked for with the X */
    ask: (q, o) => {
      if (q.x?.type !== "field") return q;
      const x = { ...q.x };
      if (typeof o.size === "string" && !/^\d/.test(o.size)) x.size = o.size;
      if (o.color_by && o.color_by !== "series") x.color_by = o.color_by;
      return { ...q, x };
    },
    options: [
    { key: "size", label: "Point size or field", type: "field", numeric: true, default: 4 },
    { key: "opacity", label: "Opacity", type: "number", min: 0.1, max: 1, step: 0.1, default: 0.7 },
    { key: "trend", label: "Trend line", type: "choice", choices: ["none", "linear"], default: "none" },
    { key: "color_by", label: "Colour by", type: "field", extra: ["series"], default: "series" },
  ] });
  registerPlotForm("phase", { label: "Phase portrait", group: "dynamics", needs: { x: ["query"], text: "two measures, paired in time" }, draw: drawPhase,
    check: (r) => (r.series.some((x) => x.xs.filter((v, i) => v != null && x.values[i] != null).length >= 2) ? "" : "A phase portrait needs at least two points in time."),
    options: [
      { key: "direction", label: "Direction marks", type: "choice", choices: ["on", "off"], default: "on" },
      { key: "fade", label: "Fade older points", type: "choice", choices: ["on", "off"], default: "on" },
      { key: "markers", label: "Start and end", type: "choice", choices: ["on", "off"], default: "on" },
    ] });
  window.plotTrace = trace;
})();
