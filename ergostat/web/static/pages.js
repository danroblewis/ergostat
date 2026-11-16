/* the pages besides the diagram: Loops, Agents, Record, Items, an item, Residuals, Guide, Check */
"use strict";
/* ------------------------------------------------------------------ the other pages */

function page(main, title, lede) {
  const p = h("div", { class: "page" }, h("h1", {}, title), lede ? h("p", { class: "lede" }, lede) : null);
  main.append(p);
  return p;
}

async function pageLoops(main) {
  const p = page(main, "Loops", "Each controller that holds a stock is a loop. Holding: within its setpoint. Off: outside it. Open: it cannot close (a sensor or valve is missing). Unknown: no reading yet.");
  const box = h("div"), cap = h("p", { class: "muted small" });
  p.append(box, cap);
  async function tick() {
    const [loops, stocks] = [await api("loops"), await api("graph")];
    const st = S.status, recorded = st?.first ? st.at - st.first : null;
    cap.textContent = st?.window ? `time off and back in: over the ${recorded != null && recorded < st.window * 0.95 ? dur(recorded) + " recorded" : "last " + dur(st.window)}` +
      ". Back in: typically, from going off to holding again." : "";
    const pts = Object.fromEntries(stocks.nodes.filter((n) => n.kind === "stock").map((n) => [n.label, n.points]));
    box.replaceChildren(h("table", {}, h("tr", {}, ["loop", "status", "holds", "now", "setpoint", "e = r − y", "time off", "back in", "trend", "acted"].map((x) => h("th", {}, x))),
      Object.entries(loops).map(([n, lp]) => h("tr", { class: "click", onclick: () => openLoop(n) },
        h("td", {}, h("b", {}, n), lp.open_loop ? h("span", { class: "muted", title: "acts on its schedule, reads nothing" }, " ⏲ open loop") : null),
        h("td", {}, statusEl(lp.status)), h("td", { class: "nowrap-cell" }, lp.stock), h("td", { class: "num" }, fmt(lp.value)),
        h("td", { class: "num nowrap" }, lp.setpoint + (lp.band || "")),
        h("td", { class: `num s-${lp.status}` }, lp.error != null ? fmt(lp.error) : ""),
        h("td", { class: "num", title: "the share of the window the loop spent off" }, lp.off_share ? `${Math.round(lp.off_share * 100)}%` : "0%"),
        h("td", { class: "num", title: lp.back_in != null ? `typically holding again this long after going off (slowest ${dur(lp.back_in_slowest)}, ${lp.times_off} times); its valve opens ${lp.answers_in != null ? dur(lp.answers_in) : "?"} after` : "it has not gone off and come back in the window" },
          lp.back_in != null ? dur(lp.back_in) : "–"),
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

async function pageRecord(main, q) {
  const p = page(main, "Record", "Every event, as it happens, newest first. An event about an item (an id like ticket/12) links to that item; one of ergostat's own links to the part it is about.");
  const filt = h("input", { placeholder: "type, e.g. valve.* or ticket.*", value: q.get("type") || "" });
  const runs = h("input", { type: "checkbox" });
  const box = h("div");
  p.append(h("div", { class: "filters" }, filt, h("button", { onclick: () => tick() }, "filter"),
                h("label", { class: "muted" }, runs, " show runs (agent.started, agent.ran)"), h("a", { href: "#/items" }, "the items →")), box);
  runs.addEventListener("change", () => tick());
  filt.addEventListener("keydown", (ev) => { if (ev.key === "Enter") tick(); });
  async function tick() {
    const evs = await api("events", { n: 80, ...(runs.checked ? { runs: 1 } : {}), ...(filt.value ? { type: filt.value } : {}) });
    box.replaceChildren(evs.length ? eventsTable(evs, false) : h("p", { class: "muted" }, "nothing recorded yet"));
  }
  await tick();
  S.timer = setInterval(() => { if (!box.querySelector("details[open]")) tick(); }, 3000);
}

function stateChip(st, on) { return h("span", { class: `chip${on ? " on" : ""}` }, st || "–"); }

async function pageItems(main, q) {
  const p = page(main, "Items", "The record folded by id: every event about one item (ticket/12, github/pull_request/4231), replayed in order. Its fields are the events' data, the latest winning; its state is where the last event its kind maps moved it. Stocks and flows may count them.");
  const kinds = h("div", { class: "kinds" }), box = h("div"), search = h("input", { placeholder: "search ids and fields", value: q.get("q") || "" });
  const more = h("p", { class: "muted small" });
  p.append(kinds, h("div", { class: "filters" }, search), box, more);
  let kind = q.get("kind"), state = q.get("state");
  const go = () => { const u = new URLSearchParams(); if (kind) u.set("kind", kind); if (state) u.set("state", state); if (search.value) u.set("q", search.value);
                     history.replaceState(null, "", "#/items" + (u.toString() ? "?" + u : "")); tick(); };
  search.addEventListener("input", () => go());
  async function tick() {
    const d = await api("items", { ...(kind ? { kind } : {}), ...(state ? { state } : {}) });
    kinds.replaceChildren(...[...d.kinds.map((k) => h("div", { class: `kindrow${kind === k.name ? " on" : ""}` },
      h("a", { href: "#", class: "kname", onclick: (ev) => { ev.preventDefault(); kind = kind === k.name && !state ? null : k.name; state = null; go(); } }, h("b", {}, k.name), " ", h("span", { class: "muted mono" }, k.id)),
      h("div", { class: "states" }, (k.states.length ? k.states : [""]).map((st, i) => [i ? h("span", { class: "arrow" }, "→") : null,
        h("a", { href: "#", class: `stbox${kind === k.name && state === st ? " on" : ""}`, onclick: (ev) => { ev.preventDefault(); [kind, state] = kind === k.name && state === st ? [null, null] : [k.name, st]; go(); } },
          h("span", { class: "n" }, String(k.counts[st] || 0)), h("span", { class: "muted" }, st || "items"))])))),
      d.unkinded ? h("p", { class: "muted small" }, `${d.unkinded} item${d.unkinded > 1 ? "s" : ""} match no kind under items: in ergostat.yaml (shown with their fields, no state)`) : null,
      !d.kinds.length && !d.unkinded ? h("p", { class: "muted" }, "no items yet. An item is what events with an id like ticket/12 are about: a block prints {\"event\": \"ticket.opened\", \"item\": \"ticket/12\", \"data\": {...}}, or ergostat event --add ticket.opened --item ticket/12. Its kind (items: in ergostat.yaml) gives it states.") : null].filter(Boolean));
    const shown = [...new Set(d.kinds.filter((k) => !kind || k.name === kind).flatMap((k) => k.show))];
    const needle = search.value.trim().toLowerCase();
    const rows = d.items.filter((i) => !needle || (i.id + " " + JSON.stringify(i.fields)).toLowerCase().includes(needle));
    box.replaceChildren(rows.length ? h("table", {}, h("tr", {}, ["item", kind ? null : "kind", "state", ...shown, "in state", "events", "latest", "last"].filter((x) => x !== null).map((x) => h("th", {}, x))),
      rows.slice(0, 300).map((i) => h("tr", { class: "click", onclick: () => { location.hash = `#/item/${encodeURIComponent(i.id)}`; } },
        h("td", { class: "nowrap" }, h("b", {}, i.id)), kind ? null : h("td", { class: "muted" }, i.kind || "–"), h("td", {}, i.state ? stateChip(i.state, true) : "–"),
        shown.map((f) => h("td", { class: "cell" }, i.fields[f] == null ? "" : typeof i.fields[f] === "object" ? JSON.stringify(i.fields[f]) : String(i.fields[f]))),
        h("td", { class: "num nowrap" }, i.state ? dur(nowS() - i.entered) : ""), h("td", { class: "num" }, i.events), h("td", { class: "muted nowrap" }, i.latest), h("td", { class: "muted nowrap" }, ago(i.last)))))
      : (d.items.length ? h("p", { class: "muted" }, "nothing matches") : ""));
    more.textContent = d.total > rows.length && !needle ? `${d.total - Math.min(rows.length, 300)} more not shown` : "";
  }
  await tick();
  S.timer = setInterval(tick, 4000);
}

async function pageItem(main, id) {
  const p = page(main, id, null);
  const body = h("div");
  p.append(body);
  async function tick() {
    let d;
    try { d = await api(`items/${encodeURIComponent(id)}`); } catch (e) { d = null; }
    if (!d) { body.replaceChildren(h("p", { class: "muted" }, "nothing is recorded about this id")); return; }
    const k = d.kind_of;
    const head = h("p", { class: "lede" }, k ? [h("a", { href: `#/items?kind=${encodeURIComponent(k.name)}` }, k.name), " · "] : "no kind (nothing under items: matches this id) · ",
      d.state ? ["in ", stateChip(d.state, true), ` for ${dur(nowS() - d.entered)} · `] : null, `${d.events} events since ${ago(d.first)}, the latest ${d.latest} ${ago(d.last)}`);
    const track = k && k.states.length ? h("div", { class: "track" }, k.states.map((st, i) => [i ? h("span", { class: "arrow" }, "→") : null,
      h("span", { class: `stbox${st === d.state ? " on" : ""}${d.moves.some((m) => m.to === st) || (i === 0) ? " been" : ""}` }, h("span", {}, st))])) : null;
    const moves = d.moves.length ? h("table", {}, h("tr", {}, ["when", "from", "to", "by event", "after"].map((x) => h("th", {}, x))),
      d.moves.map((m, i) => h("tr", {}, h("td", { class: "num nowrap" }, new Date(m.time * 1000).toLocaleString([], { hour12: false })), h("td", {}, m.from || "–"), h("td", {}, stateChip(m.to, true)),
        h("td", { class: "muted" }, m.type), h("td", { class: "num muted" }, dur(m.time - (i ? d.moves[i - 1].time : d.first)))))) : h("p", { class: "muted" }, k && k.states.length ? `it has stayed in ${d.state} since it was first seen` : "its kind has no states");
    const fields = Object.keys(d.fields).length ? h("table", { class: "fields" }, Object.entries(d.fields).sort(([a], [b]) => (a < b ? -1 : 1)).map(([f, v]) => h("tr", {},
      h("th", {}, f), h("td", { class: "mono" }, typeof v === "object" && v !== null ? h("pre", {}, JSON.stringify(v, null, 2)) : String(v))))) : h("p", { class: "muted" }, "no fields: its events carry no data");
    body.replaceChildren(head, track || "", h("h2", {}, "fields"), fields, h("h2", {}, "how it moved"), moves,
      h("h2", {}, `events (${d.events})`), eventsTable(d.record, true));
  }
  await tick();
  S.timer = setInterval(() => { if (!body.querySelector("details[open]")) tick(); }, 4000);
}

async function pageResiduals(main) {
  const p = page(main, "Residuals", "For each stock: how much its readings changed in the window, how much its known flows explain, and the rest. A disturbance nothing measures is estimated from the rest (lumped: it holds every error in the model too); anything left is unexplained, and worth a look.");
  const cap = h("p", { class: "muted" }), box = h("div");
  p.append(cap, box);
  async function tick() {
    const r = await api("residuals");
    const st = S.status, recorded = st?.first ? (st.at - st.first) : null, win = st?.window;
    cap.textContent = win ? (recorded != null && recorded < win * 0.95 ? `over the ${dur(recorded)} recorded (the window is ${dur(win)})` : `over the last ${dur(win)}`) : "";
    box.replaceChildren(h("table", {}, h("tr", {}, ["stock", "changed", "explained", "unexplained", ""].map((x) => h("th", {}, x))),
      Object.entries(r).map(([k, v]) => h("tr", {}, h("td", {}, h("b", {}, k)), h("td", { class: "num" }, fmt(v.change)), h("td", { class: "num" }, fmt(v.explained)),
        h("td", { class: "num" }, fmt(v.unexplained)),
        h("td", {}, v.significant ? h("span", { class: "s-open status" }, "unexplained") : (v.absorbed_by.length ? `estimated as ${v.absorbed_by.join(", ")}` : h("span", { class: "s-holding status" }, "explained")))))));
    if (!Object.keys(r).length) box.append(h("p", { class: "muted" }, "no stock has two readings in this window yet"));
  }
  await tick();
  S.timer = setInterval(tick, 5000);
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

