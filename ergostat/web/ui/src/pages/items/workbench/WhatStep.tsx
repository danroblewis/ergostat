import { useState } from "react";
import { FOLDS, TYPES, type Draft } from "./draft";
import { Commit } from "./KindsStep";
import type { MappingEdits } from "./MappingStep";

/* Step 1, what it is: the object's identity before any event is read. Its key (key:, the fields that are its
   identity, in order: several make a composite key; each kind of event's key is then what it maps to them, step 4) and
   its fields (fields:, each its type, values, fold and description). The query, the kinds of event and the mapping
   then find the parts. */

/** The key: the declared fields chosen, in order (each moved up or down, or taken out), and a choice of the others
 *  to add. None chosen: the events' own item. */
export function KeyFields({ draft, editable, onChange }: { draft: Draft; editable: boolean; onChange: (names: string[]) => void }) {
  const key = draft.key;
  const others = draft.fields.map((f) => f.name).filter((f) => !key.includes(f));
  const move = (i: number, by: number) => {
    const x = [...key];
    [x[i], x[i + by]] = [x[i + by], x[i]];
    onChange(x);
  };
  return (
    <div className="wb-keyfields">
      {key.length === 0 ? <p className="muted small">None: each event is its own item&apos;s (its <code>key</code>).</p> : (
        <ol className="wb-keyparts" aria-label="The projection's key">
          {key.map((f, i) => (
            <li key={f}>
              <code>{f}</code>{!draft.fields.some((x) => x.name === f) && <span className="lvl-error small"> not a field</span>}{" "}
              <button type="button" className="ghost" disabled={!editable || i === 0} aria-label={`Move ${f} up`} onClick={() => move(i, -1)}>↑</button>
              <button type="button" className="ghost" disabled={!editable || i === key.length - 1} aria-label={`Move ${f} down`} onClick={() => move(i, 1)}>↓</button>
              <button type="button" className="ghost" disabled={!editable} aria-label={`Take ${f} out of the key`}
                onClick={() => onChange(key.filter((x) => x !== f))}>×</button>
            </li>
          ))}
        </ol>
      )}
      <select value="" aria-label="Add a field to the key" disabled={!editable || !others.length}
        onChange={(e) => { const f = e.target.value; if (f) onChange([...key, f]); }}>
        <option value="">{others.length ? "add a field to the key…" : draft.fields.length ? "every field is in the key" : "declare a field first"}</option>
        {others.map((f) => <option key={f} value={f}>{f}</option>)}
      </select>
    </div>
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

export function WhatStep({ draft, ed, editable }: { draft: Draft; ed: MappingEdits; editable: boolean }) {
  return (
    <>
      <h3 className="small">Its key <span className="muted">(the fields that are an object&apos;s identity, in order; each kind of event maps them)</span></h3>
      <KeyFields draft={draft} editable={editable} onChange={ed.setKey} />
      <h3 className="small">Its fields</h3>
      <Fields draft={draft} ed={ed} editable={editable} />
    </>
  );
}
