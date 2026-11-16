/* the wiring view: the machines the event log shows, and what it proves passed between them. Drawn
   with the diagram's own layout and lines; only a machine's box and the legend are its own */
"use strict";

const DRAW_AGENT = DRAW.agent;
function drawMachine(n, w, hgt) {
  if (!n.machine) return DRAW_AGENT(n, w, hgt);
  const g = s("g", { class: "machine" + (n.silent ? " silent" : "") });
  g.append(s("rect", { class: "hit", width: w, height: hgt, rx: 6, fill: "var(--panel)",
                       stroke: n.failing ? "var(--bad)" : n.silent ? "var(--muted)" : "var(--ink)",
                       "stroke-width": n.silent ? 1.2 : 1.6, "stroke-dasharray": n.silent ? "4 3" : null }));
  g.append(s("text", { x: 12, y: 20, class: "t-label" }, n.label));
  g.append(s("text", { x: w - 12, y: 20, class: "t-sub", "text-anchor": "end" }, n.agentKind || ""));
  const said = n.silent ? (n.declared ? "declared, silent" : "silent")
    : `${n.instances?.length ? n.instances.length + " instances · " : ""}last ${ago(n.last)}${n.declared ? "" : " · not in the model"}`;
  g.append(s("text", { x: 12, y: 38, class: "t-sub" }, said));
  (n.roles || []).slice(0, 3).forEach((r, i) => g.append(s("text", { x: 12, y: 56 + i * 14, class: "t-sub mono-sub" }, `${r.kind} ${r.name}`)));
  return g;
}
DRAW.agent = drawMachine;
LINE_COLOR.wire = "var(--ink)";

const LEGEND = legend;
legend = function (view) {                   // (diagram.js calls it by name: this one draws the wiring's)
  if (view !== "wiring") return LEGEND(view);
  const svg = (t) => h("span", { html: `<svg width="26" height="16">${t}</svg>` });
  return h("div", { class: "legend" },
    svg('<rect x="2" y="2" width="22" height="12" rx="3" fill="var(--panel)" stroke="var(--ink)" stroke-width="1.6"/>'), "a machine on the record in the window",
    svg('<rect x="2" y="2" width="22" height="12" rx="3" fill="var(--panel)" stroke="var(--muted)" stroke-width="1.2" stroke-dasharray="4 3"/>'), "declared, silent: nothing on the record",
    svg('<path d="M2 8 H18" stroke="var(--ink)" stroke-width="1.8"/><path d="M17 4 L24 8 L17 12 Z" fill="var(--ink)"/>'), "seen: an event it caused, or one it listens for and ran after (type · how many)",
    svg('<path d="M2 8 H18" stroke="var(--muted)" stroke-width="1.6" stroke-dasharray="5 4"/><path d="M17 4 L24 8 L17 12 Z" fill="var(--muted)"/>'), "declared, never seen");
};
