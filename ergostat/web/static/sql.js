/* The query box of a SQL data source (ergostat/datasources/sql.py): the text highlighted as it is written (keywords,
   functions, the source's views and their columns, strings, numbers, comments) and completed from SQL's own words and
   from the source's views (after FROM or JOIN) and the columns of the views the text names (elsewhere), which the server
   lists (GET /api/query/suggest: what=metrics for views, what=labels&metric=VIEW for a view's columns). Ctrl+Enter (or
   Cmd+Enter) runs the query. Registered as window.queryEditors.SQL; it draws with the PromQL box's classes (pq-*).
   Plain JavaScript, no library and no build step. */
(function () {
  "use strict";
  const KEYWORDS = ("select from where group by order having limit offset as and or not in is null like glob between case " +
    "when then else end join left inner outer cross on using with recursive union all distinct asc desc over partition " +
    "window rows range preceding following current row unbounded exists cast filter nulls first last").split(" ");
  const FUNCTIONS = ("count sum avg min max total median percentile percentile_cont group_concat coalesce ifnull iif " +
    "nullif abs round length lower upper substr trim replace instr printf date time datetime julianday unixepoch " +
    "strftime json_extract row_number rank dense_rank lag lead first_value last_value ntile cume_dist floor ceil").split(" ");
  const KW = new Set(KEYWORDS), FN = new Set(FUNCTIONS);
  const HINT = "select state, count(*) as n from item_spans where \"left\" is null group by state";
  const LEX = /(--[^\n]*|\/\*[\s\S]*?(?:\*\/|$))|('(?:''|[^'])*'?)|("(?:""|[^"])*"?)|((?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)|([A-Za-z_][A-Za-z0-9_]*)|(:[A-Za-z_]+|\|\||<=|>=|<>|!=|->>|->|[-+*/%<>=])|([(),.;])|(\s+)|(.)/gy;
  const KINDS = [null, "comment", "string", "column", "number", "word", "op", "punct", "space", "other"];

  /* the tokens of ``text``: a word is a keyword, a function (before "("), a view, a column, or (none known) a column */
  function tokens(text, views) {
    const out = [];
    let m;
    LEX.lastIndex = 0;
    while (LEX.lastIndex < text.length && (m = LEX.exec(text))) {
      const kind = KINDS[m.slice(1).findIndex(x => x !== undefined) + 1], w = m[0], t = { kind, s: m.index, e: LEX.lastIndex, w };
      if (kind === "word") {
        const lw = w.toLowerCase();
        t.kind = FN.has(lw) && /^\s*\(/.test(text.slice(t.e)) ? "function" : KW.has(lw) ? "keyword" : views.has(w) ? "view" : "column";
      }
      out.push(t);
    }
    return out;
  }
  function prev(ts, i) { for (let j = i - 1; j >= 0; j--) if (ts[j].kind !== "space") return ts[j]; return null; }

  /* what may be completed at the caret: {what: "views"|"columns", prefix, from, of, open}, or null (in a string or
     comment). ``of``: the view after "VIEW." or "ALIAS.", whose columns alone are offered. ``open``: a list is shown
     before anything is typed (after FROM or JOIN, after a "VIEW.", and where a column is wanted next) */
  function context(text, at, views) {
    const ts = tokens(text.slice(0, at), views), last = ts[ts.length - 1];
    if (last && ["comment", "string", "number"].includes(last.kind) && last.e === at) return null;
    const word = last && ["view", "column", "keyword", "function"].includes(last.kind) && last.e === at ? last : null;
    const i = word ? ts.length - 1 : ts.length, p = prev(ts, i);
    const c = { prefix: word ? word.w : "", from: word ? word.s : at };
    if (p && p.kind === "keyword" && /^(from|join)$/i.test(p.w)) return { ...c, what: "views", open: true };
    const owner = p?.w === "." && ts[i - 1] === p ? prev(ts, ts.indexOf(p)) : null;
    if (owner) return { ...c, what: "columns", of: viewOf(text, owner.w, views), open: true };
    return { ...c, what: "columns", open: !!p && (p.w === "," || /^(select|where|by|on|and|or|having)$/i.test(p.w)) };
  }
  /* the view ``name`` stands for: itself, or the view it names as an alias ("ticket t", "ticket as t"), or "" */
  function viewOf(text, name, views) {
    if (views.has(name)) return name;
    const ts = tokens(text, views).filter(t => t.kind !== "space" && t.kind !== "comment");
    for (let j = 1; j < ts.length; j++) {
      if (ts[j].w !== name) continue;
      const v = ts[j - 1].kind === "keyword" && /^as$/i.test(ts[j - 1].w) ? ts[j - 2] : ts[j - 1];
      if (v?.kind === "view") return v.w;
    }
    return "";
  }
  function named(text, views) {                // the views the text reads
    return [...new Set(tokens(text, views).filter(t => t.kind === "view").map(t => t.w))];
  }

  function make({ source, onInput, onRun }) {
    const area = h("textarea", { "data-slot": "text", rows: 3, spellcheck: "false", class: "pe-text pq-area", placeholder: HINT,
                                 wrap: "off", autocomplete: "off", "aria-autocomplete": "list", "aria-expanded": "false" });
    const shown = h("pre", { class: "pq-hl", "aria-hidden": "true" }), lines = codeBox.gutter(area);
    const list = h("ul", { class: "pq-list", role: "listbox", hidden: true, "aria-label": "Suggestions" });
    const hint = h("div", { class: "pq-hint" }, "Views: item_spans, transitions, item_fields and one per item kind · Ctrl+Space suggests · Ctrl+Enter runs");
    const el = h("div", { class: "pq-editor" }, h("div", { class: "pq-box" }, lines.el, h("div", { class: "pq-code" }, shown, area)), list, hint);
    const kept = new Map();
    let views = new Set(), ctx = null, picks = [], chosen = 0, asked = 0, timer = null;

    function ask(what, metric = "") {             // each asked once a source: the views do not change while one edits
      const key = JSON.stringify([source(), what, metric]);
      if (!kept.has(key)) kept.set(key, api("query/suggest", { source: source(), what, prefix: "", metric, label: "" })
        .then(got => { if (got.error) kept.delete(key); return got.suggestions || []; }, () => { kept.delete(key); return []; }));
      return kept.get(key);
    }
    function render() {
      const ts = tokens(area.value, views);
      const br = document.activeElement === area && area.selectionStart === area.selectionEnd ? codeBox.brackets(ts, area.selectionStart) : null;
      const parts = ts.map((t, i) => t.kind === "space" ? document.createTextNode(t.w) : h("span", { class: `pq-${t.kind}${codeBox.bracketClass(br, i)}` }, t.w));
      shown.replaceChildren(...parts, document.createTextNode("\n"));
      shown.scrollTop = area.scrollTop; shown.scrollLeft = area.scrollLeft;
      lines.draw();
    }
    function close() { list.hidden = true; picks = []; area.setAttribute("aria-expanded", "false"); }
    function show(items) {
      picks = items; chosen = 0;
      list.replaceChildren(...items.map((x, i) => h("li", { role: "option", class: "pq-pick", "data-kind": x.kind, "data-i": String(i),
        onmousedown: ev => { ev.preventDefault(); chosen = i; accept(); } }, h("span", { class: "pq-pick-name" }, x.name), h("span", { class: "pq-pick-kind" }, x.kind))));
      list.hidden = !items.length;
      area.setAttribute("aria-expanded", items.length ? "true" : "false");
      mark();
    }
    function mark() { for (const li of list.querySelectorAll(".pq-pick")) li.setAttribute("aria-selected", li.dataset.i === String(chosen) ? "true" : "false"); }
    async function suggest(force = false) {
      const mine = ++asked;
      views = new Set(await ask("metrics"));
      if (mine !== asked) return;
      render();
      const c = context(area.value, area.selectionStart, views);
      if (!c || area.selectionStart !== area.selectionEnd || (!force && !c.prefix && !c.open)) { ctx = null; close(); return; }
      let got;
      if (c.what === "views") got = [...views].map(name => ({ name, kind: "view" }));
      else {
        const cols = await Promise.all((c.of ? [c.of] : named(area.value, views)).map(v => ask("labels", v)));
        got = [...new Set(cols.flat())].map(name => ({ name, kind: "column" }));
        if (c.of === undefined && (c.prefix || force))      // (SQL's own words once something is typed, or asked for)
          got = got.concat(FUNCTIONS.map(name => ({ name, kind: "function" })), KEYWORDS.map(name => ({ name, kind: "keyword" })));
      }
      if (mine !== asked) return;
      ctx = c;
      show(got.filter(x => x.name.toLowerCase().startsWith(c.prefix.toLowerCase()) && x.name !== c.prefix).slice(0, 100));
    }
    function accept() {
      const x = picks[chosen];
      if (!x || !ctx) return;
      const at = area.selectionStart;
      area.setRangeText(x.name + (x.kind === "function" && !area.value.slice(at).startsWith("(") ? "(" : ""), ctx.from, at, "end");
      close();
      typed();
    }
    function typed() {
      close();
      render();
      onInput(area.value);
      clearTimeout(timer);
      timer = setTimeout(suggest, 120);
    }
    area.addEventListener("input", typed);
    area.addEventListener("scroll", render);
    area.addEventListener("blur", () => setTimeout(() => { close(); render(); }, 0));
    for (const on of ["keyup", "mouseup", "focus"]) area.addEventListener(on, render);   // (the caret moved: its brackets)
    area.addEventListener("keydown", ev => {
      const own = () => { ev.preventDefault(); ev.stopPropagation(); };
      if (ev.key === "Enter" && (ev.ctrlKey || ev.metaKey)) { own(); close(); onRun(); return; }
      if (ev.key === " " && ev.ctrlKey) { own(); suggest(true); return; }
      if (list.hidden || !picks.length) return;
      if (ev.key === "ArrowDown" || ev.key === "ArrowUp") { own(); chosen = (chosen + (ev.key === "ArrowDown" ? 1 : picks.length - 1)) % picks.length; mark(); }
      else if (ev.key === "Enter" || ev.key === "Tab") { own(); accept(); }
      else if (ev.key === "Escape") { own(); close(); }
    });
    render();
    suggest();                                   // (the views, so they are highlighted before anything is typed)
    return { el, area, set(value) { if (area.value !== value) { area.value = value; render(); } } };
  }

  window.queryEditors = Object.assign(window.queryEditors || {}, { SQL: make });
  window.sqlEditor = { tokens, context, HINT };
})();
