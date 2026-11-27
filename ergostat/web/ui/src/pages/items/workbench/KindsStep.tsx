import { useEffect, useMemo, useState } from "react";
import { useSend } from "../../../hooks/useSend";
import type { Draft } from "./draft";
import { n, Samples } from "./common";
import { howRead } from "./QueryStep";

/* Step 2, the kinds of event (POST /api/events/kinds): the query's result by shape, each a suggested kind with its
   count, its `when:` and samples; accepted, it is an `events:` entry the user renames, edits or removes. The remainder
   (events no kind takes, from the review) is always shown, by shape, each shape acceptable as a kind too. */

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

export function KindsStep({ draft, since, review, editable, onAdd, onRename, onWhen, onRemove }: {
  draft: Draft; since: string; review: any; editable: boolean;
  onAdd: (ks: { name: string; when: string }[]) => void; onRename: (from: string, to: string) => void;
  onWhen: (kind: string, when: string) => void; onRemove: (kind: string) => void;
}) {
  const body = useMemo(() => (draft.query.trim() ? { query: draft.query, since: since || undefined } : null), [draft.query, since]);
  const got = useSend<{ count: number; kinds: Suggested[]; kinds_left?: number; read: any }>("events/kinds", body, 600);
  const counts: Record<string, number> = Object.fromEntries((review?.kinds || []).map((k: any) => [k.name, k.count]));
  const fresh = (got.data?.kinds || []).filter((s) => !draft.kinds.some((k) => same(k.when, s.when)));
  const rem = review?.residual?.remainder;

  return (
    <>
      <h3 className="small">Its kinds of event <span className="muted">(events:, in order: the first whose when: holds takes an event)</span></h3>
      {draft.kinds.length === 0 ? <p className="muted">None yet: accept a suggestion below, or a shape of the remainder.</p> : (
        <table className="wb-table" aria-label="Its kinds of event">
          <thead><tr><th>Name</th><th>when:</th><th>Takes</th><th /></tr></thead>
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

      <h3 className="small">The remainder <span className="muted">(events no kind takes)</span>{" "}
        <strong data-testid="remainder-count">{rem ? n(rem.count) : "–"}</strong></h3>
      {rem?.count > 0 && (
        <ul className="wb-kinds" aria-label="The remainder, by shape">
          {rem.kinds.map((k: Suggested) => <Suggestion key={k.when} k={k} editable={editable} onAccept={() => onAdd([k])} />)}
        </ul>
      )}
      {rem && rem.count === 0 && <p className="muted small">Every event of the query's result is taken by a kind.</p>}

      <h3 className="small">Suggested from the query's result{" "}
        {fresh.length > 1 && <button type="button" disabled={!editable} onClick={() => onAdd(fresh)}>Accept all {fresh.length}</button>}</h3>
      {!body ? <p className="muted">Type a query first.</p> : got.error ? <p className="note lvl-error">{got.error}</p>
        : !got.data ? <p className="muted">Reading…</p> : (
          <>
            <p className="muted small">{n(got.data.count)} events; {howRead(got.data.read || {})}.</p>
            {fresh.length === 0 ? <p className="muted small">Each shape is a kind of event already.</p> : (
              <ul className="wb-kinds" aria-label="Suggested kinds of event">
                {fresh.map((k) => <Suggestion key={k.when} k={k} editable={editable} onAccept={() => onAdd([k])} />)}
              </ul>
            )}
            {got.data.kinds_left ? <p className="muted small">{got.data.kinds_left} more shapes not shown.</p> : null}
          </>
        )}
    </>
  );
}
