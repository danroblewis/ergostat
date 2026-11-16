/* the detail panel: a part, a loop or an agent, with its charts */
"use strict";
/* ------------------------------------------------------------------ details */

function closeDetail() { if (S.selKey) { S.selKey = null; trace(S.hoverKey); } const d = $("#detail"); d.hidden = true; d.replaceChildren(); for (const n of document.querySelectorAll(".node.sel")) n.classList.remove("sel"); }
function showDetail(...kids) {
  if (S.selKey) { S.selKey = null; trace(S.hoverKey); }  // another detail: the line chosen before lets go
  const d = $("#detail");
  d.replaceChildren(h("button", { class: "close", onclick: closeDetail }, "close"), ...kids.filter((k) => k != null && k !== false));
  d.hidden = false;
}
/* what each kind of thing on the diagram is: said first, in plain words, before how it is now */
const WHAT = {
  stock: ["Stock", "something that accumulates. It rises and falls only by its flows, and its level is what a goal holds."],
  variable: ["Variable", "something measured or set that does not accumulate: a score, a ratio, a setting. No flow fills it. Measured, it is a loop's process variable (what a goal holds); set by a block, it is a manipulated variable, a knob the loop turns."],
  valve: ["Flow, controlled (a valve)", "material moving into or out of a stock, set by something in the model: a block opens it when its controller commands."],
  disturbance: ["Flow, uncontrolled (a disturbance)", "material moving into or out of a stock that nothing in the model sets. The world pushes it; the loops on its stocks must make up for it."],
  sensor: ["Sensor", "an instrument. It reads one stock or flow; a loop sees only what its sensor reads."],
  controller: ["Controller", "the part that decides, to hold a goal. At its summing point (the Σ in its corner) it compares the stock's reading y with the setpoint r: e = r − y. While that error says the goal is off, it commands a valve. The badge names the block that fills it. With its sensor, the stock and the valve it closes a feedback loop: the loop is the whole cycle, not this box."],
  loop: ["Feedback loop", "a goal on a stock and what serves it. When the stock's reading is off the setpoint, the controller commands a valve until it is back."],
  system: ["System", "a part of the model drawn as one part. Its ports are what crosses its edge: what it reads and is told, what it moves and drives."],
  agent: ["Agent", "the program, AI or person that does a part's work: reads a sensor, decides as a controller, or opens a valve."],
  pipe: ["Flow (material)", "the pipe a flow runs along: material leaving one stock and arriving in another (or coming from or going to outside the model). Only flows change stocks."],
  measure: ["Measurement (information)", "a sensor reading a stock or flow: the measured output, y. The arrow points into the sensor because that is the way the information goes: the stock's level is what the sensor reports. It moves nothing; it only tells."],
  signal: ["Feedback (information)", "a sensor's reading going to a controller, which compares it with its setpoint r and acts on the error e = r − y. This is what makes the loop a loop."],
  action: ["Control action (information)", "a controller commanding a valve: the control signal, u. How hard it pushes is the loop's gain; how long until the stock shows it is the loop's delay."],
  influence: ["Influence (information)", "one thing's rate following another's, declared with driven-by: a release fixing what was broken, more users asking for more. Nothing moves along it; it is how a loop closes through another system."],
  wire: ["Wire (who reaches whom)", "one agent's output reaching another: through a stock one changes and the other measures, a reading handed to a controller, a decision handed to a valve, or an event."],
};
const DRAWN = {
  pipe: "a thick double line; it runs with blue dots while material moves along it (orange edged and dotted when nothing controls it)",
  measure: "a blue dotted line, from what is read to the sensor",
  signal: "a blue line, from the sensor to the controller",
  action: "a purple line, from the controller to the valve it opens",
  influence: "an orange dashed line, from what drives to the flow that follows",
  wire: "a blue line between agents, labelled with what joins them",
};
function whatIs(kind) {
  const w = WHAT[kind];
  return w ? h("p", { class: "what" }, h("b", {}, w[0]), ": ", w[1]) : null;
}

function dl(pairs) { return h("dl", {}, pairs.filter(([, v]) => v != null && v !== "").flatMap(([k, v]) => [h("dt", {}, k), h("dd", {}, v)])); }
function agentLink(a) { return a ? h("a", { href: "#", onclick: (ev) => { ev.preventDefault(); openAgent(a.name); } }, `${a.name} (rung ${a.rung} ${a.kind})`) : h("span", { class: "muted" }, "unfilled"); }

function openSystem(n) {                               // a system as one part: what goes in and out, and how its loops do
  const side = (d) => (n.ports || []).filter((p) => p.side === d);
  const list = (ps, none) => ps.length ? h("table", {}, ps.map((p) => h("tr", {}, h("td", {}, p.label), h("td", { class: "muted" }, p.kind),
    h("td", { class: "num" }, p.value || "")))) : h("p", { class: "muted" }, none);
  showDetail(h("div", { class: "kind" }, "system"), h("h2", {}, n.label, " ", n.status ? statusEl(n.status) : null), whatIs("system"),
    n.description ? h("p", { class: "muted" }, n.description) : null,
    dl([["loops", loopsText(n)], ["inside", n.subsystems?.length ? n.subsystems.join(", ") : null],
        ["inner loop", n.inner?.length ? `given a setpoint for ${n.inner.join(", ")} from outside, it holds it: an outer loop can treat it as one block` : null]]),
    h("h3", {}, "in: what reaches it from outside"), list(side("in"), "nothing outside reaches in (here)"),
    h("h3", {}, "out: what it reaches outside"), list(side("out"), "nothing outside sees it (here)"),
    h("p", {}, h("button", { onclick: () => S.toggleSystem?.(n.label) }, "▸ open it here"), " ",
               h("button", { onclick: () => S.drill?.(n.label) }, "⤓ draw it alone")),
    h("p", { class: "muted small" }, "Its ports are worked out from the model: every part outside that it reads, sets, feeds or is driven by. ",
      h("code", {}, `ergostat explain system.${n.label}`), " says the same in sentences."));
}

async function openNode(n) {
  for (const x of document.querySelectorAll(".node.sel")) x.classList.remove("sel");
  document.querySelector(`.node[data-id="${CSS.escape(n.id)}"]`)?.classList.add("sel");
  if (n.kind === "agent") return openAgent(n.label);
  if (n.kind === "system") return openSystem(n);
  const [kind, name] = n.kind === "valve" ? ["valve", n.label] : n.kind === "disturbance" ? ["disturbance", n.flow] : n.id.split(":");
  if (kind === "controller") return openLoop(name, true);
  const d = await api(`part/${kind}/${encodeURIComponent(name)}`);
  const m = d.model, now = d.now || {};
  const rows = [["description", m.description]];
  if (kind === "stock") rows.push(["now", `${fmt(now.value)} ${m.unit}`], ["measured", now.at ? `${ago(now.at)} by ${now.sensor}` : "never"],
                                  ["in", `${fmt(now.inflow)}/h`], ["out", `${fmt(now.outflow)}/h`]);
  if (kind === "disturbance") rows.push(["pushes", m.target ? `into ${m.target}` : `out of ${m.source}`], ["rate", `${fmt(now.rate)}/h`], ["how we know", now.how]);
  if (kind === "valve") rows.push(["acts on", m.flow], ["mode", m.mode], ["most a run", m.max != null ? fmt(m.max) : null],
                                  ["filled by", agentLink(d.agent)], ["rate", `${fmt(now.flow?.rate)}/h`]);
  const rd = now.readings || [], last = rd[rd.length - 1];
  if (kind === "sensor") rows.push(["measures", m.measures], ["filled by", agentLink(d.agent)],
                                   ["last reading", last ? `${fmt(last[1])}, ${ago(last[0])}` : "none yet"], ["in the window", `${now.count ?? rd.length} readings`]);
  const shown = n.kind === "variable" ? "variable" : kind;
  if (n.kind === "variable") for (let i = rows.length - 1; i >= 0; i--) if (rows[i][0] === "in" || rows[i][0] === "out") rows.splice(i, 1);
  if (n.kind === "variable" && n.agent) rows.push(["set by", agentLink(n.agent)]);
  const kids = [h("div", { class: "kind" }, shown), h("h2", {}, name), whatIs(shown), h("h3", {}, "how it is now"), dl(rows)];
  if (kind === "stock" && now.points?.length > 1) kids.push(sparkSvg(now.points, 380, 70));
  if (kind === "sensor" && now.readings?.length > 1) kids.push(sparkSvg(now.readings, 380, 70));
  if (kind === "sensor" && rd.length) {
    kids.push(h("h3", {}, "its last readings"), h("table", {}, rd.slice(-10).reverse().map(([t, v]) =>
      h("tr", {}, h("td", { class: "num nowrap" }, new Date(t * 1000).toLocaleTimeString([], { hour12: false })), h("td", { class: "num" }, fmt(v))))));
  }
  if (kind === "valve") {
    // one row per run that opened it (an agent may report each thing it moves on its own line)
    const runs = [];
    for (const e of (now.openings || []).slice().reverse()) {
      const last = runs[runs.length - 1];
      if (last && e.causedby && last.causedby === e.causedby) { last.n += 1; last.amount += e.data.amount ?? 1; continue; }
      runs.push({ causedby: e.causedby, time: e.time, n: 1, amount: e.data.amount ?? 1, source: e.source, note: e.data.note });
    }
    kids.push(h("h3", {}, "recent openings, by run"));
    kids.push(h("table", {}, runs.slice(0, 12).map((r) => h("tr", {},
      h("td", { class: "num nowrap" }, new Date(r.time * 1000).toLocaleTimeString([], { hour12: false })),
      h("td", { class: "num" }, fmt(r.amount)), h("td", { class: "muted" }, `${r.n > 1 ? `in ${r.n} openings · ` : ""}${r.source}${r.note ? " · " + r.note : ""}`)))));
  }
  kids.push(h("p", {}, h("a", { href: `#/diagram?around=${kind}/${encodeURIComponent(name)}` }, "draw what is around it")));
  showDetail(...kids);
}

async function openLoop(name, asController = false) {
  let lp;
  try { lp = await api(`loops/${encodeURIComponent(name)}`); } catch (e) { return; }
  const recorded = Math.min(lp.until - lp.since, S.status?.first ? lp.until - S.status.first : Infinity);
  const windowWords = recorded < (lp.until - lp.since) * 0.95 ? `of the ${dur(recorded)} recorded` : "of the window";
  const kids = asController
    ? [h("div", { class: "kind" }, "controller"), h("h2", {}, name, " ", statusEl(lp.status)), whatIs("controller"),
       h("h3", {}, "the loop it closes"), whatIs("loop")]
    : [h("div", { class: "kind" }, lp.open_loop ? "loop · ⏲ open loop" : "loop"), h("h2", {}, name, " ", statusEl(lp.status)), whatIs("loop")];
  if (lp.description) kids.push(h("p", { class: "muted" }, lp.description));
  if (lp.open_loop) kids.push(h("p", {}, "An open loop: it acts on its schedule and reads nothing; its sensor only watches it against the setpoint."));
  kids.push(dl([["holds", `${lp.stock} ${lp.setpoint}${lp.band || ""}`], ["now", fmt(lp.value)],
    ["error", lp.error ? fmt(lp.error) : "0"], ["time off", `${Math.round((lp.off_share || 0) * 100)}% ${windowWords}`],
    ["typically", lp.answers_in != null || lp.back_in != null ? [
      lp.answers_in != null ? `its valve opens ${dur(lp.answers_in)} after it goes off` : null,
      lp.back_in != null ? `it holds again ${dur(lp.back_in)} after (slowest ${dur(lp.back_in_slowest)}, ${lp.times_off} times)` : null,
    ].filter(Boolean).join("; ") : null],
    ["moves", lp.flows.map((f) => `${f} ${fmt(lp.rates?.[f])}/h`).join(", ") || "none"],
    ["cycled", lp.observed ? "yes, in this window" : "not in this window"]]));
  // each part along the loop, who fills it, and what it last did: as `ergostat loop NAME`
  kids.push(h("table", { class: "parts" }, h("tr", {}, ["part", "name", "filled by", "last"].map((x) => h("th", {}, x))),
    (lp.parts || []).map((pt) => h("tr", {}, h("td", {}, pt.kind), h("td", {}, h("b", {}, pt.name),
        pt.kind === "valve" ? h("span", { class: "muted" }, ` (${pt.mode}${pt.max ? `, ≤ ${fmt(pt.max)} a run` : ""})`) : null),
      h("td", {}, agentLink(pt.agent)),
      h("td", {}, pt.kind === "sensor" ? (pt.last ? `read ${ago(pt.last.time)}: ${fmt(pt.last.value)}` : h("span", { class: "muted" }, "no reading yet"))
        : pt.kind === "controller" ? (pt.last ? `decided ${ago(pt.last.time)}: ${pt.last.data.decision}`
          : h("span", { class: "muted" }, pt.open_loop ? "acts on its schedule, reads nothing" : "no decision yet"))
        : (pt.last ? `opened ${ago(pt.last.time)}: ${fmt(pt.last.amount)}${pt.last.count > 1 ? ` in ${pt.last.count} openings` : ""}`
          : h("span", { class: "muted" }, "never opened")))))));
  if ((lp.points || []).length > 1) kids.push(trendChart(lp, 400, 170));
  if (lp.openings_total > (lp.openings || []).length) kids.push(h("div", { class: "muted small" }, `ticks: ${lp.openings.length} of its ${lp.openings_total} openings, spread over the window`));
  for (const g of lp.gaps || []) kids.push(h("div", { class: "att" }, h("div", {}, h("b", {}, "cannot close: "), g)));
  for (const hint of lp.hints || []) kids.push(h("div", { class: "att" }, h("div", { class: "hint" }, h("b", {}, "hint: "), hint.says)));
  if (lp.crossings?.length) {
    kids.push(h("h3", {}, `crossings${lp.crossings_total > lp.crossings.length ? `, the newest ${lp.crossings.length} of ${lp.crossings_total}` : ""}`));
    kids.push(h("table", {}, lp.crossings.slice().reverse().map((e) => h("tr", {},
      h("td", { class: "num nowrap" }, new Date(e.time * 1000).toLocaleTimeString([], { hour12: false })),
      h("td", {}, statusEl(e.type.split(".")[1])), h("td", { class: "num" }, fmt(e.data.value)),
      h("td", { class: "muted" }, e.type === "loop.off" && e.data.error != null ? `off by ${fmt(Math.abs(e.data.error))}` : "")))));
  }
  if (lp.decisions?.count) {
    kids.push(h("h3", {}, `decisions (${lp.decisions.count}), alike when only their numbers differ`));
    kids.push(h("table", {}, lp.decisions.kinds.slice(0, 6).map(([w, n]) => h("tr", {}, h("td", { class: "num" }, n), h("td", {}, w.replaceAll("#", "N"))))));
  }
  kids.push(h("p", {}, h("a", { href: `#/diagram?around=loop/${encodeURIComponent(name)}` }, "draw this loop alone")));
  showDetail(...kids);
}

async function openAgent(name) {
  const a = await api(`agents/${encodeURIComponent(name)}`);
  const kids = [h("div", { class: "kind" }, `agent · rung ${a.rung} ${a.kind}`), h("h2", {}, name), whatIs("agent"),
    dl([["description", a.agent.description], ["command", a.agent.command ? h("code", {}, a.agent.command) : null],
        ["runs", a.schedule || "not run by ergostat"],
        ["fills", (a.roles || []).map((r) => `${r.kind} ${r.name}`).join(", ") || "nothing"],
        ["the load", (a.loads || []).map((x) => `disturbance ${x}`).join(", ") || null],
        ["in window", `${a.runs} runs, ${a.failed} failed` + (a.refused ? `, ${a.refused} lines refused` : "") + (a.unread ? `, ${a.unread} unreadable` : "")],
        ["durations", (() => { const ss = (a.recent || []).slice(-40).map((e) => e.data.seconds).filter((x) => x != null);
                               return ss.length ? `${Math.min(...ss)}s to ${Math.max(...ss)}s over its last ${ss.length} runs` : null; })()],
        ["stale", (a.stale || []).length ? `no recent reading from ${a.stale.join(", ")}` : null],
        ["log", a.log_path ? h("code", {}, a.log_path) : null]])];
  if ((a.recent || []).length > 1) kids.push(h("h3", {}, `its last ${a.recent.length} runs`), runsChart(a.recent, 400, 90));
  kids.push(h("h3", {}, "recent runs"));
  kids.push(h("table", {}, h("tr", {}, h("th", {}, "when"), h("th", {}, "result"), h("th", {}, "said")),
    (a.recent || []).slice(-10).reverse().map((e) => h("tr", {}, h("td", {}, ago(e.time)),
      h("td", {}, e.type === "agent.failed" ? h("span", { class: "s-off" }, e.data.note || "failed") : "ok"),
      h("td", { class: "muted" }, `${e.data.readings || 0} readings, ${e.data.openings || 0} openings, ${e.data.decisions || 0} decisions`)))));
  if (a.log?.length) kids.push(h("h3", {}, "end of its log"), h("pre", {}, a.log.slice(-15).join("\n")));
  showDetail(...kids);
}

/* a loop's trend: the stock over the window, the setpoint with its tolerance band, the stretches
   when the loop was off shaded, and a tick on the time axis for each valve opening */
function trendChart(lp, w, hgt) {
  const pad = { l: 36, r: 8, t: 10, b: 22 };
  const t0 = Math.max(lp.since, lp.points[0][0]), t1 = lp.until;
  const vs = lp.points.map((p) => p[1]);
  const spv = setpointOf(lp.setpoint), tol = lp.tolerance || 0;
  let lo = Math.min(...vs, spv ?? Infinity), hi = Math.max(...vs, spv ?? -Infinity);
  if (spv != null) { lo = Math.min(lo, spv - tol); hi = Math.max(hi, spv + tol); }
  const span = (hi - lo) || 1; lo -= span * 0.08; hi += span * 0.08;
  const x = (t) => pad.l + ((t - t0) / ((t1 - t0) || 1)) * (w - pad.l - pad.r);
  const y = (v) => pad.t + (1 - (v - lo) / (hi - lo)) * (hgt - pad.t - pad.b);
  const out = s("svg", { width: w, height: hgt, class: "trend", viewBox: `0 0 ${w} ${hgt}` });
  // off stretches over the whole window (the server reduces them from every crossing)
  for (const [a, b] of lp.off_stretches || []) {
    const xa = x(Math.max(a, t0)), xb = x(Math.min(b, t1));
    if (xb > xa - 1) out.append(s("rect", { x: xa, y: pad.t, width: Math.max(1, xb - xa), height: hgt - pad.t - pad.b, fill: "var(--bad)", opacity: 0.08 }));
  }
  if (spv != null) {
    // the tolerance on the side that matters, as the status reads it: above <=, below >=, both for ==
    const op = (/(<=|>=|==|<|>|=)/.exec(lp.setpoint) || [])[1] || "==";
    const [bLo, bHi] = op.startsWith("<") ? [spv, spv + tol] : op.startsWith(">") ? [spv - tol, spv] : [spv - tol, spv + tol];
    if (tol) out.append(s("rect", { x: pad.l, y: y(bHi), width: w - pad.l - pad.r, height: Math.max(1, y(bLo) - y(bHi)), fill: "var(--warn)", opacity: 0.08 }));
    out.append(s("line", { x1: pad.l, x2: w - pad.r, y1: y(spv), y2: y(spv), stroke: "var(--ok)", "stroke-dasharray": "4 3", "stroke-width": 1.2 }));
    out.append(s("text", { x: w - pad.r - 4, y: y(spv) - 4, "text-anchor": "end", fill: "var(--ok)", "font-size": 10.5, "paint-order": "stroke",
                           stroke: "var(--panel)", "stroke-width": 3 }, (lp.open_loop ? "watched against " : "setpoint ") + lp.setpoint));
  }
  const d = lp.points.map((p, i) => `${i ? "L" : "M"}${x(p[0])},${y(p[1])}`).join("");
  out.append(s("path", { d, fill: "none", stroke: "var(--accent)", "stroke-width": 1.8 }));
  for (const o of lp.openings || []) out.append(s("line", { x1: x(o.time), x2: x(o.time), y1: hgt - pad.b, y2: hgt - pad.b + 6, stroke: "var(--ctl-line)", "stroke-width": 1.4 }, s("title", {}, `${o.valve} opened: ${o.amount}`)));
  out.append(s("line", { x1: pad.l, x2: w - pad.r, y1: hgt - pad.b, y2: hgt - pad.b, stroke: "var(--line)" }));
  const lab = (t, xx, yy, anchor = "start") => s("text", { x: xx, y: yy, "text-anchor": anchor, fill: "var(--muted)", "font-size": 10.5 }, t);
  out.append(lab(fmt(hi - span * 0.08), 0, pad.t + 8), lab(fmt(lo + span * 0.08), 0, hgt - pad.b));
  const tl = (t) => new Date(t * 1000).toLocaleTimeString([], { hour12: false, hour: "2-digit", minute: "2-digit" });
  out.append(lab(tl(t0), pad.l, hgt - 4), lab(tl(t1), w - pad.r, hgt - 4, "end"), lab("valve openings ▮", (w + pad.l) / 2, hgt - 4, "middle"));
  return out;
}

/* an agent's runs as bars: height is how long each took, red when it failed */
function runsChart(runs, w, hgt) {
  const secs = runs.map((e) => e.data.seconds || 0), top = Math.max(...secs, 0.001);
  const bw = Math.max(2, (w - 40) / runs.length - 1);
  const out = s("svg", { width: w, height: hgt, class: "runs" });
  runs.forEach((e, i) => {
    const bh = Math.max(2, (secs[i] / top) * (hgt - 22));
    out.append(s("rect", { x: 36 + i * (bw + 1), y: hgt - 16 - bh, width: bw, height: bh, rx: 1,
                           fill: e.type === "agent.failed" ? "var(--bad)" : (e.data.refused ? "var(--warn)" : "var(--accent)"), opacity: 0.85 },
      s("title", {}, `${new Date(e.time * 1000).toLocaleTimeString([], { hour12: false })}: ${secs[i]}s` +
                     (e.type === "agent.failed" ? ` · ${e.data.note || "failed"}` : "") + (e.data.refused ? ` · ${e.data.refused} refused` : ""))));
  });
  const lab = (t, x, y, a = "start") => s("text", { x, y, "text-anchor": a, fill: "var(--muted)", "font-size": 10.5 }, t);
  out.append(lab(`${fmt(top)}s`, 0, 10), lab("0", 0, hgt - 16), lab("oldest", 36, hgt - 3), lab("newest", w, hgt - 3, "end"));
  return out;
}

function sparkSvg(points, w, hgt, setpoint = null) {
  const vs = points.map((p) => p[1]);
  let lo = Math.min(...vs), hi = Math.max(...vs);
  if (setpoint != null) { lo = Math.min(lo, setpoint); hi = Math.max(hi, setpoint); }
  const small = hgt < 50, pad = small ? 3 : 6, left = small ? 2 : 34;
  const y = (v) => hgt - pad - ((v - lo) / ((hi - lo) || 1)) * (hgt - 2 * pad);
  const d = vs.map((v, i) => `${i ? "L" : "M"}${left + (i / (vs.length - 1)) * (w - left - 4)},${y(v)}`).join("");
  const out = s("svg", { width: w, height: hgt, class: "spark" });
  if (setpoint != null) out.append(s("line", { x1: left, x2: w - 2, y1: y(setpoint), y2: y(setpoint), stroke: "var(--muted)", "stroke-dasharray": "3 3", "stroke-width": 1 }));
  out.append(s("path", { d, fill: "none", stroke: "var(--accent)", "stroke-width": small ? 1.6 : 2 }));
  if (!small) out.append(s("text", { x: 0, y: 12, fill: "var(--muted)", "font-size": 11 }, fmt(hi)), s("text", { x: 0, y: hgt - 2, fill: "var(--muted)", "font-size": 11 }, fmt(lo)));
  return out;
}
const setpointOf = (sp) => { const m = /(-?\d+(\.\d+)?)/.exec(sp || ""); return m ? +m[1] : null; };

function partLink(name) {                              // ergostat's own events are about a part: open it
  if (S.status?.loops && name in S.status.loops) return h("a", { href: "#", onclick: (ev) => { ev.preventDefault(); openLoop(name); } }, name);
  return h("a", { href: "#", class: "muted", title: "a part of the model", onclick: (ev) => { ev.preventDefault(); openAgent(name).catch(() => {}); } }, name);
}
function itemLink(id) {
  return id.includes("/") ? h("a", { href: `#/item/${encodeURIComponent(id)}` }, id) : partLink(id);
}
function dataCell(d) {                                  // the whole of it, one click away
  const flat = JSON.stringify(d || {});
  if (flat === "{}") return h("td", { class: "mono muted" }, "");
  if (flat.length <= 110) return h("td", { class: "mono muted data" }, flat);
  return h("td", { class: "mono muted data" }, h("details", {}, h("summary", {}, flat.slice(0, 100) + " …"),
    h("pre", {}, JSON.stringify(d, null, 2))));
}
function eventsTable(evs, compact) {
  return h("table", {}, h("tr", {}, h("th", {}, "when"), h("th", {}, "type"), compact ? null : h("th", {}, "item"), h("th", {}, "source"), h("th", {}, "data")),
    evs.slice().reverse().map((e) => h("tr", {}, h("td", { class: "num nowrap", title: new Date(e.time * 1000).toLocaleString() }, new Date(e.time * 1000).toLocaleTimeString([], { hour12: false })),
      h("td", { class: "nowrap" }, h("a", { href: "#", class: "plain", title: `event ${e.id}`, onclick: (ev) => { ev.preventDefault(); showEvent(e); } }, e.type)),
      compact ? null : h("td", { class: "nowrap" }, e.item ? itemLink(e.item) : "–"),
      h("td", { class: "muted nowrap" }, e.source || "–"), dataCell(e.data))));
}
function showEvent(e) {                                 // one event, all of it, in the side panel
  showDetail(h("div", { class: "kind" }, "event"), h("h2", {}, e.type),
    dl([["item", e.item ? itemLink(e.item) : null], ["source", e.source], ["when", new Date(e.time * 1000).toLocaleString()], ["id", e.id],
        ["caused by", e.causedby]]),
    h("pre", {}, JSON.stringify(e.data || {}, null, 2)));
}


/* a line, clicked: what kind of connection it is (a flow of material, or a signal in a loop), what
   it joins, what it carries now, and the loops it is part of */
async function openEdge(e) {
  const g = S.graph || { nodes: [], loops: {} };
  const byId = Object.fromEntries(g.nodes.map((n) => [n.id, n]));
  const src = original(e.source, e.sourcePort), dst = original(e.target, e.targetPort);
  const nameOf = (id) => { const n = byId[id]; return n && (n.kind === "valve" || n.kind === "disturbance") ? n.flow : n?.label ?? id.split(":").slice(1).join(":"); };
  const link = (id) => {
    const n = byId[id];
    if (n && n.kind !== "cloud" && n.kind !== "terminal") return h("a", { href: "#", onclick: (ev) => { ev.preventDefault(); openNode(n); } }, nameOf(id));
    if (id.startsWith("cloud:")) return h("span", { class: "muted" }, "outside the model");
    return h("b", {}, nameOf(id));
  };
  const crossing = [e.sourcePort && `leaves system ${e.source.slice(7)} at its port ${nameOf(src)}`,
                    e.targetPort && `enters system ${e.target.slice(7)} at its port ${nameOf(dst)}`,
                    e.source.startsWith("term:") && `comes from outside this system (${byId[e.source]?.in || "elsewhere"})`,
                    e.target.startsWith("term:") && `goes outside this system (${byId[e.target]?.in || "elsewhere"})`].filter(Boolean);
  const loops = (e.loops || []).map((k) => h("a", { href: "#", onclick: (ev) => { ev.preventDefault(); highlightLoop(k); openLoop(k); } }, k));
  const rows = [];
  let kind, what;
  if (e.kind === "pipe") {
    kind = "flow · system dynamics";
    let d = null;
    try { d = await api(`part/flow/${encodeURIComponent(e.flow)}`); } catch (err) { d = null; }
    const m = d?.model || {}, now = d?.now || {};
    const valve = g.nodes.find((n) => (n.kind === "valve" || n.kind === "disturbance") && n.flow === e.flow);
    what = `Here: ${e.flow} moves material from ${m.source || "outside the model"} to ${m.target || "outside the model"}.`;
    rows.push(["flow", e.flow], ["from", m.source || "outside the model"], ["to", m.target || "outside the model"],
              ["rate now", now.rate != null ? `${fmt(now.rate)}/h` : (valve?.rateText || "not known yet")],
              ["how we know", now.how || valve?.how],
              ["moved by", valve?.kind === "valve" ? [valve.label, valve.agent ? ` (${badgeText(valve.agent)})` : ""] :
                           "nothing in the model: a disturbance to the loops on its stocks"],
              ["follows", (m.driven_by || []).join(", ") || null]);
  } else if (e.kind === "measure") {
    kind = "measurement · control";
    const sn = byId[dst];
    what = `Here: sensor ${nameOf(dst)} reads ${nameOf(src)}.`;
    rows.push(["measures", link(src)], ["sensor", link(dst)], ["reading", sn?.reading || "none yet"]);
  } else if (e.kind === "signal") {
    kind = "feedback · control";
    const c = byId[dst];
    what = `Here: ${nameOf(src)}'s reading goes to the controller of ${nameOf(dst)}.`;
    rows.push(["from", link(src)], ["reading", byId[src]?.reading || null], ["to", link(dst)],
              ["setpoint", c?.setpoint || null], ["error now", c?.error != null ? fmt(c.error) : null], ["status", c?.status ? statusEl(c.status) : null]);
  } else if (e.kind === "action") {
    kind = "control action · control";
    const c = byId[src], v = byId[dst];
    what = `Here: the controller of ${nameOf(src)} opens the valve on ${nameOf(dst)} while its goal is off.`;
    rows.push(["controller", link(src)], ["holds", c?.setpoint || null], ["status", c?.status ? statusEl(c.status) : null],
              ["acts on", link(dst)], ["filled by", v?.agent ? badgeText(v.agent) : null], ["rate now", v?.rateText || null],
              ["last decision", c?.decision ? `“${c.decision}”${c.decisionAt ? " · " + ago(c.decisionAt) : ""}` : null]);
  } else if (e.kind === "influence") {
    kind = "influence · driven-by";
    what = `Here: the rate of ${nameOf(dst)} follows ${nameOf(src)}. Declared (driven-by), not yet checked against the record.`;
    rows.push(["follows", link(src)], ["flow", link(dst)], ["its rate now", byId[dst]?.rateText || null]);
  } else if (e.kind === "wire") {
    kind = "wiring · who reaches whom";
    what = `Here: ${nameOf(src)}'s output reaches ${nameOf(dst)}.`;
    rows.push(["from", link(src)], ["to", link(dst)], ["through", (e.via || []).join("; ") || null]);
  } else {
    kind = e.kind;
    what = "";
    rows.push(["from", link(src)], ["to", link(dst)]);
  }
  const title = e.kind === "pipe" ? [e.flow, h("span", { class: "muted" }, ` (${rows[1][1]} → ${rows[2][1]})`)] : [nameOf(src), " → ", nameOf(dst)];
  showDetail(h("div", { class: "kind" }, WHAT[e.kind] ? "line" : kind), h("h2", {}, ...title), whatIs(e.kind),
    what ? h("p", { class: "muted" }, what) : null,
    DRAWN[e.kind] ? h("p", { class: "muted small" }, "Drawn as " + DRAWN[e.kind] + ".") : null,
    h("h3", {}, "how it is now"), dl(rows),
    crossing.length ? h("p", {}, crossing.join("; ") + ".") : null,
    loops.length ? h("p", {}, "part of the loop", loops.length > 1 ? "s " : " ", loops.flatMap((x, i) => [i ? ", " : "", x])) : h("p", { class: "muted" }, "part of no loop drawn here"));
  S.selKey = linkKey(e);                               // it stays traced while its panel is open
  trace(S.selKey);
}
