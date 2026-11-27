import { Document, isMap, isScalar, isSeq, parse as parseYaml, parseDocument, type Pair, type YAMLMap, type YAMLSeq } from "yaml";

/* A projection's definition (SPEC §5a), its YAML body read into what the workbench's steps show, and each edit a step
   makes written back into the text, the rest of it (comments, order, quoting) kept as it was. Pure: no React. */

export interface FieldDef { name: string; type: string; values: string; fold: string; description: string }
export interface KindDef { name: string; when: string; key: string; keyParts: string[]; values: [string, string][] }
export interface Draft { query: string; key: string; keyParts: string[]; time: string; fields: FieldDef[]; kinds: KindDef[] }

const OUT = { lineWidth: 0, flowCollectionPadding: false } as const;
const ORDER = ["query", "key", "time", "fields", "events"];

export const TYPES = ["text", "number", "integer", "boolean", "time", "duration", "map", "list of text"];
export const FOLDS = ["replace", "first", "add", "min", "max", "append", "union", "merge", "count", "mean", "stdev", "rms"];

/** A key's parts: a list's members, or a single expression as one part (none: []). */
function partsOf(v: unknown): string[] {
  if (v == null || v === "") return [];
  if (Array.isArray(v)) return v.map((x) => (x == null ? "" : String(x)));
  return [String(v)];
}

/** An expression's text as the steps show it (a list, as YAML writes one in a line). */
function said(v: unknown): string {
  if (v == null) return "";
  if (typeof v === "string") return v;
  if (Array.isArray(v)) return flow(v);
  return String(v);
}

/** A list as one line of YAML (`[data.account, "each(x, 'id')"]`): what a key's box shows and is read back from. */
function flow(v: unknown[]): string {
  const d = new Document(v);
  (d.contents as YAMLSeq).flow = true;
  return d.toString(OUT).trim();
}

function typeOf(v: unknown): string {
  if (v == null) return "";
  if (typeof v === "string") return v;
  if (typeof v === "object" && !Array.isArray(v)) {
    return typeOf((v as Record<string, unknown>).type);
  }
  return String(v);
}

export function read(text: string): { draft: Draft } | { error: string } {
  const doc = parseDocument(text);
  if (doc.errors.length) return { error: doc.errors[0].message.split("\n")[0] };
  const js = (doc.toJS() ?? {}) as unknown;
  if (typeof js !== "object" || Array.isArray(js) || js == null) return { error: "the definition is a map: query:, key:, fields:, events:" };
  const o = js as Record<string, any>;
  const fields: FieldDef[] = Object.entries(o.fields && typeof o.fields === "object" ? o.fields : {}).map(([name, v]: [string, any]) => ({
    name, type: typeOf(v),
    values: v && typeof v === "object" && Array.isArray(v.values) ? flow(v.values) : "",
    fold: v && typeof v === "object" && !Array.isArray(v) ? said(v.fold) : "",
    description: v && typeof v === "object" && !Array.isArray(v) ? said(v.description) : "",
  }));
  const kinds: KindDef[] = Object.entries(o.events && typeof o.events === "object" ? o.events : {}).map(([name, v]: [string, any]) => {
    const e = v && typeof v === "object" && !Array.isArray(v) ? v : {};
    return { name, when: said(e.when), key: said(e.key), keyParts: partsOf(e.key),
      values: Object.entries(e).filter(([k]) => k !== "when" && k !== "key").map(([k, x]) => [k, said(x)] as [string, string]) };
  });
  return { draft: { query: said(o.query), key: said(o.key), keyParts: partsOf(o.key), time: said(o.time), fields, kinds } };
}

// ---- edits: each takes the text and gives it back changed (unchanged when the text does not parse)

function edit(text: string, f: (doc: Document, top: YAMLMap) => void): string {
  const doc = parseDocument(text);
  if (doc.errors.length) return text;
  if (!isMap(doc.contents)) doc.contents = doc.createNode({}) as any;
  f(doc, doc.contents as unknown as YAMLMap);
  const out = doc.toString(OUT);
  return out.trim() === "{}" ? "" : out;
}

/** A value typed in a box, as YAML holds it: a number, true, false or null on its own; a list for `[...]`; else text. */
function valueOf(s: string): unknown {
  const t = s.trim();
  if (/^-?\d+(\.\d+)?$/.test(t)) return Number(t);
  if (t === "true" || t === "false") return t === "true";
  if (t === "null") return null;
  if (t.startsWith("[") && t.endsWith("]")) {
    try { const v = parseYaml(t); if (Array.isArray(v)) return v; } catch { /* text, then */ }
  }
  return s;
}

/** A field's values typed in a box (`pending, running` or `[pending, running]`) as a list; none: "". */
function valuesOf(s: string): unknown {
  const t = s.trim();
  if (!t) return "";
  const v = valueOf(t.startsWith("[") ? t : `[${t}]`);
  return Array.isArray(v) && v.length ? v : "";
}

function node(doc: Document, v: unknown) {
  const n = doc.createNode(v);
  if (isSeq(n)) n.flow = true;
  return n;
}

const pairOf = (m: YAMLMap, k: string): Pair | undefined =>
  m.items.find((p) => (isScalar(p.key) ? String(p.key.value) : String(p.key)) === k) as Pair | undefined;

/** Set `k` of map `m` to `v` (in place, keeping a scalar's quoting), inserted by `order` when new; "" or null takes it out. */
function put(doc: Document, m: YAMLMap, k: string, v: unknown, order?: string[]) {
  if (v === "" || v === undefined) { m.delete(k); return; }
  const p = pairOf(m, k);
  if (p) {
    if (isScalar(p.value) && !Array.isArray(v) && (v === null || typeof v !== "object")) { p.value.value = v; return; }
    p.value = node(doc, v);
    return;
  }
  const np = doc.createPair(k, v);
  if (isSeq(np.value)) (np.value as YAMLSeq).flow = true;
  const at = order ? order.indexOf(k) : -1;
  const i = at < 0 ? -1 : m.items.findIndex((x) => order!.indexOf(isScalar(x.key) ? String(x.key.value) : "") > at
    || order!.indexOf(isScalar(x.key) ? String(x.key.value) : "") < 0);
  if (i < 0) m.items.push(np as any); else m.items.splice(i, 0, np as any);
}

/** The map under `k` (made, block style, when missing or not a map). */
function mapAt(doc: Document, top: YAMLMap, k: string): YAMLMap {
  const p = pairOf(top, k);
  if (p && isMap(p.value)) return p.value as YAMLMap;
  put(doc, top, k, {}, ORDER);
  const m = pairOf(top, k)!.value as YAMLMap;
  m.flow = false;
  return m;
}

function rename(m: YAMLMap, from: string, to: string, doc: Document) {
  const p = pairOf(m, from);
  if (p && !pairOf(m, to)) p.key = doc.createNode(to) as any;
}

/** The query, the key or the time (`time:`), a key's text read as a list when it is one. */
export const setTop = (text: string, k: "query" | "key" | "time", v: string) =>
  edit(text, (doc, top) => put(doc, top, k, k === "key" ? valueOf(v) : v.trim() ? v : "", ORDER));

/** A key as its parts: one part written as itself, several as a list, none takes the key out. Each part is one
 *  expression, never parsed as YAML here, so `data.detail['instance-id']` needs no quoting. */
function keyValue(parts: string[]): unknown {
  const ps = parts.map((x) => x.trim()).filter(Boolean);
  return ps.length === 0 ? "" : ps.length === 1 ? ps[0] : ps;
}

/** The projection's key, from its parts. */
export const setKeyParts = (text: string, parts: string[]) =>
  edit(text, (doc, top) => put(doc, top, "key", keyValue(parts), ORDER));

/** A kind of event's own key, from its parts (none: it uses the projection's). */
export const setKindKeyParts = (text: string, kind: string, parts: string[]) =>
  edit(text, (doc, top) => {
    const p = pairOf(mapAt(doc, top, "events"), kind);
    if (!p) return;
    if (!isMap(p.value)) { const e = doc.createNode({}) as YAMLMap; e.flow = false; p.value = e; }
    put(doc, p.value as YAMLMap, "key", keyValue(parts), ["when", "key"]);
  });

export const addField = (text: string, name: string, type = "text") =>
  edit(text, (doc, top) => {
    const m = mapAt(doc, top, "fields");
    if (pairOf(m, name)) return;
    const n = doc.createNode({ type }) as YAMLMap;
    n.flow = true;
    m.items.push(doc.createPair(name, n) as any);
  });

/** One part of a field's entry (its type, values, fold or description; "" takes it out). Its values (the only ones it
    may hold, `values: [a, b]`) are typed as a list, with or without the brackets. */
export const setField = (text: string, name: string, part: "type" | "values" | "fold" | "description", v: string) =>
  edit(text, (doc, top) => {
    const m = mapAt(doc, top, "fields");
    const p = pairOf(m, name);
    if (!p) return;
    if (!isMap(p.value)) {                              // `name: text` or `name:`: written out as a map
      const was = isScalar(p.value) && p.value.value != null ? String(p.value.value) : "";
      const n = doc.createNode(was ? { type: was } : {}) as YAMLMap;
      n.flow = true;
      p.value = n;
    }
    const f = p.value as YAMLMap;
    const value = part === "values" ? valuesOf(v) : part === "fold" && v === "replace" ? "" : v;
    put(doc, f, part, value, ["type", "values", "fold", "description"]);
  });

/** A field renamed, and in every kind of event that tells it. */
export const renameField = (text: string, from: string, to: string) =>
  edit(text, (doc, top) => {
    rename(mapAt(doc, top, "fields"), from, to, doc);
    const ev = pairOf(top, "events");
    if (ev && isMap(ev.value)) for (const k of (ev.value as YAMLMap).items) if (isMap(k.value)) rename(k.value as YAMLMap, from, to, doc);
  });

/** A field taken out, and out of every kind of event that told it. */
export const removeField = (text: string, name: string) =>
  edit(text, (_doc, top) => {
    const f = pairOf(top, "fields");
    if (f && isMap(f.value)) (f.value as YAMLMap).delete(name);
    const ev = pairOf(top, "events");
    if (ev && isMap(ev.value)) for (const k of (ev.value as YAMLMap).items) if (isMap(k.value)) (k.value as YAMLMap).delete(name);
  });

/** A kind of event added with its `when:` (a name taken already gets -2, -3...). */
export const addKind = (text: string, name: string, when: string) =>
  edit(text, (doc, top) => {
    const m = mapAt(doc, top, "events");
    let n = name, i = 2;
    while (pairOf(m, n)) n = `${name}-${i++}`;
    const e = doc.createNode({ when: valueOf(when) }) as YAMLMap;
    e.flow = false;
    m.items.push(doc.createPair(n, e) as any);
  });

export const renameKind = (text: string, from: string, to: string) =>
  edit(text, (doc, top) => rename(mapAt(doc, top, "events"), from, to, doc));

export const removeKind = (text: string, name: string) =>
  edit(text, (doc, top) => { mapAt(doc, top, "events").delete(name); });

/** A kind of event's `when:`, `key:` or the expression for a field it tells ("" takes it out). */
export const setKind = (text: string, kind: string, entry: string, v: string) =>
  edit(text, (doc, top) => {
    const p = pairOf(mapAt(doc, top, "events"), kind);
    if (!p) return;
    if (!isMap(p.value)) { const e = doc.createNode({}) as YAMLMap; e.flow = false; p.value = e; }
    put(doc, p.value as YAMLMap, entry, v.trim() ? valueOf(v) : "", ["when", "key"]);
  });

// ---- expressions made from a value clicked in an event

const KEYWORDS = new Set(["and", "or", "not", "in", "is", "if", "else", "for", "from", "import", "class", "def", "return",
  "lambda", "None", "True", "False", "pass", "while", "with", "yield", "as", "assert", "break", "continue", "del", "elif",
  "except", "finally", "global", "nonlocal", "raise", "try", "async", "await"]);

const quoted = (s: string) => `'${s.replace(/\\/g, "\\\\").replace(/'/g, "\\'")}'`;

/** The expression reading the value at `path` in an event (`data.detail['instance-id']`, `data.items[0].id`). */
export function pathExpr(path: (string | number)[]): string {
  let s = String(path[0]);
  for (const p of path.slice(1)) {
    s += typeof p === "number" ? `[${p}]` : /^[A-Za-z_][A-Za-z0-9_]*$/.test(p) && !KEYWORDS.has(p) ? `.${p}` : `[${quoted(p)}]`;
  }
  return s;
}

/** A value as the expression writes it. */
export function literal(v: unknown): string {
  if (v == null) return "null";
  if (typeof v === "string") return quoted(v);
  if (typeof v === "boolean") return v ? "true" : "false";
  return String(v);
}

/** The query narrowed by one more condition. */
export function narrowed(query: string, cond: string): string {
  const q = query.trim();
  if (!q) return cond;
  return /\bor\b/.test(q) ? `(${q}) and ${cond}` : `${q} and ${cond}`;
}

/** The query's events of one kind: the query and its `when:`. */
export function ofKind(query: string, when: string): string {
  const w = when.trim();
  if (!w || w === "true") return query;
  return query.trim() ? `(${query}) and (${w})` : w;
}
