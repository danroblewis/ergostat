/* the detail panel: a part, a loop or an agent, with its charts */
"use strict";
/* ------------------------------------------------------------------ details */

function closeDetail() { const d = $("#detail"); d.hidden = true; d.replaceChildren(); for (const n of document.querySelectorAll(".node.sel")) n.classList.remove("sel"); }
function showDetail(...kids) {
  const d = $("#detail");
  d.replaceChildren(h("button", { class: "close", onclick: closeDetail }, "close"), ...kids);
  d.hidden = false;
}
function dl(pairs) { return h("dl", {}, pairs.filter(([, v]) => v != null && v !== "").flatMap(([k, v]) => [h("dt", {}, k), h("dd", {}, v)])); }
function agentLink(a) { return a ? h("a", { href: "#", onclick: (ev) => { ev.preventDefault(); openAgent(a.name); } }, `${a.name} (rung ${a.rung} ${a.kind})`) : h("span", { class: "muted" }, "unfilled"); }

async function openNode(n) {
  for (const x of document.querySelectorAll(".node.sel")) x.classList.remove("sel");
  document.querySelector(`.node[data-id="${CSS.escape(n.id)}"]`)?.classList.add("sel");
  if (n.kind === "agent") return openAgent(n.label);
  const [kind, name] = n.kind === "valve" ? ["valve", n.label] : n.kind === "disturbance" ? ["disturbance", n.flow] : n.id.split(":");
  if (kind === "controller") return openLoop(name);
  const d = await api(`part/${kind}/${encodeURIComponent(name)}`);
  const m = d.model, now = d.now || {};
  const rows = [["description", m.description]];
  if (kind === "stock") rows.push(["now", `${fmt(now.value)} ${m.unit}`], ["measured", now.at ? `${ago(now.at)} by ${now.sensor}` : "never"],
                                  ["in", `${fmt(now.inflow)}/h`], ["out", `${fmt(now.outflow)}/h`]);
  if (kind === "disturbance") rows.push(["pushes", m.target ? `into ${m.target}` : `out of ${m.source}`], ["rate", `${fmt(now.rate)}/h`], ["how we know", now.how]);
  if (kind === "valve") rows.push(["acts on", m.flow], ["mode", m.mode], ["filled by", agentLink(d.agent)], ["rate", `${fmt(now.flow?.rate)}/h`]);
  if (kind === "sensor") rows.push(["measures", m.measures], ["filled by", agentLink(d.agent)], ["readings", String((now.readings || []).length)]);
  const kids = [h("div", { class: "kind" }, kind), h("h2", {}, name), dl(rows)];
  if (kind === "stock" && now.points?.length > 1) kids.push(sparkSvg(now.points, 380, 70));
  if (kind === "sensor" && now.readings?.length > 1) kids.push(sparkSvg(now.readings, 380, 70));
  if (kind === "valve") {
    kids.push(h("h3", {}, "recent openings"));
    kids.push(eventsTable(now.openings || [], true));
  }
  kids.push(h("p", {}, h("a", { href: `#/diagram?around=${kind}/${encodeURIComponent(name)}` }, "draw what is around it")));
  showDetail(...kids);
}

async function openLoop(name) {
  let lp;
  try { lp = await api(`loops/${encodeURIComponent(name)}`); } catch (e) { return; }
  const kids = [h("div", { class: "kind" }, "loop"), h("h2", {}, name, " ", statusEl(lp.status)),
    dl([["holds", `${lp.stock} ${lp.setpoint}` + (lp.tolerance ? ` (± ${lp.tolerance})` : "")], ["now", fmt(lp.value)],
        ["error", lp.error ? fmt(lp.error) : "0"], ["time off", `${Math.round((lp.off_share || 0) * 100)}% of the window`], ["sensors", lp.sensors.join(", ") || "none"], ["valves", lp.valves.join(", ") || "none"],
        ["moves", lp.flows.join(", ") || "none"], ["last reading", ago(lp.last_read)],
        ["last decision", lp.last_decision ? `${ago(lp.last_decision.time)}: ${lp.last_decision.data.decision}` : "none"],
        ["last opening", ago(lp.last_opening)], ["cycled", lp.observed ? "yes, in this window" : "not in this window"]])];
  if ((lp.points || []).length > 1) kids.push(trendChart(lp, 400, 170));
  for (const g of lp.gaps || []) kids.push(h("div", { class: "att" }, h("div", {}, h("b", {}, "cannot close: "), g)));
  for (const hint of lp.hints || []) kids.push(h("div", { class: "att" }, h("div", { class: "hint" }, h("b", {}, "hint: "), hint.says)));
  if (lp.crossings?.length) {
    kids.push(h("h3", {}, "crossings"));
    kids.push(h("table", {}, lp.crossings.slice().reverse().map((e) => h("tr", {},
      h("td", { class: "num nowrap" }, new Date(e.time * 1000).toLocaleTimeString([], { hour12: false })),
      h("td", {}, statusEl(e.type.split(".")[1])), h("td", { class: "num" }, fmt(e.data.value))))));
  }
  if (lp.decisions?.count) {
    kids.push(h("h3", {}, `decisions (${lp.decisions.count})`));
    kids.push(h("table", {}, lp.decisions.kinds.slice(0, 6).map(([w, n]) => h("tr", {}, h("td", { class: "num" }, n), h("td", {}, w)))));
  }
  kids.push(h("p", {}, h("a", { href: `#/diagram?around=loop/${encodeURIComponent(name)}` }, "draw this loop alone")));
  showDetail(...kids);
}

async function openAgent(name) {
  const a = await api(`agents/${encodeURIComponent(name)}`);
  const kids = [h("div", { class: "kind" }, `agent · rung ${a.rung} ${a.kind}`), h("h2", {}, name),
    dl([["description", a.agent.description], ["command", a.agent.command ? h("code", {}, a.agent.command) : null],
        ["runs", a.schedule || "not run by ergostat"],
        ["fills", (a.roles || []).map((r) => `${r.kind} ${r.name}`).join(", ") || "nothing"],
        ["in window", `${a.runs} runs, ${a.failed} failed`]])];
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
  const out = s("svg", { width: w, height: hgt, class: "trend" });
  // off stretches, from the crossings
  const cr = (lp.crossings || []).slice().sort((a, b) => a.time - b.time);
  let offFrom = null;
  for (const c of cr) {
    if (c.type === "loop.off") offFrom = c.time;
    if (c.type === "loop.holding" && offFrom != null) { out.append(s("rect", { x: x(offFrom), y: pad.t, width: Math.max(1, x(c.time) - x(offFrom)), height: hgt - pad.t - pad.b, fill: "var(--bad)", opacity: 0.08 })); offFrom = null; }
  }
  if (offFrom != null) out.append(s("rect", { x: x(offFrom), y: pad.t, width: Math.max(1, x(t1) - x(offFrom)), height: hgt - pad.t - pad.b, fill: "var(--bad)", opacity: 0.08 }));
  if (spv != null) {
    if (tol) out.append(s("rect", { x: pad.l, y: y(spv + tol), width: w - pad.l - pad.r, height: Math.max(1, y(spv - tol) - y(spv + tol)), fill: "var(--ok)", opacity: 0.08 }));
    out.append(s("line", { x1: pad.l, x2: w - pad.r, y1: y(spv), y2: y(spv), stroke: "var(--ok)", "stroke-dasharray": "4 3", "stroke-width": 1.2 }));
    out.append(s("text", { x: pad.l + 4, y: y(spv) - 4, fill: "var(--ok)", "font-size": 10.5, "paint-order": "stroke",
                           stroke: "var(--panel)", "stroke-width": 3 }, "setpoint " + lp.setpoint));
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

function eventsTable(evs, compact) {
  return h("table", {}, h("tr", {}, h("th", {}, "when"), h("th", {}, "type"), compact ? null : h("th", {}, "item"), h("th", {}, "source"), h("th", {}, "data")),
    evs.slice().reverse().map((e) => h("tr", {}, h("td", { class: "num nowrap" }, new Date(e.time * 1000).toLocaleTimeString([], { hour12: false })),
      h("td", { class: "nowrap" }, e.type),
      compact ? null : h("td", { class: "nowrap" }, e.item ? h("a", { href: `#/item/${encodeURIComponent(e.item)}` }, e.item) : "–"),
      h("td", { class: "muted nowrap" }, e.source || "–"), h("td", { class: "mono muted" }, JSON.stringify(e.data).slice(0, 110)))));
}

