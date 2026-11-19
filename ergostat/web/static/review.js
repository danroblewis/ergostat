/* the review queue on the Model page: every change to the model waiting for the owner, read like a pull request
   (numbers/review.py). Each entry: what kind of change (its title), where (the parts, and Show on diagram,
   which chooses them and opens the diagram with the other view beside it), why, how it was found, its
   benefit; opened, its effect (the parts' record, the model's line as it is and with the change, and the
   projections, simulated with the change in memory) and exactly the diff Accept writes. Accept asks once
   more, beside the diff; Dismiss takes a reason. Simulate all pending tries every one together. */
"use strict";

const REVIEW_OPEN = new Set();                         // the entries opened, kept across the page's refreshes
const PART_WORDS = { stock: "stock", flow: "flow", auxiliary: "auxiliary", goal: "goal", block: "block", system: "system" };

/* the parts chosen, and the diagram opened on them: the dynamics view, with the block diagram beside it */
function showOnDiagram(parts, systems = []) {
  choose(parts);
  if (!PANE && typeof SPLIT === "object" && innerWidth >= SPLIT_NARROW && !SPLIT.open) { SPLIT.open = true; SPLIT.edge = "right"; SPLIT.frac = 0.5; }
  const q = new URLSearchParams({ view: "dynamics", ...(systems.length ? { open: systems.join(",") } : {}) });
  S.graphSig = "";
  navigate(`/diagram?${q}`);
}

/* a model tool's panel, from the Model page: the diagram in the view the tool lives in, every system open so
   the part is drawn, the part chosen and its panel opened once it is drawn (toolArrived, after each drawing).
   `part` is a model part (stock.x, flow.x, auxiliary.x); `find` picks a shape (a loop's process block); `causal`
   names a feedback loop in the dynamics view */
function openTool({ view, part = null, find = null, causal = null, goal = null }) {
  S.toolOpen = { view, part, find, causal, goal, at: Date.now() };
  S.graphSig = ""; S.fitted = false;
  navigate(`/diagram?${new URLSearchParams({ view, open: "*" })}`);
}
function toolArrived() {
  const t = S.toolOpen, g = S.graph;
  if (!t || !g || g.kind !== t.view) return;
  S.toolOpen = null;
  if (Date.now() - t.at > 60000) return;
  if (t.causal) {
    const c = (g.causalLoops || []).find((x) => x.name === t.causal) || (g.causalLoops || []).find((x) => x.name.startsWith(t.causal));
    if (c) { sdHighlight(c.name); openCausal(c.name); lookAt(document.querySelector(`svg.canvas .loop-marker[data-loop="${CSS.escape(c.name)}"]`)); }
    return;
  }
  const id = t.find ? g.nodes.find(t.find)?.id : (g.corr?.parts?.[t.part] || [])[0];
  const n = id && g.nodes.find((x) => x.id === id);
  if (!n) return;
  if (g.kind === "blocks") { S.bdSel = { node: n.id }; bdTrace($("svg.canvas"), S.bdSel); chooseShape(n.id); openBlock(n); }
  else { chooseShape(n.id); openNode(n); }
  lookAt(document.querySelector(`svg.canvas g.node[data-id="${CSS.escape(n.id)}"]`));
  if (t.goal) scrollToLoop(t.goal);
}
/* the view panned (at the zoom it has) so a shape is in the middle of the canvas */
function lookAt(el) {
  const svg = $("svg.canvas");
  if (!el || !svg || !S.view) return;
  const r = svg.getBoundingClientRect(), b = el.getBoundingClientRect();
  S.view = { ...S.view, x: S.view.x + (r.left + r.width / 2) - (b.left + b.width / 2), y: S.view.y + (r.top + r.height / 2) - (b.top + b.height / 2) };
  applyView(svg);
}
/* a panel holding several loops' sections (a MIMO process, a controller of several): scrolled to the loop's own */
function scrollToLoop(goal, tries = 40) {
  const el = [...document.querySelectorAll("#detail .control h3")].find((x) => x.textContent.includes(`loop ${goal}`));
  if (el) return el.scrollIntoView({ block: "start" });
  if (tries > 0) setTimeout(() => scrollToLoop(goal, tries - 1), 250);
}

function partWords(refs, max = 6) {
  const out = refs.slice(0, max).map((r) => {
    const [k, ...rest] = r.split(".");
    return h("span", { class: "part-ref" }, h("span", { class: "muted" }, `${PART_WORDS[k] || k} `), rest.join("."));
  });
  const joined = out.flatMap((x, i) => (i ? [", ", x] : [x]));
  if (refs.length > max) joined.push(h("span", { class: "muted" }, ` and ${refs.length - max} more`));
  return joined;
}

const nm = (v) => (v == null ? "–" : fmt(v));
const r2s = (v) => (v == null ? "–" : v.toFixed(2));
function benefitRows(b) {
  const rows = [];
  if (b.said) rows.push(h("div", { class: b.better === false ? "s-open" : "" }, `scaled error: ${b.said}`));
  else if (b.nmse_before != null || b.nmse_after != null) rows.push(h("div", {}, `scaled error ${nm(b.nmse_before)} → ${nm(b.nmse_after)}`,
    h("span", { class: "muted" }, b.nmse_after != null && b.nmse_before != null ? (b.nmse_after < b.nmse_before ? ", better" : b.nmse_after > b.nmse_before ? ", worse" : ", the same") : "")));
  for (const x of b.parts || []) if (x.r2_before != null || x.r2_after != null)
    rows.push(h("div", { class: "small" }, h("span", { class: "muted" }, `${x.ref.split(".").slice(1).join(".")} `), rich(`R² ${r2s(x.r2_before)} → ${r2s(x.r2_after)}`)));
  if (b.margins) rows.push(h("div", { class: "small" }, b.margins));
  return rows.length ? rows : null;
}
function howText(hw) {
  const bits = [hw.method || "–"];
  if (hw.span) bits.push(`over ${dur(hw.span)} of record`);
  if (hw.n) bits.push(`${hw.n} points`);
  return [h("div", {}, bits.join(", ")), hw.confidence ? h("div", { class: "small muted" }, hw.confidence) : null];
}

/* the effect, simulated: a small chart per part (measured, the model as it is dashed, with the change in the
   accent), and what changes ahead */
function effectView(d, box) {
  if (d.error) return box.replaceChildren(h("p", { class: "s-open small" }, d.error));
  const group = chartGroup("review");
  const charts = (d.charts || []).map((c, i, all) => lineChart({ group, name: c.name, role: c.new ? "new" : c.gone ? "removed" : c.same ? "unchanged" : PART_WORDS[c.kind],
    unit: c.unit, per: c.per, times: d.times, values: c.measured?.length ? c.measured : d.times.map(() => null), since: d.since, until: d.until,
    replay: c.before, projection: c.proj_before, ptimes: d.ptimes, whatifReplay: c.after, whatifProjection: c.proj_after,
    height: 56, xAxis: i === all.length - 1 }));
  const fb = d.fit_before?.total, fa = d.fit_after?.total;
  box.replaceChildren(...[
    d.predicts ? h("p", { class: "predicts" }, "Predicts: ", d.predicts.said) : null,
    charts.length ? h("div", { class: "review-charts" }, ...charts) : h("p", { class: "muted small" }, "Nothing it changes is replayed."),
    charts.length ? h("p", { class: "muted small" }, `Measured, solid; the model as it is, dashed; with the change, in blue; past now, the projections over ${dur(d.horizon || 0)}${d.loops === "closed" ? ", with the loops running (each machine block by its identified model)" : ", held (open loop)"}.`) : null,
    d.valid === false ? h("p", { class: "s-open small" }, `With it the replay is not valid: ${(d.invalid || []).join("; ")}.`) : null,
    dl([["fit now", fb || fa ? `scaled error ${nm(fb?.nmse)} → ${nm(fa?.nmse)}` : null],
        ["ahead", (d.operational || []).length ? h("div", {}, ...d.operational.map((x) => h("div", {}, x))) : null],
        ["leverage", (d.leverage || []).length ? h("div", {}, ...d.leverage.map((x) => h("div", {}, x)))
          : h("span", { class: "muted small" }, "none to say: no flow it touches moves what a goal holds in the projection")],
        ["not drawn", (d.undrawn || []).length ? h("div", {}, ...d.undrawn.map((x) => h("div", { class: "small" }, x))) : null],
        ["left out", (d.left || []).length ? h("div", {}, ...d.left.map((x) => h("div", { class: "small" }, h("span", { class: "mono" }, x.id), ` ${x.why}`))) : null]])].filter(Boolean));
}

function diffView(u) {
  return h("pre", { class: "diff" }, String(u || "").replace(/\n$/, "").split("\n").map((l) =>
    h("div", { class: l.startsWith("+++") || l.startsWith("---") ? "muted" : l.startsWith("+") ? "add" : l.startsWith("-") ? "del" : l.startsWith("@@") ? "muted" : "" }, l || " ")));
}

/* a change a block proposed (a propose line, SPEC §12e): the block and its rung, and each reason with the evidence
   ergostat checked it against */
function proposedBy(e) {
  return h("div", {}, h("span", { class: "part-ref" }, h("span", { class: "muted" }, `${e.made_by_rung || "block"} `), e.made_by),
    e.confidence != null ? h("span", { class: "muted small" }, ` · ${Math.round(e.confidence * 100)}% sure`) : null,
    (e.findings?.answered || []).length ? h("div", { class: "small muted" }, `answers ${e.findings.answered.join(", ")}`) : null);
}
function reasonsView(rs) {
  return h("ul", { class: "plain" }, ...rs.map((r) => h("li", {}, r.says,
    ...(r.verified || r.evidence || []).map((v) => h("div", { class: "small muted" }, v)))));
}

/* one entry of the queue */
function reviewEntry(e, { onDone }) {
  const open = REVIEW_OPEN.has(e.id);
  const body = h("div", { class: "entry-body", hidden: !open });
  const effBox = h("div", { class: "entry-effect" });
  const said = h("p", { class: "small" });
  const toggle = h("button", { class: "ghost", "aria-expanded": open ? "true" : "false", onclick: () => setOpen(body.hidden) }, open ? "Hide effect and diff" : "Effect and diff");
  let loaded = false;
  async function loadEffect() {
    if (loaded || !e.simulable) return;
    loaded = true;
    effBox.replaceChildren(h("p", { class: "muted small" }, "Simulating…"));
    try { effectView(await api("proposal-effect", { ids: e.id }), effBox); }
    catch (err) { effBox.replaceChildren(h("p", { class: "muted small" }, String(err.message || err))); loaded = false; }
  }
  function setOpen(on) {
    body.hidden = !on; toggle.textContent = on ? "Hide effect and diff" : "Effect and diff"; toggle.setAttribute("aria-expanded", on ? "true" : "false");
    if (on) { REVIEW_OPEN.add(e.id); loadEffect(); } else REVIEW_OPEN.delete(e.id);
  }
  if (open) setTimeout(loadEffect, 0);
  // Accept: the diff is shown first, then written only on a second answer, carrying its hash back
  const confirmRow = h("div", { class: "actions confirm", hidden: true });
  const reasonIn = h("input", { type: "text", class: "reason", placeholder: "Why not (optional): remembered with it", "aria-label": "Why not" });
  const dismissRow = h("div", { class: "actions confirm", hidden: true });
  const accept = h("button", { onclick: () => { setOpen(true); confirmRow.hidden = false; dismissRow.hidden = true; } }, "Accept");
  const dismiss = h("button", { class: "ghost", onclick: () => { dismissRow.hidden = false; confirmRow.hidden = true; reasonIn.focus(); } }, "Dismiss");
  async function answer(what) {
    for (const b of body.querySelectorAll("button")) b.disabled = true;
    said.className = "small"; said.textContent = what === "accept" ? "Writing the change…" : "";
    try {
      const got = await apiPost(`proposals/${encodeURIComponent(e.id)}/${what}`, what === "accept" ? { expect: e.diff.hash } : { reason: reasonIn.value });
      said.textContent = what === "accept" ? `Accepted: ${e.diff.files.map((f) => f.file).join(", ")} written.` +
        (got.applied ? ` Fit in total: scaled error ${nm(got.applied.fit_before?.nmse)} → ${nm(got.applied.fit_after?.nmse)}.` : "")
        : "Dismissed: it is not proposed again unchanged.";
      S.graphSig = "";
      REVIEW_OPEN.delete(e.id);
      onDone?.(what);
    } catch (err) {
      said.className = "s-open small"; said.textContent = String(err.message || err);
      for (const b of body.querySelectorAll("button")) b.disabled = false;
    }
  }
  const files = e.diff.files?.length ? e.diff.files.map((f) => f.file).join(", ") : "the model";
  confirmRow.append(h("span", { class: "small" }, `This writes exactly the diff above to ${files}.`), h("button", { onclick: () => answer("accept") }, "Write it"),
    h("button", { class: "ghost", onclick: () => { confirmRow.hidden = true; } }, "Cancel"));
  dismissRow.append(reasonIn, h("button", { onclick: () => answer("dismiss") }, "Dismiss it"), h("button", { class: "ghost", onclick: () => { dismissRow.hidden = true; } }, "Cancel"));
  const where = e.where;
  const canShow = where.select.length && !PANE;
  body.append(
    h("div", { class: "entry-label" }, "Effect"),
    e.simulable ? effBox : h("p", { class: "muted small" }, `Not simulated: ${e.not_simulated || "nothing it changes is replayed"}.`),
    h("div", { class: "entry-label" }, "The change"),
    e.diff.error ? h("p", { class: "s-open small" }, `ergostat cannot make this edit (${e.diff.error}); write it by hand.`) : diffView(e.diff.unified),
    SNAP ? h("p", { class: "muted small" }, `ergostat accept ${e.id} applies it.`)
      : e.diff.error ? null : h("div", { class: "actions" }, accept, dismiss), confirmRow, dismissRow, said);
  return h("article", { class: "entry", "data-id": e.id, "data-kind": e.kind },
    h("h3", {}, e.what),
    h("p", { class: "entry-change" }, op(e.title || "").replaceAll(" * ", " × ")),
    dl([["where", h("div", {}, h("div", {}, ...partWords(where.parts)),
                    where.new.length ? h("div", { class: "small muted" }, "new: ", ...partWords(where.new)) : null,
                    where.gone.length ? h("div", { class: "small muted" }, "removed: ", ...partWords(where.gone)) : null,
                    where.files.length ? h("div", { class: "small muted mono" }, where.files.map((f) => `${f.file}:${f.lines.join(",")}`).join("  ")) : null)],
        ["made by", e.by_block ? proposedBy(e) : e.made_by === "owner" ? "you (a what-if)" : null],
        ["why", e.by_block && (e.reasons || []).length ? reasonsView(e.reasons) : e.why],
        ["judged", e.verdict ? h("div", { class: e.verdict.verdict === "dropped" ? "s-open small" : "small" }, `${e.verdict.verdict === "testing" ? "testing" : e.verdict.verdict}: ${e.verdict.why}`) : null],
        ["how found", h("div", {}, ...howText(e.how))],
        [e.benefit?.better === false ? "effect" : "benefit", benefitRows(e.benefit) ? h("div", {}, ...benefitRows(e.benefit)) : null],
        ["conflicts", e.conflicts.length ? h("div", {}, ...e.conflicts.map((c) => h("div", { class: "s-open small" }, `with ${c.id}: ${c.why}`))) : null]]),
    h("div", { class: "actions" }, canShow ? h("button", { class: "ghost", onclick: () => showOnDiagram(where.select, where.systems || []) }, "Show on diagram") : null, toggle,
      h("span", { class: "muted small mono" }, e.id)),
    body);
}

/* everything waiting, tried together */
async function simulateAll(ids, box, btn) {
  btn.disabled = true;
  box.replaceChildren(h("p", { class: "muted small" }, `Simulating ${ids.length} together…`));
  try {
    const d = await api("proposal-effect", { ids: ids.join(",") });
    const eff = h("div");
    effectView(d, eff);
    box.replaceChildren(h("h3", {}, `All pending, together: ${d.taken?.length || 0} of ${ids.length}`),
      h("p", { class: "muted small" }, "Applied together in the simulator, not in the file; nothing is written until each is accepted."), eff);
  } catch (err) { box.replaceChildren(h("p", { class: "s-open small" }, String(err.message || err))); }
  btn.disabled = false;
}

/* what ergostat can propose now, what it cannot yet, and what it found and could not make */
function proposableView(d) {
  return h("div", {},
    table(["change", "found by"], (d.can || []).map((c) => h("tr", {}, h("td", {}, c.what), h("td", { class: "small" }, c.how))), "can"),
    h("h3", {}, "Not yet"),
    h("ul", { class: "plain" }, ...(d.cannot || []).map((x) => h("li", {}, x))),
    h("p", { class: "muted small" }, "The residual-pattern structure finder, for missing stocks, flows and delays and for replacements, is the next piece of work."),
    ...((d.not_made || []).length ? [h("h3", {}, "Found, and not proposed"),
      table(["change", "why not"], d.not_made.map((x) => h("tr", {}, h("td", {}, x.title), h("td", { class: "small" }, x.why))), "can")] : []));
}

/* ---- the Model page's "What's available": for this project, each loop (identified or not, and what would
   identify it), each parameter to estimate (and whether the record is long enough yet), and where each model
   tool lives; every link opens the part's view and panel (openTool). Loops are analysed one at a time, each
   kept half a minute (the server's own analysis is as old) */
const AVAIL = new Map();
let availBusy = false;
async function availLoops(goals, redraw) {
  if (availBusy) return;
  availBusy = true;
  try {
    for (const g of goals) {
      const got = AVAIL.get(g);
      if (got && Date.now() - got.t < 30000) continue;
      try { AVAIL.set(g, { t: Date.now(), d: await api("loop-control", { goal: g }) }); } catch (e) { AVAIL.set(g, { t: Date.now(), d: null, err: String(e.message || e) }); }
      redraw();
    }
  } finally { availBusy = false; }
}
const toolLink = (text, how, title = null) => h("a", { href: "#", title, onclick: (ev) => { ev.preventDefault(); typeof how === "function" ? how() : openTool(how); } }, text);
const linkList = (xs) => xs.filter(Boolean).flatMap((x, i) => (i ? [", ", x] : [x]));
const isProcess = (goal) => (n) => n.role === "process" && (n.y_of || []).includes(goal);
const isController = (goal) => (n) => n.role === "controller" && n.id?.startsWith("blk:") && (n.loops || []).includes(goal);
const isComparator = (goal) => (n) => n.role === "comparator" && (n.loops || []).includes(goal);

/* a loop's process: what is known of it, in a few words */
function processWord(d) {
  const r = d.identified || {};
  if (d.why) return "none: it closes through queues";
  if (d.declared) return d.declared.identified ? "in the model, identified" : "in the model, declared";
  if (r.found && r.proposable) return "identified: in the queue below";
  if (d.known) return "an integrator, from the model";
  if (r.found) return "a best guess, not proposed";
  return "not identified";
}
/* what would identify it (or, identified, what is offered for its controller) */
function nextWord(d) {
  const r = d.identified || {}, t = d.tuning || {}, c = d.controller || {};
  const props = d.proposals || [];
  if (d.why) return "nothing to identify";
  const out = [];
  if (props.some((x) => x.kind === "step-test")) out.push("a step test is offered: approve it in the process's panel");
  else if (!d.declared && !(r.found && r.proposable)) {
    const why = r.why || [];
    const key = why.find((w) => /^u (stepped|did not move)/.test(w)) || why.find((w) => /readings fitted|spans less/.test(w)) || why[0];
    if (d.known) out.push("its dead time: a step of u, or a step test");
    else if (key) out.push(key.replace(/: nothing to tell its dynamics from$/, ""));
    if (d.step_test_waiting) out.push(`a step test once steady (${d.step_test_waiting.replace(/^waiting for steady operation: /, "")})`);
    else if (d.step_test_refused) out.push(`no step test: ${d.step_test_refused}`);
  }
  if (props.some((x) => x.kind === "tuning")) out.push("a tuning is offered: in the controller's panel");
  else if (d.declared || (r.found && r.proposable)) out.push(c.law ? (t.why ? `tuning: ${t.why}` : "margins and tuning: the controller's panel") : `no tuning: ${c.says || "no linear law"}`);
  return out.join("; ");
}
function loopRows(goals) {
  return goals.map((g) => {
    const got = AVAIL.get(g), d = got?.d;
    const name = h("td", {}, h("b", {}, g));
    if (!got) return h("tr", {}, name, h("td", { class: "muted", colspan: 3 }, "analysing…"));
    if (!d) return h("tr", {}, name, h("td", { class: "muted", colspan: 3 }, got.err || "not a loop of the model's goals"));
    const u = (d.u || "").split(".").slice(1).join("."), y = (d.y || "").split(".").slice(1).join(".");
    const links = d.why ? [toolLink("scope", { view: "blocks", find: isComparator(g) }, "its scope and how it is doing")]
      : [toolLink("process", { view: "blocks", find: isProcess(g), goal: g }, "identification, step response, Bode, step tests"),
         toolLink("controller", { view: "blocks", find: isController(g), goal: g }, "margins, closed-loop step and Bode, tuning"),
         toolLink("scope", { view: "blocks", find: isComparator(g) }, "how it is doing: Harris index, oscillation, settling")];
    return h("tr", {}, name, h("td", { class: "small" }, u && y ? `${u} → ${y}` : "", h("div", {}, processWord(d))),
      h("td", { class: "small" }, nextWord(d)), h("td", { class: "small nowrap" }, ...linkList(links)));
  });
}
function paramRows(d) {
  const rd = d.readiness || {}, np = Object.entries(d.not_proposed || {});
  const queued = new Set((d.proposals || []).filter((x) => x.kind === "parameter").flatMap((x) => Object.keys(x.parameters || {})));
  return (d.to_estimate || []).map((n) => {
    const r = rd[n] || {};
    const parts = (r.parts || []).map((ref) => toolLink(ref.split(".").slice(1).join("."), { view: "dynamics", part: ref },
      "its equation, the what-if and the calibrations"));
    const short = [r.needs != null && r.span < r.needs ? `${dur(r.span)} of the ${dur(r.needs)} it needs` : null,
                   r.points != null && r.points < r.points_needed ? `${r.points} of ${r.points_needed} points` : null].filter(Boolean);
    const record = r.span == null ? "" : short.length ? short.join(", ") : "long enough";
    const why = np.filter(([k]) => k === n || k.startsWith(`${n} (`));
    const now = queued.has(n) ? "proposed: in the queue below"
      : why.length ? `not proposed: ${why[0][1]}`
      : d.estimated_at ? "calibrated: no change to propose" : "not calibrated yet: Calibrate, below";
    return h("tr", {}, h("td", {}, h("b", {}, n)), h("td", { class: "small" }, ...linkList(parts)),
      h("td", { class: "small" }, record), h("td", { class: "small" }, now));
  });
}
function availableView(d, box) {
  const goals = Object.keys(S.status?.loops || {});
  const draw = () => {
    if (!box.isConnected) return;
    const modelled = (d.stocks || [])[0];
    const eqParts = [...new Set(Object.values(d.readiness || {}).flatMap((r) => r.parts || []))].slice(0, 3);
    const findings = (S.status?.check || []).length;
    const queues = goals.filter((g) => AVAIL.get(g)?.d?.why), one = goals.filter((g) => !queues.includes(g));
    const tools = [
      ["replay, projection, fan", modelled ? h("span", {}, "a modelled part's chart: ", toolLink(modelled.name, { view: "dynamics", part: modelled.ref })) : "no stock is moved by an equation yet"],
      ["what-if, calibrations", eqParts.length ? h("span", {}, "a part with an equation: ", ...linkList(eqParts.map((r) => toolLink(r.split(".").slice(1).join("."), { view: "dynamics", part: r }))))
        : "no equation uses a parameter marked estimate: true"],
      ["loop dominance", modelled || goals.length ? h("span", {}, "a feedback loop's panel: ", toolLink(modelled?.name || goals[0], { view: "dynamics", causal: modelled?.name || goals[0] })) : "no feedback loop"],
      ["extreme conditions, signs", h("span", {}, h("a", { href: "/check" }, "Check"), findings ? `: ${findings} found` : ": nothing found")],
      ["review queue, calibrate", h("a", { href: "#", onclick: (ev) => { ev.preventDefault(); document.getElementById("review-queue")?.scrollIntoView(); } }, "below")],
      ["fit, residuals, history", h("a", { href: "#", onclick: (ev) => { ev.preventDefault(); document.getElementById("model-fit")?.scrollIntoView(); } }, "below")],
    ];
    patch(box,
      h("h3", {}, "Loops"),
      goals.length ? table(["loop", "u \u2192 y, process", "what would identify or tune it", "panels"], loopRows(one), "avail") : h("p", { class: "muted" }, "No goal: no loop to identify."),
      queues.length ? h("p", { class: "small muted" }, "Closing through queues, with no one process to identify: ",
        ...linkList(queues.map((g) => toolLink(g, { view: "blocks", find: isComparator(g) }, "its scope and how it is doing"))), ".") : null,
      h("h3", {}, "Parameters to estimate"),
      (d.to_estimate || []).length ? table(["parameter", "in", "record", "estimate"], paramRows(d), "avail")
        : h("p", { class: "muted small" }, "None is marked estimate: true: nothing to calibrate."),
      h("h3", {}, "Tools"),
      table(["tool", "where"], tools.map(([k, v]) => h("tr", {}, h("td", {}, k), h("td", { class: "small" }, v))), "avail"));
  };
  draw();
  availLoops(goals, draw);
}

/* a fix's or a change's impact (SPEC §12n), on its item's page: worked out once, apart from the page's refresh; the
   sentence, the stocks without the fix and with it at the best time, the cost by rollout time, each goal's chance of
   being off, and the change-management fields */
function impactBox(id) {
  const box = h("div", { class: "impact" }, h("p", { class: "muted" }, "Working out its impact…"));
  (async () => {
    let d = null;
    for (let i = 0; i < 90; i++) {                  // a minute and a half at most
      try { d = await api("impact", { item: id }); } catch (e) { d = { error: String(e.message || e) }; }
      if (!d.working) break;
      await new Promise((r) => setTimeout(r, 1000));
    }
    box.replaceChildren(...impactView(d || { error: "not worked out in time" }));
  })();
  return box;
}
function impactView(d) {
  if (d.error) return [h("p", { class: "muted small" }, d.error)];
  const group = chartGroup("impact"), at = d.at, ro = d.rollout, f = d.fields, t = f.touches;
  const end = d.ptimes.length ? d.ptimes[d.ptimes.length - 1] : at;
  const stocks = d.charts.map((c) => lineChart({ group, name: c.name, role: PART_WORDS[c.kind], unit: c.unit, per: c.per, times: d.times,
    values: c.measured.length ? c.measured : d.times.map(() => null), since: d.times[0], until: at, projection: c.without, ptimes: d.ptimes,
    whatifProjection: c.with, goal: c.goal, height: 56 }));
  const opts = ro ? ro.options : [];
  const cost = opts.length > 1 ? lineChart({ group: chartGroup("impact-cost"), name: "cost by rollout time", unit: "h", times: opts.map((o) => o.at),
    values: opts.map((o) => o.cost), replay: opts.map((o) => o.hours_off), since: opts[0].at, until: opts[opts.length - 1].at, height: 64, xAxis: true, zero: true }) : null;
  const risks = Object.entries(d.goals).filter(([, g]) => g.p_off).map(([n, g]) => lineChart({ group: chartGroup("impact-risk"), name: `${n}: chance off`,
    times: d.ptimes, values: g.p_off, since: d.ptimes[0], until: end, height: 48, yRange: () => [0, 1], zero: true }));
  const goalRows = Object.entries(d.goals).map(([n, g]) => h("div", {}, h("b", {}, n), ` (${g.of} ${g.hold}): `,
    g.off_at == null ? "holds without the fix" : `off at +${dur(Math.max(0, g.off_at - at))} without the fix, ${dur(g.hours_off * 3600)} off`,
    g.hours_off_fixed_now != null ? `; fixed now, ${g.hours_off_fixed_now ? dur(g.hours_off_fixed_now * 3600) + " off" : "it holds"}` : "",
    g.said ? h("div", { class: "muted small" }, g.said) : null));
  return [h("p", { class: "predicts" }, d.said),
    stocks.length ? h("div", { class: "review-charts" }, ...stocks) : null,
    stocks.length ? h("p", { class: "muted small" }, `Measured, solid; past now, ${d.kind === "change" ? "the model as it is, dashed; with the change, in blue" : "without the fix, dashed; with it at the best time, in blue"}, over ${dur(d.horizon)} with the loops running.`) : null,
    cost ? h("div", { class: "review-charts" }, cost) : null,
    cost ? h("p", { class: "muted small" }, `Each rollout time's cost: the goals' hours off (dashed) plus ${dur(ro.penalty * 3600)} for the busiest hour of the day. ${ro.said}.`) : null,
    risks.length ? h("div", { class: "review-charts" }, ...risks) : null,
    dl([["goals", goalRows.length ? h("div", {}, ...goalRows) : null],
        ["touches", [t.blocks.length ? `blocks ${t.blocks.join(", ")}` : "", t.goals.length ? `goals ${t.goals.join(", ")}` : "",
                     t.commands.length ? `commands ${t.commands.join(", ")}` : ""].filter(Boolean).join("; ") || "nothing else"],
        ["writes", f.read_only ? "nothing: read-only" : t.actions.map((a) => `${a.name} (${a.gate})`).join(", ")],
        ["rollback", f.rollback.said], ["risk", `${f.risk.level}: ${f.risk.why.join("; ")}`], ["confidence", f.confidence.said],
        ["notes", (d.notes || []).length || d.stopped ? h("div", {}, ...[...d.notes, d.stopped].filter(Boolean).map((x) => h("div", { class: "small muted" }, x))) : null]])];
}
