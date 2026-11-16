/* the pages besides the diagram: Loops, Agents, Record, Items, an item, Residuals, Check (the Guide: guide.js) */
"use strict";
/* ------------------------------------------------------------------ the other pages */

function page(main, title) {
  const p = h("div", { class: "page" }, h("h1", {}, title));
  main.append(p);
  return p;
}
const RANK = { off: 0, open: 1, unknown: 2, holding: 3 };   // the loops that need someone first
const windowNote = () => {
  const st = S.status, recorded = st?.first ? st.at - st.first : null;
  return st?.window ? (recorded != null && recorded < st.window * 0.95 ? `over the ${dur(recorded)} recorded` : `over the last ${dur(st.window)}`) : "";
};
const table = (head, rows, cls = "") => h("div", { class: "table-wrap" }, h("table", { class: cls },
  h("tr", {}, head.map((x) => (Array.isArray(x) ? h("th", { class: x[1] }, x[0]) : h("th", {}, x)))), rows));

async function pageLoops(main) {
  const p = page(main, "Loops");
  const box = h("div"), cap = h("p", { class: "note" });
  p.append(box, cap);
  async function tick() {
    const loops = await api("loops");
    // the stocks' trends: every system open (or, where that is not at hand, a snapshot, each closed system's measures)
    const stocks = await api("graph", { open: "*" }).catch(() => api("graph"));
    for (const n of stocks.nodes) for (const m of n.measures || []) if (m.points) stocks.nodes.push({ kind: "stock", label: m.label, points: m.points });
    const w = windowNote();
    cap.textContent = w ? `Time off and back in: ${w}. Back in: typically, from going off to holding again.` : "";
    const pts = Object.fromEntries(stocks.nodes.filter((n) => n.kind === "stock").map((n) => [n.label, n.points]));
    const rows = Object.entries(loops).sort((a, b) => (RANK[a[1].status] ?? 2) - (RANK[b[1].status] ?? 2));
    box.replaceChildren(table(["loop", "status", "holds", ["now", "num"], ["setpoint", "num"], ["error", "num"], ["time off", "num"], ["back in", "num"], "trend", "acted"],
      rows.map(([n, lp]) => h("tr", { class: "click", onclick: () => openLoop(n) },
        h("td", { class: "nowrap" }, h("b", {}, n), lp.open_loop ? h("span", { class: "muted", title: "Acts on its schedule, reads nothing" }, " open loop") : null),
        h("td", {}, statusEl(lp.status)), h("td", { class: "nowrap" }, lp.stock), h("td", { class: "num" }, fmt(lp.value)),
        h("td", { class: "num nowrap" }, op(lp.setpoint) + (lp.band || "")),
        h("td", { class: "num", title: "e = r − y" }, lp.error != null ? fmt(lp.error) : ""),
        h("td", { class: "num", title: "The share of the window the loop spent off" }, lp.off_share ? `${Math.round(lp.off_share * 100)}%` : "0%"),
        h("td", { class: "num", title: lp.back_in != null ? `Typically holding again this long after going off (slowest ${dur(lp.back_in_slowest)}, ${lp.times_off} times); its valve opens ${lp.answers_in != null ? dur(lp.answers_in) : "?"} after` : "It has not gone off and come back in the window" },
          lp.back_in != null ? dur(lp.back_in) : "–"),
        h("td", {}, (pts[lp.stock] || []).length > 1 ? sparkSvg(pts[lp.stock], 120, 24, setpointOf(lp.setpoint)) : ""),
        h("td", { title: "In the window, its sensor read and its controller decided or its valve opened" }, lp.observed ? "yes" : h("span", { class: "muted" }, "no"))))));
  }
  await tick();
  S.timer = setInterval(tick, 3000);
}

/* the ladder: one list, by rung, from the most general agent to none; the ladder itself one line of counts */
async function pageAgents(main) {
  const p = page(main, "Agents");
  const ladder = h("div", { class: "ladder-line" }), box = h("div");
  p.append(ladder, box);
  async function tick() {
    const agents = await api("agents");
    const cols = [...RUNG_NAMES, "retired"];
    const of = (i) => Object.entries(agents).filter(([, a]) => a.rung === i);
    ladder.replaceChildren(...cols.flatMap((k, i) => [i ? h("span", { class: "arrow" }, "→") : null,
      h("span", { class: "step", title: RUNG_HINT[i] }, of(i).length ? h("b", {}, String(of(i).length)) : "0", ` ${k}`)]).filter(Boolean));
    const last = (a) => a.runs_itself ? (a.running_since ? `running for ${ago(a.running_since).replace(" ago", "")}` : a.last ? ago(a.last.time) : "never ran")
      : a.kind === "person" ? "a person" : "not run here";
    const groups = cols.map((k, i) => [i, k, of(i)]).filter(([, , xs]) => xs.length);
    box.replaceChildren(h("div", { class: "table-wrap" }, h("table", {},
      h("tr", {}, h("th", {}, "agent"), h("th", {}, "roles"), h("th", { class: "num" }, "runs"), h("th", {}, "last run"), h("th", {}, "runs when")),
      groups.map(([i, k, xs]) => h("tbody", { class: "group" },
        h("tr", {}, h("th", { colspan: 5 }, `${i} ${k}`, h("span", { class: "muted" }, `  ${RUNG_HINT[i]}`))),
        xs.map(([name, a]) => h("tr", { class: "click", onclick: () => openAgent(name) },
          h("td", { class: "nowrap" }, h("b", {}, name), a.failing ? h("span", { class: "s-off" }, " failing") : null),
          h("td", {}, (a.roles || []).map((r) => `${r.kind} ${r.name}`).join(", ") || h("span", { class: "muted" }, "no roles"),
            (a.hints || []).length ? h("ul", { class: "hints" }, a.hints.map((hint) => h("li", { class: hint.about === "loop" ? "warn" : "", title: hint.says },
              hint.about === "loop" ? op(hint.says)
                : `${hint.controller}: “${hint.decision}” ${Math.round(hint.share * 100)}% of ${hint.count}; a cheaper rung could fill it`))) : null),
          h("td", { class: "num" }, a.runs_itself ? String(a.runs) : ""),
          h("td", { class: "nowrap muted" }, last(a)),
          h("td", { class: "muted" }, a.schedule || a.every || ""))))))));
  }
  await tick();
  S.timer = setInterval(tick, 3000);
}

async function pageRecord(main, q) {
  const p = page(main, "Record");
  const filt = h("input", { type: "search", placeholder: "Type, e.g. valve.* or ticket.*", value: q.get("type") || "", "aria-label": "Event type" });
  const runs = h("input", { type: "checkbox" });
  const box = h("div");
  // from the wiring: one machine's events (its instances too), in the page's window
  const machine = q.get("machine") || "", inWindow = q.get("window") === "1";
  const scope = machine || inWindow ? h("span", { class: "muted" }, [machine ? `from ${machine}` : "", inWindow ? "in the window" : ""].filter(Boolean).join(", "),
    " ", h("a", { href: "#/record" + (filt.value ? "?type=" + encodeURIComponent(filt.value) : "") }, "Show all")) : null;
  p.append(h("div", { class: "filters" }, filt, h("button", { onclick: () => tick() }, "Filter"), scope,
                h("label", { class: "check" }, runs, "Show runs", h("span", { class: "muted" }, "(agent.started, agent.ran)"))), box);
  runs.addEventListener("change", () => tick());
  filt.addEventListener("keydown", (ev) => { if (ev.key === "Enter") tick(); });
  async function tick() {
    let evs;
    try {
      evs = await api("events", { n: 80, ...(runs.checked ? { runs: 1 } : {}), ...(filt.value ? { type: filt.value } : {}),
                                  ...(machine ? { machine } : {}), ...(inWindow ? { window: 1 } : {}) });
    } catch (err) { box.replaceChildren(h("p", { class: "muted" }, String(err.message || err))); return; }
    box.replaceChildren(evs.length ? eventsTable(evs, false) : h("p", { class: "muted" }, "Nothing recorded yet."));
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
    const url = fileUrl(path);
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
const fileUrl = (path) => "/file/" + path.split("/").map(encodeURIComponent).join("/");   // a path: relative links resolve
function render(text, fmt, path) {
  if (fmt === "markdown") return md(text, path);
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
function md(text, path = null) {                          // Markdown, its raw HTML shown as text (nothing in it runs), code highlighted
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
  for (const a of el.querySelectorAll("a")) {
    const href = a.getAttribute("href") || "";
    if (path && href && !/^([a-z][a-z0-9+.-]*:|\/|#)/i.test(href)) {      // relative to the file: beside it in the project
      a.href = new URL(href, location.origin + fileUrl(path)).pathname;
    }
    a.target = "_blank"; a.rel = "noopener";
  }
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
            r ? null : h("span", { class: "muted" }, ", running")),
          inp.command ? code(inp.command, "bash") : inp.old_string != null ? code(`- ${inp.old_string}\n+ ${inp.new_string}`, "diff")
                      : inp.content != null ? code(inp.content, CODE[(String(inp.file_path || "").split(".").pop() || "").toLowerCase()]) : code(JSON.stringify(inp, null, 2), "json"),
          res != null ? h("div", {}, h("div", { class: "muted small" }, r.is_error ? "It failed:" : "It said:"), h("pre", { class: "plain" }, res.slice(0, 20000))) : null));
      }
    }
  }
  if (!out.children.length) out.append(h("p", { class: "muted" }, "Nothing said yet."));
  return out;
}

function stateWord(st) { return st ? h("span", {}, st) : h("span", { class: "muted" }, "–"); }

async function pageItems(main, q) {
  const p = page(main, "Items");
  const kinds = h("div", { class: "kinds" }), notes = h("div"), box = h("div");
  const search = h("input", { type: "search", placeholder: "Search ids and fields", value: q.get("q") || "", "aria-label": "Search" });
  const more = h("p", { class: "note" });
  p.append(kinds, notes, h("div", { class: "filters" }, search), box, more);
  let kind = q.get("kind"), state = q.get("state");
  const go = () => { const u = new URLSearchParams(); if (kind) u.set("kind", kind); if (state) u.set("state", state); if (search.value) u.set("q", search.value);
                     history.replaceState(null, "", "#/items" + (u.toString() ? "?" + u : "")); tick(); };
  search.addEventListener("input", () => go());
  async function tick() {
    const d = await api("items", { ...(kind ? { kind } : {}), ...(state ? { state } : {}) });
    // each kind one line: its states as counts, the ones with items in them in ink
    kinds.replaceChildren(...d.kinds.flatMap((k) => [
      h("a", { href: "#", class: `kname${kind === k.name && !state ? " on" : ""}`, onclick: (ev) => { ev.preventDefault(); kind = kind === k.name && !state ? null : k.name; state = null; go(); } },
        k.name, h("span", { class: "mono" }, k.id)),
      h("div", { class: "states" }, (k.states.length ? k.states : [""]).map((st, i) => [i ? h("span", { class: "arrow" }, "→") : null,
        h("a", { href: "#", class: `stbox${k.counts[st] ? " some" : ""}${kind === k.name && state === st ? " on" : ""}`,
                 onclick: (ev) => { ev.preventDefault(); [kind, state] = kind === k.name && state === st ? [null, null] : [k.name, st]; go(); } },
          h("span", { class: "n" }, String(k.counts[st] || 0)), st || "items")]))]));
    notes.replaceChildren(...[
      d.unkinded ? h("p", { class: "note" }, `${d.unkinded} item${d.unkinded > 1 ? "s" : ""} match no kind under items: in ergostat.yaml; shown with their fields, no state.`) : null,
      !d.kinds.length && !d.unkinded ? h("p", { class: "muted" }, "No items yet. An item is what events with an id like ticket/12 are about; see the Guide.") : null].filter(Boolean));
    const needle = search.value.trim().toLowerCase();
    const rows = d.items.filter((i) => !needle || (i.id + " " + JSON.stringify(i.fields)).toLowerCase().includes(needle));
    const val = (v) => v == null ? "" : typeof v === "object" ? JSON.stringify(v) : String(v);
    const kindOf = Object.fromEntries(d.kinds.map((x) => [x.name, x]));
    const isNum = (its, f) => its.some((i) => typeof i.fields[f] === "number") && its.every((i) => i.fields[f] == null || typeof i.fields[f] === "number");
    const tableOf = (its, show, limit) => {
      const nums = new Set(show.filter((f) => isNum(its, f)));
      return table(["item", "state", ...show.map((f) => (nums.has(f) ? [f, "num"] : f)), ["in state", "num"], ["events", "num"], "latest", "last"],
        its.slice(0, limit).map((i) => h("tr", { class: "click", onclick: () => { location.hash = `#/item/${encodeURIComponent(i.id)}`; } },
          h("td", { class: "nowrap" }, h("b", {}, i.id)), h("td", { class: "nowrap" }, stateWord(i.state)),
          show.map((f) => h("td", { class: nums.has(f) ? "num" : "cell", title: val(i.fields[f]) }, fieldView(i.fields[f], true, 0, (kindOf[i.kind]?.formats || {})[f]))),
          h("td", { class: "num nowrap" }, i.state ? dur(nowS() - i.entered) : ""), h("td", { class: "num" }, String(i.events)),
          h("td", { class: "muted nowrap" }, i.latest), h("td", { class: "muted nowrap" }, ago(i.last)))), "items");
    };
    const groups = (kind ? d.kinds.filter((k) => k.name === kind) : d.kinds).map((k) => [k.name, k.show]);
    if (!kind && d.unkinded) groups.push(["", []]);
    const parts = [];
    for (const [name, show] of groups) {                   // one table per kind, each with its own columns
      const its = rows.filter((i) => (i.kind || "") === name);
      if (!its.length) continue;
      const limit = kind ? 300 : 25;
      parts.push(h("h2", {}, name || "No kind", h("span", { class: "muted" }, ` ${its.length}`)));
      parts.push(tableOf(its, show, limit));
      if (its.length > limit) parts.push(h("p", { class: "note" }, h("a", { href: "#", onclick: (ev) => { ev.preventDefault(); kind = name; state = null; go(); } }, `All ${its.length}`)));
    }
    box.replaceChildren(...(parts.length ? parts : [d.items.length ? h("p", { class: "muted" }, "Nothing matches.") : ""]));
    more.textContent = d.total > d.items.length ? `${d.total - d.items.length} older items not loaded.` : "";
  }
  await tick();
  S.timer = setInterval(tick, 4000);
}

async function pageItem(main, id) {
  const p = page(main, id);
  const body = h("div");
  p.append(body);
  async function tick() {
    let d;
    try { d = await api(`items/${encodeURIComponent(id)}`); } catch (e) { d = null; }
    if (!d) { body.replaceChildren(h("p", { class: "muted" }, "Nothing is recorded about this id.")); return; }
    const k = d.kind_of;
    const pair = (label, value) => h("span", {}, h("span", {}, label), value);
    const head = h("div", { class: "meta" },
      pair("Kind", k ? h("a", { href: `#/items?kind=${encodeURIComponent(k.name)}` }, k.name) : h("span", { class: "muted" }, "none (nothing under items: matches this id)")),
      d.state ? pair("State", h("span", {}, h("b", {}, d.state), ` for ${dur(nowS() - d.entered)}`)) : null,
      pair("Events", String(d.events)), pair("First", ago(d.first)), pair("Latest", h("span", {}, d.latest, h("span", { class: "muted" }, `, ${ago(d.last)}`))));
    const track = k && k.states.length ? h("div", { class: "track" }, k.states.map((st, i) => [i ? h("span", { class: "arrow" }, "→") : null,
      h("span", { class: `stbox${st === d.state ? " on" : ""}${d.moves.some((m) => m.to === st) || (i === 0) ? " been" : ""}` }, st)])) : null;
    const moves = d.moves.length ? table(["when", "from", "to", "by event", ["after", "num"]],
      d.moves.map((m, i) => h("tr", {}, h("td", { class: "nowrap" }, new Date(m.time * 1000).toLocaleString([], { hour12: false })), h("td", { class: m.from ? "" : "muted" }, m.from || "arrived"), h("td", {}, m.to),
        h("td", { class: "muted" }, m.type), h("td", { class: "num muted" }, i ? dur(m.time - d.moves[i - 1].time) : "")))) : h("p", { class: "muted" }, "Its kind has no states.");
    // its kind's chosen fields first, in their order, then the rest by name
    const first = (k?.show || []).filter((f) => f in d.fields);
    const order = [...first, ...Object.keys(d.fields).filter((f) => !first.includes(f)).sort()];
    const fields = order.length ? h("div", { class: "table-wrap" }, h("table", { class: "fields" }, order.map((f) => h("tr", {},
      h("th", {}, f), h("td", {}, fieldView(d.fields[f], false, 0, (k?.formats || {})[f]))))))
      : h("p", { class: "muted" }, "No fields: its events carry no data.");
    body.replaceChildren(head, track || "", h("h2", {}, "Fields"), fields, h("h2", {}, "How it moved"), moves,
      h("h2", {}, "Events", h("span", { class: "muted" }, ` ${d.events}`)), eventsTable(d.record, true));
  }
  await tick();
  S.timer = setInterval(() => { if (!body.querySelector("details[open]")) tick(); }, 4000);
}

async function pageResiduals(main) {
  const p = page(main, "Residuals");
  const cap = h("p", { class: "note" }), box = h("div");
  p.append(box, cap);
  async function tick() {
    const r = await api("residuals");
    const w = windowNote();
    cap.textContent = w ? `Changes ${w}. A disturbance nothing measures is estimated from the rest; what is left is unexplained.` : "";
    const rows = Object.entries(r).sort((a, b) => (b[1].significant ? 1 : 0) - (a[1].significant ? 1 : 0));
    box.replaceChildren(Object.keys(r).length ? table(["stock", ["changed", "num"], ["explained", "num"], ["unexplained", "num"], ""],
      rows.map(([k, v]) => h("tr", {}, h("td", {}, h("b", {}, k)), h("td", { class: "num" }, fmt(v.change)), h("td", { class: "num" }, fmt(v.explained)),
        h("td", { class: "num" }, fmt(v.unexplained)),
        h("td", {}, v.significant ? h("span", { class: "s-open" }, "unexplained") : (v.absorbed_by.length ? h("span", { class: "muted" }, `estimated as ${v.absorbed_by.join(", ")}`) : "")))), "fit")
      : h("p", { class: "muted" }, "No stock has two readings in this window yet."));
  }
  await tick();
  S.timer = setInterval(tick, 5000);
}

async function pageCheck(main) {
  const st = await api("status");
  const errors = st.check.filter((c) => c.level === "error").length, warnings = st.check.length - errors;
  const words = [errors ? `${errors} error${errors > 1 ? "s" : ""}` : "", warnings ? `${warnings} warning${warnings > 1 ? "s" : ""}` : ""].filter(Boolean);
  const p = page(main, words.length ? `Check: ${words.join(", ")}` : "The model is whole");
  if (st.check.length) p.append(h("div", { class: "att" }, st.check.map((c) => h("div", {},
    h("b", { class: c.level === "error" ? "lvl-error" : "lvl-warning" }, c.level === "error" ? "Error" : "Warning"), " ", op(c.message)))));
  p.append(h("h2", {}, "Counts"), h("dl", { class: "counts" }, Object.entries(st.counts).flatMap(([k, v]) => [h("dt", {}, k), h("dd", {}, fmt(v))])));
}
