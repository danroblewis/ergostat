import { useMemo, useState } from "react";
import type { JsonPath } from "../../../components/JsonValues";
import { useSend } from "../../../hooks/useSend";
import { FOLDS, ofKind, pathExpr, TYPES, type Draft, type KindDef } from "./draft";
import { EventList, short, type QEvent } from "./common";
import { Commit } from "./KindsStep";

/* Step 3, the mapping: the fields declared at the top (fields:, each its type, values, fold and description), the
   projection's key (and time:), and, per kind of event, its key (the projection's or its own) and the expression for
   each field it tells. A value clicked in one of that kind's sample events writes its path where it is put. */

export interface MappingEdits {
  setTop: (k: "key" | "time", v: string) => void;
  addField: (name: string) => void;
  setField: (name: string, part: "type" | "values" | "fold" | "description", v: string) => void;
  renameField: (from: string, to: string) => void;
  removeField: (name: string) => void;
  setKind: (kind: string, entry: string, v: string) => void;
  setKeyParts: (parts: string[]) => void;
  setKindKeyParts: (kind: string, parts: string[]) => void;
}

/** A key as its parts, one expression a row (a composite key: account, region, id), with a row added or taken out.
 *  Each row is an expression as written: no brackets or quoting. */
function KeyParts({ parts, label, editable, onChange }: {
  parts: string[]; label: string; editable: boolean; onChange: (parts: string[]) => void;
}) {
  const [adding, setAdding] = useState("");
  const add = () => { const v = adding.trim(); if (v) { onChange([...parts, v]); setAdding(""); } };
  return (
    <ol className="wb-keyparts" aria-label={label}>
      {parts.map((p, i) => (
        <li key={`${i}:${p}`}>
          <Commit className="mono" value={p} label={`${label}, part ${i + 1}`} disabled={!editable}
            onCommit={(v) => onChange(parts.map((x, j) => (j === i ? v : x)).filter((x) => x.trim()))} />
          {parts.length > 1 && <button type="button" className="ghost" disabled={!editable} aria-label={`Take out part ${i + 1}`}
            onClick={() => onChange(parts.filter((_, j) => j !== i))}>×</button>}
        </li>
      ))}
      <li>
        <input className="mono" value={adding} onChange={(e) => setAdding(e.target.value)} disabled={!editable}
          placeholder={parts.length ? "another part (a composite key)" : "an expression: key, data.id, ..."}
          aria-label={`${label}, a new part`} onKeyDown={(e) => { if (e.key === "Enter") add(); }} />{" "}
        <button type="button" disabled={!editable || !adding.trim()} onClick={add}>Add</button>
      </li>
    </ol>
  );
}

function Fields({ draft, ed, editable }: { draft: Draft; ed: MappingEdits; editable: boolean }) {
  const [name, setName] = useState("");
  const add = () => { const v = name.trim(); if (/^[A-Za-z_][\w-]*$/.test(v)) { ed.addField(v); setName(""); } };
  return (
    <table className="wb-table" aria-label="Its fields">
      <thead><tr><th>Field</th><th>type</th><th>values</th><th>fold</th><th>description</th><th /></tr></thead>
      <tbody>
        {draft.fields.map((f) => (
          <tr key={f.name}>
            <td><Commit value={f.name} label={`The name of ${f.name}`} disabled={!editable} onCommit={(v) => v.trim() && ed.renameField(f.name, v.trim())} /></td>
            <td><Commit value={f.type} label={`The type of ${f.name}`} disabled={!editable} placeholder="any"
              onCommit={(v) => ed.setField(f.name, "type", v.trim())} /></td>
            <td><Commit className="mono" value={f.values} label={`The values of ${f.name}`} disabled={!editable} placeholder="any"
              onCommit={(v) => ed.setField(f.name, "values", v)} /></td>
            <td>
              <select value={f.fold || "replace"} aria-label={`The fold of ${f.name}`} disabled={!editable}
                onChange={(e) => ed.setField(f.name, "fold", e.target.value)}>
                {(FOLDS.includes(f.fold) || !f.fold ? FOLDS : [f.fold, ...FOLDS]).map((x) => <option key={x}>{x}</option>)}
              </select>
            </td>
            <td><Commit value={f.description} label={`The description of ${f.name}`} disabled={!editable}
              onCommit={(v) => ed.setField(f.name, "description", v)} /></td>
            <td><button type="button" className="ghost" disabled={!editable} aria-label={`Remove ${f.name}`} onClick={() => ed.removeField(f.name)}>×</button></td>
          </tr>
        ))}
        <tr>
          <td colSpan={6}>
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="a field's name" aria-label="A new field's name"
              disabled={!editable} onKeyDown={(e) => { if (e.key === "Enter") add(); }} />{" "}
            <button type="button" disabled={!editable || !name.trim()} onClick={add}>Add a field</button>
          </td>
        </tr>
      </tbody>
      <tfoot><tr><td colSpan={6} className="muted small">type: {TYPES.join(", ")}; values: the only values it may hold (the field named <code>state</code> is the lifecycle).</td></tr></tfoot>
    </table>
  );
}

function KindMapping({ k, draft, ed, editable }: { k: KindDef; draft: Draft; ed: MappingEdits; editable: boolean }) {
  const q = ofKind(draft.query, k.when);
  const body = useMemo(() => (q.trim() ? { query: q, limit: 2 } : null), [q]);
  const got = useSend<{ events: QEvent[] }>("events/query", body, 600);
  const [picked, setPicked] = useState<JsonPath | null>(null);
  const [ownKey, setOwnKey] = useState(false);
  const expr = picked ? pathExpr(picked) : "";
  const told: Record<string, string> = Object.fromEntries(k.values);
  const extra = k.values.filter(([f]) => !draft.fields.some((x) => x.name === f));
  const put = (entry: string) => { ed.setKind(k.name, entry, expr); setPicked(null); };
  const putKey = () => { ed.setKindKeyParts(k.name, [...(k.keyParts.length ? k.keyParts : []), expr]); setOwnKey(true); setPicked(null); };
  return (
    <details className="wb-map" open>
      <summary><strong>{k.name}</strong> <code className="muted small">{short(k.when, 80)}</code></summary>
      <table className="wb-table" aria-label={`What ${k.name} tells`}>
        <tbody>
          <tr>
            <th scope="row">its key</th>
            <td className="wb-grow">
              {k.keyParts.length || ownKey ? (
                <>
                  <KeyParts parts={k.keyParts} label={`The key of ${k.name}`} editable={editable}
                    onChange={(ps) => { ed.setKindKeyParts(k.name, ps); if (!ps.length) setOwnKey(false); }} />
                  <button type="button" className="ghost small" disabled={!editable}
                    onClick={() => { ed.setKindKeyParts(k.name, []); setOwnKey(false); }}>Use the projection's key</button>
                </>
              ) : (
                <span className="muted small">the projection's ({draft.keyParts.join(" / ") || "key"}){" "}
                  <button type="button" className="ghost small" disabled={!editable}
                    onClick={() => { setOwnKey(true); ed.setKindKeyParts(k.name, draft.keyParts.length ? draft.keyParts : ["key"]); }}>
                    Its ids are elsewhere: give it its own</button></span>
              )}
            </td>
          </tr>
          {[...draft.fields.map((f) => f.name), ...extra.map(([f]) => f)].map((f) => (
            <tr key={f}>
              <th scope="row">{f}</th>
              <td className="wb-grow"><Commit className="mono" value={told[f] ?? ""} label={`${k.name}: ${f}`} disabled={!editable}
                placeholder="not told" onCommit={(v) => ed.setKind(k.name, f, v)} /></td>
            </tr>
          ))}
        </tbody>
      </table>
      {picked && (
        <p className="wb-picked">
          <code>{expr}</code> into{" "}
          {draft.fields.map((f) => (
            <button key={f.name} type="button" disabled={!editable} onClick={() => put(f.name)}>{f.name}</button>
          ))}{" "}
          <button type="button" disabled={!editable} onClick={putKey}>a part of its own key</button>{" "}
          <button type="button" className="ghost" aria-label="Forget the value picked" onClick={() => setPicked(null)}>×</button>
        </p>
      )}
      <p className="muted small">Its events: click a value to read a field from it.</p>
      {got.error ? <p className="note lvl-error">{got.error}</p> : got.data && (
        <EventList events={got.data.events} open picked={picked ? JSON.stringify(picked) : undefined} onPick={(p) => setPicked(p)} />
      )}
    </details>
  );
}

export function MappingStep({ draft, ed, editable }: { draft: Draft; ed: MappingEdits; editable: boolean }) {
  return (
    <>
      <div className="wb-row">
        <div className="wb-grow"><span className="small">key</span>{" "}
          <span className="muted small">(an object's identity; several parts make a composite key)</span>
          <KeyParts parts={draft.keyParts} label="The projection's key" editable={editable} onChange={ed.setKeyParts} /></div>
        <label>time <Commit className="mono" value={draft.time} label="The event's own time" disabled={!editable}
          placeholder="the recorded time" onCommit={(v) => ed.setTop("time", v)} /></label>
      </div>
      <h3 className="small">Its fields <span className="muted">(what an object is)</span></h3>
      <Fields draft={draft} ed={ed} editable={editable} />
      <h3 className="small">What each kind of event tells</h3>
      {draft.kinds.length === 0 ? <p className="muted">No kinds of event yet (step 2).</p>
        : draft.kinds.map((k) => <KindMapping key={k.name} k={k} draft={draft} ed={ed} editable={editable} />)}
    </>
  );
}
