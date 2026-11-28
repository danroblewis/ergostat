import { useMemo, useRef, useState } from "react";
import type { JsonPath } from "../../../components/JsonValues";
import { QueryEditor } from "../../../components/query";
import { Select } from "../../../components/ui";
import { useSend } from "../../../hooks/useSend";
import { literal, narrowed, pathExpr } from "./draft";
import { EventList, n, short, type QEvent } from "./common";
import type { Suggested, Suggestions } from "./KindsStep";

/* Step 2, the query (POST /api/events/query): which events the projection reads, over the whole record; each change
   says what it added and dropped, and how it was answered (from the index, exact or evaluated; a scan; a sample). */

export const SPANS = [
  { value: "", label: "the whole record" }, { value: "1h", label: "the last hour" }, { value: "1d", label: "the last day" },
  { value: "7d", label: "the last 7 days" }, { value: "30d", label: "the last 30 days" },
];

export interface QueryAnswer {
  query: string; total: number; events: QEvent[]; shown: number; indexed: boolean; exact: boolean; paths: string[];
  scanned: boolean; candidates?: number; read: number; capped?: boolean; sampled?: boolean; sample_of?: number;
  estimated?: boolean; record: number; compare?: { query: string; total: number; added: number; dropped: number; estimated?: boolean };
  took_ms: number;
}

const HAS = /\bhas\(\s*('(?:[^'\\]|\\.)*'|"(?:[^"\\]|\\.)*")\s*\)/;   // the query's first has('text') of the whole event

/** The text the query's has('…') term searches for ("" when it has none). */
export function searchedText(query: string): string {
  const m = HAS.exec(query);
  if (!m) return "";
  return m[1].slice(1, -1).replace(/\\(.)/g, "$1");
}

/** The query with its has('…') term searching for `text` instead: put first when it had none (the rest narrowing it),
    taken out (and the `and` with it) when `text` is empty. */
export function withSearch(query: string, text: string): string {
  const q = query.trim();
  const term = text ? `has(${literal(text)})` : "";
  if (HAS.test(q)) {
    if (term) return q.replace(HAS, () => term);
    for (const re of [new RegExp(`^${HAS.source}\\s+and\\s+`), new RegExp(`\\s+and\\s+${HAS.source}`), HAS]) {
      if (re.test(q)) return q.replace(re, "").trim();
    }
  }
  if (!term) return q;
  if (!q) return term;
  return /\bor\b/.test(q) ? `${term} and (${q})` : `${term} and ${q}`;
}

/** How the answer was had, said plainly. */
export function howRead(a: { indexed?: boolean; exact?: boolean; scanned?: boolean; candidates?: number; read?: number;
  capped?: boolean; sampled?: boolean; sample_of?: number; record?: number; source?: string }): string {
  if (a.source && a.source !== "record") return `read from ${a.source}`;
  const cap = a.capped ? " (cut at the most it reads: there may be more)" : "";
  if (a.sampled) return `estimated from a sample of ${n(a.sample_of ?? a.read)} events${cap}`;
  if (a.scanned) return `scanned the newest ${n(a.read)} events: no part of the query is indexed${cap}`;
  if (a.exact) return "answered from the index, exactly (no event read)";
  if (a.indexed) return `${n(a.candidates)} candidates from the index, each evaluated${cap}`;
  return "";
}

/** What the kinds of event the result holds would take, and Accept all; once all is taken, that said. */
function Cover({ s, kinds, editable, onAccept }: { s: Suggestions; kinds: number; editable: boolean; onAccept: (ks: Suggested[]) => void }) {
  const of = kinds ? s.untaken : s.count;
  const took = s.kinds.reduce((a, k) => a + k.count, 0);
  if (!s.kinds.length) {
    return kinds && !s.untaken ? <p className="wb-cover" data-testid="accept-line">✓ All events taken by {kinds} kind{kinds === 1 ? "" : "s"} of event.</p> : null;
  }
  const pct = of ? Math.round((1000 * took) / of) / 10 : 0;
  return (
    <p className="wb-cover" data-testid="accept-line">
      {s.kinds.length}{kinds ? " more" : ""} kind{s.kinds.length === 1 ? "" : "s"} of event cover {pct}% of {kinds ? "the events not taken yet" : "these events"}
      {" · "}<button type="button" disabled={!editable} onClick={() => onAccept(s.kinds)}>Accept all</button>
    </p>
  );
}

export function QueryStep({ query, onQuery, since, onSince, editable, sugg, kinds, onAccept }: {
  query: string; onQuery: (q: string) => void; since: string; onSince: (s: string) => void; editable: boolean;
  sugg: Suggestions | null; kinds: number; onAccept: (ks: Suggested[]) => void;
}) {
  const shownQ = useRef<string | null>(null);     // the query whose answer is shown: what the next one is compared with
  const body = useMemo(() => (query.trim() ? {
    query, since: since || undefined, limit: 20,
    compare: shownQ.current && shownQ.current !== query ? shownQ.current : undefined,
  } : null), [query, since]);
  const got = useSend<QueryAnswer>("events/query", body, 400);
  const a = got.data;
  if (a && shownQ.current !== a.query) shownQ.current = a.query;
  const [picked, setPicked] = useState<{ path: JsonPath; value: unknown } | null>(null);
  const expr = picked ? pathExpr(picked.path) : "";
  const searched = searchedText(query);

  return (
    <>
      <label className="wb-search">Find events containing{" "}
        <input type="search" value={searched} disabled={!editable} spellCheck={false} data-testid="query-search"
          placeholder="an id, a name, any text (has('…') in the query)" aria-label="Find events containing"
          onChange={(e) => onQuery(withSearch(query, e.target.value))} />
      </label>
      <div className="wb-row">
        <div className="wb-grow">
          <QueryEditor source="expression" value={query} onChange={(q) => editable && onQuery(q)} label="The query" events={a?.events}
            placeholder="data.source == 'aws.ec2' and not data.detail.eventName.startswith('Describe')" />
        </div>
        <label className="wb-since">Over <Select value={since} onChange={(e) => onSince(e.target.value)} options={SPANS} aria-label="Over" /></label>
      </div>
      {!query.trim() ? <p className="muted">Find the events containing an id above, or type a query: an expression of the event (<code>type</code>, <code>key</code>, <code>source</code>, <code>data.a.b</code>, <code>has('text')</code>) that holds for the events it reads; then narrow it.</p>
        : got.error ? <p className="note lvl-error" role="alert">{got.error}</p> : null}
      {a && query.trim() && (
        <>
          <p className="wb-count" aria-live="polite" aria-busy={got.busy}>
            <strong data-testid="query-total">{n(a.total)}</strong> event{a.total === 1 ? "" : "s"}{a.estimated ? " (estimated)" : ""}
            <span className="muted"> of {n(a.record)} on the record</span>
            {a.compare && (
              <span className="wb-compare" data-testid="query-compare" title={`compared with ${a.compare.query}`}>
                {" "}<span className="wb-added">+{n(a.compare.added)}</span>, <span className="wb-dropped">−{n(a.compare.dropped)}</span>
                <span className="muted"> since <code>{short(a.compare.query, 50)}</code></span>
              </span>
            )}
          </p>
          {sugg && <Cover s={sugg} kinds={kinds} editable={editable} onAccept={onAccept} />}
          <p className="muted small" data-testid="query-how">{howRead(a)}{a.paths?.length ? `; indexed paths read: ${a.paths.join(", ")}` : ""} · {a.took_ms} ms</p>
          {picked && (
            <p className="wb-picked">
              <code>{expr}</code> = <code>{short(picked.value)}</code>{" "}
              <button type="button" disabled={!editable} onClick={() => { onQuery(narrowed(query, `${expr} == ${literal(picked.value)}`)); setPicked(null); }}>
                and {expr} == {short(literal(picked.value), 30)}</button>{" "}
              <button type="button" disabled={!editable} onClick={() => { onQuery(narrowed(query, `${expr} != ${literal(picked.value)}`)); setPicked(null); }}>
                and {expr} != {short(literal(picked.value), 30)}</button>{" "}
              <button type="button" className="ghost" onClick={() => navigator.clipboard?.writeText(expr)}>Copy the path</button>{" "}
              <button type="button" className="ghost" aria-label="Forget the value picked" onClick={() => setPicked(null)}>×</button>
            </p>
          )}
          <details className="wb-newest">
            <summary className="muted small">The newest {n(a.shown)}{a.shown < a.total ? ` of ${n(a.total)}` : ""}: open one and click a value to narrow the query by it</summary>
            <EventList events={a.events} picked={picked ? JSON.stringify(picked.path) : undefined}
              onPick={(path, value) => setPicked({ path, value })} />
          </details>
        </>
      )}
    </>
  );
}
