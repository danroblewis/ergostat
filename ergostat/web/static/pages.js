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
  const perf = {};
  let pts = {}, ptsAt = 0;
  p.append(box, cap);
  async function tick() {
    const loops = await api("loops");
    // the stocks' trends: every system open (or, where that is not at hand, a snapshot, each closed system's measures);
    // the whole graph is a large answer and a trend over the window hardly moves in seconds: asked for every 30s
    if (Date.now() - ptsAt > 30000) {
      const stocks = await api("graph", { open: "*" }).catch(() => api("graph"));
      for (const n of stocks.nodes) for (const m of n.measures || []) if (m.points) stocks.nodes.push({ kind: "stock", label: m.label, points: m.points });
      pts = Object.fromEntries(stocks.nodes.filter((n) => n.kind === "stock").map((n) => [n.label, n.points]));
      ptsAt = Date.now();
    }
    const w = windowNote();
    cap.textContent = w ? `Time off and back in: ${w}. Back in: typically, from going off to holding again.` : "";
    const rows = Object.entries(loops).sort((a, b) => (RANK[a[1].status] ?? 2) - (RANK[b[1].status] ?? 2));
    // how each loop is doing, as a control engineer reads its scope (control.js), over the last day of record: asked
    // for every 5 minutes, not every tick (each is an identification on the server, up to a second or two, for every loop)
    if (!perf.at || Date.now() - perf.at > 300000) {
      perf.at = Date.now();
      for (const [n] of rows) loopControl(n).then((d) => { perf[n] = performanceWord(d); if (cells[n]) cells[n].textContent = perf[n]; }).catch(() => {});
    }
    const cells = {};
    box.replaceChildren(table(["loop", "status", "holds", ["now", "num"], ["setpoint", "num"], ["error", "num"], ["time off", "num"], ["back in", "num"], "trend", "behaviour", "acted"],
      rows.map(([n, lp]) => h("tr", { class: "click", onclick: () => openLoop(n) },
        h("td", { class: "nowrap" }, h("b", {}, n), lp.open_loop ? h("span", { class: "muted", title: "Acts on its schedule, reads nothing" }, " open loop") : null),
        h("td", {}, statusEl(lp.status)), h("td", { class: "nowrap" }, lp.stock), h("td", { class: "num" }, fmt(lp.value)),
        h("td", { class: "num nowrap" }, op(lp.setpoint) + (lp.band || "")),
        h("td", { class: "num", title: "e = r − y" }, lp.error != null ? fmt(lp.error) : ""),
        h("td", { class: "num", title: "The share of the window the loop spent off" }, lp.off_share ? `${Math.round(lp.off_share * 100)}%` : "0%"),
        h("td", { class: "num", title: lp.back_in != null ? `Typically holding again this long after going off (slowest ${dur(lp.back_in_slowest)}, ${lp.times_off} times); its valve opens ${lp.answers_in != null ? dur(lp.answers_in) : "?"} after` : "It has not gone off and come back in the window" },
          lp.back_in != null ? dur(lp.back_in) : "–"),
        h("td", { class: "spark-cell", title: "Its scope: r and y, u, e over the window" },
          (pts[lp.stock] || []).length > 1 ? sparkSvg(pts[lp.stock], 120, 24, setpointOf(lp.setpoint)) : ""),
        cells[n] = h("td", { class: "nowrap", title: "Oscillating, saturated, or its Harris index: from its scope, over the last day of record" }, perf[n] || ""),
        h("td", { title: "In the window, its sensor read and its controller decided or its valve opened" }, lp.observed ? "yes" : h("span", { class: "muted" }, "no"))))));
  }
  await tick();
  S.timer = poll(tick, 3000, p);
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
  S.timer = poll(tick, 3000, p);
}

async function pageRecord(main, q) {
  const p = page(main, "Record");
  const filt = h("input", { type: "search", placeholder: "Type, e.g. valve.* or ticket.*", value: q.get("type") || "", "aria-label": "Event type" });
  const runs = h("input", { type: "checkbox" });
  const box = h("div");
  // from the wiring: one machine's events (its instances too), in the page's window
  const machine = q.get("machine") || "", inWindow = q.get("window") === "1", item = q.get("item") || "";
  const scope = machine || inWindow || item ? h("span", { class: "muted" }, [item ? `about ${item}` : "", machine ? `from ${machine}` : "", inWindow ? "in the window" : ""].filter(Boolean).join(", "),
    " ", h("a", { href: "/record" + (filt.value ? "?type=" + encodeURIComponent(filt.value) : "") }, "Show all")) : null;
  p.append(h("div", { class: "filters" }, filt, h("button", { onclick: () => tick() }, "Filter"), scope,
                h("label", { class: "check" }, runs, "Show runs", h("span", { class: "muted" }, "(agent.started, agent.ran)"))), box);
  runs.addEventListener("change", () => tick());
  filt.addEventListener("keydown", (ev) => { if (ev.key === "Enter") tick(); });
  async function tick() {
    let evs;
    try {
      evs = await api("events", { n: 80, ...(runs.checked ? { runs: 1 } : {}), ...(filt.value ? { type: filt.value } : {}),
                                  ...(machine ? { machine } : {}), ...(item ? { item } : {}), ...(inWindow ? { window: 1 } : {}) });
    } catch (err) { box.replaceChildren(h("p", { class: "muted" }, String(err.message || err))); return; }
    box.replaceChildren(evs.length ? eventsTable(evs, false) : h("p", { class: "muted" }, "Nothing recorded yet."));
  }
  await tick();
  S.timer = poll(() => (box.querySelector("details[open]") ? null : tick()), 3000, p);
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
      const shown = v.slice(-LIST_SHOWN), cols = [...new Set(shown.flatMap((x) => Object.keys(x)))];
      return h("div", {}, v.length > shown.length ? h("p", { class: "note" }, `The latest ${shown.length} of ${v.length}.`) : null,
        h("table", { class: "sub" }, h("tr", {}, cols.map((c) => h("th", {}, c))),
          shown.map((x) => h("tr", {}, cols.map((c) => h("td", {}, fieldView(x[c], false, depth + 1)))))));
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
  return table(["message", "state", "sent", "text", "outcome"], ms.map((m) => h("tr", { class: "click", ...rowLink(`/item/${encodeURIComponent(m.id)}`) },
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

function stateWord(st) { return st ? h("span", {}, st) : h("span", { class: "muted" }, "–"); }

async function pageItems(main, q) {
  const p = page(main, "Items");
  const kinds = h("div", { class: "kind-flows" }), notes = h("div"), box = h("div");
  const search = h("input", { type: "search", placeholder: "Search ids and fields", value: q.get("q") || "", "aria-label": "Search" });
  const more = h("p", { class: "note" });
  let kind = q.get("kind"), state = q.get("state");
  const compose = messageBox({ hint: "to the work in flight: routed to what it concerns, and delivered to it", done: () => tick() });
  p.append(kinds, notes, h("div", { class: "filters" }, search), compose, box, more);
  const group = chartGroup("items"), drawn = {};      // each kind's charts, kept while their data is the same (charts.js)
  let flows = {}, flowsAt = 0;
  const keep = (key, sig, make) => {
    const was = drawn[key];
    if (was && (was.sig === sig || was.el.matches(":hover"))) return was.el;
    drawn[key] = { sig, el: make() };
    return drawn[key].el;
  };
  const go = () => { const u = new URLSearchParams(); if (kind) u.set("kind", kind); if (state) u.set("state", state); if (search.value) u.set("q", search.value);
                     replaceRoute("/items" + (u.toString() ? "?" + u : "")); tick(); };
  search.addEventListener("input", () => go());
  async function tick() {
    compose.hidden = kind !== MESSAGE_KIND || !!SNAP;
    // the list as the page shows it: the newest of each kind (all a chosen kind's, up to 300), matched to the
    // search where it is kept, each with its kind's columns only (a snapshot holds the whole list: filtered here)
    const needle = search.value.trim().toLowerCase();
    const d = await api("items", { ...(kind ? { kind } : {}), ...(state ? { state } : {}),
                                   ...(SNAP ? {} : { per_kind: kind ? 300 : 25, shown: 1, ...(needle ? { q: needle } : {}) }) });
    // each kind: its states stacked over the window (a cumulative flow diagram), each named with its count,
    // a click on one shows its items; a kind without states, one line of its count. A flow over the window
    // hardly moves in seconds: each asked for every 30s, not on every refresh of the list
    if (Date.now() - flowsAt > 30000) {
      flowsAt = Date.now();
      flows = Object.fromEntries(await Promise.all(d.kinds.map(async (k) =>
        [k.name, k.states.length ? await api("items-flow", { kind: k.name, points: CHART_POINTS }).catch(() => null) : null])));
      for (const [name, fl] of Object.entries(flows)) if (fl && !Object.values(fl.counts).some((c) => c.some((x) => x))) flows[name] = null;   // none yet: its counts
    }
    const pick = (k, st) => { [kind, state] = kind === k.name && state === st ? [null, null] : [k.name, st]; go(); };
    kinds.replaceChildren(...d.kinds.map((k) => {
      const name = h("a", { href: "#", class: `kname${kind === k.name && !state ? " on" : ""}`, onclick: (ev) => { ev.preventDefault(); kind = kind === k.name && !state ? null : k.name; state = null; go(); } },
        k.name, h("span", { class: "mono" }, k.id));
      const fl = flows[k.name];
      if (!fl) return h("div", { class: "kind-flow" }, name, h("div", { class: "states" }, (k.states.length ? k.states : [""]).map((st, i) => [i ? h("span", { class: "arrow" }, "→") : null,
        h("a", { href: "#", class: `stbox${k.counts[st] ? " some" : ""}${kind === k.name && state === st ? " on" : ""}`, onclick: (ev) => { ev.preventDefault(); pick(k, st); } },
          h("span", { class: "n" }, String(k.counts[st] || 0)), st || "items")])));
      const chosen = kind === k.name ? state : null;
      return h("div", { class: "kind-flow" }, name,
        keep(`cfd:${k.name}`, JSON.stringify([fl.times, fl.counts, chosen]), () => flowChart(fl, group, { chosen, onState: (st) => pick(k, st) })));
    }));
    notes.replaceChildren(...[
      d.unkinded ? h("p", { class: "note" }, `${d.unkinded} item${d.unkinded > 1 ? "s" : ""} match no kind under items: in ergostat.yaml; shown with their fields, no state.`) : null,
      !d.kinds.length && !d.unkinded ? h("p", { class: "muted" }, "No items yet. An item is what events with an id like ticket/12 are about; see the Guide.") : null].filter(Boolean));
    const rows = SNAP ? d.items.filter((i) => !needle || (i.id + " " + JSON.stringify(i.fields)).toLowerCase().includes(needle)) : d.items;
    const val = (v) => v == null ? "" : typeof v === "object" ? JSON.stringify(v) : String(v);
    const kindOf = Object.fromEntries(d.kinds.map((x) => [x.name, x]));
    const isNum = (its, f) => its.some((i) => typeof i.fields[f] === "number") && its.every((i) => i.fields[f] == null || typeof i.fields[f] === "number");
    const tableOf = (its, show, limit) => {
      const nums = new Set(show.filter((f) => isNum(its, f)));
      return table(["item", "state", ...show.map((f) => (nums.has(f) ? [f, "num"] : f)), ["in state", "num"], ["events", "num"], "latest", "last"],
        its.slice(0, limit).map((i) => h("tr", { class: "click", ...rowLink(`/item/${encodeURIComponent(i.id)}`) },
          h("td", { class: "nowrap" }, h("a", { href: `/item/${encodeURIComponent(i.id)}`, class: "plain" }, h("b", {}, i.id))), h("td", { class: "nowrap" }, stateWord(i.state)),
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
      const limit = kind ? 300 : 25, many = d.matched?.[name] ?? its.length;
      parts.push(h("h2", {}, name || "No kind", h("span", { class: "muted" }, ` ${many}`)));
      parts.push(tableOf(its, show, limit));
      if (name === CLAIM_KIND) {                          // how far each block's claims held
        const t = await api("trust").catch(() => null);
        if (t) parts.push(keep("trust", JSON.stringify([t.rows, Math.round(t.until - t.since)]), () => trustView(t)));
      }
      const fl = flows[name];                              // under its table: how long its finished items took
      if (fl) parts.push(keep(`cycle:${name}`, JSON.stringify([fl.times[0], fl.finished]), () => cycleChart(fl, group)));
      if (many > limit) parts.push(h("p", { class: "note" }, h("a", { href: "#", onclick: (ev) => { ev.preventDefault(); kind = name; state = null; go(); } }, `All ${many}`)));
    }
    const listed = d.listed ?? d.items.length;          // what the server's list held, before the search and the cut per kind
    box.replaceChildren(...(parts.length ? parts : [listed ? h("p", { class: "muted" }, "Nothing matches.") : ""]));
    more.textContent = d.total > listed ? `${d.total - listed} older items not loaded.` : "";
  }
  await tick();
  S.timer = poll(tick, 4000, p);
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
  const rows = cs.slice().reverse().map((c) => h("tr", {}, h("td", { class: "nowrap" }, when(c.time)), h("td", { class: "nowrap" }, how(c)),
    h("td", { class: "mono small" }, c.path || "/"), h("td", { class: "cell" }, c.op === "refused" ? c.why : val(c.before)),
    h("td", { class: "cell" }, c.op === "refused" ? "" : val(c.after)), h("td", { class: "nowrap" }, eventLink(c.event, c.type, d))));
  return h("details", { class: "history" }, h("summary", {}, `history (${total} change${total > 1 ? "s" : ""})`),
    total > cs.length ? h("p", { class: "note" }, `The latest ${cs.length} of ${total}; `, h("code", {}, `ergostat item ${d.id} --history`), " lists all.") : null,
    table(["when", "change", "path", "before", "after", "by event"], rows, "history"));
}

async function pageItem(main, id) {
  const p = page(main, id);
  const body = h("div");
  p.append(body);
  const note = messageBox({ about: id, title: "Send a note about this", done: () => tick() });
  let full = null;                                   // its full history, once asked for: kept across refreshes
  async function tick() {
    if (note.contains(document.activeElement) && note.querySelector("textarea").value) return;   // being written
    let d;
    try { d = await api(`items/${encodeURIComponent(id)}`); } catch (e) { d = null; }
    if (!d) { body.replaceChildren(h("p", { class: "muted" }, "Nothing is recorded about this id.")); return; }
    const k = d.kind_of;
    const pair = (label, value) => h("span", {}, h("span", {}, label), value);
    const head = h("div", { class: "meta" },
      pair("Kind", k ? h("a", { href: `/items?kind=${encodeURIComponent(k.name)}` }, k.name) : h("span", { class: "muted" }, "none (nothing under items: matches this id)")),
      d.state ? pair("State", h("span", {}, h("b", {}, d.state), ` for ${dur(nowS() - d.entered)}`)) : null,
      pair("Events", String(d.events)), pair("First", ago(d.first)), pair("Latest", h("span", {}, d.latest, h("span", { class: "muted" }, `, ${ago(d.last)}`))));
    const track = k && k.states.length ? h("div", { class: "track" }, k.states.map((st, i) => [i ? h("span", { class: "arrow" }, "→") : null,
      h("span", { class: `stbox${st === d.state ? " on" : ""}${d.moves.some((m) => m.to === st) || (i === 0) ? " been" : ""}` }, st)])) : null;
    const moves = d.moves.length ? table(["when", "from", "to", "by event", ["after", "num"]],
      d.moves.map((m, i) => h("tr", {}, h("td", { class: "nowrap" }, new Date(m.time * 1000).toLocaleString([], { hour12: false })), h("td", { class: m.from ? "" : "muted" }, m.from || "arrived"), h("td", {}, m.to),
        h("td", { class: "muted" }, m.type), h("td", { class: "num muted" }, i ? dur(m.time - d.moves[i - 1].time) : "")))) : h("p", { class: "muted" }, "Its kind has no states.");
    // its kind's chosen fields first, in their order, then the rest by name
    const first = (k?.show || []).filter((f) => f in d.fields);
    const hist = d.history || {}, gone = Object.keys(hist).filter((f) => f && !(f in d.fields));   // removed since: still have a history
    const order = [...first, ...Object.keys(d.fields).filter((f) => !first.includes(f)).sort(), ...gone.sort()];
    const fields = order.length ? h("div", { class: "table-wrap" }, h("table", { class: "fields" }, order.map((f) => h("tr", { "data-field": f },
      h("th", {}, f, k?.fold?.[f] ? h("span", { class: "muted small rule", title: "how its events' data folds into it" }, ` ${k.fold[f]}`) : null),
      h("td", {}, f in d.fields ? fieldView(d.fields[f], false, 0, (k?.formats || {})[f]) : h("span", { class: "muted" }, "removed"),
        historyView(hist[f] || [], (d.changes || {})[f] || 0, d))))))
      : h("p", { class: "muted" }, "No fields: its events carry no data.");
    const refused = (d.refused || []).length ? [h("h2", {}, "Refused"), h("p", { class: "note" }, "Events recorded that changed nothing: their changeset could not apply, so none of it did."),
      table(["when", "event", "as", "why"], d.refused.slice().reverse().map((r) => h("tr", {}, h("td", { class: "nowrap" }, when(r.time)),
        h("td", { class: "nowrap" }, eventLink(r.event, r.type, d)), h("td", { class: "muted" }, r.form), h("td", {}, r.why))), "refused")] : [];
    const said = d.transcript_events ? h("p", { class: "note" }, `${d.transcript_events} more events are its transcript's lines (claude.*), folded into its fields above; `,
      recordLinkItem(id), ".") : null;
    const verdict = k?.name === CLAIM_KIND ? [h("h2", {}, "Verdict"), claimView(d)]
      : k?.name === DECISION_KIND || k?.name === CORRECTION_KIND ? [h("h2", {}, k.name === DECISION_KIND ? "The decision" : "The correction"), intentView(d, tick)]
      : k?.name === MESSAGE_KIND ? [h("h2", {}, "Message"), messageView(d, tick)] : [];
    let about = [];
    if (!k?.name?.startsWith("ergostat.")) {               // the owner's messages about it, and a note to send
      const ms = await api("messages", { item: id }).catch(() => null);
      if (ms) about = [h("h2", {}, "Messages", h("span", { class: "muted" }, ` ${ms.messages.length}`)), messagesAbout(ms.messages), SNAP ? "" : note];
    }
    // its oldest events rolled up into a snapshot (SPEC §4b): the originals are in the archive, read when asked for
    const ro = d.rollup;
    const rolled = ro ? h("p", { class: "note" }, `Its ${ro.archived.events} oldest events, up to ${when(ro.last)}, are rolled up into one snapshot and archived. `,
      full ? null : h("button", { class: "ghost", onclick: async () => { full = await api(`items/${encodeURIComponent(id)}`, { archived: 1, n: 1000 }); tick(); } }, "Show the full history"),
      full && full.total > full.events.length ? h("span", { class: "muted" }, ` (the first ${full.events.length} of ${full.total})`) : null) : null;
    body.replaceChildren(head, track || "", ...verdict, ...about, h("h2", {}, "Fields"), fields, ...refused, h("h2", {}, "How it moved"), moves,
      h("h2", {}, "Events", h("span", { class: "muted" }, ` ${d.events}`)), said || "", rolled || "",
      eventsTable(full ? full.events : d.record, true));
  }
  await tick();
  S.timer = poll(() => (body.querySelector("details[open], .intent-act:not([hidden])") ? null : tick()), 4000, p);
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
  async function tick() {
    let d;
    try { d = await api("fit"); } catch (e) { d = null; }
    if (!d) { fitBox.replaceChildren(h("p", { class: "muted" }, "The model is an ergostat.toml: equations and their fit come with ergostat.yaml.")); return; }
    availableView(d, availBox);
    const span = d.until && d.since ? dur(d.until - d.since) : "";
    fitBox.replaceChildren(
      ...(d.invalid?.length ? [h("p", { class: "s-off" }, `The replay is not valid: ${d.invalid.join("; ")}.`)] : []),
      h("h3", {}, "Model fit", h("span", { class: "muted" }, ` the stocks an equation moves, over the last ${span} of record`)),
      d.stocks.length ? table(fitHead(d.words, "stock"), fitRows(d.stocks, d.total), "fit")
        : h("p", { class: "muted" }, "No stock is moved by an equation: nothing here tests the model's equations yet."));
    const judged = Object.entries(d.judged_by_stock || {});
    eqBox.replaceChildren(...(d.partial.length || d.equations.length || judged.length ? [
      h("h3", {}, "Equations, inputs as measured", h("span", { class: "muted" }, " the partial-model test")),
      d.partial.length ? table(fitHead(d.words, "worked out"), fitRows(d.partial, null), "fit") : h("p", { class: "muted" }, "No equation's part is measured."),
      ...(d.equations.length ? [h("h3", {}, "Equations, replayed", h("span", { class: "muted" }, " every stock integrated")),
        table(fitHead(d.words, "worked out"), fitRows(d.equations, null), "fit")] : []),
      ...judged.map(([r, st]) => h("p", { class: "muted small" }, `${r.split(".").slice(1).join(".")} is measured from its stock's changes: judged by ${st ? st.split(".").slice(1).join(".") : "its stock"}'s replay, above.`)),
    ] : []));
    accBox.replaceChildren(...(d.accounting.length ? [h("h3", {}, "Accounting", h("span", { class: "muted" }, " stocks moved only by measured flows")),
      table(fitHead(d.words, "stock"), fitRows(d.accounting, null), "fit")] : []));
    notes.replaceChildren(...d.notes.map((n) => h("p", { class: "muted small" }, n)));
    const why = Object.entries(d.not_proposed || {});
    const q = d.queue || [];
    const sig = JSON.stringify(q.map((x) => [x.id, x.diff?.hash, x.conflicts.length])) + (d.estimated_at || "") + JSON.stringify(why) + d.loops_analysed;
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
        said].filter(Boolean));
      queueBox.replaceChildren(...(q.length ? q.map((x) => reviewEntry(x, { onDone: () => { propSig = null; allBox.replaceChildren(); setTimeout(tick, 600); } }))
        : [h("p", { class: "muted" }, "Nothing waiting.")]));
      whyBox.replaceChildren(...(why.length ? [h("h3", {}, "Estimates not proposed"),
        table(["parameter", "why"], why.map(([n, w]) => h("tr", {}, h("td", {}, h("b", {}, n)), h("td", { class: "small" }, w))), "can")] : []),
        ...(d.open_loops?.length ? [h("p", { class: "muted small" }, `Every stock integrated still leaves open ${d.open_said}, since the replay takes what a decision sets as measured.`)] : []));
      canBox.replaceChildren(proposableView(d));
    }
    const events = [...d.history.map((v) => ({ t: v.first, v })), ...d.accepted.map((a) => ({ t: a.time, a }))].sort((x, y) => y.t - x.t);
    histBox.replaceChildren(events.length ? table(["when", "version", ["scaled error", "num"], ["over", "num"], ""], events.slice(0, 30).map(({ v, a }) => (v
      ? h("tr", {}, h("td", { class: "nowrap" }, ago(v.first)), h("td", { class: "mono" }, v.version, v.version === d.version ? h("span", { class: "muted" }, " now") : null),
          h("td", { class: "num" }, v.total?.nmse != null ? fmt(v.total.nmse) : ""), h("td", { class: "num nowrap" }, v.window ? dur(v.window) : ""),
          h("td", { class: "muted small" }, `fitted ${v.fits} time${v.fits > 1 ? "s" : ""}, last ${ago(v.last)}`))
      : h("tr", {}, h("td", { class: "nowrap" }, ago(a.time)), h("td", { class: "mono muted" }, `${a.version_before} \u2192 ${a.version_after}`),
          h("td", { class: "num nowrap" }, `${a.fit_before?.nmse != null ? fmt(a.fit_before.nmse) : "\u2013"} \u2192 ${a.fit_after?.nmse != null ? fmt(a.fit_after.nmse) : "\u2013"}`),
          h("td", {}, ""), h("td", {}, "accepted: ", op(a.title))))), "fit")
      : h("p", { class: "muted" }, "Not fitted before."));
    const r = d.residuals || {};
    const rows = Object.entries(r).sort((a, b) => (b[1].significant ? 1 : 0) - (a[1].significant ? 1 : 0));
    resBox.replaceChildren(Object.keys(r).length ? table(["stock", ["changed", "num"], ["explained", "num"], ["unexplained", "num"], ""],
      rows.map(([k, v]) => h("tr", {}, h("td", {}, h("b", {}, k)), h("td", { class: "num" }, fmt(v.change)), h("td", { class: "num" }, fmt(v.explained)),
        h("td", { class: "num" }, fmt(v.unexplained)),
        h("td", {}, v.significant ? h("span", { class: "s-open" }, "unexplained") : (v.absorbed_by.length ? h("span", { class: "muted" }, `estimated as ${v.absorbed_by.join(", ")}`) : "")))), "fit")
      : h("p", { class: "muted" }, "No stock has two readings in this window yet."));
    cap.replaceChildren(rich(`Version ${d.version}, fitted over the last ${span} of record (at most a day, whatever the window above). ` +
      "The model is read the way the record was made: a level at its reading's moment, a counted flow by what it moved in each bucket, a rate a sensor averages by the model's own average. " +
      `Each series needs ${d.min_points} points over three of its slowest time constant to be judged. ` +
      `The total: ${d.words.nmse}. R\u00b2: ${d.words.r2}. MAPE: ${d.words.mape}. Theil's U_M: ${d.words.um}; U_S: ${d.words.us}; U_C: ${d.words.uc}; the three sum to 1. ` +
      `Accounting: ${d.words.accounting}. ` +
      "Residuals: what each stock did against what its known flows explain; a disturbance nothing measures is estimated from the rest."));
  }
  await tick();
  S.timer = poll(tick, 5000, p);
}

async function pageCheck(main) {
  const st = await api("status");
  let quiet = [];                                          // the parts the record has not exercised (a finding each)
  try { quiet = await api("exercised"); } catch (e) { quiet = []; }
  st.check = [...st.check, ...quiet.map((x) => ({ level: "warn", message: x.message }))];
  const errors = st.check.filter((c) => c.level === "error").length, warnings = st.check.length - errors;
  const words = [errors ? `${errors} error${errors > 1 ? "s" : ""}` : "", warnings ? `${warnings} warning${warnings > 1 ? "s" : ""}` : ""].filter(Boolean);
  const p = page(main, words.length ? `Check: ${words.join(", ")}` : "The model is whole");
  if (st.check.length) p.append(h("div", { class: "att" }, st.check.map((c) => h("div", {},
    h("b", { class: c.level === "error" ? "lvl-error" : "lvl-warning" }, c.level === "error" ? "Error" : "Warning"), " ", op(c.message)))));
  p.append(h("h2", {}, "Counts"), h("dl", { class: "counts" }, Object.entries(st.counts).flatMap(([k, v]) => [h("dt", {}, k), h("dd", {}, fmt(v))])));
}
