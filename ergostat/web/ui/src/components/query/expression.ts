import { StreamLanguage, type StringStream } from "@codemirror/language";
import type { Completion, CompletionContext, CompletionResult } from "@codemirror/autocomplete";
import { tags } from "@lezer/highlight";

/* The expression language (SPEC §5a: a projection's query, a kind's when:, spec/handlers.py): drawn by a small
   StreamLanguage (Python's tokens, its few names and functions), and completed at the cursor from what the record
   holds: the paths into the events (the sample the page was given and GET /api/events/shape) after `data.`, a name
   that is not an identifier in bracket form (`data['detail-type']`), the values seen at a path after `PATH == '`,
   and the names, functions, methods and words of the language. */

export const NAMES = ["data", "type", "key", "source", "time"];
export const FUNCTIONS: [string, string][] = [
  ["has", "has('text'): some text of the event contains it"], ["glob", "glob(path, 'a*'): matches the pattern"],
  ["each", "each(list, 'field')"], ["pairs", "pairs(list, 'key', 'value')"], ["pick", "pick(obj, 'a', ...)"],
  ["omit", "omit(obj, 'a', ...)"], ["rename", "rename(obj, old='new')"],
  ["int", "int(x): a whole number from a number or its text (null if not)"], ["float", "float(x): a number (null if not)"],
  ["str", "str(x): as text"], ["json", "json(text): the JSON parsed (null if not JSON)"],
  ["lower", "lower(x): lower case"], ["upper", "upper(x): upper case"],
  ["unexplained", "unexplained(): no projection takes the event (the Events query only)"],
];
export const METHODS = ["startswith", "endswith", "lower", "upper", "strip", "split", "replace", "get"];
const WORDS = ["and", "or", "not", "in", "if", "else", "true", "false", "null"];
const KEYWORDS = new Set(["and", "or", "not", "in", "is", "if", "else"]);
const ATOMS = new Set(["true", "false", "null", "True", "False", "None"]);
const FN = new Set(FUNCTIONS.map(([f]) => f));

interface St { afterDot: boolean }

export const expressionLanguage = StreamLanguage.define<St>({
  name: "expression",
  startState: () => ({ afterDot: false }),
  token(stream: StringStream, st: St): string | null {
    if (stream.eatSpace()) return null;
    const dot = st.afterDot;
    st.afterDot = false;
    const q = stream.peek();
    if (q === "'" || q === '"') {
      stream.next();
      let esc = false;
      for (let c = stream.next(); c != null; c = stream.next()) {
        if (c === q && !esc) break;
        esc = !esc && c === "\\";
      }
      return "string";
    }
    if (stream.match(/^-?\d+(\.\d+)?([eE][+-]?\d+)?/)) return "number";
    if (stream.match(/^[A-Za-z_]\w*/)) {
      const w = stream.current();
      if (dot) return stream.peek() === "(" ? "function" : "propertyName";
      if (KEYWORDS.has(w)) return "keyword";
      if (ATOMS.has(w)) return "atom";
      if (FN.has(w) || stream.peek() === "(") return "function";
      if (NAMES.includes(w)) return "typeName";
      return "invalid";
    }
    if (stream.eat(".")) { st.afterDot = true; return "punctuation"; }
    if (stream.match(/^(==|!=|<=|>=|\*\*|\/\/|[<>+\-*/%])/)) return "operator";
    stream.next();
    return "punctuation";
  },
  tokenTable: { function: tags.function(tags.variableName) },
  languageData: { closeBrackets: { brackets: ["(", "[", "'", '"'] } },
});

// ---- what the record holds: a tree of paths, each with the values seen there

export interface Shape { children: Map<string, Set<string>>; values: Map<string, Map<string, unknown>> }

const K = (segs: string[]) => segs.join("\u0000");
const VALUES_MOST = 40;

export function emptyShape(): Shape { return { children: new Map(), values: new Map() }; }

function note(sh: Shape, segs: string[], value?: unknown, hasValue = false) {
  for (let i = 1; i < segs.length; i++) {
    const k = K(segs.slice(0, i));
    let c = sh.children.get(k);
    if (!c) sh.children.set(k, (c = new Set()));
    c.add(segs[i]);
  }
  if (hasValue && (value === null || ["string", "number", "boolean"].includes(typeof value))) {
    const k = K(segs);
    let vs = sh.values.get(k);
    if (!vs) sh.values.set(k, (vs = new Map()));
    if (vs.size < VALUES_MOST) vs.set(JSON.stringify(value), value);
  }
}

function walk(sh: Shape, v: unknown, segs: string[], depth: number) {
  if (Array.isArray(v)) {
    note(sh, segs);
    if (depth < 8) for (const x of v.slice(0, 5)) walk(sh, x, [...segs, "0"], depth + 1);
  } else if (v && typeof v === "object") {
    note(sh, segs);
    if (depth < 8) for (const [k, x] of Object.entries(v as Record<string, unknown>)) walk(sh, x, [...segs, k], depth + 1);
  } else note(sh, segs, v, true);
}

/** Events (as the query engine gives them: type, item, source, data) added to the shape. */
export function addEvents(sh: Shape, events: { type?: unknown; item?: unknown; source?: unknown; data?: unknown }[]) {
  for (const e of events.slice(0, 200)) {
    for (const [name, v] of [["type", e.type], ["key", e.item], ["source", e.source]] as const) if (v != null) note(sh, [name], v, true);
    walk(sh, e.data ?? {}, ["data"], 0);
  }
}

/** GET /api/events/shape's paths (`data.a.b`, a list's members `[]`, `item` the key) added to the shape. */
export function addShape(sh: Shape, rows: { path: string; examples?: unknown[] }[]) {
  for (const r of rows) {
    const segs = r.path.replace(/\[\]/g, ".0").split(".");
    if (segs[0] === "item") segs[0] = "key";
    if (!NAMES.includes(segs[0])) continue;
    note(sh, segs);
    for (const x of r.examples || []) note(sh, segs, x, true);
  }
}

// ---- completing

const IDENT = /^[A-Za-z_]\w*$/;
const PYWORDS = new Set([...KEYWORDS, ...ATOMS, "for", "from", "import", "class", "def", "return", "lambda", "pass",
  "while", "with", "yield", "as", "assert", "break", "continue", "del", "elif", "except", "finally", "global",
  "nonlocal", "raise", "try", "async", "await"]);
const quote = (s: string) => `'${s.replace(/\\/g, "\\\\").replace(/'/g, "\\'")}'`;
const lit = (v: unknown) => (v === null ? "null" : typeof v === "string" ? quote(v) : typeof v === "boolean" ? String(v) : String(v));
const seg = (s: string) => (/^\d+$/.test(s) ? `[${s}]` : IDENT.test(s) && !PYWORDS.has(s) ? `.${s}` : `[${quote(s)}]`);

const PATH = String.raw`(?:data|type|key|source|time)(?:\.[A-Za-z_]\w*|\[(?:'(?:[^'\\]|\\.)*'|"(?:[^"\\]|\\.)*"|\d+)\])*`;
const END_DOT = new RegExp(`(?:^|[^\\w.\\]'"])(${PATH})\\.(\\w*)$`);
const END_BRACKET = new RegExp(`(?:^|[^\\w.\\]'"])(${PATH})\\[(['"])([^'"]*)$`);
const END_VALUE = new RegExp(`(?:^|[^\\w.\\]'"])(${PATH})\\s*(?:==|!=|in\\s*\\[)\\s*(?:(['"])([^'"]*)|(\\w*))$`);
const END_WORD = /(?:^|[^\w.'"])([A-Za-z_]\w*)$/;

/** A path's text as its parts: `data.detail['x'][0]` is data, detail, x, 0. */
export function segments(text: string): string[] {
  const m = /^[A-Za-z_]\w*/.exec(text);
  if (!m) return [];
  const out = [m[0]];
  const re = /\.([A-Za-z_]\w*)|\[(?:'((?:[^'\\]|\\.)*)'|"((?:[^"\\]|\\.)*)"|(\d+))\]/g;
  re.lastIndex = m[0].length;
  for (let x = re.exec(text); x; x = re.exec(text)) out.push((x[1] ?? x[2] ?? x[3] ?? x[4]).replace(/\\(.)/g, "$1"));
  return out;
}

const starts = (name: string, typed: string) => name.toLowerCase().startsWith(typed.toLowerCase());

/** The completion source over the shape ``get()`` gives at the moment it is asked. */
export function expressionCompletion(get: () => Shape) {
  return (ctx: CompletionContext): CompletionResult | null => {
    const line = ctx.state.doc.lineAt(ctx.pos);
    const before = line.text.slice(0, ctx.pos - line.from);
    const sh = get();
    let m = END_VALUE.exec(before);
    if (m) {                                                  // a value seen at the path, after PATH == ' (or == )
      const vs = [...(sh.values.get(K(segments(m[1]))) || new Map()).values()];
      if (m[2] != null) {
        const typed = m[3];
        const opts: Completion[] = vs.filter((v): v is string => typeof v === "string" && starts(v, typed))
          .map((v) => ({ label: v, type: "text", detail: "seen", apply: v.replace(/\\/g, "\\\\").replace(new RegExp(m![2], "g"), `\\${m![2]}`) }));
        return opts.length ? { from: ctx.pos - typed.length, options: opts, filter: false } : null;
      }
      const typed = m[4] || "";
      const opts: Completion[] = vs.map((v) => ({ label: lit(v), type: "text", detail: "seen" })).filter((o) => starts(o.label, typed) || !typed);
      return opts.length || ctx.explicit ? { from: ctx.pos - typed.length, options: opts, filter: false } : null;
    }
    m = END_BRACKET.exec(before);
    if (m) {                                                  // data['de|
      const typed = m[3];
      const names = [...(sh.children.get(K(segments(m[1]))) || [])].filter((k) => !/^\d+$/.test(k) && starts(k, typed));
      return names.length ? { from: ctx.pos - typed.length, options: names.map((k) => ({ label: k, type: "property" })), filter: false } : null;
    }
    m = END_DOT.exec(before);
    if (m) {                                                  // data.detail.|  (a name not an identifier in bracket form)
      const typed = m[2];
      const from = ctx.pos - typed.length - 1;               // from the dot: a bracket name replaces it
      const kids = [...(sh.children.get(K(segments(m[1]))) || [])];
      const opts: Completion[] = kids.filter((k) => starts(k, typed) || (!typed && /^\d+$/.test(k)))
        .map((k) => ({ label: seg(k), type: "property", detail: sh.values.has(K([...segments(m![1]), k])) ? "value" : "",
          boost: seg(k).startsWith(".") ? 1 : 0 }));         // a dotted name first, a bracketed one after
      for (const f of METHODS) if (starts(f, typed)) opts.push({ label: `.${f}(`, type: "method", detail: "method", boost: -10 });
      opts.sort((a, b) => (b.boost || 0) - (a.boost || 0) || a.label.localeCompare(b.label));   // (filter: false keeps this order)
      return opts.length ? { from, options: opts, filter: false } : null;
    }
    m = END_WORD.exec(before);
    if (m || ctx.explicit) {
      const typed = m ? m[1] : "";
      const opts: Completion[] = [
        ...NAMES.map((x) => ({ label: x, type: "variable", detail: "the event's" })),
        ...FUNCTIONS.map(([f, info]) => ({ label: f, type: "function", detail: "function", info, apply: `${f}(` })),
        ...WORDS.map((w) => ({ label: w, type: "keyword" })),
      ].filter((o) => starts(o.label, typed) && o.label !== typed);
      return opts.length ? { from: ctx.pos - typed.length, options: opts, filter: false } : null;
    }
    return null;
  };
}
