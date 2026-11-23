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
  bound: (g) => h("td", { class: "num nowrap" }, holdText(g.setpoint, g.band)),
  far: (g) => h("td", { class: "num nowrap", "data-off": g.name, title: `How far it is from its ${isLimit(g.setpoint) ? "limit" : "setpoint"}` }, g.off_by_words || ""),
  timeOff: (g) => h("td", { class: "num", title: "The share of the window the loop spent off" }, shareText(g.off_share)),
  backIn: (g) => h("td", { class: "num", title: g.back_in != null ? `Typically holding again this long after going off (slowest ${dur(g.back_in_slowest)}, ${g.times_off} times); its valve opens ${g.answers_in != null ? dur(g.answers_in) : "?"} after` : "It has not gone off and come back in the window" },
    g.back_in != null ? dur(g.back_in) : "–"),
  spark: (g) => h("td", { class: "spark-cell", title: "Its scope: r and y, u, e over the window" },
    (g.points || []).length > 1 ? sparkSvg(g.points, 120, 24, setpointOf(g.setpoint)) : ""),
  performance: (g) => h("td", { class: "nowrap", "data-perf": g.name, title: "Flapping (gone off 20 times or more in the window), oscillating, saturated, past or within its bound, or its Harris index: from its scope, over the last day of record; on Loops it changes only once the new behaviour has held a while" },
    g.behaviour ?? goalPerf(g.perf)),
  expected: (g) => h("td", { class: "muted" }, g.row?.expected ?? ""),
  acted: (g) => h("td", { title: "In the window, its sensor read and its controller decided or its valve opened" }, g.observed ? "yes" : h("span", { class: "muted" }, "no")),
  // on a phone each goal is a card (style.css): its name and word, then its value against its bound and how long off
  // (up to the moment the answer is as of: the past moment chosen, else now)
  card: (g) => h("td", { class: "card" }, h("div", {}, h("b", {}, g.name), " · ", statusEl(goalWord(g))),
    h("div", { class: "muted" }, [`${fmt(g.value)} against ${op(g.setpoint)}`, goalOffFor(g),
      g.back_in != null ? `usually back in ${dur(g.back_in)}` : null].filter(Boolean).join(" · "))),
};
const goalOffFor = (g) => goalWord(g) !== "off" ? null : g.off_since == null ? "off since ?"
  : `off ${g.off_before_window ? "over " : ""}${dur((S.at || nowS()) - g.off_since)}`;
/* the cells of one goal ({name, ...its /api/loops entry}), in the columns asked for */
function goalRow(goal, { columns }) { return columns.map((c) => GOAL_CELLS[c](goal)); }
