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
/* a part of a page known by what it is, wherever a refresh puts it (patch() matches by it) */
const keyed = (el, key) => { if (el?.nodeType) el.__key = String(key); return el; };

async function pageLoops(main) {
  const p = page(main, "Loops");
  const box = h("div"), cap = h("p", { class: "note" });
  p.append(box, cap);
  const ans = answers();
  async function tick(force = true) {
    ans.begin();
    // every loop in one answer: its stock's trend, and how it is doing (control.js), worked out on the server in the background
    const loops = await ans.api("loops", { perf: 1 });
    const word = (s) => (s == null || s.not_analysed ? "" : s.working ? "being worked out" : s.failed ? "could not be worked out" : performanceWord(s));
    const w = windowNote();
    setText(cap, w ? `Time off and back in: ${w}. Back in: typically, from going off to holding again.` : "");
    if (!force && !ans.changed) return;                  // nothing changed: nothing touched
    const rows = Object.entries(loops).sort((a, b) => (RANK[a[1].status] ?? 2) - (RANK[b[1].status] ?? 2));
    patch(box, table(["loop", "status", "holds", ["now", "num"], ["setpoint", "num"], ["error", "num"], ["time off", "num"], ["back in", "num"], "trend", "behaviour", "acted"],
      rows.map(([n, lp]) => h("tr", { class: "click", key: n, onclick: () => openLoop(n) },
        h("td", { class: "nowrap" }, h("button", { class: "name", type: "button", onclick: (ev) => { ev.stopPropagation(); openLoop(n); } }, h("b", {}, n)), lp.open_loop ? h("span", { class: "muted", title: "Acts on its schedule, reads nothing" }, " open loop") : null),
        h("td", {}, statusEl(lp.status)), h("td", { class: "nowrap" }, lp.stock), h("td", { class: "num" }, fmt(lp.value)),
        h("td", { class: "num nowrap" }, op(lp.setpoint) + (lp.band || "")),
        h("td", { class: "num", title: "e = r − y" }, lp.error != null ? fmt(lp.error) : ""),
        h("td", { class: "num", title: "The share of the window the loop spent off" }, lp.off_share ? `${Math.round(lp.off_share * 100)}%` : "0%"),
        h("td", { class: "num", title: lp.back_in != null ? `Typically holding again this long after going off (slowest ${dur(lp.back_in_slowest)}, ${lp.times_off} times); its valve opens ${lp.answers_in != null ? dur(lp.answers_in) : "?"} after` : "It has not gone off and come back in the window" },
          lp.back_in != null ? dur(lp.back_in) : "–"),
        h("td", { class: "spark-cell", title: "Its scope: r and y, u, e over the window" },
          (lp.points || []).length > 1 ? sparkSvg(lp.points, 120, 24, setpointOf(lp.setpoint)) : ""),
        h("td", { class: "nowrap", "data-perf": n, title: "Oscillating, saturated, or its Harris index: from its scope, over the last day of record" }, word(lp.perf)),
        h("td", { title: "In the window, its sensor read and its controller decided or its valve opened" }, lp.observed ? "yes" : h("span", { class: "muted" }, "no"))))));
  }
  await tick();
  S.timer = poll(() => tick(false), 3000, p);
}

/* the ladder: one list, by rung, from the most general agent to none; the ladder itself one line of counts */
async function pageAgents(main) {
  const p = page(main, "Agents");
  const ladder = h("div", { class: "ladder-line" }), box = h("div"), cap = h("p", { class: "note" }), dbox = h("div");
  p.append(ladder, box, cap, dbox);
  const ans = answers();
  async function tick(force = true) {
    ans.begin();
    const agents = await ans.api("agents"), daemons = await ans.api("daemons");
    const w = WINDOW_WORDS[S.since] ? `over the ${WINDOW_WORDS[S.since].toLowerCase()}` : windowNote();
    setText(cap, `What the runs cost${w ? ", " + w : ""}: dollars their AI sessions cost (as Claude Code reported them; ` +
      `"est." where only tokens were known and a price table priced them), their tokens, the CPU time of each run's ` +
      `processes (user and system), and the most memory one run held. Open an agent for its history, run by run.`);
    if (!force && !ans.changed) return;                  // nothing changed: nothing touched
    const cols = [...RUNG_NAMES, "retired"];
    const of = (i) => Object.entries(agents).filter(([, a]) => a.rung === i);
    patch(ladder, ...cols.map((k, i) => h("span", { class: "step", "data-kind": k, title: RUNG_HINT[i] },
      of(i).length ? h("b", {}, String(of(i).length)) : "0", ` ${k}`)), h("span", { class: "muted" }, "most general → most specific"));
    const last = (a) => a.runs_itself ? (a.running_since ? `running for ${ago(a.running_since).replace(" ago", "")}` : a.last ? ago(a.last.time) : "never ran")
      : a.kind === "person" ? "a person" : "not run here";
    const groups = cols.map((k, i) => [i, k, of(i)]).filter(([, , xs]) => xs.length);
    const use = (a) => a.use || {};
    patch(box, h("div", { class: "table-wrap" }, h("table", {},
      h("tr", {}, h("th", {}, "agent"), h("th", {}, "roles"), h("th", { class: "num" }, "runs"), h("th", {}, "last run"), h("th", {}, "runs when"),
        h("th", { class: "num", title: "What its AI sessions cost in the window, in USD" }, "cost"),
        h("th", { class: "num", title: "Tokens its AI sessions used in the window: input, output, cache reads and writes" }, "tokens"),
        h("th", { class: "num", title: "CPU time of its runs' processes in the window, user and system" }, "CPU"),
        h("th", { class: "num", title: "The most memory one of its runs held (its processes together)" }, "peak memory")),
      groups.map(([i, k, xs]) => h("tbody", { class: "group", key: k },
        h("tr", {}, h("th", { colspan: 9, "data-kind": k }, `${k} · `, h("span", { class: "count" }, String(xs.length)),
          h("small", { class: "muted" }, `  rung ${i}, ${RUNG_HINT[i]}`))),
        xs.map(([name, a]) => h("tr", { class: "click", key: name, onclick: () => openAgent(name) },
          h("td", { class: "nowrap" }, h("b", {}, name), a.failing ? h("span", { class: "s-off" }, " failing") : null),
          h("td", {}, rolesText(a.roles) || h("span", { class: "muted" }, "no roles"),
            (a.hints || []).length ? h("ul", { class: "hints" }, a.hints.map((hint) => h("li", { class: hint.about === "loop" ? "warn" : "", title: hint.says },
              hint.about === "loop" ? op(hint.says)
                : `${hint.controller}: “${hint.decision}” ${Math.round(hint.share * 100)}% of ${hint.count}; a cheaper rung could fill it`))) : null),
          h("td", { class: "num" }, a.runs_itself ? String(a.runs) : ""),
          h("td", { class: "nowrap muted" }, last(a)),
          h("td", { class: "muted" }, a.schedule || a.every || (a.leased ? "on demand, per item (leased)"
            : a.runs_itself ? "on demand" : a.kind === "person" ? "by a person" : "not run here")),
          h("td", { class: "num nowrap", "data-use": "cost", title: use(a).cost ? `${use(a).cost}, over ${use(a).ai_runs} runs` : "" },
            usd(use(a).cost_usd), use(a).cost && use(a).cost !== "reported" ? h("span", { class: "muted" }, " est.") : null),
          h("td", { class: "num", "data-use": "tokens" }, tokensText(use(a).ai_runs ? use(a).tokens : null)),
          h("td", { class: "num", "data-use": "cpu" }, cpuText(use(a).cpu)),
          h("td", { class: "num", "data-use": "memory" }, bytesText(use(a).memory_peak)))))))));
    const ds = Object.entries(daemons || {});
    patch(dbox, ...(ds.length ? [h("h3", {}, "Daemons"), h("p", { class: "note" }, "Long-lived processes the blocks' runs and the " +
      "sensors' readings are handed to (SPEC §9.7). Their CPU and memory are the process's, sampled; an item's run is charged its wall time only."),
      h("div", { class: "table-wrap" }, h("table", { "data-daemons": "" },
        h("tr", {}, ["daemon", "state", "serves", "restarts", "last line", "in flight", "CPU", "memory"].map((c, i) => h("th", i > 2 ? { class: "num" } : {}, c))),
        ds.map(([n, d]) => h("tr", { key: n, "data-daemon": n },
          h("td", { class: "nowrap", title: d.run || "" }, h("b", {}, n)),
          h("td", { title: d.why || "" }, h("span", { class: d.state === "running" ? "s-holding" : "s-off" }, d.state), d.alarm ? h("span", { class: "s-off", title: d.alarm.why }, " alarm") : null),
          h("td", { class: "muted" }, (d.users || []).length > 3 ? `${d.users.length} parts` : (d.users || []).join(", ")),
          h("td", { class: "num", title: `${d.restarts_total} in all` }, String(d.restarts)),
          h("td", { class: "num nowrap" }, d.last_line ? ago(d.last_line) : "–"),
          h("td", { class: "num" }, `${d.in_flight} of ${d.concurrency}`),
          h("td", { class: "num" }, cpuText(d.cpu)), h("td", { class: "num" }, bytesText(d.memory))))))] : []));
  }
  await tick();
  S.timer = poll(() => tick(false), 3000, p);
}

async function pageRecord(main, q) {
  const p = page(main, "Record");
  const filt = h("input", { type: "search", placeholder: "Type, e.g. valve.* or ticket.*", value: q.get("type") || "", "aria-label": "Event type" });
  const runs = h("input", { type: "checkbox" });
  const box = h("div");
  // one machine's events (its instances too), in the page's window: a sensor's observations link here
  const machine = q.get("machine") || "", inWindow = q.get("window") === "1", item = q.get("item") || "";
  const remote = q.get("remote") || "";                // a remote's events, read there (SPEC §4c): never the local record's
  const scope = machine || inWindow || item || remote ? h("span", { class: "muted" }, [item ? `about ${item}` : "", machine ? `from ${machine}` : "", remote ? `of remote ${remote}` : "", inWindow ? "in the window" : ""].filter(Boolean).join(", "),
    " ", h("a", { href: "/record" + (filt.value ? "?type=" + encodeURIComponent(filt.value) : "") }, "Show all")) : null;
  const remotes = h("span", { class: "remote-links" });
  if (!SNAP) api("items", { n: 1 }).then((d) => patch(remotes, ...(d.remotes || []).map((r) => h("a", { key: r.name, class: r.name === remote ? "on" : "",
    href: `/record?remote=${encodeURIComponent(r.name)}`, title: `${r.url}: its events, read there` }, `remote ${r.name}`)))).catch(() => {});
  p.append(h("div", { class: "filters" }, filt, h("button", { onclick: () => tick() }, "Filter"), scope, remotes,
                h("label", { class: "check" }, runs, "Show runs", h("span", { class: "muted" }, "(agent.started, agent.ran)"))), box);
  runs.addEventListener("change", () => tick());
  filt.addEventListener("keydown", (ev) => { if (ev.key === "Enter") tick(); });
  const ans = answers();
  async function tick(force = true) {
    if (remote) {                                       // what failed said, with how old what is shown is; never "nothing"
      const d = await remoteApi("events", { remote, n: 80, ...(filt.value ? { type: filt.value } : {}) });
      if (!p.isConnected) return;
      const list = d.failed ? null : d.events.length ? eventsTable(d.events, false) : d.ok ? h("p", { class: "muted" }, "Nothing recorded yet.") : null;
      patch(box, ...[remoteSaid(remote, d), list].filter(Boolean));
      return;
    }
    let evs;
    ans.begin();
    try {
      evs = await ans.api("events", { n: 80, ...(runs.checked ? { runs: 1 } : {}), ...(filt.value ? { type: filt.value } : {}),
                                  ...(machine ? { machine } : {}), ...(item ? { item } : {}), ...(inWindow ? { window: 1 } : {}) });
    } catch (err) { patch(box, h("p", { class: "muted" }, String(err.message || err))); return; }
    if (!force && !ans.changed) return;                  // nothing changed: nothing touched
    patch(box, evs.length ? eventsTable(evs, false) : h("p", { class: "muted" }, "Nothing recorded yet."));
  }
  await tick();
  S.timer = poll(() => tick(false), 3000, p);
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
const LIST_SHOWN = 40;      // a long list (a session's messages) shows its latest; the API and the CLI give all of it
function fieldView(v, small = false, depth = 0, declared = null, there = "") {
  if (v == null || v === "") return h("span", { class: "muted" }, "–");
  // a remote's file: is a file in its own project, never ours: text, never fetched from our /file/ (SPEC §4c)
  if (there && typeof v === "string" && v.startsWith("file:")) return h("span", { class: "mono remote-file", title: `a file at remote ${there}, not read here` }, v);
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
      const shown = v.slice(-LIST_SHOWN), cols = [...new Set(shown.flatMap((x) => Object.keys(x)))];
      return h("div", {}, v.length > shown.length ? h("p", { class: "note" }, `The latest ${shown.length} of ${v.length}.`) : null,
        h("table", { class: "sub" }, h("tr", {}, cols.map((c) => h("th", {}, c))),
          shown.map((x) => h("tr", {}, cols.map((c) => h("td", {}, fieldView(x[c], false, depth + 1, null, there)))))));
    }
    return v.length ? v.map((x, i) => [i ? ", " : "", fieldView(x, false, depth + 1, null, there)]) : h("span", { class: "muted" }, "none");
  }
  return h("table", { class: "sub" }, Object.entries(v).map(([k, x]) => h("tr", {}, h("th", {}, k), h("td", {}, fieldView(x, false, depth + 1, null, there)))));
}

/* a file's contents, shown as what they are: one view of each file, kept across refreshes and asked for again
   with each (a 304 while it is the same); changed, only what differs in it is redrawn (open tool calls stay open) */
const FILES = {};
function fileView(path, url, fmt) {
  const f = FILES[path] || (FILES[path] = { el: h("div", { class: `file-view f-${fmt}` }, h("span", { class: "muted" }, "…")), text: null });
  f.url = url; f.fmt = fmt;
  loadFile(path);
  return live(f.el);
}
function loadFile(path) {
  const f = FILES[path];
  fetch(f.url).then((r) => (r.ok ? r.text() : Promise.reject(r.status))).then((text) => {
    if (f.text === text) return;                          // unchanged: left as it is
    f.text = text;
    patch(f.el, render(text, f.fmt, path));
  }).catch((e) => { f.text = null; patch(f.el, h("span", { class: "muted" }, `cannot read ${path} (${e})`)); });
}
/* the files on the page, asked for again (a refresh whose answers did not change still reads them) */
function refreshFiles() { for (const [path, f] of Object.entries(FILES)) if (f.el.isConnected) loadFile(path); }
const fileUrl = (path) => "/file/" + path.split("/").map(encodeURIComponent).join("/");   // a path: relative links resolve
function render(text, fmt, path) {
  if (fmt === "markdown") return md(text, path);
  if (fmt === "json") { try { text = JSON.stringify(JSON.parse(text), null, 2); } catch (e) { /* as it is */ } return code(text, "json"); }
  if (fmt === "code") return code(text, CODE[(path.split(".").pop() || "").toLowerCase()]);
  if (fmt === "claude-session") return conversation(text);
  return h("pre", { class: "plain", sig: text }, text);
}
function code(text, lang) {                               // highlighted again only when its text changed (its sig)
  const el = h("code", { class: "hljs" });
  try { el.innerHTML = lang && window.hljs?.getLanguage(lang) ? hljs.highlight(text, { language: lang }).value : (window.hljs ? hljs.highlightAuto(text).value : esc(text)); }
  catch (e) { el.textContent = text; }
  return h("pre", { class: "code", sig: `${lang || ""}\n${text}` }, el);
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
  const el = h("div", { class: "md", sig: `${path || ""}\n${text}` });     // rendered again only when its text changed
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
  // each turn known by its line and place (a refresh appends the new ones), and drawn again only when it changed
  lines.forEach((l, li) => {
    const m = l.message;
    if (!m || (l.type !== "user" && l.type !== "assistant")) return;
    const when = l.timestamp ? new Date(l.timestamp).toLocaleTimeString([], { hour12: false }) : "";
    const parts = typeof m.content === "string" ? [{ type: "text", text: m.content }] : (m.content || []);
    parts.forEach((c, ci) => {
      const key = `${l.uuid || li}:${ci}`;
      if (c.type === "tool_result") return;               // shown with its call
      if (c.type === "text" && l.type === "user") {
        const long = c.text.length > 600;
        out.append(h("div", { class: "turn user", key, sig: [when, c.text] }, h("div", { class: "who" }, "prompt", h("span", { class: "muted" }, when)),
          long ? h("details", {}, h("summary", {}, c.text.split("\n")[0].slice(0, 140) + " …"), md(c.text)) : md(c.text)));
      } else if (c.type === "text") {
        turns += 1;
        out.append(h("div", { class: "turn assistant", key, sig: [when, c.text] }, h("div", { class: "who" }, "claude", h("span", { class: "muted" }, when)), md(c.text)));
      } else if (c.type === "thinking") {
        out.append(h("details", { class: "turn thinking", key, sig: c.thinking || "" }, h("summary", {}, "thinking"), md(c.thinking || "")));
      } else if (c.type === "tool_use") {
        const r = results[c.id], inp = c.input || {};
        const head = inp.command || inp.file_path || inp.pattern || inp.path || inp.description || JSON.stringify(inp).slice(0, 120);
        const res = r ? (Array.isArray(r.content) ? r.content.map((x) => x.text || "").join("\n") : String(r.content ?? "")) : null;
        out.append(h("details", { class: `turn tool${r?.is_error ? " failed" : ""}`, key, sig: [c, r || null] },
          h("summary", {}, h("b", {}, c.name), " ", h("span", { class: "mono" }, String(head).split("\n")[0].slice(0, 160)),
            r ? null : h("span", { class: "muted" }, ", running")),
          inp.command ? code(inp.command, "bash") : inp.old_string != null ? code(`- ${inp.old_string}\n+ ${inp.new_string}`, "diff")
                      : inp.content != null ? code(inp.content, CODE[(String(inp.file_path || "").split(".").pop() || "").toLowerCase()]) : code(JSON.stringify(inp, null, 2), "json"),
          res != null ? h("div", {}, h("div", { class: "muted small" }, r.is_error ? "It failed:" : "It said:"), h("pre", { class: "plain" }, res.slice(0, 20000))) : null));
      }
    });
  });
  if (!out.children.length) out.append(h("p", { class: "muted" }, "Nothing said yet."));
  return out;
}

/* claims (SPEC §12g): what blocks said they did, checked by ergostat. Under the ergostat.claim table, how far each
   block's (each rung's, each model's) claims held; on a claim's own page, its verdict and the evidence first */
const CLAIM_KIND = "ergostat.claim";
function trustView(t) {
  const rows = t.rows.map((r) => h("tr", {}, h("td", { class: "muted" }, r.by), h("td", {}, h("b", {}, r.name)),
    h("td", { class: "num" }, String(r.claims)), h("td", { class: "num" }, String(r.verified)),
    h("td", { class: `num${r.contradicted ? " s-off" : ""}` }, String(r.contradicted)), h("td", { class: "num" }, String(r.unchecked)),
    h("td", { class: "num" }, pct(r.contradicted_share))));
  return h("div", { class: "trust" },
    h("h3", {}, "Trust", h("span", { class: "muted" }, ` over the last ${dur(t.until - t.since)}: how far each block's claims held when ergostat checked them`)),
    rows.length ? table(["by", "who", ["claims", "num"], ["verified", "num"], ["contradicted", "num"], ["unchecked", "num"], ["share contradicted", "num"]], rows, "fit compact")
      : h("p", { class: "muted" }, "No claims in this window."),
    h("p", { class: "note" }, "Unchecked claims are recorded, not trusted. A goal can hold these: a sensor reads ",
      h("code", {}, "builtin: ergostat.trust.contradicted@BLOCK"), " (or @rung:KIND, @model:MODEL)."));
}
function claimView(d) {
  const f = d.fields, ev = f.evidence || {};
  const cls = d.state === "contradicted" ? "s-off" : d.state === "unchecked" ? "s-open" : "";
  const rest = Object.entries(ev).filter(([k]) => k !== "output");
  const about = f.about && Object.keys(f.about).length ? Object.entries(f.about).map(([k, v]) => (k === "item" ? itemLink(v) : `${k} ${v}`)) : null;
  return h("div", { class: "claim" },
    h("p", {}, h("b", {}, `\u201c${f.says}\u201d`), about ? [" about ", ...about] : null, h("span", { class: "muted" },
      ` said by ${f.block}${f.rung ? ` (${f.rung}${f.model ? `, ${f.model}` : ""})` : ""}`), f.session ? [h("span", { class: "muted" }, " in "), itemLink(f.session)] : null),
    h("p", {}, h("span", { class: cls || "status" }, d.state === "made" ? "not checked yet" : d.state),
      f.kind ? h("span", { class: "muted" }, ` by the ${f.kind} check`) : null, f.why ? `: ${f.why}` : ""),
    rest.length ? dl(rest.map(([k, v]) => [k, typeof v === "object" ? JSON.stringify(v) : String(v)])) : null,
    ev.output ? h("pre", { class: "plain" }, ev.output) : null);
}

/* a decision or correction (the owner's intent, SPEC §5a): the owner's words with where they were said, and the
   owner's answers to it, each with a reason: Confirm and Dismiss while proposed; Supersede (a decision, naming the
   one that replaces it) or Retire (a correction) once confirmed */
const DECISION_KIND = "ergostat.decision", CORRECTION_KIND = "ergostat.correction";
function quoteView(w) {
  const sess = w.session ? String(w.session) : "";
  const where = [sess ? `session ${/^[0-9a-f-]{36}$/.test(sess) ? sess.slice(0, 8) : sess}` : null, w.line ? `line ${w.line}` : null,
    w.time ? String(w.time).slice(0, 16).replace("T", " ") : null, w.event ? `event ${String(w.event).slice(0, 12)}` : null].filter(Boolean).join(", ");
  return h("blockquote", { class: "owner-words" }, h("p", {}, w.text), where ? h("p", { class: "muted small" }, where) : null);
}
function intentView(d, onDone) {
  const f = d.fields, isDec = d.kind === DECISION_KIND;
  const said = h("p", { class: "small" });
  const acts = d.state === "proposed" ? ["confirm", "dismiss"] : d.state === "confirmed" ? [isDec ? "supersede" : "retire"] : [];
  const label = { confirm: "Confirm", dismiss: "Dismiss", supersede: "Supersede", retire: "Retire" };
  const hint = { confirm: "Why (optional): kept with it", dismiss: "Why not (required): the extractor learns from it",
                 supersede: "Why it no longer holds (required)", retire: "Why it no longer applies (required)" };
  const done = { confirm: "Confirmed: it is in every session's starting context from now on.", dismiss: "Dismissed, with its reason.",
                 supersede: "Superseded: the decision that replaces it holds from now on.", retire: "Retired: it is no longer shown to sessions." };
  const rows = {}, buttons = [];
  for (const a of acts) {
    const reason = h("input", { type: "text", class: "reason", placeholder: hint[a], "aria-label": `${label[a]}: reason` });
    const by = a === "supersede" ? h("select", { class: "by", "aria-label": "The decision that replaces it" }, h("option", { value: "" }, "replaced by…")) : null;
    const row = h("div", { class: "actions confirm intent-act", hidden: true, "data-act": a });
    async function answer() {
      for (const b of row.querySelectorAll("button")) b.disabled = true;
      try {
        await apiPost(`intent/${a}`, { id: d.id, reason: reason.value, ...(by ? { by: by.value } : {}) });
        said.className = "small"; said.textContent = done[a];
        row.hidden = true; onDone?.();
      } catch (err) {
        said.className = "s-open small"; said.textContent = String(err.message || err);
        for (const b of row.querySelectorAll("button")) b.disabled = false;
      }
    }
    row.append(...[reason, by].filter(Boolean), h("button", { onclick: answer }, `${label[a]} it`), h("button", { class: "ghost", onclick: () => { row.hidden = true; } }, "Cancel"));
    rows[a] = row;
    buttons.push(h("button", { class: a === "confirm" ? "" : "ghost", "data-act": a, onclick: async () => {
      for (const r of Object.values(rows)) r.hidden = true;
      row.hidden = false; reason.focus();
      if (by && by.options.length < 2) {
        const all = await api("items", { kind: DECISION_KIND }).catch(() => ({ items: [] }));
        for (const x of all.items.filter((x) => x.id !== d.id && !["dismissed", "superseded"].includes(x.state)))
          by.append(h("option", { value: x.id }, `${x.fields.decision || x.id} (${x.state})`));
      }
    } }, label[a]));
  }
  const list = (xs) => xs && xs.length ? xs.join("; ") : null;
  return h("div", { class: "intent" },
    h("p", {}, h("b", {}, isDec ? f.decision : f.correction)),
    ...(f.words || []).slice(0, 6).map(quoteView),
    (f.words || []).length > 6 ? h("p", { class: "note" }, `${f.words.length - 6} more of the owner's words, under Fields.`) : null,
    dl([["reasons", list(f.reasons)], ["rejected", (f.alternatives || []).length ? h("div", {}, ...f.alternatives.map((a) => h("div", {}, a.option, a.why ? h("span", { class: "muted" }, ` (${a.why})`) : null))) : null],
        ["corrects", f.corrects || null], ["kind of work", list(f.kind_of_work)], ["scope", list(f.scope)],
        ["supersedes", (f.supersedes || []).length ? h("div", {}, ...f.supersedes.map(itemLink)) : null],
        ["superseded by", f.superseded_by ? h("div", {}, itemLink(f.superseded_by), f.superseded_reason ? `: ${f.superseded_reason}` : "") : null],
        ["repeats", f.repeats ? itemLink(f.repeats) : null],
        ["given again", (f.repeated_by || []).length ? h("div", {}, ...f.repeated_by.map((r) => h("div", {}, itemLink(r.item)))) : null],
        ["proposed by", f.proposed_by ? `${f.proposed_by}${f.extractor?.model ? ` (${f.extractor.model})` : ""}${f.confidence != null ? `, confidence ${f.confidence}` : ""}` : null],
        ["dismissed", f.dismissed_reason || null], ["retired", f.retired_reason || null], ["confirmed", f.confirmed_reason || null]]),
    SNAP ? h("p", { class: "muted small" }, `ergostat ${isDec ? "decisions" : "corrections"} confirm ${d.id} answers it, where the project is.`)
      : buttons.length ? h("div", { class: "actions" }, ...buttons) : null,
    ...Object.values(rows), said);
}

/* the owner's messages (SPEC §12h): on the Items page's ergostat.message kind, a box to send one; on an item's page,
   the messages about it and a field to send a note about it; on a message's own page, where it went */
const MESSAGE_KIND = "ergostat.message";
function messageBox({ about = null, title = "Message", hint = null, done = null } = {}) {
  const text = h("textarea", { rows: about ? 2 : 3, placeholder: about ? `A note about ${about}: it goes to the work on it now` : "Say it as you would to whoever is doing the work: “that review can wait”, “check the flag ramp first”", "aria-label": title });
  const at = about ? null : h("input", { type: "text", placeholder: "about (optional): review/2041, block.developer", "aria-label": "About" });
  const said = h("p", { class: "note", "aria-live": "polite" });
  const send = h("button", { onclick: async () => {
    if (!text.value.trim()) { text.focus(); return; }
    send.disabled = true;
    try {
      const m = await apiSend("message", { text: text.value, ...(about ? { about } : at.value.trim() ? { about: at.value.trim() } : {}) });
      said.replaceChildren(itemLink(m.id), `: ${m.outcome}`);
      said.className = `note${m.state === "unrouted" ? " s-off" : ""}`;
      text.value = ""; if (at) at.value = "";
      done?.(m);
    } catch (e) { said.textContent = e.message; said.className = "note s-off"; }
    send.disabled = false;
  } }, "Send");
  return h("div", { class: "message-box" }, h("h3", {}, title, hint ? h("span", { class: "muted" }, ` ${hint}`) : null), text,
    h("div", { class: "row" }, at, send), said);
}
function messagesAbout(ms) {
  if (!ms.length) return h("p", { class: "muted" }, "No messages about it yet.");
  return table(["message", "state", "sent", "text", "outcome"], ms.map((m) => h("tr", { class: "click", key: m.id, ...rowLink(`/item/${encodeURIComponent(m.id)}`) },
    h("td", { class: "nowrap" }, h("a", { href: `/item/${encodeURIComponent(m.id)}`, class: "plain" }, h("b", {}, m.id.split("/")[1]))), h("td", { class: m.state === "unrouted" ? "s-off" : "" }, m.state), h("td", { class: "muted nowrap" }, ago(m.time)),
    h("td", { class: "cell" }, m.text), h("td", { class: "cell muted" }, m.outcome))), "messages");
}
function messageView(d, refresh) {
  const f = d.fields;
  const to = (f.routed_to || []).map((t) => h("li", {}, t.item ? itemLink(t.item) : h("code", {}, t.part || ""), t.block ? h("span", { class: "muted" }, ` worked on by ${t.block}`) : null,
    t.run ? h("span", { class: "muted" }, `, run ${String(t.run).slice(0, 8)}`) : null, t.session ? [h("span", { class: "muted" }, ", session "), itemLink(t.session)] : null));
  const dv = (f.deliveries || []).map((x) => h("li", {}, h("b", {}, x.how), x.session ? [" to ", itemLink(x.session)] : x.block ? ` to block ${x.block}` : "",
    x.item ? [" about ", itemLink(x.item)] : null, x.follow_up ? [": ", itemLink(x.follow_up)] : null, h("span", { class: "muted" }, ` ${ago(x.at)}`)));
  const an = (f.answers || []).map((x) => h("li", {}, h("span", { class: "muted" }, `${x.session || x.by}: `), x.says));
  const route = d.state === "unrouted" || d.state === "routed" ? (() => {
    const at = h("input", { type: "text", placeholder: "review/2041, block.developer", "aria-label": "Route it to" });
    const said = h("span", { class: "note" });
    return h("div", { class: "row" }, h("span", {}, d.state === "unrouted" ? "It reached no work. Route it to " : "Route it again, to "), at,
      h("button", { onclick: async () => {
        if (!at.value.trim()) { at.focus(); return; }
        try { const m = await apiSend("message", { route: d.id, about: at.value.trim() }); said.textContent = ` ${m.outcome}`; refresh?.(); } catch (e) { said.textContent = ` ${e.message}`; }
      } }, "Route"), said);
  })() : null;
  return h("div", { class: "claim" },
    h("blockquote", { class: "said" }, f.text),
    h("p", { class: "muted" }, `from ${f.by}, ${ago(f.sent || d.first)}, by ${f.via || "?"}`, (f.about || []).length ? [", about ", ...f.about.map((a) => (a.includes("/") ? itemLink(a) : h("code", {}, a)))] : null),
    h("p", {}, h("span", { class: d.state === "unrouted" ? "s-off" : d.state === "routed" ? "s-open" : "status" }, d.state === "routed" ? "awaiting delivery" : d.state),
      f.matched ? h("span", { class: "muted" }, ` matched by ${f.matched}`) : null, f.why ? `: ${f.why}` : ""),
    to.length ? [h("h3", {}, "Routed to"), h("ul", {}, to)] : null,
    dv.length ? [h("h3", {}, "Delivered"), h("ul", {}, dv)] : null,
    f.queued ? h("p", { class: "note" }, `Queued for ${f.queued.session}: ${f.queued.why}`) : null,
    f.missed ? h("p", { class: "s-off" }, `Missed: ${f.missed.item} finished (${f.missed.state}) before it was delivered; the work was ${f.missed.policy === "reopen" ? "reopened" : "followed up"}.`) : null,
    an.length ? [h("h3", {}, "Answered"), h("ul", {}, an)] : null,
    route);
}

/* gated actions (SPEC §12k): what a session asked to do outward, held for the owner or let through by its gate; on a
   work item's page the actions asked for about it, with Approve and Deny on each one held; on an action's own page,
   its command, where it runs, its answer and its output */
const ACTION_KIND = "ergostat.action";
function actionAnswer(a, done) {
  if (a.state !== "requested" || SNAP) return null;
  const note = h("input", { type: "text", placeholder: "why (optional)", "aria-label": "Why" });
  const said = h("span", { class: "note", "aria-live": "polite" });
  const answer = (what) => h("button", { class: what === "deny" ? "ghost" : "", onclick: async (ev) => {
    ev.stopPropagation();
    for (const b of row.querySelectorAll("button")) b.disabled = true;
    try { const got = await apiPost(`action/${encodeURIComponent(a.id)}/${what}`, note.value.trim() ? { note: note.value.trim() } : {}); said.textContent = ` ${got.state}`; done?.(); }
    catch (e) { said.textContent = ` ${e.message}`; for (const b of row.querySelectorAll("button")) b.disabled = false; }
  } }, what === "approve" ? "Approve" : "Deny");
  const row = h("div", { class: "row action-act" }, answer("approve"), answer("deny"), note, said);
  return row;
}
function actionsAbout(as, done) {
  if (!as.length) return h("p", { class: "muted" }, "No gated actions asked for about it.");
  return h("div", {}, as.map((a) => h("div", { class: "claim" },
    h("p", {}, h("a", { href: `/item/${encodeURIComponent(a.id)}`, class: "plain" }, h("b", {}, a.action)), " ",
      h("span", { class: a.state === "requested" ? "s-open" : a.state === "denied" || a.state === "failed" ? "s-off" : "status" }, a.state === "requested" ? "waiting for approval" : a.state),
      h("span", { class: "muted" }, ` ${ago(a.time)}, gate ${a.gate}, asked by ${a.by}` + (a.state === "requested" ? "" : a.state === "denied" ? `, ${a["approved by"]}` : `, approved by ${a["approved by"]}`))),
    h("pre", { class: "mono small" }, a.command || ""),
    actionAnswer(a, done))));
}
function actionView(d, refresh) {
  const f = d.fields;
  const by = f.approved_by ? `approved by ${f.approved_by}` : f.denied_by ? `denied by ${f.denied_by}` : "";
  return h("div", { class: "claim" },
    h("p", {}, h("span", { class: d.state === "requested" ? "s-open" : d.state === "denied" || d.state === "failed" ? "s-off" : "status" }, d.state === "requested" ? "waiting for approval" : d.state),
      h("span", { class: "muted" }, ` ${f.action}, class ${f.class}, gate ${f.gate}`), by ? `: ${by}` : "", f.note ? ` (${f.note})` : ""),
    h("pre", { class: "mono small" }, f.command || ""),
    h("p", { class: "muted" }, `in ${f.in || "?"}`, f.item ? [", for ", itemLink(f.item)] : null, f.session ? [", asked by ", itemLink(f.session)] : f.block ? `, asked by block ${f.block}` : ""),
    actionAnswer(d, refresh),
    d.state === "ran" || d.state === "failed" ? [h("h3", {}, `Output (exit ${f.exit ?? "none"})`), h("pre", { class: "mono small" }, f.output || "")] : null,
    (f.deliveries || []).length ? h("p", { class: "muted" }, "Given to ", f.deliveries.map((x, i) => [i ? ", " : "", x.session ? itemLink(x.session) : `block ${x.block}`, ` (${x.how})`])) : null);
}

function stateWord(st) { return st ? h("span", {}, st) : h("span", { class: "muted" }, "–"); }

/* the Items page: the kinds grouped by the system each is in (the server decides: item_systems.py), each
   system a group that folds away; a folded system keeps its charts, and its lists of items are neither drawn nor asked for.
   Which are folded is remembered per project */
const foldedKey = () => `ergostat.items.folded.${S.status?.name || ""}`;
function foldedSystems() { try { return new Set(JSON.parse(localStorage.getItem(foldedKey()) || "[]")); } catch (e) { return new Set(); } }
function rememberFolded(set) {
  try { if (set.size) localStorage.setItem(foldedKey(), JSON.stringify([...set])); else localStorage.removeItem(foldedKey()); }
  catch (e) { /* not remembered */ }
}

/* a set's span of moves, in the reader's time: ", 10:00 to 11:00" (its address says it in UTC, or in seconds) */
function setSpan(params) {
  const t = (x) => (x == null ? null : isNaN(+x) ? Date.parse(x) / 1000 : +x);
  const a = t(params?.moved_since?.[0]), b = t(params?.moved_until?.[0]);
  return a != null && b != null ? `, ${when(a)} to ${when(b)}` : "";
}

/* a remote's items and events, read there (SPEC §4c): an answer, or what failed (never taken as nothing) */
async function remoteApi(path, params) {
  if (SNAP) return { failed: true, why: "a remote is not in a snapshot" };
  try {
    const r = await fetch(`/api/${path}?${new URLSearchParams(params)}`);
    const b = await r.json().catch(() => ({}));
    return r.ok ? b : { failed: true, code: r.status, why: b.error || `${r.status}` };
  } catch (err) { return { failed: true, why: String(err.message || err) }; }
}
/* how a remote answered: not at all, or with what it said before, and how old that is */
function remoteSaid(name, d) {
  const old = d.read != null ? `; these were read ${dur(d.age)} ago` : "";
  if (d.failed || !d.ok) return h("p", { class: "note remote-says bad" }, d.code === 503 ? `${name}: ${d.why}` : `${name} does not answer (${d.why})${old}`);
  return d.why ? h("p", { class: "note remote-says" }, `${d.why}${old}`) : null;
}
/* the ids that may be opened here: as remote/items.py's openable, an allowlist (/-separated segments, no "..") */
const REMOTE_ID = /^[A-Za-z0-9_][A-Za-z0-9_.:@#+=-]*(\/[A-Za-z0-9_][A-Za-z0-9_.:@#+=-]*)*$/;
function remoteItemLink(id, name) {
  return typeof id === "string" && id.length <= 200 && REMOTE_ID.test(id) && !id.includes("..") ? h("a", { href: `/item/${encodeURIComponent(id)}?remote=${encodeURIComponent(name)}` }, id)
    : h("span", { title: "its id cannot be opened here: on its own page only" }, id);
}
/* a remote's section of the Items page, framed and marked remote: its counts by kind and state, its newest items */
function remoteSection(r, d) {
  const head = h("h2", { class: "sys-head" }, `remote ${r.name}`, h("span", { class: "muted" }, ` · ${r.url}`));
  const counts = d.failed ? null : h("div", { class: "kind-flows" }, Object.entries(d.counts).map(([k, st]) => h("div", { class: "kind-flow", key: k },
    h("span", { class: "kname" }, k), h("div", { class: "states" }, Object.entries(st).map(([s, n]) =>
      h("span", { class: `stbox${n ? " some" : ""}` }, h("span", { class: "n" }, String(n)), s || "items"))))));
  const rows = d.failed ? null : table(["item", "kind", "state", "there"], d.items.map((i) => h("tr", { key: i.id },
    h("td", { class: "nowrap" }, remoteItemLink(i.id, r.name)), h("td", {}, i.kind || ""), h("td", {}, stateWord(i.state)),
    h("td", {}, h("a", { href: `${r.url}/item/${encodeURIComponent(i.id)}`, target: "_blank", rel: "noopener" }, "its own page")))), "items");
  return h("section", { class: "sys-group remote", "data-remote": r.name, key: `remote:${r.name}` }, head, remoteSaid(r.name, d), counts, rows);
}

async function pageItems(main, q) {
  const p = page(main, "Items");
  const notes = h("div"), box = h("div", { class: "item-systems" });
  const search = h("input", { type: "search", placeholder: "Search kinds, ids and fields", value: q.get("q") || "", "aria-label": "Search" });
  const more = h("p", { class: "note" });
  let kind = q.get("kind"), state = q.get("state");
  // how the items are shown (relations.js): as lists, as a graph of their relations, or as a timeline; the graph's
  // and the timeline's choices, in the address too
  let view = ["graph", "timeline"].includes(q.get("view")) ? q.get("view") : "list";
  // the list sorted by a column's field (a header's click: up, down, off), in the address: sort=rank, sort=-rank
  let sort = q.get("sort") || "";
  // both show the frontier (the unfinished, and what they wait on) with the finished collapsed, so the timeline opens
  // at now; unless asked otherwise
  const said = (k) => (q.get(k) == null ? null : q.get(k) !== "0");
  const ask = { frontier: said("frontier"), collapse: said("collapse") };
  const ro = { get frontier() { return ask.frontier ?? true; }, get collapse() { return ask.collapse ?? true; },
               group: q.get("group") === "kind" ? "kind" : "parent", lanes: q.get("rows") === "lanes", status: q.get("status") || null };
  const viewBar = h("span", { class: "rg-viewbar" });
  // a set of items a side panel links to (item_sets.py): fields matched, and moves in a span; shown as a chip
  // (and the process map's, process.js: through a node, along a line, caused from another kind, by states or events)
  let where = q.getAll("where"), moved = q.get("moved"), movedSince = q.get("moved_since"), movedUntil = q.get("moved_until");
  let pm = { by: q.get("by"), through: q.get("through"), followed: q.get("followed"), caused: q.getAll("caused") };
  const spanned = () => moved || pm.through || pm.followed || pm.caused.length;
  const setParams = () => ({ ...(where.length ? { where } : {}), ...(moved ? { moved } : {}),
                             ...Object.fromEntries(Object.entries(pm).filter(([, v]) => v && v.length)),
                             ...(spanned() && movedSince ? { moved_since: movedSince } : {}), ...(spanned() && movedUntil ? { moved_until: movedUntil } : {}) });
  const dropSet = () => { where = []; moved = movedSince = movedUntil = null; pm = { by: null, through: null, followed: null, caused: [] }; };
  const chip = h("span", { class: "set-chip-place" });
  const compose = messageBox({ hint: "to the work in flight: routed to what it concerns, and delivered to it", done: () => refresh() });
  const rbox = h("div", { class: "item-systems remote-systems" });   // each remote's, asked on its own: never delaying ours
  p.append(notes, h("div", { class: "filters" }, search, viewBar, chip), compose, box, rbox, more);
  let rbusy = false;
  const remoteTick = async (rs) => {
    if (rbusy || SNAP || !rs.length) return;
    rbusy = true;
    try {
      const got = await Promise.all(rs.map(async (r) => [r, await remoteApi("items", { remote: r.name, n: 25 })]));
      if (p.isConnected) patch(rbox, ...got.map(([r, d]) => remoteSection(r, d)));
    } finally { rbusy = false; }
  };
  const group = chartGroup("items"), drawn = {};      // each kind's charts, kept while their data is the same (charts.js)
  let used = new Set();
  const flows = {}, flowsAt = {};                     // each kind's flow over the window, and when it was asked for
  // a chart lives across refreshes: kept while its data is the same (or under the pointer), its data set in
  // place when it can take it (``update``), made again only when it cannot
  const keep = (key, sig, make, update = null) => {
    used.add(key);
    const was = drawn[key];
    if (was && (was.sig === sig || was.el.matches(":hover"))) return live(was.el);
    if (was && update && update(was.el)) { was.sig = sig; return live(was.el); }
    drawn[key] = { sig, el: make() };
    return live(drawn[key].el);
  };
  // one refresh at a time: one asked for while another runs is run once after it (the poll's rule, kept by clicks
  // too); the poll's draws only what changed, a click's always
  let busy = null, again = false, forced = false;
  async function refresh(force = true) {
    forced ||= force;
    if (busy) { again = true; return busy; }
    busy = (async () => { do { again = false; const f = forced; forced = false; await tick(f); } while (again && p.isConnected); })();
    try { await busy; } finally { busy = null; }
  }
  const ans = answers();
  const go = () => { const u = new URLSearchParams(); if (kind) u.set("kind", kind); if (state) u.set("state", state);
                     for (const [k, v] of Object.entries(kind ? setParams() : {})) for (const x of [].concat(v)) u.append(k, x);
                     if (search.value) u.set("q", search.value);
                     if (sort && view === "list") u.set("sort", sort);
                     if (view !== "list") { u.set("view", view); for (const k of ["frontier", "collapse"]) if (ask[k] != null) u.set(k, ask[k] ? "1" : "0");
                                            if (view === "graph" && ro.group === "kind") u.set("group", "kind");
                                            if (ro.status) u.set("status", ro.status);
                                            if (view === "timeline" && ro.lanes) u.set("rows", "lanes"); }
                     replaceRoute("/items" + (u.toString() ? "?" + u : "")); refresh(); };
  search.addEventListener("input", () => go());
  let sysOf = {};                                      // each kind's system, as last listed
  const toggle = (sys) => {                            // a chosen kind's system is open: folding it lets the kind go
    const folded = foldedSystems(), chosen = kind && sysOf[kind] === sys;
    if (folded.has(sys) && !chosen) folded.delete(sys);
    else { folded.add(sys); if (chosen) { kind = state = null; dropSet(); } }
    rememberFolded(folded);
    go();
  };
  async function tick(force = true) {
    if (compose.hidden !== (kind !== MESSAGE_KIND || !!SNAP)) compose.hidden = !compose.hidden;
    ans.begin();
    // the list as the page shows it: the newest of each kind (all a chosen kind's, up to 300), matched to the
    // search where it is kept, each with its kind's columns only, and nothing of a folded system
    // (a snapshot holds the whole list: filtered here)
    const needle = search.value.trim().toLowerCase();
    const folded = foldedSystems();
    let d;
    try {
      d = await ans.api("items", { ...(kind ? { kind, ...setParams() } : {}), ...(state ? { state } : {}),
                                   ...(SNAP ? {} : { per_kind: kind ? 300 : 25, shown: 1, ...(needle ? { q: needle } : {}), ...whatifParams(),
                                                     ...(folded.size && !kind && !needle ? { hide: [...folded].join(",") } : {}) }) });
    } catch (err) {                                     // a filter that is not one: said where the chip goes, the rest as it was
      patch(chip, h("span", { class: "set-chip bad" }, String(err.message || err), " ",
        h("button", { class: "ghost", title: "Remove this filter", "aria-label": "Remove this filter", onclick: () => { kind = state = null; dropSet(); go(); } }, "\u00d7")));
      return;
    }
    remoteTick(d.remotes || []);                        // (not waited on)
    const flowsWere = JSON.stringify(flows);
    sysOf = Object.fromEntries(d.kinds.map((k) => [k.name, k.system]));
    const named = (k) => needle && `${k.name} ${k.title || ""}`.toLowerCase().includes(needle);   // the search names the kind
    const isOpen = (sys) => !folded.has(sys) || (kind && sysOf[kind] === sys) || d.kinds.some((k) => k.system === sys && named(k));
    const systems = d.systems || [{ name: "", kinds: d.kinds.map((k) => k.name) }];
    const kindOf = Object.fromEntries(d.kinds.map((x) => [x.name, x]));
    // each open kind: its states stacked over the window (a cumulative flow diagram), each named with its count,
    // a click on one shows its items; a kind without states, one line of its count. A flow over the window
    // hardly moves in seconds: each asked for every 30s, not on every refresh of the list, and only while shown
    const shownKinds = systems.flatMap((g) => g.kinds.map((n) => kindOf[n]).filter(Boolean));   // folded or not: the charts stay
    const due = shownKinds.filter((k) => k.states.length && !(Date.now() - (flowsAt[k.name] || 0) < 30000));
    await Promise.all(due.map(async (k) => {
      flowsAt[k.name] = Date.now();
      const fl = await api("items-flow", { kind: k.name, points: CHART_POINTS }).catch(() => null);
      flows[k.name] = fl && Object.values(fl.counts).some((c) => c.some((x) => x)) ? fl : null;   // none yet: its counts
    }));
    // how far each block's claims held, under the ergostat.claim table
    const trust = d.items.some((i) => i.kind === CLAIM_KIND) && (!kind || kind === CLAIM_KIND) ? await ans.api("trust").catch(() => null) : null;
    // the Graph's and the Timeline's answers (relations.js), asked on every refresh: a relation can change on an item
    // the list does not show. Of the kinds with relations (or named by one) in each open system; the chosen kind alone
    const relKinds = new Set();
    for (const k of d.kinds) for (const [, ts] of Object.entries(k.relations || {})) { relKinds.add(k.name); ts.forEach((t) => relKinds.add(t)); }
    const relAsked = {};
    if (view !== "list") for (const g of systems) {
      if (!isOpen(g.name) || (d.set && !g.kinds.includes(kind))) continue;
      const want = kind ? (g.kinds.includes(kind) ? [kind] : []) : g.kinds.filter((n) => relKinds.has(n));
      relAsked[g.name] = { want, d: want.length ? await ans.api("items-graph", { kinds: want.join(","), ...whatifParams() }).catch((err) => ({ err })) : null };
    }
    if (!p.isConnected) return;
    if (!force && !ans.changed && JSON.stringify(flows) === flowsWere) return;     // nothing changed: nothing touched
    const seg = (label, items) => h("span", { class: "seg", role: "group", "aria-label": label }, ...items.map(([on, text, title, fn]) =>
      h("button", { class: on ? "on" : "", title, onclick: fn }, text)));
    const check = (on, text, title, fn) => h("label", { class: "rg-check", title }, h("input", { type: "checkbox", ...(on ? { checked: "" } : {}), onchange: fn }), text);
    patch(viewBar, seg("Show", [[view === "list", "List", "Each kind's items, newest first", () => { view = "list"; go(); }],
                                [view === "graph", "Graph", "The items and their relations: what each waits on, the critical path", () => { view = "graph"; go(); }],
                                [view === "timeline", "Timeline", "A Gantt chart: each item's states over time, and what is projected for the unfinished", () => { view = "timeline"; go(); }]]),
      ...(view === "list" ? [] : [
        check(ro.frontier, "Frontier", "Only the unfinished, and what they wait on however far back", (ev) => { ask.frontier = ev.target.checked; go(); }),
        check(ro.collapse, "Collapse done", "Finished items vanish; a chain through them is one dashed line, via N done", (ev) => { ask.collapse = ev.target.checked; go(); }),
        ...(view === "graph" ? [seg("Group", [[ro.group === "parent", "By parent", "A parent (an epic) is a stadium its children hang off", () => { ro.group = "parent"; go(); }],
                                              [ro.group === "kind", "By kind", "Each kind a frame", () => { ro.group = "kind"; go(); }]])]
          : [seg("Rows", [[!ro.lanes, "By item", "A row an item: what happened, and its projected bars", () => { ro.lanes = false; go(); }],
                          [ro.lanes, "Lanes", "A row a lane of each block that takes items: at most its capacity at once, the projected runs in them", () => { ro.lanes = true; go(); }]])])]));
    patch(chip, ...(d.set ? [h("span", { class: "set-chip", title: "The items shown are this set: the address is shareable" },
      d.set.says + setSpan(d.set.params), h("b", { class: "n" }, d.moves != null ? ` ${d.total} item${d.total === 1 ? "" : "s"}, ${d.moves} move${d.moves === 1 ? "" : "s"}` : ` ${d.total}`),
      h("button", { class: "ghost", title: "Remove this filter", "aria-label": "Remove this filter", onclick: () => { kind = state = null; dropSet(); go(); } }, "\u00d7"))] : []));
    used = new Set();
    const pick = (k, st) => { [kind, state] = kind === k.name && state === st ? [null, null] : [k.name, st]; dropSet(); go(); };
    const card = (k) => {
      const name = h("a", { href: "#", class: `kname${kind === k.name && !state ? " on" : ""}`, onclick: (ev) => { ev.preventDefault(); kind = kind === k.name && !state ? null : k.name; state = null; dropSet(); go(); } },
        k.title || k.name, h("span", { class: "mono" }, k.title ? k.name : k.id));
      const fl = flows[k.name];
      if (!fl) return h("div", { class: "kind-flow", key: k.name }, name, h("div", { class: "states" }, (k.states.length ? k.states : [""]).map((st, i) => [i ? h("span", { class: "arrow" }, "→") : null,
        h("a", { href: "#", class: `stbox${k.counts[st] ? " some" : ""}${kind === k.name && state === st ? " on" : ""}`, onclick: (ev) => { ev.preventDefault(); pick(k, st); } },
          h("span", { class: "n" }, String(k.counts[st] || 0)), st || "items")])));
      const chosen = kind === k.name ? state : null;
      return h("div", { class: "kind-flow", key: k.name }, name,
        keep(`cfd:${k.name}`, JSON.stringify([fl.times, fl.counts, chosen]), () => flowChart(fl, group, { chosen, onState: (st) => pick(k, st) }),
             (el) => el.update?.(fl, chosen)));
    };
    patch(notes, ...[
      d.unkinded ? h("p", { class: "note" }, `${d.unkinded} item${d.unkinded > 1 ? "s" : ""} match no kind under items: in ergostat.yaml; shown with their fields, no state.`) : null,
      !d.kinds.length && !d.unkinded ? h("p", { class: "muted" }, "No items yet. An item is what events with an id like ticket/12 are about; see the Guide.") : null].filter(Boolean));
    const rows = SNAP ? d.items.filter((i) => !needle || (i.id + " " + JSON.stringify(i.fields)).toLowerCase().includes(needle)) : d.items;
    const val = (v) => v == null ? "" : typeof v === "object" ? JSON.stringify(v) : String(v);
    const isNum = (its, f) => its.some((i) => typeof i.fields[f] === "number") && its.every((i) => i.fields[f] == null || typeof i.fields[f] === "number");
    const tableOf = (its, show, limit) => {
      const nums = new Set(show.filter((f) => isNum(its, f)));
      const leased = its.some((i) => i.fields.lease && typeof i.fields.lease === "object");   // leases on them (SPEC §9.5)
      const movedCol = its.some((i) => i.moved_at);       // a set of moves: when each moved, in its span
      const etaCol = its.some((i) => i.eta);              // each open item's completion estimate (eta.py): p50, p90 in its title
      show = show.filter((f) => f !== "lease");
      const by = sort.replace(/^-/, ""), down = sort.startsWith("-") ? -1 : 1;
      if (show.includes(by)) {                             // missing last; numbers as numbers, else as text
        const v = (i) => i.fields[by];
        its = [...its].sort((a, b) => (v(a) == null) - (v(b) == null) || (v(a) == null ? 0
          : down * (nums.has(by) ? v(a) - v(b) : String(val(v(a))).localeCompare(String(val(v(b)))))));
      }
      const head = (f) => h("button", { class: "ghost sort", title: `Sort by ${f}`, "aria-sort": by === f ? (down > 0 ? "ascending" : "descending") : "none",
        onclick: () => { sort = by !== f ? f : down > 0 ? `-${f}` : ""; go(); } }, f, by === f ? (down > 0 ? " \u25b4" : " \u25be") : "");
      return table(["item", "state", ...show.map((f) => (nums.has(f) ? [head(f), "num"] : head(f))),
        ...(leased ? ["leased by", ["expires in", "num"], ["attempts", "num"]] : []), ...(movedCol ? [["moved", "num"]] : []), ...(etaCol ? [["done by", "num"]] : []), ["in state", "num"], ["events", "num"], "latest", "last"],
        its.slice(0, limit).map((i) => h("tr", { class: "click", key: i.id, ...rowLink(`/item/${encodeURIComponent(i.id)}`) },
          h("td", { class: "nowrap" }, h("a", { href: `/item/${encodeURIComponent(i.id)}`, class: "plain" }, h("b", {}, i.id))), h("td", { class: "nowrap" }, stateWord(i.state)),
          show.map((f) => h("td", { class: nums.has(f) ? "num" : "cell", title: val(i.fields[f]) }, fieldView(i.fields[f], true, 0, (kindOf[i.kind]?.formats || {})[f]))),
          ...(leased ? leaseCells(i.fields.lease, i.state) : []),
          ...(movedCol ? [h("td", { class: "num nowrap", title: (i.moved_at || []).map(when).join("\n") },
                              (i.moved_at || []).length ? when(i.moved_at[i.moved_at.length - 1]) + (i.moved_at.length > 1 ? ` (${i.moved_at.length}\u00d7)` : "") : "")] : []),
          ...(etaCol ? [etaCell(i.eta)] : []),
          h("td", { class: "num nowrap" }, i.state ? dur(nowS() - i.entered) : ""), h("td", { class: "num" }, String(i.events)),
          h("td", { class: "muted nowrap" }, i.latest), h("td", { class: "muted nowrap" }, ago(i.last)))), "items");
    };
    const tables = async (names) => {                    // one table per kind, each with its own columns
      const parts = [];
      for (const name of names) {
        if (kind && name !== kind) continue;
        const its = rows.filter((i) => (i.kind || "") === name);
        if (!its.length) continue;
        const limit = kind ? 300 : 25, many = d.matched?.[name] ?? its.length;
        const title = kindOf[name]?.title;
        parts.push(h("h3", { class: "kind-head", key: `head:${name}` }, title || name || "No kind",
          title ? h("span", { class: "muted small mono" }, ` ${name}`) : null, h("span", { class: "muted" }, ` ${many}`)));
        parts.push(keyed(tableOf(its, kindOf[name]?.show || [], limit), `table:${name}`));
        if (name === CLAIM_KIND && trust) parts.push(keyed(trustView(trust), "trust"));   // how far each block's claims held
        const fl = flows[name];                            // under its table: how long its finished items took
        if (fl) parts.push(keyed(keep(`cycle:${name}`, JSON.stringify([fl.times[0], fl.finished]), () => cycleChart(fl, group), (el) => el.update?.(fl)), `cycle:${name}`));
        if (many > limit && !d.set?.params?.where && !d.set?.params?.moved)
          parts.push(h("p", { class: "note", key: `all:${name}` }, h("a", { href: "#", onclick: (ev) => { ev.preventDefault(); kind = name; state = null; go(); } }, `All ${many}`)));
      }
      return parts;
    };
    // the Graph and the Timeline (relations.js), from the answers asked for above
    const openItem = (id) => navigate(`/item/${encodeURIComponent(id)}`);
    const relPart = async (g) => {
      const { want, d: rd } = relAsked[g.name] || { want: [] };
      if (!want.length) return kind ? [] : [h("p", { class: "muted", key: `rel-none:${g.name}` }, "No relations among these kinds: a kind declares them under relations: (blocked_by: ticket).")];
      if (!rd || rd.err) return [h("p", { class: "muted", key: `rel-none:${g.name}` }, SNAP ? "The graph and the timeline are not in a snapshot." : String(rd?.err?.message || rd?.err || "not read"))];
      const o = { frontier: ro.frontier, collapse: ro.collapse, group: ro.group, q: needle, status: ro.status };
      const m = rgModel(rd, o);
      const key = `rel:${view}:${g.name}`;
      const draw = (el) => { if (view === "graph") el.draw(m, o); else el.draw(m, rd, ro.lanes); return true; };
      const el = keep(key, JSON.stringify([view, o, rd, ro.lanes]), () => { const e = view === "graph" ? relGraph(openItem) : relTimeline(openItem); draw(e); return e; }, draw);
      return [keyed(relLegend(m, rd, (st) => { ro.status = ro.status === st ? null : st; go(); }, ro.status), `legend:${g.name}`), el];
    };
    const groups = [];
    let anyRows = false;
    for (const g of systems) {
      if (d.set && !g.kinds.includes(kind)) continue;     // a set: the page is about its kind alone, until its chip goes
      const names = [...g.kinds, ...(g.name === "other" && d.unkinded ? [""] : [])];
      const n = g.kinds.reduce((a, k) => a + Object.values(kindOf[k]?.counts || {}).reduce((x, y) => x + y, 0), 0) + (names.includes("") ? d.unkinded : 0);
      const open = isOpen(g.name);
      const head = h("h2", { class: "sys-head" },
        h("button", { class: "ghost disclose", "aria-expanded": String(!!open), title: open ? "Fold away this system's lists of items" : "Show this system's lists of items",
                      onclick: () => toggle(g.name) }, h("span", { class: "tri", "aria-hidden": "true" }, open ? "▾" : "▸"), g.name),
        h("span", { class: "muted" }, ` ${n} item${n === 1 ? "" : "s"}, ${g.kinds.length} kind${g.kinds.length === 1 ? "" : "s"}`),
        g.description ? h("span", { class: "muted sys-desc" }, g.description) : null);
      const charts = h("div", { class: "kind-flows" }, g.kinds.filter((k) => !d.set || k === kind).map((k) => kindOf[k]).filter(Boolean).map(card));
      if (!open) { groups.push(h("section", { class: "sys-group folded", "data-system": g.name, key: g.name }, head, charts)); continue; }   // the charts, not the lists
      const t = view === "list" ? await tables(names) : await relPart(g);
      anyRows ||= t.length > 0;
      groups.push(h("section", { class: "sys-group", "data-system": g.name, key: g.name }, head, charts, ...t));
    }
    if (!p.isConnected) return;
    for (const key of Object.keys(drawn)) if (!used.has(key)) delete drawn[key];   // a folded kind's charts let go
    const listed = d.listed ?? d.items.length;          // what the server's list held, before the search and the cut per kind
    const none = !anyRows && listed && (needle || state || kind) ? h("p", { class: "muted" }, folded.size ? "Nothing matches in the systems shown." : "Nothing matches.") : null;
    patch(box, ...groups, ...(none ? [none] : []));
    sweepPlots();                                         // the charts just replaced (or folded away) let go now, not at the next one drawn
    setText(more, d.total > listed ? `${d.total - listed} older items not loaded.` : "");
  }
  await refresh();
  S.timer = poll(() => refresh(false), 4000, p);
}

/* an item's completion estimate (SPEC §5a, Completion estimates): when, by the p50; the p90 and why on hover */
const etaWhen = (t) => (t == null ? "beyond the horizon" : new Date(t * 1000).toLocaleString([], { hour12: false, month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }));
/* a p90 after its p50: the time alone on the same day, else with its date; not said under twenty runs */
const etaP90 = (e) => (e.p90 == null && e.runs != null && e.runs < 20 ? `p90 not worked out (${e.runs} runs)`
  : e.p90 == null || e.p50 == null || new Date(e.p90 * 1000).toDateString() !== new Date(e.p50 * 1000).toDateString() ? `p90 ${etaWhen(e.p90)}`
  : `p90 ${new Date(e.p90 * 1000).toLocaleTimeString([], { hour12: false, hour: "2-digit", minute: "2-digit" })}`);
const ordinal = (n) => n + (n % 100 > 10 && n % 100 < 14 ? "th" : ["th", "st", "nd", "rd"][n % 10] || "th");
function etaCell(e) {
  if (!e) return h("td", {}, "");
  return h("td", { class: "num nowrap", "data-eta": "", title: `p50 ${etaWhen(e.p50)}, ${etaP90(e)}${e.why ? "\n" + e.why : ""}` },
    e.p50 == null ? h("span", { class: "muted" }, "beyond the horizon") : etaWhen(e.p50), h("span", { class: "muted small" }, ` ${etaP90(e)}`));
}

/* an item's lease (SPEC §9.5): who holds it and until when, its attempts; a dead letter said as one */
function leaseCells(l, state) {
  if (!l || typeof l !== "object") return [h("td", {}, ""), h("td", {}, ""), h("td", {}, "")];
  const left = l.holder ? l.expires - nowS() : null;
  return [h("td", { class: "nowrap", "data-lease": l.holder ? "held" : state === "dead" ? "dead" : "free" },
            l.holder ? h("span", { title: `run ${l.holder}, lease ${l.fence}` }, `${l.block} `, h("span", { class: "muted" }, l.holder.slice(0, 8)),
                         l.taken ? h("span", { class: "muted", title: "held for" }, `, ${dur(nowS() - l.taken)}`) : null)
              : state === "dead" ? h("b", { class: "bad" }, "dead letter") : h("span", { class: "muted" }, "–")),
          h("td", { class: "num nowrap" + (left != null && left < 0 ? " bad" : "") }, left == null ? "" : left < 0 ? `overdue ${dur(-left)}` : dur(left)),
          h("td", { class: "num" }, `${l.attempts || 0}/${l.max ?? "?"}`)];
}
function leaseView(l, state) {
  const left = l.holder ? l.expires - nowS() : null;
  const says = l.holder ? [h("b", {}, `held by ${l.block}`), ` (run ${l.holder.slice(0, 8)}, lease ${l.fence}, ${l.tier}), `,
      left < 0 ? h("b", { class: "bad" }, `overdue ${dur(-left)}`) : `expires in ${dur(left)}`, `; renewed ${ago(l.renewed)} (TTL ${dur(l.ttl)})`]
    : state === "dead" ? [h("b", { class: "bad" }, "A dead letter"), `: given up on after ${l.attempts} attempts. `,
        h("code", {}, "ergostat lease ITEM --redrive"), " gives it another go."]
    : ["Not held", l.not_before && l.not_before > nowS() ? `; not taken again for ${dur(l.not_before - nowS())}` : ""];
  const rows = (l.history || []).slice().reverse().map((x) => h("tr", { key: `${x.fence}|${x.run || ""}` }, h("td", { class: "num" }, String(x.fence)), h("td", {}, x.block || ""),
    h("td", { class: "mono small" }, (x.run || "").slice(0, 8)), h("td", { class: "nowrap" }, when(x.taken)),
    h("td", { class: x.how === "ack" ? "" : "bad" }, x.how || "holding"), h("td", { class: "num nowrap" }, dur((x.ended || nowS()) - x.taken)),
    h("td", { class: "num" }, x.exit == null ? "" : String(x.exit)), h("td", {}, (x.why || "") + (x.silent ? ` (silent ${dur(x.silent)})` : "") + (x.counted === false ? " (not counted)" : ""))));
  return h("div", { class: "lease" }, h("p", {}, ...says, ` Attempts ${l.attempts || 0} of ${l.max ?? "?"}.`),
    rows.length ? table(["lease", "block", "run", "taken", "how", ["for", "num"], ["exit", "num"], "why"], rows, "leases") : null);
}

/* a field's history: each change, oldest first, with the event that made it (a click opens it) */
const when = (t) => new Date(t * 1000).toLocaleString([], { hour12: false });
function eventLink(eid, type, d) {
  return h("a", { href: "#", class: "plain", title: `event ${eid}`, onclick: async (ev) => {
    ev.preventDefault();
    const e = (d.record || []).find((x) => x.id === eid) || await api(`events/${encodeURIComponent(eid)}`).catch(() => null);
    if (e) showEvent(e);
  } }, type);
}
function recordLinkItem(id) {
  return h("a", { href: `/record?item=${encodeURIComponent(id)}` }, "all of them in the Record");
}
function historyView(cs, total, d) {
  if (!total) return null;
  const how = (c) => c.op === "rolled up" ? `${c.count} change${c.count > 1 ? "s" : ""} from ${when(c.first.time)}, rolled up`
    : c.op === "refused" ? "refused" : c.op + (c.rule && c.rule !== "replace" ? ` (${c.rule})` : "") + (c.form !== "data" ? ` by ${c.form}` : "");
  const val = (v) => (v == null ? h("span", { class: "muted" }, "–") : fieldView(v, true));
  const rows = cs.slice().reverse().map((c, i) => h("tr", { key: c.event ? `${c.event}|${c.path || "/"}|${c.op}` : `${c.time}|${i}` }, h("td", { class: "nowrap" }, when(c.time)), h("td", { class: "nowrap" }, how(c)),
    h("td", { class: "mono small" }, c.path || "/"), h("td", { class: "cell" }, c.op === "refused" ? c.why : val(c.before)),
    h("td", { class: "cell" }, c.op === "refused" ? "" : val(c.after)), h("td", { class: "nowrap" }, eventLink(c.event, c.type, d))));
  return h("details", { class: "history" }, h("summary", {}, `history (${total} change${total > 1 ? "s" : ""})`),
    total > cs.length ? h("p", { class: "note" }, `The latest ${cs.length} of ${total}; `, h("code", {}, `ergostat item ${d.id} --history`), " lists all.") : null,
    table(["when", "change", "path", "before", "after", "by event"], rows, "history"));
}

/* an item's relations both ways (SPEC §5a, Relations): what it names, and what names it (the inverse, derived),
   each related item with its state; what it waits on said first */
function relationsView(r, k) {
  if (!r) return [];
  const item = (i) => { const x = r.items?.[i]; return h("span", { class: "rel-item", key: i }, h("a", { href: `/item/${encodeURIComponent(i)}` }, i),
    x ? h("span", { class: "muted" }, ` ${x.done ? "✓ " : ""}${x.state || ""}${x.title ? " · " + x.title : ""}`) : h("span", { class: "muted" }, " not recorded")); };
  const rows = [...Object.entries(r.out).map(([n, ids]) => [n, ids, r.relations?.[n]]), ...Object.entries(r.in).map(([n, ids]) => [n, ids, null])];
  const graph = k ? h("a", { href: `/items?kind=${encodeURIComponent(k.name)}&view=graph` }, "the graph") : null;
  return [h("h2", {}, "Relations"),
    r.waiting?.length ? h("p", { class: "note" }, h("b", {}, "Waiting on "), `${r.waiting.join(", ")}: not finished yet.`)
      : r.relations && Object.values(r.relations).some((x) => x.precedence) ? h("p", { class: "note" }, "Nothing it waits on is unfinished.") : null,
    h("div", { class: "table-wrap" }, h("table", { class: "fields relations" }, rows.map(([n, ids, rel]) => h("tr", { key: n },
      h("th", {}, n.replace(/_/g, " "), h("span", { class: "muted small rule" }, rel ? (rel.precedence ? " precedence" : rel.group ? " parent" : "") : " derived")),
      h("td", {}, ids.map((i, j) => [j ? h("br") : null, item(i)])))))),
    graph ? h("p", { class: "note" }, "All of them in ", graph, ".") : null];
}

/* a remote's item, read there (SPEC §4c): its fields, its moves and its events, read only: no message box, no actions */
async function pageRemoteItem(main, id, name) {
  const p = page(main, id);
  p.querySelector("h1").append(h("span", { class: "muted remote-mark" }, ` remote ${name}`));
  const body = h("div");
  p.append(body);
  async function tick() {
    const d = await remoteApi(`items/${encodeURIComponent(id)}`, { remote: name });
    if (!p.isConnected) return;
    if (d.failed) { patch(body, d.code === 404 ? h("p", { class: "muted" }, d.why) : remoteSaid(name, d)); return; }
    const it = d.item, f = it.fields || {};
    const pair = (label, value) => h("span", {}, h("span", {}, label), value);
    const evs = (it.record || []).map((e) => ({ ...e, remote: name }));
    patch(body, remoteSaid(name, d), h("div", { class: "meta" }, pair("Remote", name), pair("Kind", it.kind_of?.name || it.kind || "–"),
      pair("State", stateWord(it.state)), pair("Events", String(it.events ?? evs.length))),
      h("h2", {}, "Fields"), Object.keys(f).length ? h("div", { class: "table-wrap" }, h("table", { class: "fields" }, Object.keys(f).sort().map((k) =>
        h("tr", { key: k }, h("th", {}, k), h("td", {}, fieldView(f[k], false, 0, null, name)))))) : h("p", { class: "muted" }, "No fields."),
      h("h2", {}, "How it moved"), (it.moves || []).length ? table(["when", "from", "to", "by event"], it.moves.map((m) => h("tr", { key: `${m.time}|${m.to}` },
        h("td", { class: "nowrap" }, when(m.time)), h("td", {}, m.from || "arrived"), h("td", {}, m.to), h("td", { class: "muted" }, m.type)))) : h("p", { class: "muted" }, "No moves."),
      h("h2", {}, "Events"), eventsTable(evs, true));
  }
  await tick();
  S.timer = poll(() => tick(), 4000, p);
}

async function pageItem(main, id, q) {
  if (q?.get("remote")) return pageRemoteItem(main, id, q.get("remote"));
  const p = page(main, id);
  const body = h("div");
  p.append(body);
  const note = messageBox({ about: id, title: "Send a note about this", done: () => tick() });   // lives across refreshes: what is typed stays
  let full = null;                                   // its full history, once asked for: kept across refreshes
  let impact = null;                                 // a failure's or a change's impact (review.js): worked out once
  const ans = answers();
  // a refresh asks for its answers first; if none changed (each a 304), nothing on the page is touched (its files
  // are still asked for: a transcript may grow before its events are recorded); else only what differs is
  async function tick(force = true) {
    ans.begin();
    let d;
    try { d = await ans.api(`items/${encodeURIComponent(id)}`, whatifParams()); } catch (e) { d = null; }
    if (!d) { patch(body, h("p", { class: "muted" }, "Nothing is recorded about this id.")); return; }
    const k = d.kind_of;
    const ms = !k?.name?.startsWith("ergostat.") ? await ans.api("messages", { item: id }).catch(() => null) : null;
    const as = !k?.name?.startsWith("ergostat.") || k?.name === "ergostat.workspace" || /^session\//.test(id)
      ? await ans.api("actions", { item: id }).catch(() => null) : null;
    if (!p.isConnected) return;
    if (!force && !ans.changed) { refreshFiles(); return; }
    const pair = (label, value) => h("span", {}, h("span", {}, label), value);
    const head = h("div", { class: "meta" },
      pair("Kind", k ? h("a", { href: `/items?kind=${encodeURIComponent(k.name)}` }, k.name) : h("span", { class: "muted" }, "none (nothing under items: matches this id)")),
      d.state ? pair("State", h("span", {}, h("b", {}, d.state), ` for ${dur(nowS() - d.entered)}`)) : null,
      d.eta ? pair("Expected done", h("span", { "data-eta": "" }, h("b", {}, etaWhen(d.eta.p50)), h("span", { class: "muted" }, ` (${etaP90(d.eta)}`
        + (d.eta.start != null && d.eta.start > nowS() + 60 ? `; started about ${etaWhen(d.eta.start)}` : "")
        + (d.eta.dead ? `; a dead letter in ${Math.round(d.eta.dead * 100)}% of runs` : "") + ")"))) : null,
      pair("Events", String(d.events)), pair("First", ago(d.first)), pair("Latest", h("span", {}, d.latest, h("span", { class: "muted" }, `, ${ago(d.last)}`))));
    // the path it took, arrow by arrow, to where it is now; the other states apart, with no arrow (its endings double-bordered)
    const fin = new Set(k?.final || []), box = (st) => h("span", { class: `stbox${st === d.state ? " on" : ""}${fin.has(st) ? " final" : ""}` }, st);
    const path = d.moves.map((m) => m.to).filter((s, i, a) => s && s !== a[i - 1]);
    if (d.state && path[path.length - 1] !== d.state) path.push(d.state);
    const ended = fin.has(d.state), rest = (k?.states || []).filter((s) => !path.includes(s) && (!ended || fin.has(s)));
    const track = k && k.states.length ? h("div", { class: "track" }, path.map((st, i) => [i ? h("span", { class: "arrow" }, "→") : null, box(st)]),
      rest.length ? h("span", { class: "alt" }, ended ? "could also have ended:" : "its other states:", rest.map(box)) : null) : null;
    const moves = d.moves.length ? table(["when", "from", "to", "by event", ["after", "num"]],
      d.moves.map((m, i) => h("tr", { key: `${m.time}|${m.to}` }, h("td", { class: "nowrap" }, new Date(m.time * 1000).toLocaleString([], { hour12: false })), h("td", { class: m.from ? "" : "muted" }, m.from || "arrived"), h("td", {}, m.to),
        h("td", { class: "muted" }, m.type), h("td", { class: "num muted" }, i ? dur(m.time - d.moves[i - 1].time) : "")))) : h("p", { class: "muted" }, "Its kind has no states.");
    // its kind's chosen fields first, in their order, then the rest by name
    const first = (k?.show || []).filter((f) => f in d.fields);
    const hist = d.history || {}, gone = Object.keys(hist).filter((f) => f && !(f in d.fields));   // removed since: still have a history
    const order = [...first, ...Object.keys(d.fields).filter((f) => !first.includes(f)).sort(), ...gone.sort()].filter((f) => f !== "lease");
    const lease = d.fields.lease && typeof d.fields.lease === "object" ? [h("h2", {}, "Lease"), leaseView(d.fields.lease, d.state)] : [];
    const fields = order.length ? h("div", { class: "table-wrap" }, h("table", { class: "fields" }, order.map((f) => h("tr", { "data-field": f, key: f },
      h("th", {}, f, k?.fold?.[f] ? h("span", { class: "muted small rule", title: "how its events' data folds into it" }, ` ${k.fold[f]}`) : null),
      h("td", {}, f in d.fields ? fieldView(d.fields[f], false, 0, (k?.formats || {})[f]) : h("span", { class: "muted" }, "removed"),
        historyView(hist[f] || [], (d.changes || {})[f] || 0, d))))))
      : h("p", { class: "muted" }, "No fields: its events carry no data.");
    const refused = (d.refused || []).length ? [h("h2", {}, "Refused"), h("p", { class: "note" }, "Events recorded that changed nothing: their changeset could not apply, so none of it did."),
      table(["when", "event", "as", "why"], d.refused.slice().reverse().map((r) => h("tr", { key: r.event }, h("td", { class: "nowrap" }, when(r.time)),
        h("td", { class: "nowrap" }, eventLink(r.event, r.type, d)), h("td", { class: "muted" }, r.form), h("td", {}, r.why))), "refused")] : [];
    const said = d.transcript_events ? h("p", { class: "note" }, `${d.transcript_events} more events are its transcript's lines (claude.*), folded into its fields above; `,
      recordLinkItem(id), ".") : null;
    // the parts the owner answers in (their buttons, reasons being typed): kept whole while what they show is the same
    const whole = (el, ...from) => { el.__sig = JSON.stringify(from); return el; };
    const verdict = k?.name === CLAIM_KIND ? [h("h2", {}, "Verdict"), claimView(d)]
      : k?.name === DECISION_KIND || k?.name === CORRECTION_KIND ? [h("h2", {}, k.name === DECISION_KIND ? "The decision" : "The correction"), whole(intentView(d, tick), d.state, d.fields)]
      : k?.name === MESSAGE_KIND ? [h("h2", {}, "Message"), whole(messageView(d, tick), d.state, d.fields)]
      : k?.name === ACTION_KIND ? [h("h2", {}, "Gated action"), whole(actionView(d, tick), d.state, d.fields)]
      : k?.name === REPORT_KIND ? [h("h2", {}, "Report upstream"), whole(reportView(d, tick), d.state, d.fields)] : [];
    let about = [];
    if (ms) about = [h("h2", {}, "Messages", h("span", { class: "muted" }, ` ${ms.messages.length}`)), messagesAbout(ms.messages), SNAP ? "" : live(note)];
    if (as && as.actions.length) {                      // the gated actions asked for about it
      const held = as.actions.filter((a) => a.state === "requested").length;
      about = [h("h2", {}, "Gated actions", h("span", { class: held ? "s-open" : "muted" }, held ? ` ${held} waiting for approval` : ` ${as.actions.length}`)),
               whole(actionsAbout(as.actions, tick), as.actions), ...about];
    }
    // its oldest events rolled up into a snapshot (SPEC §4b): the originals are in the archive, read when asked for
    const ro = d.rollup;
    const rolled = ro ? h("p", { class: "note" }, `Its ${ro.archived.events} oldest events, up to ${when(ro.last)}, are rolled up into one snapshot and archived. `,
      full ? null : h("button", { class: "ghost", onclick: async () => { full = await api(`items/${encodeURIComponent(id)}`, { archived: 1, n: 1000 }); tick(); } }, "Show the full history"),
      full && full.total > full.events.length ? h("span", { class: "muted" }, ` (the first ${full.events.length} of ${full.total})`) : null) : null;
    if (!impact && (/^ergostat\.failure\//.test(id) || k?.name === "ergostat.model-change")) impact = impactBox(id);
    const imp = impact ? [h("h2", {}, "Impact"), live(impact)] : [];
    const why = d.eta?.why ? h("p", { class: "note eta-why" }, h("b", {}, d.eta.waits_in ? `Waiting in ${d.eta.waits_in}` + (d.eta.position ? `, ${ordinal(d.eta.position)} in its queue` : "") + ": " : ""),
      d.eta.why, h("span", { class: "muted" }, ` (estimated from the record: ${d.eta.runs} runs of a simulation of every open item, which leaves out a goal that switches a block off and a capacity no block declares; `, h("a", { href: `/items?kind=${encodeURIComponent(k?.name || "")}&view=timeline` }, "the timeline"), ")")) : null;
    patch(body, head, track, why, ...lease, ...relationsView(d.relations, d.kind_of), ...verdict, ...imp, ...about, h("h2", {}, "Fields"), fields, ...refused, h("h2", {}, "How it moved"), moves,
      h("h2", {}, "Events", h("span", { class: "muted" }, ` ${d.events}`)), said, rolled,
      eventsTable(full ? full.events : d.record, true));
  }
  await tick();
  // not while the owner is answering (a reason being typed in a decision's or an action's row)
  S.timer = poll(() => (body.querySelector(".intent-act:not([hidden])") || document.activeElement?.closest?.(".action-act") ? null : tick(false)), 4000, p);
}

/* Model: first what is available for this project (each loop, each parameter to estimate, and where each
   model tool lives: a link chooses the part and opens its view and panel); then the review queue; then the
   fit: how well the model follows the record, on the reference window (the last day at most, whatever
   the window above): the stocks its equations move (the model's fit, and the total), each equation
   with its inputs as measured and replayed, the stocks moved only by measured flows (accounting), with
   Theil's breakdown of each error and what it says; the history across versions; the proposals
   waiting, and why the estimates not proposed were not; and the residuals */
const two = (x) => (x == null ? "" : x.toFixed(2));
const pct = (x) => (x == null ? "" : `${Math.round(x * 100)}%`);
/* MAPE where it means something; else the mean absolute error as a share of the readings' mean or range */
const errorText = (s) => (s.mape != null ? pct(s.mape) : s.error_share != null ? `${pct(s.error_share)} of ${s.error_of}` : "");
function fitRows(rows, total) {
  const cells = (s) => [h("td", { class: "num" }, s.n ?? ""), h("td", { class: "num" }, two(s.r2)), h("td", { class: "num nowrap" }, errorText(s)),
                        h("td", { class: "num" }, two(s.um)), h("td", { class: "num" }, two(s.us)), h("td", { class: "num" }, two(s.uc)),
                        h("td", { class: "small" }, s.says || "")];
  const out = rows.map((s) => h("tr", {}, h("td", {}, h("b", {}, s.name), s.unit ? h("span", { class: "muted" }, ` ${s.unit}`) : null),
    ...(s.n == null ? [h("td", { class: "muted", colspan: 7 }, "too few points to say")]
      : s.too_little ? [h("td", { class: "num" }, s.n), h("td", { class: "muted small", colspan: 6 }, `too little record: ${s.too_little}`)]
      : s.exact ? [h("td", { class: "num" }, s.n), h("td", { class: "muted", colspan: 6 }, "no error: the replay is the record")] : cells(s))));
  // the total is judged on its payoff (each stock's squared error over its own size, averaged), R² and MAPE per stock
  if (total) out.push(h("tr", { class: "total" }, h("td", {}, h("b", {}, "total")), h("td", { class: "num" }, total.n ?? ""), h("td", {}, ""), h("td", {}, ""),
    h("td", { class: "num" }, two(total.um)), h("td", { class: "num" }, two(total.us)), h("td", { class: "num" }, two(total.uc)),
    h("td", { class: "small", title: "each stock's mean squared error over its own size (mean square measured), averaged: what a calibration minimises" },
      total.nmse != null ? `scaled error ${fmt(total.nmse)}` : "")));
  return out;
}
function fitHead(words, first) {
  return [first, ...["n", "R\u00b2", "MAPE", "U_M", "U_S", "U_C"].map((label) => [rich(label), "num"]), ""];
}
async function pageModel(main) {
  const p = page(main, "Model");
  const availBox = h("div", { class: "available" });
  p.append(h("h2", {}, "What's available"), availBox);
  const fitBox = h("div"), eqBox = h("div"), accBox = h("div"), notes = h("div"), histBox = h("div"), resBox = h("div"), cap = h("p", { class: "note" });
  const qHead = h("h2", { id: "review-queue" }, "Changes to review"), qActions = h("div", { class: "actions" }), allBox = h("div", { class: "review-all" });
  const queueBox = h("div", { class: "review" }), whyBox = h("div"), canBox = h("div");
  p.append(qHead, qActions, allBox, queueBox, whyBox, h("h2", {}, "What ergostat can propose"), canBox,
           h("h2", { id: "model-fit" }, "How well the model fits"), fitBox, eqBox, accBox, notes, h("h2", {}, "History"), histBox, h("h2", {}, "Residuals"), resBox, cap);
  let propSig = null, busy = false, chosen = "parts";
  async function estimateNow(btn, said, which = "parts") {
    btn.disabled = true; busy = true; said.textContent = which === "parts" ? "Estimating\u2026" : "Calibrating\u2026";
    try { await apiPost("estimate", { calibrate: which }); said.textContent = ""; propSig = null; }
    catch (e) { said.textContent = String(e.message || e); }
    busy = false; btn.disabled = false; tick();
  }
  const answering = () => busy || queueBox.querySelector("button:disabled, .confirm:not([hidden])") ||
    (queueBox.contains(document.activeElement) && document.activeElement.tagName === "INPUT");
  const ans = answers();
  async function tick(force = true) {
    let d;
    ans.begin();
    try { d = await ans.api("fit"); } catch (e) { d = null; }
    if (!d) { patch(fitBox, h("p", { class: "muted" }, "The model is an ergostat.toml: equations and their fit come with ergostat.yaml.")); return; }
    if (!force && !ans.changed) return;                  // nothing changed: nothing touched
    availableView(d, availBox);
    const span = d.until && d.since ? dur(d.until - d.since) : "";
    patch(fitBox, 
      ...(d.modelling?.says ? [h("p", { class: "muted" }, h("b", {}, "Modelling: "), d.modelling.says)] : []),
      ...(d.invalid?.length ? [h("p", { class: "s-off" }, `The replay is not valid: ${d.invalid.join("; ")}.`)] : []),
      h("h3", {}, "Model fit", h("span", { class: "muted" }, ` the stocks an equation moves, over the last ${span} of record`)),
      d.stocks.length ? table(fitHead(d.words, "stock"), fitRows(d.stocks, d.total), "fit")
        : h("p", { class: "muted" }, "No stock is moved by an equation: nothing here tests the model's equations yet."));
    const judged = Object.entries(d.judged_by_stock || {});
    patch(eqBox, ...(d.partial.length || d.equations.length || judged.length ? [
      h("h3", {}, "Equations, inputs as measured", h("span", { class: "muted" }, " the partial-model test")),
      d.partial.length ? table(fitHead(d.words, "worked out"), fitRows(d.partial, null), "fit") : h("p", { class: "muted" }, "No equation's part is measured."),
      ...(d.equations.length ? [h("h3", {}, "Equations, replayed", h("span", { class: "muted" }, " every stock integrated")),
        table(fitHead(d.words, "worked out"), fitRows(d.equations, null), "fit")] : []),
      ...judged.map(([r, st]) => h("p", { class: "muted small" }, `${r.split(".").slice(1).join(".")} is measured from its stock's changes: judged by ${st ? st.split(".").slice(1).join(".") : "its stock"}'s replay, above.`)),
    ] : []));
    patch(accBox, ...(d.accounting.length ? [h("h3", {}, "Accounting", h("span", { class: "muted" }, " stocks moved only by measured flows")),
      table(fitHead(d.words, "stock"), fitRows(d.accounting, null), "fit")] : []));
    patch(notes, ...d.notes.map((n) => h("p", { class: "muted small" }, n)));
    const why = Object.entries(d.not_proposed || {});
    const q = d.queue || [];
    const sig = JSON.stringify(q.map((x) => [x.id, x.diff?.hash, x.conflicts.length, x.state])) + (d.estimated_at || "") + JSON.stringify(why) + d.loops_analysed +
      JSON.stringify([d.redesigns?.asked, d.redesigns?.last?.id, d.redesigns?.last?.result]);
    if (sig !== propSig && !answering()) {
      propSig = sig;
      const said = h("span", { class: "muted small" });
      // calibration: each part alone (and equations for flows with none), each system alone driven by its
      // measured inputs, or the whole model's replay; each a set of proposals with the fit before and after
      const ways = (d.calibrations || []).filter((c) => c.key === "parts" || c.count);
      const pick = ways.length > 1 ? h("select", { "aria-label": "what to fit at once", onchange: (ev) => { chosen = ev.target.value; } },
        ways.map((c) => h("option", { value: c.key, selected: c.key === chosen ? "selected" : null },
          c.key === "whole" && d.open_loops?.length ? `${c.words} (${d.open_loops.length} loop${d.open_loops.length > 1 ? "s" : ""} left open)` : c.words))) : null;
      const btn = h("button", { class: "ghost", onclick: () => estimateNow(btn, said, pick ? pick.value : "parts") }, d.to_estimate.length ? "Calibrate" : "Estimate now");
      const sims = q.filter((x) => x.simulable).map((x) => x.id);
      const all = h("button", { onclick: () => simulateAll(sims, allBox, all), disabled: sims.length < 1 ? "" : null }, "Simulate all pending");
      const kinds = {};
      for (const x of q) kinds[x.what] = (kinds[x.what] || 0) + 1;
      qHead.replaceChildren("Changes to review", h("span", { class: "muted" }, q.length ? ` ${q.length} waiting` : ""));
      qActions.replaceChildren(...[SNAP ? null : all, SNAP ? null : btn, SNAP ? null : pick,
        h("span", { class: "muted small" }, d.to_estimate.length
          ? `${d.to_estimate.length} parameter${d.to_estimate.length > 1 ? "s" : ""} to estimate${d.estimated_at ? `, last calibrated ${ago(d.estimated_at)}` : ", not calibrated yet"}`
          : "no parameter is marked estimate: true"),
        d.loops_analysed < d.loops ? h("span", { class: "muted small" }, `loops analysed for proposals: ${d.loops_analysed} of ${d.loops}`) : null,
        said, redesignAsk(d.redesigns, () => { propSig = null; setTimeout(tick, 600); })].filter(Boolean));
      queueBox.replaceChildren(...(q.length ? q.map((x) => reviewEntry(x, { onDone: () => { propSig = null; allBox.replaceChildren(); setTimeout(tick, 600); } }))
        : [h("p", { class: "muted" }, "Nothing waiting.")]));
      whyBox.replaceChildren(...(why.length ? [h("h3", {}, "Estimates not proposed"),
        table(["parameter", "why"], why.map(([n, w]) => h("tr", {}, h("td", {}, h("b", {}, n)), h("td", { class: "small" }, w))), "can")] : []),
        ...(d.open_loops?.length ? [h("p", { class: "muted small" }, `Every stock integrated still leaves open ${d.open_said}, since the replay takes what a decision sets as measured.`)] : []));
      canBox.replaceChildren(proposableView(d));
    }
    const events = [...d.history.map((v) => ({ t: v.first, v })), ...d.accepted.map((a) => ({ t: a.time, a }))].sort((x, y) => y.t - x.t);
    patch(histBox, events.length ? table(["when", "version", ["scaled error", "num"], ["over", "num"], ""], events.slice(0, 30).map(({ v, a }) => (v
      ? h("tr", {}, h("td", { class: "nowrap" }, ago(v.first)), h("td", { class: "mono" }, v.version, v.version === d.version ? h("span", { class: "muted" }, " now") : null),
          h("td", { class: "num" }, v.total?.nmse != null ? fmt(v.total.nmse) : ""), h("td", { class: "num nowrap" }, v.window ? dur(v.window) : ""),
          h("td", { class: "muted small" }, `fitted ${v.fits} time${v.fits > 1 ? "s" : ""}, last ${ago(v.last)}`))
      : h("tr", {}, h("td", { class: "nowrap" }, ago(a.time)), h("td", { class: "mono muted" }, `${a.version_before} \u2192 ${a.version_after}`),
          h("td", { class: "num nowrap" }, `${a.fit_before?.nmse != null ? fmt(a.fit_before.nmse) : "\u2013"} \u2192 ${a.fit_after?.nmse != null ? fmt(a.fit_after.nmse) : "\u2013"}`),
          h("td", {}, ""), h("td", {}, "accepted: ", op(a.title))))), "fit")
      : h("p", { class: "muted" }, "Not fitted before."));
    const r = d.residuals || {};
    const rows = Object.entries(r).sort((a, b) => (b[1].significant ? 1 : 0) - (a[1].significant ? 1 : 0));
    patch(resBox, Object.keys(r).length ? table(["stock", ["changed", "num"], ["explained", "num"], ["unexplained", "num"], ""],
      rows.map(([k, v]) => h("tr", {}, h("td", {}, h("b", {}, k)), h("td", { class: "num" }, fmt(v.change)), h("td", { class: "num" }, fmt(v.explained)),
        h("td", { class: "num" }, fmt(v.unexplained)),
        h("td", {}, v.significant ? h("span", { class: "s-open" }, "unexplained") : (v.absorbed_by.length ? h("span", { class: "muted" }, `estimated as ${v.absorbed_by.join(", ")}`) : "")))), "fit")
      : h("p", { class: "muted" }, "No stock has two readings in this window yet."));
    patch(cap, rich(`Version ${d.version}, fitted over the last ${span} of record (at most a day, whatever the window above). ` +
      "The model is read the way the record was made: a level at its reading's moment, a counted flow by what it moved in each bucket, a rate a sensor averages by the model's own average. " +
      `Each series needs ${d.min_points} points over three of its slowest time constant to be judged. ` +
      `The total: ${d.words.nmse}. R\u00b2: ${d.words.r2}. MAPE: ${d.words.mape}. Theil's U_M: ${d.words.um}; U_S: ${d.words.us}; U_C: ${d.words.uc}; the three sum to 1. ` +
      `Accounting: ${d.words.accounting}. ` +
      "Residuals: what each stock did against what its known flows explain; a disturbance nothing measures is estimated from the rest."));
  }
  await tick();
  S.timer = poll(() => tick(false), 5000, p);
}

async function pageCheck(main) {
  const st = await api("status");
  let quiet = [];                                          // the parts the record has not exercised (a finding each)
  try { quiet = await api("exercised"); } catch (e) { quiet = []; }
  st.check = [...st.check, ...quiet.map((x) => ({ level: "warn", message: x.message }))];
  const info = st.check.filter((c) => c.level === "info");  // the extreme-conditions tests, while they run in the background
  st.check = st.check.filter((c) => c.level !== "info");
  const errors = st.check.filter((c) => c.level === "error").length, warnings = st.check.length - errors;
  const words = [errors ? `${errors} error${errors > 1 ? "s" : ""}` : "", warnings ? `${warnings} warning${warnings > 1 ? "s" : ""}` : ""].filter(Boolean);
  const p = page(main, words.length ? `Check: ${words.join(", ")}` : "The model is whole");
  if (st.check.length) p.append(h("div", { class: "att" }, st.check.map((c) => h("div", {},
    h("b", { class: c.level === "error" ? "lvl-error" : "lvl-warning" }, c.level === "error" ? "Error" : "Warning"), " ", op(c.message)))));
  if (info.length) p.append(h("p", { class: "muted small extremes-status" }, info.map((c) => c.message).join("; ")));
  if (info.some((c) => c.message.startsWith("extremes: running")))   // drawn again once they are done
    S.timer = poll(async () => { const s2 = await api("status"); if (!s2.check.some((c) => c.level === "info" && c.message.startsWith("extremes: running"))) { S.timer.stop(); pageCheck(main); } }, 2000, p);
  const slot = h("div");                                   // the three views held against each other (SPEC §12l), when read
  p.append(slot, h("h2", {}, "Counts"), h("dl", { class: "counts" }, Object.entries(st.counts).flatMap(([k, v]) => [h("dt", {}, k), h("dd", {}, fmt(v))])));
  let coh = null;
  try { coh = await api("coherence"); } catch (e) { coh = null; }
  if (coh && Object.keys(coh.kinds || {}).length) slot.append(coherenceSection(coh));
}

/* Coherence: each kind's score (agreements of comparisons, or the record it still needs), then each mismatch grouped
   by the pair of views that disagrees, with its file and line, its fix and the check findings it is linked to */
function coherenceSection(coh) {
  const box = h("section", { class: "coherence" }, h("h2", {}, "Coherence",
    h("span", { class: "muted" }, " the Process, Dynamics and Blocks views held against each other, over the record")));
  box.append(h("ul", { class: "coh-scores" }, Object.entries(coh.kinds).map(([k, x]) => {
    const all = x.compared && x.agree === x.compared;
    const cls = x.compared ? (all ? "s-holding" : "s-open") : "muted";
    return h("li", {}, h("b", {}, k), " ", x.compared ? h("span", { class: cls }, `${x.agree} of ${x.compared} agree`) : "",
      x.needs ? h("span", { class: "muted" }, `${x.compared ? "; the record not compared yet: " : ""}needs ${x.needs}`) : "");
  })));
  const finds = coh.findings || [];
  for (const [pair, title] of Object.entries(coh.pairs || {})) {
    const mine = finds.filter((f) => f.pair === pair);
    if (!mine.length) continue;
    const bad = mine.filter((f) => f.level === "mismatch").length;
    box.append(h("h3", {}, title, h("span", { class: "muted" }, bad ? ` ${bad} mismatch${bad > 1 ? "es" : ""}` : " notes only")),
      h("div", { class: "att" }, mine.map((f) => h("div", { class: f.level === "note" ? "muted" : "" },
        h("b", { class: f.level === "note" ? "" : "lvl-warning" }, f.code), " ",
        f.file ? h("span", { class: "muted" }, `${f.file.split("/").pop()}:${f.line} `) : "", op(f.message),
        f.fix ? h("div", { class: "note" }, "Fix: ", op(f.fix)) : "",
        f.links?.length ? h("div", { class: "note" }, `See: ${f.links.join(", ")}`) : ""))));
  }
  return box;
}
