/* behaviour over time, beside the model (docs/proposals/charts.md): the causes strip (a part, and what
   drives it), a loop's scope (r and y, u, e), an item kind's cumulative flow and cycle times. Drawn
   with uPlot (static/uplot), coloured only from the page's tokens; every chart in one place shares
   its cursor (a group), and covers the page's window */
"use strict";

const CHART_POINTS = 120;                                // buckets over the window (snapshot.py asks for the same)
const tok = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const PLOTS = new Set();

/* plots whose element is gone let go of their group; a chart is drawn once it has a width (a panel
   being built has none yet), and follows its width after */
function sweepPlots() { for (const p of PLOTS) if (!p.root.isConnected) { p.destroy(); PLOTS.delete(p); } }
function mountPlot(el, make) {
  sweepPlots();
  const ro = new ResizeObserver(() => {
    const w = Math.floor(el.clientWidth);
    if (!w) return;
    if (!el.plot) { el.plot = make(w); PLOTS.add(el.plot); }
    else if (Math.abs(el.plot.width - w) > 1) el.plot.setSize({ width: w, height: el.plot.height });
  });
  ro.observe(el);
}

/* a group of charts with one cursor, and one line saying the moment it is at */
function chartGroup(key) {
  const when = h("span", { class: "chart-when" });
  return { key: `${key}-${Math.random().toString(36).slice(2, 8)}`, when, at(t) { when.textContent = t == null ? "" : clockS(t); } };
}
const TIME_STEPS = [60, 120, 300, 600, 900, 1800, 3600, 7200, 10800, 21600, 43200, 86400, 172800, 604800];
const clockS = (t) => new Date(t * 1000).toLocaleTimeString([], { hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" });
const clockM = (t) => new Date(t * 1000).toLocaleTimeString([], { hour12: false, hour: "2-digit", minute: "2-digit" });

/* the options every chart shares: its window, its cursor (with its group), thin axes in the muted ink */
function baseOpts({ width, height, group, since, until, xAxis = true, yValues = null, yRange = null, hooks = {}, warp = null }) {
  const font = `${tok("--canvas-sm")} ${tok("--font")}`;
  const axis = { stroke: tok("--muted"), font, grid: { stroke: tok("--line"), width: 1 }, ticks: { show: false }, gap: 4 };
  return {
    width, height, padding: [6, 8, xAxis ? 0 : 6, 0], legend: { show: false },
    cursor: { sync: { key: group.key, setSeries: false }, drag: { x: false, y: false, setScale: false }, y: false,
              points: { show: dataPoint, size: 6, width: 1.5, fill: tok("--bg") } },
    select: { show: false },
    scales: { x: { time: true, auto: false, range: () => [since, until] }, y: { range: yRange || ((u, lo, hi) => padRange(lo, hi)) } },
    axes: [
      { ...axis, show: xAxis, size: xAxis ? 22 : 0, space: 64, incrs: TIME_STEPS, grid: { ...axis.grid, show: false },
        values: (u, ts, ai, space, incr) => ts.map((t) => (incr >= 86400 ? new Date(t * 1000).toLocaleDateString([], { month: "short", day: "numeric" }) : clockM(t))),
        ...(warp ? { splits: warp.splits, values: warp.values } : {}) },
      { ...axis, size: 44, space: 24, values: (u, vs) => vs.map((v) => yValues ? yValues(v) : fmt(v)) },
    ],
    hooks: { ...hooks, setCursor: [...(hooks.setCursor || []), (u) => { const i = u.cursor.idx; group.at(i == null ? null : warp ? warp.real(u.data[0][i]) : u.data[0][i]); }] },
  };
}
/* the cursor's mark, on the data only (not on a dashed level beside it) */
function dataPoint(u, si) {
  if (si !== 1) return null;
  const pt = document.createElement("div"), size = 6;
  Object.assign(pt.style, { width: `${size}px`, height: `${size}px`, marginLeft: `${-size / 2}px`, marginTop: `${-size / 2}px`, borderWidth: "1.5px" });
  return pt;
}
function padRange(lo, hi) {
  if (lo == null || hi == null || !Number.isFinite(lo) || !Number.isFinite(hi)) return [0, 1];
  if (lo === hi) { const d = Math.abs(lo) * 0.1 || 1; return [lo - d, hi + d]; }
  const d = (hi - lo) * 0.08;
  return [lo - d, hi + d];
}

/* drawn under the data: the stretches a loop was off (the one red), a tolerance band, a zero line */
function underlay({ off = [], band = null, zero = false, now = null }) {
  return (u) => {
    const ctx = u.ctx, { left, top, width, height } = u.bbox;
    ctx.save();
    ctx.beginPath(); ctx.rect(left, top, width, height); ctx.clip();
    ctx.fillStyle = tok("--bad-wash");
    for (const [a, b] of off) {
      const x0 = u.valToPos(a, "x", true), x1 = u.valToPos(b, "x", true);
      ctx.fillRect(x0, top, Math.max(devicePixelRatio, x1 - x0), height);
    }
    if (band) {
      const y0 = u.valToPos(band[1], "y", true), y1 = u.valToPos(band[0], "y", true);
      ctx.fillStyle = tok("--fill");
      ctx.fillRect(left, y0, width, Math.max(devicePixelRatio, y1 - y0));
    }
    if (now != null) {                                   // now: where the record ends and the projection begins
      const x = Math.round(u.valToPos(now, "x", true)) + 0.5;
      ctx.strokeStyle = tok("--line-strong"); ctx.lineWidth = devicePixelRatio;
      ctx.beginPath(); ctx.moveTo(x, top); ctx.lineTo(x, top + height); ctx.stroke();
    }
    if (zero) {
      const y = Math.round(u.valToPos(0, "y", true)) + 0.5;
      ctx.strokeStyle = tok("--line-strong"); ctx.lineWidth = devicePixelRatio;
      ctx.beginPath(); ctx.moveTo(left, y); ctx.lineTo(left + width, y); ctx.stroke();
    }
    ctx.restore();
  };
}
/* a label at a dashed line's right end (the desired level, r, a limit, the median): no legend needed */
function lineLabel(value, text) {
  return (u) => {
    if (value == null) return;
    const ctx = u.ctx, { left, width, top, height } = u.bbox, y = u.valToPos(value, "y", true);
    if (y < top - 1 || y > top + height + 1) return;
    ctx.save();
    ctx.font = `${parseFloat(tok("--canvas-sm")) * devicePixelRatio}px ${tok("--font")}`;
    ctx.textAlign = "right"; ctx.textBaseline = "bottom";
    ctx.lineWidth = 3 * devicePixelRatio; ctx.strokeStyle = tok("--chrome"); ctx.fillStyle = tok("--muted");
    const tx = left + width - 4 * devicePixelRatio, ty = y < top + 14 * devicePixelRatio ? y + 13 * devicePixelRatio : y - 3 * devicePixelRatio;
    ctx.strokeText(text, tx, ty); ctx.fillText(text, tx, ty);
    ctx.restore();
  };
}
function before(vs, i) { for (let j = i; j >= 0; j--) if (vs[j] != null) return vs[j]; return null; }
const inkLine = (extra = {}) => ({ stroke: tok("--ink"), width: 1.5, spanGaps: true, points: { show: false }, ...extra });
const dashLine = (extra = {}) => ({ stroke: tok("--muted"), width: 1, dash: [4, 3], points: { show: false }, ...extra });
/* the model's own lines: its replay dashed in ink over the measured one; its projection past now dashed, lighter;
   a what-if (the owner's own values, tried and not kept) the same in the accent: what they chose */
const replayLine = () => ({ stroke: tok("--ink"), width: 1.25, dash: [5, 3], spanGaps: true, points: { show: false } });
const projectionLine = () => ({ stroke: tok("--muted"), width: 1.25, dash: [2, 3], spanGaps: true, points: { show: false } });
const whatifLine = (ahead) => ({ stroke: tok("--accent"), width: 1.25, dash: ahead ? [2, 3] : [5, 3], spanGaps: true, points: { show: false } });

/* the projection's fan (sensitivity analysis): the 90% and 50% of the runs over what the model says is
   uncertain, shaded from now (the last reading) out to the horizon, under the lines */
function fanUnder(fan, ptimes, until, from) {
  return (u) => {
    if (!fan || !ptimes?.length) return;
    const ctx = u.ctx, { left, top, width, height } = u.bbox;
    ctx.save();
    ctx.beginPath(); ctx.rect(left, top, width, height); ctx.clip();
    for (const [lo, hi, colour] of [["p5", "p95", "--fan-90"], ["p25", "p75", "--fan-50"]]) {
      const a = fan[lo], b = fan[hi];
      if (!a || !b) continue;
      const ts = from != null ? [until, ...ptimes] : ptimes, ya = from != null ? [from, ...a] : a, yb = from != null ? [from, ...b] : b;
      ctx.beginPath();
      ts.forEach((t, i) => { const x = u.valToPos(t, "x", true), y = u.valToPos(yb[i] ?? 0, "y", true); i ? ctx.lineTo(x, y) : ctx.moveTo(x, y); });
      for (let i = ts.length - 1; i >= 0; i--) ctx.lineTo(u.valToPos(ts[i], "x", true), u.valToPos(ya[i] ?? 0, "y", true));
      ctx.closePath();
      ctx.fillStyle = tok(colour);
      ctx.fill();
    }
    ctx.restore();
  };
}

/* the replay's own spread over the record (Vensim's sensitivity graph over the run): the same greys, under the
   replay, from where the replay starts */
function fanPast(fan, times) {
  return (u) => {
    if (!fan) return;
    const ctx = u.ctx, { left, top, width, height } = u.bbox;
    ctx.save();
    ctx.beginPath(); ctx.rect(left, top, width, height); ctx.clip();
    for (const [lo, hi, colour] of [["p5", "p95", "--fan-90"], ["p25", "p75", "--fan-50"]]) {
      const a = fan[lo], b = fan[hi];
      if (!a || !b) continue;
      const idx = times.map((_, i) => i).filter((i) => a[i] != null && b[i] != null);
      if (idx.length < 2) continue;
      ctx.beginPath();
      idx.forEach((i, j) => { const x = u.valToPos(times[i], "x", true), y = u.valToPos(b[i], "y", true); j ? ctx.lineTo(x, y) : ctx.moveTo(x, y); });
      for (let j = idx.length - 1; j >= 0; j--) ctx.lineTo(u.valToPos(times[idx[j]], "x", true), u.valToPos(a[idx[j]], "y", true));
      ctx.closePath();
      ctx.fillStyle = tok(colour);
      ctx.fill();
    }
    ctx.restore();
  };
}

/* a projection too short to see on the window's axis (a minute ahead on an hour) gets a quarter of the chart's
   width, on a time axis of its own past now (+20s, +40s): the past keeps its clock, the projection its own scale */
const AHEAD_SHARE = 0.25;
const AHEAD_STEPS = [1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600, 7200, 10800, 21600, 43200, 86400];
function aheadWarp(since, until, end) {
  const W = until - since, H = end - until, D = (W * AHEAD_SHARE) / (1 - AHEAD_SHARE);
  if (!(H > 0) || H >= D) return null;
  const k = D / H;
  const real = (x) => (x <= until ? x : until + (x - until) / k);
  return {
    k, end: until + D, at: (t) => (t <= until ? t : until + (t - until) * k), real,
    splits: (u) => {
      const px = (u.bbox.width / devicePixelRatio) / (W + D), out = [];
      const step = TIME_STEPS.find((s) => s * px >= 64) || TIME_STEPS[TIME_STEPS.length - 1];
      for (let t = Math.ceil(since / step) * step; t <= until - step * 0.4; t += step) out.push(t);
      const fits = AHEAD_STEPS.filter((s) => s <= H);
      const r = fits.find((s) => s * k * px >= 40) || fits[fits.length - 1] || H;
      for (let x = r; x <= H - r * 0.35 + 1e-6; x += r) out.push(until + x * k);   // none at the very edge, where it would be cut
      return out;
    },
    values: (u, ts) => ts.map((t) => (t <= until + 1e-6 ? clockM(t) : `+${dur(real(t) - until)}`)),
  };
}

/* one chart: a line, its name and its value at the cursor (or its last) above it */
function lineChart({ group, name, role, unit, per, times, values, since, until, goal = null, off = [], height = 64, xAxis = false,
                     zero = false, href = null, stepped = false, level = null, replay = null, projection = null, ptimes = null,
                     fan = null, replayFan = null, whatifReplay = null, whatifProjection = null, yRange = null, flow = name }) {
  if (per) {                                           // a rate: in the unit that reads best for its size, its axis too (util.js)
    const all = [values, replay, projection, whatifReplay, whatifProjection].flatMap((xs) => xs || []).filter((v) => v != null && Number.isFinite(v));
    // (a goal on a rate keeps the unit its setpoint is written in, per hour, unless the flow says another)
    const ru = goal && !rateOver(flow) ? "hour" : rateUnit(all.length ? Math.max(...all.map(Math.abs)) : null, rateOver(flow));
    const k = RATE_PER_HOUR[ru], sc = (xs) => xs && xs.map((v) => (v == null ? v : v * k));
    const scFan = (f) => f && Object.fromEntries(Object.entries(f).map(([q, xs]) => [q, Array.isArray(xs) ? sc(xs) : xs]));
    [values, replay, projection, whatifReplay, whatifProjection] = [values, replay, projection, whatifReplay, whatifProjection].map(sc);
    [fan, replayFan] = [scFan(fan), scFan(replayFan)];
    if (goal && k !== 1) goal = { ...goal, value: goal.value == null ? goal.value : goal.value * k, band: goal.band && goal.band.map((v) => v * k),
                                  setpoint: `${goal.setpoint} /h` };
    per = RATE_SUFFIX[ru];
  }
  const last = [...values].reverse().find((v) => v != null);
  const unitText = per ? `${unit || ""}${per}` : unit || "";
  const val = h("span", { class: "chart-val" });
  const show = (v) => { val.textContent = v == null ? "–" : `${fmt(v)}${unitText ? " " + unitText : ""}`; };
  show(last);
  const head = h("div", { class: "chart-head" }, href ? h("a", { href: "#", class: "chart-name", onclick: (ev) => { ev.preventDefault(); href(); } }, name)
                                                     : h("span", { class: "chart-name" }, name),
                 role ? h("span", { class: "muted" }, role) : null, val);
  const plotEl = h("div", { class: "chart-plot" });
  const el = h("div", { class: "chart" }, head, plotEl);
  const desired = goal ? goal.value : null;
  // past now, the strip runs on to the projection's end; the measured line stops at now
  const real = ptimes?.length ? ptimes : [], pad = (xs) => [...xs, ...real.map(() => null)];
  const warp = real.length ? aheadWarp(since, until, real[real.length - 1]) : null;
  const ahead = warp ? real.map(warp.at) : real;
  const xs = [...times, ...ahead], end = warp ? warp.end : ahead.length ? ahead[ahead.length - 1] : until;
  const data = [xs, pad(values)];
  const series = [{}, inkLine(stepped ? { paths: uPlot.paths.stepped({ align: 1 }) } : {})];
  if (desired != null) { data.push(xs.map(() => desired)); series.push(dashLine()); }
  const hasReplay = replay && replay.some((v) => v != null);
  if (hasReplay) { data.push(pad(replay)); series.push(replayLine()); }
  const hasProj = projection && projection.some((v) => v != null) && ahead.length;
  if (hasProj) {                                         // from the last reading (what the projection starts from)
    const start = last ?? [...(replay || [])].reverse().find((v) => v != null) ?? null;
    data.push([...times.map((_, i) => (i === times.length - 1 ? start : null)), ...projection]);
    series.push(projectionLine());
  }
  const projIdx = hasProj ? data.length - 1 : null;
  const from = last ?? [...(replay || [])].reverse().find((v) => v != null) ?? null;
  if (whatifReplay && whatifReplay.some((v) => v != null)) { data.push(pad(whatifReplay)); series.push(whatifLine(false)); }
  if (whatifProjection && whatifProjection.some((v) => v != null) && ahead.length) {
    data.push([...times.map((_, i) => (i === times.length - 1 ? from : null)), ...whatifProjection]);
    series.push(whatifLine(true));
  }
  const outer = fan?.p5 ? ["p5", "p95"] : ["p25", "p75"];
  const hasFan = fan && ahead.length && (fan[outer[0]] || []).some((v) => v != null);
  const fanLo = hasFan ? Math.min(...fan[outer[0]].filter((v) => v != null)) : Infinity, fanHi = hasFan ? Math.max(...fan[outer[1]].filter((v) => v != null)) : -Infinity;
  const pastLo = replayFan ? Math.min(...(replayFan.p5 || replayFan.p25).filter((v) => v != null)) : Infinity;
  const pastHi = replayFan ? Math.max(...(replayFan.p95 || replayFan.p75).filter((v) => v != null)) : -Infinity;
  const valueAt = (i) => (i < times.length ? before(values, i) : projIdx != null ? data[projIdx][i] : null);
  mountPlot(plotEl, (width) => {
    const o = baseOpts({ width, height, group, since, until: end, xAxis, warp,
      yRange: yRange || ((u, lo, hi) => padRange(Math.min(lo ?? desired ?? 0, desired ?? Infinity, goal?.band?.[0] ?? Infinity, zero ? 0 : Infinity, fanLo, pastLo),
                                                 Math.max(hi ?? desired ?? 1, desired ?? -Infinity, goal?.band?.[1] ?? -Infinity, zero ? 0 : -Infinity, fanHi, pastHi))),
      hooks: { drawClear: [underlay({ off, band: goal?.band, zero, now: ahead.length ? until : null }), ...(hasFan ? [fanUnder(fan, ahead, until, from)] : []),
                            ...(replayFan ? [fanPast(replayFan, times)] : [])],
               draw: desired != null ? [lineLabel(desired, level || `desired ${op(goal.setpoint)}`)] : [],
               setCursor: [(u) => { const i = u.cursor.idx; if (i == null) return show(last); const v = valueAt(i);
                                    val.textContent = v == null ? "\u2013" : `${fmt(v)}${unitText ? " " + unitText : ""}${i >= times.length ? ", projected" : ""}`; }] } });
    o.series = series;
    return new uPlot(o, data, plotEl);
  });
  if (hasReplay || hasProj) el.classList.add("modelled");
  return el;
}

/* ---------------------------------------------------------------- the causes strip */

/* what a chart says while its numbers are asked for: in words, never a bare ellipsis that reads as a stuck load */
const working = () => h("div", { class: "muted small" }, "being worked out");

/* a part's series and what drives it (api series?strip=1): the part first, taller, then each cause,
   one time axis under the last */
const ROLE_WORDS = { inflow: "inflow", outflow: "outflow", "driven by": "drives it", from: "it drains", into: "it fills" };
function partRef(n) {
  if (!n) return null;
  if (n.kind === "stock") return `stock.${n.label}`;
  if (n.kind === "auxiliary" && !n.role) return `auxiliary.${n.label}`;
  if ((n.kind === "valve" || n.kind === "disturbance") && (n.flow || n.label)) return `flow.${n.flow || n.label}`;
  return null;
}
function causesStrip(ref, group = chartGroup("strip")) {
  const box = h("div", { class: "strip" }, working());
  let tries = 0;                                         // the closed loop's fan, worked out apart: asked for again
  const load = () => api("series", { refs: ref, strip: 1, replay: 1, points: CHART_POINTS, ...(SNAP ? {} : { fan: S.replayFan ? "replay" : 1 }),
                                     ...(S.loops ? { loops: S.loops } : {}), ...whatifParams() }).then((d) => {
    if (d.fan_pending && !SNAP && tries++ < 8) setTimeout(() => { if (box.isConnected) load(); }, 2500);
    const list = d.series || [];
    if (!list.length || list.every((s) => s.values.every((v) => v == null) && !(s.replay || []).some((v) => v != null))) {
      box.replaceChildren(h("p", { class: "muted small" }, `Nothing measured in ${windowSaid(d)}.`));
      return;
    }
    const modelled = list.some((s) => s.replay || s.projection);
    box.replaceChildren(...list.map((s, i) => lineChart({
      group, name: i === 0 ? (s.kind === "flow" ? "rate" : "value") : s.name,
      role: i === 0 ? (s.kind === "flow" ? s.how : null) : ROLE_WORDS[s.role] || s.role,
      unit: s.unit, per: s.per, flow: s.name, times: d.times, values: s.values, since: d.since, until: d.until,
      goal: s.goal, height: i === 0 ? 84 : 52, xAxis: i === list.length - 1, zero: s.kind === "flow",
      replay: s.replay, projection: s.projection, ptimes: d.projection_times, fan: s.fan, replayFan: s.replay_fan,
      whatifReplay: s.whatif_replay, whatifProjection: s.whatif_projection,
      href: i === 0 ? null : () => openRef(s.ref) })),
      h("div", { class: "chart-foot" }, h("span", { class: "muted" }, [d.low_confidence ? `Low confidence: ${d.low_confidence}; the band is widened by the replay's own error` : "",
        list.length > 1 ? "On one time axis; each rate in the unit that reads best for it" : "",
        modelled ? `dashed: the model's replay; past now, lighter: its projection ${dur(d.horizon)} ahead, ${d.inputs || "inputs held where they were"}` : "",
        modelled ? (d.fan_pending ? "the spread with the loops running is being worked out" : fanSaid(d, list.some((s) => s.fan))) : "", replayFanSaid(d, list.some((s) => s.replay_fan)), whatifSaid(d),
        list[0].replay ? "" : noReplaySaid(list[0])].filter(Boolean).join(". ")),
        group.when),
      ...riskLines(d), ...modelsSaid(d),
      ...(!SNAP && (d.fan?.parameters?.length || d.loops_can_close) ? [h("div", { class: "actions" },
        d.fan?.parameters?.length ? h("button", { class: "ghost", onclick: () => { S.replayFan = !S.replayFan;
          for (const b of document.querySelectorAll(".strip")) b.redraw?.(); } }, S.replayFan ? "Hide the spread over the record" : "Spread over the record") : null,
        d.loops_can_close ? loopsToggle(d.loops) : null)] : []),
      ...(d.whatif_invalid?.length ? [h("p", { class: "s-open small" }, `With the what-if the model cannot run: ${d.whatif_invalid.join("; ")}. ` +
        "Each fault is taken as 0, so the blue lines are not what the model would do.")] : []));
  }).catch((e) => box.replaceChildren(h("p", { class: "muted small" }, String(e.message || e))));
  load();
  box.redraw = () => { tries = 0; load(); };           // a what-if tried: drawn again with it
  if (!SNAP) rememberChart(ref);
  return box;
}

/* how much of the behaviour a feedback loop drives over the window (Loops That Matter, on the simulation at its
   step): at each stock it runs through, its relative loop score (−1 to +1) beside every scored loop competing
   there (in grey), as Stella's loop dominance view shows them; how often it dominated, unless loops through the
   stock are not scored or it is tied; or why it is not worked out */
function loopDominance(name, group = chartGroup("dominance")) {
  const box = h("div", { class: "strip dominance" }, working());
  api("dominance", { points: CHART_POINTS }).then((d) => {      // every stock's (as a snapshot keeps it); this loop's below
    if (!d) { box.replaceChildren(h("p", { class: "muted small" }, "How much of the behaviour it drives is not worked out: the model cannot be read.")); return; }
    const why = d.not_scored?.[name];
    if (why) { box.replaceChildren(h("p", { class: "muted small" }, `How much of the behaviour it drives is not worked out: ${why}.`)); return; }
    const at = (d.stocks || []).filter((x) => (x.relative?.[name] || []).some((v) => v != null));
    if (!at.length) {
      box.replaceChildren(h("p", { class: "muted small" }, "Its loop score was 0 throughout the window: some link along it did not move when its cause did, so it drove none of the behaviour then."));
      return;
    }
    const out = [];
    at.forEach((x, n) => {
      const st = x.stock.split(".").slice(1).join(".");
      const others = Object.keys(x.relative).filter((k) => k !== name);
      out.push(dominanceChart({ group, title: `at ${st}`, times: d.times, since: d.since, until: d.until, mine: x.relative[name],
        others: others.map((k) => x.relative[k]), xAxis: n === at.length - 1 }));
      const share = x.share?.[name], last = [...(x.dominant || [])].reverse().find((k) => k);
      const scored = `${x.scored} of the ${x.loops} loop${x.loops === 1 ? "" : "s"} through ${st} ${x.scored === 1 ? "is" : "are"} scored`;
      const words = !x.named
        ? `${scored}; the others run through decisions or parts whose response the model does not write, so no loop is named as dominant there`
        : x.scored === 1 ? `The only loop through ${st}: it drives all of its feedback`
        : [share != null ? `Dominant at ${st} in ${Math.round(share * 100)}% of the window${last === name ? ", and now" : last ? `; now ${last}` : ""}` : "",
           x.ties ? `tied with another in ${x.ties} bucket${x.ties === 1 ? "" : "s"} (no loop named then)` : "",
           others.length ? `grey: ${others.join(", ")}` : ""].filter(Boolean).join("; ");
      out.push(h("p", { class: "muted small" }, `${words}.`));
    });
    out.push(h("div", { class: "chart-foot" }, h("span", { class: "muted" },
      ["+1: it drives everything at the stock, reinforcing; \u22121: balancing. Computed on the model's replay at its integration step",
       d.assumed?.[name]?.length ? `assumed to pass on all of their cause's change (the model does not write how they answer): ${d.assumed[name].join(", ")}` : ""].filter(Boolean).join(". ")), group.when));
    box.replaceChildren(...out);
  }).catch((e) => box.replaceChildren(h("p", { class: "muted small" }, `How much of the behaviour it drives is not worked out: ${e.message || e}.`)));
  return box;
}
/* a loop's relative score in ink over the others competing at the same stock in grey, on −1 to +1 */
function dominanceChart({ group, title, times, since, until, mine, others, xAxis }) {
  const val = h("span", { class: "chart-val" });
  const last = [...mine].reverse().find((v) => v != null);
  const show = (v) => { val.textContent = v == null ? "\u2013" : fmt(v); };
  show(last);
  const plotEl = h("div", { class: "chart-plot" });
  const el = h("div", { class: "chart" }, h("div", { class: "chart-head" }, h("span", { class: "chart-name" }, "relative loop score"),
    h("span", { class: "muted" }, title), val), plotEl);
  mountPlot(plotEl, (width) => {
    const o = baseOpts({ width, height: 96, group, since, until, xAxis, yRange: () => [-1.1, 1.1],
      hooks: { drawClear: [underlay({ zero: true })], setCursor: [(u) => { const i = u.cursor.idx; show(i == null ? last : mine[i]); }] } });
    o.series = [{}, inkLine(), ...others.map(() => ({ stroke: tok("--muted"), width: 1, spanGaps: true, points: { show: false } }))];
    return new uPlot(o, [times, mine, ...others], plotEl);
  });
  return el;
}

/* the projection with the loops running (the goals, the built-ins and each machine block's identified model, simulated) or
   held (open loop): one choice for every chart on the page (S.loops), the loops running by default where there are any */
function loopsToggle(now) {
  const closed = now === "closed";
  return h("span", { class: "seg", role: "group", "aria-label": "how the projection runs" },
    ...[["closed", "With the loops running"], ["held", "Held"]].map(([k, words]) => h("button", {
      class: `ghost${(k === "closed") === closed ? " on" : ""}`, "aria-pressed": String((k === "closed") === closed),
      title: k === "closed" ? "The goals, the built-in blocks and each machine block's identified model run on past now"
                            : "Open loop: every block held as it was, every input held where it was",
      onclick: () => { S.loops = k; for (const b of document.querySelectorAll(".strip")) b.redraw?.(); } }, words)));
}
/* with the loops running: each goal on these parts, its chance of being off at the horizon (the Monte Carlo's) */
function riskLines(d) {
  return (d.risk || []).filter((r) => r.sentence).map((r) => forecastEl(r, "small risk"));
}
/* a goal's forecast as a sentence (forecast_words.py), its p, runs, horizon and method in its title and a closed disclosure */
function forecastEl(r, cls = "") {
  return h("div", { class: `forecast ${cls}` }, h("p", { class: r.p_off_end >= 0.5 ? "s-open" : "", title: r.title }, `${r.goal}: ${r.sentence}`),
    r.how?.length ? h("details", { class: "small" }, h("summary", { class: "muted" }, "How this was worked out"), dl(r.how)) : null);
}
/* what stands in for the machine blocks near these parts, in words (the closed-loop projection runs them, not the blocks) */
function modelsSaid(d) {
  if (d.loops !== "closed" || !d.models?.length) return [];
  return [h("details", { class: "block-models small" }, h("summary", { class: "muted" },
    `Each block's identified model (${d.models.length})${d.models_assumed?.length ? `; assumed: ${d.models_assumed.join(", ")}` : ""}`),
    h("ul", {}, d.models.map((x) => h("li", { class: x.assumed ? "s-open" : null }, x.said,
      SNAP || x.pool == null ? null : h("span", { class: "muted" }, "; what if its pool were ", whatifField(`block.${x.block}.pool`,
        `what if ${x.block}'s pool were`, x.pool, "another number of runs at once"), " and it failed ", whatifField(`block.${x.block}.failure`,
        `what if ${x.block} failed`, x.success != null ? `${Math.round((1 - x.success) * 100)}%` : "", "a share of its runs given back (rework): 20%"),
        " of its runs (the items' estimates too)")))))];
}
/* a what-if only the closed-loop projection can try (an input's rate, a goal's setpoint, a pool), typed in a panel:
   drawn on every chart on the page, never kept */
function whatifField(key, label, shown, hint) {
  const input = h("input", { class: "whatif-in num", value: S.whatif?.[key] ?? shown ?? "", size: 7, "aria-label": label,
    "data-name": key, "data-declared": shown ?? "", title: `${hint}; drawn with the loops running, nothing is saved` });
  input.addEventListener("change", () => { const v = input.value.trim(); setWhatif(key, v === String(shown ?? "") || v === "" ? null : v); });
  return h("span", { class: "nowrap" }, input);
}

/* an input from outside: its rate to try (per hour, or x2 for twice what it is now) */
function inputWhatif(flow) {
  if (SNAP) return null;
  return h("p", { class: "muted small" }, "What if it came at ", whatifField(`flow.${flow}`, `what if ${flow} came at`, "",
    "a rate per hour, or x2 for twice its mean over the window"), " an hour (or x2: twice its mean), with the loops running");
}

/* the owner's what-if: parameters tried at other values, for every chart on the page, never kept (S.whatif) */
function whatifParams() {
  const w = Object.entries(S.whatif || {});
  return w.length ? { whatif: w.map(([k, v]) => `${k}:${v}`).join(",") } : {};
}
function setWhatif(name, value) {
  S.whatif = { ...(S.whatif || {}) };
  if (value == null || value === "") delete S.whatif[name]; else S.whatif[name] = String(value).trim();
  for (const b of document.querySelectorAll(".strip")) b.redraw?.();
  for (const f of document.querySelectorAll(".whatif, .whatif-redraw")) f.redraw?.();
}
const tried = (w) => (w.duration ? dur(w.value * 3600) : `${fmt(w.value)}${w.unit ? " " + w.unit : ""}`);
function whatifSaid(d) {
  if (d.whatif_error) return `What-if not drawn: ${d.whatif_error}`;
  if (!d.whatif?.length) return "";
  return `in blue, what if ${d.whatif.map((w) => (w.said ? w.said : `${w.name} were ${tried(w)}`)).join(" and ")} (not saved)`;
}
function replayFanSaid(d, drawn) {
  const f = d.replay_fan;
  if (!f) return "";
  if (!drawn) return "the replay's spread over the record is too small to draw";
  return `before now, shaded: the replay's half${f.tails ? ", and nine in ten," : ""} of ${f.samples} replays over the same values`;
}
/* why the part itself has no replay, projection or fan: the replay works out a stock with flows and a part with an
   equation; anything else it takes as measured */
function noReplaySaid(s) {
  if (s.modelled === "identified model") return "no replay: a block moves it, and the replay takes it as measured; past now, its block's identified model";
  if (s.kind === "stock") return "no replay or projection: no flow fills or drains it in the model";
  return "no replay, projection or fan: no equation works it out, so the replay takes it as measured";
}
function fanSaid(d, drawn) {
  const f = d.fan;
  if (!f) return "";
  if (f.closed) {
    if (!f.samples) return "no spread drawn: no run with the loops running was valid";
    const bad = f.invalid ? `; ${f.invalid} of ${f.samples + f.invalid} runs not valid` : "";
    const names = f.parameters.map((u) => u.name);
    return `shaded: half${f.tails ? ", and nine in ten," : ""} of ${f.samples} runs with the loops running` +
      (names.length ? `, over ${names.slice(0, 5).join(", ")}${names.length > 5 ? ` and ${names.length - 5} more` : ""} (estimates and identified models \u00b12 standard errors; inputs by how far their mean could move)` : "") +
      bad + (f.stopped ? `; ${f.stopped}` : "") + (drawn ? "" : "; too narrow to draw here");
  }
  if (!f.parameters?.length) return "no spread drawn: no parameter it uses has a range or an estimate's error";
  if (!f.samples) return "no spread drawn: every run of the uncertain parameters blew up";
  if (!drawn) return `no spread drawn: its projection is the same over ${f.parameters.map((u) => u.name).join(", ")} as far as it looks`;
  const how = [...new Set(f.parameters.map((u) => (u.how === "range" ? "range" : "estimate \u00b12 standard errors")))];
  return `shaded: half${f.tails ? ", and nine in ten," : ""} of ${f.samples} runs over ${f.parameters.map((u) => `${u.name} ${u.duration ? dur(u.low * 3600) : fmt(u.low)} to ${u.duration ? dur(u.high * 3600) : fmt(u.high)}`).join(", ")}` +
    ` (${f.parameters.length > 1 ? "each its" : "its"} ${how.join(" or ")})` + (f.joint ? `; ${f.joint}` : "") +
    (f.tails ? "" : `; nine in ten not drawn from fewer than 100 runs`);
}
/* a system's own measures (its show:, else its goals' measures), each a chart on one time axis: what its
   box used to draw as sparklines, now in its panel */
function moduleCharts(n, group = chartGroup("module")) {
  const refs = [...new Set((n.charted || n.measures || []).filter((x) => !x.missing && !x.unchecked)   // (nothing to ask for)
    .map((x) => x.part.replace(":", ".")))];
  if (!refs.length) return null;
  const box = h("div", { class: "strip" }, working());
  api("series", { refs: refs.join(","), points: CHART_POINTS }).then((d) => {
    const list = d.series || [];
    if (!list.length || list.every((s) => s.values.every((v) => v == null))) {
      box.replaceChildren(h("p", { class: "muted small" }, `Nothing measured in ${windowSaid(d)}.`));
      return;
    }
    box.replaceChildren(...list.map((s, i) => lineChart({
      group, name: s.name, role: s.kind === "flow" ? "rate" : null, unit: s.unit, per: s.per, times: d.times, values: s.values,
      since: d.since, until: d.until, goal: s.goal, height: 60, xAxis: i === list.length - 1, zero: s.kind === "flow",
      href: () => openRef(s.ref) })), h("div", { class: "chart-foot" }, h("span", { class: "muted" }, "Its measures, on one time axis"), group.when));
  }).catch((e) => box.replaceChildren(h("p", { class: "muted small" }, String(e.message || e))));
  return box;
}
const windowSaid = (d) => (d && d.until - d.since < (S.status?.window || 0) * 0.95 ? `the ${dur(d.until - d.since)} recorded` : "the window");

/* a part named in a strip, opened as if clicked on the diagram */
function openRef(ref) {
  const [kind, ...rest] = ref.split("."), name = rest.join(".");
  const n = (S.graph?.nodes || []).find((x) => partRef(x) === ref) ||
    { id: `${kind === "flow" ? "flow" : "stock"}:${name}`, kind: kind === "flow" ? "valve" : kind, label: name, flow: kind === "flow" ? name : undefined };
  return openNode(n);
}

/* "your charts": the parts charted last, per project, in this browser */
function chartsKey() { return `ergostat.charts.${S.status?.name || ""}`; }
function rememberedCharts() { try { return JSON.parse(localStorage.getItem(chartsKey()) || "[]"); } catch (e) { return []; } }
function rememberChart(ref) {
  try { localStorage.setItem(chartsKey(), JSON.stringify([ref, ...rememberedCharts().filter((r) => r !== ref)].slice(0, 3))); }
  catch (e) { /* not remembered */ }
}

/* the side panel's charts, in the dynamics view: the parts chosen (Shift-click, or a box), each one's
   strip on one time axis; with nothing chosen, the user's charts. Kept between the panel's refreshes */
function sideCharts(side) {
  const g = S.graph;
  const chosen = [...(S.sel || [])].filter((p) => /^(stock|flow|auxiliary)\.[^.]+$/.test(p) && (g?.corr?.parts?.[p] || []).length);   // (parts: interact.js)
  const refs = chosen.length ? chosen.slice(0, 6) : rememberedCharts();
  const sig = (chosen.length ? "chosen:" : "yours:") + refs.join(",") + `|${S.since}|${S.at || ""}`;
  const box = S.sideChartsEl || (S.sideChartsEl = h("div", { class: "side-charts" }));
  const stale = Date.now() - (box.drawnAt || 0) > 15000 && !box.matches(":hover");     // fresh data, but never under the pointer
  if (box.sig === sig && box.side === side && !stale) return box;
  box.sig = sig; box.side = side; box.drawnAt = Date.now();
  if (!refs.length) { box.replaceChildren(); return box; }
  const group = chartGroup("side");
  box.replaceChildren(h("h3", {}, chosen.length ? "Charts of the parts chosen" : "Your charts"),
    ...refs.map((r) => h("div", { class: "side-strip" }, h("div", { class: "strip-title" }, h("a", { href: "#", onclick: (ev) => { ev.preventDefault(); openRef(r); } },
      r.split(".").slice(1).join(".")), h("span", { class: "muted" }, r.split(".")[0])), causesStrip(r, group))));
  return box;
}
function sideChartsChanged() {                          // the chosen parts changed: the side panel follows at once
  const sig = [...(S.sel || [])].sort().join(",");
  if (sig === S.selSig) return;
  S.selSig = sig;
  if (S.graph?.kind === "dynamics" && S.sideChartsEl?.isConnected) S.redrawSide?.();
}

/* ---------------------------------------------------------------- the scope */

/* a loop as a control engineer reads it: y measured and r dashed on one plot, the tolerance shaded;
   u below (each opening of its valve, or the knob's value), its limits dashed; e = r − y below that;
   the stretches it was off tinted red on all three; then its numbers */
function loopScope(goal, { numbers = true } = {}) {
  const box = h("div", { class: "strip scope" }, working());
  api("loop-scope", { goal, points: CHART_POINTS }).then((d) => {
    const group = chartGroup("scope");
    const u = d.u || {};
    const charts = [lineChart({ group, name: "y", role: `${d.stock}, measured`, unit: d.unit, times: d.times, values: d.y, since: d.since,
                                until: d.until, off: d.off, height: 96, goal: { value: d.r, setpoint: d.setpoint, band: d.band },
                                level: `r ${op(d.setpoint)}` })];
    charts.push(u.openings ? openingsChart(group, d, u) : u.values ? lineChart({ group, name: "u", role: u.how, unit: u.unit, times: d.times,
      values: u.values, since: d.since, until: d.until, off: d.off, height: 60, stepped: true, ...limitsLevel(u) })
      : h("div", { class: "chart" }, h("div", { class: "chart-head" }, h("span", { class: "chart-name" }, "u"),
                                       h("span", { class: "muted" }, d.open_loop ? "it acts on its schedule" : "nothing in the model acts for it"))));
    charts.push(lineChart({ group, name: "e", role: "r − y", unit: d.unit, times: d.times, values: d.e, since: d.since, until: d.until,
                            off: d.off, height: 60, zero: true, xAxis: true }));
    const nb = d.numbers || {};
    box.replaceChildren(...charts, h("div", { class: "chart-foot" }, h("span", { class: "muted" }, d.off.length ? "Red: off" : ""), group.when),
      numbers ? dl([["time off", numbers === "new" ? null : shareText(nb.off_share)],
                    ["back in", numbers === "new" || nb.back_in == null ? null : `${dur(nb.back_in)}, typically (${nb.times_off} times)`],
                    ["saturated", nb.saturated != null ? `${Math.round(nb.saturated * 100)}% of ${u.openings ? "its openings" : "the time"}` : null],
                    ["last decision", nb.last_decision ? `${ago(nb.last_decision.time)}: ${nb.last_decision.decision ?? "–"}` : null]]) : null);
  }).catch((e) => box.replaceChildren(h("p", { class: "muted small" }, String(e.message || e))));
  return h("div", {}, box, controlBox(goal, "scope"));  // and how it is doing, as a control engineer reads it (control.js)
}
/* a knob's limit, as its chart's dashed level */
function limitsLevel(u) {
  const [lo, hi] = u.limits || [];
  if (hi != null) return { goal: { value: hi, setpoint: "", band: null }, level: `most ${fmt(hi)}` };
  if (lo != null) return { goal: { value: lo, setpoint: "", band: null }, level: `least ${fmt(lo)}` };
  return {};
}
/* u for a valve: each opening a point, on the time axis, with the most one run may move dashed */
function openingsChart(group, d, u) {
  const ts = u.openings.map((o) => o[0]), vs = u.openings.map((o) => o[1]);
  const hi = u.limits?.[1], lo = u.limits?.[0];
  const val = h("span", { class: "chart-val" }, vs.length ? `${fmt(vs[vs.length - 1])} ${u.unit || ""}`.trim() : "never opened");
  const plotEl = h("div", { class: "chart-plot" });
  const el = h("div", { class: "chart" }, h("div", { class: "chart-head" }, h("span", { class: "chart-name" }, "u"), h("span", { class: "muted" }, u.how), val), plotEl);
  if (!ts.length) { plotEl.append(h("div", { class: "muted small" }, `Its valve did not open in ${windowSaid(d)}.`)); return el; }
  mountPlot(plotEl, (width) => {
    const o = baseOpts({ width, height: 60, group, since: d.since, until: d.until, xAxis: false,
      yRange: (_, a, b) => padRange(Math.min(a ?? 0, 0, lo ?? 0), Math.max(b ?? 1, hi ?? -Infinity)),
      hooks: { drawClear: [underlay({ off: d.off, zero: true })],
               draw: [lineLabel(hi, `most a run ${fmt(hi)}`), ...(lo ? [lineLabel(lo, `${fmt(lo)}`)] : []), stems],
               setCursor: [(p) => { const i = p.cursor.idx; val.textContent = i == null ? `${fmt(vs[vs.length - 1])}` : `${fmt(vs[i])} at ${clockS(ts[i])}`; }] } });
    o.series = [{}, { stroke: tok("--ink"), width: 0, paths: () => null, points: { show: true, size: 5, fill: tok("--ink"), stroke: tok("--ink") } },
                ...(hi != null ? [dashLine()] : []), ...(lo ? [dashLine()] : [])];
    return new uPlot(o, [ts, vs, ...(hi != null ? [ts.map(() => hi)] : []), ...(lo ? [ts.map(() => lo)] : [])], plotEl);
  });
  return el;
}
/* a stem from zero to each opening, as a sampled signal is drawn */
function stems(u) {
  const ctx = u.ctx, y0 = u.valToPos(0, "y", true);
  ctx.save(); ctx.strokeStyle = tok("--ink"); ctx.lineWidth = devicePixelRatio; ctx.setLineDash([]);
  ctx.beginPath();
  for (let i = 0; i < u.data[0].length; i++) {
    const x = Math.round(u.valToPos(u.data[0][i], "x", true)) + 0.5, y = u.valToPos(u.data[1][i], "y", true);
    ctx.moveTo(x, y0); ctx.lineTo(x, y);
  }
  ctx.stroke(); ctx.restore();
}

/* an agent's runs by one number each (SPEC §9.1): a stem at each run's end; or summed by hour, stepped (what it spent) */
function useChart({ group, name, unit = "", times, values, since, until, text = fmt, hourly = false, height = 56, xAxis = false }) {
  const val = h("span", { class: "chart-val" });
  const total = values.reduce((a, v) => a + (v || 0), 0), last = values.length ? values[values.length - 1] : null;
  const show = (i) => {
    val.textContent = i != null ? `${text(values[i])} ${hourly ? "in the hour from" : "at"} ${clockM(times[i])}`
      : hourly ? `${text(total)} in all` : last == null ? "\u2013" : `${text(last)}, its last run`;
  };
  show(null);
  const plotEl = h("div", { class: "chart-plot" });
  const el = h("div", { class: "chart use-chart" }, h("div", { class: "chart-head" }, h("span", { class: "chart-name" }, name),
    unit ? h("span", { class: "muted" }, unit) : null, val), plotEl);
  if (!times.length) { plotEl.append(h("div", { class: "muted small" }, "Nothing recorded in the window.")); return el; }
  mountPlot(plotEl, (width) => {
    const o = baseOpts({ width, height: height + (xAxis ? 22 : 0), group, since, until, xAxis, yValues: text,
      yRange: (_, a, b) => padRange(0, Math.max(b ?? 1, 0) || 1),
      hooks: { drawClear: [underlay({ zero: true })], draw: hourly ? [] : [stems], setCursor: [(u) => show(u.cursor.idx)] } });
    o.series = [{}, hourly ? inkLine({ paths: uPlot.paths.stepped({ align: 1 }) })
      : { stroke: tok("--ink"), width: 0, paths: () => null, points: { show: true, size: 5, fill: tok("--ink"), stroke: tok("--ink") } }];
    return new uPlot(o, [times, values], plotEl);
  });
  return el;
}

/* ---------------------------------------------------------------- items: the cumulative flow, the cycle times */

/* a kind's states stacked over the window in state order, the first on top and where they finish at
   the bottom: bands are stocks, their edges' slopes flows. Each state named at the right with its count
   (at the cursor, or now): a click filters the table, as the counts did */
function flowChart(d, group, { chosen = null, onState = null } = {}) {
  const states = d.states;
  const ramp = ["--line", "--line-strong", "--muted", "--ink-2"];
  const step = (i) => ramp[Math.min(ramp.length - 1, Math.floor((i / Math.max(1, states.length - 1)) * (ramp.length - 1) + 0.0001))];
  const shade = (i) => tok(step(i));
  // cumulative from the bottom (the last state) up
  const cumOf = (d) => states.map((_, k) => Array.from({ length: d.times.length }, (_, i) => states.slice(k).reduce((a, st) => a + d.counts[st][i], 0)));
  const boxClass = (d, st, chosen) => `stbox${d.now[st] ? " some" : ""}${chosen === st ? " on" : ""}`;
  let cur = d;                                            // the data shown: set in place by update()
  const labels = states.map((st, k) => {
    const n0 = h("span", { class: "n" }, String(d.now[st] || 0));
    const a = h("a", { href: "#", class: boxClass(d, st, chosen),
                      onclick: (ev) => { ev.preventDefault(); onState?.(st); } }, h("span", { class: "swatch", style: `background:var(${step(k)})` }), n0, st);
    a.count = n0;
    return a;
  });
  const plotEl = h("div", { class: "chart-plot" });
  const el = h("div", { class: "cfd" }, plotEl, h("div", { class: "cfd-states" }, ...labels.slice()));
  mountPlot(plotEl, (width) => {
    const o = baseOpts({ width, height: 120, group, since: cur.since, until: cur.until, xAxis: true,
      yRange: (_, lo, hi) => [0, Math.max(1, hi || 1) * 1.05],
      hooks: { setCursor: [(u) => { const i = u.cursor.idx;
        states.forEach((st, k) => { setText(labels[k].count, String(i == null ? cur.now[st] || 0 : cur.counts[st][i])); }); }] } });
    o.scales.x.range = () => [cur.since, cur.until];
    o.axes[1].values = (u, vs) => vs.map((v) => (Number.isInteger(v) ? String(v) : ""));
    o.series = [{}, ...states.map((st, k) => ({ stroke: tok("--bg"), width: 1, fill: shade(k), points: { show: false } }))];
    o.cursor.points = { show: false };
    return new uPlot(o, [cur.times, ...cumOf(cur)], plotEl);
  });
  // new data for the same states: the counts and the plot's data set in place (false: the states differ, draw it again)
  el.update = (d2, chosen2 = null) => {
    if (JSON.stringify(d2.states) !== JSON.stringify(states)) return false;
    cur = d2;
    states.forEach((st, k) => {
      setText(labels[k].count, String(d2.now[st] || 0));
      const c = boxClass(d2, st, chosen2);
      if (labels[k].className !== c) labels[k].className = c;
    });
    plotEl.plot?.setData([d2.times, ...cumOf(d2)]);
    return true;
  };
  return el;
}
/* each finished item: when it finished, and how long it took, with the median dashed */
function cycleChart(d, group) {
  let cur = d, f = d.finished || [];                     // the data shown: set in place by update()
  const medianSaid = () => (cur.median != null ? `median ${dur(cur.median)}` : "");
  const headSaid = () => `from arriving to ${cur.finished_states.join(" or ")}, ${cur.finished_total ?? f.length} finished${(cur.finished_total ?? 0) > f.length ? ` (${f.length} shown)` : ""}`;
  const val = h("span", { class: "chart-val" }, medianSaid());
  const said = h("span", { class: "muted" }, headSaid());
  const plotEl = h("div", { class: "chart-plot" });
  const el = h("div", { class: "chart cycle" }, h("div", { class: "chart-head" }, h("span", { class: "chart-name" }, "Cycle time"), said, val), plotEl);
  if (!f.length) { plotEl.append(h("div", { class: "muted small" }, `None finished in ${windowSaid(d)}.`)); return el; }
  const series = () => [f.map((x) => x.time), f.map((x) => x.took), f.map(() => cur.median)];
  mountPlot(plotEl, (width) => {
    const o = baseOpts({ width, height: 100, group, since: cur.since, until: cur.until, xAxis: true, yValues: (v) => (v > 0 ? dur(v) : v === 0 ? "0" : ""),
      yRange: (_, lo, hi) => [0, Math.max(hi || 1, cur.median || 0) * 1.1],
      hooks: { draw: [(u) => lineLabel(cur.median, `median ${dur(cur.median)}`)(u)],
               setCursor: [(u) => { const i = u.cursor.idx; setText(val, i == null ? medianSaid() : `${f[i].id}: ${dur(f[i].took)}`); }] } });
    o.scales.x.range = () => [cur.since, cur.until];
    o.series = [{}, { stroke: tok("--ink"), width: 0, paths: () => null, points: { show: true, size: 5, fill: tok("--ink"), stroke: tok("--ink") } },
                dashLine()];
    return new uPlot(o, series(), plotEl);
  });
  // new data with some finished still: set in place (false when there are none: drawn again)
  el.update = (d2) => {
    if (!(d2.finished || []).length) return false;
    cur = d2; f = d2.finished;
    setText(val, medianSaid()); setText(said, headSaid());
    plotEl.plot?.setData(series());
    return true;
  };
  return el;
}
