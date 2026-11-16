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
function baseOpts({ width, height, group, since, until, xAxis = true, yValues = null, yRange = null, hooks = {} }) {
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
        values: (u, ts, ai, space, incr) => ts.map((t) => (incr >= 86400 ? new Date(t * 1000).toLocaleDateString([], { month: "short", day: "numeric" }) : clockM(t))) },
      { ...axis, size: 44, space: 24, values: (u, vs) => vs.map((v) => yValues ? yValues(v) : fmt(v)) },
    ],
    hooks: { ...hooks, setCursor: [...(hooks.setCursor || []), (u) => { const i = u.cursor.idx; group.at(i == null ? null : u.data[0][i]); }] },
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
/* the model's own lines: its replay dashed in ink over the measured one; its projection past now dashed, lighter */
const replayLine = () => ({ stroke: tok("--ink"), width: 1.25, dash: [5, 3], spanGaps: true, points: { show: false } });
const projectionLine = () => ({ stroke: tok("--muted"), width: 1.25, dash: [2, 3], spanGaps: true, points: { show: false } });

/* one chart: a line, its name and its value at the cursor (or its last) above it */
function lineChart({ group, name, role, unit, per, times, values, since, until, goal = null, off = [], height = 64, xAxis = false,
                     zero = false, href = null, stepped = false, level = null, replay = null, projection = null, ptimes = null }) {
  const last = [...values].reverse().find((v) => v != null);
  const unitText = per ? `${unit || ""}/h` : unit || "";
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
  const ahead = ptimes?.length ? ptimes : [], pad = (xs) => [...xs, ...ahead.map(() => null)];
  const xs = [...times, ...ahead], end = ahead.length ? ahead[ahead.length - 1] : until;
  const data = [xs, pad(values)];
  const series = [{}, inkLine(stepped ? { paths: uPlot.paths.stepped({ align: 1 }) } : {})];
  if (desired != null) { data.push(xs.map(() => desired)); series.push(dashLine()); }
  const hasReplay = replay && replay.some((v) => v != null);
  if (hasReplay) { data.push(pad(replay)); series.push(replayLine()); }
  const hasProj = projection && projection.some((v) => v != null) && ahead.length;
  if (hasProj) {                                         // from the last reading (what the projection starts from)
    const from = last ?? [...(replay || [])].reverse().find((v) => v != null) ?? null;
    data.push([...times.map((_, i) => (i === times.length - 1 ? from : null)), ...projection]);
    series.push(projectionLine());
  }
  const valueAt = (i) => (i < times.length ? before(values, i) : hasProj ? data[data.length - 1][i] : null);
  mountPlot(plotEl, (width) => {
    const o = baseOpts({ width, height, group, since, until: end, xAxis,
      yRange: (u, lo, hi) => padRange(Math.min(lo ?? desired ?? 0, desired ?? Infinity, goal?.band?.[0] ?? Infinity, zero ? 0 : Infinity),
                                      Math.max(hi ?? desired ?? 1, desired ?? -Infinity, goal?.band?.[1] ?? -Infinity, zero ? 0 : -Infinity)),
      hooks: { drawClear: [underlay({ off, band: goal?.band, zero, now: ahead.length ? until : null })],
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
  const box = h("div", { class: "strip" }, h("div", { class: "muted small" }, "…"));
  api("series", { refs: ref, strip: 1, replay: 1, points: CHART_POINTS }).then((d) => {
    const list = d.series || [];
    if (!list.length || list.every((s) => s.values.every((v) => v == null) && !(s.replay || []).some((v) => v != null))) {
      box.replaceChildren(h("p", { class: "muted small" }, `Nothing measured in ${windowSaid(d)}.`));
      return;
    }
    const modelled = list.some((s) => s.replay);
    box.replaceChildren(...list.map((s, i) => lineChart({
      group, name: i === 0 ? (s.kind === "flow" ? "rate" : "value") : s.name,
      role: i === 0 ? (s.kind === "flow" ? s.how : null) : ROLE_WORDS[s.role] || s.role,
      unit: s.unit, per: s.per, times: d.times, values: s.values, since: d.since, until: d.until,
      goal: s.goal, height: i === 0 ? 84 : 52, xAxis: i === list.length - 1, zero: s.kind === "flow",
      replay: s.replay, projection: s.projection, ptimes: d.projection_times,
      href: i === 0 ? null : () => openRef(s.ref) })),
      h("div", { class: "chart-foot" }, h("span", { class: "muted" }, [list.length > 1 ? "Rates per hour, on one time axis" : "",
        modelled ? `dashed: the model's replay; past now, lighter: its projection ${dur(d.horizon)} ahead, ${d.inputs || "inputs held where they were"}` : ""].filter(Boolean).join(". ")), group.when));
  }).catch((e) => box.replaceChildren(h("p", { class: "muted small" }, String(e.message || e))));
  if (!SNAP) rememberChart(ref);
  return box;
}
/* a system's own measures (its show:, else its goals' measures), each a chart on one time axis: what its
   box used to draw as sparklines, now in its panel */
function moduleCharts(n, group = chartGroup("module")) {
  const refs = [...new Set((n.charted || n.measures || []).map((x) => x.part.replace(":", ".")))];
  if (!refs.length) return null;
  const box = h("div", { class: "strip" }, h("div", { class: "muted small" }, "…"));
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
  const chosen = [...(S.sel || [])].map((id) => partRef((g?.nodes || []).find((n) => n.id === id))).filter(Boolean);
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
  const box = h("div", { class: "strip scope" }, h("div", { class: "muted small" }, "…"));
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
      numbers ? dl([["time off", numbers === "new" ? null : `${Math.round((nb.off_share || 0) * 100)}%`],
                    ["back in", numbers === "new" || nb.back_in == null ? null : `${dur(nb.back_in)}, typically (${nb.times_off} times)`],
                    ["saturated", nb.saturated != null ? `${Math.round(nb.saturated * 100)}% of ${u.openings ? "its openings" : "the time"}` : null],
                    ["last decision", nb.last_decision ? `${ago(nb.last_decision.time)}: ${nb.last_decision.decision ?? "–"}` : null]]) : null);
  }).catch((e) => box.replaceChildren(h("p", { class: "muted small" }, String(e.message || e))));
  return box;
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

/* ---------------------------------------------------------------- items: the cumulative flow, the cycle times */

/* a kind's states stacked over the window in state order, the first on top and where they finish at
   the bottom: bands are stocks, their edges' slopes flows. Each state named at the right with its count
   (at the cursor, or now): a click filters the table, as the counts did */
function flowChart(d, group, { chosen = null, onState = null } = {}) {
  const states = d.states, n = d.times.length;
  const ramp = ["--line", "--line-strong", "--muted", "--ink-2"];
  const step = (i) => ramp[Math.min(ramp.length - 1, Math.floor((i / Math.max(1, states.length - 1)) * (ramp.length - 1) + 0.0001))];
  const shade = (i) => tok(step(i));
  // cumulative from the bottom (the last state) up
  const cum = states.map((_, k) => Array.from({ length: n }, (_, i) => states.slice(k).reduce((a, st) => a + d.counts[st][i], 0)));
  const labels = states.map((st, k) => {
    const n0 = h("span", { class: "n" }, String(d.now[st] || 0));
    const a = h("a", { href: "#", class: `stbox${d.now[st] ? " some" : ""}${chosen === st ? " on" : ""}`,
                      onclick: (ev) => { ev.preventDefault(); onState?.(st); } }, h("span", { class: "swatch", style: `background:var(${step(k)})` }), n0, st);
    a.count = n0;
    return a;
  });
  const plotEl = h("div", { class: "chart-plot" });
  const el = h("div", { class: "cfd" }, plotEl, h("div", { class: "cfd-states" }, ...labels.slice()));
  mountPlot(plotEl, (width) => {
    const o = baseOpts({ width, height: 120, group, since: d.since, until: d.until, xAxis: true,
      yRange: (_, lo, hi) => [0, Math.max(1, hi || 1) * 1.05],
      hooks: { setCursor: [(u) => { const i = u.cursor.idx;
        states.forEach((st, k) => { labels[k].count.textContent = String(i == null ? d.now[st] || 0 : d.counts[st][i]); }); }] } });
    o.axes[1].values = (u, vs) => vs.map((v) => (Number.isInteger(v) ? String(v) : ""));
    o.series = [{}, ...states.map((st, k) => ({ stroke: tok("--bg"), width: 1, fill: shade(k), points: { show: false } }))];
    o.cursor.points = { show: false };
    return new uPlot(o, [d.times, ...cum], plotEl);
  });
  return el;
}
/* each finished item: when it finished, and how long it took, with the median dashed */
function cycleChart(d, group) {
  const f = d.finished || [];
  const val = h("span", { class: "chart-val" }, d.median != null ? `median ${dur(d.median)}` : "");
  const plotEl = h("div", { class: "chart-plot" });
  const el = h("div", { class: "chart cycle" }, h("div", { class: "chart-head" }, h("span", { class: "chart-name" }, "Cycle time"),
    h("span", { class: "muted" }, `from arriving to ${d.finished_states.join(" or ")}, ${f.length} finished`), val), plotEl);
  if (!f.length) { plotEl.append(h("div", { class: "muted small" }, `None finished in ${windowSaid(d)}.`)); return el; }
  mountPlot(plotEl, (width) => {
    const o = baseOpts({ width, height: 100, group, since: d.since, until: d.until, xAxis: true, yValues: (v) => (v > 0 ? dur(v) : v === 0 ? "0" : ""),
      yRange: (_, lo, hi) => [0, Math.max(hi || 1, d.median || 0) * 1.1],
      hooks: { draw: [lineLabel(d.median, `median ${dur(d.median)}`)],
               setCursor: [(u) => { const i = u.cursor.idx; val.textContent = i == null ? `median ${dur(d.median)}` : `${f[i].id}: ${dur(f[i].took)}`; }] } });
    o.series = [{}, { stroke: tok("--ink"), width: 0, paths: () => null, points: { show: true, size: 5, fill: tok("--ink"), stroke: tok("--ink") } },
                dashLine()];
    return new uPlot(o, [f.map((x) => x.time), f.map((x) => x.took), f.map(() => d.median)], plotEl);
  });
  return el;
}
