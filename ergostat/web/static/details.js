/* the detail panel: a part, a loop or an agent, with its charts */
"use strict";
/* ------------------------------------------------------------------ details */

function closeDetail() { if (S.selKey) { S.selKey = null; trace(S.hoverKey); } if (S.hlCausal) sdHighlight(null); const d = $("#detail"); d.hidden = true; d.replaceChildren(); for (const n of document.querySelectorAll(".node.sel")) n.classList.remove("sel"); }
function showDetail(...kids) {
  if (S.selKey) { S.selKey = null; trace(S.hoverKey); }  // another detail: the line chosen before lets go
  const d = $("#detail");
  kids = kids.filter((k) => k != null && k !== false);
  // what it is now first; what a thing of its kind is (a definition) last, one click away
  const defs = kids.filter((k) => k.nodeType && k.matches?.("details.what")), rest = kids.filter((k) => !defs.includes(k));
  const close = h("button", { class: "close ghost", title: "Close (Esc)", "aria-label": "Close", onclick: closeDetail }, "\u00d7");
  const head = rest[0]?.classList?.contains("kind") ? h("div", { class: "head" }, rest.shift(), close) : h("div", { class: "head" }, h("span"), close);
  d.replaceChildren(head, ...rest, ...defs);
  d.hidden = false;
  d.scrollTop = 0;
  if (typeof panelNote === "function") panelNote(d);   // where the other view draws what is chosen (interact.js)
}
/* what each kind of thing on the diagram is: said first, in plain words, before how it is now */
const WHAT = {
  stock: ["Stock", "something that accumulates. It rises and falls only by its flows, and its level is what a goal holds."],
  auxiliary: ["Auxiliary", "a quantity without memory: determined at each moment by others (a score, a ratio, a share), through its equation where the model writes one, else measured. What keeps its value between changes is a stock. What a goal holds is its loop's process variable; what a controller turns is its manipulated variable: roles in a loop, not kinds of quantity."],
  valve: ["Flow, controlled (a valve)", "material moving into or out of a stock, set by something in the model: a block opens it when its controller commands."],
  disturbance: ["Flow, uncontrolled (a disturbance)", "material moving into or out of a stock that nothing in the model sets. The world pushes it; the loops on its stocks must make up for it."],
  sensor: ["Sensor", "an instrument. It reads one stock or flow; a loop sees only what its sensor reads."],
  controller: ["Controller", "the part that decides, to hold a goal. At its summing point (the Σ in its corner) it compares the stock's reading y with the setpoint r: e = r − y. While that error says the goal is off, it commands a valve. The badge names the block that fills it. With its sensor, the stock and the valve it closes a feedback loop: the loop is the whole cycle, not this box."],
  loop: ["Feedback loop", "a goal on a stock and what serves it. When the stock's reading is off the setpoint, the controller commands a valve until it is back."],
  system: ["System", "a part of the model drawn as one part. Its ports are what crosses its edge: what it reads and is told, what it moves and drives."],
  agent: ["Agent", "the program, AI or person that does a part's work: reads a sensor, decides as a controller, or opens a valve."],
  pipe: ["Flow", "the pipe a flow runs along: material leaving one stock and arriving in another (or coming from or going to outside the model). Only flows change stocks."],
  measure: ["Information link: measurement", "a sensor reading a stock or flow: the measured output, y. The arrow points into the sensor because that is the way the information goes: the stock's level is what the sensor reports. It moves nothing; it only tells."],
  signal: ["Information link: feedback", "a sensor's reading going to a controller, which compares it with its setpoint r and acts on the error e = r − y. This is what makes the loop a loop."],
  action: ["Information link: control action", "a controller commanding a valve: the control signal, u. How hard it pushes is the loop's gain; how long until the stock shows it is the loop's delay."],
  influence: ["Information link: influence", "a cause, declared with driven-by: what is at the arrow's end changes when what is at its start changes (a release fixing what was broken, more users asking for more, the code kept so far deciding a benchmark score). No formula: the value at the end is measured, and nothing moves or is computed along it. It is how a loop closes through another system."],
  wire: ["Wire (what the record shows)", "something that passed from one machine to another, proven by the event log: an event of the second's (or its run) caused by the first's event or run, or an event the second listens for, published by the first, after which the second ran. A wire the model declares that the log never shows is drawn dashed."],
  machine: ["Machine", "something that publishes on the event log (an event's source; machine/instance is one of its instances), or one the model declares. A block's runs are its own, though ergostat records them."],
};
function whatIs(kind) {
  const w = WHAT[kind];
  return w ? h("details", { class: "what" }, h("summary", {}, `About ${w[0].toLowerCase().replace(/^(information link|flow), /, "")}`), h("p", {}, w[1][0].toUpperCase() + w[1].slice(1))) : null;
}

function dl(pairs) { return h("dl", {}, pairs.filter(([, v]) => v != null && v !== "").flatMap(([k, v]) => [h("dt", {}, k), h("dd", {}, v)])); }
function agentLink(a) { return a ? h("span", {}, h("a", { href: "#", onclick: (ev) => { ev.preventDefault(); openAgent(a.name); } }, a.name), h("span", { class: "muted" }, ` ${a.kind}`)) : h("span", { class: "s-open" }, "unfilled"); }

function openSystem(n) {                               // a system as one part: what goes in and out, and how its loops do
  const side = (d) => (n.ports || []).filter((p) => p.side === d);
  const list = (ps, none) => ps.length ? h("table", {}, ps.map((p) => h("tr", {}, h("td", {}, p.label), h("td", { class: "muted" }, p.kind),
    h("td", { class: "num" }, p.value || "")))) : h("p", { class: "muted" }, none);
  showDetail(h("div", { class: "kind" }, "System"), h("h2", {}, n.label, exceptional(n.status) ? statusEl(n.status) : null),
    typeof moduleCharts === "function" ? moduleCharts(n) : null, whatIs("system"),
    n.description ? h("p", { class: "muted" }, n.description) : null,
    dl([["loops", loopsText(n)], ["inside", n.subsystems?.length ? n.subsystems.join(", ") : null],
        ["inner loop", n.inner?.length ? `given a setpoint for ${n.inner.join(", ")} from outside, it holds it: an outer loop can treat it as one block` : null]]),
    h("h3", {}, "In, from outside"), list(side("in"), "Nothing outside reaches in here."),
    h("h3", {}, "Out, to outside"), list(side("out"), "Nothing outside sees it here."),
    h("div", { class: "actions" }, h("button", { onclick: () => S.toggleSystem?.(n.label) }, "Open it here"),
               h("button", { onclick: () => S.drill?.(n.label) }, "Draw it alone")),
    h("p", { class: "note" }, h("code", {}, `ergostat explain system.${n.label}`), " says the same in sentences."));
}

async function openNode(n) {
  for (const x of document.querySelectorAll(".node.sel")) x.classList.remove("sel");
  document.querySelector(`.node[data-id="${CSS.escape(n.id)}"]`)?.classList.add("sel");
  if (n.kind === "agent") return n.machine ? openMachine(n) : openAgent(n.label);
  if (S.graph?.kind === "dynamics") return n.kind === "system" ? sdOpenSystem(n) : openNodeSD(n);   // dynamics.js
  if (n.kind === "system") return openSystem(n);
  const [kind, name] = n.kind === "valve" ? ["valve", n.label] : n.kind === "disturbance" ? ["disturbance", n.flow] : n.id.split(":");
  if (kind === "controller") return openLoop(name, true);
  const d = await api(`part/${kind}/${encodeURIComponent(name)}`);
  const m = d.model, now = d.now || {};
  const rows = [["description", m.description], inferredRow(d.inferred)].filter(Boolean);
  const knob = n.kind === "auxiliary" && n.agent;          // what a block sets is not measured: it is what the block said
  if (kind === "stock") rows.push(["now", `${fmt(now.value)} ${m.unit}`],
    knob ? ["set", h("span", {}, now.at ? `${ago(now.at)} by ` : "never yet, by ", agentLink(n.agent))]
         : ["measured", now.at ? `${ago(now.at)} by its sensor ${now.sensor}` : "never"],
    ...(n.kind === "auxiliary" ? [] : [["in", rateText(now.inflow)], ["out", rateText(now.outflow)]]));
  if (kind === "disturbance") rows.push(["pushes", m.target ? `into ${m.target}` : `out of ${m.source}`], ["rate", rateText(now.rate, "", name)], ["how we know", now.how]);
  if (kind === "valve") rows.push(["acts on", m.flow], ["mode", m.mode], ["most a run", m.max != null ? fmt(m.max) : null],
                                  ["filled by", agentLink(d.agent)], ["rate", rateText(now.flow?.rate, "", m.flow)]);
  const rd = now.readings || [], last = rd[rd.length - 1];
  if (kind === "sensor") rows.push(["measures", m.measures], ["filled by", agentLink(d.agent)],
                                   ["last reading", last ? `${fmt(last[1])}, ${ago(last[0])}` : "none yet"], ["in the window", `${now.count ?? rd.length} readings`]);
  const shown = n.kind === "auxiliary" ? "auxiliary" : kind;
  if (n.kind === "auxiliary") for (let i = rows.length - 1; i >= 0; i--) if (rows[i][0] === "in" || rows[i][0] === "out") rows.splice(i, 1);
  const kids = [h("div", { class: "kind" }, shown), h("h2", {}, name), whatIs(shown), dl(rows), findingsNote(d)].filter(Boolean);
  const its = itemsSection(d.items);                    // what goes through it (itemsets.js)
  if (kind === "stock" && now.points?.length > 1) kids.push(sparkSvg(now.points, 380, 70));
  if (kind === "sensor" && now.readings?.length > 1) kids.push(sparkSvg(now.readings, 380, 70));
  if (kind === "sensor" && rd.length) {
    kids.push(h("h3", {}, "Last readings"), h("table", {}, rd.slice(-10).reverse().map(([t, v]) =>
      h("tr", {}, h("td", { class: "nowrap" }, new Date(t * 1000).toLocaleTimeString([], { hour12: false })), h("td", { class: "num" }, fmt(v))))));
  }
  if (kind === "valve") {
    // one row per run that opened it (an agent may report each thing it moves on its own line)
    const runs = [];
    for (const e of (now.openings || []).slice().reverse()) {
      const last = runs[runs.length - 1];
      if (last && e.causedby && last.causedby === e.causedby) { last.n += 1; last.amount += e.data.amount ?? 1; continue; }
      runs.push({ causedby: e.causedby, time: e.time, n: 1, amount: e.data.amount ?? 1, source: e.source, note: e.data.note });
    }
    kids.push(h("h3", {}, "Recent openings, by run"));
    kids.push(h("table", {}, runs.slice(0, 12).map((r) => h("tr", {},
      h("td", { class: "nowrap" }, new Date(r.time * 1000).toLocaleTimeString([], { hour12: false })),
      h("td", { class: "num" }, fmt(r.amount)), h("td", { class: "muted" }, [r.n > 1 ? `in ${r.n} openings` : "", r.source, r.note].filter(Boolean).join(", "))))));
  }
  if (its) kids.push(its);
  kids.push(h("p", {}, h("a", { href: `/diagram?around=${kind}/${encodeURIComponent(name)}` }, "Draw what is around it")));
  showDetail(...kids);
}

async function openLoop(name, asController = false) {
  let lp;
  try { lp = await api(`loops/${encodeURIComponent(name)}`); } catch (e) { return; }
  const recorded = Math.min(lp.until - lp.since, S.status?.first ? lp.until - S.status.first : Infinity);
  const windowWords = recorded < (lp.until - lp.since) * 0.95 ? `of the ${dur(recorded)} recorded` : "of the window";
  const kids = asController
    ? [h("div", { class: "kind" }, "Controller"), h("h2", {}, name, exceptional(lp.status) ? statusEl(lp.status) : null), whatIs("controller"), whatIs("loop")]
    : [h("div", { class: "kind" }, lp.open_loop ? "Open loop" : "Loop"), h("h2", {}, name, exceptional(lp.status) ? statusEl(lp.status) : null), whatIs("loop")];
  kids.push(loopScope(name, { numbers: "new" }));       // its scope first (charts.js); time off and back in are below
  if (lp.description) kids.push(h("p", { class: "muted" }, lp.description));
  if (lp.open_loop) kids.push(h("p", {}, "It acts on its schedule and reads nothing; its sensor only watches it against the setpoint."));
  kids.push(dl([["status", statusEl(lp.status)], ["holds", `${lp.stock} ${op(lp.setpoint)}${lp.band || ""}`], ["now", fmt(lp.value)],
    ["error", lp.error ? fmt(lp.error) : "0"], ["time off", `${Math.round((lp.off_share || 0) * 100)}% ${windowWords}`],
    ["typically", lp.answers_in != null || lp.back_in != null ? [
      lp.answers_in != null ? `its valve opens ${dur(lp.answers_in)} after it goes off` : null,
      lp.back_in != null ? `it holds again ${dur(lp.back_in)} after (slowest ${dur(lp.back_in_slowest)}, ${lp.times_off} times)` : null,
    ].filter(Boolean).join("; ") : null],
    ["moves", lp.flows.map((f) => `${f} ${rateText(lp.rates?.[f], "", f)}`).join(", ") || "nothing"],
    ["cycled", lp.observed ? "yes, in this window" : "not in this window"]]));
  // each part along the loop, who fills it, and what it last did: as `ergostat loop NAME`
  kids.push(h("table", { class: "parts" }, h("tr", {}, ["part", "name", "filled by", "last"].map((x) => h("th", {}, x))),
    (lp.parts || []).map((pt) => h("tr", {}, h("td", {}, pt.kind), h("td", {}, h("b", {}, pt.name),
        pt.kind === "valve" ? h("span", { class: "muted" }, ` ${pt.mode}${pt.max ? `, \u2264 ${fmt(pt.max)} a run` : ""}`) : null),
      h("td", {}, agentLink(pt.agent)),
      h("td", {}, pt.kind === "sensor" ? (pt.last ? `read ${ago(pt.last.time)}: ${fmt(pt.last.value)}` : h("span", { class: "muted" }, "no reading yet"))
        : pt.kind === "controller" ? (pt.last ? `decided ${ago(pt.last.time)}: ${pt.last.data.decision}`
          : h("span", { class: "muted" }, pt.open_loop ? "acts on its schedule, reads nothing" : "no decision yet"))
        : (pt.last ? `opened ${ago(pt.last.time)}: ${fmt(pt.last.amount)}${pt.last.count > 1 ? ` in ${pt.last.count} openings` : ""}`
          : h("span", { class: "muted" }, "never opened")))))));
  kids.push(controlBox(name, "loop"));                  // its process identified, its controller with it (control.js)
  for (const g of lp.gaps || []) kids.push(h("p", {}, h("b", { class: "lvl-warn" }, "Cannot close: "), g));
  for (const hint of lp.hints || []) kids.push(h("p", {}, h("b", {}, "Suggestion: "), op(hint.says)));
  if (lp.crossings?.length) {
    kids.push(h("h3", {}, `Crossings${lp.crossings_total > lp.crossings.length ? `, the newest ${lp.crossings.length} of ${lp.crossings_total}` : ""}`));
    kids.push(h("table", {}, lp.crossings.slice().reverse().map((e) => h("tr", {},
      h("td", { class: "nowrap" }, new Date(e.time * 1000).toLocaleTimeString([], { hour12: false })),
      h("td", {}, statusEl(e.type.split(".")[1])), h("td", { class: "num" }, fmt(e.data.value)),
      h("td", { class: "muted" }, e.type === "loop.off" && e.data.error != null ? `by ${fmt(Math.abs(e.data.error))}` : "")))));
  }
  if (lp.decisions?.count) {
    kids.push(h("h3", {}, `Decisions (${lp.decisions.count})`), h("div", { class: "note" }, "Alike when only their numbers differ."));
    kids.push(h("table", {}, lp.decisions.kinds.slice(0, 6).map(([w, n]) => h("tr", {}, h("td", { class: "num" }, n), h("td", {}, w.replaceAll("#", "N"))))));
  }
  kids.push(h("p", {}, h("a", { href: `/diagram?around=loop/${encodeURIComponent(name)}` }, "Draw this loop alone")));
  showDetail(...kids);
}

async function openAgent(name, itself = false) {
  const m = itself ? null : (S.graph?.nodes || []).find((n) => n.machine && n.label === name);
  if (m) return openMachine(m);                        // the wiring: the machine as the record shows it
  const a = await api(`agents/${encodeURIComponent(name)}`);
  const kids = [h("div", { class: "kind" }, `Agent, ${a.kind}`), h("h2", {}, name), whatIs("agent"),
    dl([["description", a.agent.description], ["command", a.agent.command ? h("code", {}, a.agent.command) : null],
        ["runs", a.schedule || "not run by ergostat"],
        ["fills", (a.roles || []).map((r) => `${r.kind} ${r.name}`).join(", ") || "nothing"],
        ["the load", (a.loads || []).map((x) => `disturbance ${x}`).join(", ") || null],
        ["in window", `${a.runs} runs, ${a.failed} failed` + (a.refused ? `, ${a.refused} lines refused` : "") + (a.unread ? `, ${a.unread} unreadable` : "")],
        ["durations", (() => { const ss = (a.recent || []).slice(-40).map((e) => e.data.seconds).filter((x) => x != null);
                               return ss.length ? `${Math.min(...ss)}s to ${Math.max(...ss)}s over its last ${ss.length} runs` : null; })()],
        ["stale", (a.stale || []).length ? `no recent reading from ${a.stale.join(", ")}` : null],
        ["log", a.log_path ? h("code", {}, a.log_path) : null]])];
  if ((a.recent || []).length > 1) kids.push(h("h3", {}, `Last ${a.recent.length} runs`), runsChart(a.recent, 400, 90));
  kids.push(h("h3", {}, "Recent runs"));
  kids.push(h("table", {}, h("tr", {}, h("th", {}, "when"), h("th", { class: "num" }, "readings"), h("th", { class: "num" }, "openings"), h("th", { class: "num" }, "decisions"), h("th", {}, "")),
    (a.recent || []).slice(-10).reverse().map((e) => h("tr", {}, h("td", { class: "nowrap" }, ago(e.time)),
      h("td", { class: "num" }, String(e.data.readings || 0)), h("td", { class: "num" }, String(e.data.openings || 0)), h("td", { class: "num" }, String(e.data.decisions || 0)),
      h("td", {}, e.type === "agent.failed" ? h("span", { class: "s-off" }, e.data.note || "failed") : "")))));
  if (a.log?.length) kids.push(h("h3", {}, "End of its log"), h("pre", {}, a.log.slice(-15).join("\n")));
  showDetail(...kids);
}

/* an agent's runs as bars: height is how long each took, red when it failed */
function runsChart(runs, w, hgt) {
  const secs = runs.map((e) => e.data.seconds || 0), top = Math.max(...secs, 0.001);
  const bw = Math.max(2, (w - 40) / runs.length - 1);
  const out = s("svg", { width: w, height: hgt, class: "runs" });
  runs.forEach((e, i) => {
    const bh = Math.max(2, (secs[i] / top) * (hgt - 22));
    out.append(s("rect", { x: 36 + i * (bw + 1), y: hgt - 16 - bh, width: bw, height: bh,
                           class: "chart-bar" + (e.type === "agent.failed" ? " failed" : e.data.refused ? " refused" : "") },
      s("title", {}, `${new Date(e.time * 1000).toLocaleTimeString([], { hour12: false })}: ${fmt(secs[i])}s` +
                     (e.type === "agent.failed" ? `, ${e.data.note || "failed"}` : "") + (e.data.refused ? `, ${e.data.refused} refused` : ""))));
  });
  const lab = (t, x, y, a = "start") => s("text", { x, y, "text-anchor": a, class: "chart-tick" }, t);
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
  if (setpoint != null) out.append(s("line", { x1: left, x2: w - 2, y1: y(setpoint), y2: y(setpoint), class: "chart-set" }));
  out.append(s("path", { d, class: "chart-line" }));
  if (!small) out.append(s("text", { x: 0, y: 12, class: "chart-tick" }, fmt(hi)), s("text", { x: 0, y: hgt - 2, class: "chart-tick" }, fmt(lo)));
  return out;
}
const setpointOf = (sp) => { const m = /(-?\d+(\.\d+)?)/.exec(sp || ""); return m ? +m[1] : null; };

function partLink(name) {                              // ergostat's own events are about a part: open it
  if (S.status?.loops && name in S.status.loops) return h("a", { href: "#", onclick: (ev) => { ev.preventDefault(); openLoop(name); } }, name);
  return h("a", { href: "#", class: "muted", title: "a part of the model", onclick: (ev) => { ev.preventDefault(); openAgent(name).catch(() => {}); } }, name);
}
function itemLink(id) {
  return id.includes("/") ? h("a", { href: `/item/${encodeURIComponent(id)}` }, id) : partLink(id);
}
function dataCell(d) {                                  // the whole of it, one click away (rounded: the event's panel has it exactly)
  const flat = JSON.stringify(tidy(d || {}));
  if (flat === "{}") return h("td", { class: "mono muted" }, "");
  if (flat.length <= 110) return h("td", { class: "mono muted data" }, flat);
  return h("td", { class: "mono muted data" }, h("details", {}, h("summary", {}, flat.slice(0, 100) + "\u2026"),
    h("pre", {}, JSON.stringify(tidy(d), null, 2))));
}
function eventsTable(evs, compact) {
  return h("div", { class: "table-wrap" }, h("table", {}, h("tr", {}, h("th", {}, "when"), h("th", {}, "type"), compact ? null : h("th", {}, "item"), h("th", {}, "source"), h("th", {}, "data")),
    evs.slice().reverse().map((e) => h("tr", {}, h("td", { class: "nowrap", title: new Date(e.time * 1000).toLocaleString() }, new Date(e.time * 1000).toLocaleTimeString([], { hour12: false })),
      h("td", { class: "nowrap" }, h("a", { href: "#", class: "plain", title: `event ${e.id}`, onclick: (ev) => { ev.preventDefault(); showEvent(e); } }, e.type)),
      compact ? null : h("td", { class: "nowrap" }, e.item ? itemLink(e.item) : "–"),
      h("td", { class: "muted nowrap" }, e.source || "\u2013"), dataCell(changeOf(e))))));
}
function showEvent(e) {                                 // one event, all of it, in the side panel
  showDetail(h("div", { class: "kind" }, "Event"), h("h2", {}, e.type),
    dl([["item", e.item ? itemLink(e.item) : null], ["source", e.source], ["when", new Date(e.time * 1000).toLocaleString()], ["id", e.id],
        ["caused by", e.causedby]]),
    h("pre", {}, JSON.stringify(changeOf(e), null, 2)));
}
/* what an event says of its item: its data, or the JSON Patch or whole document it carries (SPEC §5a) */
const changeOf = (e) => (e.patch ? { patch: e.patch } : e.set ? { set: e.set } : e.data || {});


/* the wiring: a machine, with what it published and listened for in the window */
function recordLink(type, machine, text) {
  const q = new URLSearchParams({ ...(type ? { type } : {}), ...(machine ? { machine } : {}), window: "1" });
  return h("a", { href: `/record?${q}`, title: "The Record, filtered to these events in the window" }, text || "Record");
}
function windowWords() {
  const g = S.graph || {};
  return g.span ? `the ${dur(g.span)} ${g.span < (S.status?.window || g.span) * 0.95 ? "recorded" : "window"}` : "the window";
}
function wireRow(e, mine) {                              // one wire, from a machine's panel: open it
  const other = (mine === e.source ? e.target : e.source).split(":").slice(1).join(":");
  return h("tr", { class: "click", onclick: () => openEdge(e) }, h("td", {}, other),
    h("td", { class: "muted" }, e.seen ? (e.types || []).map((t) => t.type).join(", ") : "declared, never seen"),
    h("td", { class: "num" }, e.seen ? String(e.count) : "\u2013"),
    h("td", { class: "muted" }, e.seen ? (e.undeclared ? "undeclared" : "declared") : ""));
}
function openMachine(n) {
  const g = S.graph || { edges: [] };
  const into = g.edges.filter((e) => e.target === n.id), out = g.edges.filter((e) => e.source === n.id);
  const wires = (es, none) => es.length ? h("table", {}, h("tr", {}, h("th", {}, "machine"), h("th", {}, "what"), h("th", { class: "num" }, "count"), h("th", {}, "")),
    es.map((e) => wireRow(e, n.id))) : h("p", { class: "muted" }, none);
  const pub = n.published || [];
  const listens = n.listens || [];
  showDetail(h("div", { class: "kind" }, `Machine${n.agentKind ? ", " + n.agentKind : ""}`), h("h2", {}, n.label), whatIs("machine"),
    n.description ? h("p", { class: "muted" }, n.description) : null,
    dl([["on the record", n.seen ? `yes: last ${ago(n.last)}` : `nothing in ${windowWords()}`],
        ["in the model", n.declared ? (n.label === "ergostat" ? "ergostat itself: it records the loops' crossings and the blocks' runs" : "declared") : "not declared: seen only on the record"],
        ["kind", n.agentKind || null],
        ["instances", n.instances?.length ? n.instances.join(", ") : null],
        ["runs", n.runs ? String(n.runs) : null], ["runs when", n.schedule || null]]),
    h("h3", {}, `Published, in ${windowWords()}`),
    pub.length ? h("table", {}, h("tr", {}, h("th", {}, "type"), h("th", { class: "num" }, "count"), h("th", { class: "num" }, "rate"), h("th", {}, "last"), h("th", {}, "")),
      pub.map((p) => h("tr", {}, h("td", { class: "mono" }, p.type), h("td", { class: "num" }, String(p.count)), h("td", { class: "num" }, rateText(p.perHour)),
        h("td", { class: "muted nowrap" }, ago(p.last)), h("td", {}, recordLink(p.type, n.label)))))
      : h("p", { class: "muted" }, "nothing"),
    h("h3", {}, "Listens for"),
    listens.length ? h("table", {}, h("tr", {}, h("th", {}, "pattern (on:)"), h("th", { class: "num" }, "heard in the window")),
      listens.map((p) => h("tr", {}, h("td", { class: "mono" }, p), h("td", { class: "num" }, String(n.heard?.[p] || 0)))))
      : h("p", { class: "muted" }, "Nothing: it runs on its schedule, or when a block commands it."),
    h("h3", {}, "Reached from"), wires(into, "Nothing on the record reached it."),
    h("h3", {}, "Reaches"), wires(out, "Nothing on the record shows it reaching another machine."),
    n.declared && n.label !== "ergostat" && !n.agentKind?.startsWith("sensor") ? h("p", {}, h("a", { href: "#", onclick: (ev) => { ev.preventDefault(); openAgent(n.label, true); } }, "Its runs and its log")) : null,
    h("p", {}, recordLink(null, n.label, "All it published, in the Record")));
}
function openWire(e, link, nameOf) {
  const a = nameOf(e.source), b = nameOf(e.target);
  const how = (t) => t.how === "run" ? `${a}'s runs caused ${b === "ergostat" ? "ergostat's" : b + "'s"} ${t.type}` : `${a}'s ${t.type} reached ${b}`;
  const evidence = (t) => [t["caused-by"] ? `caused by: ${t["caused-by"]}` : null, t["listened-and-ran"] ? `listened and ran: ${t["listened-and-ran"]}` : null].filter(Boolean).join("; ");
  const model = e.declaredAs?.length ? h("p", {}, h("b", {}, e.seen ? "Declared, and seen. " : "Declared, never seen. "), "The model says: ", e.declaredAs.join("; "),
    e.seen ? "." : `; nothing in ${windowWords()} of the record shows it.`)
    : h("p", {}, h("b", {}, "Undeclared. "), `Nothing in the model says ${a} reaches ${b}; the record shows it does.`);
  const kids = [h("div", { class: "kind" }, e.seen ? "Wire, seen on the record" : "Wire, declared, never seen"), h("h2", {}, a, " \u2192 ", b), whatIs("wire"), model];
  if (e.seen) {
    kids.push(dl([["from", link(e.source)], ["to", link(e.target)], ["events", `${e.count} in ${windowWords()}, ${rateText(e.perHour)}`],
                  ["last seen", ago(e.last)], ["evidence", e.evidence.join(", ")]]),
      h("h3", {}, "What passed"),
      h("table", {}, h("tr", {}, h("th", {}, "event type"), h("th", { class: "num" }, "count"), h("th", {}, "last"), h("th", {}, "")),
        e.types.map((t) => h("tr", {}, h("td", {}, h("span", { class: "mono" }, t.type), h("div", { class: "muted small" }, [how(t), evidence(t)].filter(Boolean).join("; "))),
          h("td", { class: "num", title: rateText(t.perHour) }, String(t.count)), h("td", { class: "muted nowrap" }, ago(t.last)),
          h("td", { class: "nowrap" }, recordLink(t.type, t.publisher))))),
      h("p", { class: "note" }, "Caused by: an event's causedby names the other's event or run. Listened and ran: it listens (on:) for that type, and ran after it."));
  } else {
    kids.push(dl([["from", link(e.source)], ["to", link(e.target)]]));
  }

  showDetail(...kids);
  S.selKey = linkKey(e);
  trace(S.selKey);
}

/* a line, clicked: what kind of connection it is (a flow of material, or a signal in a loop), what
   it joins, what it carries now, and the loops it is part of */
async function openEdge(e) {
  if (S.graph?.kind === "dynamics") return openEdgeSD(e);   // dynamics.js
  const g = S.graph || { nodes: [], loops: {} };
  const byId = Object.fromEntries(g.nodes.map((n) => [n.id, n]));
  // a part inside a closed system is not drawn: its port on the system's box stands for it
  for (const box of g.nodes) for (const p of box.ports || []) {
    if (byId[p.part]) continue;
    const name = p.part.split(":").slice(1).join(":");
    byId[p.part] = { id: p.part, kind: p.kind, label: p.named || p.label, value: p.value,
                     ...((p.kind === "valve" || p.kind === "disturbance") ? { flow: name } : {}) };
  }
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
              ["rate, over the window", now.rate != null ? rateText(now.rate, d?.unit, e.flow) : (valve?.rateText || "not known yet")],
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
              ["last decision", c?.decision ? `“${c.decision}”${c.decisionAt ? ", " + ago(c.decisionAt) : ""}` : null]);
  } else if (e.kind === "influence") {
    kind = "influence · driven-by";
    const kindWord = (id) => ({ valve: "flow", disturbance: "flow", auxiliary: "auxiliary", stock: "stock" })[byId[id]?.kind] || "";
    const toVar = byId[dst]?.kind === "auxiliary";
    what = toVar ? `Here: ${nameOf(dst)} changes when ${nameOf(src)} changes (declared with driven-by in the YAML). It is a cause, not a formula: ` +
                   `${nameOf(dst)}'s value comes from its own sensor, and nothing is computed along this line.`
                 : `Here: the rate of ${nameOf(dst)} follows ${nameOf(src)} (declared with driven-by in the YAML). A cause, not a formula: ` +
                   `the rate is measured, and nothing is computed along this line.`;
    rows.push(["cause", h("span", {}, link(src), ` (${kindWord(src)})`)], ["changes", h("span", {}, link(dst), ` (${kindWord(dst)})`)],
              [toVar ? "its value now" : "its rate now", toVar ? byId[dst]?.value != null ? fmt(byId[dst].value) : null : byId[dst]?.rateText || null]);
  } else if (e.kind === "wire") {
    return openWire(e, link, nameOf);
  } else {
    kind = e.kind;
    what = "";
    rows.push(["from", link(src)], ["to", link(dst)]);
  }
  const title = e.kind === "pipe" ? [e.flow, h("span", { class: "muted" }, ` (${rows[1][1]} → ${rows[2][1]})`)] : [nameOf(src), " → ", nameOf(dst)];
  const named = { pipe: "flow", measure: "information link, measurement", signal: "information link, feedback",
                  action: "information link, control action", influence: "information link, influence", wire: "wire" }[e.kind] || kind;
  showDetail(h("div", { class: "kind" }, named), h("h2", {}, ...title), whatIs(e.kind),
    what ? h("p", { class: "muted" }, what) : null,

    dl(rows),
    crossing.length ? h("p", {}, crossing.join("; ") + ".") : null,
    loops.length ? h("p", {}, "Part of the loop", loops.length > 1 ? "s " : " ", loops.flatMap((x, i) => [i ? ", " : "", x])) : h("p", { class: "muted" }, "Part of no loop drawn here."));
  S.selKey = linkKey(e);                               // it stays traced while its panel is open
  trace(S.selKey);
}
