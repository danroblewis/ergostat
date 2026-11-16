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
  // from the wiring: one machine's events (its instances too), in the page's window
  const machine = q.get("machine") || "", inWindow = q.get("window") === "1";
  const scope = machine || inWindow ? h("span", { class: "muted" }, [machine ? `from ${machine}` : "", inWindow ? "in the window" : ""].filter(Boolean).join(", "),
    " ", h("a", { href: "#/record" + (filt.value ? "?type=" + encodeURIComponent(filt.value) : "") }, "(all)")) : null;
  p.append(h("div", { class: "filters" }, filt, h("button", { onclick: () => tick() }, "filter"), scope,
                h("label", { class: "muted" }, runs, " show runs (agent.started, agent.ran)"), h("a", { href: "#/items" }, "the items →")), box);
  runs.addEventListener("change", () => tick());
  filt.addEventListener("keydown", (ev) => { if (ev.key === "Enter") tick(); });
  async function tick() {
    let evs;
    try {
      evs = await api("events", { n: 80, ...(runs.checked ? { runs: 1 } : {}), ...(filt.value ? { type: filt.value } : {}),
                                  ...(machine ? { machine } : {}), ...(inWindow ? { window: 1 } : {}) });
    } catch (err) { box.replaceChildren(h("p", { class: "muted" }, String(err.message || err))); return; }
    box.replaceChildren(evs.length ? eventsTable(evs, false) : h("p", { class: "muted" }, "nothing recorded yet"));
  }
  await tick();
  S.timer = setInterval(() => { if (!box.querySelector("details[open]")) tick(); }, 3000);
}

/* an item's field, as what it is: a file the project holds (file:PATH) as the image it is, or a link;
   a record as a small table of its fields; a list of records as a table; text as text */
const IMAGE = /\.(png|jpe?g|gif|webp|svg|bmp|avif)$/i;
const CODE = { py: "python", js: "javascript", ts: "typescript", sh: "bash", json: "json", yaml: "yaml", yml: "yaml", toml: "ini",
               go: "go", rs: "rust", java: "java", c: "c", h: "c", cpp: "cpp", rb: "ruby", sql: "sql", html: "xml", css: "css", diff: "diff" };
function formatOf(path, declared) {                      // how a file is shown: as its kind says, else by its extension
  if (declared) return declared;
  const ext = (path.split(".").pop() || "").toLowerCase();
  return IMAGE.test(path) ? "image" : ext === "md" ? "markdown" : ext === "json" ? "json" : CODE[ext] ? "code" : "text";
}
function fieldView(v, small = false, depth = 0, declared = null) {
  if (v == null || v === "") return h("span", { class: "muted" }, "–");
  if (typeof v === "string" && v.startsWith("file:")) {
    const path = v.slice(5), name = path.split("/").pop(), fmt = formatOf(path, declared);
    if (SNAP) return h("span", { class: "mono muted", title: path }, name);
    const url = `/file?path=${encodeURIComponent(path)}`;
    if (fmt === "image") return h("a", { href: url, target: "_blank", title: path, onclick: (ev) => ev.stopPropagation() },
                                  h("img", { src: url, class: small ? "thumb" : "pic", alt: name, loading: "lazy" }));
    if (small) return h("a", { href: url, target: "_blank", class: "mono", onclick: (ev) => ev.stopPropagation() },
                        fmt === "claude-session" ? "conversation" : name);
    return fileView(path, url, fmt);
  }
  if (typeof v !== "object") return typeof v === "number" ? fmt(v) : String(v);
  if (small || depth > 2) return h("span", { class: "mono muted" }, JSON.stringify(v).slice(0, 80));
  if (Array.isArray(v)) {
    if (v.length && v.every((x) => x && typeof x === "object" && !Array.isArray(x))) {
      const cols = [...new Set(v.flatMap((x) => Object.keys(x)))];
      return h("table", { class: "sub" }, h("tr", {}, cols.map((c) => h("th", {}, c))),
        v.map((x) => h("tr", {}, cols.map((c) => h("td", {}, fieldView(x[c], false, depth + 1))))));
    }
    return v.length ? v.map((x, i) => [i ? ", " : "", fieldView(x, false, depth + 1)]) : h("span", { class: "muted" }, "none");
  }
  return h("table", { class: "sub" }, Object.entries(v).map(([k, x]) => h("tr", {}, h("th", {}, k), h("td", {}, fieldView(x, false, depth + 1)))));
}

/* a file's contents, shown as what they are; kept while unchanged, so a refresh keeps what is open */
const FILES = {};
function fileView(path, url, fmt) {
  const box = FILES[path]?.el || h("div", { class: `file-view f-${fmt}` }, h("span", { class: "muted" }, "…"));
  FILES[path] = FILES[path] || { el: box, len: -1 };
  fetch(url).then((r) => (r.ok ? r.text() : Promise.reject(r.status))).then((text) => {
    if (FILES[path].len === text.length) return;          // unchanged: leave it as it is (open tool calls stay open)
    FILES[path].len = text.length;
    box.replaceChildren(render(text, fmt, path));
  }).catch((e) => box.replaceChildren(h("span", { class: "muted" }, `cannot read ${path} (${e})`)));
  return box;
}
function render(text, fmt, path) {
  if (fmt === "markdown") return md(text);
  if (fmt === "json") { try { text = JSON.stringify(JSON.parse(text), null, 2); } catch (e) { /* as it is */ } return code(text, "json"); }
  if (fmt === "code") return code(text, CODE[(path.split(".").pop() || "").toLowerCase()]);
  if (fmt === "claude-session") return conversation(text);
  return h("pre", { class: "plain" }, text);
}
function code(text, lang) {
  const el = h("code", { class: "hljs" });
  try { el.innerHTML = lang && window.hljs?.getLanguage(lang) ? hljs.highlight(text, { language: lang }).value : (window.hljs ? hljs.highlightAuto(text).value : esc(text)); }
  catch (e) { el.textContent = text; }
  return h("pre", { class: "code" }, el);
}
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
let mdReady = false;
function md(text) {                                       // Markdown, its raw HTML shown as text (nothing in it runs), code highlighted
  if (!window.marked) return h("pre", { class: "plain" }, text);
  if (!mdReady) {
    marked.use({ renderer: { html: (t) => esc(typeof t === "string" ? t : t.text || ""),
                             code: (src, lang) => { const s = typeof src === "string" ? src : src.text; const l = typeof src === "string" ? lang : src.lang;
                                                    try { return `<pre class="code"><code class="hljs">${l && hljs.getLanguage(l) ? hljs.highlight(s, { language: l }).value : hljs.highlightAuto(s).value}</code></pre>`; }
                                                    catch (e) { return `<pre class="code"><code>${esc(s)}</code></pre>`; } } } });
    mdReady = true;
  }
  const el = h("div", { class: "md" });
  el.innerHTML = marked.parse(String(text));
  for (const a of el.querySelectorAll("a")) { a.target = "_blank"; a.rel = "noopener"; }
  return el;
}

/* a Claude Code transcript (one JSON object a line): the conversation, each reply as Markdown, each
   tool call one line that opens to its input and what came back */
function conversation(text) {
  const lines = text.split("\n").filter(Boolean).map((l) => { try { return JSON.parse(l); } catch (e) { return null; } }).filter(Boolean);
  const results = {};
  for (const l of lines) for (const c of (Array.isArray(l.message?.content) ? l.message.content : [])) if (c.type === "tool_result") results[c.tool_use_id] = c;
  const out = h("div", { class: "convo" });
  let turns = 0;
  for (const l of lines) {
    const m = l.message;
    if (!m || (l.type !== "user" && l.type !== "assistant")) continue;
    const when = l.timestamp ? new Date(l.timestamp).toLocaleTimeString([], { hour12: false }) : "";
    const parts = typeof m.content === "string" ? [{ type: "text", text: m.content }] : (m.content || []);
    for (const c of parts) {
      if (c.type === "tool_result") continue;             // shown with its call
      if (c.type === "text" && l.type === "user") {
        const long = c.text.length > 600;
        out.append(h("div", { class: "turn user" }, h("div", { class: "who" }, "prompt", h("span", { class: "muted" }, when)),
          long ? h("details", {}, h("summary", {}, c.text.split("\n")[0].slice(0, 140) + " …"), md(c.text)) : md(c.text)));
      } else if (c.type === "text") {
        turns += 1;
        out.append(h("div", { class: "turn assistant" }, h("div", { class: "who" }, "claude", h("span", { class: "muted" }, when)), md(c.text)));
      } else if (c.type === "thinking") {
        out.append(h("details", { class: "turn thinking" }, h("summary", {}, "thinking"), md(c.thinking || "")));
      } else if (c.type === "tool_use") {
        const r = results[c.id], inp = c.input || {};
        const head = inp.command || inp.file_path || inp.pattern || inp.path || inp.description || JSON.stringify(inp).slice(0, 120);
        const res = r ? (Array.isArray(r.content) ? r.content.map((x) => x.text || "").join("\n") : String(r.content ?? "")) : null;
        out.append(h("details", { class: `turn tool${r?.is_error ? " failed" : ""}` },
          h("summary", {}, h("b", {}, c.name), " ", h("span", { class: "mono" }, String(head).split("\n")[0].slice(0, 160)),
            r ? null : h("span", { class: "muted" }, " · running")),
          inp.command ? code(inp.command, "bash") : inp.old_string != null ? code(`- ${inp.old_string}\n+ ${inp.new_string}`, "diff")
                      : inp.content != null ? code(inp.content, CODE[(String(inp.file_path || "").split(".").pop() || "").toLowerCase()]) : code(JSON.stringify(inp, null, 2), "json"),
          res != null ? h("div", {}, h("div", { class: "muted small" }, r.is_error ? "it failed:" : "it said:"), h("pre", { class: "plain" }, res.slice(0, 20000))) : null));
      }
    }
  }
  if (!out.children.length) out.append(h("p", { class: "muted" }, "nothing said yet"));
  return out;
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
    const needle = search.value.trim().toLowerCase();
    const rows = d.items.filter((i) => !needle || (i.id + " " + JSON.stringify(i.fields)).toLowerCase().includes(needle));
    const val = (v) => v == null ? "" : typeof v === "object" ? JSON.stringify(v) : String(v);
    const kindOf = Object.fromEntries(d.kinds.map((x) => [x.name, x]));
    const tableOf = (its, show, limit) => h("table", { class: "items" }, h("tr", {}, ["item", "state", ...show, "in state", "events", "latest", "last"].map((x) => h("th", {}, x))),
      its.slice(0, limit).map((i) => h("tr", { class: "click", onclick: () => { location.hash = `#/item/${encodeURIComponent(i.id)}`; } },
        h("td", { class: "nowrap" }, h("b", {}, i.id)), h("td", {}, i.state ? stateChip(i.state, true) : "–"),
        show.map((f) => h("td", { class: "cell", title: val(i.fields[f]) }, fieldView(i.fields[f], true, 0, (kindOf[i.kind]?.formats || {})[f]))),
        h("td", { class: "num nowrap" }, i.state ? dur(nowS() - i.entered) : ""), h("td", { class: "num" }, i.events), h("td", { class: "muted nowrap" }, i.latest), h("td", { class: "muted nowrap" }, ago(i.last)))));
    const groups = (kind ? d.kinds.filter((k) => k.name === kind) : d.kinds).map((k) => [k.name, k.show]);
    if (!kind && d.unkinded) groups.push(["", []]);
    const parts = [];
    for (const [name, show] of groups) {                   // one table per kind, each with its own columns
      const its = rows.filter((i) => (i.kind || "") === name);
      if (!its.length) continue;
      const limit = kind ? 300 : 25;
      if (!kind) parts.push(h("h2", {}, name || "no kind", ` (${its.length})`));
      parts.push(tableOf(its, show, limit));
      if (its.length > limit) parts.push(h("p", { class: "muted small" }, h("a", { href: "#", onclick: (ev) => { ev.preventDefault(); kind = name; state = null; go(); } }, `all ${its.length} →`)));
    }
    box.replaceChildren(...(parts.length ? parts : [d.items.length ? h("p", { class: "muted" }, "nothing matches") : ""]));
    more.textContent = d.total > d.items.length ? `${d.total - d.items.length} older items not loaded` : "";
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
      d.moves.map((m, i) => h("tr", {}, h("td", { class: "num nowrap" }, new Date(m.time * 1000).toLocaleString([], { hour12: false })), h("td", { class: m.from ? "" : "muted" }, m.from || "(arrived)"), h("td", {}, stateChip(m.to, true)),
        h("td", { class: "muted" }, m.type), h("td", { class: "num muted" }, i ? dur(m.time - d.moves[i - 1].time) : "")))) : h("p", { class: "muted" }, "its kind has no states");
    // its kind's chosen fields first, in their order, then the rest by name
    const first = (k?.show || []).filter((f) => f in d.fields);
    const order = [...first, ...Object.keys(d.fields).filter((f) => !first.includes(f)).sort()];
    const fields = order.length ? h("table", { class: "fields" }, order.map((f) => h("tr", {},
      h("th", {}, f), h("td", {}, fieldView(d.fields[f], false, 0, (k?.formats || {})[f])))))
      : h("p", { class: "muted" }, "no fields: its events carry no data");
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
    "The wiring view shows what actually happened between the machines in the window, from the event log: a line only where an event proves one reached another (caused by it, or listened for and run after), dashed where the model declares a connection the log never shows. The slider in the header shows any past moment."));
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

