/* each answer's shape, and the chart families that take it (SPEC §4e, Result shapes). The server says what an answer is:
   series, table, points, distribution or response, with its roles, form, order or dims. Each family declares, under
   `shapes`, what it takes of each shape; this says whether it takes an answer and, when not, how to reshape the data,
   in one sentence. It also lays a table out as each family reads it, and holds the reshaping no query language does
   for us: pivot, join by field, group. Reshaping happens here, after the answer: it never asks the server again. */
"use strict";

(() => {
  const CANDLE = ["open", "high", "low", "close"], TWO = ["input", "output"];
  const hasRoles = (r, roles) => roles.every((x) => (r.roles || []).includes(x));
  const list = (xs) => (xs.length < 2 ? xs.join("") : `${xs.slice(0, -1).join(", ")} or ${xs[xs.length - 1]}`);
  const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;

  /* does result r meet c, what a family declared it takes of r's shape */
  function meets(c, r) {
    if (r.shape === "series") {
      if (c.roles === "none") return !(r.roles || []).length;
      if (Array.isArray(c.roles)) return hasRoles(r, c.roles);
      return !hasRoles(r, CANDLE);                       // (candles are for a family that names their roles)
    }
    if (r.shape === "table") {
      const dims = r.dims || [];
      return (c.dims == null || dims.length === c.dims) && (c.dim == null || dims[0]?.type === c.dim)
        && (c.rows == null || (r.rows || []).length === c.rows) && (c.measures == null || (r.measures || []).length >= c.measures);
    }
    if (r.shape === "points") return !c.order || r.order === c.order;
    if (r.shape === "distribution") return !c.form || c.form.includes(r.form);
    if (r.shape === "response") return !c.has || (r.has || []).includes(c.has);
    return false;
  }
  function wanted(shape, c) {
    if (shape === "series") return c.roles === "none" ? "values over time" : !Array.isArray(c.roles) ? "values over time or two signals"
      : c.roles[0] === "input" ? "two signals, an input and an output" : "open, high, low and close over time";
    if (shape === "table") return `a table${c.dims === 1 ? " of one dimension" : ""}${c.dim === "number" ? " that is a number" : ""}`
      + `${c.rows === 1 ? " and one row" : ""}${c.measures ? ` and ${c.measures} measures` : ""}`;
    if (shape === "points") return c.order === "time" ? "points in time order" : "points";
    if (shape === "distribution") return `a distribution as ${list(c.form || ["bins"])}`;
    return c.has === "system" ? "a model's poles and zeros" : "a frequency response";
  }
  function what(r) {
    if (r.shape === "series") return hasRoles(r, TWO) ? "two signals" : hasRoles(r, CANDLE) ? "candles" : "values over time";
    if (r.shape === "table") return `a table of ${plural((r.dims || []).length, "dimension")}, ${plural((r.measures || []).length, "measure")} and ${plural((r.rows || []).length, "row")}`;
    if (r.shape === "points") return r.order === "time" ? "points in time order" : "points";
    if (r.shape === "distribution") return `a distribution as ${r.form}`;
    return (r.has || []).includes("system") ? "a model's response" : "a frequency response from data";
  }
  /* null when the family `reg` takes every one of these results; else one sentence: what it needs, and how to get it */
  function mismatch(reg, results) {
    const takes = reg?.shapes || {};
    for (const r of results) {
      if (!r.shape || r.error) continue;
      if (takes[r.shape] && meets(takes[r.shape], r)) continue;
      const pivot = r.shape === "table" && (r.dims || []).length > 1 && takes.table;
      const fix = pivot ? `pivot it by ${r.dims[1].name} (Reshape: pivot ${r.dims[1].name})` : reg?.reshape || "choose another chart";
      return `${reg?.label || "This chart"} needs ${list(Object.entries(takes).map(([s, c]) => wanted(s, c)))}; this result is ${what(r)}: ${fix}.`;
    }
    return null;
  }

  /* a table as `family` reads it: a stat or table a value a row, a scatter its first two measures against each other,
     the rest each measure across the one dimension. The server's own layout is kept until a reshaping drops it */
  function drawable(r, family) {
    if (r.shape !== "table" || r.error) return r;
    const dims = r.dims || [], ms = r.measures || [], rows = r.rows || [], d = dims.length;
    const name = (row) => row.slice(0, d).join(" · ");
    if (family === "stat" || family === "table") {
      return { ...r, x: undefined, times: [0], series: rows.flatMap((row) => ms.map((m, j) => ({
        name: ms.length > 1 ? `${name(row)} · ${m.name}` : name(row), values: [row[d + j]] }))) };
    }
    if (family === "scatter" && ms.length >= 2) {
      return { ...r, unit: ms[1].unit, x: { type: "field", label: ms[0].name, unit: ms[0].unit, scale: "number" },
               series: [{ name: ms[1].name, xs: rows.map((x) => x[d]), values: rows.map((x) => x[d + 1]), ids: null }] };
    }
    if (r.x && r.series) return r;
    if (d !== 1) return { ...r, series: [] };
    const dim = dims[0], type = dim.edges ? "bins" : dim.type === "string" ? "category" : "field";
    return { ...r, x: { type, label: dim.name, unit: "", scale: type === "category" ? "category" : "number", ...(dim.edges ? { edges: dim.edges } : {}) },
             series: ms.map((m, j) => ({ name: m.name, xs: rows.map((x) => x[0]), values: rows.map((x) => x[1 + j]), ids: null })) };
  }

  /* the reshaping steps, each on a table and giving a table; a step that cannot apply says so as the result's error */
  const asTable = (r, dims, measures, rows) => ({ ...r, x: undefined, series: undefined, dims, measures, rows, unit: measures[0]?.unit ?? r.unit });
  const dimAt = (r, field) => (r.dims || []).findIndex((x) => x.name === field);
  const refused = (r, words) => ({ ...r, error: `Reshape: ${words}` });
  function pivot(r, field) {
    const at = dimAt(r, field), d = (r.dims || []).length;
    if (r.shape !== "table" || at < 0 || d < 2) return refused(r, `pivot ${field} needs a table with ${field} and another dimension`);
    const keep = r.dims.filter((_, i) => i !== at), values = [...new Set(r.rows.map((x) => String(x[at])))];
    const measures = values.flatMap((v) => r.measures.map((m) => ({ ...m, name: r.measures.length > 1 ? `${v} · ${m.name}` : v })));
    const rows = new Map();
    for (const x of r.rows) {
      const k = x.slice(0, d).filter((_, i) => i !== at), key = JSON.stringify(k);
      if (!rows.has(key)) rows.set(key, [...k, ...measures.map(() => null)]);
      const into = rows.get(key), base = keep.length + values.indexOf(String(x[at])) * r.measures.length;
      r.measures.forEach((_, j) => { into[base + j] = x[d + j]; });
    }
    return asTable(r, keep, measures, [...rows.values()]);
  }
  function group(r, field) {
    const at = dimAt(r, field), d = (r.dims || []).length;
    if (r.shape !== "table" || at < 0) return refused(r, `group ${field} needs a table with the dimension ${field}`);
    const rows = new Map();
    for (const x of r.rows) {
      const key = String(x[at]);
      if (!rows.has(key)) rows.set(key, [x[at], ...r.measures.map(() => null)]);
      const into = rows.get(key);
      r.measures.forEach((_, j) => { if (x[d + j] != null) into[1 + j] = (into[1 + j] ?? 0) + x[d + j]; });
    }
    return asTable(r, [r.dims[at]], r.measures, [...rows.values()]);
  }
  /* the tables of one dimension `field` joined into the first of them, row by row on its value; only rows in all stay */
  function join(results, field) {
    const tables = results.filter((r) => !r.error && r.shape === "table" && r.dims?.length === 1 && r.dims[0].name === field);
    if (tables.length < 2) return results.map((r) => refused(r, `join ${field} needs two tables whose one dimension is ${field}`));
    const keyed = tables.map((t) => new Map(t.rows.map((x) => [String(x[0]), x.slice(1)])));
    const rows = tables[0].rows.filter((x) => keyed.every((m) => m.has(String(x[0])))).map((x) => [x[0], ...keyed.flatMap((m) => m.get(String(x[0])))]);
    const joined = asTable(tables[0], tables[0].dims, tables.flatMap((t) => t.measures), rows);
    return results.filter((r) => !tables.includes(r) || r === tables[0]).map((r) => (r === tables[0] ? joined : r));
  }
  const STEPS = ["pivot", "join", "group"];
  /* a panel's reshaping, written one step a line ("pivot state"), applied in turn to its results */
  function reshaped(text, results) {
    let out = results;
    for (const line of String(text || "").split("\n").map((x) => x.trim()).filter(Boolean)) {
      const [step, field, ...rest] = line.split(/\s+/);
      if (!field || rest.length || !STEPS.includes(step)) return results.map((r) => refused(r, `"${line}" is not a step: write pivot, join or group, then a dimension's name`));
      out = step === "join" ? join(out, field) : out.map((r) => (r.error ? r : step === "pivot" ? pivot(r, field) : group(r, field)));
    }
    return out;
  }

  window.resultFrames = { mismatch, meets, drawable, reshaped, CANDLE, TWO };
})();
