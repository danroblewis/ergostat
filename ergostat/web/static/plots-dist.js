/* the forms that show a distribution: a histogram, whose bars touch because its X is continuous, and a box plot, with
   a named whisker rule and an optional violin of the same values */
"use strict";

(() => {
  const F = plotFrame, M = plotMath, N = () => panelNumbers;

  function binned(result, o, off) {
    const shown = result.series.filter((x) => !off.has(x.key));
    if (result.shape === "bins") {
      const out = shown.map((x) => ({ one: x, counts: x.values.map((v) => v ?? 0), edges: result.x?.edges || M.edgesFromX(x.xs, x.values.length) }));
      return { edges: out[0]?.edges || [0, 1], rows: out, given: true };
    }
    const all = shown.flatMap((x) => M.finite(x.values));
    const bins = o.bins === "auto" || o.bins == null ? M.autoBins(all) : Math.max(1, Math.round(+o.bins));
    const edges = M.edgesOver(all.length ? Math.min(...all) : 0, all.length ? Math.max(...all) : 1, bins);
    return { edges, rows: shown.map((x) => ({ one: x, counts: M.countInto(x.values, edges), edges })), given: false };
  }

  function drawHistogram(target, first, config, opts) {
    const o = opts.options, d = config.display || {};
    return F.view(target, first, opts, (result, off) => {
      const { edges, rows } = binned(result, o, off);
      const shaped = rows.map((r) => M.shapeCounts(r.counts, edges, { normalize: o.normalize, cumulative: o.cumulative === "on" }));
      const stacked = o.stack === "stacked";
      const lows = shaped.map((r) => r.map(() => 0));
      const tops = shaped.map((r) => r.slice());
      if (stacked) for (let k = 1; k < shaped.length; k++) shaped[k].forEach((v, i) => { lows[k][i] = tops[k - 1][i]; tops[k][i] = lows[k][i] + v; });
      const word = o.cumulative === "on"
        ? (o.normalize === "percent" ? "Cumulative share (%)" : o.normalize === "density" ? "Cumulative proportion" : "Cumulative count")
        : (o.normalize === "percent" ? "Share (%)" : o.normalize === "density" ? "Density" : "Count");
      const xUnit = result.shape === "bins" ? N().parseUnit(result.x?.unit || "") : opts.unit;
      const q = (config.queries || []).find((c) => !c.hidden) || {};
      const xWord = d.x?.label || result.x?.label || q.label || q.field || q.series || "Value";
      const xTitle = F.titled(xWord, xUnit), plain = N().parseUnit("");
      const xr = F.range(edges, { ...d.x, log: false }, { pad: 0 });
      const yr = F.range(tops.flat(), { ...d.y, log: false }, { zero: true, pad: 0.06 });
      let hits = [];
      const paint = (ctx, w, ht) => {
        const plot = F.cartesian(ctx, w, ht, { xr, yr, xUnit, yUnit: plain, xTitle, yTitle: word });
        const { box, X, Y } = plot;
        hits = [];
        const overlay = rows.length > 1 && !stacked;
        F.clipTo(ctx, box, () => rows.forEach((r, k) => {
          ctx.fillStyle = F.alpha(r.one.colour, overlay ? 0.38 : 0.82);
          ctx.strokeStyle = F.ink("--bg"); ctx.lineWidth = 1;
          tops[k].forEach((top, i) => {
            const x0 = X.at(edges[i]), x1 = X.at(edges[i + 1]), y0 = Y.at(lows[k][i]), y1 = Y.at(top);
            if (top !== lows[k][i]) {
              ctx.fillRect(x0, y1, x1 - x0, y0 - y1);
              if (!overlay && x1 - x0 > 3) ctx.strokeRect(Math.round(x0) + 0.5, y1, Math.round(x1 - x0), y0 - y1);
            }
            hits.push({ x0, x1, y0, y1, px: (x0 + x1) / 2, py: y1, i, k, one: r.one, c: r.counts[i], shown: shaped[k][i] });
          });
          if (overlay) {
            ctx.strokeStyle = r.one.colour; ctx.lineWidth = 1.25; ctx.beginPath();
            tops[k].forEach((top, i) => { const y = Y.at(top); if (i) ctx.lineTo(X.at(edges[i]), y); else ctx.moveTo(X.at(edges[0]), y); ctx.lineTo(X.at(edges[i + 1]), y); });
            ctx.stroke();
          }
        }));
        plot.finish();
      };
      const pick = (x, y) => {
        const here = hits.filter((b) => x >= b.x0 && x < b.x1);
        if (!here.length) return null;
        const b = here.reduce((best, c) => (Math.abs(c.py - y) < Math.abs(best.py - y) ? c : best));
        const range = `${N().formatValue(edges[b.i], xUnit)} to ${N().formatValue(edges[b.i + 1], xUnit)}`;
        const tail = o.normalize === "count" && o.cumulative !== "on" ? "" : `, ${+b.shown.toPrecision(3)}`;
        return { marks: [{ x: b.px, y: b.py, colour: b.one.colour }], text: `${rows.length > 1 ? `${b.one.name}  ` : ""}${range}: ${b.c}${tail}` };
      };
      return { paint, pick, entries: result.series.map((x) => ({ key: x.key, name: x.name, colour: x.colour, off: off.has(x.key) })),
               model: { edges, counts: rows.map((r) => r.counts), shaped, tops } };
    });
  }

  const WHISKER_WORD = { tukey: "whiskers: furthest value within 1.5 IQR", "min-max": "whiskers: minimum and maximum", "p5-p95": "whiskers: 5th and 95th percentiles" };

  function drawBox(target, first, config, opts) {
    const o = opts.options, d = config.display || {};
    return F.view(target, first, opts, (result, off) => {
      const rows = result.series.filter((x) => !off.has(x.key)).map((one) => {
        const stats = one.box ? M.boxFrom(one.box, o.whiskers, one.values) : M.boxStats(one.values, o.whiskers);
        return { one, stats, shape: o.violin === "on" ? M.density(one.values) : null };
      }).filter((r) => r.stats);
      const horizontal = o.orientation === "horizontal";
      const all = rows.flatMap(({ stats: b }) => [b.lo, b.hi, b.q1, b.q3, ...(o.outliers === "off" ? [] : b.outliers)]);
      const vr = F.range(all, { ...(horizontal ? d.x : d.y) }, { pad: 0.06 });
      const n = F.names(result, config, opts.unit);
      const vTitle = F.titled(n.yWord, opts.unit);
      const value = (v) => N().formatValue(v, opts.unit);
      let hits = [];
      const paint = (ctx, w, ht) => {
        ctx.font = F.font();
        const catW = horizontal ? Math.min(w * 0.3, Math.ceil(Math.max(...rows.map((r) => ctx.measureText(r.one.name).width))) + 8) : 0;
        const probe = F.ticksOf(F.scale(vr.min, vr.max, ht - 34, 6, vr.log), "number", ht - 40, opts.unit, 34).words;
        const box = horizontal ? F.layout(ctx, w, ht, { left: catW, xTitle: vTitle }) : F.layout(ctx, w, ht, { yWords: probe, yTitle: vTitle, bottom: 22 });
        const V = horizontal ? F.scale(vr.min, vr.max, box.left, box.right, vr.log) : F.scale(vr.min, vr.max, box.bottom, box.top, vr.log);
        const vt = F.ticksOf(V, "number", horizontal ? box.width : box.height, opts.unit, horizontal ? 56 : 34);
        F.grid(ctx, box, horizontal ? V : null, horizontal ? null : V, horizontal ? vt : null, horizontal ? null : vt);
        const along = (horizontal ? box.height : box.width) / Math.max(1, rows.length);
        const P = (c, v) => (horizontal ? [V.at(v), c] : [c, V.at(v)]);
        const seg = (c0, v0, c1, v1) => { const [a, b] = P(c0, v0), [e, f] = P(c1, v1); F.line(ctx, a, b, e, f); };
        hits = [];
        F.clipTo(ctx, box, () => rows.forEach((r, k) => {
          const b = r.stats, mid = (horizontal ? box.top : box.left) + (k + 0.5) * along, half = Math.min(along * 0.3, 34), cap = half * 0.55;
          if (r.shape) {
            const top = Math.max(...r.shape.values) || 1;
            ctx.beginPath();
            r.shape.at.forEach((v, i) => { const [x, y] = P(mid - r.shape.values[i] / top * along * 0.44, v); if (i) ctx.lineTo(x, y); else ctx.moveTo(x, y); });
            [...r.shape.at].reverse().forEach((v, j) => { const i = r.shape.at.length - 1 - j; const [x, y] = P(mid + r.shape.values[i] / top * along * 0.44, v); ctx.lineTo(x, y); });
            ctx.closePath();
            ctx.fillStyle = F.alpha(r.one.colour, 0.2); ctx.fill();
          }
          const thin = r.shape ? Math.min(half, 7) : half, thinCap = r.shape ? thin : cap;
          ctx.strokeStyle = r.one.colour; ctx.lineWidth = 1.25;
          seg(mid, b.q3, mid, b.hi); seg(mid, b.q1, mid, b.lo);
          seg(mid - thinCap, b.hi, mid + thinCap, b.hi); seg(mid - thinCap, b.lo, mid + thinCap, b.lo);
          const [x0, y0] = P(mid - thin, b.q3), [x1, y1] = P(mid + thin, b.q1);
          ctx.fillStyle = F.alpha(r.one.colour, r.shape ? 0.55 : 0.22);
          ctx.fillRect(Math.min(x0, x1), Math.min(y0, y1), Math.abs(x1 - x0), Math.abs(y1 - y0));
          ctx.strokeRect(Math.min(x0, x1), Math.min(y0, y1), Math.abs(x1 - x0), Math.abs(y1 - y0));
          ctx.lineWidth = 2.5; seg(mid - thin, b.median, mid + thin, b.median); ctx.lineWidth = 1.25;
          if (o.outliers !== "off") for (const v of b.outliers) { const [x, y] = P(mid, v); ctx.beginPath(); ctx.arc(x, y, 2.75, 0, 7); ctx.stroke(); }
          const [px, py] = P(mid, b.median);
          hits.push({ px, py, r, low: (horizontal ? box.top : box.left) + k * along, high: (horizontal ? box.top : box.left) + (k + 1) * along });
        }));
        if (horizontal) F.xAxis(ctx, box, V, vt, vTitle); else { F.yAxis(ctx, box, V, vt, vTitle); F.line(ctx, box.left, Math.round(box.bottom) + 0.5, box.right, Math.round(box.bottom) + 0.5); }
        ctx.fillStyle = F.ink("--muted");
        const fit = (text, room) => { let c = text; while (c.length > 1 && ctx.measureText(`${c}…`).width > room) c = c.slice(0, -1); return ctx.measureText(text).width <= room ? text : `${c}…`; };
        if (horizontal) {
          ctx.textAlign = "right"; ctx.textBaseline = "middle";
          F.line(ctx, Math.round(box.left) + 0.5, box.top, Math.round(box.left) + 0.5, box.bottom);
          rows.forEach((r, k) => ctx.fillText(fit(r.one.name, catW - 6), box.left - 4, box.top + (k + 0.5) * along));
        } else {
          ctx.textAlign = "center"; ctx.textBaseline = "top";
          rows.forEach((r, k) => ctx.fillText(fit(r.one.name, along - 4), box.left + (k + 0.5) * along, box.bottom + 4));
        }
      };
      const pick = (x, y) => {
        const at = horizontal ? y : x, hit = hits.find((c) => at >= c.low && at < c.high);
        if (!hit) return null;
        const b = hit.r.stats;
        return { marks: [{ x: hit.px, y: hit.py, colour: hit.r.one.colour }],
                 text: `${hit.r.one.name}  median ${value(b.median)}, Q1 ${value(b.q1)}, Q3 ${value(b.q3)}${b.n ? `, n ${b.n}` : ""}` };
      };
      const anyGiven = rows.some((r) => r.one.box && r.one.box.p5 == null);
      const unsent = rows.reduce((a, r) => a + (o.outliers === "off" ? 0 : r.stats.outliers_more || 0), 0);
      const notes = [{ mark: F.svgLine({ "stroke-width": 3 }), text: "median" }, { mark: (m) => m.append(s("rect", { x: 2, y: 1, width: 12, height: 8, fill: "none", stroke: "currentColor" })), text: "box: Q1 to Q3" },
                     { mark: F.svgLine({}), text: anyGiven ? "whiskers as given" : WHISKER_WORD[o.whiskers] }];
      if (o.outliers !== "off" && o.whiskers !== "min-max") notes.push({ mark: F.svgDot({ fill: "none", r: 2.75 }), text: "beyond the whiskers" });
      if (unsent) notes.push({ text: `${unsent} nearer outliers not drawn` });
      if (o.outliers !== "off" && rows.some((r) => r.stats.sampled)) notes.push({ text: "outliers from a sample of the values" });
      if (o.violin === "on") notes.push({ text: "shape: kernel density, cut at the data's range" });
      return { paint, pick, notes, entries: result.series.map((x) => ({ key: x.key, name: x.name, colour: x.colour, off: off.has(x.key) })),
               model: { boxes: rows.map((r) => ({ name: r.one.name, ...r.stats })) } };
    });
  }

  const onOff = (key, label, first = "off") => ({ key, label, type: "choice", choices: first === "off" ? ["off", "on"] : ["on", "off"], default: first });
  registerPlotForm("histogram", { label: "Histogram", group: "distribution", needs: { x: ["bins", "time"], text: "a binned X, or a measure over time" }, draw: drawHistogram,
    ask: (q, o) => (q.x?.type === "bins" && o.bins !== "auto" ? { ...q, x: { ...q.x, bins: Math.max(1, Math.round(+o.bins)) } } : q), options: [
    { key: "bins", label: "Bins", type: "number", min: 1, max: 200, step: 1, default: "auto", auto: true },
    onOff("cumulative", "Cumulative"),
    { key: "normalize", label: "Height shows", type: "choice", choices: ["count", "percent", "density"], default: "count" },
    { key: "stack", label: "Several series", type: "choice", choices: ["none", "stacked"], default: "none" },
  ] });
  registerPlotForm("box", { label: "Box plot", group: "distribution", needs: { x: ["category", "time", "field", "query"], text: "a numeric field of items by category, or a measure over time" }, draw: drawBox,
    /* a numeric field of items is drawn item by item, one box per category: the answer's spread, never an aggregate of it */
    ask: (q) => {
      const type = q.x?.type || "time";
      if (q.source !== "items" || !q.field || (type !== "time" && type !== "category")) return q;
      const { transform, rate_per, window: w, group_by, ...rest } = q;
      return { ...rest, x: { type: "category", by: type === "category" ? q.x.by : group_by || "state" }, agg: "none" };
    },
    check: (r) => (r.shape === "category" && !r.x?.distribution ? "A box plot needs many values per category: choose a numeric field of items." : ""),
    options: [
    { key: "whiskers", label: "Whiskers", type: "choice", choices: ["tukey", "min-max", "p5-p95"], default: "tukey" },
    onOff("outliers", "Outliers", "on"),
    { key: "orientation", label: "Orientation", type: "choice", choices: ["vertical", "horizontal"], default: "vertical" },
    onOff("violin", "Violin"),
  ] });
})();
