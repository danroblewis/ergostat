import { useEffect, useMemo, useState } from "react";
import type { JsonPath, PathMark } from "../../../components/JsonValues";
import { useSend } from "../../../hooks/useSend";
import { fieldName, guessType, isPath, ofKind, pathExpr, reads, solvedKey, TYPES, underAny, type Draft, type KindDef } from "./draft";
import { EventValues, short, type QEvent } from "./common";
import { Commit } from "./KindsStep";

/* Step 4, the mapping: per kind of event, its key as solved from what it maps to the key's fields (✓ each part's
   expression, ✗ a part it does not tell, a click away from its mapping), one of its events shown as it reads (each
   value read into a field tagged with the field, a value nothing reads standing out, an ignored path hidden) beside
   the record that event makes; a value clicked is put into a field (a key field among them), a new field, or ignored
   (in every kind's events); what another kind already maps the same way is offered at once. And the event's own time
   (time:). */

export interface MappingEdits {
  setTop: (k: "time", v: string) => void;
  addField: (name: string) => void;
  setField: (name: string, part: "type" | "values" | "fold" | "description", v: string) => void;
  renameField: (from: string, to: string) => void;
  removeField: (name: string) => void;
  setKind: (kind: string, entry: string, v: string) => void;
  setKinds: (kind: string, pairs: [string, string][]) => void;
  createAndMap: (kind: string, field: string, type: string, expr: string) => void;
  ignore: (path: string) => void;
  setKey: (names: string[]) => void;
}

/** Every path in an event (its parts' and all within them), and its values' paths alone. */
function pathsOf(e: QEvent): { all: JsonPath[]; leaves: JsonPath[] } {
  const all: JsonPath[] = [], leaves: JsonPath[] = [];
  const walk = (v: unknown, p: JsonPath) => {
    all.push(p);
    if (v !== null && typeof v === "object") {
      const es = Array.isArray(v) ? v.map((x, i) => [i, x] as [number, unknown]) : Object.entries(v as Record<string, unknown>);
      if (es.length) { for (const [k, x] of es) walk(x, [...p, k]); return; }
    }
    leaves.push(p);
  };
  for (const [k, v] of [["type", e.type], ["key", e.item], ["source", e.source], ["data", e.data]] as [string, unknown][]) if (v != null) walk(v, [k]);
  return { all, leaves };
}

/** The record one event makes by the draft (POST /api/projections/fold). */
function Made({ e, kind, fold }: { e: QEvent; kind: string; fold: (evs: QEvent[]) => Record<string, unknown> | null }) {
  const got = useSend<any>("projections/fold", fold([e]), 500);
  const r = got.data;
  let body;
  if (got.error) body = <p className="note lvl-error small">{got.error}</p>;
  else if (!r) body = <p className="muted small">Folding…</p>;
  else if (!r.ok) body = <p className="muted small">The draft does not check yet.</p>;
  else if (r.took?.[e.id] && r.took[e.id] !== kind) body = <p className="muted small">{r.took[e.id]} takes this event first.</p>;
  else if (!r.objects.length) body = <p className="muted small">Keyed to nothing: a part of its key (above) is not told, or reads no value here.</p>;
  else body = r.objects.slice(0, 3).map((o: any) => (
    <div key={o.key}>
      <p className="small"><code>{o.key}</code></p>
      <ul className="jv">
        {o.state != null && <li><span className="jv-key">state</span> <span className="jv-val">{JSON.stringify(o.state)}</span></li>}
        {Object.entries(o.fields || {}).map(([f, v]) => <li key={f}><span className="jv-key">{f}</span> <span className="jv-val">{short(v, 80)}</span></li>)}
        {o.state == null && !Object.keys(o.fields || {}).length && <li className="muted">no field yet</li>}
      </ul>
      {o.refused?.length > 0 && <p className="lvl-error small">refused: {o.refused[0]}</p>}
    </div>
  ));
  return <div className="wb-record" aria-label={`The record ${kind}'s event makes`}><h4 className="small muted">The record it makes</h4>{body}</div>;
}

/** The value picked: into a field, a part of the key, a new field made there and then, or ignored everywhere. */
function Picked({ k, draft, ed, editable, path, value, onDone }: {
  k: KindDef; draft: Draft; ed: MappingEdits; editable: boolean; path: JsonPath; value: unknown; onDone: () => void;
}) {
  const expr = pathExpr(path);
  const last = [...path].reverse().find((x) => typeof x === "string") as string | undefined;
  const [name, setName] = useState(() => fieldName(last));
  const [type, setType] = useState(() => guessType(value));
  const taken = draft.fields.some((f) => f.name === name.trim());
  const ok = /^[A-Za-z_][\w-]*$/.test(name.trim()) && !taken;
  const done = (f: () => void) => () => { f(); onDone(); };
  return (
    <div className="wb-picked" role="group" aria-label="The value picked">
      <p><code>{expr}</code> = <code>{short(value)}</code>{" "}
        <button type="button" className="ghost" aria-label="Forget the value picked" onClick={onDone}>×</button></p>
      <p>Into{" "}
        {draft.fields.map((f) => (
          <button key={f.name} type="button" disabled={!editable} onClick={done(() => ed.setKind(k.name, f.name, expr))}>{f.name}</button>
        ))}{" "}
        <button type="button" disabled={!editable} onClick={done(() => ed.ignore(expr))}>ignore this path</button>
      </p>
      <p>New field{" "}
        <input value={name} onChange={(e) => setName(e.target.value)} aria-label="The new field's name" className="mono" spellCheck={false} />{" "}
        <select value={type} onChange={(e) => setType(e.target.value)} aria-label="The new field's type">
          {TYPES.map((t) => <option key={t}>{t}</option>)}
        </select>{" "}
        <button type="button" disabled={!editable || !ok} onClick={done(() => ed.createAndMap(k.name, name.trim(), type, expr))}>Create and map</button>
        {taken && <span className="muted small"> (a field already)</span>}
      </p>
    </div>
  );
}

function KindMapping({ k, draft, ed, editable, fold }: {
  k: KindDef; draft: Draft; ed: MappingEdits; editable: boolean; fold: (evs: QEvent[]) => Record<string, unknown> | null;
}) {
  const q = ofKind(draft.query, k.when);
  const body = useMemo(() => (q.trim() ? { query: q, limit: 5 } : null), [q]);
  const got = useSend<{ events: QEvent[] }>("events/query", body, 600);
  const evs = got.data?.events || [];
  const [at, setAt] = useState(0);
  const e = evs.length ? evs[Math.min(at, evs.length - 1)] : null;
  const [picked, setPicked] = useState<{ path: JsonPath; value: unknown } | null>(null);
  const [showIgnored, setShowIgnored] = useState(false);
  const [adding, setAdding] = useState<string[]>([]);
  const [unticked, setUnticked] = useState<Set<string>>(new Set());
  const told: Record<string, string> = Object.fromEntries(k.values);
  const solved = solvedKey(draft.key, k);
  const [focus, setFocus] = useState<string | null>(null);
  useEffect(() => {                                   // a ✗ clicked: that field's mapping for this kind, ready to type
    if (!focus) return;
    const el = document.querySelector<HTMLInputElement>(`input[aria-label="${CSS.escape(`${k.name}: ${focus}`)}"]`);
    if (el) { el.focus(); el.scrollIntoView({ block: "nearest" }); setFocus(null); }
  });

  const mark = (p: JsonPath): PathMark => {
    const x = pathExpr(p);
    if (underAny(x, draft.ignore)) return { ignored: true };
    for (const [f, ex] of k.values) if (reads(ex, x)) return { to: f };
    for (const kp of solved) if (kp.spread && kp.expr && reads(kp.expr, x)) return { to: kp.field };
    if (!draft.key.length && x === "key") return { to: "key" };
    if (draft.time && reads(draft.time, x)) return { to: "time" };
    return {};
  };
  const paths = e ? pathsOf(e) : { all: [], leaves: [] };
  const nIgnored = paths.leaves.filter((p) => underAny(pathExpr(p), draft.ignore)).length;

  // what another kind maps by a plain path that this kind's events have too, and this kind does not tell yet
  const same = useMemo(() => {
    const present = new Set(evs.flatMap((x) => pathsOf(x).all.map(pathExpr)));
    const out: [string, string][] = [];
    for (const o of draft.kinds) {
      if (o.name === k.name) continue;
      for (const [f, ex] of o.values) {
        if (f in told || !draft.fields.some((x) => x.name === f) || out.some(([g]) => g === f)) continue;
        if (isPath(ex) && present.has(ex.trim())) out.push([f, ex.trim()]);
      }
    }
    return out;
  }, [evs, draft, k.name]);   // eslint-disable-line react-hooks/exhaustive-deps
  const chosen = same.filter(([f]) => !unticked.has(f));

  const rows = [...k.values.map(([f]) => f), ...adding.filter((f) => !(f in told))];
  const untold = draft.fields.map((f) => f.name).filter((f) => !rows.includes(f));

  return (
    <details className="wb-map" open>
      <summary><strong>{k.name}</strong> <code className="muted small">{short(k.when, 80)}</code></summary>
      {same.length > 0 && (
        <p className="wb-same" data-testid={`same-${k.name}`}>
          Map these the same way:{" "}
          {same.map(([f, ex]) => (
            <label key={f} className="wb-same-one">
              <input type="checkbox" checked={!unticked.has(f)} aria-label={`${ex} → ${f}`}
                onChange={() => setUnticked((s) => { const x = new Set(s); if (x.has(f)) x.delete(f); else x.add(f); return x; })} />
              <code>{ex}</code> → {f}
            </label>
          ))}{" "}
          <button type="button" disabled={!editable || !chosen.length} onClick={() => ed.setKinds(k.name, chosen)}>Apply</button>
        </p>
      )}
      <table className="wb-table" aria-label={`What ${k.name} tells`}>
        <tbody>
          <tr>
            <th scope="row">its key</th>
            <td className="wb-grow" data-testid={`key-${k.name}`}>
              {!solved.length ? <span className="muted small">the events&apos; own item (<code>key</code>)</span> : (
                <span className="wb-solved" aria-label={`The key of ${k.name}`}>
                  {solved.map((kp, i) => (
                    <span key={kp.field} className={kp.expr ? "wb-key-ok" : "wb-key-no"}>
                      {i > 0 && <span className="muted"> · </span>}
                      {kp.field}{" "}
                      {kp.expr ? <><span aria-label="told">✓</span> <code>{short(kp.expr, 60)}</code>{kp.spread && <span className="muted small"> (by the spread)</span>}</>
                        : <button type="button" className="ghost lvl-error" disabled={!editable} aria-label={`Map ${kp.field} for ${k.name}`}
                          onClick={() => { setAdding((x) => (x.includes(kp.field) ? x : [...x, kp.field])); setFocus(kp.field); }}>✗ not told</button>}
                    </span>
                  ))}
                </span>
              )}
            </td>
          </tr>
          {rows.map((f) => (
            <tr key={f}>
              <th scope="row">{f}</th>
              <td className="wb-grow"><Commit className="mono" value={told[f] ?? ""} label={`${k.name}: ${f}`} disabled={!editable}
                placeholder="an expression of the event" onCommit={(v) => ed.setKind(k.name, f, v)} /></td>
            </tr>
          ))}
          {untold.length > 0 && (
            <tr>
              <th scope="row" />
              <td>
                <select value="" aria-label={`${k.name}: tell another field`} disabled={!editable}
                  onChange={(ev) => { const f = ev.target.value; if (f) setAdding((a) => [...a, f]); }}>
                  <option value="">tell another field…</option>
                  {untold.map((f) => <option key={f} value={f}>{f}</option>)}
                </select>
              </td>
            </tr>
          )}
        </tbody>
      </table>
      {picked && (
        <Picked key={JSON.stringify(picked.path)} k={k} draft={draft} ed={ed} editable={editable} path={picked.path} value={picked.value}
          onDone={() => setPicked(null)} />
      )}
      {got.error ? <p className="note lvl-error">{got.error}</p> : !e ? <p className="muted small">{got.data ? "None of its events in the query's result." : "Reading…"}</p> : (
        <>
          <p className="muted small wb-sample-nav">
            An event of it{evs.length > 1 && <>, {at + 1} of {evs.length}{" "}
              <button type="button" className="ghost" aria-label="The previous event" disabled={at === 0} onClick={() => setAt(at - 1)}>‹</button>
              <button type="button" className="ghost" aria-label="The next event" disabled={at >= evs.length - 1} onClick={() => setAt(at + 1)}>›</button></>}
            : click a value to put it somewhere.
            {nIgnored > 0 && <>{" "}<button type="button" className="ghost small" aria-pressed={showIgnored}
              onClick={() => setShowIgnored(!showIgnored)}>{showIgnored ? "hide" : "show"} ignored ({nIgnored})</button></>}
          </p>
          <div className="wb-pair">
            <div className="wb-sample" aria-label={`An event of ${k.name}`}>
              <EventValues e={e} mark={mark} showIgnored={showIgnored} picked={picked ? JSON.stringify(picked.path) : undefined}
                onPick={(path, value) => setPicked({ path, value })} />
            </div>
            <Made e={e} kind={k.name} fold={fold} />
          </div>
        </>
      )}
    </details>
  );
}

export function MappingStep({ draft, ed, editable, fold }: {
  draft: Draft; ed: MappingEdits; editable: boolean; fold: (evs: QEvent[]) => Record<string, unknown> | null;
}) {
  return (
    <>
      <p className="wb-row">
        <label>The event's own time <Commit className="mono" value={draft.time} label="The event's own time" disabled={!editable}
          placeholder="the recorded time" onCommit={(v) => ed.setTop("time", v)} /></label>
      </p>
      {draft.kinds.length === 0 ? <p className="muted">No kinds of event yet (step 3).</p>
        : draft.kinds.map((k) => <KindMapping key={k.name} k={k} draft={draft} ed={ed} editable={editable} fold={fold} />)}
    </>
  );
}
