/* The query box of a PromQL data source: the text highlighted as it is written, completed from PromQL's own words
   (functions, aggregations, keywords) and from the source's names (metrics, labels, a label's values), which the server
   asks of the source's metadata (GET /api/query/suggest, bounded there). Ctrl+Enter (or Cmd+Enter) runs the query; where
   the source says the text is wrong is marked in it. The panel editor picks an editor by its source's language
   (window.queryEditors); a language with none gets a plain text box. Plain JavaScript, no library and no build step. */
(function () {
  "use strict";
  const FUNCTIONS = ("abs absent absent_over_time acos acosh asin asinh atan atanh avg_over_time ceil changes clamp clamp_max " +
    "clamp_min cos cosh count_over_time day_of_month day_of_week day_of_year days_in_month deg delta deriv exp floor " +
    "histogram_avg histogram_count histogram_fraction histogram_quantile histogram_stddev histogram_stdvar histogram_sum " +
    "holt_winters idelta increase irate label_join label_replace last_over_time ln log10 log2 mad_over_time max_over_time " +
    "min_over_time minute month pi predict_linear present_over_time quantile_over_time rad rate resets round scalar sgn sin " +
    "sinh sort sort_by_label sort_by_label_desc sort_desc sqrt stddev_over_time stdvar_over_time sum_over_time tan tanh time " +
    "timestamp vector year").split(" ");
  const AGGREGATIONS = "sum min max avg group stddev stdvar count count_values bottomk topk quantile limitk limit_ratio".split(" ");
  const KEYWORDS = "by without on ignoring group_left group_right offset bool and or unless".split(" ");
  const MATCHERS = new Set(["=", "!=", "=~", "!~"]);
  const GROUPING = new Set(["by", "without", "on", "ignoring", "group_left", "group_right"]);
  const WORDS = new Set([...FUNCTIONS, ...AGGREGATIONS]);
  const HINT = 'count by(__name__)({__name__=~".+"})';      // the owner's way in: every metric and how many series it has
  const DEBOUNCE_MS = 120, MOST_KEPT = 200;
  const LEX = /(#[^\n]*)|("(?:\\.|[^"\\\n])*"?|'(?:\\.|[^'\\\n])*'?|`[^`]*`?)|(\d+(?:ms|[smhdwy])(?:\d+(?:ms|[smhdwy]))*|0x[0-9a-fA-F]+|(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)|([A-Za-z_:][A-Za-z0-9_:]*)|(=~|!~|!=|==|<=|>=|[-+*/%^<>=])|([(){}\[\],@])|(\s+)|(.)/gy;
  const KINDS = [null, "comment", "string", "number", "ident", "op", "punct", "space", "other"];

  /* the tokens of ``text``, each with its place and what it is: an ident is a function, a keyword, a label (in braces or
     a grouping's parentheses) or a metric; ``open`` on a string not yet closed */
  function tokens(text) {
    const out = [];
    let brace = 0, group = 0, paren = 0, m;
    LEX.lastIndex = 0;
    while (LEX.lastIndex < text.length && (m = LEX.exec(text))) {
      const kind = KINDS[m.slice(1).findIndex(x => x !== undefined) + 1], s = m.index, e = LEX.lastIndex, w = m[0];
      const t = { kind, s, e, w };
      if (kind === "punct") {
        if (w === "{") brace++; else if (w === "}") brace = Math.max(0, brace - 1);
        else if (w === "(") { paren++; if (prev(out)?.group) group = paren; }
        else if (w === ")") { if (group === paren) group = 0; paren = Math.max(0, paren - 1); }
      } else if (kind === "string") t.open = w.length < 2 || w[w.length - 1] !== w[0];   // (an escaped quote is read with its \)
      else if (kind === "ident") {
        if (brace || group) t.kind = "label";
        else if (GROUPING.has(w)) { t.kind = "keyword"; t.group = true; }
        else if (KEYWORDS.includes(w)) t.kind = "keyword";
        else if (WORDS.has(w) && /^\s*\(|^\s+(by|without)\b/.test(text.slice(e))) t.kind = "function";
        else t.kind = "metric";
      }
      t.inBrace = brace > 0 && !(kind === "punct" && w === "{");
      t.inGroup = group > 0;
      out.push(t);
    }
    return out;
  }
  function prev(ts, i = ts.length) { for (let j = i - 1; j >= 0; j--) if (ts[j].kind !== "space") return ts[j]; return null; }

  /* what may be completed at the caret: {what, prefix, from, metric, label}, or null */
  function context(text, at) {
    const ts = tokens(text.slice(0, at)), last = ts[ts.length - 1];
    const word = last && ["metric", "label", "function", "keyword"].includes(last.kind) && last.e === at ? last : null;
    const prefix = word ? word.w : "", from = word ? word.s : at;
    const before = word ? ts.length - 1 : ts.length;
    if (last?.kind === "string" && last.open && last.e === at && last.inBrace) {
      const op = prev(ts, ts.length - 1), lab = op?.kind === "op" && prev(ts, ts.indexOf(op));
      if (lab?.kind !== "label") return null;
      return { what: "values", label: lab.w, metric: metricOf(ts), prefix: last.w.slice(1), from: last.s + 1, quote: last.w[0] };
    }
    if (last?.kind === "string" || last?.kind === "comment" || last?.kind === "number") return null;
    const p = prev(ts, before);
    const inBrace = word ? word.inBrace : last?.inBrace || (last?.kind === "punct" && last.w === "{");
    if (inBrace && p?.kind === "op" && MATCHERS.has(p.w)) {      // a value not yet quoted: it is put in quotes
      const lab = prev(ts, ts.indexOf(p));
      return lab?.kind === "label" ? { what: "values", label: lab.w, metric: metricOf(ts), prefix, from, quote: '"', bare: true } : null;
    }
    if (inBrace) return p && (p.w === "{" || p.w === ",") ? { what: "labels", metric: metricOf(ts), prefix, from } : null;
    const inGroup = word ? word.inGroup : last?.inGroup;
    if (inGroup) return p && (p.w === "(" || p.w === ",") ? { what: "labels", metric: "", prefix, from } : null;
    return { what: "metrics", prefix, from };
  }
  function metricOf(ts) {
    for (let i = ts.length - 1; i >= 0; i--) if (ts[i].kind === "punct" && ts[i].w === "{") { const p = prev(ts, i); return p?.kind === "metric" ? p.w : ""; }
    return "";
  }

  /* line and column (each from 1) as an offset in ``text``; the column counts UTF-8 bytes, as Prometheus counts it */
  function offsetOf(text, [line, col]) {
    let off = 0;
    for (let l = 1; l < line; l++) { const n = text.indexOf("\n", off); if (n < 0) return text.length; off = n + 1; }
    for (let bytes = Math.max(0, col - 1); bytes > 0 && off < text.length;) {
      const c = text.codePointAt(off);
      bytes -= c < 0x80 ? 1 : c < 0x800 ? 2 : c < 0x10000 ? 3 : 4;
      off += c > 0xffff ? 2 : 1;
    }
    return off;
  }

  /* ``source()``: the data source's name now (the query may be moved to another source of the same language) */
  function make({ source, onInput, onRun }) {
    const area = h("textarea", { "data-slot": "text", rows: 3, spellcheck: "false", class: "pe-text pq-area", placeholder: HINT,
                                 wrap: "off", autocomplete: "off", "aria-autocomplete": "list", "aria-expanded": "false" });
    const shown = h("pre", { class: "pq-hl", "aria-hidden": "true" }), lines = codeBox.gutter(area);
    const list = h("ul", { class: "pq-list", role: "listbox", hidden: true, "aria-label": "Suggestions" });
    const hint = h("div", { class: "pq-hint" }, "Try ", h("code", {}, HINT), " to list every metric · Ctrl+Space suggests · Ctrl+Enter runs");
    const el = h("div", { class: "pq-editor" }, h("div", { class: "pq-box" }, lines.el, h("div", { class: "pq-code" }, shown, area)), list, hint);
    const kept = new Map();
    let mark = null, ctx = null, picks = [], chosen = 0, asked = 0, timer = null;

    function render() {
      const text = area.value, err = mark ? offsetOf(text, mark.at) : -1, parts = [], ts = tokens(text);
      const br = document.activeElement === area && area.selectionStart === area.selectionEnd ? codeBox.brackets(ts, area.selectionStart) : null;
      ts.forEach((t, i) => {
        const hit = err >= t.s && err < t.e;
        parts.push(t.kind === "space" && !hit ? document.createTextNode(t.w)
          : h("span", { class: `pq-${t.kind}${hit ? " pq-err" : ""}${codeBox.bracketClass(br, i)}`, ...(hit ? { title: mark.words, "data-at": String(t.s) } : {}) }, t.w));
      });
      if (err >= text.length) parts.push(h("span", { class: "pq-err", title: mark.words, "data-at": String(text.length) }, " "));
      parts.push(document.createTextNode("\n"));       // (a last empty line keeps its height)
      shown.replaceChildren(...parts);
      area.setAttribute("aria-invalid", mark ? "true" : "false");
      syncScroll();
    }
    function syncScroll() { shown.scrollTop = area.scrollTop; shown.scrollLeft = area.scrollLeft; lines.draw(); }

    function close() { list.hidden = true; picks = []; area.setAttribute("aria-expanded", "false"); }
    function show(items) {
      picks = items; chosen = 0;
      list.replaceChildren(...items.map((x, i) => h("li", { role: "option", class: "pq-pick", "data-kind": x.kind, "data-i": String(i),
        onmousedown: ev => { ev.preventDefault(); chosen = i; accept(); } }, h("span", { class: "pq-pick-name" }, x.name), h("span", { class: "pq-pick-kind" }, x.kind))));
      if (ctx?.more) list.append(h("li", { class: "pq-more", role: "presentation" }, "More: type more of the name"));
      list.hidden = !items.length;
      area.setAttribute("aria-expanded", items.length ? "true" : "false");
      highlightPick();
    }
    function highlightPick() {
      for (const li of list.querySelectorAll(".pq-pick")) li.setAttribute("aria-selected", li.dataset.i === String(chosen) ? "true" : "false");
      list.querySelector('[aria-selected="true"]')?.scrollIntoView?.({ block: "nearest" });
    }
    function names(c) {                         // the source's names for this place, each asked once (a bounded number kept)
      const key = JSON.stringify([source(), c.what, c.prefix, c.metric || "", c.label || ""]);
      if (!kept.has(key)) {
        if (kept.size >= MOST_KEPT) kept.delete(kept.keys().next().value);
        kept.set(key, api("query/suggest", { source: source(), what: c.what, prefix: c.prefix, metric: c.metric || "", label: c.label || "" })
          .then(got => { if (got.error) kept.delete(key); return got; },     // (a refusal or a failure is asked again next time)
                e => { kept.delete(key); return { suggestions: [], error: String(e?.message || e) }; }));
      }
      return kept.get(key);
    }
    async function suggest(force = false) {
      const c = context(area.value, area.selectionStart);
      const mine = ++asked;
      if (!c || area.selectionStart !== area.selectionEnd || (!force && !c.prefix && c.what === "metrics")) { ctx = null; close(); return; }
      const own = c.what === "metrics" ? [...AGGREGATIONS, ...FUNCTIONS].filter(w => w.startsWith(c.prefix)).map(name => ({ name, kind: "function" })) : [];
      const got = await names(c);
      if (mine !== asked) return;               // typed on since: this answer is for a place no longer there
      ctx = { ...c, more: !!got.more };
      const kind = { metrics: "metric", labels: "label", values: "value" }[c.what];
      const theirs = (got.suggestions || []).filter(n => n !== c.prefix || c.what === "values").map(name => ({ name, kind }));
      show([...theirs, ...own]);
    }
    function accept() {
      const x = picks[chosen];
      if (!x || !ctx) return;
      const at = area.selectionStart, rest = area.value.slice(at);
      let put = x.name;
      if (x.kind === "function") put += rest.startsWith("(") ? "" : "(";
      if (x.kind === "value") put = (ctx.bare ? ctx.quote : "") + JSON.stringify(put).slice(1, -1) + (!ctx.bare && rest.startsWith(ctx.quote) ? "" : ctx.quote);
      area.setRangeText(put, ctx.from, at, "end");
      close();
      typed();
    }
    function typed() {
      mark = null;
      close();                                  // (the names shown were for the text before: none is picked by mistake)
      render();
      onInput(area.value);
      clearTimeout(timer);
      timer = setTimeout(suggest, DEBOUNCE_MS);
    }

    area.addEventListener("input", typed);
    area.addEventListener("scroll", syncScroll);
    area.addEventListener("blur", () => setTimeout(() => { close(); render(); }, 0));
    for (const on of ["keyup", "mouseup", "focus"]) area.addEventListener(on, render);   // (the caret moved: its brackets)
    area.addEventListener("keydown", ev => {
      const own = () => { ev.preventDefault(); ev.stopPropagation(); };
      if (ev.key === "Enter" && (ev.ctrlKey || ev.metaKey)) { own(); close(); onRun(); return; }
      if (ev.key === " " && ev.ctrlKey) { own(); suggest(true); return; }
      if (list.hidden || !picks.length) return;
      if (ev.key === "ArrowDown" || ev.key === "ArrowUp") { own(); chosen = (chosen + (ev.key === "ArrowDown" ? 1 : picks.length - 1)) % picks.length; highlightPick(); }
      else if (ev.key === "Enter" || ev.key === "Tab") { own(); accept(); }
      else if (ev.key === "Escape") { own(); close(); }
    });
    render();
    return {
      el, area,
      set(value) { if (area.value !== value) { area.value = value; render(); } },
      /* where the source said the text is wrong ([line, column], each from 1), or null */
      mark(at, words) { const next = Array.isArray(at) && at.length === 2 ? { at, words: words || "" } : null;
                        if (JSON.stringify(next) !== JSON.stringify(mark)) { mark = next; render(); } },
    };
  }

  window.queryEditors = Object.assign(window.queryEditors || {}, { PromQL: make });
  window.promql = { tokens, context, offsetOf, HINT };
})();
