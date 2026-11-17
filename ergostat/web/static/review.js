/* the review queue on the Fit page: every change to the model waiting for the owner, read like a pull request
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
  location.hash = `#/diagram?${q}`;
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
  if (b.nmse_before != null || b.nmse_after != null) rows.push(h("div", {}, `scaled error ${nm(b.nmse_before)} → ${nm(b.nmse_after)}`,
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
    charts.length ? h("div", { class: "review-charts" }, ...charts) : h("p", { class: "muted small" }, "Nothing it changes is replayed."),
    charts.length ? h("p", { class: "muted small" }, `Measured, solid; the model as it is, dashed; with the change, in blue; past now, the projections over ${dur(d.horizon || 0)}.`) : null,
    d.valid === false ? h("p", { class: "s-open small" }, `With it the replay is not valid: ${(d.invalid || []).join("; ")}.`) : null,
    dl([["fit now", fb || fa ? `scaled error ${nm(fb?.nmse)} → ${nm(fa?.nmse)}` : null],
        ["ahead", (d.operational || []).length ? h("div", {}, ...d.operational.map((x) => h("div", {}, x))) : null],
        ["leverage", (d.leverage || []).length ? h("div", {}, ...d.leverage.map((x) => h("div", {}, x))) : null],
        ["not drawn", (d.undrawn || []).length ? h("div", {}, ...d.undrawn.map((x) => h("div", { class: "small" }, x))) : null],
        ["left out", (d.left || []).length ? h("div", {}, ...d.left.map((x) => h("div", { class: "small" }, h("span", { class: "mono" }, x.id), ` ${x.why}`))) : null]])].filter(Boolean));
}

function diffView(u) {
  return h("pre", { class: "diff" }, String(u || "").replace(/\n$/, "").split("\n").map((l) =>
    h("div", { class: l.startsWith("+++") || l.startsWith("---") ? "muted" : l.startsWith("+") ? "add" : l.startsWith("-") ? "del" : l.startsWith("@@") ? "muted" : "" }, l || " ")));
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
        ["why", e.why],
        ["how found", h("div", {}, ...howText(e.how))],
        ["benefit", benefitRows(e.benefit) ? h("div", {}, ...benefitRows(e.benefit)) : null],
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
