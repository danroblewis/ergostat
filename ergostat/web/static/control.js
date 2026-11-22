/* a loop as a control engineer reads it (api loop-control, ergostat/control): in the panels that are
   already there. A process block's panel: the process identified (K, τ, θ, with how sure, and how it
   was tested), its step response and Bode plot, the proposal to write it into the model or a step test
   to identify it deliberately. A controller's panel: its law with that process, the margins, the
   closed loop's step response and the loop's Bode plot, and a SIMC tuning. The scope: how the loop is
   doing (Harris index, oscillation, settling and overshoot, saturation). Nothing changes until the
   owner accepts. Coloured only from the page's tokens. */
"use strict";

const CTL = new Map();                                    // goal -> its analysis, a few seconds
async function loopControl(goal) {
  const got = CTL.get(goal);
  if (got && Date.now() - got.t < 8000) return got.d;
  const d = await api("loop-control", { goal });
  CTL.set(goal, { t: Date.now(), d });
  return d;
}

const secs = (x) => (x == null ? "–" : x < 600 ? `${fmt(x)} s` : dur(x));
const pmText = (v, se) => (se != null ? `${fmt(v)} ± ${fmt(se)}` : fmt(v));

/* P(s) as MathML: K e^(−θs)/(τs + 1), or k e^(−θs)/s */
function processMath(p, sub) {
  const k = ["mn", fmt(p.K)];
  const delay = p.theta ? ["msup", ["mi", "e"], ["mrow", ["mo", "−"], ["mn", fmt(p.theta)], ["mi", "s"]]] : null;
  const num = delay ? ["mrow", k, ["mo", "⁢"], delay] : k;
  const den = p.form === "integrating" ? ["mi", "s"] : ["mrow", ["mn", fmt(p.tau)], ["mi", "s"], ["mo", "+"], ["mn", "1"]];
  return mathml(["mrow", ["msub", ["mi", "P"], ["mtext", sub]], ["mo", "("], ["mi", "s"], ["mo", ")"], ["mo", "="], ["mfrac", num, den]]);
}

/* ---- charts with an axis of their own: seconds after a step, or frequency */
const decade = (v) => v != null && v > 0 && Math.abs(Math.log10(v) - Math.round(Math.log10(v))) < 1e-6;
const logTicks = (u, vs) => vs.map((v) => (decade(v) ? fmt(v) : ""));       // a log axis named at its decades only
function xyOpts({ width, height, xlog = false, ylog = false, xValues = null, yValues = null, xRange = null, yRange = null, hooks = {} }) {
  const font = `${tok("--canvas-sm")} ${tok("--font")}`;
  const axis = { stroke: tok("--muted"), font, grid: { stroke: tok("--line"), width: 1 }, ticks: { show: false }, gap: 4 };
  return {
    width, height, padding: [6, 8, 0, 0], legend: { show: false },
    cursor: { drag: { x: false, y: false, setScale: false }, y: false, points: { show: false } }, select: { show: false },
    scales: { x: { time: false, distr: xlog ? 3 : 1, ...(xRange ? { range: xRange } : {}) },
              y: { distr: ylog ? 3 : 1, ...(yRange ? { range: yRange } : {}) } },
    axes: [{ ...axis, size: 22, space: 56, values: xValues || (xlog ? logTicks : (u, vs) => vs.map((v) => (v == null ? "" : fmt(v)))) },
           { ...axis, size: 48, space: 24, values: yValues || (ylog ? logTicks : (u, vs) => vs.map((v) => (v == null ? "" : fmt(v)))) }],
    hooks,
  };
}
function vline(x, text) {                                   // a mark at one x: a crossover, where the record held out starts
  return (u) => {
    if (x == null) return;
    const ctx = u.ctx, { top, height } = u.bbox, px = Math.round(u.valToPos(x, "x", true)) + 0.5;
    ctx.save(); ctx.strokeStyle = tok("--line-strong"); ctx.lineWidth = devicePixelRatio; ctx.setLineDash([3 * devicePixelRatio, 3 * devicePixelRatio]);
    ctx.beginPath(); ctx.moveTo(px, top); ctx.lineTo(px, top + height); ctx.stroke();
    if (text) {
      ctx.setLineDash([]); ctx.font = `${parseFloat(tok("--canvas-sm")) * devicePixelRatio}px ${tok("--font")}`;
      ctx.textAlign = "left"; ctx.textBaseline = "top"; ctx.fillStyle = tok("--muted");
      ctx.lineWidth = 3 * devicePixelRatio; ctx.strokeStyle = tok("--chrome");
      ctx.strokeText(text, px + 3 * devicePixelRatio, top + 2 * devicePixelRatio); ctx.fillText(text, px + 3 * devicePixelRatio, top + 2 * devicePixelRatio);
    }
    ctx.restore();
  };
}
function chartBox(name, role, plotEl, val = null) {
  return h("div", { class: "chart" }, h("div", { class: "chart-head" }, h("span", { class: "chart-name" }, name),
    role ? h("span", { class: "muted" }, role) : null, val), plotEl);
}

/* a step response: y against the seconds after the step, the final value dashed; a second response dashed */
function stepChart(name, role, st, { other = null, final = null, label = "" } = {}) {
  const plotEl = h("div", { class: "chart-plot" });
  const said = [st.overshoot != null ? `overshoot ${Math.round(st.overshoot * 100)}%` : null,
                st.settling != null ? `settles in ${secs(st.settling)}` : st.settled === false ? "does not settle in view" : null].filter(Boolean).join(", ");
  const el = chartBox(name, role, plotEl, h("span", { class: "chart-val" }, said));
  mountPlot(plotEl, (width) => {
    const xs = st.t, data = [xs, st.y], series = [{}, inkLine()];
    if (other) { data.push(xs.map((t) => interp(other.t, other.y, t))); series.push(replayLine()); }
    if (final != null) { data.push(xs.map(() => final)); series.push(dashLine()); }
    const o = xyOpts({ width, height: 84, xValues: (u, vs) => vs.map((v) => (v == null ? "" : v ? (v < 600 ? `${fmt(v)}s` : dur(v)) : "0")),
      hooks: { draw: final != null ? [lineLabel(final, label)] : [] } });
    o.series = series;
    return new uPlot(o, data, plotEl);
  });
  return el;
}
function interp(ts, ys, t) {
  if (!ts.length || t > ts[ts.length - 1]) return null;
  let i = 0;
  while (i < ts.length - 1 && ts[i + 1] < t) i++;
  const t0 = ts[i], t1 = ts[i + 1] ?? t0;
  return t1 === t0 ? ys[i] : ys[i] + (ys[i + 1] - ys[i]) * (t - t0) / (t1 - t0);
}

/* the Bode plot: magnitude (a ratio, on a log axis) and phase (degrees) against frequency (rad/s, log) */
function bodeCharts(b, m, { loop = false } = {}) {
  const ws = b.w, main = loop && b.loop ? b.loop : b.process, second = loop && b.closed ? b.closed : null;
  const magEl = h("div", { class: "chart-plot" }), phEl = h("div", { class: "chart-plot" });
  const what = loop ? "L = CP, the loop opened; dashed T = L/(1 + L), closed" : "P(jω)";
  const out = h("div", {}, chartBox("|·|", what, magEl), chartBox("∠", "phase, degrees; ω in rad/s", phEl));
  const wc = m?.crossover, w180 = m?.phase_crossover;
  mountPlot(magEl, (width) => {
    const data = [ws, main.mag], series = [{}, inkLine()];
    if (second) { data.push(second.mag); series.push(replayLine()); }
    if (loop) { data.push(ws.map(() => 1)); series.push(dashLine()); }
    const o = xyOpts({ width, height: 96, xlog: true, ylog: true, xValues: (u, vs) => vs.map(() => ""),
      hooks: { draw: [...(loop ? [lineLabel(1, "1")] : []), vline(wc, wc ? `ωc ${fmt(wc)}` : "")] } });
    o.series = series;
    return new uPlot(o, data, magEl);
  });
  mountPlot(phEl, (width) => {
    const data = [ws, main.phase], series = [{}, inkLine()];
    if (second) { data.push(second.phase); series.push(replayLine()); }
    data.push(ws.map(() => -180)); series.push(dashLine());
    const o = xyOpts({ width, height: 84, xlog: true, yValues: (u, vs) => vs.map((v) => `${Math.round(v)}°`),
      hooks: { draw: [lineLabel(-180, "−180°"), vline(w180, w180 ? `ω180 ${fmt(w180)}` : "")] } });
    o.series = series;
    return new uPlot(o, data, phEl);
  });
  return out;
}

/* y as measured, and the model's own simulation (ŷ, dashed) from u and the measured inputs beside it,
   with u's own part dotted when there are any; where the record held out starts is marked */
function validationChart(d) {
  const rec = d.record;
  if (!rec?.yhat) return null;
  const plotEl = h("div", { class: "chart-plot" });
  const r = d.identified || {};
  const role = rec.yhat_u ? "measured; dashed, the model driven by u and the measured inputs; dotted, u's own part"
    : "measured, and the model driven by u (dashed)";
  const el = chartBox("y and ŷ", role, plotEl);
  const group = chartGroup("ident");
  const mark = (r.tests_used || []).length > 1 ? "the last test, held out" : r.test ? "stepped back" : "held out";
  mountPlot(plotEl, (width) => {
    const o = baseOpts({ width, height: 84, group, since: rec.since, until: rec.until, xAxis: true,
      hooks: { draw: [vline(rec.held_from, mark)] } });
    o.series = [{}, inkLine(), replayLine(), ...(rec.yhat_u ? [projectionLine()] : [])];
    return new uPlot(o, [rec.t, rec.y, rec.yhat, ...(rec.yhat_u ? [rec.yhat_u] : [])], plotEl);
  });
  return el;
}

/* ---- the proposals: what changes, why, the edit, and the owner's answer */
function controlProposal(x, goal, onDone) {
  const said = h("p", { class: "small" });
  const test = x.kind === "step-test";
  const accept = h("button", { onclick: () => answer("accept") }, test ? "Approve" : "Accept");
  const dismiss = h("button", { class: "ghost", onclick: () => answer("dismiss") }, "Dismiss");
  async function answer(what) {
    accept.disabled = dismiss.disabled = true;
    said.textContent = what === "accept" ? (test ? "Approving…" : "Applying the edit…") : "";
    try {
      const got = await apiPost(`control/${encodeURIComponent(x.id)}/${what}`);
      said.className = "small";
      said.textContent = what === "dismiss" ? "Dismissed: it is not offered again until the loop changes in the model."
        : test ? "Approved: ergostat runs it now, and the record will show it." :
          `Accepted: ${(got.edit?.files || []).map((f) => Path(f.file)).join(", ")} changed.`;
      CTL.delete(goal);
      S.graphSig = "";
      onDone?.(what);
    } catch (e) {
      said.className = "s-open small";
      said.textContent = String(e.message || e);
      accept.disabled = dismiss.disabled = false;
    }
  }
  const kind = { process: "Proposed process", tuning: "Proposed tuning", "step-test": "Proposed step test" }[x.kind] || "Proposed";
  return h("div", { class: "proposal" },
    h("div", { class: "proposal-title" }, h("span", { class: "muted small" }, kind), h("div", {}, x.title)),
    h("p", { class: "muted small" }, x.reason),
    x.edit?.diff ? h("pre", { class: "diff" }, x.edit.diff.split("\n").map((l) => h("div", { class: l.startsWith("+") ? "add" : l.startsWith("-") ? "del" : "muted" }, l))) : null,
    SNAP ? h("p", { class: "muted small" }, "Answered where the model is, not in a snapshot.") : h("div", { class: "actions" }, accept, dismiss),
    said);
}

/* ---- what is known of the process, in words */
function identRows(d) {
  const r = d.identified || {};
  const se = r.se || {};
  if (!r.found) return [];
  return [["gain K", pmText(r.K, se.K)], ["time constant τ", r.form === "integrating" ? "none: an integrator" : `${pmText(r.tau, se.tau)} s`],
    ["dead time θ", `${pmText(r.theta, se.theta)} s`],
    ["fit", r.fit_val != null ? `${Math.max(0, Math.round(r.fit_val))}% of the record held out, of the ${Math.max(0, Math.round(r.fit_best ?? 0))}% its noise allows; ${Math.max(0, Math.round(r.fit_est ?? 0))}% of what it was fitted to` : null],
    ["left", r.rms_val != null && r.noise ? `${fmt(r.rms_val / r.noise)} × the noise, of the record held out` : null],
    ["from", `${(r.tests_used || []).length > 1 ? `${r.tests_used.length} step tests, fitted together (open loop)` : r.test ? "a step test (open loop)" : "the loop working (closed loop)"}, ${dur(r.span)}, ${r.n_est} readings fitted, ${r.n_val} held out${r.moves ? `, u stepped ${r.moves} time${r.moves === 1 ? "" : "s"}` : ""}`],
    ["errors held out", r.whiteness ? `${r.whiteness.white ? "white" : "not white"} (Ljung–Box Q ${fmt(r.whiteness.q)} against ${fmt(r.whiteness.limit)}, ${r.whiteness.lags} lags)` : null],
    ["against u", r.independence ? (r.independence.ok ? "independent of u" : `not independent (cross-correlation ${fmt(r.independence.max)}, past ±${fmt(r.independence.bound)})`) : null],
    ["also fitted", Object.keys(r.gains || {}).length ? Object.entries(r.gains).map(([k, v]) => `${k.split(".").slice(1).join(".")} ×${fmt(v)}`).join(", ") : null]];
}

function processSection(d, done) {
  if (d.why) return [h("p", { class: "muted small" }, `The loop ${d.goal}: ${d.why}.`)];
  const kids = [h("h3", { "data-goal": d.goal }, `The loop ${d.goal}, from u to y`)];
  const u = (d.u || "").split(".").slice(1).join("."), y = (d.y || "").split(".").slice(1).join(".");
  kids.push(h("p", { class: "muted small" }, `u: ${u} (${d.how === "valve" ? "what its valve moves, a rate" : "the setting its controller steps"}); y: ${y}.`));
  if (d.known) kids.push(h("p", { class: "small" }, d.known + "."));
  if (d.declared) {
    kids.push(h("div", { class: "bd-math" }, processMath(d.process, d.goal)),
      h("p", { class: "muted small" }, d.declared.identified ? `In the model, identified ${d.declared.identified}.` : "In the model, declared."));
  }
  const r = d.identified || {};
  if (r.found) {
    const from = { form: r.form, K: r.K, tau: r.tau, theta: r.theta };
    kids.push(h("p", { class: "small" }, d.declared ? "The record now says:" : r.proposable ? "Identified from the record:" : "The record's best guess, not proposed:"),
      h("div", { class: "bd-math" }, processMath(from, d.goal)), dl(identRows(d)));
    if (!r.proposable) kids.push(h("p", { class: "muted small" }, `Not proposed: ${(r.why || []).join("; ")}.`));
    const o = r.instead_of;
    if (o) kids.push(h("p", { class: "muted small" }, `From ${o.from} instead: K ${fmt(o.K)}${o.tau != null ? `, τ ${fmt(o.tau)} s` : ""}, θ ${fmt(o.theta)} s` +
      (o.fit_val != null ? `, ${Math.max(0, Math.round(o.fit_val))}% of its record held out` : "") + "."));
    const v = validationChart(d);
    if (v) kids.push(v);
  } else if (!d.known) {
    kids.push(h("p", { class: "muted small" }, `Not identified: ${(r.why || []).join("; ") || "nothing to read"}.`));
  }
  if (d.process) {
    kids.push(stepChart("y", "u stepped by 1", d.process_step,
                        { final: d.process.form === "fopdt" ? d.process.K : null, label: d.process.form === "fopdt" ? `K ${fmt(d.process.K)}` : "" }));
    kids.push(bodeCharts(d.bode, null));
  }
  for (const t of (d.tests || []).slice(-3)) kids.push(h("p", { class: "muted small" },
    `Step test ${t.id}: started ${ago(t.started)}${t.from != null ? ` from ${fmt(t.from)}` : ""}${t.finished ? `, ${t.how}` : ", running"}.`));
  if (d.step_test_waiting) kids.push(h("p", { class: "muted small" }, `No step test yet: ${d.step_test_waiting}.`));
  if (d.step_test_refused) kids.push(h("p", { class: "muted small" }, `No step test: ${d.step_test_refused}.`));
  for (const x of (d.proposals || []).filter((p) => p.kind !== "tuning")) kids.push(controlProposal(x, d.goal, done));
  return kids;
}

function controllerSection(d, done) {
  const kids = [h("h3", { "data-goal": d.goal }, `With the loop ${d.goal}'s process`)];
  const c = d.controller || {};
  if (!c.law) {
    kids.push(h("p", { class: "muted small" }, `${c.says || "Its law is not known"}: no closed loop worked out.`));
  } else if (!d.process) {
    kids.push(h("p", { class: "muted small" }, `Its process is not identified yet, so no margins, closed-loop step or tuning: ${d.step_test_waiting ? "a step test is offered once the loop is steady" : (d.proposals || []).some((x) => x.kind === "step-test") ? "the process's panel offers a step test" : "the process's panel says what would identify it"}.`));
    if (d.robust) kids.push(dl([["at the worst", robustText(d.robust)]]));
  } else {
    const m = d.margins || {};
    const weak = (m.phase_margin ?? 90) < 30 || (m.ms ?? 0) > 2;
    kids.push(h("p", { class: "muted small" }, d.process_from === "model" ? "With the process in the model." :
      "With the process the record suggests, not yet in the model."),
      dl([["gain margin", m.gain_margin != null ? `${fmt(m.gain_margin)}×` : "no phase crossover"],
          ["phase margin", m.phase_margin != null ? `${fmt(m.phase_margin)}°` : "no gain crossover"],
          ["delay margin", m.delay_margin != null ? secs(m.delay_margin) : null],
          ["Ms", m.ms != null ? `${fmt(m.ms)} (the sensitivity's peak)` : null],
          ["closed loop", m.stable === false ? h("span", { class: "s-off" }, "does not settle")
            : weak ? h("span", { class: "s-open" }, `settles, but not robustly: ${(m.ms ?? 0) > 2 ? "Ms past 2" : "phase margin under 30°"} (the textbooks' limits: Ms 1.2 to 2, phase margin 30° or more)`) : "settles"],
          ["its own delay", c.law.delay ? `${secs(c.law.delay)}: the reading it acts on ${secs(c.law.age || 0)} old, its run ${secs(c.law.run || 0)}; added to θ` : null],
          ["at the worst", d.robust ? robustText(d.robust) : null]]));
    for (const x of d.nonlinear || []) kids.push(h("p", { class: "muted small" }, `Left out: ${x}.`));
    const t = d.tuning || {};
    kids.push(stepChart("y", t.step ? "r stepped by 1; dashed: SIMC" : "r stepped by 1", d.closed_step, { other: t.step, final: 1, label: "r" }));
    kids.push(bodeCharts(d.bode, m, { loop: true }));
  }
  const t = d.tuning || {};
  if (t.simc) {
    const s = t.simc, tm = t.margins || {};
    kids.push(h("p", { class: "small" }, `SIMC (Skogestad): ${s.form === "I" ? `gain ${fmt(s.g)} a step (K_I ${fmt(s.Ki)}/s)` : `K_c ${fmt(s.Kc)}${s.Ti ? `, τ_I ${secs(s.Ti)}` : ""}`}, τ_c ${secs(s.tc)}; ` +
      `gain margin ${fmt(tm.gain_margin)}×, phase margin ${fmt(tm.phase_margin)}°, Ms ${fmt(tm.ms)}.`));
    if (t.why) kids.push(h("p", { class: "muted small" }, `Not proposed: ${t.why}.`));
  } else if (t.why && c.law) kids.push(h("p", { class: "muted small" }, `No tuning: ${t.why}.`));
  if (t.detune) {
    const dc = t.detune.controller, rb = t.detune.robust || {};
    kids.push(h("p", { class: "small" }, `Detuned for robustness: ${dc.form === "I" ? `gain ${fmt(dc.g)} a step` : `K_c ${fmt(dc.Kc)}`}; ` +
      `at the worst the process could be, gain margin ${fmt(rb.gain_margin)}×, phase margin ${fmt(rb.phase_margin)}°.`));
  }
  for (const x of (d.proposals || []).filter((p) => p.kind === "tuning")) kids.push(controlProposal(x, d.goal, done));
  return kids;
}

/* the loop's margins at the worst its process could be, in words */
function robustText(rb) {
  if (!rb.known) return rb.why;
  const se = rb.se || {};
  const word = rb.stable ? (rb.gain_margin != null && rb.gain_margin < 2 ? "stable, but with little to spare" : "robustly stable") : "may be unstable";
  const span = `over K ± 2σ, θ + 2σ${se.tau != null ? ", τ ± 2σ" : ""} (σ: K ${fmt(se.K)}, θ ${secs(se.theta)})`;
  const cls = rb.stable ? (rb.gain_margin != null && rb.gain_margin < 2 ? "s-open" : null) : "s-off";
  return h("span", {}, h("span", cls ? { class: cls } : {}, word), `: gain margin ${rb.gain_margin != null ? fmt(rb.gain_margin) + "×" : "–"}, ` +
    `phase margin ${rb.phase_margin != null ? fmt(rb.phase_margin) + "°" : "–"}, Ms ${fmt(rb.ms)}, ${span}`);
}

/* how the loop is doing, under its scope */
function performanceRows(d) {
  const pf = d.performance || {};
  const hr = pf.harris || {}, os = pf.oscillation || {}, ex = pf.excursions || {};
  const harris = hr.index != null ? `${fmt(hr.index)}; at 1 it leaves no more variance than the best controller could, given the dead time` : hr.why;
  const osc = os.oscillating ? `yes: every ${secs(os.period)}, ±${fmt(os.amplitude)} (regularity ${fmt(os.regularity)})`
    : os.crossings != null ? "no" : null;
  const cn = pf.constraint;
  const nl = d.predicted?.nonlinear?.length ? "; linear, the dead band and the setting's steps left out (the controller's panel says what they do)" : "";
  return [["Harris index", harris], ["past its bound", cn ? `${Math.round(cn.share * 100)}% of the time (${Math.round(cn.share_off * 100)}% past its tolerance), by ${fmt(cn.mean)} typically, ${fmt(cn.worst)} at worst` : null],
    ["oscillating", osc],
    ["settles", ex.count ? `in ${secs(ex.settling)}, typically (slowest ${secs(ex.slowest)}, ${ex.count} times)` : null],
    ["overshoot", ex.overshoot != null ? `${Math.round(ex.overshoot * 100)}% past the setpoint, typically` : null],
    ["saturated", pf.saturation != null ? `${Math.round(pf.saturation * 100)}% of the ${d.how === "valve" ? "openings, at its most" : "time, at a limit"}` : null],
    ["left out", pf.left_out ? `${dur(pf.left_out)} of step tests and starts` : null],
    ["predicted", d.predicted && d.predicted.overshoot != null ? `for a step of r: overshoot ${Math.round(d.predicted.overshoot * 100)}%, ` +
      (d.predicted.settling != null ? `settling in ${secs(d.predicted.settling)}` : "not settled in view") + nl : null]];
}

/* the box each place shows: "process", "controller", "scope", or "loop" (the Loops page's panel) */
function controlBox(goal, part, { block = null } = {}) {
  const box = h("div", { class: "control" });
  const draw = () => loopControl(goal).then((d) => {
    if (!d) return box.replaceChildren();
    if (part === "controller" && block && d.controller?.block !== block && !(d.controllers || []).includes(block)) return box.replaceChildren();
    const done = () => { CTL.delete(goal); draw(); };
    const kids = part === "process" ? processSection(d, done) : part === "controller" ? controllerSection(d, done)
      : part === "scope" ? [h("h3", {}, "How it is doing"), performanceRows(d).some(([, v]) => v != null && v !== "") ? dl(performanceRows(d))
          : h("p", { class: "muted small" }, d.why ? "Not worked out: it has no one process." : "Not worked out yet: too little record since the loop started (its first ten controller periods, two minutes at least, are left out).")]
      : [...processSection(d, done), ...(d.controller?.law ? controllerSection(d, done) : [])];
    box.replaceChildren(...kids);
  }).catch((e) => box.replaceChildren(h("p", { class: "muted small" }, String(e.message || e))));
  draw();
  return box;
}

/* one word or two for the Loops page: how the loop is doing */
function performanceWord(d) {
  if (!d) return "";
  if (d.why) return "no one process";
  const pf = d.performance || {};
  if (pf.oscillation?.oscillating) return `oscillates, ${secs(pf.oscillation.period)}`;
  if (pf.saturation != null && pf.saturation > 0.2) return `saturated ${Math.round(pf.saturation * 100)}%`;
  if (pf.constraint) return pf.constraint.share ? `past its bound ${Math.round(pf.constraint.share * 100)}%` : "within its bound";
  if (pf.harris?.index != null) return `Harris ${fmt(pf.harris.index)}`;
  if (pf.harris?.short) return "too little record";
  if (pf.harris?.needs_theta) return "needs θ";
  return "";
}
