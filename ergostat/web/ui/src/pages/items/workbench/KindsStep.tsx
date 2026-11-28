import { useEffect, useState } from "react";
import type { Draft } from "./draft";
import { n, Samples } from "./common";

/* Step 2, the kinds of event: its `events:` entries (each renamed, its `when:` edited, removed, with what it takes),
   and the events no kind takes yet, by shape (POST /api/events/kinds given the kinds' `when:`s: only shapes that would
   take an event), each accepted as a kind. */

export interface Suggested { name: string; count: number; when: string; shape?: Record<string, unknown>; paths?: string[]; samples?: string[] }

const same = (a: string, b: string) => a.replace(/\s+/g, " ").trim() === b.replace(/\s+/g, " ").trim();

/** A box that writes what it holds when it is left (or Enter), not at every key: a name or a key read whole. */
export function Commit({ value, onCommit, label, className, disabled, placeholder }: {
  value: string; onCommit: (v: string) => void; label: string; className?: string; disabled?: boolean; placeholder?: string;
}) {
  const [v, setV] = useState(value);
  useEffect(() => setV(value), [value]);
  const done = () => { if (v !== value) onCommit(v); };
  return (
    <input className={className} value={v} aria-label={label} disabled={disabled} placeholder={placeholder} spellCheck={false}
      onChange={(e) => setV(e.target.value)} onBlur={done} onKeyDown={(e) => { if (e.key === "Enter") done(); }} />
  );
}

function Suggestion({ k, onAccept, editable }: { k: Suggested; onAccept: () => void; editable: boolean }) {
  return (
    <li className="wb-kind">
      <div className="wb-kind-line">
        <span className="wb-kind-n">{n(k.count)}</span> <strong>{k.name}</strong> <code className="wb-when">{k.when}</code>{" "}
        <button type="button" disabled={!editable} onClick={onAccept}>Accept</button>
      </div>
      <details className="small"><summary className="muted">samples</summary><Samples samples={k.samples} /></details>
    </li>
  );
}

export interface Suggestions { query: string; taken: string[]; count: number; untaken: number; kinds: Suggested[]; kinds_left?: number; read: any }

export function KindsStep({ draft, review, sugg, editable, onAdd, onRename, onWhen, onRemove }: {
  draft: Draft; review: any; sugg: { data: Suggestions | null; error: string | null }; editable: boolean;
  onAdd: (ks: { name: string; when: string }[]) => void; onRename: (from: string, to: string) => void;
  onWhen: (kind: string, when: string) => void; onRemove: (kind: string) => void;
}) {
  const counts: Record<string, number> = Object.fromEntries((review?.kinds || []).map((k: any) => [k.name, k.count]));
  const s = sugg.data;
  const fresh = (s?.kinds || []).filter((x) => !draft.kinds.some((k) => same(k.when, x.when)));
  const left = review?.residual?.remainder?.count ?? s?.untaken;

  return (
    <>
      {draft.kinds.length === 0 ? <p className="muted">None yet: accept the kinds the query's result holds, below (or all of them, in step 1).</p> : (
        <table className="wb-table" aria-label="Its kinds of event">
          <thead><tr><th>Name</th><th>when: <span className="muted">(the first that holds takes an event)</span></th><th>Takes</th><th /></tr></thead>
          <tbody>{draft.kinds.map((k) => (
            <tr key={k.name}>
              <td><Commit value={k.name} label={`The name of ${k.name}`} disabled={!editable}
                onCommit={(v) => v.trim() && onRename(k.name, v.trim())} /></td>
              <td className="wb-grow"><Commit className="mono" value={k.when} label={`The when: of ${k.name}`} disabled={!editable}
                onCommit={(v) => onWhen(k.name, v)} /></td>
              <td className={review && counts[k.name] === 0 ? "lvl-warn" : ""} title={review && counts[k.name] === 0 ? "it takes no event of the query's result" : undefined}>
                {review ? n(counts[k.name] ?? 0) : ""}</td>
              <td><button type="button" className="ghost" disabled={!editable} aria-label={`Remove ${k.name}`} onClick={() => onRemove(k.name)}>×</button></td>
            </tr>
          ))}</tbody>
        </table>
      )}

      {left === 0 && draft.kinds.length ? <p className="muted small" data-testid="all-taken">✓ Every event of the query's result is taken by a kind.</p> : (
        <h3 className="small">Not taken yet <strong data-testid="remainder-count">{left == null ? "–" : n(left)}</strong>
          {" "}<span className="muted">events no kind takes, by shape</span></h3>
      )}
      {!draft.query.trim() ? <p className="muted">Type a query first (step 1).</p> : sugg.error ? <p className="note lvl-error">{sugg.error}</p>
        : !s ? (left === 0 ? null : <p className="muted">Reading…</p>)
        : fresh.length === 0 ? null : (
          <>
            <ul className="wb-kinds" aria-label="The remainder, by shape">
              {fresh.map((k) => <Suggestion key={k.when} k={k} editable={editable} onAccept={() => onAdd([k])} />)}
            </ul>
            {s.kinds_left ? <p className="muted small">{s.kinds_left} more shapes, once these are taken.</p> : null}
          </>
        )}
    </>
  );
}
