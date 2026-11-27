import { useState } from "react";
import { FOLDS, TYPES, type Draft } from "./draft";
import { Commit } from "./KindsStep";
import type { MappingEdits } from "./MappingStep";

/* Step 1, what it is: the object's identity before any event is read. Its key (key:, one expression a row: a
   composite key is several) and its fields (fields:, each its type, values, fold and description). The query, the
   kinds of event and the mapping then find the parts. */

/** A key as its parts, one expression a row (a composite key: account, region, id), with a row added or taken out.
 *  Each row is an expression as written: no brackets or quoting. */
export function KeyParts({ parts, label, editable, onChange }: {
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

export function WhatStep({ draft, ed, editable }: { draft: Draft; ed: MappingEdits; editable: boolean }) {
  return (
    <>
      <h3 className="small">Its key <span className="muted">(an object's identity; several parts make a composite key)</span></h3>
      <KeyParts parts={draft.keyParts} label="The projection's key" editable={editable} onChange={ed.setKeyParts} />
      <h3 className="small">Its fields</h3>
      <Fields draft={draft} ed={ed} editable={editable} />
    </>
  );
}
