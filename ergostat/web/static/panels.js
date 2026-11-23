/* one chart panel, drawn from a query and display options, and the batched asking for a page of them
   (the dashboard contract). chartPanel draws a panel; queryPanels asks for many in one request; pagePanels
   keeps a page of them current. The legend sits beside the plot and nothing is drawn over the plot but the
   cursor: what the cursor points at is read in the legend, or in the panel's head when the legend is hidden. */
"use strict";

(() => {
  /* the correspondence hues in the order that keeps neighbours apart in both themes and under colour blindness
     (worst adjacent difference 10 for colour-blind readers, 17 for the rest); the red and the brown are left out,
     red meaning a failure here. Past eight a hue comes again dashed; "other" is always the muted ink */
  const SERIES_ORDER = [0, 1, 5, 9, 4, 2, 6, 7];
  const LATE_AFTER_TICKS = 1, GIVE_UP_TICKS = 4;
  const LOG_FORMS = new Set(["line"]);
  const PLOT_FORMS = new Set(["line", "bar"]);
  const DEFAULT_COLUMNS = ["last", "avg", "max"];
  const COLUMN_WORD = { last: "Last", avg: "Avg", min: "Min", max: "Max" };
  const DASH = "–", MINUS = "−";
  const PERCENT_UNIT = { raw: "%", per: null, kind: "percent", mult: 1, label: "%" };

  const inks = new Map();
  const ink = (name) => { if (!inks.has(name)) inks.set(name, tok(name)); return inks.get(name); };
  const LIVE = new Set();
  window.matchMedia?.("(prefers-color-scheme: dark)").addEventListener?.("change", () => {
    inks.clear();
    for (const p of LIVE) p.retheme();
  });
  const mixed = (a, b, share) => "#" + [1, 3, 5].map((i) => Math.round(parseInt(a.slice(i, i + 2), 16) * share + parseInt(b.slice(i, i + 2), 16) * (1 - share))
    .toString(16).padStart(2, "0")).join("");
  function seriesInk(item) {
    if (item.other) return ink("--muted");
    const hue = ink(`--g${SERIES_ORDER[item.slot % SERIES_ORDER.length]}`);
    return item.slot < SERIES_ORDER.length ? hue : mixed(hue, ink("--ink"), 0.62);
  }
  const washed = (hex, alpha) => `${hex}${alpha}`;

  /* ------------------------------------------------ the chart families and their options */

  /* a form is a family; its variants are options, declared here so the editor can offer them knowing no chart */
  const FORM_REGISTRY = new Map();
  function registerPlotForm(name, def) { FORM_REGISTRY.set(name, { name, ...FORM_REGISTRY.get(name), ...def }); }
  const plotForms = () => Object.fromEntries(FORM_REGISTRY);
  const choice = (key, label, choices, when) => ({ key, label, type: "choice", choices, default: choices[0], ...(when ? { when } : {}) });
  const stackedOn = (c) => (c.options?.stack || "none") !== "none";
  /* `shapes`: what each family takes of each result shape (frames.js); `reshape`: how to get there, said when it cannot */
  registerPlotForm("line", { label: "Line", group: "time", needs: { x: ["time", "query", "field", "bins"], text: "a measure over time, or against any X" },
    shapes: { series: {}, table: { dims: 1, dim: "number" }, points: {} }, reshape: "ask for values over time, or plot them against a number", options: [
    choice("style", "Line style", ["linear", "smooth", "step-after", "step-before", "step-middle"]),
    choice("fill", "Fill", ["none", "area", "gradient"]),
    choice("stack", "Stacking", ["none", "stacked", "percent"]),
    choice("points", "Points", ["auto", "always", "never"]),
    { key: "width", label: "Line width", type: "number", min: 1, max: 4, step: 1, default: 1.5 },
    choice("nulls", "Missing values", ["gap", "connect", "zero"]),
  ] });
  registerPlotForm("bar", { label: "Bar", group: "comparison", needs: { x: ["category", "time", "bins", "query", "field"], text: "values to compare" },
    shapes: { series: {}, table: { dims: 1 }, distribution: { form: ["bins"] } }, reshape: "ask for values over time or by category", options: [
    choice("orientation", "Orientation", ["vertical", "horizontal"]),
    choice("stack", "Stacking", ["none", "stacked", "percent"]),
    choice("grouping", "Several series", ["grouped", "overlaid"], (c) => !stackedOn(c)),
    choice("sort", "Sort", ["none", "value-desc", "value-asc"]),
    choice("values", "Value labels", ["off", "on"]),
  ] });
  registerPlotForm("stat", { label: "Stat", group: "single value", needs: { x: ["time"], text: "a measure over time" },
    shapes: { series: { roles: "none" }, table: { dims: 1, rows: 1 } }, reshape: "ask for one measure over time", options: [
    choice("value", "Value", ["last", "avg", "min", "max", "sum"]),
    choice("sparkline", "Sparkline", ["on", "off"]),
    choice("delta", "Change", ["on", "off"]),
    choice("color", "Colour", ["none", "thresholds"]),
  ] });
  registerPlotForm("table", { label: "Table", group: "single value", needs: { x: ["time"], text: "a measure over time" },
    shapes: { series: { roles: "none" }, table: { dims: 1 } }, reshape: "ask for values over time, or a table", options: [
    { key: "columns", label: "Columns", type: "choice", multiple: true, choices: ["last", "avg", "min", "max"], default: ["last", "avg", "max"] },
    choice("sort", "Sort", ["none", "name", "last", "avg", "min", "max"]),
    choice("bars_in_cells", "Bars in cells", ["off", "on"]),
  ] });

  /* the names panels were saved under before families. Old bars were stacked unless they said otherwise, and keep that */
  function normalizeForm(config) {
    const form = config?.form;
    const stack = config?.display?.stack;
    const old = form === "area" ? { form: "line", options: { fill: "area", ...(stack === true ? { stack: "stacked" } : {}) } }
      : form === "stacked" ? { form: "line", options: { fill: "area", stack: "stacked" } }
      : form === "step" ? { form: "line", options: { style: "step-after" } }
      : form === "bars" ? { form: "bar", options: { stack: stack === false ? "none" : "stacked" } }
      : form === "hbar" ? { form: "bar", options: { orientation: "horizontal" } }
      : null;
    return old ? { ...config, form: old.form, options: { ...old.options, ...(config.options || {}) } } : config;
  }
  /* each declared option at its asked value, or its default when unset or no longer one of the choices */
  function formOptions(config) {
    const asked = config.options || {}, out = { ...asked };
    for (const o of FORM_REGISTRY.get(config.form)?.options || []) {
      const v = asked[o.key];
      if (o.auto && v === "auto") { out[o.key] = "auto"; continue; }
      const fine = v != null && (o.type !== "choice" || o.multiple || o.free || o.choices.includes(v))
        && (o.type !== "number" || (Number.isFinite(+v) && (o.min == null || +v >= o.min) && (o.max == null || +v <= o.max)));
      out[o.key] = fine ? (o.type === "number" ? +v : v) : o.default;
    }
    return out;
  }

  /* ------------------------------------------------ units and numbers */

  const PER = { second: 1 / 3600, minute: 1 / 60, hour: 1, day: 24, week: 168 };
  const PER_WORD = { s: "second", sec: "second", second: "second", m: "minute", min: "minute", minute: "minute",
                     h: "hour", hr: "hour", hour: "hour", d: "day", day: "day", w: "week", wk: "week", week: "week" };
  const PER_SUFFIX = { second: "/s", minute: "/min", hour: "/h", day: "/day", week: "/week" };
  const DURATION = { ms: 0.001, millisecond: 0.001, milliseconds: 0.001, s: 1, sec: 1, secs: 1, second: 1, seconds: 1,
                     min: 60, mins: 60, minute: 60, minutes: 60, h: 3600, hr: 3600, hrs: 3600, hour: 3600, hours: 3600,
                     d: 86400, day: 86400, days: 86400 };
  const MONEY = new Set(["usd", "$", "dollar", "dollars"]);
  const PERCENT = new Set(["%", "percent", "pct"]);
  const BYTES = new Set(["b", "byte", "bytes"]);
  const SCALES = {
    plain: [[1e12, "T"], [1e9, "B"], [1e6, "M"], [1e3, "k"]],
    bytes: [[1e12, " TB"], [1e9, " GB"], [1e6, " MB"], [1e3, " KB"], [1, " B"]],
    dur: [[86400, " d"], [3600, " h"], [60, " min"], [1, " s"], [0.001, " ms"]],
  };

  function parseUnit(text) {
    const raw = String(text ?? "").trim();
    const cut = raw.lastIndexOf("/");
    const tail = cut > 0 ? PER_WORD[raw.slice(cut + 1).trim().toLowerCase()] : null;
    const base = (tail ? raw.slice(0, cut) : raw).trim();
    const low = base.toLowerCase();
    const unit = { raw, per: tail || null, kind: "plain", mult: 1, label: base };
    if (MONEY.has(low)) Object.assign(unit, { kind: "money", label: "$" });
    else if (PERCENT.has(low)) Object.assign(unit, { kind: "percent", label: "%" });
    else if (BYTES.has(low)) Object.assign(unit, { kind: "bytes", label: "" });
    else if (low in DURATION) Object.assign(unit, { kind: "dur", mult: DURATION[low], label: "" });
    return unit;
  }
  const chipOf = (u) => (u.kind === "dur" && !u.per ? "" : `${u.label}${u.per ? PER_SUFFIX[u.per] : ""}`);

  /* a rate whose unit the panel did not choose reads in the unit that suits its size (util.js's rule); money
     stays in the period it was asked for, since $62/h says more than $1.04/min */
  function readableRate(unit, largest) {
    if (!unit.per || largest == null || unit.kind === "money") return { unit, factor: 1 };
    const perHour = largest / PER[unit.per];
    const to = rateUnit(perHour);
    return { unit: { ...unit, per: to }, factor: PER[to] / PER[unit.per] };
  }

  const trimmed = (t) => (t.includes(".") ? t.replace(/\.?0+$/, "") : t);
  function digits(x, decimals, keep = false) {
    const a = Math.abs(x);
    if (decimals != null) return a.toFixed(decimals);
    if (a === 0) return "0";
    if (a < 0.01) return trimmed(a.toPrecision(2));
    const t = a.toFixed(a >= 100 ? 0 : a >= 10 ? 1 : 2);
    return keep ? t : trimmed(t);
  }
  function scaleOf(kind, a, from) {
    const list = SCALES[kind === "money" ? "plain" : kind];
    if (!list) return null;
    for (const [div, suffix] of list) if (a >= div && (kind === "dur" || kind === "bytes" || div >= from)) return { div, suffix };
    return kind === "dur" ? { div: 0.001, suffix: " ms" } : kind === "bytes" ? { div: 1, suffix: " B" } : null;
  }
  function dressed(body, negative, unit, suffix, withLabel) {
    const sign = negative ? MINUS : "";
    const per = unit.per ? PER_SUFFIX[unit.per] : "";
    if (unit.kind === "money") return `${sign}$${body}${suffix}${per}`;
    if (unit.kind === "percent") return `${sign}${body}%${per}`;
    if (unit.kind === "plain") return `${sign}${body}${suffix}${withLabel && unit.label ? ` ${unit.label}` : ""}${per}`;
    return `${sign}${body}${suffix}${per}`;
  }
  /* a value in full: in the legend, the stat and the table */
  function formatValue(v, unit, decimals = null, withLabel = false) {
    if (v == null || !Number.isFinite(v)) return DASH;
    const x = v * unit.mult, a = Math.abs(x);
    const sc = scaleOf(unit.kind, a, 1e4);
    const shown = sc ? a / sc.div : a;
    const body = !sc && a >= 1000 ? Math.round(a).toLocaleString("en-US") : digits(shown, decimals, unit.kind === "money" && !sc);
    return dressed(body, x < 0, unit, sc ? sc.suffix : "", withLabel);
  }
  /* an axis's labels: one scale for them all, as many places as tell the ticks truly, no rate suffix (the head says
     the unit), and a plain 0. On a log axis the ticks span decades, so each is said in its own scale */
  function axisLabels(values, unit, log = false) {
    const plain = { ...unit, per: null };
    const xs = values.filter((v) => v != null && Number.isFinite(v)).map((v) => v * unit.mult);
    if (!xs.length) return values.map(() => "");
    const zero = unit.kind === "money" ? "$0" : unit.kind === "percent" ? "0%" : "0";
    if (log) return values.map((v) => (v == null ? "" : v === 0 ? zero : formatValue(v, plain).replace(" ", "")));
    const sc = scaleOf(unit.kind, Math.max(...xs.map(Math.abs)), 1e3);
    const div = sc ? sc.div : 1;
    let places = 0;
    while (places < 4 && xs.some((x) => Math.abs(+(x / div).toFixed(places) - x / div) > 1e-6 * Math.max(1, Math.abs(x / div)))) places++;
    return values.map((v) => {
      if (v == null || !Number.isFinite(v)) return "";
      if (v === 0) return zero;
      const x = v * unit.mult;
      return dressed((Math.abs(x) / div).toFixed(places), x < 0, plain, sc ? sc.suffix.trim() : "", false);
    });
  }
  /* y ticks on steps a reader counts in: seconds, minutes and hours for a duration */
  const DECIMAL_STEPS = [];
  for (let e = -4; e <= 12; e++) for (const m of [1, 2, 2.5, 5]) DECIMAL_STEPS.push(+(m * 10 ** e).toPrecision(3));
  const DURATION_STEPS = [0.001, 0.002, 0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600, 7200,
                          14400, 21600, 43200, 86400, 172800, 432000, 864000];
  function logSplits(u, axisIdx, lo, hi) {
    const out = [];
    for (let e = Math.floor(Math.log10(lo)); e <= Math.ceil(Math.log10(hi)); e++) {
      const v = 10 ** e;
      if (v >= lo * 0.999 && v <= hi * 1.001) out.push(v);
    }
    if (out.length >= 2) return out;
    const fine = [];
    for (let e = Math.floor(Math.log10(lo)); e <= Math.ceil(Math.log10(hi)); e++) {
      for (const m of [1, 2, 5]) { const v = m * 10 ** e; if (v >= lo * 0.999 && v <= hi * 1.001) fine.push(v); }
    }
    return fine;
  }
  const timeText = (t, span) => {
    const d = new Date(t * 1000);
    const clock = d.toLocaleTimeString([], { hour12: false, hour: "2-digit", minute: "2-digit" });
    return span > 86400 ? `${d.toLocaleDateString([], { month: "short", day: "numeric" })} ${clock}` : clock;
  };

  /* ------------------------------------------------ an answer, as the series a panel draws */

  const queryWord = (q) => q.label || q.field || q.series || q.measure || q.type || q.source || q.id;
  const OTHER = "other";
  const ZERO_FILLED = new Set(["sum", "count"]);       // an empty bucket of these answers 0, which says nothing happened in it
  /* the different units a panel's queries answer in, when it chose none: one axis cannot be read in one of them */
  const unitsApart = (cfg, results) => {
    if (cfg.display?.unit && cfg.display.unit !== "auto") return [];
    const on = new Set(shownQueries(cfg).map((q) => q.id));
    const units = [...new Set(results.filter((r) => on.has(r.id) && !r.error && r.unit).map((r) => r.unit))];
    return units.length > 1 ? units : [];
  };

  /* the ids a shown query reads from: as its X, or as a frequency response's input or output */
  const readsFrom = (q) => [q.x?.query, q.input, q.output].filter((r) => typeof r === "string" || typeof r === "number").map(String);
  /* what is drawn: a query that only feeds another is that query's axis, not a series of its own. If every shown query
     feeds another (a cycle) they are all kept, so the answer's words about it reach the panel */
  function shownQueries(cfg) {
    const on = (cfg.queries || []).filter((q) => !q.hidden);
    const fed = new Set(on.flatMap((q) => readsFrom(q).filter((r) => r !== String(q.id))));
    const drawn = on.filter((q) => !fed.has(String(q.id)));
    return drawn.length ? drawn : on;
  }
  const allHidden = (cfg) => (cfg.queries || []).length > 0 && !shownQueries(cfg).length;
  const ALL_HIDDEN = "All of this panel's queries are hidden";

  function statsOf(values) {
    let n = 0, sum = 0, min = Infinity, max = -Infinity, last = null;
    for (const v of values) {
      if (v == null || !Number.isFinite(v)) continue;
      n++; sum += v; last = v;
      if (v < min) min = v;
      if (v > max) max = v;
    }
    return n ? { n, last, avg: sum / n, min, max } : { n: 0, last: null, avg: null, min: null, max: null };
  }
  function alignedTimes(results) {
    const first = results[0].times || [];
    const same = results.every((r) => (r.times || []).length === first.length && (r.times || []).every((t, i) => t === first[i]));
    if (same) return { times: first, at: null };
    /* several grids on one axis: a query holds a value only at its own times. undefined there (no bucket of its own) is
       joined across by the line; null (its bucket, empty) stays a gap. Nothing is filled in */
    const times = [...new Set(results.flatMap((r) => r.times || []))].sort((a, b) => a - b);
    return { times, at: new Map(times.map((t, i) => [t, i])) };
  }
  function readAnswer(cfg, results, slots) {
    const on = new Set(shownQueries(cfg).map((q) => q.id));
    const drawn = results.filter((r) => on.has(r.id));
    const good = drawn.filter((r) => !r.error && r.series);
    const failed = drawn.filter((r) => r.error);
    const { times, at } = good.length ? alignedTimes(good) : { times: [], at: null };
    const queries = shownQueries(cfg);
    const many = queries.length > 1;
    const items = [];
    for (const r of good) {
      const q = queries.find((x) => x.id === r.id) || { id: r.id };
      for (const one of r.series) {
        const word = queryWord(q);
        const name = one.name ? (many ? `${word}: ${one.name}` : one.name) : word;
        const key = `${r.id}\u0000${one.name ?? ""}`;
        let values = one.values || [];
        if (at) {
          const placed = new Array(times.length).fill(undefined);
          (r.times || []).forEach((t, i) => { placed[at.get(t)] = values[i] ?? null; });
          values = placed;
        }
        const other = one.name === OTHER;
        if (!other && !slots.has(key)) slots.set(key, slots.size);
        items.push({ key, name, values, other, slot: other ? 0 : slots.get(key), unit: r.unit, tally: ZERO_FILLED.has(q.agg) && q.source !== "counts" });
      }
    }
    return { times, items, failed, mixed: !!at, capped: good.reduce((sum, r) => sum + (r.capped || 0), 0) };
  }

  /* ------------------------------------------------ drawing on the plot */

  function stackedValues(times, items, off) {
    const running = new Array(times.length).fill(0);
    const any = times.map((_, t) => items.some((it) => !off.has(it.key) && it.values[t] != null));
    const shared = times.map((_, t) => items.every((it) => off.has(it.key) || it.values[t] !== undefined));   // a sum needs them all
    return items.map((it) => times.map((_, t) => {
      if (!shared[t]) return undefined;
      if (!any[t]) return null;
      if (!off.has(it.key)) running[t] += it.values[t] ?? 0;
      return running[t];
    }));
  }
  /* bars over each bucket, side by side or stacked, with the paper showing between them */
  function sharesOf(rows, off) {
    const n = rows[0]?.length || 0;
    const totals = new Array(n).fill(0);
    rows.forEach((r, k) => { if (!off(k)) r.forEach((v, i) => { if (v != null) totals[i] += Math.abs(v); }); });
    return rows.map((r) => r.map((v, i) => (v == null ? v : totals[i] ? v / totals[i] * 100 : 0)));
  }
  function barPaths(st) {
    return (u, si, i0, i1) => {
      const path = new Path2D(), dpr = devicePixelRatio;
      const shown = st.items.map((it, i) => (st.off.has(it.key) ? -1 : i)).filter((i) => i >= 0);
      const lane = shown.indexOf(si - 1);
      if (lane < 0) return { stroke: path, fill: path, clip: null, band: null, gaps: null };
      const lanes = st.stacked || st.overlaid ? 1 : shown.length;
      const base0 = u.valToPos(0, "y", true);
      for (let i = i0; i <= i1; i++) {
        const v = u.data[si][i];
        if (v == null) continue;
        const t = u.data[0][i];
        const left = u.valToPos(t, "x", true), right = u.valToPos(t + st.step, "x", true);
        const full = right - left, gap = Math.min(2 * dpr, full * 0.2), w = Math.max(dpr, (full - gap) / lanes);
        const x = left + gap / 2 + (st.stacked || st.overlaid ? 0 : lane * w);
        const prev = st.stacked && lane > 0 ? u.data[shown[lane - 1] + 1][i] : null;
        const y0 = prev == null ? base0 : u.valToPos(prev, "y", true);
        const y1 = u.valToPos(v, "y", true);
        if (v === (prev ?? 0)) continue;
        const inset = prev == null ? 0 : Math.min(dpr, Math.abs(y0 - y1) / 2);
        const top = Math.min(y0, y1), height = Math.max(dpr, Math.abs(y0 - y1) - inset);
        const r = st.stacked && lane < shown.length - 1 ? 0 : Math.min(1.5 * dpr, w / 2, height / 2);
        if (path.roundRect) path.roundRect(x, top, Math.max(dpr, w - (lanes > 1 ? dpr : 0)), height, v >= (prev ?? 0) ? [r, r, 0, 0] : [0, 0, r, r]);
        else path.rect(x, top, w, height);
      }
      return { stroke: path, fill: path, clip: null, band: null, gaps: null };
    };
  }
  function thresholdLines(st) {
    return (u) => {
      const lines = st.display.thresholds || [];
      if (!lines.length || st.percent) return;
      const ctx = u.ctx, { left, top, width, height } = u.bbox;
      ctx.save();
      ctx.beginPath(); ctx.rect(left, top, width, height); ctx.clip();
      ctx.strokeStyle = ink("--ink-2"); ctx.lineWidth = devicePixelRatio;
      ctx.setLineDash([5 * devicePixelRatio, 4 * devicePixelRatio]);
      for (const th of lines) {
        if (th.value == null || (st.logScale && th.value <= 0)) continue;
        const y = Math.round(u.valToPos(th.value * st.factor, "y", true)) + 0.5;
        ctx.beginPath(); ctx.moveTo(left, y); ctx.lineTo(left + width, y); ctx.stroke();
      }
      ctx.restore();
    };
  }
  function yRangeOf(st) {
    return (u, lo, hi) => {
      if (st.percent) return [0, 100];
      const asked = st.display.y || {};
      const y = { min: asked.min == null ? null : asked.min * st.factor, max: asked.max == null ? null : asked.max * st.factor };
      const levels = (st.display.thresholds || []).map((x) => x.value * st.factor).filter(Number.isFinite);
      if (st.logScale) {
        const pos = levels.filter((v) => v > 0);
        const a = y.min > 0 ? y.min : Math.min(lo > 0 ? lo : Infinity, ...pos);
        const b = y.max > 0 ? y.max : Math.max(hi > 0 ? hi : -Infinity, ...pos);
        if (!Number.isFinite(a) || !Number.isFinite(b)) return [1, 10];
        const [rl, rh] = uPlot.rangeLog(a, b === a ? a * 10 : b, 10, true);
        return [y.min > 0 ? y.min : rl, y.max > 0 ? y.max : rh];
      }
      let a = Math.min(lo ?? Infinity, ...levels), b = Math.max(hi ?? -Infinity, ...levels);
      if (!Number.isFinite(a) || !Number.isFinite(b)) { a = 0; b = 1; }
      if ((st.form !== "line" || st.filled) && a > 0) a = 0;
      if (a === b) { const d = Math.abs(a) * 0.1 || 1; a -= a === 0 ? 0 : d; b += d; }
      const nice = uPlot.rangeNum(a, b, { min: { pad: a === 0 ? 0 : 0.06, soft: 0, mode: 2 }, max: { pad: 0.08, soft: 0, mode: 2 } });
      return [y.min ?? (a === 0 ? 0 : nice[0]), y.max ?? nice[1]];
    };
  }
  const dashOf = (st, it) => (!st.stacked && st.form !== "bar" && (it?.slot ?? 0) >= SERIES_ORDER.length ? [6, 3] : undefined);
  function linePaths(style) {
    if (style === "step-after") return uPlot.paths.stepped({ align: 1 });
    if (style === "step-before") return uPlot.paths.stepped({ align: -1 });
    if (style === "smooth" && uPlot.paths.spline) return uPlot.paths.spline();
    return undefined;
  }
  function gradientFill(u, colour) {
    const { top, height } = u.bbox, g = u.ctx.createLinearGradient(0, top, 0, top + height);
    g.addColorStop(0, washed(colour, "8c"));
    g.addColorStop(1, washed(colour, "0a"));
    return g;
  }
  function seriesOptions(st, index) {
    const item = () => st.items[index] || st.items[0];
    const colour = () => { const it = item(); return !it || st.off.has(it.key) ? "transparent" : seriesInk(it); };
    const isBar = st.form === "bar", o = st.options;
    const wanted = (si) => (o.points === "always" ? true : o.points === "never" ? false : (st.items[si - 1]?.stats.n ?? 0) <= 2);
    const opts = { label: item()?.name || "", width: isBar ? 0 : o.width ?? 1.5, stroke: colour, spanGaps: !isBar && o.nulls === "connect",
                   dash: dashOf(st, st.items[index]),
                   points: { show: (u, si) => !isBar && wanted(si), size: 5, stroke: colour, fill: colour } };
    if (isBar) { opts.paths = barPaths(st); opts.fill = st.overlaid ? () => (colour() === "transparent" ? colour() : washed(colour(), "8c")) : colour; return opts; }
    const paths = linePaths(o.style);
    if (paths) opts.paths = paths;
    const fillOf = (u, alpha) => { const c = colour(); return c === "transparent" ? c : o.fill === "gradient" ? gradientFill(u, c) : washed(c, alpha); };
    if (st.stacked) {
      if (st.filled && index === 0) { opts.fill = (u) => fillOf(u, "a6"); opts.fillTo = () => 0; }
    } else if (st.filled) {
      opts.fill = (u) => fillOf(u, "2e");
      opts.fillTo = st.logScale ? undefined : () => 0;
    }
    return opts;
  }
  function setBands(st, plot) {
    while (plot.bands?.length) plot.delBand(0);
    if (!st.stacked || st.form === "bar" || !st.filled) return;
    for (let i = 1; i < st.items.length; i++) {
      const it = () => st.items[i];
      plot.addBand({ series: [i + 1, i], fill: (u) => {
        if (!it() || st.off.has(it().key)) return "transparent";
        return st.options.fill === "gradient" ? gradientFill(u, seriesInk(it())) : washed(seriesInk(it()), "a6");
      } });
    }
  }
  function cursorMark(u, si) {
    const pt = document.createElement("div"), size = 7;
    if (!u.series[si]) return null;
    Object.assign(pt.style, { width: `${size}px`, height: `${size}px`, marginLeft: `${-size / 2}px`, marginTop: `${-size / 2}px`, borderWidth: "2px" });
    return pt;
  }

  /* ------------------------------------------------ the panel */

  const spark = () => {
    const svg = s("svg", { class: "panel-spark", viewBox: "0 0 100 32", preserveAspectRatio: "none", "aria-hidden": "true" });
    const fill = s("path", { class: "panel-spark-fill" }), line = s("path", { class: "panel-spark-line" });
    svg.append(fill, line);
    svg.setValues = (values, colour) => {
      const st = statsOf(values);
      if (!st.n) { line.setAttribute("d", ""); fill.setAttribute("d", ""); return; }
      const span = st.max - st.min || 1, n = Math.max(1, values.length - 1);
      const X = (i) => (i / n * 100).toFixed(2), Y = (v) => (29 - (v - st.min) / span * 26).toFixed(2);
      let d = "", area = "", open = false, start = 0, lastI = 0;
      values.forEach((v, i) => {
        if (v === undefined) return;                     // no bucket of its own here: the line carries on
        if (v == null) { if (open) area += `L${X(lastI)} 32L${X(start)} 32Z`; open = false; return; }
        if (!open) { start = i; d += `M${X(i)} ${Y(v)}`; area += `M${X(i)} 32L${X(i)} ${Y(v)}`; open = true; }
        else { d += `L${X(i)} ${Y(v)}`; area += `L${X(i)} ${Y(v)}`; }
        lastI = i;
      });
      if (open) area += `L${X(lastI)} 32L${X(start)} 32Z`;
      line.setAttribute("d", d); fill.setAttribute("d", area);
      svg.style.setProperty("--spark", colour);
    };
    return svg;
  };

  function chartPanel(config, { group = null } = {}) {
    const st = { cfg: null, display: {}, options: {}, form: "line", filled: false, percent: false, overlaid: false, view: null, viewKey: "", stacked: false, logScale: false, items: [], times: [], step: 60, x0: 0, x1: 1,
                 unit: parseUnit(""), factor: 1, off: new Set(), slots: new Map(), hasData: false, visible: true, dirty: false,
                 last: null, state: "loading", sort: null, draws: 0, columns: [] };
    const cursorGroup = group || sharedGroup();
    const title = h("h3", { class: "panel-title" });
    const note = h("p", { class: "panel-note" });
    const flag = h("span", { class: "panel-flag", role: "status" });
    const readout = h("span", { class: "panel-readout" });
    const chip = h("span", { class: "panel-unit" });
    const head = h("header", { class: "panel-head" }, h("div", { class: "panel-names" }, title, note), readout, chip, flag);
    const host = h("div", { class: "panel-canvas" });
    const plotBox = h("div", { class: "panel-plot" }, host);
    const legend = h("div", { class: "panel-legend" });
    const keys = h("div", { class: "panel-keys" });
    const chartArea = h("div", { class: "panel-chart" }, h("div", { class: "panel-plot-col" }, plotBox, keys), legend);
    const stats = h("div", { class: "panel-stats" });
    const tableBox = h("div", { class: "panel-table" });
    const message = h("div", { class: "panel-message" });
    const warning = h("p", { class: "panel-warning", role: "note", hidden: true });
    const body = h("div", { class: "panel-body" }, chartArea, stats, tableBox, message, warning);
    const el = h("section", { class: "panel" }, head, body);

    /* the plot */
    function makePlot(width, target) {
      const height = Math.max(60, Math.floor(host.clientHeight));
      const hooks = { drawClear: [thresholdLines(st)], setCursor: [onCursor] };
      const o = baseOpts({ width, height, group: cursorGroup, since: st.x0, until: st.x1, xAxis: true, yRange: yRangeOf(st), hooks });
      o.padding = [8, 20, 0, 0];
      o.scales.x.range = () => [st.x0, st.x1];
      o.scales.y = { range: yRangeOf(st), ...(st.logScale ? { distr: 3, log: 10 } : {}) };
      const axisInk = () => ink("--muted"), gridInk = () => ink("--line");
      const [xAxis, yAxis] = o.axes;
      xAxis.stroke = axisInk;
      xAxis.size = 24;
      yAxis.stroke = axisInk;
      yAxis.grid = { ...yAxis.grid, stroke: gridInk };
      yAxis.space = 30;
      yAxis.values = (u, vals) => axisLabels(vals, st.percent ? PERCENT_UNIT : st.unit, st.logScale);
      if (st.logScale) yAxis.splits = logSplits;
      else yAxis.incrs = (st.unit.kind === "dur" ? DURATION_STEPS.map((x) => x / st.unit.mult) : DECIMAL_STEPS);
      yAxis.size = (u, vals) => {
        if (!vals) return 40;
        u.ctx.save();
        u.ctx.font = yAxis.font?.[0] || `${parseFloat(tok("--canvas-sm")) * devicePixelRatio}px ${tok("--font")}`;
        const widest = Math.max(...vals.map((v) => u.ctx.measureText(v).width));
        u.ctx.restore();
        return Math.ceil(widest / devicePixelRatio) + 10;
      };
      o.cursor.points = { show: cursorMark, size: 7, width: 2, fill: () => ink("--bg") };
      o.series = [{}, ...st.items.map((_, i) => seriesOptions(st, i))];
      const data = plotData();
      const plot = new uPlot(o, data, target);
      setBands(st, plot);
      if (st.items.length) plot.redraw(true, true);
      return plot;
    }
    function plotData() {
      const filledIn = (v) => (v === null && st.form === "line" && st.options.nulls === "zero" ? 0 : v);
      const shownValue = (v) => (v == null ? v : st.logScale && v <= 0 ? null : v * st.factor);
      let scaled = st.items.map((it) => it.values.map((v) => shownValue(filledIn(v))));
      if (st.percent) scaled = sharesOf(scaled, (k) => st.off.has(st.items[k].key));
      if (st.stacked) {
        const shadow = st.items.map((it, i) => ({ ...it, values: scaled[i] }));
        return [st.times, ...stackedValues(st.times, shadow, st.off)];
      }
      return [st.times, ...st.items.map((it, i) => (st.off.has(it.key) ? st.times.map(() => null) : scaled[i]))];
    }
    function mountChart() {
      host.replaceChildren();
      delete host.plot;
      const inner = h("div", { class: "panel-mount" });
      host.append(inner);
      mountPlot(inner, (w) => makePlot(w, inner));
      st.mount = inner;
    }
    const livePlot = () => { const p = st.mount?.plot; return p && p.root.isConnected ? p : null; };
    function dropPlot() {
      const p = st.mount?.plot;
      if (p) { p.destroy(); PLOTS.delete(p); }
      st.mount?.remove();
      st.mount = null;
    }
    function drawPlot() {
      if (!PLOT_FORMS.has(st.form) || st.view) return;
      if (st.mount?.plot && !livePlot()) dropPlot();     // the page took it away and let it go (charts.js sweeps)
      if (!st.mount) mountChart();
      const plot = livePlot();
      if (!plot) return;
      plot.batch(() => {
        const want = st.items.length + 1;
        while (plot.series.length > want) plot.delSeries(plot.series.length - 1);
        while (plot.series.length < want) plot.addSeries(seriesOptions(st, plot.series.length - 1), plot.series.length);
        st.items.forEach((it, i) => {
          plot.series[i + 1].label = it.name;
          plot.series[i + 1].dash = dashOf(st, it);
        });
        setBands(st, plot);
        plot.setData(plotData());
      });
      st.draws++;
    }
    const heightWatch = new ResizeObserver(() => {
      const p = livePlot();
      const w = Math.floor(st.mount?.clientWidth || 0), hh = Math.floor(host.clientHeight);
      if (p && w && hh && (Math.abs(p.height - hh) > 1 || Math.abs(p.width - w) > 1)) p.setSize({ width: w, height: hh });
    });
    heightWatch.observe(host);

    /* the cursor is read beside the plot */
    function onCursor(u) {
      const i = u.cursor.idx, span = st.x1 - st.x0;
      const hovering = i != null && st.times[i] != null;
      el.toggleAttribute("data-hover", hovering);
      if (st.legendHead) st.legendHead.textContent = hovering ? timeText(st.times[i], span) : st.columns.includes("last") ? COLUMN_WORD.last : "";
      for (const row of legend.querySelectorAll("tr[data-key]")) {
        const it = st.items.find((x) => x.key === row.__item);
        if (!it) continue;
        row.__now.textContent = hovering ? formatValue(it.values[i] == null ? null : it.values[i] * st.factor, st.unit, st.places)
                                         : st.columns.includes("last") ? formatValue(it.stats.last == null ? null : it.stats.last * st.factor, st.unit, st.places) : "";
      }
      if (legendShown()) { readout.textContent = ""; return; }
      if (hovering) {
        const near = nearestItem(u, i);
        readout.textContent = near ? `${timeText(st.times[i], span)}  ${st.items.length > 1 ? `${near.name} ` : ""}${formatValue(near.values[i] == null ? null : near.values[i] * st.factor, st.unit, st.places)}` : timeText(st.times[i], span);
      } else restReadout();
    }
    function nearestItem(u, i) {
      const y = u.cursor.top;
      let best = null, gap = Infinity;
      st.items.forEach((it, k) => {
        const v = u.data[k + 1]?.[i];
        if (v == null || st.off.has(it.key)) return;
        const d = y == null || y < 0 ? k : Math.abs(u.valToPos(v, "y") - y);
        if (d < gap) { gap = d; best = it; }
      });
      return best;
    }
    function restReadout() {
      if (legendShown() || PLOT_FORMS.has(st.form) === false || st.items.length !== 1) { readout.textContent = ""; return; }
      const v = st.items[0].stats.last;
      readout.textContent = v == null ? "" : formatValue(v * st.factor, st.unit, st.places);
    }

    /* the legend */
    function legendPlace() {
      const asked = st.display.legend;
      if (asked === "hidden" || asked === "bottom" || asked === "right") return asked;
      return "right";                                    // unset is automatic: beside, or under a narrow panel (panels.css)
    }
    const legendShown = () => PLOT_FORMS.has(st.form) && legendPlace() !== "hidden";
    function drawLegend() {
      const place = PLOT_FORMS.has(st.form) ? legendPlace() : "hidden";
      el.dataset.legend = place;
      legend.hidden = place === "hidden";
      if (place === "hidden") return;
      const asked = st.display.legend_values;
      const columns = Array.isArray(asked) ? asked.filter((c) => COLUMN_WORD[c]) : [];
      st.columns = columns;
      const rest = columns.filter((c) => c !== "last");
      const sig = JSON.stringify(rest);
      let table = legend.firstElementChild;
      if (!table || table.__sig !== sig) {
        st.legendHead = h("th", { class: "panel-num panel-now", scope: "col" });
        table = h("table", { class: "panel-legend-table" },
          h("thead", {}, h("tr", {}, h("th", { scope: "col" }, h("span", { class: "panel-sr" }, "Series")), st.legendHead,
                                  rest.map((c) => h("th", { class: "panel-num", scope: "col" }, COLUMN_WORD[c])))),
          h("tbody"));
        table.__sig = sig;
        legend.replaceChildren(table);
      }
      if (!el.hasAttribute("data-hover")) st.legendHead.textContent = columns.includes("last") ? COLUMN_WORD.last : "";
      const tbody = table.tBodies[0], have = new Map([...tbody.rows].map((r) => [r.__item, r]));
      st.items.forEach((it, index) => {
        let row = have.get(it.key);
        if (!row) {
          const swatch = h("i", { class: "panel-swatch" });
          const name = h("span", { class: "panel-series-name" });
          const button = h("button", { type: "button", class: "panel-series", onclick: () => toggle(row.__item) }, swatch, name);
          row = h("tr", { "data-key": it.key }, h("td", { class: "panel-series-cell" }, button), h("td", { class: "panel-num panel-now" }),
                  rest.map(() => h("td", { class: "panel-num" })));
          row.__item = it.key; row.__swatch = swatch; row.__name = name; row.__button = button; row.__now = row.cells[1];
        }
        have.delete(it.key);
        if (tbody.rows[index] !== row) tbody.insertBefore(row, tbody.rows[index] || null);
        const isOff = st.off.has(it.key);
        row.classList.toggle("off", isOff);
        row.__button.setAttribute("aria-pressed", String(!isOff));
        row.__button.title = isOff ? `Show ${it.name}` : `Hide ${it.name}`;
        row.__swatch.style.setProperty("--swatch", seriesInk(it));
        row.__swatch.classList.toggle("dashed", !!dashOf(st, it));
        if (row.__name.textContent !== it.name) row.__name.textContent = it.name;
        const value = (v) => formatValue(v == null ? null : v * st.factor, st.unit, st.places);
        if (!el.hasAttribute("data-hover")) row.__now.textContent = columns.includes("last") ? value(it.stats.last) : "";
        rest.forEach((c, k) => { row.cells[k + 2].textContent = value(it.stats[c]); });
      });
      for (const row of have.values()) row.remove();
    }
    /* a form drawn on its own canvas (plots-*.js), or a line or bar the time plot cannot draw */
    const shapeOf = (r) => (r.frequency ? "frequency" : r.x?.type || "time");
    function drawnBy(results) {
      const def = FORM_REGISTRY.get(st.form);
      if (!def?.draw) return null;
      if (!PLOT_FORMS.has(st.form)) return def;
      const r = results.find((x) => !x.error);
      if (!r && st.view) return def;                     // a failed refresh leaves what is drawn, and says so in the head
      if (r && shapeOf(r) !== "time") return def;
      const o = st.options;
      if (st.form === "line") return o.style === "step-middle" || (o.style === "smooth" && !uPlot.paths.spline) ? def : null;
      return o.orientation === "horizontal" || o.sort !== "none" || o.values === "on" ? def : null;
    }
    function dropView() {
      st.view?.destroy();
      st.view = null;
      st.viewKey = "";
      st.viewMount?.remove();
      st.viewMount = null;
    }
    function mergedResult(good) {
      const queries = shownQueries(st.cfg), many = queries.length > 1, series = [];
      for (const r of good) {
        const q = queries.find((x) => x.id === r.id) || { id: r.id };
        for (const one of r.series || []) {
          const word = queryWord(q);
          const key = `${r.id}\u0000${one.name ?? ""}`, other = one.name === OTHER;
          if (!other && !st.slots.has(key)) st.slots.set(key, st.slots.size);
          const times = one.times || r.times || null;
          const item = { key, other, slot: other ? 0 : st.slots.get(key) };
          series.push({ ...one, key, other, slot: item.slot, colour: seriesInk(item), times,
                        name: one.name && one.name !== "y" ? (many ? `${word}: ${one.name}` : one.name) : word,
                        xs: one.xs || r.times || [], values: one.values || [] });
        }
      }
      const first = good[0] || {};
      return { ...first, shape: shapeOf(first), x: first.x || { type: "time" }, series, capped: good.reduce((n, r) => n + (r.capped || 0), 0) };
    }
    const hasPoints = (r) => (r.frequency ? (r.frequency.hz || []).length > 0
      : r.series.some((x) => (x.close || x.values || []).some((v) => v != null)) || !!(r.poles?.length || r.zeros?.length));
    function drawForm(def) {
      const results = st.shown, { meta } = st.last;
      const on = new Set(shownQueries(st.cfg).map((q) => q.id));
      const drawn = (results || []).filter((r) => on.has(r.id));
      const good = drawn.filter((r) => !r.error), failed = drawn.filter((r) => r.error);
      if (failed.length && !good.length) {
        st.hasData = st.hasData && !!st.view;
        setState("error", failed.map((r) => r.error).join("; "));
        return;
      }
      if (allHidden(st.cfg)) { dropView(); setState("empty", ALL_HIDDEN); return; }
      const result = mergedResult(good);
      const accepted = def.needs?.source === "frequency" ? ["frequency"] : def.needs?.x;
      const why = !good.length ? "This panel has no query yet."
        : accepted && !good.some((r) => r.shape) && !accepted.includes(result.shape) ? `${def.label || st.form} needs ${def.needs?.text || `an X axis of ${accepted.join(" or ")}`}; this query has ${result.shape}.`
        : def.check?.(result, st.cfg) || (hasPoints(result) ? "" : `Nothing recorded for ${shownQueries(st.cfg).map(queryWord).join(", ") || "this query"}.`);
      if (why) { dropView(); setState("empty", why); return; }
      if (st.mount) dropPlot();
      const chosen = st.display.unit && st.display.unit !== "auto";
      const apart = unitsApart(st.cfg, good);
      if (apart.length) said(`These queries are in different units (${apart.join(", ")}) on one axis: compare their shapes, not their heights.`);
      st.unit = parseUnit(chosen ? st.display.unit : apart.length ? "" : result.unit);
      st.factor = 1;
      st.hasData = true;
      chip.textContent = chipOf(st.unit);
      chip.hidden = !chip.textContent;
      setState("drawn");
      setBody("chart");
      const place = legendPlace();
      el.dataset.legend = place;
      legend.hidden = place === "hidden";
      if (place === "hidden") legend.replaceChildren();
      const failedSaid = failed.length ? `${failed.length} of ${drawn.length} queries failed: ${failed.map((r) => r.error).join("; ")}` : "";
      if (failedSaid) { flag.classList.add("is-error"); flag.textContent = "Partial"; flag.title = failedSaid; }
      keys.replaceChildren();
      if (result.capped) keys.append(h("span", { class: "panel-key panel-key-note" }, `${result.capped} more not drawn`));
      keys.hidden = !keys.childElementCount;
      result.meta = meta;
      const key = JSON.stringify([st.form, st.options, st.display, result.shape]);
      if (st.view && st.viewKey === key) st.view.update(result);
      else {
        dropView();
        host.replaceChildren();
        st.viewMount = h("div", { class: "panel-mount" });
        host.append(st.viewMount);
        st.view = def.draw(st.viewMount, result, st.cfg, { label: `${def.label || st.form}: ${st.cfg.title || "Untitled"}`, options: st.options, unit: st.unit, legend: place === "hidden" ? null : legend,
                                                         readout: (text) => { readout.textContent = text; } });
        st.viewKey = key;
      }
      st.draws++;
    }
    function toggle(key) {
      if (st.off.has(key)) st.off.delete(key); else st.off.add(key);
      drawLegend();
      drawPlot();
    }
    function drawKeys() {
      const lines = PLOT_FORMS.has(st.form) ? (st.display.thresholds || []).filter((x) => x.value != null) : [];
      keys.hidden = !lines.length;
      keys.replaceChildren(...lines.map((x) => h("span", { class: "panel-key" }, h("i", { class: "panel-key-line" }),
        `${x.label ? `${x.label} ` : ""}${formatValue(x.value * st.factor, st.unit, st.places)}`)));
    }

    /* a stat: one large number for each series, its trend under it */
    function drawStats() {
      const have = new Map([...stats.children].map((c) => [c.__key, c]));
      stats.dataset.count = String(Math.min(st.items.length, 4));
      st.items.forEach((it, index) => {
        let tile = have.get(it.key);
        if (!tile) {
          const name = h("div", { class: "panel-stat-name" }, h("i", { class: "panel-swatch" }), h("span"));
          const num = h("div", { class: "panel-stat-num" });
          const change = h("div", { class: "panel-stat-change" });
          const line = spark();
          tile = h("div", { class: "panel-stat" }, name, num, change, line);
          tile.__key = it.key; tile.__nameEl = name; tile.__num = num; tile.__change = change; tile.__spark = line;
        }
        have.delete(it.key);
        if (stats.children[index] !== tile) stats.insertBefore(tile, stats.children[index] || null);
        tile.__nameEl.hidden = st.items.length === 1;
        tile.__nameEl.lastChild.textContent = it.name;
        tile.__nameEl.firstChild.style.setProperty("--swatch", seriesInk(it));
        const o = st.options;
        const known = it.values.filter((v) => v != null && Number.isFinite(v));
        /* the last bucket of a sum or a count is 0 when nothing has happened in it yet: the last that held something is read */
        const lastHeld = (o.value || "last") === "last" && it.tally && it.stats.last === 0 ? it.values.findLastIndex((v) => v != null && v !== 0) : -1;
        const shown = lastHeld >= 0 ? it.values[lastHeld]
          : o.value === "sum" ? (known.length ? known.reduce((a, b) => a + b, 0) : null) : it.stats[o.value || "last"];
        tile.__num.textContent = formatValue(shown == null ? null : shown * st.factor, st.unit, st.places, true);
        const passed = o.color === "thresholds" && shown != null ? (st.display.thresholds || []).filter((x) => x.value != null && shown >= x.value).length : 0;
        const levels = (st.display.thresholds || []).filter((x) => x.value != null).length;
        tile.__num.classList.toggle("is-bad", passed > 0 && passed === levels);
        tile.__num.classList.toggle("is-warn", passed > 0 && passed < levels);
        tile.__change.hidden = o.delta === "off";
        tile.__change.textContent = lastHeld >= 0 && st.times[lastHeld] != null ? `at ${timeText(st.times[lastHeld], st.x1 - st.x0)}, none since`
          : o.delta === "off" ? "" : changeSaid(it.values);
        tile.__spark.style.display = o.sparkline === "off" ? "none" : "";
        tile.__spark.setValues(it.values, st.items.length === 1 ? ink("--g0") : seriesInk(it));
      });
      for (const tile of have.values()) tile.remove();
    }
    function changeSaid(values) {
      const known = values.filter((v) => v != null);
      if (known.length < 2 || !known[0]) return "";
      const pct = (known[known.length - 1] - known[0]) / Math.abs(known[0]) * 100;
      if (!Number.isFinite(pct)) return "";
      const size = Math.abs(pct);
      const said = size >= 100 ? size.toFixed(0) : size.toFixed(1);
      return size < 0.05 ? "no change over the window" : `${pct > 0 ? "▲" : "▼"} ${said}% over the window`;
    }

    /* a table: a row for each series */
    function drawTable() {
      const asked = Array.isArray(st.cfg.options?.columns) ? st.cfg.options.columns : st.display.legend_values;
      const columns = Array.isArray(asked) && asked.some((c) => COLUMN_WORD[c]) ? asked.filter((c) => COLUMN_WORD[c]) : DEFAULT_COLUMNS;
      const sig = JSON.stringify(columns);
      if (!st.sort && st.options.sort && st.options.sort !== "none") st.sort = { key: st.options.sort, down: st.options.sort !== "name" };
      let table = tableBox.firstElementChild;
      if (!table || table.__sig !== sig) {
        const header = (word, key, cls) => {
          const b = h("button", { type: "button", onclick: () => { st.sort = st.sort?.key === key ? { key, down: !st.sort.down } : { key, down: key !== "name" }; drawTable(); } }, word);
          const th = h("th", { class: cls, scope: "col" }, b);
          th.__sortKey = key;
          return th;
        };
        table = h("table", { class: "panel-data-table" },
          h("thead", {}, h("tr", {}, header("Series", "name", ""), columns.map((c) => header(COLUMN_WORD[c], c, "panel-num")),
                                  h("th", { class: "panel-trend", scope: "col" }, "Trend"))),
          h("tbody"));
        table.__sig = sig;
        tableBox.replaceChildren(table);
      }
      for (const th of table.tHead.rows[0].cells) {
        if (th.__sortKey) th.setAttribute("aria-sort", st.sort?.key === th.__sortKey ? (st.sort.down ? "descending" : "ascending") : "none");
      }
      const ordered = [...st.items];
      if (st.sort) {
        const { key, down } = st.sort;
        const val = (it) => (key === "name" ? it.name : it.stats[key]);
        ordered.sort((a, b) => {
          const x = val(a), y = val(b);
          if (x == null || y == null) return x == null ? (y == null ? 0 : 1) : -1;
          const c = typeof x === "string" ? x.localeCompare(y) : x - y;
          return down ? -c : c;
        });
      }
      const tbody = table.tBodies[0], have = new Map([...tbody.rows].map((r) => [r.__item, r]));
      ordered.forEach((it, index) => {
        let row = have.get(it.key);
        if (!row) {
          const line = spark();
          const swatch = h("i", { class: "panel-swatch" });
          const name = h("span", { class: "panel-series-name" });
          row = h("tr", {}, h("td", { class: "panel-table-name" }, swatch, name), columns.map(() => h("td", { class: "panel-num" })),
                  h("td", { class: "panel-trend" }, line));
          row.__item = it.key; row.__swatch = swatch; row.__name = name; row.__spark = line;
        }
        have.delete(it.key);
        if (tbody.rows[index] !== row) tbody.insertBefore(row, tbody.rows[index] || null);
        row.__swatch.style.setProperty("--swatch", seriesInk(it));
        if (row.__name.textContent !== it.name) row.__name.textContent = it.name;
        columns.forEach((c, k) => {
          const cell = row.cells[k + 1], v = it.stats[c];
          cell.textContent = formatValue(v == null ? null : v * st.factor, st.unit, st.places);
          const top = st.options.bars_in_cells === "on" ? Math.max(0, ...st.items.map((x) => Math.abs(x.stats[c] ?? 0))) : 0;
          cell.classList.toggle("panel-cell-bar", top > 0);
          if (top > 0) cell.style.setProperty("--cell", `${Math.abs(v ?? 0) / top * 100}%`); else cell.style.removeProperty("--cell");
        });
        row.__spark.setValues(it.values, seriesInk(it));
      });
      for (const row of have.values()) row.remove();
    }

    /* the states: loading, empty, late, error. With data on the panel, late and error are said in its head and the
       numbers stay; with none, they take the panel's place. The words never sit on the plot */
    function setBody(which) {
      chartArea.hidden = which !== "chart";
      stats.hidden = which !== "stat";
      tableBox.hidden = which !== "table";
      message.hidden = which !== "message";
    }
    const dataBody = () => (st.form === "stat" ? "stat" : st.form === "table" ? "table" : "chart");
    const WORDS = { empty: "No data", late: "Late", error: "Could not load" };
    function setState(asked, reason = "") {
      /* late with nothing yet to show is a first load still under way: it is never said as a failure */
      const state = asked === "late" && !st.hasData ? "loading" : asked;
      if (asked === "late" && state === "loading") reason = `Still loading: ${reason || "waiting for the answer"}`;
      st.state = state;
      el.dataset.state = state;
      flag.className = "panel-flag";
      flag.textContent = "";
      flag.removeAttribute("title");
      if (state === "drawn") return;
      if (state === "loading") {
        if (st.hasData) { setBody(dataBody()); return; }
        message.className = "panel-message is-loading";
        message.replaceChildren(h("div", { class: "panel-skeleton", "aria-hidden": "true" }, h("span"), h("span"), h("span")),
                                h("p", { class: "panel-message-text" }, reason || "Loading"));
        setBody("message");
        return;
      }
      if ((state === "late" || state === "error") && st.hasData) {
        setBody(dataBody());
        flag.classList.add(`is-${state}`);
        flag.textContent = state === "late" ? "Late" : "Error";
        if (reason) flag.title = reason;
        return;
      }
      if (state === "empty") { st.hasData = false; readout.textContent = ""; }
      message.className = `panel-message is-${state}`;
      message.replaceChildren(h("p", { class: "panel-message-head" }, WORDS[state] || state),
                              reason ? h("p", { class: "panel-message-text" }, reason) : null);
      setBody("message");
    }

    /* what the answer says about itself (only part of the record was read, say), under the plot in every family */
    function said(words) {
      if (!words || warning.__lines.includes(words)) return;
      warning.__lines.push(words);
      warning.textContent = warning.__lines.join(" ");
      warning.title = warning.textContent;
      warning.hidden = false;
    }
    function sayNotes(results) {
      warning.__lines = [];
      warning.textContent = "";
      warning.hidden = true;
      const shown = shownQueries(st.cfg);
      for (const r of results) {
        const q = shown.find((x) => x.id === r.id);
        if (!q || r.error) continue;
        const words = r.note || (r.truncated ? "Only part of the record was read, so this chart is incomplete." : "");
        if (words) said(`${shown.length > 1 ? `${queryWord(q)}: ` : ""}${words.charAt(0).toUpperCase()}${words.slice(1)}${/[.!?]$/.test(words) ? "" : "."}`);
      }
    }
    function draw() {
      st.dirty = false;
      if (!st.last) return;
      const { meta } = st.last;
      /* the answer reshaped as the panel asks (never asked again for it), and each table laid out as this family reads it */
      const results = st.shown = resultFrames.reshaped(st.cfg.reshape, st.last.results || []).map((r) => resultFrames.drawable(r, st.form));
      sayNotes(results);
      if (st.form !== "stat" && st.form !== "table" && !FORM_REGISTRY.has(st.form)) {
        dropView();
        setState("error", `This panel asks for a chart form that is not available: ${st.form}.`);
        return;
      }
      const misfit = resultFrames.mismatch(FORM_REGISTRY.get(st.form), results);   // the shape decides which charts apply
      if (misfit) { dropView(); setState("empty", misfit); return; }
      if (st.form !== "box" && results.some((r) => r.x?.distribution && !r.shape)) {   // each category's spread is a box plot's answer
        dropView();
        setState("empty", "Aggregation none on a category is for a box plot: choose an aggregation for this chart.");
        return;
      }
      const byForm = drawnBy(results);
      if (byForm) { drawForm(byForm); return; }
      if (st.view) { dropView(); host.replaceChildren(); }
      const answer = readAnswer(st.cfg, results, st.slots);
      const span = (meta?.until ?? 0) - (meta?.since ?? 0);
      if (answer.failed.length && !answer.items.length) {
        st.hasData = st.hasData && st.items.length > 0;
        setState("error", answer.failed.map((r) => r.error).join("; "));
        return;
      }
      for (const it of answer.items) it.stats = statsOf(it.values);
      if (!answer.items.some((it) => it.stats.n)) {
        if (allHidden(st.cfg)) { setState("empty", ALL_HIDDEN); return; }
        const asked = shownQueries(st.cfg).map(queryWord).filter(Boolean).join(", ");
        setState("empty", shownQueries(st.cfg).length
          ? `Nothing recorded for ${asked || "this query"}${span > 0 ? ` in the last ${dur(span)}` : ""}.`
          : "This panel has no query yet.");
        return;
      }
      st.items = answer.items;
      st.times = answer.times;
      st.step = meta?.step || (answer.times.length > 1 ? answer.times[1] - answer.times[0] : 60);
      if (answer.mixed) st.step = Math.min(...answer.times.slice(1).map((t, i) => t - answer.times[i]));   // bars side by side, none over another
      if (answer.mixed && st.stacked) {
        const shared = answer.times.filter((_, t) => answer.items.every((it) => it.values[t] !== undefined)).length;
        said(`These queries have different time steps: stacked only at the ${shared} of ${answer.times.length} times they share.`);
      }
      st.x0 = meta?.since ?? answer.times[0];
      st.x1 = meta?.until ?? answer.times[answer.times.length - 1];
      if (st.form === "bar") st.x1 = Math.max(st.x1, answer.times[answer.times.length - 1] + st.step);
      if (st.x1 <= st.x0) st.x1 = st.x0 + st.step;
      const chosen = st.display.unit && st.display.unit !== "auto";
      const apart = unitsApart(st.cfg, results || []);
      if (apart.length) said(`These queries are in different units (${apart.join(", ")}) on one axis: compare their shapes, not their heights.`);
      const base = parseUnit(chosen ? st.display.unit : apart.length ? "" : answer.items.find((it) => it.unit)?.unit);
      const largest = Math.max(0, ...answer.items.map((it) => Math.max(Math.abs(it.stats.max ?? 0), Math.abs(it.stats.min ?? 0))));
      const read = chosen ? { unit: base, factor: 1 } : readableRate(base, largest);
      st.unit = read.unit;
      st.factor = read.factor;
      st.hasData = true;
      const big = largest * read.factor;
      st.places = st.display.decimals ?? (st.unit.kind === "dur" || st.unit.kind === "bytes" || big >= 1e4 ? null
        : st.unit.kind === "money" ? (big < 1000 ? 2 : 0) : big >= 100 ? 0 : big >= 10 ? 1 : 2);
      chip.textContent = chipOf(st.unit);
      chip.hidden = !chip.textContent;
      setState("drawn");
      setBody(dataBody());
      const logAsked = st.display.y?.log && !LOG_FORMS.has(st.form);
      const failedSaid = answer.failed.length ? `${answer.failed.length} of ${results.length} queries failed: ${answer.failed.map((r) => r.error).join("; ")}` : "";
      if (failedSaid) { flag.classList.add("is-error"); flag.textContent = "Partial"; flag.title = failedSaid; }
      const notes = [logAsked ? "log scale is for lines and areas" : "", answer.capped ? `${answer.capped} more grouped as other` : ""].filter(Boolean);
      drawKeys();
      if (notes.length) keys.append(h("span", { class: "panel-key panel-key-note" }, notes.join("; ")));
      keys.hidden = !keys.childElementCount;
      if (st.form === "stat") drawStats();
      else if (st.form === "table") drawTable();
      else { drawLegend(); drawPlot(); restReadout(); }
    }
    const applyConfig = (asked) => {
      const before = st.cfg;
      const cfg = normalizeForm({ ...asked, form: asked.form || "line" });
      st.cfg = cfg;
      st.display = cfg.display || {};
      st.form = cfg.form;
      const sortBefore = st.options.sort;
      st.options = formOptions(cfg);
      if (st.form === "table" && sortBefore !== st.options.sort) st.sort = null;
      const stack = PLOT_FORMS.has(st.form) ? st.options.stack : "none";
      st.stacked = stack === "stacked" || stack === "percent";
      st.percent = stack === "percent";
      st.filled = st.form === "line" && st.options.fill !== "none";
      st.overlaid = st.form === "bar" && !st.stacked && st.options.grouping === "overlaid";
      st.logScale = !!st.display.y?.log && LOG_FORMS.has(st.form) && !st.stacked;
      el.className = `panel panel-${cfg.size || "m"} panel-form-${st.form}${cfg.tall ? " panel-tall" : ""}`;
      el.dataset.panelId = cfg.id ?? "";
      title.textContent = cfg.title || "Untitled";
      note.textContent = cfg.note || "";
      note.hidden = !cfg.note;
      const shape = (c) => c && JSON.stringify([c.form, !!c.display?.y?.log, formOptions(c)]);
      if (before && shape(before) !== shape(cfg)) { dropPlot(); dropView(); }
    };

    el.update = (results, meta) => {
      st.last = { results, meta };
      if (!st.visible) { st.dirty = true; return; }
      draw();
    };
    el.setState = (state, reason) => setState(state, reason);
    el.setConfig = (cfg) => {
      const asked = JSON.stringify(st.cfg.queries || []);
      applyConfig(cfg);
      if (asked !== JSON.stringify(cfg.queries || [])) {   // what is on the panel no longer answers it
        st.last = null; st.dirty = false; st.hasData = false; readout.textContent = ""; warning.hidden = true; chip.textContent = ""; chip.hidden = true;
        if (allHidden(cfg)) setState("empty", ALL_HIDDEN); else setState("loading");
        return;
      }
      if (st.last) { if (st.visible) draw(); else st.dirty = true; }
    };
    el.destroy = () => {
      LIVE.delete(api_);
      seen.disconnect();
      heightWatch.disconnect();
      dropPlot();
      dropView();
      el.remove();
    };
    Object.defineProperty(el, "draws", { get: () => st.draws });
    Object.defineProperty(el, "plotView", { get: () => st.view });
    const api_ = { retheme() {
      const p = livePlot();
      if (p) p.redraw(true, true);
      if (st.view) { st.viewKey = ""; if (st.last) draw(); return; }
      if (st.hasData) { if (st.form === "stat") drawStats(); else if (st.form === "table") drawTable(); else drawLegend(); }
    } };
    LIVE.add(api_);

    /* off the screen nothing is redrawn; the newest answer is drawn when it comes back */
    const seen = new IntersectionObserver((entries) => {
      st.visible = entries[entries.length - 1].isIntersecting;
      if (st.visible && st.dirty) draw();
    }, { rootMargin: "200px" });
    seen.observe(el);

    applyConfig(config);
    if (allHidden(config)) setState("empty", ALL_HIDDEN); else setState("loading");
    return el;
  }

  /* ------------------------------------------------ a diagram on a dashboard (dev/records/dashboard-diagram-panel.md) */

  /* a Diagram address (view, system, open, select, item or kind) or an Items Graph address (kinds, kind or system), as
     the panel draws it; null when it is neither */
  function diagramAddress(text) {
    let u;
    try { u = new URL(String(text || ""), location.origin); } catch (e) { return null; }
    if (u.origin !== location.origin) return null;
    const got = (k) => u.searchParams.get(k) || "";
    if (u.pathname === "/diagram") {
      const q = new URLSearchParams({ view: got("view") || "dynamics" });
      for (const k of ["system", "open", "select", "item", "kind", "window"]) if (got(k)) q.set(k, got(k));
      return { model: true, route: `/diagram?${q}` };
    }
    if (u.pathname !== "/items" && !u.pathname.startsWith("/items/")) return null;
    let tail;                                          // a path that will not decode is no address: this panel says so
    try { tail = decodeURIComponent(u.pathname.slice(7)); } catch (e) { return null; }
    const kinds = got("kinds") || got("kind") || tail, system = got("system");
    return kinds || system ? { model: false, ask: kinds ? { kinds } : { system }, route: u.pathname + u.search } : null;
  }
  /* one model diagram is live on the page at a time: another is drawn when it is clicked. Nothing is asked until a
     panel is on the screen; of those that come on it together, the first in reading order is the one drawn */
  let liveDiagram = null;
  const onScreen = new IntersectionObserver((es) => {
    const now = es.filter((e) => e.isIntersecting).map((e) => e.target)
      .sort((a, b) => (a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING ? -1 : 1));
    for (const el of now) { onScreen.unobserve(el); el.__seen?.(); }
  });
  function diagramPanel(config) {
    let cfg = config, at = diagramAddress(cfg.display?.address), frame = null, graph = null, asked = "", seen = false, ready = false, n = 0;
    const title = h("h3", { class: "panel-title" }), note = h("p", { class: "panel-note" }), flag = h("span", { class: "panel-flag", role: "status" });
    const body = h("div", { class: "panel-body panel-diagram" });
    const el = h("section", { class: "panel panel-form-diagram" }, h("header", { class: "panel-head" }, h("div", { class: "panel-names" }, title, note), flag), body);
    const say = (words) => { note.textContent = words; note.hidden = !words; };
    const link = (kid) => h("a", { class: "panel-diagram-link", href: appHref(at.route), title: "Open it whole",
                                   onclick: (ev) => { if (el.closest(".editing")) ev.preventDefault(); } }, kid);
    function sleep() {                                   // drawn again on a click, while another is live
      frame = null; ready = false;
      if (liveDiagram === api_) liveDiagram = null;
      body.replaceChildren(h("button", { type: "button", class: "ghost panel-diagram-wake", onclick: wake }, "Draw this diagram here"));
    }
    function wake() {
      if (liveDiagram && liveDiagram !== api_) liveDiagram.sleep();
      liveDiagram = api_;
      ready = false;
      frame = h("iframe", { title: cfg.title || "Diagram", tabindex: "-1", src: `${at.route}&pane=embed` });
      body.replaceChildren(link(frame));
      el.dataset.state = "loading";
    }
    async function drawGraph() {                         // the Items Graph, by relGraph; drawn again only when it changed
      const mine = ++n, d = await api("items-graph", at.ask).catch((e) => ({ err: e }));
      if (mine !== n || !el.isConnected) return;
      if (d.err) { body.replaceChildren(h("p", { class: "panel-message-text" }, String(d.err.message || d.err))); el.dataset.state = "error"; return; }
      const text = JSON.stringify(d);
      if (text === asked) return;
      asked = text;
      graph ||= relGraph((id) => navigate(`/item/${encodeURIComponent(id)}`));
      if (!graph.isConnected) body.replaceChildren(link(graph));
      await graph.draw(rgModel(d, { finished: "hide" }), { finished: "hide" });
      graph.querySelector(".rg-stage").style.height = "";       // the panel's height, not the Items page's
      graph.querySelector(".rg-tools button")?.dispatchEvent(new MouseEvent("click"));   // fitted to it (relGraph's Fit; not bubbling to the link)
      const vp = graph.querySelector(".rg-view"), k = Number(/scale\(([\d.]+)\)/.exec(vp?.getAttribute("transform") || "")?.[1] || 1);
      if (k < 1) vp.setAttribute("transform", "translate(8,8) scale(1)");   // 11 px text is never drawn smaller
      say(k < 1 ? "Too large to read here: open on the Items page" : cfg.note || "");
      el.dataset.state = "drawn";
    }
    function heard(ev) {                                 // the frame's word: drawn, and whether it fits
      const m = ev.data;
      if (!frame || ev.source !== frame.contentWindow || m?.ergostat !== "embed") return;
      ready = true;
      el.dataset.state = "drawn";
      say(m.fits ? cfg.note || "" : m.folded ? "Its systems closed: open on the Diagram" : "Too large to read here: open on the Diagram");
    }
    function show() {
      if (!at) { body.replaceChildren(h("p", { class: "panel-message-text" }, "Not a Diagram or an Items Graph address")); el.dataset.state = "empty"; return; }
      if (at.model) { if (!liveDiagram || liveDiagram === api_) wake(); else sleep(); } else drawGraph();
    }
    addEventListener("message", heard);
    el.__seen = () => { seen = true; show(); };
    onScreen.observe(el);
    const api_ = { sleep };
    const apply = (c) => {
      cfg = c;
      el.dataset.panelId = c.id ?? "";
      title.textContent = c.title || "Diagram";
      say(c.note || "");
    };
    el.update = () => {                                  // the dashboard's poll: values only while the structure holds
      flag.textContent = "";
      if (el.dataset.state === "late") el.dataset.state = ready || asked ? "drawn" : "loading";
      if (frame?.contentWindow && ready) frame.contentWindow.postMessage({ ergostat: "embed", type: "poll" }, location.origin);
      else if (seen && at && !at.model) drawGraph();
    };
    el.setState = (state) => { if (state !== "loading" || !el.dataset.state) el.dataset.state = state; flag.textContent = state === "late" ? "Late" : ""; };
    el.setConfig = (c) => {
      const was = at?.route;
      apply(c);
      at = diagramAddress(c.display?.address);
      if (seen && at?.route !== was) { asked = ""; graph = null; if (liveDiagram === api_) liveDiagram = null; show(); }
    };
    el.destroy = () => { onScreen.unobserve(el); removeEventListener("message", heard); if (liveDiagram === api_) liveDiagram = null; el.remove(); };
    apply(cfg);
    return el;
  }

  let pageGroup = null;
  const sharedGroup = () => (pageGroup ||= chartGroup("panels"));

  /* ------------------------------------------------ asking */

  function encodeQuery(obj) {
    const bytes = new TextEncoder().encode(JSON.stringify(obj));
    let text = "";
    for (const b of bytes) text += String.fromCharCode(b);
    return btoa(text).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  }
  /* the queries a panel shows, as its family asks for them: two families that ask alike draw one answer */
  function askedOf(asIs) {
    const cfg = normalizeForm(asIs), def = FORM_REGISTRY.get(cfg.form), options = def ? formOptions(cfg) : {};
    return shownQueries(cfg).map((q) => (def?.ask ? def.ask(q, options) : q));
  }
  /* every panel's queries in one request: an identical query is asked once, and each id is made unique and mapped back */
  async function queryPanels(configs, { since = 86400, until = null, points = 120, signal } = {}) {
    const asked = new Map(), wanted = [];
    const plain = ({ id, label, hidden, ...rest }) => rest;
    /* one query as it is sent: what it reads from is sent too, under the name that query gets. A reference that leads
       nowhere, or back to itself, keeps a name no other query has, so the answer says so for this query alone */
    function send(q, byId, path) {
      const rest = plain(q);
      const follow = (ref) => {
        const other = byId.get(String(ref));
        return other && !path.has(other) ? send(other, byId, new Set([...path, other])) : `unknown:${ref}`;
      };
      if (typeof rest.x?.query === "string" || typeof rest.x?.query === "number") rest.x = { ...rest.x, query: follow(rest.x.query) };
      else if (rest.x?.query && typeof rest.x.query === "object") rest.x = { ...rest.x, query: plain(rest.x.query) };
      for (const side of ["input", "output"]) {
        const part = rest[side];
        if (typeof part === "string" || typeof part === "number") {
          const other = byId.get(String(part));
          rest[side] = other && !path.has(other) ? plain(other) : { source: `unknown:${part}` };
        } else if (part && typeof part === "object") rest[side] = plain(part);
      }
      const shape = JSON.stringify(rest);
      if (!asked.has(shape)) asked.set(shape, { ...rest, id: `q${asked.size}` });
      return asked.get(shape).id;
    }
    configs.forEach((asIs) => {
      const cfg = normalizeForm(asIs), def = FORM_REGISTRY.get(cfg.form), options = def ? formOptions(cfg) : {};
      const byId = new Map((cfg.queries || []).filter((q) => q.id != null).map((q) => [String(q.id), q]));
      const shown = new Set(shownQueries(cfg));
      (cfg.queries || []).forEach((q, n) => {
        if (!shown.has(q)) return;
        const fitted = def?.ask ? def.ask(q, options) : q;
        wanted.push({ panel: cfg.id, id: q.id ?? String(n), as: send(fitted, byId, new Set([q])) });
      });
    });
    const out = new Map(configs.map((c) => [c.id, { results: [], meta: null }]));
    if (!asked.size) return out;
    const batches = batched([...asked.values()]);
    const q = encodeQuery({ since, until, points, queries: batches[0] });
    let answer;
    if (typeof SNAP !== "undefined" && SNAP) answer = await api("query", { q });
    else {
      const r = await fetch(`/api/query?q=${q}`, { signal });
      if (!r.ok) throw new Error(`the query answered ${r.status}`);
      answer = await r.json();
      await askAgainWhenBusy(answer, batches[0], points, signal);
      for (const more of batches.slice(1)) {             // the same window, so every panel reads the same moment
        const part = encodeQuery({ since: answer.until - answer.since, until: answer.until, points, queries: more });
        const r2 = await fetch(`/api/query?q=${part}`, { signal });
        if (!r2.ok) throw new Error(`the query answered ${r2.status}`);
        const next = await r2.json();
        await askAgainWhenBusy(next, more, points, signal);
        const have = new Set(answer.results.map((x) => x.id));
        answer.results.push(...next.results.filter((x) => !have.has(x.id)));
      }
    }
    const meta = { now: answer.now, since: answer.since, until: answer.until, step: answer.step };
    const byId = new Map((answer.results || []).map((r) => [r.id, r]));
    for (const c of configs) out.get(c.id).meta = meta;
    for (const w of wanted) {
      const r = byId.get(w.as);
      out.get(w.panel).results.push(r ? { ...r, id: w.id } : { id: w.id, error: "the answer left this query out" });
    }
    return out;
  }
  /* at most what one request may hold, a query always beside the one it reads its X from */
  const MOST_IN_REQUEST = 64;
  function batched(queries) {
    const byId = new Map(queries.map((x) => [x.id, x])), out = [[]];
    for (const x of queries) {
      const feeds = typeof x.x?.query === "string" ? byId.get(x.x.query) : null;
      let now = out[out.length - 1];
      const need = 1 + (feeds && !now.includes(feeds) ? 1 : 0);
      if (now.length + need > MOST_IN_REQUEST) out.push(now = []);
      if (feeds && !now.includes(feeds)) now.push(feeds);
      if (!now.includes(x)) now.push(x);
    }
    return out;
  }
  /* the server reads the event log for only a few charts at once and refuses the rest at once. Those are asked for again,
     alone, on the same window, a few times with a growing pause: what was read is kept there, so each round gets further */
  const BUSY = /(^|: )busy:/, BUSY_PAUSES = [500, 1000, 2000];
  const paused = (ms, signal) => new Promise((done, no) => {
    if (signal?.aborted) { no(new DOMException("gave up", "AbortError")); return; }
    const t = setTimeout(done, ms);
    signal?.addEventListener("abort", () => { clearTimeout(t); no(new DOMException("gave up", "AbortError")); }, { once: true });
  });
  async function askAgainWhenBusy(answer, sent, points, signal) {
    const byId = new Map(sent.map((x) => [x.id, x]));
    for (const pause of BUSY_PAUSES) {
      const busy = (answer.results || []).filter((r) => BUSY.test(r.error || "")).map((r) => r.id);
      if (!busy.length) return;
      await paused(pause * (0.75 + Math.random() / 2), signal);
      const wanted = new Set(busy);
      for (const id of busy) if (byId.get(id)?.x?.query != null && byId.has(byId.get(id).x.query)) wanted.add(byId.get(id).x.query);
      const q = encodeQuery({ since: answer.until - answer.since, until: answer.until, points, queries: sent.filter((x) => wanted.has(x.id)) });
      let again;
      try {
        const r = await fetch(`/api/query?q=${q}`, { signal });
        if (!r.ok) return;                               // what was answered stands, and the rest says busy
        again = await r.json();
      } catch (e) {
        if (e?.name === "AbortError") throw e;
        return;
      }
      const fresh = new Map((again.results || []).map((r) => [r.id, r]));
      answer.results = answer.results.map((r) => (busy.includes(r.id) && fresh.has(r.id) ? fresh.get(r.id) : r));
    }
  }
  let fieldsAsked = null;
  function queryFields() {
    fieldsAsked ||= (async () => {
      const r = await fetch("/api/query/fields");
      if (!r.ok) throw new Error(`the fields answered ${r.status}`);
      return r.json();
    })().catch((e) => { fieldsAsked = null; throw e; });
    return fieldsAsked;
  }

  /* a page of panels: drawn in a container and kept current in one request each refresh. A hidden tab asks for
     nothing; an answer overtaken by a newer question is dropped */
  function pagePanels(container, configs, { since = 86400, every = 30000 } = {}) {
    container.classList.add("panel-grid");
    const group = chartGroup("panels");
    const panels = new Map();
    let current = [], seq = 0, flight = null, ticks = 0, timer = null, stopped = false, lastAt = 0;

    function place(list) {
      const keep = new Set(list.map((c) => c.id));
      for (const [id, el] of panels) if (!keep.has(id)) { el.destroy(); panels.delete(id); }
      list.forEach((cfg, i) => {
        let el = panels.get(cfg.id);
        if (el) el.setConfig(cfg);
        else { el = chartPanel(cfg, { group }); panels.set(cfg.id, el); }
        if (container.children[i] !== el) container.insertBefore(el, container.children[i] || null);
      });
      current = list;
    }
    function refresh() {
      if (stopped || document.hidden) return;
      const mine = ++seq;
      flight?.ctrl.abort();
      const ctrl = new AbortController();
      flight = { ctrl };
      ticks = 0;
      queryPanels(current, { since, signal: ctrl.signal }).then((answers) => {
        if (mine !== seq || stopped) return;
        flight = null;
        lastAt = Date.now();
        for (const [id, a] of answers) {
          const el = panels.get(id);
          if (el) el.update(a.results, a.meta || {});
        }
      }).catch((e) => {
        if (mine !== seq || stopped) return;
        flight = null;
        const gaveUp = e?.name === "AbortError";         // the next tick asks again: late, or a first load still loading
        const words = gaveUp ? `no answer in ${dur((every * GIVE_UP_TICKS) / 1000)}` : e?.message || "the query failed";
        for (const el of panels.values()) el.setState(gaveUp ? "late" : "error", words);
      });
    }
    function tick() {
      if (stopped || document.hidden) return;
      if (!flight) { refresh(); return; }
      ticks++;
      if (ticks >= GIVE_UP_TICKS) {                      // given up on: the catch above says so, and the next tick asks again
        flight.ctrl.abort();
        return;
      }
      if (ticks >= LATE_AFTER_TICKS) for (const el of panels.values()) el.setState("late", `waiting ${dur((ticks * every) / 1000)} for the answer`);
    }
    const onVisible = () => { if (!document.hidden && !flight && Date.now() - lastAt >= every) refresh(); };

    place(configs);
    document.addEventListener("visibilitychange", onVisible);
    timer = setInterval(tick, every);
    refresh();
    return {
      stop() {
        stopped = true;
        clearInterval(timer);
        document.removeEventListener("visibilitychange", onVisible);
        flight?.ctrl.abort();
        for (const el of panels.values()) el.destroy();
        panels.clear();
      },
      setConfigs(next) { if (stopped) return; place(next); refresh(); },
    };
  }

  window.panelNumbers = { parseUnit, chipOf, formatValue, axisLabels, durationSteps: DURATION_STEPS };
  Object.assign(window, { chartPanel, diagramPanel, diagramAddress, queryPanels, queryFields, pagePanels, registerPlotForm, plotForms, normalizeForm, askedOf });
})();
