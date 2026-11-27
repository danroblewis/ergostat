import { useEffect, useRef, useState } from "react";
import { QueryEditor } from "../../components/query";
import { useApi } from "../../hooks/useApi";
import { apiSend, isAbort } from "../../lib/api";

/* A projection's definition, edited on its own list page (SPEC §5a, *Trying a projection*): its YAML body in the code
   editor, tried on the record ~500 ms after typing stops (POST /api/projections/try; the one in flight cancelled), its
   check errors on their lines, the try's report beside it, and the stream's shape (GET /api/events/shape) for the
   events its match: reads. The draft's id goes to the page, whose panels then draw the draft's items. Nothing is
   written until the page's Save. */

export type TryReport = Record<string, any>;

export const starter = (name: string) => `match: {type: ${name}.*}\nevents:\n`;

export function useTry(name: string, text: string | null, system: string) {
  const [report, setReport] = useState<TryReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const ctl = useRef<AbortController | null>(null);
  useEffect(() => {
    ctl.current?.abort();                         // typing again: the try in flight is of a text gone
    if (text == null) { setReport(null); setError(null); setBusy(false); return; }
    const t = setTimeout(() => {

      const c = new AbortController();
      ctl.current = c;
      setBusy(true);
      apiSend<TryReport>("projections/try", { name, yaml: text, system: system || undefined }, {}, c.signal)
        .then((r) => { setReport(r); setError(null); })
        .catch((e) => { if (!isAbort(e)) setError(String((e as Error).message || e)); })
        .finally(() => { if (ctl.current === c) setBusy(false); });
    }, 500);
    return () => clearTimeout(t);
  }, [name, text, system]);
  useEffect(() => () => ctl.current?.abort(), []);
  return { report, error, busy };
}

const n = (x: number) => x.toLocaleString();
const shapeWords = (s: Record<string, unknown>) =>
  Object.entries(s).map(([k, v]) => (k === "type" ? String(v) : `${k}=${typeof v === "string" ? v : JSON.stringify(v)}`)).join("  ");

function Groups({ label, g }: { label: string; g: any }) {
  if (!g?.count) return null;
  return (
    <details className="try-groups">
      <summary><span className="try-label">{label}</span> <strong>{n(g.count)}</strong></summary>
      <ul>
        {g.groups.map((x: any, i: number) => (
          <li key={i} title={x.samples?.[0]}><span className="try-count">{n(x.count)}</span> <code>{shapeWords(x.shape)}</code></li>
        ))}
        {g.groups_left > 0 && <li className="muted">{g.groups_left} more groups</li>}
      </ul>
    </details>
  );
}

export function Report({ r, error, busy }: { r: TryReport | null; error: string | null; busy: boolean }) {
  if (error) return <p className="note lvl-error" role="alert">{error}</p>;
  if (!r) return <p className="muted">{busy ? "Trying it on the record..." : "Type a definition to try it."}</p>;
  if (!r.ok) {
    return (
      <div className="try-report" aria-live="polite">
        <p className="lvl-error"><strong>Does not check</strong></p>
        <ul className="try-errors">{r.errors.map((e: any, i: number) => <li key={i}>{e.line ? `line ${e.line}: ` : ""}{e.message}</li>)}</ul>
      </div>
    );
  }
  const m = r.matched;
  return (
    <div className="try-report" aria-live="polite" aria-busy={busy}>
      <p className="try-line"><span className="try-label">Matched</span> <strong data-testid="try-matched">{n(m.count)}</strong>
        <span className="muted"> of {n(r.events.read)} events ({m.pct}%)</span></p>
      <p className="try-line muted small">{Object.entries(m.by_handler).map(([h, c]) => `${h} ${n(c as number)}`).join(", ") || "no handler ran"}</p>
      <p className="try-line"><span className="try-label">Items</span> <strong data-testid="try-items">{n(r.items.count)}</strong>
        <span className="muted"> keyed by {r.items.key.join(" / ")}{r.items.one_event ? `, ${r.items.one_event} with one event` : ""}</span></p>
      {r.states && <p className="try-line"><span className="try-label">States</span> {Object.entries(r.states).map(([s, c]) => `${s} ${n(c as number)}`).join(", ") || "none"}</p>}
      <Groups label="No key" g={r.unmatched.no_key} />
      <Groups label="Unchanged" g={r.unchanged} />
      <Groups label="Not read" g={r.unmatched.not_read} />
      {r.refused.count > 0 && (
        <details className="try-groups">
          <summary><span className="try-label">Refused</span> <strong>{n(r.refused.count)}</strong></summary>
          <ul>{r.refused.groups.map((g: any, i: number) => <li key={i}><span className="try-count">{n(g.count)}</span> {g.why}</li>)}</ul>
        </details>
      )}
      {r.fields.length > 0 && (
        <table className="try-fields">
          <thead><tr><th>Field</th><th>Items</th><th>Types</th><th>Values</th></tr></thead>
          <tbody>{r.fields.map((f: any) => (
            <tr key={f.field}><td><code>{f.field}</code></td><td>{f.pct}%</td><td>{Object.keys(f.types).join(", ")}</td>
              <td className="muted">{"min" in f ? `${f.min} to ${f.max}` : (f.top || []).slice(0, 3).map(([v, c]: [unknown, number]) => `${JSON.stringify(v)} ${c}`).join(", ")}</td></tr>
          ))}</tbody>
        </table>
      )}
      {r.duplicates?.says && <p className="try-line small lvl-warn">{r.duplicates.says}</p>}
    </div>
  );
}

/** The stream's shape, for the events the draft reads (or, reading none yet, every event). */
export function StreamShape({ draft }: { draft: string | null }) {
  const [open, setOpen] = useState(false);
  const got = useApi<any>(open ? "events/shape" : null, draft ? { draft } : {}, { every: null, window: false });
  return (
    <details className="try-stream" onToggle={(e) => setOpen((e.target as HTMLDetailsElement).open)}>
      <summary>Stream: the paths in its events</summary>
      {got.error ? <p className="note lvl-error">{got.error.message}</p> : !got.data ? <p className="muted">Reading...</p> : (
        <>
          <p className="muted small">{n(got.data.events)} events: {got.data.of}</p>
          <table className="try-fields">
            <thead><tr><th>Path</th><th>In</th><th>Types</th><th>Examples</th></tr></thead>
            <tbody>{got.data.paths.map((x: any) => (
              <tr key={x.path}><td><code>{x.path}</code></td><td>{x.pct}%</td><td>{Object.keys(x.types).join(", ")}</td>
                <td className="muted">{(x.examples || []).map((v: unknown) => JSON.stringify(v)).join(", ")}</td></tr>
            ))}</tbody>
          </table>
        </>
      )}
    </details>
  );
}

/** The editor beside the report. */
export function DefinitionEditor({ text, onChange, report, error, busy }: {
  text: string; onChange: (t: string) => void; report: TryReport | null; error: string | null; busy: boolean;
}) {
  const problems = report && !report.ok ? report.errors : report ? [] : undefined;
  return (
    <section className="proj-def-edit" aria-label="The projection's definition">
      <div className="proj-def-code">
        <h2 className="small">Definition</h2>
        <QueryEditor source="yaml" value={text} onChange={onChange} label="The projection's definition (YAML)" problems={problems} />
        <p className="muted small">Tried on the record as you type; Save writes it to the model.</p>
      </div>
      <div className="proj-def-side">
        <h2 className="small">Tried on the record{busy ? "..." : ""}</h2>
        <Report r={report} error={error} busy={busy} />
        <StreamShape draft={report?.ok ? report.draft : null} />
      </div>
    </section>
  );
}
