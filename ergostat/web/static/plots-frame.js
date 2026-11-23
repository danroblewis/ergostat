/* what every drawn chart form shares: a canvas that follows its box, a second canvas holding only the cursor, scales,
   axes with their names and units, and a legend beside the plot. Every colour is read from the design tokens at
   each paint, so a change of theme is a repaint */
"use strict";

const plotFrame = (() => {
  const ink = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  const SUP = { "-": "⁻", 0: "⁰", 1: "¹", 2: "²", 3: "³", 4: "⁴", 5: "⁵", 6: "⁶", 7: "⁷", 8: "⁸", 9: "⁹" };
  const power = (v) => `10${String(Math.round(Math.log10(v))).replace(/./g, (c) => SUP[c])}`;
  const TIME_TICKS = [60, 120, 300, 600, 900, 1800, 3600, 7200, 10800, 21600, 43200, 86400, 172800, 604800, 2592000];
  const font = () => `${ink("--canvas-sm")} ${ink("--font")}`;

  function mix(a, b, share) {
    const part = (hex, i) => parseInt(hex.slice(i, i + 2), 16);
    return "#" + [1, 3, 5].map((i) => Math.round(part(a, i) * share + part(b, i) * (1 - share)).toString(16).padStart(2, "0")).join("");
  }
  const alpha = (hex, a) => `${hex}${Math.round(Math.max(0, Math.min(1, a)) * 255).toString(16).padStart(2, "0")}`;

  function scale(d0, d1, r0, r1, log = false) {
    const f = log ? Math.log10 : (v) => v, g = log ? (v) => 10 ** v : (v) => v;
    const a = f(d0), b = f(d1), span = b - a || 1;
    return { d0, d1, r0, r1, log, at: (v) => r0 + (f(v) - a) / span * (r1 - r0), inv: (p) => g(a + (p - r0) / (r1 - r0) * span) };
  }
  /* a range from the data and what the panel asked for; a log axis keeps to positive values */
  function range(values, asked = {}, { pad = 0.05, zero = false } = {}) {
    const log = !!asked.log;
    const xs = plotMath.finite(values).filter((v) => !log || v > 0);
    let lo = xs.length ? Math.min(...xs) : log ? 1 : 0, hi = xs.length ? Math.max(...xs) : log ? 10 : 1;
    if (zero && !log) { lo = Math.min(lo, 0); hi = Math.max(hi, 0); }
    if (lo === hi) { const d = log ? lo * 0.5 : Math.abs(lo) * 0.1 || 1; lo -= d; hi += d; }
    if (log) { const k = (hi / lo) ** pad; lo = zero ? lo : lo / k; hi *= k; }
    else { const d = (hi - lo) * pad; lo = zero && lo === 0 ? 0 : lo - d; hi = zero && hi === 0 ? 0 : hi + d; }
    const min = asked.min != null && (!log || asked.min > 0) ? asked.min : lo;
    const max = asked.max != null && (!log || asked.max > 0) ? asked.max : hi;
    return { min, max: max > min ? max : min + (Math.abs(min) || 1), log };
  }
  const spaced = (ticks, sc, gap) => {
    let last = -Infinity;
    const dir = sc.r1 >= sc.r0 ? 1 : -1;
    return ticks.filter((t) => { const p = sc.at(t) * dir; if (p - last < gap) return false; last = p; return true; });
  };
  /* ticks and their words for an axis: time, decades, or plain numbers in the unit's own steps */
  function ticksOf(sc, kind, px, unit, gap) {
    const count = Math.max(2, Math.floor(px / gap));
    if (kind === "time") {
      const ticks = plotMath.linearTicks(sc.d0, sc.d1, count, TIME_TICKS);
      const span = sc.d1 - sc.d0;
      const text = (t) => {
        const d = new Date(t * 1000);
        return span > 172800 ? d.toLocaleDateString([], { month: "short", day: "numeric" })
          : d.toLocaleTimeString([], { hour12: false, hour: "2-digit", minute: "2-digit" });
      };
      return { major: ticks, minor: [], words: ticks.map(text) };
    }
    if (sc.log) {
      const { major, minor } = plotMath.logTicks(sc.d0, sc.d1);
      if (major.length >= 2) {
        const kept = spaced(major, sc, Math.min(gap, 34));
        return { major: kept, minor: Math.log10(sc.d1 / sc.d0) <= 6 ? minor : [], words: kept.map(power) };
      }
      const fine = spaced([...major, ...minor].sort((a, b) => a - b), sc, gap);
      return { major: fine, minor: [], words: panelNumbers.axisLabels(fine, unit, true) };
    }
    const major = plotMath.linearTicks(sc.d0, sc.d1, count, unit?.kind === "dur" ? panelNumbers.durationSteps.map((x) => x / unit.mult) : null);
    return { major, minor: [], words: panelNumbers.axisLabels(major, unit || panelNumbers.parseUnit("")) };
  }
  const titled = (word, unit) => {
    const chip = unit ? panelNumbers.chipOf(unit) : "";
    return word && chip ? `${word} (${chip})` : word || (chip ? `(${chip})` : "");
  };

  /* the plot's box: room for the y ticks and the two axis names, the rest for the data */
  function layout(ctx, w, h, { yWords = [], xTitle = "", yTitle = "", right = 10, top = 6, bottom = null, left = null }) {
    ctx.font = font();
    const widest = Math.max(0, ...yWords.map((t) => ctx.measureText(t).width));
    const l = left ?? Math.ceil(widest) + 8 + (yTitle ? 16 : 0);
    const b = bottom ?? 18 + (xTitle ? 15 : 0);
    return { left: l, top, right: Math.max(l + 20, w - right), bottom: Math.max(top + 20, h - b),
             get width() { return this.right - this.left; }, get height() { return this.bottom - this.top; } };
  }
  const line = (ctx, x0, y0, x1, y1) => { ctx.beginPath(); ctx.moveTo(x0, y0); ctx.lineTo(x1, y1); ctx.stroke(); };
  const crisp = (v) => Math.round(v) + 0.5;

  function grid(ctx, box, X, Y, xt, yt) {
    ctx.save();
    ctx.lineWidth = 1;
    ctx.strokeStyle = ink("--fill");
    for (const t of xt?.minor || []) line(ctx, crisp(X.at(t)), box.top, crisp(X.at(t)), box.bottom);
    for (const t of yt?.minor || []) line(ctx, box.left, crisp(Y.at(t)), box.right, crisp(Y.at(t)));
    ctx.strokeStyle = ink("--line");
    for (const t of xt?.major || []) line(ctx, crisp(X.at(t)), box.top, crisp(X.at(t)), box.bottom);
    for (const t of yt?.major || []) line(ctx, box.left, crisp(Y.at(t)), box.right, crisp(Y.at(t)));
    ctx.restore();
  }
  function xAxis(ctx, box, X, xt, title, { words = true } = {}) {
    ctx.save();
    ctx.font = font(); ctx.fillStyle = ink("--muted"); ctx.strokeStyle = ink("--line-strong");
    line(ctx, box.left, crisp(box.bottom), box.right, crisp(box.bottom));
    if (words) {
      ctx.textBaseline = "top";
      let edge = -Infinity;
      xt.major.forEach((t, i) => {
        const p = X.at(t), w = ctx.measureText(xt.words[i]).width;
        const at = Math.max(box.left - 4 + w / 2, Math.min(box.right + 6 - w / 2, p));
        if (at - w / 2 < edge + 6) return;
        ctx.textAlign = "center";
        ctx.fillText(xt.words[i], at, box.bottom + 4);
        edge = at + w / 2;
      });
      if (title) { ctx.textAlign = "center"; ctx.fillText(title, (box.left + box.right) / 2, box.bottom + 18, box.width); }
    }
    ctx.restore();
  }
  function yAxis(ctx, box, Y, yt, title) {
    ctx.save();
    ctx.font = font(); ctx.fillStyle = ink("--muted"); ctx.strokeStyle = ink("--line-strong");
    line(ctx, crisp(box.left), box.top, crisp(box.left), box.bottom);
    ctx.textAlign = "right"; ctx.textBaseline = "middle";
    yt.major.forEach((t, i) => ctx.fillText(yt.words[i], box.left - 4, Math.max(box.top + 5, Math.min(box.bottom - 5, Y.at(t)))));
    if (title) {
      ctx.translate(7, (box.top + box.bottom) / 2);
      ctx.rotate(-Math.PI / 2);
      ctx.textAlign = "center"; ctx.textBaseline = "middle";
      ctx.fillText(title, 0, 0, box.height);
    }
    ctx.restore();
  }
  const clipTo = (ctx, box, fn) => { ctx.save(); ctx.beginPath(); ctx.rect(box.left, box.top, box.width, box.height); ctx.clip(); fn(); ctx.restore(); };

  /* the canvas pair. paint(ctx, w, h) draws the chart; pick(x, y) says what the cursor is on, as
     {x, y, lines, marks, text}, and is drawn on the upper canvas alone */
  function create(target, { paint, pick, readout }) {
    const root = h("div", { class: "plot-frame" });
    const base = h("canvas", { class: "plot-base" }), over = h("canvas", { class: "plot-cursor" });
    root.append(base, over);
    target.append(root);
    let w = 0, ht = 0, alive = true;
    const size = (c) => {
      const d = devicePixelRatio || 1;
      c.width = Math.round(w * d); c.height = Math.round(ht * d);
      const ctx = c.getContext("2d");
      ctx.setTransform(d, 0, 0, d, 0, 0);
      return ctx;
    };
    const frame = {
      root, base, over, paints: 0,
      redraw() {
        if (!alive || !w || !ht) return;
        const ctx = size(base);
        size(over);
        paint(ctx, w, ht);
        frame.paints++;
      },
      destroy() { alive = false; watch.disconnect(); root.remove(); },
    };
    const watch = new ResizeObserver(() => {
      const nw = Math.floor(root.clientWidth), nh = Math.floor(root.clientHeight);
      if (nw === w && nh === ht) return;
      w = nw; ht = nh;
      frame.redraw();
    });
    watch.observe(root);
    const clear = () => { over.getContext("2d").clearRect(0, 0, w, ht); };
    over.addEventListener("pointermove", (e) => {
      const r = over.getBoundingClientRect(), hit = pick?.(e.clientX - r.left, e.clientY - r.top);
      clear();
      if (!hit) { readout?.(""); return; }
      const ctx = over.getContext("2d");
      ctx.save();
      ctx.strokeStyle = ink("--muted"); ctx.lineWidth = 1; ctx.setLineDash([3, 3]);
      for (const [x0, y0, x1, y1] of hit.lines || []) line(ctx, crisp(x0), crisp(y0), crisp(x1), crisp(y1));
      ctx.setLineDash([]);
      for (const m of hit.marks || []) {
        ctx.beginPath(); ctx.arc(m.x, m.y, 4, 0, Math.PI * 2);
        ctx.fillStyle = ink("--bg"); ctx.fill();
        ctx.strokeStyle = m.colour || ink("--ink"); ctx.lineWidth = 2; ctx.stroke();
      }
      ctx.restore();
      readout?.(hit.text || "");
    });
    over.addEventListener("pointerleave", () => { clear(); readout?.(""); });
    return frame;
  }

  /* the legend beside the plot: a button for each series that can be turned off, and what each mark means */
  function legend(el, entries, notes, onToggle) {
    if (!el) return;
    const list = h("div", { class: "plot-legend" });
    for (const e of entries) {
      const swatch = h("i", { class: "panel-swatch" });
      swatch.style.setProperty("--swatch", e.colour);
      const word = h("span", { class: "panel-series-name" }, e.name);
      const value = e.value ? h("span", { class: "plot-legend-value" }, e.value) : null;
      if (onToggle) {
        list.append(h("button", { type: "button", class: `panel-series plot-legend-row${e.off ? " off" : ""}`, "aria-pressed": String(!e.off),
                                  title: `${e.off ? "Show" : "Hide"} ${e.name}`, onclick: () => onToggle(e.key) }, swatch, word, value));
      } else list.append(h("div", { class: "plot-legend-row" }, swatch, word, value));
    }
    for (const n of notes || []) {
      const mark = s("svg", { class: "plot-legend-mark", viewBox: "0 0 16 10", "aria-hidden": "true" });
      n.mark?.(mark);
      list.append(h("div", { class: "plot-legend-note" }, mark, h("span", {}, n.text)));
    }
    el.replaceChildren(list);
  }
  const svgLine = (attrs) => (m) => m.append(s("line", { x1: 1, y1: 5, x2: 15, y2: 5, stroke: "currentColor", "stroke-width": 1.5, ...attrs }));
  const svgDot = (attrs) => (m) => m.append(s("circle", { cx: 8, cy: 5, r: 3.5, stroke: "currentColor", "stroke-width": 1.5, fill: "currentColor", ...attrs }));

  /* a chart form's life: build(result, off) says how to paint and what the cursor reads; a refresh repaints the same
     canvases, and turning a series off in the legend rebuilds from the same answer */
  function view(target, first, opts, build) {
    const off = new Set();
    let result = first, built = null;
    const frame = create(target, {
      paint: (ctx, w, ht) => built.paint(ctx, w, ht),
      pick: (x, y) => built.pick?.(x, y),
      readout: opts.readout,
    });
    frame.base.setAttribute("role", "img");
    if (opts.label) frame.base.setAttribute("aria-label", opts.label);
    frame.over.setAttribute("aria-hidden", "true");
    const rebuild = () => {
      built = build(result, off);
      legend(opts.legend, built.entries || [], built.notes || [], built.entries?.length > 1 ? (key) => {
        if (off.has(key)) off.delete(key); else off.add(key);
        rebuild();
      } : null);
      frame.redraw();
    };
    rebuild();
    return { update(next) { result = next; rebuild(); }, destroy() { frame.destroy(); }, model: () => built.model || {}, frame };
  }
  /* axes for two numeric or time scales, with grid; what each form draws goes inside the box this returns */
  function cartesian(ctx, w, ht, { xr, yr, xKind = "number", xUnit, yUnit, xTitle, yTitle, right = 10, top = 6, equal = false, yTicks = null }) {
    let yScale = scale(yr.min, yr.max, ht - 34, top, yr.log);
    let yt = yTicks || ticksOf(yScale, "number", ht - 40, yUnit, 34);    // yTicks: {major, minor, words} the form chose
    const box = layout(ctx, w, ht, { yWords: yt.words, xTitle, yTitle, right, top });
    let X = scale(xr.min, xr.max, box.left, box.right, xr.log);
    let Y = scale(yr.min, yr.max, box.bottom, box.top, yr.log);
    if (equal) {
      const per = Math.max((xr.max - xr.min) / box.width, (yr.max - yr.min) / box.height);
      const cx = (xr.min + xr.max) / 2, cy = (yr.min + yr.max) / 2;
      X = scale(cx - per * box.width / 2, cx + per * box.width / 2, box.left, box.right);
      Y = scale(cy - per * box.height / 2, cy + per * box.height / 2, box.bottom, box.top);
    }
    yt = yTicks || ticksOf(Y, "number", box.height, yUnit, 34);
    let xt = ticksOf(X, xKind, box.width, xUnit, 56);
    if (equal) {                                         // one unit, one tick spacing, on both axes
      const step = plotMath.niceStep((X.d1 - X.d0) / box.width * 56, 1);   // at least 56 px apart, on the shorter axis too
      const every = (sc) => { const out = []; for (let k = Math.ceil(sc.d0 / step); k * step <= sc.d1; k++) out.push(+(k * step).toPrecision(12)); return out; };
      const said = (major, unit) => ({ major, minor: [], words: panelNumbers.axisLabels(major, unit || panelNumbers.parseUnit("")) });
      xt = said(every(X), xUnit);
      yt = said(every(Y), yUnit);
    }
    grid(ctx, box, X, Y, xt, yt);
    return { box, X, Y, xt, yt, finish() { xAxis(ctx, box, X, xt, xTitle); yAxis(ctx, box, Y, yt, yTitle); } };
  }
  /* the axis names: what the panel asked for, else what the answer calls its X and what the query measures */
  function names(result, config, unit) {
    const d = config.display || {}, x = result.x || {};
    const q = (config.queries || []).find((c) => !c.hidden) || {};
    const xUnit = panelNumbers.parseUnit(x.unit || "");
    const yWord = d.y?.label || q.label || q.field || q.series || q.measure || q.type || "";
    return { xUnit, xKind: x.type === "time" || !x.type ? "time" : "number",
             xTitle: titled(d.x?.label || x.label || (x.type === "time" || !x.type ? "Time" : ""), xUnit),
             yTitle: titled(yWord, unit), yWord };
  }
  const nearest = (points, x, y, limit = 40) => {
    let best = null, gap = limit * limit;
    for (const p of points) { const d = (p.px - x) ** 2 + (p.py - y) ** 2; if (d < gap) { gap = d; best = p; } }
    return best;
  };
  const whenText = (t) => (t == null ? "" : new Date(t * 1000).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false }));

  return { view, cartesian, names, nearest, whenText, ink, mix, alpha, scale, range, ticksOf, titled, layout, grid, xAxis, yAxis, clipTo, create, legend, line, power, svgLine, svgDot, font };
})();
