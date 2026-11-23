/* a bar chart the time plot cannot draw: horizontal, sorted, with values, or over categories. The values are read in a
   margin of their own, beside the bars and never on the plot */
"use strict";

(() => {
  const F = plotFrame, N = () => panelNumbers;
  const MANY_TIMES = 24;

  /* categories and one row per series. A long time series has no categories of its own, so each series is one bar, its latest value */
  function tableOf(result, o) {
    const series = result.series;
    if (result.shape === "time") {
      const n = series[0]?.xs.length || 0;
      if (o.orientation === "horizontal" || o.sort !== "none" || n > MANY_TIMES) {
        const last = (x) => { for (let i = x.values.length - 1; i >= 0; i--) if (x.values[i] != null) return x.values[i]; return null; };
        return { cats: series.map((x) => x.name), rows: [series.map(last)], series: [{ key: "latest", name: "Latest value", colour: series[0].colour }],
                 colours: series.map((x) => x.colour), latest: true };
      }
      const when = (t) => new Date(t * 1000).toLocaleTimeString([], { hour12: false, hour: "2-digit", minute: "2-digit" });
      return { cats: series[0].xs.map(when), rows: series.map((x) => x.values), series };
    }
    const cats = [...new Set(series.flatMap((x) => x.xs))];
    const at = new Map(cats.map((c, i) => [c, i]));
    const rows = series.map((x) => { const r = new Array(cats.length).fill(null); x.xs.forEach((c, i) => { r[at.get(c)] = x.values[i]; }); return r; });
    return { cats: cats.map((c) => (typeof c === "number" ? N().formatValue(c, N().parseUnit(result.x?.unit || "")) : String(c))), rows, series };
  }
  function ordering(t, o) {
    const idx = t.cats.map((_, i) => i);
    if (o.sort === "none") return idx;
    const total = (i) => t.rows.reduce((a, r) => a + (r[i] ?? 0), 0);
    const sign = o.sort === "value-desc" ? -1 : 1;
    return idx.sort((a, b) => sign * (total(a) - total(b)) || a - b);
  }

  function drawBar(target, first, config, opts) {
    const o = opts.options, d = config.display || {};
    return F.view(target, first, opts, (result, off) => {
      const t = tableOf(result, o);
      const live = t.series.map((x, k) => ({ x, k })).filter(({ x }) => !off.has(x.key));
      const order = ordering(t, o);
      const horizontal = o.orientation === "horizontal", stacked = o.stack !== "none", percent = o.stack === "percent";
      const unit = percent ? N().parseUnit("%") : opts.unit;
      const shareOf = (k, i) => {
        const v = t.rows[k][i];
        if (v == null || !percent) return v;
        const all = live.reduce((a, l) => a + Math.abs(t.rows[l.k][i] ?? 0), 0);
        return all ? v / all * 100 : 0;
      };
      const bars = [], extent = [0];
      for (const i of order) {
        let up = 0, down = 0;
        for (const { k } of live) {
          const v = shareOf(k, i);
          if (v == null) continue;
          if (stacked) { const from = v >= 0 ? up : down; if (v >= 0) up += v; else down += v; bars.push({ i, k, from, to: from + v, v: t.rows[k][i] }); extent.push(from + v); }
          else { bars.push({ i, k, from: 0, to: v, v: t.rows[k][i] }); extent.push(v); }
        }
      }
      const asked = horizontal ? d.x : d.y;
      const vr = percent ? { min: 0, max: 100, log: false } : F.range(extent, { ...asked, log: false }, { pad: 0.04, zero: true });
      const n = F.names(result, config, unit);
      const vTitle = F.titled(n.yWord, unit), cTitle = d.x?.label && !horizontal ? d.x.label : result.x?.label || "";
      const lanes = stacked || o.grouping === "overlaid" ? 1 : Math.max(1, live.length);
      const laneOf = (k) => (lanes === 1 ? 0 : live.findIndex((l) => l.k === k));
      const value = (v) => N().formatValue(v, opts.unit);
      const labelled = order.map((i) => {
        if (stacked) return { i, v: t.rows.reduce((a, r, k) => (off.has(t.series[k].key) ? a : a + (r[i] ?? 0)), 0) };
        return { i, v: live.length === 1 ? t.rows[live[0].k][i] : null };
      });
      let hits = [], frameBox = null;
      const colourOf = (b) => (t.colours ? t.colours[b.i] : t.series[b.k].colour);
      const paint = (ctx, w, ht) => {
        ctx.font = F.font();
        const showValues = o.values === "on";
        const gutter = showValues && horizontal ? Math.ceil(Math.max(0, ...labelled.map((l) => (l.v == null ? 0 : ctx.measureText(value(l.v)).width)))) + 8 : 0;
        const catW = horizontal ? Math.min(w * 0.34, Math.ceil(Math.max(...t.cats.map((c) => ctx.measureText(c).width))) + 8) : 0;
        const box = horizontal
          ? F.layout(ctx, w, ht, { left: catW + (cTitle ? 16 : 0), xTitle: vTitle, right: 10 + gutter })
          : (() => {
            const Y0 = F.scale(vr.min, vr.max, ht - 34, 6);
            const yw = F.ticksOf(Y0, "number", ht - 40, unit, 34).words;
            return F.layout(ctx, w, ht, { yWords: yw, yTitle: vTitle, xTitle: cTitle, top: showValues ? 18 : 6 });
          })();
        frameBox = box;
        const V = horizontal ? F.scale(vr.min, vr.max, box.left, box.right) : F.scale(vr.min, vr.max, box.bottom, box.top);
        const vt = F.ticksOf(V, "number", horizontal ? box.width : box.height, unit, horizontal ? 56 : 34);
        const along = (horizontal ? box.height : box.width) / Math.max(1, order.length);
        const place = new Map(order.map((i, r) => [i, r]));
        F.grid(ctx, box, horizontal ? V : null, horizontal ? null : V, horizontal ? vt : null, horizontal ? null : vt);
        hits = [];
        F.clipTo(ctx, box, () => {
          for (const b of bars) {
            const r = place.get(b.i), gap = Math.min(along * 0.22, 6), inner = along - gap, size = Math.max(1, inner / lanes - (lanes > 1 ? 1 : 0));
            const start = (horizontal ? box.top : box.left) + r * along + gap / 2 + laneOf(b.k) * (inner / lanes);
            const a = V.at(b.from), z = V.at(b.to);
            const rect = horizontal ? [Math.min(a, z), start, Math.max(1, Math.abs(z - a)), size] : [start, Math.min(a, z), size, Math.max(1, Math.abs(z - a))];
            ctx.fillStyle = o.grouping === "overlaid" && !stacked && live.length > 1 ? F.alpha(colourOf(b), 0.55) : colourOf(b);
            ctx.fillRect(...rect);
            hits.push({ b, rect, px: rect[0] + rect[2] / 2, py: rect[1] + rect[3] / 2 });
          }
        });
        ctx.strokeStyle = F.ink("--line-strong");
        if (horizontal) F.line(ctx, Math.round(V.at(Math.max(vr.min, 0))) + 0.5, box.top, Math.round(V.at(Math.max(vr.min, 0))) + 0.5, box.bottom);
        else F.line(ctx, box.left, Math.round(V.at(Math.max(vr.min, 0))) + 0.5, box.right, Math.round(V.at(Math.max(vr.min, 0))) + 0.5);
        ctx.fillStyle = F.ink("--muted");
        const fit = (text, room) => {
          if (ctx.measureText(text).width <= room) return text;
          let cut = text;
          while (cut.length > 1 && ctx.measureText(`${cut}…`).width > room) cut = cut.slice(0, -1);
          return `${cut}…`;
        };
        if (horizontal) {
          F.xAxis(ctx, box, V, vt, vTitle);
          ctx.textAlign = "right"; ctx.textBaseline = "middle";
          const every = Math.ceil(13 / along);
          order.forEach((i, r) => { if (r % every === 0) ctx.fillText(fit(t.cats[i], catW - 6), box.left - 4, box.top + (r + 0.5) * along); });
          F.line(ctx, Math.round(box.left) + 0.5, box.top, Math.round(box.left) + 0.5, box.bottom);
          if (cTitle) { ctx.save(); ctx.translate(7, (box.top + box.bottom) / 2); ctx.rotate(-Math.PI / 2); ctx.textAlign = "center"; ctx.fillText(cTitle, 0, 0, box.height); ctx.restore(); }
          if (showValues) { ctx.textAlign = "left"; labelled.forEach((l, r) => { if (l.v != null && r % every === 0) ctx.fillText(value(l.v), box.right + 4, box.top + (r + 0.5) * along); }); }
        } else {
          F.yAxis(ctx, box, V, vt, vTitle);
          F.line(ctx, box.left, Math.round(box.bottom) + 0.5, box.right, Math.round(box.bottom) + 0.5);
          ctx.textAlign = "center"; ctx.textBaseline = "top";
          const widest = Math.max(...t.cats.map((c) => ctx.measureText(c).width));
          const every = along >= 30 || widest + 8 <= along ? 1 : Math.ceil(30 / along);   // a category is cut short before it is left out
          order.forEach((i, r) => { if (r % every === 0) ctx.fillText(fit(t.cats[i], along * every - 4), box.left + (r + 0.5) * along, box.bottom + 4); });
          if (cTitle) ctx.fillText(cTitle, (box.left + box.right) / 2, box.bottom + 18, box.width);
          if (showValues) {
            ctx.textBaseline = "alphabetic";
            const room = Math.max(...labelled.map((l) => (l.v == null ? 0 : ctx.measureText(value(l.v)).width))) + 6;
            const skip = Math.max(1, Math.ceil(room / along));
            labelled.forEach((l, r) => { if (l.v != null && r % skip === 0) ctx.fillText(value(l.v), box.left + (r + 0.5) * along, box.top - 5); });
          }
        }
      };
      const pick = (x, y) => {
        const hit = hits.find(({ rect: [a, b, c, e] }) => x >= a - 1 && x <= a + c + 1 && y >= b - 1 && y <= b + e + 1);
        if (!hit || !frameBox) return null;
        const b = hit.b;
        return { marks: [{ x: hit.px, y: hit.py, colour: colourOf(b) }],
                 text: `${t.cats[b.i]}${t.latest ? "" : `  ${t.series[b.k].name}`} ${value(b.v)}${percent ? ` (${(b.to - b.from).toFixed(1)}%)` : ""}` };
      };
      const entries = t.colours ? t.cats.map((c, i) => ({ key: `c:${i}`, name: c, colour: t.colours[i] }))
        : t.series.map((x) => ({ key: x.key, name: x.name, colour: x.colour, off: off.has(x.key) }));
      return { paint, pick, entries, notes: t.latest ? [{ text: "latest value of each series" }] : [],
               model: { order: order.map((i) => t.cats[i]), bars: bars.map((b) => ({ cat: t.cats[b.i], from: b.from, to: b.to })), horizontal, lanes } };
    });
  }
  registerPlotForm("bar", { draw: drawBar });
})();
