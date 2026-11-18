/* the model's numbers in its panels (SPEC §7b): an equation drawn in MathML, each parameter with its
   value and where it comes from (declared, estimated, not known), and a proposal with Accept */
"use strict";

const MATH = "http://www.w3.org/1998/Math/MathML";
function m(tag, attrs = {}, ...kids) {
  const el = document.createElementNS(MATH, tag);
  for (const [k, v] of Object.entries(attrs || {})) if (v != null && v !== false) el.setAttribute(k, v);
  for (const kid of kids.flat(Infinity)) if (kid != null && kid !== false) el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  return el;
}
const PREC = { "+": 1, "-": 1, "*": 2, "/": 3, "^": 4, neg: 2 };
const FN_WORDS = { MIN: "min", MAX: "max", LN: "ln" };

/* the tree spec/equation.py gives (tree_json), as MathML: a sum's terms, × between factors, a
   quotient as a fraction, a power as a superscript, a part by its name (its kind on hover) */
function mathTree(n, outer = 0) {
  const paren = (inner, need) => (need ? m("mrow", {}, m("mo", {}, "("), inner, m("mo", {}, ")")) : inner);
  if (n.num != null) return m("mn", {}, fmt(n.num).replace("−", "-") === String(n.num) ? fmt(n.num) : fmt(n.num));
  if (n.par) return m("mi", { class: "eq-par", title: "a parameter" }, n.par);
  if (n.ref) return m("mi", { class: "eq-ref", title: `${n.kind}.${n.name}` }, n.name);
  if (n.op === "neg") return paren(m("mrow", {}, m("mo", {}, "−"), mathTree(n.args[0], PREC.neg + 1)), outer > PREC.neg);
  if (n.op === "/") return m("mfrac", {}, mathTree(n.args[0]), mathTree(n.args[1]));
  if (n.op === "^") return m("msup", {}, mathTree(n.args[0], 5), mathTree(n.args[1]));
  if (n.op) {
    const p = PREC[n.op], sym = { "+": "+", "-": "−", "*": "×" }[n.op];
    const right = n.op === "-" || n.op === "*" ? p + 1 : p;
    return paren(m("mrow", {}, mathTree(n.args[0], p), m("mo", {}, sym), mathTree(n.args[1], right)), outer > p);
  }
  if (n.fn === "ABS") return m("mrow", {}, m("mo", {}, "|"), mathTree(n.args[0]), m("mo", {}, "|"));
  if (n.fn === "SQRT") return m("msqrt", {}, mathTree(n.args[0]));
  if (n.fn === "EXP") return m("msup", {}, m("mi", {}, "e"), mathTree(n.args[0]));
  const args = n.args.flatMap((a, i) => [i ? m("mo", { separator: "true" }, ",") : null, mathTree(a)]);
  return m("mrow", {}, m("mi", { class: n.lookup ? "eq-par" : "eq-fn" }, FN_WORDS[n.fn] || n.fn), m("mo", {}, "("), args, m("mo", {}, ")"));
}
function equationMath(name, tree, broken = false) {
  const lhs = [m("mi", { class: "eq-ref" }, name), m("mo", {}, "=")];
  const split = broken && splitTerms(tree);
  if (!split) return m("math", { class: "eq", displaystyle: "true" }, m("mrow", {}, lhs, mathTree(tree)));
  // too wide for the panel: one term a line, the sum's signs leading, as a textbook sets a long equation
  const { prefix, terms, suffix } = split;
  const rows = terms.map(({ sign, node }, i) => m("mtr", {}, m("mtd", { columnalign: "left" }, m("mrow", {},
    i === 0 ? [...lhs, ...prefix] : [m("mspace", { width: "2em" }), m("mo", {}, sign)],
    mathTree(node, sign === "\u2212" ? 2 : 1), i === terms.length - 1 ? suffix : null))));
  return m("math", { class: "eq", displaystyle: "true" }, m("mtable", { columnalign: "left" }, rows));
}
/* where a long equation breaks: the terms of its sum, or of the sum one factor holds (k × (a + b + c)) */
function splitTerms(tree) {
  const flat = (n, sign = "+") => (n.op === "+" || n.op === "-")
    ? [...flat(n.args[0], sign), ...flat(n.args[1], n.op === "-" ? "\u2212" : "+")] : [{ sign, node: n }];
  if (tree.op === "+" || tree.op === "-") return { prefix: [], terms: flat(tree), suffix: [] };
  if (tree.op === "*" && (tree.args[1].op === "+" || tree.args[1].op === "-"))
    return { prefix: [mathTree(tree.args[0], 2), m("mo", {}, "\u00d7"), m("mo", {}, "(")], terms: flat(tree.args[1]), suffix: [m("mo", {}, ")")] };
  return null;
}
/* the equation in its box, broken into lines when it is wider than the panel */
function equationBox(name, tree) {
  const box = h("div", { class: "eq-box" }, equationMath(name, tree));
  const ro = new ResizeObserver(() => {
    if (!box.clientWidth) return;
    ro.disconnect();
    if (box.scrollWidth > box.clientWidth + 1 && splitTerms(tree)) box.replaceChildren(equationMath(name, tree, true));
  });
  ro.observe(box);
  return box;
}

/* a parameter's number with its unit; a duration as a duration (it is kept in hours) */
const amount = (p, v, unit = true) => (p.duration ? dur(v * 3600) : `${fmt(v)}${unit && p.unit ? " " + p.unit : ""}`);
/* where a parameter's number comes from, in words: declared or not known, and what it might be; its
   calibrations are a table of their own beneath (calibrationTable) */
function provenance(p) {
  const bits = [];
  if (p.table) bits.push("a lookup, declared");
  else if (p.value != null) bits.push("declared");
  else bits.push(p.estimate ? "not known yet: to be estimated" : "not known yet");
  if (p.range) bits.push(`might be ${amount(p, p.range[0], false)} to ${amount(p, p.range[1], false)} (its range)`);
  const n = (p.calibrated || []).length;
  if (n) bits.push(`${n} calibration${n > 1 ? "s" : ""} below`);
  else if (p.estimate_note) bits.push(p.estimate_note);
  else if (p.estimate && p.value != null) bits.push("to estimate: not calibrated yet (the Model page's Calibrate)");
  return bits.join("; ");
}
/* each calibration of a parameter side by side (Oliva 2003): which, its estimate ± one standard error (marked
   when it is outside the range or at its end), from how many points (and how many independent), and whether
   it is proposed or why not */
function calibrationTable(params) {
  const rows = (params || []).flatMap((p) => (p.calibrated || []).map((c) => ({ p, c })));
  if (!rows.length) return null;
  const words = { parts: "each part alone", whole: "the whole model" };
  return h("table", { class: "params calibrations" },
    h("tr", {}, h("th", {}, "calibrated"), h("th", { class: "num" }, "estimate"), h("th", { class: "num" }, "n"), h("th", {}, "")),
    rows.map(({ p, c }) => h("tr", {},
      h("td", {}, h("b", {}, p.name), h("span", { class: "muted" }, ` ${c.scope?.startsWith("system:") ? `system ${c.scope.slice(7)} alone` : c.scope === "parts" ? words.parts : c.scope_words || words[c.scope] || ""}`)),
      h("td", { class: "num nowrap" }, c.value != null ? `${amount(p, c.value, false)}${c.se != null ? ` \u00b1 ${amount(p, c.se, false)}` : ""}` : "\u2013",
        c.outside_range ? h("span", { class: "s-open" }, " outside its range") : c.at_range ? h("span", { class: "s-open" }, ` at its ${c.at_range} end`) : null),
      h("td", { class: "num nowrap" }, c.n != null ? `${c.n}${c.n_eff != null && c.n_eff < c.n * 0.9 ? ` (${Math.round(c.n_eff)})` : ""}` : ""),
      h("td", { class: "muted small" }, c.value == null ? (c.note || "no value") : c.note ? `not proposed: ${c.note}` : `supported${c.when ? `, ${ago(c.when)}` : ""}`))));
}
/* a value as the owner would type it: a time in seconds (read as a duration), else the number */
const typed = (p, v) => (v == null ? "" : p.duration ? `${+(v * 3600).toPrecision(4)}s` : String(+v.toPrecision(6)));
function parameterTable(params) {
  if (!params?.length) return null;
  const cell = (p) => {
    if (p.table) return `${p.table.length} points`;
    if (SNAP || p.value == null) return p.value != null ? amount(p, p.value) : "?";
    // what if it were another value? typed here, drawn on every chart, kept nowhere unless proposed and accepted
    const input = h("input", { class: "whatif-in num", value: S.whatif?.[p.name] ?? typed(p, p.value), size: 7, "aria-label": `what if ${p.name} were`,
      "data-name": p.name, "data-declared": typed(p, p.value),
      title: `Type another value to see what the model does with it (${p.duration ? "a duration, like 40s or 2m; a bare number is in seconds, as shown" : p.unit || "a number"}); nothing is saved` });
    input.addEventListener("change", () => {
      let v = input.value.trim();
      if (p.duration && /^[+\-\u2212]?(\d+\.?\d*|\.\d+)$/.test(v)) input.value = v = `${v}s`;   // in the unit it is shown in
      setWhatif(p.name, v === typed(p, p.value) ? null : v);
    });
    return h("span", { class: "nowrap" }, input, p.duration || !p.unit ? null : h("span", { class: "muted" }, ` ${p.unit}`));
  };
  return h("table", { class: "params" }, h("tr", {}, h("th", {}, "parameter"), h("th", { class: "num" }, "value"), h("th", {}, "from")),
    params.map((p) => h("tr", {}, h("td", { title: p.description || null }, p.name),
      h("td", { class: "num nowrap" }, cell(p)),
      h("td", { class: "muted small" }, provenance(p)))));
}
/* the what-ifs tried (on this panel's parameters, and any others the charts draw with them): what they are, their
   fit on the record before anything is stored (each stock it moves, and the payoff), and the owner's two answers:
   propose them, together, as the charts drew them, or put them back; redrawn whenever one changes */
function whatifBox(params) {
  const box = h("div", { class: "whatif" });
  const mine = new Set((params || []).filter((p) => !p.table).map((p) => p.name));
  box.redraw = () => {
    const tried = Object.entries(S.whatif || {});
    if (!tried.some(([k]) => mine.has(k)) || SNAP) { box.replaceChildren(); return; }
    const said = h("p", { class: "small" });
    const out = h("div");
    const fit = h("div", { class: "small muted" }, "Fitting it to the record\u2026");
    const propose = h("button", { onclick: async (ev) => {
      ev.target.disabled = true; said.textContent = "Fitting it to the record\u2026";
      try { const x = await apiPost("propose", whatifParams()); said.textContent = ""; out.replaceChildren(proposalBlock(x, { onDone: () => { for (const [k] of tried) setWhatif(k, null); } })); }
      catch (e) { said.className = "s-open small"; said.textContent = String(e.message || e); }
      ev.target.disabled = false;
    } }, tried.length > 1 ? "Propose these" : "Propose it");
    box.replaceChildren(h("p", { class: "small" }, "What if ", tried.map(([k, v], i) => [i ? " and " : "", h("b", {}, k), ` were ${v}`]),
      ": drawn in blue on the charts above. Nothing is saved."), fit,
      h("div", { class: "actions" }, propose,
        h("button", { class: "ghost", onclick: () => { for (const [k] of tried) setWhatif(k, null); for (const i of document.querySelectorAll(".whatif-in")) i.value = i.dataset.declared; } }, "Put it back")),
      said, out);
    api("whatif-fit", whatifParams()).then((d) => {
      if (d.error) { fit.className = "s-open small"; fit.textContent = d.error; propose.disabled = true; return; }
      const rows = (d.touched || []).map((r) => {
        const fb = d.fit_before?.stocks?.[r] || d.fit_before?.equations?.[r], fa = d.fit_after?.stocks?.[r] || d.fit_after?.equations?.[r];
        const t = beforeAfter(fb, fa);
        return t !== "\u2013" ? [r.split(".").slice(1).join("."), t] : null;
      }).filter(Boolean);
      fit.className = "small";
      fit.replaceChildren(dl([...rows, ["fit, in total", payoffText(d.fit_before?.total, d.fit_after?.total)]]),
        ...(d.refused || []).map((w) => h("p", { class: "s-open small" }, `Not to be proposed: ${w}.`)),
        ...(d.warnings || []).map((w) => h("p", { class: "s-open small" }, `${w[0].toUpperCase()}${w.slice(1)}.`)));
      if (d.refused?.length) propose.disabled = true;
    }).catch((e) => { fit.textContent = String(e.message || e); });
  };
  box.redraw();
  return box;
}

/* what the record says of a part (the part API's findings): not exercised, over which span, and why; or nothing */
function findingsNote(d) {
  const xs = d?.findings || [];
  return xs.length ? h("div", { class: "numbers" }, xs.map((x) => h("p", { class: "s-open small" }, x.message))) : null;
}

/* a valve's or an auxiliary's numbers: its equation, its parameters, how its replay fits, its proposals */
function equationSection(name, nb, { said = "", exogenous = false } = {}) {
  if (!nb) return null;
  const out = [];
  if (!nb.equation_tree) out.push(h("p", { class: "muted small" }, noEquationWords(said, exogenous)));
  if (nb.equation_tree) {
    out.push(h("h3", {}, "Equation"), equationBox(name, nb.equation_tree), parameterTable(nb.parameters), whatifBox(nb.parameters),
      calibrationTable(nb.parameters));
    const ps = (nb.parameters || []).filter((p) => !p.table);
    if (ps.length && !ps.some((p) => p.estimate || p.range))
      out.push(h("p", { class: "muted small" }, "No calibration and no fan: none of its parameters is marked estimate: true or has a range."));
    const notes = [];
    if (nb.unit_problems?.length) notes.push(h("p", { class: "s-open small" }, op(nb.unit_problems.join("; "))));
    else if (nb.equation_ok === false) notes.push(h("p", { class: "s-open small" }, `It comes out in ${nb.equation_unit}: its units do not agree (ergostat check says how).`));
    if (nb.left_out) notes.push(h("p", { class: "muted small" }, nb.left_out.split(": ").slice(1).join(": ")));
    if (nb.invalid?.length) notes.push(h("p", { class: "s-off small" }, `The replay is not valid: ${nb.invalid.join("; ")}.`));
    if (nb.judged_by_stock) {
      const st = nb.judged_by_stock.split(".").slice(1).join(".");
      notes.push(h("p", { class: "muted small" }, `Measured from its stock's changes, so judged by ${st}'s replay` +
        (nb.stock_fit ? `: ${fitWords(nb.stock_fit)}.` : ".")));
    } else {
      if (nb.partial) notes.push(h("p", { class: "muted small" }, `Inputs as measured (the partial-model test): ${fitWords(nb.partial)}.`));
      if (nb.replay) notes.push(h("p", { class: "muted small" }, `Replayed, every stock integrated: ${fitWords(nb.replay)}.`));
      if ((nb.partial || nb.replay) && nb.fit_span) notes.push(h("p", { class: "muted small" }, `Over the last ${dur(nb.fit_span)} of record.`));
      else if (nb.replayed && !nb.left_out) notes.push(h("p", { class: "muted small" }, "Not compared with its readings yet: too little record, or nothing measures it."));
    }
    out.push(...notes);
  }
  for (const x of nb.proposals || []) out.push(proposalBlock(x));
  return out.length ? h("div", { class: "numbers" }, out) : null;
}

/* why a valve or an auxiliary has no equation, what-if or calibration in its panel, and what would give it one
   (said: the model's own words for its rate, dynamics.equation) */
function noEquationWords(said, exogenous) {
  const setter = /^set by the decision ([^:]+)/.exec(said || "");
  if (setter) return `No equation, what-if or calibration: ${setter[1]} sets it, and the replay takes what it moved as measured. Its loop's process, margins and tuning are in the blocks view.`;
  if (exogenous) return "No equation, what-if or calibration: it comes from outside the model (exogenous), and the replay takes it as measured.";
  if (/declared cause/.test(said || "")) return "No equation yet, so no what-if or calibration: the Model page's Calibrate proposes one from its measured rate and its declared causes, when they explain half its variation; or write equation:.";
  return "No equation, so no replay, what-if or calibration: write equation: (or give it causes with driven-by:, for Calibrate to propose one).";
}

/* one series' fit, in a line: its R², its error (MAPE, or as a share of the readings' mean or range),
   what a large error says; or why there is too little to judge */
function fitWords(s) {
  if (s.too_little) return `too little record (${s.too_little})`;
  if (s.exact) return `no error (${s.n} points)`;
  const err = s.mape != null ? `MAPE ${Math.round(s.mape * 100)}%` : s.error_share != null ? `error ${Math.round(s.error_share * 100)}% of the ${s.error_of}` : "";
  return [s.r2 != null ? `R\u00b2 ${s.r2.toFixed(2)}` : "", err, s.says || "", `${s.n} points`].filter(Boolean).join(", ");
}

/* a proposal: what it changes, why, the fit before and after, the edit, and the owner's two answers */
const r2Text = (t) => (t?.r2 != null ? t.r2.toFixed(2) : "–");
const mapeText = (t) => (t?.mape != null ? `${Math.round(t.mape * 100)}%` : t?.error_share != null ? `${Math.round(t.error_share * 100)}% of ${t.error_of}` : "–");
function proposalBlock(x, { onDone = null } = {}) {
  const b = x.fit_before?.total, a = x.fit_after?.total;
  const said = h("p", { class: "small" });
  const accept = h("button", { onclick: () => answer("accept") }, "Accept");
  const dismiss = h("button", { class: "ghost", onclick: () => answer("dismiss") }, "Dismiss");
  async function answer(what) {
    accept.disabled = dismiss.disabled = true;
    said.textContent = what === "accept" ? "Applying the edit…" : "";
    try {
      const got = await apiPost(`proposals/${encodeURIComponent(x.id)}/${what}`);
      said.className = "small";
      said.textContent = what === "accept"
        ? `Accepted: ${(got.edit?.files || []).map((f) => Path(f.file)).join(", ")} changed; fit in total, ${payoffText(got.applied?.fit_before, got.applied?.fit_after)}.`
        : "Dismissed: it is not proposed again for this model.";
      S.graphSig = "";                                    // the model changed: draw it again
      onDone?.(what);
    } catch (e) {
      said.className = "s-open small";
      said.textContent = String(e.message || e);
      accept.disabled = dismiss.disabled = false;
    }
  }
  return h("div", { class: "proposal" },
    h("div", { class: "proposal-title" }, h("span", { class: "muted small" }, x.kind === "parameter"
      ? (x.scope === "what-if" ? "Your value, proposed" : x.scope && x.scope !== "parts" ? `Proposed value, calibrated on ${x.scope_words}` : "Proposed value") : "Proposed equation"),
      h("div", {}, op(x.title).replaceAll(" * ", " \u00d7 "))),
    h("p", { class: "muted small" }, x.reason),
    dl([...(x.objective ? [["fitted to", objectiveText(x.objective)]] : []), ...touchedFits(x), ["fit, in total", b || a ? payoffText(b, a) : null]]),
    x.edit?.diff ? h("pre", { class: "diff" }, x.edit.diff.split("\n").map((l) => h("div", { class: l.startsWith("+") ? "add" : l.startsWith("-") ? "del" : "muted" }, l)))
      : h("p", { class: "s-open small" }, `ergostat cannot make this edit (${x.edit?.error}); write it by hand.`),
    SNAP ? h("p", { class: "muted small" }, `ergostat accept ${x.id} applies it.`) : h("div", { class: "actions" }, accept, dismiss),
    said);
}
const Path = (f) => String(f || "").split("/").pop();
/* what a proposal was fitted to, each before and after: the parts it moves */
function touchedFits(x) {
  return (x.touched || []).map((r) => {
    const fb = x.fit_before?.stocks?.[r] || x.fit_before?.equations?.[r], fa = x.fit_after?.stocks?.[r] || x.fit_after?.equations?.[r];
    const said = beforeAfter(fb, fa);
    return said !== "\u2013" ? [r.split(".").slice(1).join("."), said] : null;
  }).filter(Boolean);
}
/* the weighted error the estimate minimised, before and after, on the record fitted and the record held out */
function objectiveText(o) {
  const f = (v) => (v == null ? "\u2013" : fmt(v));
  return `weighted error ${f(o.before)} \u2192 ${f(o.after)}` + (o.held_before != null ? `; held out ${f(o.held_before)} \u2192 ${f(o.held_after)}` : "");
}
/* the total as a calibration judges it: the payoff, each stock's squared error over its own size, averaged
   (lower is better; R² and MAPE are per stock, above it) */
function payoffText(b, a) {
  const f = (t) => (t?.nmse != null ? fmt(t.nmse) : "\u2013");
  return b?.nmse != null || a?.nmse != null ? `scaled error ${f(b)} \u2192 ${f(a)}` : "\u2013";
}
/* R² and MAPE, before and after, leaving out what neither has */
function beforeAfter(b, a) {
  return [b?.r2 != null || a?.r2 != null ? `R\u00b2 ${r2Text(b)} \u2192 ${r2Text(a)}` : "",
          b?.mape != null || a?.mape != null ? `MAPE ${mapeText(b)} \u2192 ${mapeText(a)}` : ""].filter(Boolean).join(", ") || "\u2013";
}
