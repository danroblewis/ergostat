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
/* where a parameter's number comes from, in words */
function provenance(p) {
  const bits = [];
  if (p.table) bits.push("a lookup, declared");
  else if (p.value != null) bits.push("declared");
  else bits.push(p.estimate ? "not known yet: to be estimated" : "not known yet");
  const e = p.estimated;
  if (e) bits.push(`estimated ${amount(p, e.value, false)}${e.se != null ? ` \u00b1 ${amount(p, e.se, false)}` : ""} (${e.n} points, ${ago(e.when)})`);
  if (p.estimate_note) bits.push(e ? `not proposed: ${p.estimate_note}` : p.estimate_note);
  return bits.join("; ");
}
function parameterTable(params) {
  if (!params?.length) return null;
  return h("table", { class: "params" }, h("tr", {}, h("th", {}, "parameter"), h("th", { class: "num" }, "value"), h("th", {}, "from")),
    params.map((p) => h("tr", {}, h("td", { title: p.description || null }, p.name),
      h("td", { class: "num nowrap" }, p.table ? `${p.table.length} points` : p.value != null ? amount(p, p.value) : "?"),
      h("td", { class: "muted small" }, provenance(p)))));
}

/* a valve's or an auxiliary's numbers: its equation, its parameters, how its replay fits, its proposals */
function equationSection(name, nb) {
  if (!nb) return null;
  const out = [];
  if (nb.equation_tree) {
    out.push(h("h3", {}, "Equation"), equationBox(name, nb.equation_tree), parameterTable(nb.parameters));
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
        ? `Accepted: ${(got.edit?.files || []).map((f) => Path(f.file)).join(", ")} changed; fit in total R² ${r2Text(got.applied?.fit_before)} → ${r2Text(got.applied?.fit_after)}.`
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
    h("div", { class: "proposal-title" }, h("span", { class: "muted small" }, x.kind === "parameter" ? "Proposed value" : "Proposed equation"), h("div", {}, op(x.title).replaceAll(" * ", " \u00d7 "))),
    h("p", { class: "muted small" }, x.reason),
    dl([...(x.objective ? [["fitted to", objectiveText(x.objective)]] : []), ...touchedFits(x), ["fit, in total", b || a ? beforeAfter(b, a) : null]]),
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
/* R² and MAPE, before and after, leaving out what neither has */
function beforeAfter(b, a) {
  return [b?.r2 != null || a?.r2 != null ? `R\u00b2 ${r2Text(b)} \u2192 ${r2Text(a)}` : "",
          b?.mape != null || a?.mape != null ? `MAPE ${mapeText(b)} \u2192 ${mapeText(a)}` : ""].filter(Boolean).join(", ") || "\u2013";
}
