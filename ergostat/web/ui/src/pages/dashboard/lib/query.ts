/* What a dashboard asks the server (/api/query): every panel's queries in one request, an identical query asked once,
   each answer mapped back to its panel (panels.js queryPanels). Pure: no React, no DOM. */

export type Query = Record<string, any> & { id?: string; source: string; label?: string; hidden?: boolean; text?: string };

export interface Panel {
  id: string;
  title: string;
  note?: string;
  form: string;
  size?: "s" | "m" | "l" | "full";
  tall?: boolean;
  queries: Query[];
  display?: Record<string, any>;
  options?: Record<string, any>;
  layout?: { x: number; y: number; w: number; h: number };
}

export interface Dashboard {
  title: string;
  since: string | null;
  panels: Panel[];
  rows?: any[];
  vars?: Record<string, any>;
}

export interface SeriesOut { name: string; values: (number | null)[]; labels?: Record<string, string> }
export interface Result {
  id: string;
  times?: number[];
  series?: SeriesOut[];
  step?: number;
  unit?: string;
  shape?: string;
  error?: string;
  error_kind?: string;
  columns?: string[];
  rows?: unknown[][];
  meta?: any;
  [k: string]: any;
}
export interface Answer { now: number; since: number; until: number; step: number; results: Result[] }

/** The form a query is sent in: base64url of its JSON (as the server's q= reads it). */
export function encodeQuery(obj: unknown): string {
  const bytes = new TextEncoder().encode(JSON.stringify(obj));
  let text = "";
  for (const b of bytes) text += String.fromCharCode(b);
  return btoa(text).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

/** The old forms a stored dashboard may still name, read as the form and options they mean (panels.js normalizeForm). */
export function normalizeForm(p: Panel): { form: string; options: Record<string, any> } {
  const o = { ...(p.options || {}) };
  switch (p.form) {
    case "area": return { form: "line", options: { fill: "area", ...o } };
    case "stacked": return { form: "line", options: { fill: "area", stack: "stacked", ...o } };
    case "step": return { form: "line", options: { style: "step-after", ...o } };
    case "bars": return { form: "bar", options: { stack: "stacked", ...o } };
    case "hbar": return { form: "bar", options: { orientation: "horizontal", ...o } };
    default: return { form: p.form || "line", options: o };
  }
}

const plain = ({ id: _i, label: _l, hidden: _h, ...rest }: Query) => rest;

/** Every panel's shown queries, each identical query once: what to send, and which sent id each panel's query reads. */
export function plan(panels: Panel[]): { queries: Query[]; wanted: { panel: string; id: string; as: string }[] } {
  const asked = new Map<string, Query>();
  const wanted: { panel: string; id: string; as: string }[] = [];
  for (const p of panels) {
    const { form } = normalizeForm(p);
    (p.queries || []).forEach((q, n) => {
      if (q.hidden) return;
      let rest: Query = plain(q) as Query;
      if (form === "candlestick" && (q.source === "items" || q.source === "series")) rest = { ...rest, agg: "ohlc", transform: "none" };
      const shape = JSON.stringify(rest);
      if (!asked.has(shape)) asked.set(shape, { ...rest, id: `q${asked.size}` });
      wanted.push({ panel: p.id, id: q.id ?? String(n), as: asked.get(shape)!.id! });
    });
  }
  return { queries: [...asked.values()], wanted };
}

/** The answer split back into each panel's results, labelled as its queries are. */
export function split(panels: Panel[], answer: Answer | undefined, wanted: { panel: string; id: string; as: string }[]): Map<string, Result[]> {
  const out = new Map<string, Result[]>(panels.map((p) => [p.id, []]));
  if (!answer) return out;
  const byId = new Map((answer.results || []).map((r) => [r.id, r]));
  for (const w of wanted) {
    const r = byId.get(w.as);
    out.get(w.panel)?.push(r ? { ...r, id: w.id } : { id: w.id, error: "the answer left this query out" });
  }
  return out;
}

/** A labelled query's one series goes by its label alone ("completions", not "completions: entries"). */
export function named(p: Panel, results: Result[]): Result[] {
  const label = new Map((p.queries || []).filter((q) => q.label).map((q, n) => [String(q.id ?? n), q.label!]));
  return results.map((r) => (label.has(String(r.id)) && r.series?.length === 1 ? { ...r, series: [{ ...r.series[0], name: label.get(String(r.id))! }] } : r));
}
