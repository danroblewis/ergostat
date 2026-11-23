/* the panel editor: one panel's queries and display options over the page, a live preview on top. Every choice
   comes from queryFields(), so only what the model offers can be picked. It edits a copy and writes nothing to the
   server: what happens to the result is the caller's (onChange, onSave, onCancel). */
(function () {
  const DEBOUNCE_MS = 250;
  const SOURCES = [["items", "Item fields"], ["moves", "Item moves"], ["counts", "Items per state"], ["series", "Metric series"], ["events", "Events"]];
  const KINDED = new Set(["items", "moves", "counts"]);
  const MEASURES = [["entries", "Entries"], ["exits", "Exits"], ["time_in_state", "Time in state"]];
  const AGGS = { count: "Count", sum: "Sum", avg: "Average", min: "Minimum", max: "Maximum", last: "Last", p50: "Median (p50)", p90: "p90", p95: "p95", p99: "p99" };
  const TRANSFORMS = { none: "None", rate: "Rate", delta: "Change per step", cumulative: "Running total", moving_avg: "Moving average" };
  const RATES = [["second", "per second", "/s"], ["minute", "per minute", "/min"], ["hour", "per hour", "/h"], ["day", "per day", "/d"]];
  const WINDOWS = [2, 3, 5, 10, 20, 60];
  const FORM_GROUPS = [["time", "Time series"], ["comparison", "Comparison"], ["distribution", "Distribution"], ["dynamics", "Dynamics and control"]];
  /* decoration only, for the families known today: what a form can do is read from its registration, and a new one takes ``icon`` or the plain mark */
  const ICONS = {
    line: "M1 13 7 7l5 3 5-7 6 4", bar: "M3 15V8h4v7zM10 15V3h4v12zM17 15v-5h4v5z", scatter: "M4 12h1M8 6h1M12 10h1M16 4h1M19 9h1",
    heatmap: "M2 2h6v6H2zM9 9h6v6H9zM16 2h6v6h-6z", candlestick: "M6 1v14M4 5h4v6H4zM16 2v13M14 4h4v5h-4z", histogram: "M2 15v-3h4V7h4V2h4v6h4v4h4v3z",
    box: "M12 1v4M12 11v4M7 5h10v6H7zM7 8h10", stat: "M4 12V4l-2 2M10 4h5v4h-5v4h5M19 4v8", table: "M2 2h20v12H2zM2 6h20M2 10h20M9 2v12",
    phase: "M12 8c3-3 7 0 5 3s-9 3-11-1 3-9 9-8", bode: "M1 4h10c4 0 6 3 12 4M1 12h10c4 0 6 2 12 3", nyquist: "M3 8a9 7 0 0 1 18 0M3 8a9 7 0 0 0 18 0M12 1v14M1 8h22",
    "pole-zero": "M5 3l4 4M9 3 5 7M17 11a2 2 0 1 0 .01 0M1 8h22M12 1v14",
  };
  const PLAIN_ICON = "M2 14h20M2 14V2";
  const X_TYPES = { time: "Time", query: "Another query", field: "An item field", category: "A category", bins: "Bins of values" };
  const SEGMENTS = [2, 3, 4, 6, 8, 12];
  const PART_NAMES = { input: "Input", output: "Output" };
  const SIZES = [["s", "Third"], ["m", "Half"], ["l", "Two thirds"], ["full", "Full"]];
  const LEGENDS = [["", "Automatic"], ["right", "Right"], ["bottom", "Below"], ["hidden", "Hidden"]];
  const LEGEND_VALUES = [["last", "Last"], ["min", "Min"], ["max", "Max"], ["avg", "Average"]];
  const UNITS = ["items", "items/h", "events", "usd", "usd/h", "s", "%", "bytes", "tokens"];
  const ORDER = ["source", "text", "kind", "field", "measure", "state", "series", "type", "where", "group_by", "agg", "transform", "rate_per", "window", "segments"];
  const FOCUSABLE = "a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex='-1'])";
  const clone = v => (v === undefined ? v : JSON.parse(JSON.stringify(v)));
  const pairs = names => names.map(n => [n, n]);
  const nameOf = x => (typeof x === "string" ? x : x?.name);

  /* a source under the model's sources: that is queried in its own language (ergostat/datasources), not a built-in one */
  const dataSource = (q, F) => (F?.datasources || []).find(d => d.name === q.source && !SOURCES.some(([n]) => n === d.name)) || null;
  function kindsOf(src) { return Array.isArray(src?.kinds) ? src.kinds : Object.keys(src?.kinds || {}); }
  function kindOf(q, F) { const k = F?.sources?.[q.source]?.kinds; return k && !Array.isArray(k) ? k[q.kind] || null : null; }
  function statesFor(q, F) { return kindOf(q, F)?.states || F?.sources?.items?.kinds?.[q.kind]?.states || []; }

  function aggNames(q, F) {
    const offered = F?.aggregations || [];
    const only = list => list.filter(a => offered.includes(a));
    if (q.agg === "ohlc") return ["ohlc"];                 // (the candlestick's: set by the form, undone by leaving it)
    if (q.x?.type === "bins") return only(["count", ...offered.filter(a => a !== "count")]);
    if (q.source === "events" || (q.source === "moves" && q.measure !== "time_in_state")) return only(["count"]);
    if (q.source === "moves") return only(["avg", "min", "max", "p50", "p90", "p95", "p99"]);
    if (q.source === "series") return offered.filter(a => a !== "count");
    return offered;
  }
  function transformNames(q, F) {
    if (q.agg === "ohlc") return (F?.transforms || []).filter(t => t === "none");
    const accumulates = q.source !== "counts" && (["count", "sum"].includes(q.agg) || (q.source === "series" && q.agg === "last"));
    return (F?.transforms || []).filter(t => accumulates || !["rate", "cumulative"].includes(t));
  }

  /* what this query can be asked, in order, given what it has chosen so far */
  function slotsOf(q, F, nested = false) {
    if (!F) return [{ key: "source", label: "Source", options: SOURCES, required: true, locked: true }];   // (until the fields are read)
    const offered = SOURCES.filter(([n]) => F.sources?.[n]);
    if (!nested) offered.push(["frequency", "Frequency response"]);
    if (!nested) for (const d of F.datasources || []) if (dataSource({ source: d.name }, F)) offered.push([d.name, `${d.name} (${d.language})`]);
    const out = [{ key: "source", label: "Source", options: offered, required: true }];
    const ds = nested ? null : dataSource(q, F);
    if (ds) return [...out, { key: "text", label: `Query (${ds.language})`, text: true, required: true, language: ds.language, source: ds.name }];
    if (q.source === "frequency") {
      if (!q.model) out.push({ key: "segments", label: "Segments", options: SEGMENTS.map(n => [n, String(n)]), required: true });
      return out;
    }
    const src = F?.sources?.[q.source];
    if (!src) return out;
    if (KINDED.has(q.source)) out.push({ key: "kind", label: "Kind", options: pairs(kindsOf(src)), required: true });
    const kind = kindOf(q, F);
    if (q.source === "items") {
      out.push({ key: "field", label: "Field", options: pairs((kind?.fields || []).map(nameOf)), required: true });
      out.push({ key: "where", label: "Only in states", options: pairs(kind?.states || []), checks: true });
      out.push({ key: "group_by", label: "Group by", options: pairs(kind?.group_by || []), none: "No grouping" });
    } else if (q.source === "moves") {
      out.push({ key: "measure", label: "Measure", options: MEASURES, required: true });
      out.push({ key: "state", label: "State", options: pairs(kind?.states || []), required: true });
    } else if (q.source === "counts") {
      const states = statesFor(q, F);
      if (states.length) out.push({ key: "where", label: "Only in states", options: pairs(states), checks: true });
    } else if (q.source === "series") {
      out.push({ key: "series", label: "Metric", options: pairs((src.series || []).map(nameOf)), required: true });
    } else if (q.source === "events") {
      out.push({ key: "type", label: "Event type", options: pairs(src.types || []), required: true });
    }
    if (q.x?.type === "field") return out;                 // (one point per item: nothing is aggregated)
    if (q.source !== "counts") out.push({ key: "agg", label: "Aggregation", options: aggNames(q, F).map(a => [a, AGGS[a] || a]), required: true });
    if (q.x?.type === "bins") return out;
    out.push({ key: "transform", label: "Transform", options: transformNames(q, F).map(t => [t, TRANSFORMS[t] || t]), required: true });
    if (q.transform === "rate") out.push({ key: "rate_per", label: "Rate unit", options: RATES.map(r => [r[0], r[1]]), required: true });
    if (q.transform === "moving_avg") out.push({ key: "window", label: "Window (steps)", options: WINDOWS.map(n => [n, String(n)]), required: true });
    return out;
  }
  const hasOption = (slot, v) => slot.options.some(([o]) => String(o) === String(v));
  function defaultFor(key, q, slot) {
    if (key === "agg") { const want = q.source === "series" || q.measure === "time_in_state" ? "avg" : "sum"; return hasOption(slot, want) ? want : slot.options[0]?.[0]; }
    if (key === "transform") return hasOption(slot, "none") ? "none" : slot.options[0]?.[0];
    if (key === "rate_per") return "hour";
    if (key === "window") return 5;
    if (key === "segments") return 4;
    return slot.required && slot.options.length === 1 ? slot.options[0][0] : undefined;
  }
  /* a choice was made at ``key``: everything after it that no longer applies goes, and what has one answer takes it */
  function choose(q, key, value, F, nested = false) {
    if (value === "" || value == null) delete q[key]; else q[key] = key === "window" || key === "segments" ? Number(value) : value;
    if (key === "source") {
      delete q.where;
      if (value === "frequency") { delete q.x; q.input ||= {}; q.output ||= {}; } else { delete q.input; delete q.output; delete q.model; }
      if (dataSource(q, F)) { delete q.x; q.text ??= ""; }
    }
    const dropped = [];
    for (const k of ORDER.slice(ORDER.indexOf(key) + 1)) {
      const slot = slotsOf(q, F, nested).find(x => x.key === k);
      if (!slot) { if (q[k] != null && !(k === "agg" && q[k] === "none")) dropped.push(k); delete q[k]; continue; }
      if (slot.text) continue;
      if (k === "where") {
        if (q.where?.state) {
          q.where.state = q.where.state.filter(v => hasOption(slot, v));
          if (!q.where.state.length) delete q.where.state;
        }
        if (q.where && !Object.keys(q.where).length) delete q.where;
        continue;
      }
      if (q[k] != null && !hasOption(slot, q[k])) { dropped.push(k); delete q[k]; }
      if (q[k] == null) { const d = defaultFor(k, q, slot); if (d != null) q[k] = d; }
    }
    if (q.x?.type === "field") q.agg = "none";
    return dropped;
  }
  /* what is wrong with a query: a value the model no longer has, or a choice not made yet */
  function problemsOf(q, F, nested = false) {
    const missing = [], incomplete = [];
    if (!F) return { missing, incomplete };
    if (q.source === "frequency" && !q.model) {
      for (const part of ["input", "output"]) {
        const sub = q[part] || {};
        if (!sub.source) incomplete.push({ key: "source", part, label: `${PART_NAMES[part]} source` });
        const got = problemsOf(sub, F, true);
        for (const [slot, v] of got.missing) missing.push([{ ...slot, part, label: `${PART_NAMES[part]} ${slot.label.toLowerCase()}` }, v]);
        for (const slot of got.incomplete) incomplete.push({ ...slot, part, label: `${PART_NAMES[part]} ${slot.label.toLowerCase()}` });
      }
    }
    if (q.x?.type === "query" && !q.x.query) incomplete.push({ key: "x_query", label: "X query" });
    for (const slot of slotsOf(q, F, nested)) {
      if (slot.checks) { for (const v of q.where?.state || []) if (!hasOption(slot, v)) missing.push([slot, v]); continue; }
      if (slot.text) { if (!String(q.text || "").trim()) incomplete.push(slot); continue; }
      if (q[slot.key] == null) { if (slot.required) incomplete.push(slot); } else if (!hasOption(slot, q[slot.key])) missing.push([slot, q[slot.key]]);
    }
    return { missing, incomplete };
  }
  function unitOf(q, F) {
    let base = null;
    if (q.source === "items") base = kindOf(q, F)?.fields?.find(f => nameOf(f) === q.field)?.unit;
    else if (q.source === "series") base = F?.sources?.series?.series?.find(f => nameOf(f) === q.series)?.unit;
    else if (q.source === "moves") base = q.measure === "time_in_state" ? "s" : "items";
    else if (q.source === "counts") base = "items";
    else if (q.source === "events") base = "events";
    if (!base) return null;
    return q.transform === "rate" ? base + (RATES.find(r => r[0] === q.rate_per)?.[2] || "") : base;
  }
  /* the X axes this query's source can answer, from the fields the model has */
  function numericFields(q, F) { return q.source === "items" ? (kindOf(q, F)?.fields || []).map(nameOf) : []; }
  function categoriesOf(q, F) {
    if (q.source === "items") return kindOf(q, F)?.group_by || [];
    return q.source === "counts" && statesFor(q, F).length ? ["state"] : [];
  }
  function xTypesOf(q, F) {
    if (!q.source || q.source === "frequency" || dataSource(q, F)) return [];
    const out = ["time", "query"];
    if (q.source === "items" && !q.kind) return out;
    if (numericFields(q, F).length >= 2) out.push("field");
    if (categoriesOf(q, F).length) out.push("category");
    out.push("bins");
    return out;
  }
  const canBeX = (o, q) => o !== q && o.source !== "frequency" && !(o.x?.type === "query" && o.x.query === q.id);
  function describe(q) { if (q.text != null) return `${q.source}: ${String(q.text).slice(0, 40)}`; return [q.field || q.series || q.type || q.measure, q.state, q.kind].filter(Boolean).join(" · ") || q.source || "not chosen yet"; }
  function xSlots(q, F, queries) {
    const types = xTypesOf(q, F);
    if (!types.length) return [];
    const x = q.x || { type: "time" };
    const out = [{ key: "x_type", label: "X axis", options: types.map(t => [t, X_TYPES[t]]), value: x.type, required: true }];
    if (x.type === "query") out.push({ key: "x_query", label: "X query", value: x.query, required: true, options: queries.filter(o => canBeX(o, q)).map(o => [o.id, `${o.id.toUpperCase()}: ${describe(o)}`]) });
    if (x.type === "field") out.push({ key: "x_field", label: "X field", value: x.field, required: true, options: pairs(numericFields(q, F).filter(n => n !== q.field)) });
    if (x.type === "category") out.push({ key: "x_by", label: "Category", value: x.by, required: true, options: pairs(categoriesOf(q, F)) });
    if (x.type === "bins") {
      if (q.source === "items") out.push({ key: "x_bin_field", label: "Field to bin", value: x.field, required: true, options: pairs(numericFields(q, F)) });
      out.push({ key: "x_bins", label: "Bins", value: x.bins, required: true, options: [5, 10, 20, 30, 50, 100].map(n => [n, String(n)]) });
    }
    return out;
  }
  /* the registry of chart families, as plotForms() gives it: the editor knows no family but by what it registered */
  function formsRegistered() {
    const r = typeof plotForms === "function" ? plotForms() : null;
    const list = r instanceof Map ? [...r] : Array.isArray(r) ? r.map(f => [f.name, f]) : Object.entries(r || {});
    return new Map(list);
  }
  const choiceOf = c => (Array.isArray(c) ? c : c && typeof c === "object" ? [c.value, c.label ?? String(c.value)] : [c, words(c)]);
  const words = v => { const t = String(v).replace(/[-_]/g, " "); return t.charAt(0).toUpperCase() + t.slice(1); };
  function applies(option, config) { try { return !option.when || !!option.when(config); } catch { return false; } }
  function formIcon(reg, name) {
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 24 16"); svg.setAttribute("class", "pe-form-icon"); svg.setAttribute("aria-hidden", "true");
    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("d", reg.icon || ICONS[name] || PLAIN_ICON);
    svg.append(path);
    return svg;
  }
  /* why the current queries cannot be drawn by a form (null when they can) */
  function formProblem(reg, queries, answer) {
    const n = reg.needs || {}, shown = queries.filter(q => q.source && !q.hidden);
    if (n.source && !shown.some(q => q.source === n.source)) return `Needs ${n.text || `a ${n.source} query`}.`;
    if (!n.source && shown.some(q => q.source === "frequency")) return "Cannot draw a frequency response.";
    if (n.x?.length) {
      const usedAsX = new Set(shown.filter(q => q.x?.type === "query").map(q => q.x.query));     // (an X is drawn as the other's axis)
      const off = shown.find(q => q.source !== "frequency" && !usedAsX.has(q.id) && !n.x.includes(q.x?.type || "time"));
      if (off) return `Needs an X axis of ${n.x.map(t => (X_TYPES[t] || t).toLowerCase()).join(" or ")}; query ${off.id.toUpperCase()} has ${(X_TYPES[off.x?.type || "time"]).toLowerCase()}.`;
    }
    if (n.data && !(answer?.results || []).some(r => r[n.data] != null || r.frequency?.[n.data] != null)) return `Needs ${n.text || n.data}, which this data does not supply.`;
    return null;
  }
  /* a form the current result can be drawn as already: nothing in the way, and any aggregation it asks for already asked */
  function formFits(reg, queries, answer) {
    if (formProblem(reg, queries, answer)) return false;
    const agg = reg.needs?.agg;
    return !agg || queries.filter(q => q.source && !q.hidden && q.source !== "frequency").every(q => q.agg === agg);
  }
  function nextId(queries) {
    const used = new Set(queries.map(q => q.id));
    for (const c of "abcdefghijklmnopqrstuvwxyz") if (!used.has(c)) return c;
    let n = 27;
    while (used.has("q" + n)) n++;
    return "q" + n;
  }

  let controlIds = 0;
  function field(label, control) {           // (a label beside its control, so a select's options are not read as its name)
    control.id ||= `pe-control-${++controlIds}`;
    return h("div", { class: "pe-f" }, h("label", { class: "pe-l", for: control.id }, label), control);
  }
  function fillSelect(sel, slot, value) {
    const known = value == null || value === "" || hasOption(slot, value);
    const sig = JSON.stringify([slot.options, slot.none, slot.required && value == null, known ? null : value]);
    if (sel.__sig !== sig) {
      sel.__sig = sig;
      const opts = [];
      if (slot.none) opts.push(h("option", { value: "" }, slot.none));
      else if (value == null) opts.push(h("option", { value: "" }, slot.options.length ? "Choose…" : "None available"));
      for (const [v, text] of slot.options) opts.push(h("option", { value: v }, text));
      if (!known) opts.push(h("option", { value }, `${value} (missing)`));
      sel.replaceChildren(...opts);
    }
    sel.value = value == null ? "" : String(value);
    sel.disabled = !!slot.locked || (!slot.options.length && known && !slot.none);
    sel.classList.toggle("pe-missing", !known);
    if (known) sel.removeAttribute("aria-invalid"); else sel.setAttribute("aria-invalid", "true");
  }
  function radios(name, legend, options, value, onPick) {
    const inputs = options.map(([v, text]) => {
      const input = h("input", { type: "radio", name, value: v, onchange: () => onPick(v) });
      input.checked = v === value;
      return h("label", { class: "pe-seg" }, input, h("span", {}, text));
    });
    return h("fieldset", { class: "pe-group" }, h("legend", { class: "pe-l" }, legend), h("div", { class: "pe-segs" }, inputs));
  }

  let openEditor = null;

  function openPanelEditor(config, { onChange, onSave, onCancel, since = 86400 } = {}) {
    openEditor?.cancel();
    const original = clone(config) || {};
    const draft = clone(config) || {};
    if (typeof normalizeForm === "function") Object.assign(draft, normalizeForm(draft) || {});   // (the old form names still load)
    draft.form ||= "line";
    draft.size ||= "m";
    draft.display ||= {};
    if (!Array.isArray(draft.queries) || !draft.queries.length) draft.queries = [{ id: "a" }];
    for (const q of draft.queries) q.id ||= nextId(draft.queries);
    const uid = "pe" + Date.now().toString(36);
    const opener = document.activeElement;
    let F = null, closed = false, timer = null, seq = 0, inFlight = false, lastSig = null, lastAnswer = null;
    const errors = new Map(), cards = new Map(), forms = formsRegistered();
    let pointerPick = false;

    const live = h("div", { class: "pe-live", "aria-live": "polite" });
    const say = text => { live.textContent = text; };
    const saveMsg = h("span", { class: "pe-save-msg", role: "alert" });
    const previewBox = h("div", { class: "pe-preview", role: "region", "aria-label": "Preview" });
    const queriesBox = h("div", { class: "pe-queries" });
    const fieldsMsg = h("div", { class: "pe-fields-msg", role: "alert", hidden: true });

    function previewConfig() {
      let ready = draft.queries.filter(q => {
        if (!q.source || q.hidden) return false;
        const p = problemsOf(q, F);
        return !p.missing.length && !p.incomplete.length;
      });
      for (let before = -1; before !== ready.length;) {        // a query plotted against one that cannot be asked waits for it
        before = ready.length;
        ready = ready.filter(q => q.x?.type !== "query" || ready.some(o => o.id === q.x.query));
      }
      const queries = ready.map(q => { const c = clone(q); delete c.hidden; return c; });
      return { ...clone(draft), id: draft.id || "editor-preview", queries };
    }
    const chart = chartPanel(previewConfig());
    previewBox.append(chart);

    function changed() {
      renderMessages();
      schedulePreview();
      onChange?.(clone(draft));
    }
    function schedulePreview() { clearTimeout(timer); timer = setTimeout(runPreview, DEBOUNCE_MS); }

    async function runPreview() {
      if (closed) return;
      const cfg = previewConfig();
      if (!cfg.queries.length) {
        seq++; inFlight = false; lastSig = null; lastAnswer = null;
        chart.setConfig(cfg);
        const f = draft.queries.find(q => q.source === "frequency" && !q.hidden && !q.model);
        const part = f && (!f.input?.source ? "input" : !f.output?.source ? "output" : null);
        chart.setState("empty", part ? `Choose the response's ${part} in the query below`
          : draft.queries.some(q => q.source && !q.hidden) ? "Finish the query below to see it"
          : draft.queries.some(q => q.hidden) ? "Every query is hidden" : "Choose what to show in a query below");
        return;
      }
      const sig = JSON.stringify([cfg.form, cfg.options || {}, cfg.queries]);   // (a family may ask for its data its own way)
      if (sig === lastSig) {                 // only the display changed: no need to ask again
        if (!inFlight) { chart.setConfig(cfg); if (lastAnswer) draw(lastAnswer); }
        return;
      }
      const mine = ++seq;
      lastSig = sig; lastAnswer = null; inFlight = true;
      let answer;
      try {
        answer = await queryPanels([cfg], { since });
      } catch (e) {
        if (closed || mine !== seq) return;
        inFlight = false; lastSig = null;
        chart.setState("error", `The preview could not be read: ${e?.message || e}`);
        return;
      }
      if (closed || mine !== seq) return;        // a newer question has been asked: this answer is stale
      inFlight = false;
      const got = answer?.get?.(cfg.id) || { results: [] };
      const results = got.results || [];
      errors.clear();
      for (const r of results) if (r.error) errors.set(r.id, r.error);
      for (const [q, card] of cards) {               // (where its source said the text is wrong, marked in it)
        const r = results.find(x => x.id === q.id);
        card.slots.get("text")?.mark?.(r?.error_at || null, r?.error);
      }
      lastAnswer = { results: results.filter(r => !r.error), meta: got.meta, firstError: results.find(r => r.error)?.error };
      renderMessages();
      chart.setConfig({ ...previewConfig(), queries: cfg.queries });
      draw(lastAnswer);
    }
    function draw({ results, meta, firstError }) {
      if (currentProblem()) { chart.setState("empty"); return; }    // (said once, above the preview)
      if (!results.length) { chart.setState("error", firstError ? "" : "No answer for these queries"); return; }   // (an error is said beside its query)
      chart.update(results, meta);             // (the panel says for itself when they hold nothing)
    }

    function renderUnit() {
      const derived = [...new Set(draft.queries.filter(q => !q.hidden).map(q => unitOf(q, F)).filter(Boolean))];
      const now = draft.display.unit;
      const names = [...new Set([...derived, ...UNITS, ...(now ? [now] : [])])];
      const sig = JSON.stringify([derived, names]);
      if (unitSel.__sig !== sig) {
        unitSel.__sig = sig;
        unitSel.replaceChildren(h("option", { value: "" }, derived.length === 1 ? `Auto (${derived[0]})` : "Automatic"), ...names.map(n => h("option", { value: n }, n)));
      }
      unitSel.value = now || "";
    }

    function renderMessages() {
      for (const q of draft.queries) {
        const card = cards.get(q);
        if (!card) continue;
        const { missing, incomplete } = problemsOf(q, F);
        const lines = missing.map(([slot, v]) => h("div", { class: "pe-msg-bad" }, `${slot.label}: “${v}” is no longer in the model. Choose another; the panel keeps its place.`));
        if (errors.has(q.id)) lines.push(h("div", { class: "pe-msg-bad" }, errors.get(q.id)));
        if (card.showIncomplete && incomplete.length) lines.push(h("div", { class: "pe-msg-warn" }, `Still to choose: ${incomplete.map(x => x.label.toLowerCase()).join(", ")}.`));
        card.msg.replaceChildren(...lines);
      }
      renderUnit();
      renderGallery();
      renderOptions();
    }

    function renderSlots(card) {
      const slots = slotsOf(card.q, F, !!card.parent), seen = new Set();
      for (const slot of slots) {
        seen.add(slot.key);
        let c = card.slots.get(slot.key);
        if (!c) {
          c = slot.checks ? checksControl(card, slot) : slot.text ? textControl(card, slot) : selectControl(card, slot);
          card.slots.set(slot.key, c);
        }
        c.sync(slot);
        card.grid.append(c.el);          // (in slot order; append moves a node without rebuilding it)
      }
      for (const [k, c] of card.slots) if (!seen.has(k)) { c.el.remove(); card.slots.delete(k); }
    }
    function renderX(card) {
      const q = card.q, slots = F ? xSlots(q, F, draft.queries) : [], seen = new Set();
      card.xBox.hidden = !slots.length;
      for (const slot of slots) {
        seen.add(slot.key);
        let c = card.xControls.get(slot.key);
        if (!c) {
          const sel = h("select", { "data-slot": slot.key, onchange: () => pickX(card, slot.key, sel.value) });
          c = { sel, el: field(slot.label, sel) };
          card.xControls.set(slot.key, c);
        }
        fillSelect(c.sel, slot, slot.value);
        card.xBox.append(c.el);
      }
      for (const [k, c] of card.xControls) if (!seen.has(k)) { c.el.remove(); card.xControls.delete(k); }
    }
    function renderParts(card) {
      const q = card.q, on = q.source === "frequency" && !q.model;
      card.partsBox.hidden = !on;
      if (!on) { card.partsBox.replaceChildren(); card.parts = null; return; }
      if (!card.parts || card.parts.input.q !== q.input || card.parts.output.q !== q.output) {
        card.parts = { input: makePart(card, "input"), output: makePart(card, "output") };
        card.partsBox.replaceChildren(card.parts.input.root, card.parts.output.root);
      }
      for (const part of Object.values(card.parts)) {
        renderSlots(part);
        const from = draft.queries.filter(o => o !== q && o.source && o.source !== "frequency");
        fillSelect(part.from, { options: from.map(o => [o.id, `${o.id.toUpperCase()}: ${describe(o)}`]), none: "Copy from a query…" }, "");
        part.fromField.hidden = !from.length;
      }
    }
    function makePart(card, name) {
      const grid = h("div", { class: "pe-q-grid" });
      const from = h("select", { "data-slot": "from", onchange: () => {
        const other = draft.queries.find(o => o.id === from.value);
        if (!other) return;
        const { id, hidden, x, ...rest } = clone(other);
        for (const k of Object.keys(part.q)) delete part.q[k];
        Object.assign(part.q, rest);
        renderCard(card);
        say(`${PART_NAMES[name]} copied from query ${other.id.toUpperCase()}`);
        changed();
      } });
      const fromField = field(`Fill ${name} from`, from);
      const root = h("fieldset", { class: "pe-group pe-part", "data-part": name }, h("legend", { class: "pe-l" }, PART_NAMES[name]), fromField, grid);
      const part = { q: card.q[name], parent: card, root, grid, from, fromField, slots: new Map() };
      return part;
    }

    function renderCard(card) {
      const q = card.q;
      card.tag.textContent = q.id.toUpperCase();
      card.root.classList.toggle("pe-q-hidden", !!q.hidden);
      card.hide.textContent = q.hidden ? "Show" : "Hide";
      card.hide.setAttribute("aria-pressed", q.hidden ? "true" : "false");
      card.hide.setAttribute("aria-label", `${q.hidden ? "Show" : "Hide"} query ${q.id.toUpperCase()}`);
      card.dup.setAttribute("aria-label", `Duplicate query ${q.id.toUpperCase()}`);
      card.del.setAttribute("aria-label", `Remove query ${q.id.toUpperCase()}`);
      const usedAsX = draft.queries.some(o => o.x?.type === "query" && o.x.query === q.id);
      card.hide.disabled = usedAsX && !q.hidden;           // (a hidden query is not asked, and the X of another must be)
      card.hide.title = card.hide.disabled ? "Another query uses this one as its X axis" : "";
      renderSlots(card);
      renderX(card);
      renderParts(card);
    }
    function selectControl(card, slot) {
      const sel = h("select", { "data-slot": slot.key, onchange: () => pick(card, slot.key, sel.value) });
      const el = field(slot.label, sel);
      return { el, sel, sync(s) { fillSelect(sel, s, card.q[s.key]); } };
    }
    /* the query's text, in its source's own language: written, not built, and asked for as it is typed */
    /* (a language with an editor of its own, window.queryEditors, gets it: highlighted, completed, run with Ctrl+Enter) */
    function textControl(card, slot) {
      const typed = v => { card.q.text = v; errors.delete(card.q.id); changed(); };
      const run = () => { lastSig = null; clearTimeout(timer); runPreview(); };
      const ed = window.queryEditors?.[slot.language]?.({ source: slot.source, onInput: typed, onRun: run }) || null;
      const area = ed?.area || h("textarea", { "data-slot": slot.key, rows: 3, spellcheck: "false", class: "pe-text", oninput: () => typed(area.value) });
      area.id ||= `pe-control-${++controlIds}`;
      const el = h("div", { class: "pe-f pe-wide" }, h("label", { class: "pe-l", for: area.id }, slot.label), ed?.el || area);
      return { el, mark: ed?.mark, sync(s) {
        el.querySelector("label").textContent = s.label;
        if (ed) ed.set(card.q.text ?? ""); else if (area.value !== (card.q.text ?? "")) area.value = card.q.text ?? "";
      } };
    }
    function checksControl(card, slot) {
      const box = h("div", { class: "pe-checks" });
      const el = h("fieldset", { class: "pe-group pe-wide", "data-slot": slot.key }, h("legend", { class: "pe-l" }, slot.label), box);
      let sig = null;
      return {
        el,
        sync(s) {
          const chosen = card.q.where?.state || [];
          const gone = chosen.filter(v => !hasOption(s, v));
          const nextSig = JSON.stringify([s.options, gone]);
          if (nextSig !== sig) {
            sig = nextSig;
            const row = (v, text, bad) => {
              const input = h("input", { type: "checkbox", value: v, onchange: () => toggleState(card, v, input.checked) });
              return h("label", { class: "pe-seg" + (bad ? " pe-seg-missing" : "") }, input, h("span", {}, text));
            };
            box.replaceChildren(...s.options.map(([v, t]) => row(v, t, false)), ...gone.map(v => row(v, `${v} (missing)`, true)));
          }
          for (const i of box.querySelectorAll("input")) i.checked = chosen.includes(i.value);
        },
      };
    }
    function toggleState(card, value, on) {
      const q = card.q, list = new Set(q.where?.state || []);
      if (on) list.add(value); else list.delete(value);
      q.where ||= {};
      if (list.size) q.where.state = [...list]; else delete q.where.state;
      if (!Object.keys(q.where).length) delete q.where;
      renderCard(card.parent || card);
      changed();
    }
    /* the X the query has stops being one its source can answer: back to time, and said */
    function repairX(q) {
      if (!q.x) return;
      const type = q.x.type, bad = !xTypesOf(q, F).includes(type)
        || (type === "field" && !numericFields(q, F).filter(n => n !== q.field).includes(q.x.field))
        || (type === "category" && !categoriesOf(q, F).includes(q.x.by))
        || (type === "bins" && q.source === "items" && !numericFields(q, F).includes(q.x.field));
      if (!bad) return;
      delete q.x;
      settleAgg(q);
      say("The X axis went back to time: this source has no such axis");
    }
    /* what the X asks of the aggregation: none for one point per item, a count for bins, and back to the source's own */
    function settleAgg(q) {
      const type = q.x?.type || "time";
      if (q.agg === "ohlc" && type !== "time") delete q.agg;
      if (type === "field") { q.agg = "none"; delete q.transform; delete q.rate_per; delete q.window; return; }
      if (type === "bins") { q.agg = "count"; delete q.transform; delete q.rate_per; delete q.window; return; }
      if (q.agg === "none") delete q.agg;
      for (const key of ["agg", "transform"]) {
        const slot = slotsOf(q, F).find(x => x.key === key);
        if (slot && (q[key] == null || !hasOption(slot, q[key]))) { const d = defaultFor(key, q, slot); if (d != null) q[key] = d; else delete q[key]; }
      }
    }
    function setXType(q, type) {
      if (type === "time") delete q.x;
      else if (type === "query") {
        const other = draft.queries.find(o => canBeX(o, q) && o.source);
        q.x = { type, ...(other ? { query: other.id } : {}) };
      } else if (type === "field") q.x = { type, field: numericFields(q, F).find(n => n !== q.field) };
      else if (type === "category") { const c = categoriesOf(q, F); q.x = { type, by: c.includes("state") ? "state" : c[0] }; }
      else q.x = { type, bins: 20, ...(q.source === "items" ? { field: q.field || numericFields(q, F)[0] } : {}) };
      settleAgg(q);
    }
    function pickX(card, key, value) {
      const q = card.q;
      if (key === "x_type") {
        setXType(q, value);
        if (value === "query" && !q.x.query) {           // nothing to plot it against yet: a new query, to fill in
          const b = { id: nextId(draft.queries) };
          draft.queries.push(b);
          q.x.query = b.id;
          renderAll();
          cards.get(b).root.querySelector("select")?.focus();
          say(`Choose what goes on the X axis in query ${b.id.toUpperCase()}`);
          changed();
          return;
        }
      } else if (key === "x_bins") q.x.bins = Number(value);
      else q.x[{ x_query: "query", x_field: "field", x_by: "by", x_bin_field: "field" }[key]] = value || undefined;
      renderAll();
      changed();
    }
    function pick(card, key, value) {
      const dropped = choose(card.q, key, value, F, !!card.parent);
      if (key === "source" || key === "kind") errors.delete(card.q.id);
      if (!card.parent) { repairX(card.q); meetForm(card.q); }
      renderAll();
      if (dropped.length) say(`Reset what no longer applies: ${dropped.join(", ")}`);
      changed();
    }

    function makeCard(q) {
      const tag = h("span", { class: "pe-q-id" });
      const hide = h("button", { type: "button", class: "ghost", onclick: () => { q.hidden ? delete q.hidden : q.hidden = true; renderCard(card); changed(); } });
      const dup = h("button", { type: "button", class: "ghost", onclick: () => duplicate(q) }, "Duplicate");
      const del = h("button", { type: "button", class: "ghost", onclick: () => removeQuery(q) }, "Remove");
      const grid = h("div", { class: "pe-q-grid" });
      const msg = h("div", { class: "pe-q-msg", role: "status" });
      const xBox = h("div", { class: "pe-q-grid pe-x", role: "group", "aria-label": "X axis" });
      const partsBox = h("div", { class: "pe-parts" });
      const root = h("section", { class: "pe-q", "data-query": q.id },
        h("div", { class: "pe-q-head" }, tag, h("span", { class: "pe-q-title" }, "Query"), h("span", { class: "pe-q-tools" }, hide, dup, del)), grid, partsBox, xBox, msg);
      const card = { q, root, tag, hide, dup, del, grid, msg, xBox, partsBox, xControls: new Map(), parts: null, slots: new Map(), showIncomplete: false };
      cards.set(q, card);
      renderCard(card);
      return card;
    }
    function renderAll() {
      for (const [q, card] of cards) if (!draft.queries.includes(q)) { card.root.remove(); cards.delete(q); }
      for (const q of draft.queries) {
        const card = cards.get(q) || makeCard(q);
        renderCard(card);
        queriesBox.append(card.root);
      }
      renderMessages();
    }
    function addQuery() {
      const q = { id: nextId(draft.queries) };
      draft.queries.push(q);
      renderAll();
      cards.get(q).root.querySelector("select")?.focus();
      say(`Query ${q.id.toUpperCase()} added`);
      changed();
    }
    function duplicate(q) {
      const copy = { ...clone(q), id: nextId(draft.queries) };
      if (copy.x?.type === "query" && copy.x.query === copy.id) delete copy.x;
      draft.queries.splice(draft.queries.indexOf(q) + 1, 0, copy);
      renderAll();
      cards.get(copy).dup.focus();
      say(`Query ${q.id.toUpperCase()} duplicated as ${copy.id.toUpperCase()}`);
      changed();
    }
    function removeQuery(q) {
      const at = draft.queries.indexOf(q);
      draft.queries.splice(at, 1);
      errors.delete(q.id);
      for (const o of draft.queries) if (o.x?.type === "query" && o.x.query === q.id) { delete o.x; settleAgg(o); }
      if (!draft.queries.length) draft.queries.push({ id: nextId([]) });
      renderAll();
      const next = draft.queries[Math.min(at, draft.queries.length - 1)];
      (cards.get(next).del || addBtn).focus();
      say(`Query ${q.id.toUpperCase()} removed`);
      changed();
    }

    const setDisplay = (key, value) => {
      if (value === "" || value == null) delete draft.display[key]; else draft.display[key] = value;
      changed();
    };
    const titleIn = h("input", { type: "text", value: draft.title || "", oninput: () => { draft.title = titleIn.value; changed(); } });
    const unitSel = h("select", { onchange: () => setDisplay("unit", unitSel.value) });
    const decSel = h("select", { onchange: () => setDisplay("decimals", decSel.value === "" ? null : Number(decSel.value)) },
      h("option", { value: "" }, "Automatic"), [0, 1, 2, 3, 4].map(n => h("option", { value: n }, String(n))));
    decSel.value = draft.display.decimals ?? "";
    const legendSel = h("select", { onchange: () => setDisplay("legend", legendSel.value) }, LEGENDS.map(([v, t]) => h("option", { value: v }, t)));
    legendSel.value = draft.display.legend || "";
    const legendValues = h("div", { class: "pe-checks" }, LEGEND_VALUES.map(([v, t]) => {
      const input = h("input", { type: "checkbox", value: v, onchange: () => {
        const on = new Set(draft.display.legend_values || []);
        if (input.checked) on.add(v); else on.delete(v);
        setDisplay("legend_values", on.size ? LEGEND_VALUES.map(x => x[0]).filter(x => on.has(x)) : null);
      } });
      input.checked = (draft.display.legend_values || []).includes(v);
      return h("label", { class: "pe-seg" }, input, h("span", {}, t));
    }));

    const y = draft.display.y || {};
    const yMin = h("input", { type: "number", step: "any", value: y.min ?? "", oninput: () => applyY() });
    const yMax = h("input", { type: "number", step: "any", value: y.max ?? "", oninput: () => applyY() });
    const yLog = h("input", { type: "checkbox", onchange: () => applyY() });
    yLog.checked = !!y.log;
    const yMsg = h("div", { class: "pe-msg-bad", role: "status" });
    const numberOf = input => (input.value.trim() === "" ? null : Number(input.value));
    function yProblem() {
      const lo = numberOf(yMin), hi = numberOf(yMax);
      if (lo != null && hi != null && lo >= hi) return ["The minimum must be below the maximum.", yMin];
      if (yLog.checked && lo != null && lo <= 0) return ["A log scale needs a minimum above 0.", yMin];
      if (yLog.checked && hi != null && hi <= 0) return ["A log scale needs a maximum above 0.", yMax];
      return null;
    }
    function applyY() {
      const bad = yProblem();
      yMsg.textContent = bad ? bad[0] : "";
      for (const i of [yMin, yMax]) i.removeAttribute("aria-invalid");
      if (bad) { bad[1].setAttribute("aria-invalid", "true"); return; }
      const lo = numberOf(yMin), hi = numberOf(yMax);
      if (lo == null && hi == null && !yLog.checked) delete draft.display.y;
      else draft.display.y = { ...(draft.display.y || {}), min: lo, max: hi, log: yLog.checked };
      changed();
    }

    const xd = draft.display.x || {};
    const xMin = h("input", { type: "number", step: "any", value: xd.min ?? "", oninput: () => applyXDisplay() });
    const xMax = h("input", { type: "number", step: "any", value: xd.max ?? "", oninput: () => applyXDisplay() });
    const xLog = h("input", { type: "checkbox", onchange: () => applyXDisplay() });
    xLog.checked = !!xd.log;
    const xLabel = h("input", { type: "text", value: xd.label || "", oninput: () => applyXDisplay() });
    const xMsg = h("div", { class: "pe-msg-bad", role: "status" });
    function xProblem() {
      const lo = numberOf(xMin), hi = numberOf(xMax);
      if (lo != null && hi != null && lo >= hi) return ["The X axis must start below where it ends.", xMin];
      if (xLog.checked && lo != null && lo <= 0) return ["A log X axis must start above 0.", xMin];
      if (xLog.checked && hi != null && hi <= 0) return ["A log X axis must end above 0.", xMax];
      return null;
    }
    function applyXDisplay() {
      const bad = xProblem();
      xMsg.textContent = bad ? bad[0] : "";
      for (const i of [xMin, xMax]) i.removeAttribute("aria-invalid");
      if (bad) { bad[1].setAttribute("aria-invalid", "true"); return; }
      const lo = numberOf(xMin), hi = numberOf(xMax), label = xLabel.value.trim();
      if (lo == null && hi == null && !xLog.checked && !label) delete draft.display.x;
      else draft.display.x = { min: lo, max: hi, log: xLog.checked, ...(label ? { label } : {}) };
      changed();
    }

    /* the gallery of chart families, grouped as they registered; one that cannot draw this is disabled, its reason in its tooltip */
    const formTiles = new Map();
    const formGuide = h("div", { class: "pe-form-guide", role: "status" });     // (the chart's one error, above the preview)
    const guideText = h("span", {});
    const guideBtn = h("button", { type: "button", onclick: () => setUpForm(true) }, "Set it up");
    formGuide.append(guideText, guideBtn);
    const currentProblem = () => { const now = formTiles.get(draft.form) || (forms.has(draft.form) ? { reg: forms.get(draft.form) } : null); return now ? formProblem(now.reg, draft.queries, lastAnswer) : null; };
    function makeGallery() {
      const groups = [...FORM_GROUPS];
      for (const reg of forms.values()) if (reg.group && !groups.some(g => g[0] === reg.group)) groups.push([reg.group, words(reg.group)]);
      const known = new Set(groups.map(g => g[0]));
      const sections = [];
      for (const [group, title] of [...groups, [null, "Other"]]) {
        const members = [...forms].filter(([, reg]) => (group === null ? !known.has(reg.group) : reg.group === group));
        if (!members.length) continue;
        const tiles = members.map(([name, reg]) => {
          const input = h("input", { type: "radio", name: uid + "-form", value: name, onchange: () => pickForm(name) });
          input.checked = name === draft.form;
          const tile = h("label", { class: "pe-seg pe-form", "data-form": name, onpointerdown: () => { pointerPick = true; } },
            input, formIcon(reg, name), h("span", { class: "pe-form-name" }, reg.label || words(name)));
          formTiles.set(name, { tile, input, reg });
          return tile;
        });
        sections.push(h("div", { class: "pe-form-group" }, h("div", { class: "pe-l" }, title), h("div", { class: "pe-segs pe-gallery" }, tiles)));
      }
      return h("fieldset", { class: "pe-group", onkeydown: ev => {
        pointerPick = false;
        if (ev.key === "Enter" && ev.target.type === "radio") { ev.preventDefault(); setUpForm(true); }
      }, "aria-label": "Chart" }, sections);
    }
    function renderGallery() {
      const judged = draft.queries.some(q => q.source && !q.hidden);     // (with nothing asked yet every form is open, and sets its queries up)
      for (const [name, t] of formTiles) {
        const why = judged ? formProblem(t.reg, draft.queries, lastAnswer) : null;
        t.input.checked = name === draft.form;
        t.input.disabled = !!why;
        t.tile.classList.toggle("pe-form-blocked", !!why);
        t.input.setAttribute("aria-description", why || "");
        t.tile.title = why || "";
      }
      const why = currentProblem(), now = formTiles.get(draft.form);
      pickOpen.disabled = !lastAnswer?.results?.length;
      pickOpen.title = pickOpen.disabled ? "Finish a query to see its charts" : "";
      formGuide.hidden = !why;
      guideText.textContent = why || "";
      guideBtn.hidden = !why || !canSetUp(now?.reg);
    }
    function canSetUp(reg) { const n = reg?.needs || {}; return !!(n.source === "frequency" || n.x?.length); }
    /* the options a change to form ``name`` keeps: what still applies stays, the rest goes */
    function keptOptions(name) {
      const schema = new Map((forms.get(name)?.options || []).map(o => [o.key, o]));
      const out = {};
      for (const [key, value] of Object.entries(draft.options || {})) {
        const o = schema.get(key);
        if (o && (o.type !== "choice" || (o.choices || []).some(c => String(choiceOf(c)[0]) === String(value)))) out[key] = value;
      }
      return Object.keys(out).length ? out : undefined;
    }
    function pickForm(name) {
      const next = forms.get(name);
      draft.form = name;
      const kept = keptOptions(name);
      if (kept) draft.options = kept; else delete draft.options;
      const wants = next?.needs?.agg || (name === "candlestick" ? "ohlc" : null);
      for (const q of draft.queries) {
        if (!q.source || q.source === "frequency") continue;
        if (wants) { if ((q.x?.type || "time") === "time" && (q.source === "items" || q.source === "series")) { q.agg = wants; q.transform = "none"; delete q.rate_per; delete q.window; } }
        else if (q.agg === "ohlc") { delete q.agg; settleAgg(q); }
      }
      if (pointerPick) setUpForm(false);                // (by arrow keys a form is only passed over: Enter or the button sets it up)
      pointerPick = false;
      renderAll();
      changed();
    }
    /* make the data fit the chosen form, as far as the form says how, and put the person where the rest is chosen */
    function setUpForm(render) {
      const reg = forms.get(draft.form), n = reg?.needs || {};
      const empty = !draft.queries.some(q => q.source);
      if (!formProblem(reg || {}, draft.queries, lastAnswer) && !(empty && n.x?.length && !n.x.includes("time"))) return;
      let focusOn = null;
      if (n.source === "frequency") focusOn = setUpFrequency();
      else if (n.x?.length) {
        let q = draft.queries.find(o => o.source !== "frequency" && !o.hidden);
        if (!q) { q = { id: nextId(draft.queries) }; draft.queries.push(q); }   // (a frequency query has no X to change: it stays)
        focusOn = setUpX(q, n.x);
      }
      if (render) { renderAll(); changed(); }
      if (focusOn) { renderAll(); setTimeout(() => { if (!closed) focusOn(); }); }   // (after the click has finished placing focus)
    }
    function setUpX(q, types) {
      const type = types.find(t => !q.source || xTypesOf(q, F).includes(t));
      if (!type) return null;
      if (!q.source && type !== "query") { say("Choose a source for this query, and its X axis follows"); return () => cards.get(q).root.querySelector("select")?.focus(); }
      setXType(q, type);
      if (type !== "query" || q.x.query) return null;
      const b = { id: nextId(draft.queries) };
      draft.queries.push(b);
      q.x.query = b.id;
      say(`Choose what goes on the X axis in query ${b.id.toUpperCase()}`);
      return () => cards.get(b).root.querySelector("select")?.focus();
    }
    function setUpFrequency() {
      const done = draft.queries.filter(q => q.source && q.source !== "frequency" && !q.hidden);
      const copy = q => { if (!q) return {}; const { id, hidden, x, ...rest } = clone(q); return rest; };
      const blank = draft.queries.find(q => !q.source);
      const f = blank || { id: nextId(draft.queries) };
      Object.assign(f, { source: "frequency", input: copy(done[0]), output: copy(done[1]), segments: 4 });
      if (!blank) draft.queries.push(f);
      for (const q of done) q.hidden = true;           // what it was built from stays, hidden, to go back to
      for (const q of done) for (const o of draft.queries) if (o.x?.query === q.id) { delete o.x; settleAgg(o); }
      say("Frequency response: choose the input and the output");
      return () => {
        const part = !f.input.source ? "input" : !f.output.source ? "output" : null;
        (part ? cards.get(f).root.querySelector(`[data-part=${part}] select[data-slot=source]`) : cards.get(f).root.querySelector("select"))?.focus();
      };
    }
    /* a query just got its source: if the chosen form asks for an X it can take without a question, it takes it */
    function meetForm(q) {
      const n = forms.get(draft.form)?.needs || {};
      if (!q.source || q.source === "frequency" || draft.queries.some(o => o.x?.type === "query" && o.x.query === q.id)) return;
      if (n.agg && (q.x?.type || "time") === "time" && (q.source === "items" || q.source === "series") && !q.agg) q.agg = n.agg;
      if (!n.x?.length || n.x.includes(q.x?.type || "time")) return;
      const type = n.x.find(t => t !== "query" && xTypesOf(q, F).includes(t));
      if (type && (type !== "bins" || q.source !== "items" || q.field)) setXType(q, type);
    }

    /* the charts the current result can be drawn as, each drawn with the answer the preview has; the one clicked is chosen */
    const pickOpen = h("button", { type: "button", class: "pe-pick-open", onclick: () => openPicker() }, "Charts of this data…");
    let picker = null;
    function openPicker() {
      if (picker || !lastAnswer?.results?.length) return;
      const base = previewConfig(), { results, meta } = lastAnswer;
      const grid = h("div", { class: "pe-pick-grid" });
      const box = h("div", { class: "pe-pick", role: "dialog", "aria-modal": "true", "aria-label": "Charts of this data" },
        h("div", { class: "pe-pick-head" }, h("h3", {}, "Charts of this data"), h("button", { type: "button", onclick: () => closePicker() }, "Close")), grid);
      picker = { box, charts: [] };
      root.append(box);
      for (const [name, reg] of forms) {
        if (!formFits(reg, draft.queries, lastAnswer)) continue;
        const one = chartPanel({ ...base, id: `${uid}-pick-${name}`, form: name, options: keptOptions(name) });
        const label = reg.label || words(name);
        const card = h("div", { class: "pe-pick-card", "data-form": name, onclick: () => choosePicked(name) },
          h("div", { class: "pe-pick-chart", inert: "" }, one), h("button", { type: "button", "aria-label": `Use ${label}` }, label));
        grid.append(card);
        picker.charts.push(one);
        one.update(results, meta);
        if (["empty", "error"].includes(one.dataset.state)) { card.remove(); one.destroy?.(); }   // (its own check found it cannot draw this)
      }
      if (!grid.childElementCount) grid.append(h("p", {}, "No chart can draw this result."));
      (grid.querySelector("button") || box.querySelector("button")).focus();
    }
    function closePicker(focus = pickOpen) {
      if (!picker) return;
      for (const c of picker.charts) c.destroy?.();
      picker.box.remove();
      picker = null;
      if (focus?.isConnected) focus.focus();
    }
    function choosePicked(name) {
      pointerPick = false;
      closePicker(formTiles.get(name)?.input);
      if (draft.form !== name) pickForm(name);
      say(`${forms.get(name)?.label || words(name)} chosen`);
    }

    /* the options of the chosen family, drawn from what it registered: a new family needs nothing here */
    const optionsBox = h("div", { class: "pe-options" });
    const optionsHead = h("h3", {}, "Chart options");
    const optionControls = new Map();
    const optionValue = o => draft.options?.[o.key] ?? o.default;
    function setOption(o, value) {
      draft.options ||= {};
      if (value == null || value === "" || value === o.default) delete draft.options[o.key]; else draft.options[o.key] = value;
      if (!Object.keys(draft.options).length) delete draft.options;
      changed();
    }
    function fieldChoices(o) {
      const names = new Set();
      for (const q of draft.queries) for (const n of numericFields(q, F)) names.add(n);
      const out = (o.choices || []).map(choiceOf);
      if (o.default != null && !out.some(([v]) => String(v) === String(o.default))) out.unshift([o.default, words(o.default)]);
      for (const n of names) if (!out.some(([v]) => String(v) === n)) out.push([n, n]);
      return out;
    }
    function optionControl(o) {
      if (o.type === "bool") {
        const input = h("input", { type: "checkbox", "data-option": o.key, onchange: () => setOption(o, input.checked) });
        return { el: h("label", { class: "check" }, input, o.label || words(o.key)), sync() { input.checked = !!optionValue(o); } };
      }
      if (o.type === "number") {
        const input = h("input", { type: "number", step: o.step ?? "any", "data-option": o.key, placeholder: o.default == null ? "Auto" : String(o.default),
          ...(o.min != null ? { min: o.min } : {}), ...(o.max != null ? { max: o.max } : {}), oninput: () => {
            const v = input.value.trim() === "" ? null : Number(input.value);
            const bad = v != null && (!Number.isFinite(v) || (o.min != null && v < o.min) || (o.max != null && v > o.max));
            if (bad) { input.setAttribute("aria-invalid", "true"); return; }
            input.removeAttribute("aria-invalid");
            setOption(o, v);
          } });
        return { el: field(o.label || words(o.key), input), sync() { if (document.activeElement !== input) input.value = draft.options?.[o.key] ?? ""; } };
      }
      const sel = h("select", { "data-option": o.key, onchange: () => {
        const found = current().find(([v]) => String(v) === sel.value);
        setOption(o, found ? found[0] : sel.value);
      } });
      const current = () => (o.type === "field" ? fieldChoices(o) : (o.choices || []).map(choiceOf));
      return { el: field(o.label || words(o.key), sel), sync() { fillSelect(sel, { options: current(), required: true }, optionValue(o)); } };
    }
    function renderOptions() {
      const list = (forms.get(draft.form)?.options || []).filter(o => applies(o, draft));
      const wanted = new Set(list.map(o => `${draft.form}/${o.key}`));
      for (const [k, c] of optionControls) if (!wanted.has(k)) { c.el.remove(); optionControls.delete(k); }
      for (const o of list) {
        const k = `${draft.form}/${o.key}`;
        let c = optionControls.get(k);
        if (!c) { c = optionControl(o); optionControls.set(k, c); }
        c.sync();
        optionsBox.append(c.el);
      }
      optionsHead.hidden = optionsBox.hidden = !list.length;
    }

    const thresholdRows = (draft.display.thresholds || []).map(t => ({ ...t }));
    const thresholdsBox = h("div", { class: "pe-thresholds" });
    function applyThresholds() {
      const list = thresholdRows.filter(t => t.value !== "" && t.value != null && Number.isFinite(Number(t.value))).map(t => ({ ...t, value: Number(t.value) }));
      if (list.length) draft.display.thresholds = list; else delete draft.display.thresholds;
      changed();
    }
    function renderThresholds(focusRow = null) {
      thresholdsBox.replaceChildren(...thresholdRows.map((t, i) => {
        const value = h("input", { type: "number", step: "any", value: t.value ?? "", "aria-label": `Threshold ${i + 1} value`, oninput: () => { t.value = value.value; applyThresholds(); } });
        const label = h("input", { type: "text", value: t.label || "", "aria-label": `Threshold ${i + 1} label`, placeholder: "Label", oninput: () => { t.label = label.value; applyThresholds(); } });
        const del = h("button", { type: "button", class: "ghost", "aria-label": `Remove threshold ${i + 1}`, onclick: () => {
          thresholdRows.splice(i, 1);
          renderThresholds();
          applyThresholds();
          (thresholdsBox.querySelector("input") || addThreshold).focus();
        } }, "Remove");
        if (focusRow === i) queueMicrotask(() => value.focus());
        return h("div", { class: "pe-threshold" }, value, label, del);
      }));
    }
    const addThreshold = h("button", { type: "button", onclick: () => { thresholdRows.push({ value: "", label: "" }); renderThresholds(thresholdRows.length - 1); } }, "Add threshold");
    renderThresholds();

    const addBtn = h("button", { type: "button", class: "pe-add", onclick: addQuery }, "Add query");
    const cancelBtn = h("button", { type: "button", onclick: cancel }, "Cancel");
    const saveBtn = h("button", { type: "button", class: "pe-primary", onclick: save }, "Save");
    const tallIn = h("input", { type: "checkbox", onchange: () => { draft.tall = tallIn.checked; changed(); } });
    tallIn.checked = !!draft.tall;
    /* a repeated panel: one on the dashboard for each series a query answers with (its label's values), or for each
       value of a variable the draft names; the choices are read when the list is opened, so they follow the queries */
    const repeatSel = h("select", { onchange: () => {
      const v = repeatSel.value;
      if (!v) delete draft.repeat; else draft.repeat = v.startsWith("$") ? { var: v.slice(1) } : { query: v };
      changed();
    } });
    function fillRepeat() {
      const asIs = draft.repeat?.var ? `$${draft.repeat.var}` : draft.repeat?.query ?? "";
      const opts = [["", "No"], ...(draft.queries || []).filter((q) => q.id != null).map((q) => [String(q.id), `One per series of query ${q.label || q.id}`])];
      if (draft.repeat?.var) opts.push([asIs, `One per value of $${draft.repeat.var}`]);
      repeatSel.replaceChildren(...opts.map(([v, text]) => h("option", { value: v }, text)));
      repeatSel.value = asIs;
    }
    repeatSel.addEventListener("focus", fillRepeat);
    fillRepeat();

    const side = h("div", { class: "pe-side" },
      h("h3", {}, "Panel"),
      field("Title", titleIn),
      h("h3", {}, "Chart"), pickOpen, makeGallery(),
      optionsHead, optionsBox,
      h("h3", {}, "Values"),
      h("div", { class: "pe-two" }, field("Unit", unitSel), field("Decimals", decSel)),
      h("h3", {}, "Legend"),
      field("Position", legendSel),
      h("fieldset", { class: "pe-group" }, h("legend", { class: "pe-l" }, "Values shown"), legendValues),
      h("h3", {}, "X axis"),
      h("div", { class: "pe-two" }, field("X from", xMin), field("X to", xMax)),
      field("X label", xLabel),
      h("label", { class: "check" }, xLog, "Log X axis"), xMsg,
      h("h3", {}, "Y axis"),
      h("div", { class: "pe-two" }, field("Minimum", yMin), field("Maximum", yMax)),
      h("label", { class: "check" }, yLog, "Log scale"), yMsg,
      h("h3", {}, "Thresholds"), thresholdsBox, addThreshold,
      h("h3", {}, "Width"),
      radios(uid + "-size", "Width on the dashboard", SIZES, draft.size, v => { draft.size = v; changed(); }),
      h("label", { class: "check" }, tallIn, "Double height"),
      h("h3", {}, "Repeat"), field("Repeat", repeatSel));

    const root = h("div", { class: "pe-overlay", role: "dialog", "aria-modal": "true", "aria-label": "Edit panel", onkeydown: onKey },
      h("header", { class: "pe-head" }, h("h2", {}, "Edit panel"), saveMsg, h("span", { class: "pe-actions" }, cancelBtn, saveBtn)),
      h("div", { class: "pe-body" },
        h("div", { class: "pe-main" }, formGuide, previewBox, h("div", { class: "pe-query-area" }, fieldsMsg, queriesBox, addBtn)),
        side),
      live);

    function onKey(ev) {
      if (ev.key === "Escape") { ev.preventDefault(); ev.stopPropagation(); if (picker) closePicker(); else cancel(); return; }
      if (ev.key !== "Tab") return;
      const scope = picker?.box || root;
      const items = [...scope.querySelectorAll(FOCUSABLE)].filter(el => el.getClientRects().length && !el.closest("[inert]"));
      if (!items.length) return;
      const first = items[0], last = items[items.length - 1], at = document.activeElement;
      if (ev.shiftKey && (at === first || !scope.contains(at))) { ev.preventDefault(); last.focus(); }
      else if (!ev.shiftKey && (at === last || !scope.contains(at))) { ev.preventDefault(); first.focus(); }
    }

    const inerted = [...document.body.children].filter(el => el !== root && !el.inert && el.tagName !== "SCRIPT");
    const bodyOverflow = document.body.style.overflow;
    function close() {
      closed = true;
      clearTimeout(timer);
      if (openEditor === handle) openEditor = null;
      closePicker(null);
      chart.destroy?.();
      root.remove();
      for (const el of inerted) el.inert = false;
      document.body.style.overflow = bodyOverflow;
      if (opener?.isConnected) opener.focus?.();
    }
    function cancel() {
      if (closed) return;
      close();
      onCancel?.(clone(original));
    }
    function save() {
      if (closed) return;
      saveMsg.textContent = "";
      const bad = yProblem();
      if (bad) { saveMsg.textContent = bad[0]; bad[1].focus(); return; }
      const badX = xProblem();
      if (badX) { saveMsg.textContent = badX[0]; badX[1].focus(); return; }
      for (const q of draft.queries) {
        const target = q.x?.type === "query" ? draft.queries.find(o => o.id === q.x.query) : null;
        if (q.source && q.x?.type === "query" && q.x.query && !target?.source) {
          saveMsg.textContent = `Query ${q.id.toUpperCase()}: choose what goes on its X axis in query ${q.x.query.toUpperCase()}.`;
          (target ? cards.get(target).root.querySelector("select") : cards.get(q).root.querySelector("[data-slot=x_query]"))?.focus();
          return;
        }
      }
      for (const q of draft.queries) {
        const card = cards.get(q);
        card.showIncomplete = !!q.source;
        const gap = q.source ? problemsOf(q, F).incomplete[0] : null;
        if (gap) {
          renderMessages();
          saveMsg.textContent = `Query ${q.id.toUpperCase()}: choose ${gap.label.toLowerCase()}.`;
          card.root.querySelector(`${gap.part ? `[data-part=${gap.part}] ` : ""}[data-slot="${gap.key}"]`)?.focus();
          return;
        }
      }
      const out = clone(draft);
      out.queries = out.queries.filter(q => q.source);       // a query nothing was chosen in is not part of the panel
      const schema = forms.get(out.form)?.options || [];
      for (const o of schema) if (out.options?.[o.key] !== undefined && !applies(o, out)) delete out.options[o.key];
      if (out.options && !Object.keys(out.options).length) delete out.options;
      close();
      onSave?.(out);
    }
    async function loadFields() {
      fieldsMsg.hidden = true;
      try {
        F = await queryFields();
      } catch (e) {
        if (closed) return;
        fieldsMsg.hidden = false;
        fieldsMsg.replaceChildren(`The list of fields could not be read: ${e?.message || e}. `,
          h("button", { type: "button", onclick: loadFields }, "Try again"));
        return;
      }
      if (closed) return;
      renderAll();
      runPreview();
      if (!root.contains(document.activeElement) || (document.activeElement === titleIn && !titleIn.value)) initialFocus();
    }
    function initialFocus() {
      const blank = draft.queries.find(q => !q.source);
      (blank ? cards.get(blank).root.querySelector("select") : titleIn).focus();
    }

    const handle = { cancel, save, get config() { return clone(draft); } };
    openEditor = handle;
    for (const el of inerted) el.inert = true;
    document.body.style.overflow = "hidden";
    document.body.append(root);
    renderAll();
    titleIn.focus();
    chart.setState("loading");
    loadFields();
    return handle;
  }
  window.openPanelEditor = openPanelEditor;
})();
