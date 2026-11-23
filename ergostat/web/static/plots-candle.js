/* a candlestick chart: each bucket's open, high, low and close, as candles, OHLC bars or hollow candles, with an
   optional pane of counts under the prices on the same time axis */
"use strict";

(() => {
  const F = plotFrame, N = () => panelNumbers;

  /* hollow candles carry two facts: filled means it closed below its open, and the colour says against the previous close */
  function candlesOf(one, times) {
    const out = [];
    let before = null;
    times.forEach((t, i) => {
      const [open, high, low, close] = [one.open[i], one.high[i], one.low[i], one.close[i]];
      if (open == null || high == null || low == null || close == null) return;
      out.push({ t, i, open, high, low, close, count: one.count?.[i] ?? null, up: close >= open, risen: before == null ? close >= open : close >= before });
      before = close;
    });
    return out;
  }

  function drawCandles(target, first, config, opts) {
    const o = opts.options, d = config.display || {};
    return F.view(target, first, opts, (result, off) => {
      const one = result.series.find((x) => !off.has(x.key) && x.open) || result.series.find((x) => x.open);
      const times = one.times || one.xs;
      const candles = candlesOf(one, times);
      const step = result.step || result.meta?.step || (times.length > 1 ? times[1] - times[0] : 60);
      const xr = { min: (result.meta?.since ?? times[0]) - step * 0.1, max: (result.meta?.until ?? times[times.length - 1]) + step, log: false };
      const yr = F.range(candles.flatMap((c) => [c.low, c.high]), { ...d.y }, { pad: 0.05 });
      const n = F.names(result, config, opts.unit);
      const volume = o.volume === "on" && candles.some((c) => c.count != null);
      const topCount = Math.max(1, ...candles.map((c) => c.count ?? 0));
      const goodUp = o.up_is !== "bad";
      const inkOf = (rising) => F.ink(rising === goodUp ? "--g2" : "--g3");
      let hits = [], price = null, pane = null;
      const paint = (ctx, w, ht) => {
        const paneH = volume ? Math.max(36, Math.round(ht * 0.24)) : 0;
        const plotH = ht - paneH - (volume ? 6 : 0);
        const probe = F.ticksOf(F.scale(yr.min, yr.max, plotH - 34, 6, yr.log), "number", plotH - 40, opts.unit, 34).words;
        const countWords = volume ? N().axisLabels([topCount], N().parseUnit("")) : [];
        const box = F.layout(ctx, w, plotH + (volume ? 0 : 0), { yWords: [...probe, ...countWords], yTitle: n.yTitle, xTitle: volume ? "" : n.xTitle, bottom: volume ? 4 : null });
        const X = F.scale(xr.min, xr.max, box.left, box.right);
        const Y = F.scale(yr.min, yr.max, box.bottom, box.top, yr.log);
        const xt = F.ticksOf(X, "time", box.width, null, 76), yt = F.ticksOf(Y, "number", box.height, opts.unit, 34);
        F.grid(ctx, box, X, Y, xt, yt);
        price = { box, X, Y };
        hits = [];
        const full = Math.abs(X.at(xr.min + step) - X.at(xr.min));
        const body = Math.max(1, Math.min(14, full * 0.68));
        F.clipTo(ctx, box, () => {
          for (const c of candles) {
            const cx = Math.round(X.at(c.t + step / 2)) + 0.5, yo = Y.at(c.open), yc = Y.at(c.close), yh = Y.at(c.high), yl = Y.at(c.low);
            const colour = inkOf(o.style === "hollow" ? c.risen : c.up);
            ctx.strokeStyle = colour; ctx.fillStyle = colour; ctx.lineWidth = 1;
            hits.push({ c, px: cx, py: yc, colour });
            if (o.style === "ohlc-bar") {
              const tick = Math.max(2, body / 2);
              F.line(ctx, cx, yh, cx, yl);
              F.line(ctx, cx - tick, Math.round(yo) + 0.5, cx, Math.round(yo) + 0.5);
              F.line(ctx, cx, Math.round(yc) + 0.5, cx + tick, Math.round(yc) + 0.5);
              continue;
            }
            const top = Math.min(yo, yc), bottom = Math.max(yo, yc), left = Math.round(cx - body / 2) + 0.5, wide = Math.max(1, Math.round(body) - 1);
            F.line(ctx, cx, yh, cx, top);
            F.line(ctx, cx, bottom, cx, yl);
            if (bottom - top < 1) { F.line(ctx, left, Math.round(top) + 0.5, left + wide, Math.round(top) + 0.5); continue; }
            if (o.style === "hollow" && c.up) { ctx.fillStyle = F.ink("--bg"); ctx.fillRect(left, top, wide, bottom - top); ctx.strokeRect(left, top, wide, bottom - top); }
            else { ctx.fillRect(left, top, wide, bottom - top); if (body > 3) ctx.strokeRect(left, top, wide, bottom - top); }
          }
        });
        F.yAxis(ctx, box, Y, yt, n.yTitle);
        if (volume) {
          F.xAxis(ctx, box, X, xt, "", { words: false });
          const low = { left: box.left, right: box.right, top: plotH + 6, bottom: ht - 33, get width() { return this.right - this.left; }, get height() { return this.bottom - this.top; } };
          const V = F.scale(0, topCount * 1.08, low.bottom, low.top);
          const vt = F.ticksOf(V, "number", low.height, N().parseUnit(""), 22);
          F.grid(ctx, low, X, V, xt, vt);
          F.clipTo(ctx, low, () => {
            for (const c of candles) {
              if (c.count == null) continue;
              const cx = Math.round(X.at(c.t + step / 2)), y = V.at(c.count);
              ctx.fillStyle = F.alpha(inkOf(o.style === "hollow" ? c.risen : c.up), 0.55);
              ctx.fillRect(Math.round(cx - body / 2), y, Math.max(1, Math.round(body)), low.bottom - y);
            }
          });
          F.xAxis(ctx, low, X, xt, n.xTitle);
          F.yAxis(ctx, low, V, vt, "Count");
          pane = { box: low, V };
        } else {
          F.xAxis(ctx, box, X, xt, n.xTitle);
          pane = null;
        }
      };
      const pick = (x) => {
        if (!hits.length || !price) return null;
        const hit = hits.reduce((a, b) => (Math.abs(b.px - x) < Math.abs(a.px - x) ? b : a));
        const v = (k) => N().formatValue(k, opts.unit), c = hit.c;
        const bottom = pane ? pane.box.bottom : price.box.bottom;
        return { lines: [[hit.px, price.box.top, hit.px, bottom]], marks: [{ x: hit.px, y: hit.py, colour: hit.colour }],
                 text: `${F.whenText(c.t)}  O ${v(c.open)} H ${v(c.high)} L ${v(c.low)} C ${v(c.close)}${c.count != null ? `  n ${c.count}` : ""}` };
      };
      const rise = { colour: inkOf(true), name: goodUp ? "Rise (good)" : "Rise (bad)" }, fall = { colour: inkOf(false), name: goodUp ? "Fall (bad)" : "Fall (good)" };
      const entries = result.series.length > 1 ? result.series.filter((x) => x.open).map((x) => ({ key: x.key, name: x.name, colour: x.colour, off: x !== one })) : [];
      const notes = [{ mark: (m) => { m.style.color = rise.colour; F.svgDot({})(m); }, text: rise.name }, { mark: (m) => { m.style.color = fall.colour; F.svgDot({})(m); }, text: fall.name }];
      if (o.style === "hollow") notes.push({ mark: F.svgDot({ fill: "none" }), text: "hollow: closed above its open; colour: against the last close" });
      if (o.style === "ohlc-bar") notes.push({ text: "left tick open, right tick close" });
      if (result.series.length > 1) notes.push({ text: `showing ${one.name}` });
      return { paint, pick, entries, notes, model: { candles, drawn: one.name, volume, step } };
    });
  }

  registerPlotForm("candlestick", { label: "Candlestick", group: "time",
    needs: { x: ["time"], agg: "ohlc", text: "open, high, low and close (aggregation ohlc)" }, draw: drawCandles,
    ask: (q) => ((q.source === "items" || q.source === "series") && (!q.x || q.x.type === "time") ? { ...q, agg: "ohlc", transform: "none" } : q),
    check: (r) => (r.series.some((x) => x.open) ? "" : "A candlestick chart needs open, high, low and close: set the query's aggregation to ohlc."),
    options: [
      { key: "style", label: "Style", type: "choice", choices: ["candle", "ohlc-bar", "hollow"], default: "candle" },
      { key: "volume", label: "Count pane", type: "choice", choices: ["off", "on"], default: "off" },
      { key: "up_is", label: "A rise is", type: "choice", choices: ["good", "bad"], default: "good" },
    ] });
})();
