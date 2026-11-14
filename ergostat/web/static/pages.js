/* the pages besides the diagram: Loops, Agents, Parts, Record, an item, Residuals, Guide, Check */
"use strict";
/* ------------------------------------------------------------------ the other pages */

function page(main, title, lede) {
  const p = h("div", { class: "page" }, h("h1", {}, title), lede ? h("p", { class: "lede" }, lede) : null);
  main.append(p);
  return p;
}

async function pageLoops(main) {
  const p = page(main, "Loops", "Each controller that holds a stock is a loop. Holding: within its setpoint. Off: outside it. Open: it cannot close (a sensor or valve is missing). Unknown: no reading yet.");
  const box = h("div");
  p.append(box);
  async function tick() {
    const [loops, stocks] = [await api("loops"), await api("graph")];
    const pts = Object.fromEntries(stocks.nodes.filter((n) => n.kind === "stock").map((n) => [n.label, n.points]));
    box.replaceChildren(h("table", {}, h("tr", {}, ["loop", "status", "holds", "now", "setpoint", "e = r − y", "time off", "trend", "acted"].map((x) => h("th", {}, x))),
      Object.entries(loops).map(([n, lp]) => h("tr", { class: "click", onclick: () => openLoop(n) },
        h("td", {}, h("b", {}, n), lp.open_loop ? h("span", { class: "muted", title: "acts on its schedule, reads nothing" }, " ⏲ open loop") : null),
        h("td", {}, statusEl(lp.status)), h("td", {}, lp.stock), h("td", { class: "num" }, fmt(lp.value)),
        h("td", { class: "num nowrap" }, lp.setpoint + (lp.band || "")),
        h("td", { class: `num s-${lp.status}` }, lp.error != null ? fmt(lp.error) : ""),
        h("td", { class: "num", title: "the share of the window the loop spent off" }, lp.off_share ? `${Math.round(lp.off_share * 100)}%` : "0%"),
        h("td", {}, (pts[lp.stock] || []).length > 1 ? sparkSvg(pts[lp.stock], 150, 30, setpointOf(lp.setpoint)) : ""),
        h("td", { title: "in the window, its sensor read and its controller decided or its valve opened" }, lp.observed ? "yes" : h("span", { class: "muted" }, "no"))))));
  }
  await tick();
  S.timer = setInterval(tick, 3000);
}

async function pageAgents(main) {
  const p = page(main, "Agents", "Agents fill roles: sensors, controllers and valves. The ladder runs from the most general agent (left) to none at all (right); every role is expected to move down the ladder, that is, to the right.");
  const box = h("div", { class: "ladder" });
  p.append(box);
  async function tick() {
    const agents = await api("agents");
    box.replaceChildren();
    const cols = [...RUNG_NAMES, "retired"];
    cols.forEach((k, i) => {
      const filled = Object.values(agents).some((a) => a.rung === i);
      const col = h("div", { class: "rung" + (filled ? "" : " empty-rung") }, h("h4", {}, h("i", { class: "kdot", style: `background:${rungColor(i)}` }, RUNG_LETTER[i]), ` ${i} ${k}`), h("div", { class: "hint" }, RUNG_HINT[i]));
      for (const [name, a] of Object.entries(agents).filter(([, a]) => a.rung === i)) {
        col.append(h("div", { class: "card" + (a.failing ? " failing" : ""), onclick: () => openAgent(name) },
          h("b", {}, name),
          h("div", { class: "muted" }, a.runs_itself ? `${a.runs} runs · ${a.running_since ? "running for " + ago(a.running_since).replace(" ago", "") : (a.last ? ago(a.last.time) : "never ran")}` : (a.kind === "person" ? "a person" : "not run here")),
          h("div", { class: "roles" }, (a.roles || []).map((r) => `${r.kind} ${r.name}`).join(" · ") || "no roles"),
          (a.hints || []).map((hint) => h("div", { class: "ladder-hint", title: hint.says },
            hint.about === "loop" ? `⚠ ${hint.says}`
              : `↘ ${hint.controller}: “${hint.decision}” ${Math.round(hint.share * 100)}% of ${hint.count}: a cheaper rung could fill it`))));
      }
      box.append(col);
    });
  }
  await tick();
  S.timer = setInterval(tick, 3000);
}

async function pageParts(main, q) {
  const p = page(main, "Parts", "Every part of the model, one kind at a time, with what it holds or does now. Click a row for its detail.");
  const kinds = ["system", "stock", "flow", "valve", "sensor", "controller", "disturbance"];
  const on = q.get("kind") || "stock";
  p.append(h("div", { class: "seg tabs" }, kinds.map((k) => h("button", { class: k === on ? "on" : "", onclick: () => { location.hash = `#/parts?kind=${k}`; } }, k + "s"))));
  const box = h("div", { style: "margin-top:14px" });
  p.append(box);
  const badgeEl = (a) => a ? h("span", { class: "rungpill", style: `background:${rungColor(a.rung)}` }, `${a.kind} · ${a.name}`) : h("span", { class: "s-open status" }, "unfilled");
  const rowsFor = {
    system: (x) => [h("b", {}, x.name), x.description, String(x.parts), x.loops.join(", ") || "–", x.off.length ? h("span", { class: "s-off status" }, x.off.join(", ")) : "0"],
    stock: (x) => [h("b", {}, x.name), h("span", { class: "num" }, `${fmt(x.value)} ${x.unit}`), x.points.length > 1 ? sparkSvg(x.points, 130, 26) : "",
                   x.sensor || h("span", { class: "s-open status" }, "unmeasured"), h("span", { class: "num" }, `${fmt(x.inflow)}/h in · ${fmt(x.outflow)}/h out`)],
    flow: (x) => [h("b", {}, x.name), x.from || "outside", x.to || "outside", h("span", { class: "num" }, `${fmt(x.rate)}/h`), h("span", { class: "muted" }, x.how)],
    disturbance: (x) => [h("b", {}, x.name), x.from || "outside", x.to || "outside", h("span", { class: "num" }, `${fmt(x.rate)}/h`), h("span", { class: "muted" }, x.how)],
    valve: (x) => [h("b", {}, x.name), x.flow, x.mode, badgeEl(x.agent), h("span", { class: "num" }, x.position != null ? fmt(x.position) : "–"),
                   h("span", { class: "num" }, `${fmt(x.rate)}/h`), ago(x.last)],
    sensor: (x) => [h("b", {}, x.name), x.measures, badgeEl(x.agent), h("span", { class: "num" }, fmt(x.reading)), ago(x.at)],
    controller: (x) => [h("b", {}, x.name), `${x.holds} ${x.setpoint}`, statusEl(x.status), badgeEl(x.agent)],
  };
  const heads = { system: ["system", "description", "parts", "loops", "off"], stock: ["stock", "now", "trend", "measured by", "flows"],
                  flow: ["flow", "from", "to", "rate", "how we know"], disturbance: ["disturbance", "from", "to", "rate", "how we know"],
                  valve: ["valve", "flow", "mode", "filled by", "open", "rate", "last opened"], sensor: ["sensor", "measures", "filled by", "reading", "read"],
                  controller: ["controller", "holds", "status", "filled by"] };
  const open = (x) => on === "system" ? (location.hash = `#/diagram?system=${encodeURIComponent(x.name)}`)
                    : on === "controller" ? openLoop(x.name)
                    : openNode({ id: `${on === "valve" ? "valve" : on}:${x.name}`, kind: on, label: x.name, flow: x.name });
  async function tick() {
    const all = await api("parts");
    const rows = all[on] || [];
    box.replaceChildren(rows.length ? h("table", {}, h("tr", {}, heads[on].map((x) => h("th", {}, x))),
      rows.map((x) => h("tr", { class: "click", onclick: () => open(x) }, rowsFor[on](x).map((c) => h("td", {}, c)))))
      : h("p", { class: "muted" }, `no ${on}s`));
  }
  await tick();
  S.timer = setInterval(tick, 3000);
}

async function pageRecord(main, q) {
  const p = page(main, "Record", "Events as they happen, newest first; items are events folded by id.");
  const filt = h("input", { placeholder: "type, e.g. valve.* or loop.off", value: q.get("type") || "" });
  const runs = h("input", { type: "checkbox" });
  const box = h("div");
  const items = h("div");
  p.append(h("div", { style: "display:flex;gap:12px;align-items:center" }, filt, h("button", { onclick: () => tick(true) }, "filter"),
                h("label", { class: "muted" }, runs, " show runs (agent.started, agent.ran)")), h("h2", {}, "events"), box, h("h2", {}, "items"), items);
  runs.addEventListener("change", () => tick());
  async function tick() {
    const evs = await api("events", { n: 60, ...(runs.checked ? { runs: 1 } : {}), ...(filt.value ? { type: filt.value } : {}) });
    box.replaceChildren(eventsTable(evs, false));
    const its = await api("items");
    items.replaceChildren(h("table", {}, h("tr", {}, ["item", "events", "latest", "last"].map((x) => h("th", {}, x))),
      its.slice(0, 40).map((i) => h("tr", { class: "click", onclick: () => { location.hash = `#/item/${encodeURIComponent(i.item)}`; } },
        h("td", {}, h("b", {}, i.item)), h("td", { class: "num" }, i.n), h("td", {}, i.latest), h("td", {}, ago(i.last))))));
  }
  await tick();
  S.timer = setInterval(tick, 3000);
}

async function pageItem(main, name) {
  const p = page(main, name, "An item: every event about one id, folded.");
  const d = await api(`items/${encodeURIComponent(name)}`);
  p.append(h("h2", {}, "fields"), dl(Object.entries(d.fields).map(([k, v]) => [k, typeof v === "object" ? JSON.stringify(v) : String(v)])),
           h("h2", {}, `events (${d.events.length})`), eventsTable(d.events, true));
}

async function pageResiduals(main) {
  const p = page(main, "Residuals", "For each stock: how much its readings changed in the window, how much its known flows explain, and the rest. A disturbance nothing measures is estimated from the rest; anything left is unexplained, and worth a look.");
  const r = await api("residuals");
  p.append(h("table", {}, h("tr", {}, ["stock", "changed", "explained", "unexplained", ""].map((x) => h("th", {}, x))),
    Object.entries(r).map(([k, v]) => h("tr", {}, h("td", {}, h("b", {}, k)), h("td", { class: "num" }, fmt(v.change)), h("td", { class: "num" }, fmt(v.explained)),
      h("td", { class: "num" }, fmt(v.unexplained)),
      h("td", {}, v.significant ? h("span", { class: "s-open status" }, "unexplained") : (v.absorbed_by.length ? `estimated as ${v.absorbed_by.join(", ")}` : h("span", { class: "s-holding status" }, "explained")))))));
  if (!Object.keys(r).length) p.append(h("p", { class: "muted" }, "no stock has two readings in this window yet"));
}

async function pageGuide(main) {
  const p = page(main, "Guide", "ergostat keeps work going. It treats the work around you as a factory, and runs it as a control system. Here is how to read yours.");
  const [parts, agents] = [await api("parts"), await api("agents")];
  const code = (t) => h("code", {}, t);
  const ex = (list, f, n = 2) => list.slice(0, n).map((x, i) => [i ? ", " : "", f(x)]);
  const sec = (title, ...kids) => p.append(h("section", { class: "guide" }, h("h2", {}, title), ...kids));
  const stock = parts.stock[0], loop = parts.controller.find((x) => !x.open_loop);   // the example of feedback is a feedback loop
  sec("Work is a flow, not a list",
    h("p", {}, "Work is change in the world over time. ergostat does not track tasks; it watches what accumulates and what moves it. ",
      "What accumulates is a ", h("b", {}, "stock"), ": ", ex(parts.stock, (x) => [code(x.name), ` (${fmt(x.value)} ${x.value === 1 && x.unit.endsWith("s") ? x.unit.slice(0, -1) : x.unit})`]) , ". ",
      "What moves a stock is a ", h("b", {}, "flow"), ", drawn as a pipe. A flow nothing controls is a ", h("b", {}, "disturbance"), ": ",
      parts.disturbance.length ? ex(parts.disturbance, (x) => code(x.name)) : "you have none declared", "."));
  sec("Three roles keep it steady",
    h("p", {}, "A ", h("b", {}, "sensor"), " measures (", ex(parts.sensor, (x) => code(x.name)), "). ",
      "A ", h("b", {}, "controller"), " decides, to hold a stock at a setpoint (", ex(parts.controller, (x) => [code(x.name), ` holds ${x.holds} ${x.setpoint}`]), "). ",
      "A ", h("b", {}, "valve"), " acts on a flow (", ex(parts.valve, (x) => code(x.name)), "). Nothing changes the world except through a valve."),
    loop ? h("p", {}, "Together they make a ", h("b", {}, "loop"), ": a sensor measures ", code(loop.holds), "; ", code(loop.name),
      " reads it, compares it with its setpoint, and opens a valve when it is off. Its status now: ", statusEl(loop.status), ". ",
      h("a", { href: "#/diagram?view=blocks" }, "See it as a block diagram"), ".") : null,
    parts.controller.some((x) => x.open_loop) ? h("p", {}, "An ", h("b", {}, "open loop"), " acts by the clock and reads nothing (",
      ex(parts.controller.filter((x) => x.open_loop), (x) => code(x.name)), "): a sensor on its stock only watches it, so its status still says ",
      "whether the timer is enough, but nothing it measures changes what it does. A clock marks it in the diagram.") : null);
  const byRung = {};
  for (const [n, a] of Object.entries(agents)) (byRung[a.rung] ||= []).push(n);
  sec("Agents fill the roles, and move down the ladder",
    h("p", {}, "An ", h("b", {}, "agent"), " is whatever acts on your behalf: a person, an AI agent, a decision, a program, a rule. ",
      "One agent can fill several roles. Every agent is held to the same discipline: measured, bounded, and acting only through the valves you grant."),
    h("p", {}, "The ladder runs from the most general agent to none at all. Yours: ",
      [0, 1, 2, 3, 4, 5].filter((r) => byRung[r]).map((r, i) => [i ? "; " : "", h("b", {}, RUNG_NAMES[r]), " ", byRung[r].join(", ")]), ". ",
      "Every role is expected to move down: start with an AI agent, then a narrower one, a decision, a program, a rule, and finally design the work out. ",
      h("a", { href: "#/agents" }, "See the ladder"), "."));
  sec("When the model does not explain it",
    h("p", {}, "A ", h("b", {}, "residual"), " is what a stock did that its known flows do not explain. An unmeasured disturbance is estimated from it; anything left over is worth a look: ",
      "it is either a disturbance you have not named, or the plant behaving differently than you think. ", h("a", { href: "#/residuals" }, "Your residuals"), "."));
  sec("Reading the diagram", legend("control"), h("p", {}, "Systems are outlines around parts that belong together; they may overlap. ",
    "The wiring view shows the agents and how each one's output reaches another. The slider in the header shows any past moment."));
  if (!stock) p.append(h("p", { class: "muted" }, "Your model is empty: describe your system with ergostat chat, or start from ergostat check --example."));
}

async function pageCheck(main) {
  const p = page(main, "Check", "Is the model whole? References that do not resolve are errors; loops that cannot close and parts nothing fills are warnings.");
  const st = await api("status");
  const list = h("div", { class: "att" });
  if (!st.check.length) list.append(h("div", { class: "ok" }, "the model is whole"));
  for (const c of st.check) list.append(h("div", { class: c.level === "error" ? "bad" : "" }, h("b", {}, c.level), " ", c.message));
  p.append(list, h("h2", {}, "counts"), h("table", {}, h("tr", {}, Object.keys(st.counts).map((k) => h("th", {}, k))),
    h("tr", {}, Object.values(st.counts).map((v) => h("td", { class: "num" }, String(v))))));
}

