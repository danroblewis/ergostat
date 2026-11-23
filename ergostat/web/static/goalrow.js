/* one goal's row, drawn the same wherever a goal is listed: the server says its word and columns once (state.goal_row),
   and only this file turns them into reader text (tests/test_graph_cli_web.py greps the other scripts for it) */
"use strict";

const GOAL_WORDS = ["holding", "off", "stale", "open", "unknown"];   // (in the order a count of them is read)
/* the one word a reader sees for a goal's state: the server's; an answer from before it (an old snapshot), its status */
const goalWord = (g) => g?.word || (GOAL_WORDS.includes(g?.status) ? g.status : "unknown");
const exceptional = (word) => word && word !== "holding";              // a word worth printing: not a goal holding
const goalRank =(g) => ({ off: 0, open: 1, unknown: 2, holding: 3 })[goalWord(g)] ?? 2;   // the ones that need someone first
/* a goal's measure against its bound, in one line: "backlog 7, setpoint ≤ 5 (+1)" */
const goalLine = (g) => `${g.row?.measure ?? g.stock} ${fmt(g.row ? g.row.value : g.value)}, setpoint ${goalBound(g)}`;
const goalBound = (g) => op(g.row ? g.row.bound_words : `${g.setpoint ?? ""}${g.band || ""}`);
const goalPerf = (s) => (s == null || s.not_analysed ? "" : s.working ? "being worked out" : s.failed ? "could not be worked out" : performanceWord(s));

const GOAL_CELLS = {
  goal: (g) => h("td", { class: "nowrap" }, h("button", { class: "name", type: "button", onclick: (ev) => { ev.stopPropagation(); openLoop(g.name); } }, h("b", {}, g.name)),
    g.open_loop ? h("span", { class: "muted", title: "Acts on its schedule, reads nothing" }, " open loop") : null),
  status: (g) => h("td", {}, statusEl(goalWord(g))),
  measure: (g) => h("td", { class: "nowrap" }, g.row?.measure ?? g.stock),
  value: (g) => h("td", { class: "num" }, fmt(g.row ? g.row.value : g.value)),
  bound: (g) => h("td", { class: "num nowrap" }, goalBound(g)),
  far: (g) => h("td", { class: "num nowrap", "data-off": g.name, title: "How far it is from its setpoint" }, g.off_by_words || ""),
  timeOff: (g) => h("td", { class: "num", title: "The share of the window the loop spent off" }, g.off_share ? `${Math.round(g.off_share * 100)}%` : "0%"),
  backIn: (g) => h("td", { class: "num", title: g.back_in != null ? `Typically holding again this long after going off (slowest ${dur(g.back_in_slowest)}, ${g.times_off} times); its valve opens ${g.answers_in != null ? dur(g.answers_in) : "?"} after` : "It has not gone off and come back in the window" },
    g.back_in != null ? dur(g.back_in) : "–"),
  spark: (g) => h("td", { class: "spark-cell", title: "Its scope: r and y, u, e over the window" },
    (g.points || []).length > 1 ? sparkSvg(g.points, 120, 24, setpointOf(g.setpoint)) : ""),
  performance: (g) => h("td", { class: "nowrap", "data-perf": g.name, title: "Oscillating, saturated, or its Harris index: from its scope, over the last day of record" }, goalPerf(g.perf)),
  expected: (g) => h("td", { class: "muted" }, g.row?.expected ?? ""),
  acted: (g) => h("td", { title: "In the window, its sensor read and its controller decided or its valve opened" }, g.observed ? "yes" : h("span", { class: "muted" }, "no")),
};
/* the cells of one goal ({name, ...its /api/loops entry}), in the columns asked for */
function goalRow(goal, { columns }) { return columns.map((c) => GOAL_CELLS[c](goal)); }
