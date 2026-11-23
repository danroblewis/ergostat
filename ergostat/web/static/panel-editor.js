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
  const FORMS = [["line", "Line"], ["area", "Area"], ["stacked", "Stacked"], ["bars", "Bars"], ["stat", "Stat"], ["table", "Table"]];
  const SIZES = [["s", "Third"], ["m", "Half"], ["l", "Two thirds"], ["full", "Full"]];
  const LEGENDS = [["", "Automatic"], ["right", "Right"], ["bottom", "Below"], ["hidden", "Hidden"]];
  const LEGEND_VALUES = [["last", "Last"], ["min", "Min"], ["max", "Max"], ["avg", "Average"]];
  const UNITS = ["items", "items/h", "events", "usd", "usd/h", "s", "%", "bytes", "tokens"];
  const ORDER = ["source", "kind", "field", "measure", "state", "series", "type", "where", "group_by", "agg", "transform", "rate_per", "window"];
  const FOCUSABLE = "a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex='-1'])";
  const clone = v => (v === undefined ? v : JSON.parse(JSON.stringify(v)));
  const pairs = names => names.map(n => [n, n]);
  const nameOf = x => (typeof x === "string" ? x : x?.name);

  function kindsOf(src) { return Array.isArray(src?.kinds) ? src.kinds : Object.keys(src?.kinds || {}); }
  function kindOf(q, F) { const k = F?.sources?.[q.source]?.kinds; return k && !Array.isArray(k) ? k[q.kind] || null : null; }
  function statesFor(q, F) { return kindOf(q, F)?.states || F?.sources?.items?.kinds?.[q.kind]?.states || []; }

  function aggNames(q, F) {
    const offered = F?.aggregations || [];
    const only = list => list.filter(a => offered.includes(a));
    if (q.source === "events" || (q.source === "moves" && q.measure !== "time_in_state")) return only(["count"]);
    if (q.source === "moves") return only(["avg", "min", "max", "p50", "p90", "p95", "p99"]);
    if (q.source === "series") return offered.filter(a => a !== "count");
    return offered;
  }
  function transformNames(q, F) {
    const accumulates = q.source !== "counts" && (["count", "sum"].includes(q.agg) || (q.source === "series" && q.agg === "last"));
    return (F?.transforms || []).filter(t => accumulates || !["rate", "cumulative"].includes(t));
  }

  /* what this query can be asked, in order, given what it has chosen so far */
  function slotsOf(q, F) {
    if (!F) return [{ key: "source", label: "Source", options: SOURCES, required: true, locked: true }];   // (until the fields are read)
    const offered = SOURCES.filter(([n]) => F.sources?.[n]);
    const out = [{ key: "source", label: "Source", options: offered, required: true }];
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
    if (q.source !== "counts") out.push({ key: "agg", label: "Aggregation", options: aggNames(q, F).map(a => [a, AGGS[a] || a]), required: true });
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
    return slot.required && slot.options.length === 1 ? slot.options[0][0] : undefined;
  }
  /* a choice was made at ``key``: everything after it that no longer applies goes, and what has one answer takes it */
  function choose(q, key, value, F) {
    if (value === "" || value == null) delete q[key]; else q[key] = key === "window" ? Number(value) : value;
    if (key === "source") delete q.where;
    const dropped = [];
    for (const k of ORDER.slice(ORDER.indexOf(key) + 1)) {
      const slot = slotsOf(q, F).find(x => x.key === k);
      if (!slot) { if (q[k] != null) dropped.push(k); delete q[k]; continue; }
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
    return dropped;
  }
  /* what is wrong with a query: a value the model no longer has, or a choice not made yet */
  function problemsOf(q, F) {
    const missing = [], incomplete = [];
    if (!F) return { missing, incomplete };
    for (const slot of slotsOf(q, F)) {
      if (slot.checks) { for (const v of q.where?.state || []) if (!hasOption(slot, v)) missing.push([slot, v]); continue; }
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
    draft.form ||= "line";
    draft.size ||= "m";
    draft.display ||= {};
    if (!Array.isArray(draft.queries) || !draft.queries.length) draft.queries = [{ id: "a" }];
    for (const q of draft.queries) q.id ||= nextId(draft.queries);
    const uid = "pe" + Date.now().toString(36);
    const opener = document.activeElement;
    let F = null, closed = false, timer = null, seq = 0, inFlight = false, lastSig = null, lastAnswer = null;
    const errors = new Map(), cards = new Map();

    const live = h("div", { class: "pe-live", "aria-live": "polite" });
    const say = text => { live.textContent = text; };
    const saveMsg = h("span", { class: "pe-save-msg", role: "alert" });
    const previewBox = h("div", { class: "pe-preview", role: "region", "aria-label": "Preview" });
    const queriesBox = h("div", { class: "pe-queries" });
    const fieldsMsg = h("div", { class: "pe-fields-msg", role: "alert", hidden: true });

    function previewConfig() {
      const queries = draft.queries.filter(q => {
        if (!q.source || q.hidden) return false;
        const p = problemsOf(q, F);
        return !p.missing.length && !p.incomplete.length;
      }).map(q => { const c = clone(q); delete c.hidden; return c; });
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
        chart.setState("empty", draft.queries.some(q => q.hidden) ? "Every query is hidden" : "Choose what to show in a query below");
        return;
      }
      const sig = JSON.stringify(cfg.queries);
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
      renderMessages();
      lastAnswer = { results: results.filter(r => !r.error), meta: got.meta, firstError: results.find(r => r.error)?.error };
      chart.setConfig({ ...previewConfig(), queries: cfg.queries });
      draw(lastAnswer);
    }
    function draw({ results, meta, firstError }) {
      if (!results.length) { chart.setState("error", firstError || "No answer for these queries"); return; }
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
    }

    function renderCard(card) {
      const q = card.q, slots = slotsOf(q, F), seen = new Set();
      card.tag.textContent = q.id.toUpperCase();
      card.root.classList.toggle("pe-q-hidden", !!q.hidden);
      card.hide.textContent = q.hidden ? "Show" : "Hide";
      card.hide.setAttribute("aria-pressed", q.hidden ? "true" : "false");
      card.hide.setAttribute("aria-label", `${q.hidden ? "Show" : "Hide"} query ${q.id.toUpperCase()}`);
      card.dup.setAttribute("aria-label", `Duplicate query ${q.id.toUpperCase()}`);
      card.del.setAttribute("aria-label", `Remove query ${q.id.toUpperCase()}`);
      for (const slot of slots) {
        seen.add(slot.key);
        let c = card.slots.get(slot.key);
        if (!c) {
          c = slot.checks ? checksControl(card, slot) : selectControl(card, slot);
          card.slots.set(slot.key, c);
        }
        c.sync(slot);
        card.grid.append(c.el);          // (in slot order; append moves a node without rebuilding it)
      }
      for (const [k, c] of card.slots) if (!seen.has(k)) { c.el.remove(); card.slots.delete(k); }
    }
    function selectControl(card, slot) {
      const sel = h("select", { "data-slot": slot.key, onchange: () => pick(card, slot.key, sel.value) });
      const el = field(slot.label, sel);
      return { el, sel, sync(s) { fillSelect(sel, s, card.q[s.key]); } };
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
      renderCard(card);
      changed();
    }
    function pick(card, key, value) {
      const dropped = choose(card.q, key, value, F);
      if (key === "source" || key === "kind") errors.delete(card.q.id);
      renderCard(card);
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
      const root = h("section", { class: "pe-q", "data-query": q.id },
        h("div", { class: "pe-q-head" }, tag, h("span", { class: "pe-q-title" }, "Query"), h("span", { class: "pe-q-tools" }, hide, dup, del)), grid, msg);
      const card = { q, root, tag, hide, dup, del, grid, msg, slots: new Map(), showIncomplete: false };
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
    const noteIn = h("input", { type: "text", value: draft.note || "", oninput: () => { draft.note = noteIn.value; changed(); } });
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

    const side = h("div", { class: "pe-side" },
      h("h3", {}, "Panel"),
      field("Title", titleIn), field("Note", noteIn),
      radios(uid + "-form", "Chart", FORMS, draft.form, v => { draft.form = v; changed(); }),
      h("h3", {}, "Values"),
      h("div", { class: "pe-two" }, field("Unit", unitSel), field("Decimals", decSel)),
      h("h3", {}, "Legend"),
      field("Position", legendSel),
      h("fieldset", { class: "pe-group" }, h("legend", { class: "pe-l" }, "Values shown"), legendValues),
      h("h3", {}, "Y axis"),
      h("div", { class: "pe-two" }, field("Minimum", yMin), field("Maximum", yMax)),
      h("label", { class: "check" }, yLog, "Log scale"), yMsg,
      h("h3", {}, "Thresholds"), thresholdsBox, addThreshold,
      h("h3", {}, "Width"),
      radios(uid + "-size", "Width on the dashboard", SIZES, draft.size, v => { draft.size = v; changed(); }),
      h("label", { class: "check" }, tallIn, "Double height"));

    const root = h("div", { class: "pe-overlay", role: "dialog", "aria-modal": "true", "aria-label": "Edit panel", onkeydown: onKey },
      h("header", { class: "pe-head" }, h("h2", {}, "Edit panel"), saveMsg, h("span", { class: "pe-actions" }, cancelBtn, saveBtn)),
      h("div", { class: "pe-body" },
        h("div", { class: "pe-main" }, previewBox, h("div", { class: "pe-query-area" }, fieldsMsg, queriesBox, addBtn)),
        side),
      live);

    function onKey(ev) {
      if (ev.key === "Escape") { ev.preventDefault(); ev.stopPropagation(); cancel(); return; }
      if (ev.key !== "Tab") return;
      const items = [...root.querySelectorAll(FOCUSABLE)].filter(el => el.getClientRects().length);
      if (!items.length) return;
      const first = items[0], last = items[items.length - 1], at = document.activeElement;
      if (ev.shiftKey && (at === first || !root.contains(at))) { ev.preventDefault(); last.focus(); }
      else if (!ev.shiftKey && (at === last || !root.contains(at))) { ev.preventDefault(); first.focus(); }
    }

    const inerted = [...document.body.children].filter(el => el !== root && !el.inert && el.tagName !== "SCRIPT");
    const bodyOverflow = document.body.style.overflow;
    function close() {
      closed = true;
      clearTimeout(timer);
      if (openEditor === handle) openEditor = null;
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
      for (const q of draft.queries) {
        const card = cards.get(q);
        card.showIncomplete = !!q.source;
        const gap = q.source ? problemsOf(q, F).incomplete[0] : null;
        if (gap) {
          renderMessages();
          saveMsg.textContent = `Query ${q.id.toUpperCase()}: choose ${gap.label.toLowerCase()}.`;
          card.grid.querySelector(`[data-slot="${gap.key}"]`)?.focus();
          return;
        }
      }
      const out = clone(draft);
      out.queries = out.queries.filter(q => q.source);       // a query nothing was chosen in is not part of the panel
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
