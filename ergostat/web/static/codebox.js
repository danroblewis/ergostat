/* What the query boxes of promql.js and sql.js share as a code editor: a gutter of line numbers beside the text, and
   the bracket at the caret drawn with its match (or as unmatched). The text is not wrapped, so a line of text is a line
   of the gutter. Plain JavaScript, no library and no build step. */
(function () {
  "use strict";
  const OPEN = { "(": ")", "[": "]", "{": "}" }, SHUT = { ")": "(", "]": "[", "}": "{" };

  /* the tokens' indices of the bracket beside the caret ``at`` (the one just before it first) and of its match:
     {at, match} (match -1 when it has none), or null when no bracket is beside the caret. Brackets in strings and
     comments are tokens of their own kind, so they are not counted. */
  function brackets(ts, at) {
    const isB = t => t && t.kind === "punct" && (OPEN[t.w] || SHUT[t.w]);
    let i = ts.findIndex(t => t.e === at && isB(t));
    if (i < 0) i = ts.findIndex(t => t.s === at && isB(t));
    if (i < 0) return null;
    const w = ts[i].w, step = OPEN[w] ? 1 : -1, other = OPEN[w] || SHUT[w];
    for (let j = i + step, depth = 0; j >= 0 && j < ts.length; j += step) {
      if (ts[j].kind !== "punct") continue;
      if (ts[j].w === w) depth++;
      else if (ts[j].w === other && depth-- === 0) return { at: i, match: j };
    }
    return { at: i, match: -1 };
  }

  /* the class a token's span gets for the brackets ``b`` (from brackets()) */
  function bracketClass(b, i) {
    if (!b || (i !== b.at && i !== b.match)) return "";
    return b.match < 0 ? " pq-nomatch" : " pq-match";
  }

  /* the gutter of ``area``: ``draw()`` numbers its lines and keeps the gutter scrolled with the text */
  function gutter(area) {
    const el = h("pre", { class: "pq-lines", "aria-hidden": "true" });
    let n = 0;
    return {
      el,
      draw() {
        const lines = area.value.split("\n").length;
        if (lines !== n) { n = lines; el.textContent = Array.from({ length: n }, (_, i) => i + 1).join("\n") + "\n"; }
        el.scrollTop = area.scrollTop;
      },
    };
  }

  window.codeBox = { brackets, bracketClass, gutter };
})();
