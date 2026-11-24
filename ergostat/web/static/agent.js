/* an agent's own page (/agent/NAME): what it is, by its rung; its definition as written; its place in the model; what it
   did (the panel's own sections, details.js). Each section is an anchor; the page is asked again as an item's page is */
"use strict";

const RUNG_SECTION = ["What they are asked", "Its prompt", "Its specification", "How it decides", "Its program", "Its law", "Its law"];
const FILE_LANG = { python: "python", shell: "bash", yaml: "yaml", json: "json", javascript: "javascript", toml: "ini",
                    markdown: "markdown", text: "plaintext" };
const SLOT = /(\{[A-Za-z_][\w.-]*\})/;
const agentHref = (n) => `/agent/${encodeURIComponent(n)}`;
const agentA = (n) => h("a", { href: agentHref(n) }, n);
/* a text for a reader: its references to SPEC's sections (in a docstring, a YAML comment) taken out */
const noSpec = (t) => String(t).replace(/\s*\([^()]*SPEC §[^()]*\)/g, "").replace(/,?\s*SPEC §[\w.§, ]*/g, "");

/* a prompt as Markdown, each {slot} outside its code marked: the engine fills it in per item */
function promptView(text) {
  const el = md(noSpec(text), null, true), hits = [];
  const walk = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
  for (let n = walk.nextNode(); n; n = walk.nextNode()) if (!n.parentElement.closest("code, pre") && SLOT.test(n.nodeValue)) hits.push(n);
  for (const n of hits) n.replaceWith(...n.nodeValue.split(SLOT).map((s, i) => (i % 2 ? h("mark", { class: "slot", title: "filled per item" }, s) : s)));
  return [el, hits.length ? h("p", { class: "note" }, "Marked: filled per item.") : null];
}
/* one of its files: its name, then its text highlighted (or why it is not shown), in a disclosure open or closed */
function fileBox(f, open, summary = f.name) {
  return h("details", { class: "agent-file", key: `${f.role}:${f.name}`, open: open ? "" : null }, h("summary", {}, summary),
    f.text != null ? code(noSpec(f.text), FILE_LANG[f.format] || null) : h("p", { class: "muted" }, f.why || "not read"));
}
/* the keys written for it, as a definition list (a record or a list as the item page shows a field) */
const keysList = (P, ks) => dl(ks.map((k) => [k, P[k] == null ? null : typeof P[k] === "object" ? fieldView(P[k]) : String(P[k])]));

function promptPart(sp, files) {
  const f = files.find((x) => x.role === "prompt"), P = sp?.params || {};
  if (f) return [h("p", { class: "muted file-name" }, f.name), f.text != null ? promptView(f.text) : h("p", { class: "muted" }, f.why || "not read")];
  const t = sp?.prompt_text ?? (typeof P.prompt === "string" ? P.prompt : null);
  return t ? promptView(t) : null;
}
function programPart(sp, files) {
  const P = sp?.params || {}, prog = files.filter((x) => x.role === "program");
  return [P.run ? h("p", {}, "Runs ", h("code", { class: "command" }, String(P.run))) : null,
    P.daemon ? h("p", {}, `Handed to the daemon ${P.daemon}.`) : null,
    sp?.own ? [h("p", { class: "own" }, h("b", {}, `ergostat's own: ${sp.own.module}`)),   // its docstring, for a reader: no SPEC sections
      sp.own.doc ? h("p", { class: "muted" }, noSpec(sp.own.doc)) : null] : null,
    prog.map((f, i) => fileBox(f, i === 0))];
}
function lawPart(sp) {
  const l = sp?.law || {}, P = sp?.params || {};
  if (l.error) return h("p", { class: "muted" }, `Its law could not be worked out: ${l.error}`);
  const rows = (l.rows || []).filter(([, v]) => v != null && v !== "");
  return [l.says ? h("p", { class: "what law-says" }, rich(op(l.says))) : null, (l.math || []).map((m) => h("div", { class: "bd-math" }, mathml(m))),
    rows.length ? dl(rows.map(([k, v]) => [k, typeof v === "string" ? rich(op(v)) : v])) : null,
    ["table", "points", "schedule"].filter((k) => P[k] && typeof P[k] === "object").map((k) => [h("h3", {}, k), fieldView(P[k])]),
    sp?.implied_by ? h("p", { class: "implied-by" }, "implied by ", agentA(sp.implied_by), "'s goal") : null];
}
function decidesPart(sp) {
  const d = sp?.decisions, hint = d?.hint;
  return [h("h3", {}, "The answers it gave in the window"), d?.count
    ? h("ol", { class: "decisions" }, d.kinds.map(([w, n]) => h("li", {}, w.replaceAll("#", "N"), h("span", { class: "muted" }, ` (${n})`))))
    : h("p", { class: "muted" }, "no decisions in the window"),
    hint ? h("p", { class: "ladder-hint" }, `${hint.controller}: “${hint.decision}” in ${Math.round(hint.share * 100)}% of ${hint.count} decisions; a cheaper rung could fill it.`) : null];
}

/* what it is, by its rung: the section a person, an AI, a narrow AI, a decision, a program or a rule is read by */
function whatItIs(a, sp, files) {
  const r = a.rung ?? a.agent?.rung, P = { ...(sp?.machine?.model ? { model: sp.machine.model } : {}), ...(sp?.params || {}) };
  const none = (t) => h("p", { class: "muted" }, t);
  if (r === 0) {
    const ask = P.ask ?? P.prompt;
    return [ask ? md(noSpec(ask)) : none("No ask written."),
      h("p", { class: "asked-now" }, a.running_since ? `Asked now: since ${ago(a.running_since)}, not answered yet.` : "Nothing is asked of them now.")];
  }
  if (r === 1) {
    const wrap = files.filter((x) => x.role === "wrapper");
    return [promptPart(sp, files) || none("No prompt written."), keysList(P, ["model", "tools", "actions", "read", "workspace", "emits", "takes", "lease"]),
      wrap.length || P.run ? h("details", { class: "wrapper", key: "wrapper" }, h("summary", {}, "Its wrapper"),
        P.run ? h("p", {}, "Runs ", h("code", { class: "command" }, String(P.run))) : null, wrap.map((f) => fileBox(f, true))) : null];
  }
  if (r === 2) return [promptPart(sp, files) || none("No prompt written."), keysList(P, ["model", "out", "outputs", "max-cost", "run"])];
  if (r === 3) return [promptPart(sp, files) || programPart(sp, files), decidesPart(sp)];
  if (r === 4) return [programPart(sp, files), !P.run && !P.daemon && sp ? h("p", { class: "muted" }, sp.rung_why) : null];
  return lawPart(sp);
}
function definitionPart(sp) {
  if (!sp) return h("p", { class: "muted" }, "Its block is not in the model's YAML.");
  if (sp.implied) return h("p", { class: "implied" }, "not written: ergostat put it in", sp.implied_by ? [" front of ", agentA(sp.implied_by)] : "", ".");
  return [sp.where ? h("p", { class: "muted file-name" }, `${sp.where.file}:${sp.where.line}`) : null,
    sp.source ? code(noSpec(sp.source), "yaml") : h("p", { class: "muted" }, "Its text could not be read.")];
}
function placePart(a, sp, loops, name) {
  const pl = a.place || {}, list = (xs) => xs.flatMap((x, i) => [i ? ", " : "", agentA(x)]);
  const w = pl.working, word = (n) => `${n} ${w.kind}${n === 1 ? "" : "s"}`;
  return [dl([["serves", servesEl(a, sp, loops, true)], ["fills", rolesText(a.roles) || "nothing"],
    ["commanded by", (pl.commanded_by || []).length ? list(pl.commanded_by) : null], ["commands", (pl.commands || []).length ? list(pl.commands) : null],
    ["working now", w ? (w.n == null ? "not known" : h("a", { href: itemsHref(w.set), class: "working" }, `working ${word(w.n)}`)) : null]]),
    h("p", {}, h("a", { href: `/diagram?view=blocks&around=block/${encodeURIComponent(name)}` }, "Show on Blocks"))];
}
/* the goals it serves, each a link to its evidence, with its word now */
function servesEl(a, sp, loops, words) {
  const gs = [...new Set([a.place?.goal, ...(a.roles || []).map((r) => r.goal || (r.kind === "controller" ? r.name : null)),
    ...(sp?.decisions?.controllers || [])].filter((g) => g && loops?.[g]))];
  return gs.length ? gs.flatMap((g, i) => [i ? ", " : "", h("a", { href: `/goals?select=${encodeURIComponent(g)}`, class: "goal" }, g),
    words ? [" ", statusEl(goalWord(loops[g]))] : null]) : null;
}

async function pageAgent(main, name) {
  const p = page(main, name);
  p.classList.add("agent-page");
  const meta = h("div", { class: "meta" }), body = h("div");
  p.append(meta, body);
  const ans = answers();
  let drawn = false;
  async function tick(force = true) {
    ans.begin();
    let a, fs, loops;
    try {
      a = await ans.api(`agents/${encodeURIComponent(name)}`);
      fs = await ans.api(`agents/${encodeURIComponent(name)}/files`).catch(() => ({ files: [] }));
      loops = await ans.api("loops").catch(() => ({}));
    } catch (e) {
      if (!p.isConnected || pageLeft(e)) return;
      if (/: 404$|not in this snapshot/.test(e.message || "")) {
        patch(meta); patch(body, h("p", { class: "no-agent" }, `no agent ${name} · `, h("a", { href: "/agents" }, "every agent")));
      } else if (!drawn) patch(body, h("p", { class: "muted" }, "Could not be read."));
      return;
    }
    if (!p.isConnected || (!force && !ans.changed)) return;      // nothing changed: nothing touched
    const sp = a.spec, r = a.rung ?? a.agent?.rung, files = fs.files || [];
    const pair = (label, value) => (value == null || value === "" ? null : h("span", {}, h("span", {}, label), value));
    const sec = (id, title, ...kids) => h("section", { id, key: id }, h("h2", {}, title), ...kids);
    const jump = (id, text) => h("a", { href: `#${id}`, onclick: (ev) => { ev.preventDefault(); document.getElementById(id)?.scrollIntoView(); } }, text);
    patch(meta, pair("Kind", h("span", { title: sp?.rung_why || "" }, `${RUNG_LETTER[r] ?? "?"} ${RUNG_NAMES[r] || "retired"}`)),
      pair("Machine", sp?.machine ? `${sp.machine.name}${sp.machine.model ? `, ${sp.machine.model}` : ""}` : null),
      pair("System", a.place?.system), pair("Serves", servesEl(a, sp, loops, true)), pair("Engaged", engagedText(a)),
      pair("Mode", a.place?.mode), pair("Defined at", sp?.where ? jump("its-definition", `${sp.where.file}:${sp.where.line}`)
        : sp?.implied ? jump("its-definition", "not written") : null));
    patch(body, a.agent?.description ? h("p", { class: "muted" }, noSpec(a.agent.description)) : null,
      sec("what-it-is", RUNG_SECTION[r] || "Its law", whatItIs(a, sp, files)),
      sec("its-definition", "Its definition", definitionPart(sp)),
      sec("its-place", "Its place", placePart(a, sp, loops, name)),
      sec("what-it-did", "What it did", dl(agentTally(a)), agentRuns(a, name)));
    if (!drawn && location.hash.length > 1 && !location.hash.startsWith("#/")) document.getElementById(location.hash.slice(1))?.scrollIntoView();
    drawn = true;
  }
  await tick();
  S.timer = poll(() => tick(false), 4000, p);
}
