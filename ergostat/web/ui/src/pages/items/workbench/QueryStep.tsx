import { useMemo, useRef, useState } from "react";
import type { JsonPath } from "../../../components/JsonValues";
import { QueryEditor } from "../../../components/query";
import { Select } from "../../../components/ui";
import { useSend } from "../../../hooks/useSend";
import { literal, narrowed, pathExpr } from "./draft";
import { EventList, n, short, type QEvent } from "./common";

/* Step 1, the query (POST /api/events/query): which events the projection reads, over the whole record; each change
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

export function QueryStep({ query, onQuery, since, onSince, editable }: {
  query: string; onQuery: (q: string) => void; since: string; onSince: (s: string) => void; editable: boolean;
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

  return (
    <>
      <div className="wb-row">
        <div className="wb-grow">
          <QueryEditor source="expression" value={query} onChange={(q) => editable && onQuery(q)} label="The query"
            placeholder="data.source == 'aws.ec2' and not data.detail.eventName.startswith('Describe')" />
        </div>
        <label className="wb-since">Over <Select value={since} onChange={(e) => onSince(e.target.value)} options={SPANS} aria-label="Over" /></label>
      </div>
      {!query.trim() ? <p className="muted">Type a query: an expression of the event (<code>type</code>, <code>key</code>, <code>source</code>, <code>data.a.b</code>) that holds for the events it reads.</p>
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
          <p className="muted small">The newest {n(a.shown)}{a.shown < a.total ? ` of ${n(a.total)}` : ""}: open one and click a value to narrow the query by it.</p>
          <EventList events={a.events} picked={picked ? JSON.stringify(picked.path) : undefined}
            onPick={(path, value) => setPicked({ path, value })} />
        </>
      )}
    </>
  );
}
