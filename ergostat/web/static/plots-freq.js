/* frequency response as a control engineer reads it: a Bode plot (gain in dB over phase in degrees, one logarithmic
   frequency axis), a Nyquist plot (equal axes, the unit circle, the critical point -1, the way frequency rises) and a
   pole-zero map. An estimate where coherence is low is shown as unreliable, never quietly dropped */
"use strict";

(() => {
  const F = plotFrame, M = plotMath, N = () => panelNumbers;
  const COHERENCE_MIN = 0.6;
  const PLAIN = () => N().parseUnit("");
  const hzText = (v) => `${+v.toPrecision(3)} Hz`;

  function pointsOf(fr, mode) {
    const co = fr.coherence;
    const out = fr.hz.map((hz, i) => ({ i, hz, db: fr.magnitude_db?.[i] ?? null, deg: fr.phase_deg?.[i] ?? null, re: fr.re?.[i] ?? null, im: fr.im?.[i] ?? null,
                                        coh: co ? co[i] ?? null : null, low: !!co && mode !== "off" && (co[i] == null || co[i] < COHERENCE_MIN) }))
      .filter((p) => p.hz > 0).sort((a, b) => a.hz - b.hz);
    return out;
  }
  /* runs of neighbouring points that are alike in reliability, each sharing its end point so the curve has no holes */
  function stretches(pts, get) {
    const runs = [];
    let cur = null;
    pts.forEach((p, k) => {
      if (get(p) == null) { cur = null; return; }
      if (!cur || cur.low !== p.low) {
        const prev = pts[k - 1], next = { low: p.low, pts: prev && get(prev) != null ? [prev, p] : [p] };
        runs.push(next); cur = next;
      } else cur.pts.push(p);
    });
    return runs;
  }
  function stroke(ctx, run, X, Y, gx, gy, colour, shade) {
    ctx.strokeStyle = run.low ? F.alpha(colour, 0.6) : colour;
    ctx.lineWidth = run.low ? 1.25 : 1.75;
    ctx.setLineDash(run.low && shade ? [4, 3] : []);
    ctx.beginPath();
    run.pts.forEach((p, i) => { const x = X.at(gx(p)), y = Y.at(gy(p)); if (i) ctx.lineTo(x, y); else ctx.moveTo(x, y); });
    ctx.stroke();
    ctx.setLineDash([]);
  }
  /* each unreliable point owns the band to the midpoints (in log frequency) of its neighbours */
  function lowBands(pts) {
    const edge = (a, b) => Math.sqrt(a.hz * b.hz), bands = [];
    pts.forEach((p, k) => {
      if (!p.low) return;
      const lo = k ? edge(pts[k - 1], p) : p.hz, hi = k < pts.length - 1 ? edge(p, pts[k + 1]) : p.hz;
      const last = bands[bands.length - 1];
      if (last && last[1] === lo) last[1] = hi; else bands.push([lo, hi]);
    });
    return bands;
  }
  const lowNote = (pts, mode) => {
    const n = pts.filter((p) => p.low).length;
    if (!n || mode === "off") return [];
    return [{ mark: F.svgLine({ "stroke-dasharray": "4 2" }),
              text: mode === "hide-low" ? `${n} of ${pts.length} points hidden: coherence under ${COHERENCE_MIN}`
                : `dashed, shaded: unreliable, coherence under ${COHERENCE_MIN} (${n} of ${pts.length})` }];
  };
  const methodNote = (r) => ({ text: r.method === "model" ? `from the identified model${r.delay_seconds ? `, delay ${+r.delay_seconds.toPrecision(3)} s` : ""}` : `estimated from ${r.samples ?? "?"} samples (Welch)` });
  const readPoint = (p) => `${hzText(p.hz)}  ${p.db == null ? "–" : p.db.toFixed(1)} dB  ${p.deg == null ? "–" : p.deg.toFixed(1)}°${p.coh == null ? "" : `  coherence ${p.coh.toFixed(2)}`}${p.low ? " (unreliable)" : ""}`;

  function drawBode(target, first, config, opts) {
    const o = opts.options, d = config.display || {};
    return F.view(target, first, opts, (result) => {
      const all = pointsOf(result.frequency, o.coherence);
      const unwrapped = M.unwrapPhase(all.map((p) => p.deg), (k) => !all[k].low);
      all.forEach((p, k) => { p.deg = o.phase_wrap === "wrapped" ? M.wrapPhase(p.deg) : unwrapped[k]; });
      const pts = o.coherence === "hide-low" ? all.filter((p) => !p.low) : all;
      const hzs = pts.map((p) => p.hz);
      const xr = { min: d.x?.min > 0 ? d.x.min : Math.min(...hzs), max: d.x?.max > 0 ? d.x.max : Math.max(...hzs), log: true };
      if (xr.max <= xr.min) { xr.min /= 2; xr.max = xr.max * 2; }
      const dbs = M.finite(pts.map((p) => p.db)), degs = M.finite(pts.map((p) => p.deg));
      const dbR = F.range(dbs, { min: d.y?.min, max: d.y?.max }, { pad: 0.08 });
      const degR = o.phase_wrap === "wrapped" ? { min: -180, max: 180, log: false } : F.range(degs, {}, { pad: 0.08 });
      const dbSteps = [1, 2, 5, 10, 20, 40, 60, 80, 100], degSteps = [5, 15, 30, 45, 90, 180, 360];
      const xTitle = d.x?.label || "Frequency (Hz)";
      const model = { pts, bands: lowBands(pts), panes: null };
      let top = null, low = null;
      const paint = (ctx, w, ht) => {
        ctx.font = F.font();
        const tickAt = (r, a, b, steps, gap) => M.linearTicks(r.min, r.max, Math.max(2, Math.floor((b - a) / gap)), steps);
        const words = (ts, tail) => ts.map((t) => `${N().formatValue(t, PLAIN())}`.replace("-", "−") + tail);
        const gapMid = 8, lowH = 33, each = Math.max(30, (ht - 6 - gapMid - lowH) / 2);
        const dbTicks = tickAt(dbR, 0, each, dbSteps, 22), degTicks = tickAt(degR, 0, each, degSteps, 22);
        const dbWords = words(dbTicks, ""), degWords = words(degTicks, "°");
        const left = Math.ceil(Math.max(...[...dbWords, ...degWords].map((t) => ctx.measureText(t).width))) + 24;
        const pane = (a, b) => ({ left, right: Math.max(left + 20, w - 10), top: a, bottom: b, get width() { return this.right - this.left; }, get height() { return this.bottom - this.top; } });
        const upper = pane(6, 6 + each), lower = pane(6 + each + gapMid, 6 + each * 2 + gapMid);
        const X = F.scale(xr.min, xr.max, left, upper.right, true);
        const xt = F.ticksOf(X, "number", upper.width, PLAIN(), 56);
        const draw = (box, R, ticks, labels, title, special, get) => {
          const Y = F.scale(R.min, R.max, box.bottom, box.top);
          F.grid(ctx, box, X, Y, xt, { major: ticks, minor: [] });
          if (o.coherence === "shade") {
            ctx.fillStyle = F.ink("--warn-wash");
            for (const [a, b] of model.bands) ctx.fillRect(X.at(a), box.top, Math.max(1, X.at(b) - X.at(a)), box.height);
          }
          if (special >= R.min && special <= R.max) { ctx.strokeStyle = F.ink("--muted"); ctx.lineWidth = 1; F.line(ctx, box.left, Math.round(Y.at(special)) + 0.5, box.right, Math.round(Y.at(special)) + 0.5); }
          F.clipTo(ctx, box, () => {
            const wraps = o.phase_wrap === "wrapped" && get === gDeg;
            for (const run of stretches(pts, get)) {
              if (!wraps) { stroke(ctx, run, X, Y, (p) => p.hz, get, F.ink("--g0"), o.coherence === "shade"); continue; }
              let part = [run.pts[0]];
              for (let k = 1; k < run.pts.length; k++) {
                if (Math.abs(run.pts[k].deg - run.pts[k - 1].deg) > 180) { stroke(ctx, { ...run, pts: part }, X, Y, (p) => p.hz, get, F.ink("--g0"), o.coherence === "shade"); part = []; }
                part.push(run.pts[k]);
              }
              stroke(ctx, { ...run, pts: part }, X, Y, (p) => p.hz, get, F.ink("--g0"), o.coherence === "shade");
            }
          });
          ctx.strokeStyle = F.ink("--line-strong"); ctx.lineWidth = 1;
          F.line(ctx, Math.round(left) + 0.5, box.top, Math.round(left) + 0.5, box.bottom);
          F.line(ctx, left, Math.round(box.bottom) + 0.5, box.right, Math.round(box.bottom) + 0.5);
          ctx.fillStyle = F.ink("--muted"); ctx.textAlign = "right"; ctx.textBaseline = "middle";
          ticks.forEach((t, i) => ctx.fillText(labels[i], left - 4, Math.max(box.top + 5, Math.min(box.bottom - 5, Y.at(t)))));
          ctx.save(); ctx.translate(7, (box.top + box.bottom) / 2); ctx.rotate(-Math.PI / 2); ctx.textAlign = "center"; ctx.fillText(title, 0, 0, box.height); ctx.restore();
          return Y;
        };
        const gDb = (p) => p.db, gDeg = (p) => p.deg;
        const Ydb = draw(upper, dbR, dbTicks, dbWords, "Magnitude (dB)", 0, gDb);
        const Ydeg = draw(lower, degR, degTicks, degWords, "Phase (deg)", -180, gDeg);
        F.xAxis(ctx, lower, X, xt, xTitle);
        top = { box: upper, X, Y: Ydb }; low = { box: lower, X, Y: Ydeg };
        model.panes = { X: { min: X.d0, max: X.d1 }, decades: xt.major.length, upperBottom: upper.bottom, lowerTop: lower.top, left, right: upper.right };
      };
      const pick = (x) => {
        if (!top || x < top.box.left || x > top.box.right) return null;
        const hz = top.X.inv(x);
        const p = pts.reduce((a, b) => (Math.abs(Math.log(b.hz / hz)) < Math.abs(Math.log(a.hz / hz)) ? b : a));
        const px = top.X.at(p.hz), colour = F.ink("--g0"), marks = [];
        if (p.db != null) marks.push({ x: px, y: top.Y.at(p.db), colour });
        if (p.deg != null) marks.push({ x: px, y: low.Y.at(p.deg), colour });
        return { lines: [[px, top.box.top, px, low.box.bottom]], marks, text: readPoint(p) };
      };
      const notes = [methodNote(result), ...lowNote(all, o.coherence)];
      if (o.phase_wrap !== "wrapped") notes.push({ text: "phase unwrapped" });
      return { paint, pick, notes, model };
    });
  }

  /* the plane's limits around what must be seen; the frame then widens one axis so a unit is the same length on both */
  function planeRange(res, ims) {
    const pad = (a, b) => { const d = (b - a) * 0.08 || 0.5; return { min: a - d, max: b + d, log: false }; };
    return { xr: pad(Math.min(...res), Math.max(...res)), yr: pad(Math.min(...ims), Math.max(...ims)) };
  }
  function arrows(ctx, pts, X, Y, colour, every = 72) {
    const px = pts.map((p) => [X.at(p.re), Y.at(p.im)]);
    let walked = every * 0.6, count = 0;
    ctx.fillStyle = colour;
    for (let i = 1; i < px.length; i++) {
      const [x0, y0] = px[i - 1], [x1, y1] = px[i], len = Math.hypot(x1 - x0, y1 - y0);
      if (!len) continue;
      while (walked <= len) {
        const t = walked / len, x = x0 + (x1 - x0) * t, y = y0 + (y1 - y0) * t, a = Math.atan2(y1 - y0, x1 - x0), r = 7;
        ctx.beginPath();
        ctx.moveTo(x + r * 0.55 * Math.cos(a), y + r * 0.55 * Math.sin(a));
        ctx.lineTo(x - r * Math.cos(a - 0.45), y - r * Math.sin(a - 0.45));
        ctx.lineTo(x - r * Math.cos(a + 0.45), y - r * Math.sin(a + 0.45));
        ctx.closePath(); ctx.fill();
        count++;
        walked += every;
      }
      walked -= len;
    }
    return count;
  }
  function criticalPoint(ctx, X, Y) {
    const x = X.at(-1), y = Y.at(0), r = 5;
    ctx.strokeStyle = F.ink("--bad"); ctx.lineWidth = 2;
    F.line(ctx, x - r, y, x + r, y); F.line(ctx, x, y - r, x, y + r);
  }

  function drawNyquist(target, first, config, opts) {
    const o = opts.options;
    return F.view(target, first, opts, (result) => {
      const all = pointsOf(result.frequency, o.coherence).filter((p) => p.re != null && p.im != null);
      const pts = o.coherence === "hide-low" ? all.filter((p) => !p.low) : all;
      const res = [...pts.map((p) => p.re), -1, 0], ims = [...pts.flatMap((p) => (o.mirror === "on" ? [p.im, -p.im] : [p.im])), 0];
      if (o.unit_circle !== "off") { res.push(1); ims.push(-1, 1); }
      const { xr, yr } = planeRange(res, ims);
      const model = { pts, arrows: 0, perX: 0, perY: 0, minus1: null, circle: o.unit_circle !== "off", mirror: o.mirror === "on" };
      let hits = [];
      const paint = (ctx, w, ht) => {
        const plot = F.cartesian(ctx, w, ht, { xr, yr, xUnit: PLAIN(), yUnit: PLAIN(), xTitle: "Real axis, Re G", yTitle: "Imaginary axis, Im G", equal: true });
        const { box, X, Y } = plot, colour = F.ink("--g0");
        model.perX = Math.abs(X.at(1) - X.at(0)); model.perY = Math.abs(Y.at(1) - Y.at(0));
        model.minus1 = { x: X.at(-1), y: Y.at(0) };
        hits = [];
        F.clipTo(ctx, box, () => {
          ctx.strokeStyle = F.ink("--line-strong"); ctx.lineWidth = 1;
          if (X.d0 < 0 && X.d1 > 0) F.line(ctx, Math.round(X.at(0)) + 0.5, box.top, Math.round(X.at(0)) + 0.5, box.bottom);
          if (Y.d0 < 0 && Y.d1 > 0) F.line(ctx, box.left, Math.round(Y.at(0)) + 0.5, box.right, Math.round(Y.at(0)) + 0.5);
          if (o.unit_circle !== "off") {
            ctx.strokeStyle = F.ink("--muted"); ctx.setLineDash([2, 3]);
            ctx.beginPath(); ctx.arc(X.at(0), Y.at(0), model.perX, 0, Math.PI * 2); ctx.stroke(); ctx.setLineDash([]);
          }
          if (o.mirror === "on") {
            ctx.strokeStyle = F.alpha(colour, 0.4); ctx.lineWidth = 1; ctx.setLineDash([1.5, 3]); ctx.beginPath();
            pts.forEach((p, i) => { const x = X.at(p.re), y = Y.at(-p.im); if (i) ctx.lineTo(x, y); else ctx.moveTo(x, y); });
            ctx.stroke(); ctx.setLineDash([]);
          }
          for (const run of stretches(pts, (p) => p.re)) stroke(ctx, run, X, Y, (p) => p.re, (p) => p.im, colour, o.coherence === "shade");
          model.arrows = arrows(ctx, pts, X, Y, colour);
          if (pts.length) {
            const a = pts[0], z = pts[pts.length - 1];
            ctx.lineWidth = 2; ctx.strokeStyle = colour; ctx.fillStyle = F.ink("--bg");
            ctx.beginPath(); ctx.arc(X.at(a.re), Y.at(a.im), 4, 0, 7); ctx.fill(); ctx.stroke();
            ctx.fillStyle = colour; ctx.beginPath(); ctx.arc(X.at(z.re), Y.at(z.im), 4, 0, 7); ctx.fill();
          }
          criticalPoint(ctx, X, Y);
          hits = pts.map((p) => ({ px: X.at(p.re), py: Y.at(p.im), p }));
        });
        plot.finish();
      };
      const pick = (x, y) => {
        const hit = F.nearest(hits, x, y, 36);
        if (!hit) return null;
        return { marks: [{ x: hit.px, y: hit.py, colour: F.ink("--g0") }], text: `${readPoint(hit.p)}  (${hit.p.re.toFixed(3)}, ${hit.p.im.toFixed(3)}j)` };
      };
      const cross = (m) => { const c = F.ink("--bad"); m.append(s("path", { d: "M4 5 H12 M8 1 V9", stroke: c, "stroke-width": 2, fill: "none" })); };
      const notes = [{ mark: cross, text: "critical point −1" }];
      if (o.unit_circle !== "off") notes.push({ mark: F.svgLine({ "stroke-dasharray": "2 2" }), text: "unit circle, |G| = 1" });
      notes.push({ mark: (m) => m.append(s("path", { d: "M3 1 L13 5 L3 9 Z", fill: "currentColor" })), text: "frequency increasing" });
      notes.push({ mark: F.svgDot({ fill: "none" }), text: `lowest, ${pts.length ? hzText(pts[0].hz) : "–"}` });
      notes.push({ mark: F.svgDot({}), text: `highest, ${pts.length ? hzText(pts[pts.length - 1].hz) : "–"}` });
      if (o.mirror === "on") notes.push({ mark: F.svgLine({ "stroke-dasharray": "1 2" }), text: "mirror: negative frequencies" });
      notes.push(...lowNote(all, o.coherence), methodNote(result));
      return { paint, pick, notes, model };
    });
  }

  const complex = (z) => (Array.isArray(z) ? { re: z[0], im: z[1] ?? 0 } : { re: z.re, im: z.im ?? 0 });

  /* poles as crosses and zeros as circles, on the s-plane with its stable left half, or the z-plane with its unit circle */
  function drawPoleZero(target, first, config, opts) {
    return F.view(target, first, opts, (result) => {
      const poles = (result.poles || []).map(complex), zeros = (result.zeros || []).map(complex);
      const discrete = result.domain === "z";
      const res = [...poles, ...zeros].map((z) => z.re), ims = [...poles, ...zeros].map((z) => z.im);
      if (discrete) { res.push(-1, 1); ims.push(-1, 1); } else { res.push(0); ims.push(0); }
      const biggest = Math.max(1e-9, ...res.map(Math.abs), ...ims.map(Math.abs));
      if (!discrete) { res.push(biggest * 0.25); ims.push(biggest * 0.5, -biggest * 0.5); }
      const { xr, yr } = planeRange(res, ims);
      const model = { poles, zeros, perX: 0, perY: 0, discrete };
      let hits = [];
      const paint = (ctx, w, ht) => {
        const title = discrete ? ["Real axis", "Imaginary axis"] : ["Real axis, σ (1/s)", "Imaginary axis, jω (rad/s)"];
        const plot = F.cartesian(ctx, w, ht, { xr, yr, xUnit: PLAIN(), yUnit: PLAIN(), xTitle: title[0], yTitle: title[1], equal: true });
        const { box, X, Y } = plot, colour = F.ink("--g0");
        model.perX = Math.abs(X.at(1) - X.at(0)); model.perY = Math.abs(Y.at(1) - Y.at(0));
        F.clipTo(ctx, box, () => {
          ctx.strokeStyle = F.ink("--muted"); ctx.lineWidth = 1;
          if (discrete) { ctx.setLineDash([2, 3]); ctx.beginPath(); ctx.arc(X.at(0), Y.at(0), model.perX, 0, 7); ctx.stroke(); ctx.setLineDash([]); }
          else {
            ctx.fillStyle = F.ink("--bad-wash");
            ctx.fillRect(X.at(0), box.top, box.right - X.at(0), box.height);
            F.line(ctx, Math.round(X.at(0)) + 0.5, box.top, Math.round(X.at(0)) + 0.5, box.bottom);
          }
          ctx.strokeStyle = F.ink("--line-strong");
          if (Y.d0 < 0 && Y.d1 > 0) F.line(ctx, box.left, Math.round(Y.at(0)) + 0.5, box.right, Math.round(Y.at(0)) + 0.5);
          ctx.strokeStyle = colour; ctx.lineWidth = 2;
          hits = [];
          for (const z of zeros) { const x = X.at(z.re), y = Y.at(z.im); ctx.beginPath(); ctx.arc(x, y, 5, 0, 7); ctx.stroke(); hits.push({ px: x, py: y, z, word: "zero" }); }
          for (const z of poles) { const x = X.at(z.re), y = Y.at(z.im), r = 5; F.line(ctx, x - r, y - r, x + r, y + r); F.line(ctx, x - r, y + r, x + r, y - r); hits.push({ px: x, py: y, z, word: "pole" }); }
        });
        plot.finish();
      };
      const pick = (x, y) => {
        const hit = F.nearest(hits, x, y, 24);
        if (!hit) return null;
        const { re, im } = hit.z;
        return { marks: [{ x: hit.px, y: hit.py, colour: F.ink("--g0") }], text: `${hit.word} ${+re.toPrecision(4)}${im ? ` ${im < 0 ? "−" : "+"} ${Math.abs(+im.toPrecision(4))}j` : ""}` };
      };
      const notes = [{ mark: (m) => m.append(s("path", { d: "M4 1 L12 9 M4 9 L12 1", stroke: "currentColor", "stroke-width": 1.5 })), text: `pole (${poles.length})` },
                     { mark: F.svgDot({ fill: "none" }), text: `zero (${zeros.length})` },
                     { text: discrete ? "stable inside the unit circle" : "shaded: right half-plane, unstable" }, methodNote(result)];
      return { paint, pick, notes, model };
    });
  }

  const coherence = { key: "coherence", label: "Low coherence", type: "choice", choices: ["shade", "hide-low", "off"], default: "shade" };
  const frequency = (text) => ({ source: "frequency", text });
  registerPlotForm("bode", { label: "Bode plot", group: "dynamics", needs: frequency("a frequency response query"), draw: drawBode, options: [
    coherence,
    { key: "phase_wrap", label: "Phase", type: "choice", choices: ["unwrapped", "wrapped"], default: "unwrapped" },
  ] });
  registerPlotForm("nyquist", { label: "Nyquist plot", group: "dynamics", needs: frequency("a frequency response query"), draw: drawNyquist,
    check: (r) => (r.frequency?.re?.some((v) => v != null) ? "" : "This response has no real and imaginary parts to draw."),
    options: [
      { key: "unit_circle", label: "Unit circle", type: "choice", choices: ["on", "off"], default: "on" },
      { key: "mirror", label: "Negative frequencies", type: "choice", choices: ["off", "on"], default: "off" },
      coherence,
    ] });
  registerPlotForm("pole-zero", { label: "Pole-zero map", group: "dynamics", needs: { source: "frequency", data: "poles", text: "poles and zeros, from an identified model" }, draw: drawPoleZero,
    check: (r) => (r.poles?.length || r.zeros?.length ? "" : "Poles and zeros come only from an identified model's response."), options: [] });
})();
