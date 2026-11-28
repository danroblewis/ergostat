import { useEffect, useRef, useState } from "react";
import { FOLDS, TYPES, type Draft } from "./draft";
import { Commit } from "./KindsStep";
import type { MappingEdits } from "./MappingStep";

/* Step 0, the schema: its fields (fields:, each its type, values, fold and description). And its key (key:, the fields
   that are an object's identity: several make a composite key; each kind of event's key is then what it maps to them,
   step 3), at the top of the panel on the right (KeySide), set before any mapping, from the fields declared. The query, the kinds of event and the mapping then find the parts. */

/** The key: the declared fields chosen, as pills on one line (each taken out with its ×), and a + at the end that
 *  opens the declared fields not in it. Its order does not matter: the YAML keeps the order they were added in. None
 *  chosen: the events' own item. */
export function KeyFields({ draft, editable, onChange }: { draft: Draft; editable: boolean; onChange: (names: string[]) => void }) {
  const key = draft.key;
  const others = draft.fields.map((f) => f.name).filter((f) => !key.includes(f));
  const [picking, setPicking] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!picking) return;
    const away = (e: MouseEvent) => { if (!box.current?.contains(e.target as Node)) setPicking(false); };
    document.addEventListener("mousedown", away);
    return () => document.removeEventListener("mousedown", away);
  }, [picking]);
  return (
    <div className="wb-keyfields" ref={box} onKeyDown={(e) => { if (e.key === "Escape") setPicking(false); }}>
      <ul className="wb-keypills" aria-label="The projection's key">
        {key.length === 0 && <li className="muted small">None: each event is its own item&apos;s (its <code>key</code>).</li>}
        {key.map((f) => (
          <li key={f} className="set-chip wb-keypill">
            <code>{f}</code>{!draft.fields.some((x) => x.name === f) && <span className="lvl-error small">not a field</span>}
            <button type="button" className="ghost" disabled={!editable} aria-label={`Take ${f} out of the key`}
              onClick={() => onChange(key.filter((x) => x !== f))}>×</button>
          </li>
        ))}
        <li className="wb-keyadd">
          <button type="button" className="ghost" aria-label="Put a field in the key" aria-expanded={picking} disabled={!editable}
            title={others.length ? "Add a field to the key" : draft.fields.length ? "Every field is in the key" : "Declare a field first (step 0)"}
            onClick={() => setPicking((x) => !x)}>+</button>
          {picking && (
            <ul className="wb-keymenu" role="menu" aria-label="The fields not in the key">
              {others.length ? others.map((f) => (
                <li key={f} role="none"><button type="button" role="menuitem" className="ghost"
                  onClick={() => { onChange([...key, f]); setPicking(false); }}><code>{f}</code></button></li>
              )) : <li className="muted small">{draft.fields.length ? "Every field is in the key." : "Declare a field first (step 0)."}</li>}
            </ul>
          )}
        </li>
      </ul>
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
      <p className="muted small">Its key is at the top of the panel on the right.</p>
      <Fields draft={draft} ed={ed} editable={editable} />
    </>
  );
}

/** The key at the top of the panel on the right: the fields that are an object's identity, chosen from those declared
 *  (step 0, the schema). */
export function KeySide({ draft, ed, editable }: { draft: Draft; ed: MappingEdits; editable: boolean }) {
  return (
    <>
    <section className="wb-keyside" aria-label="Its key">
      <h2 className="small">Its key <span className="muted">the fields that are an object&apos;s identity</span></h2>
      <KeyFields draft={draft} editable={editable} onChange={ed.setKey} />
    </section>
    <section className="wb-nameside" aria-label="Its name">
      <NameBox draft={draft} editable={editable} onCommit={(v) => ed.setTop("name", v)} />
    </section>
    </>
  );
}

/** Its name (`name:`), beside the key: an expression of the object's fields (`tags.Name or instance_id`; `key` its key),
 *  shown in place of the key; never its identity. The word being typed is completed with the field names. */
export function NameBox({ draft, editable, onCommit }: { draft: Draft; editable: boolean; onCommit: (v: string) => void }) {
  const [v, setV] = useState(draft.name);
  useEffect(() => setV(draft.name), [draft.name]);
  const done = () => { if (v.trim() !== draft.name.trim()) onCommit(v.trim()); };
  const m = /^(.*?)([A-Za-z_]\w*)?$/.exec(v)!;
  const head = m[1], word = m[2] || "";
  const names = [...draft.fields.map((f) => f.name), "key"].filter((f) => /^[A-Za-z_]\w*$/.test(f));
  const offered = names.filter((f) => f.startsWith(word) && f !== word && !/[.\]'"]$/.test(head)).map((f) => head + f);
  return (
    <label className="wb-namebox small">
      Its name <span className="muted">shown in place of the key</span>
      <input className="mono" list="wb-name-fields" value={v} disabled={!editable} spellCheck={false} aria-label="Its name, an expression of its fields"
        placeholder={names.length > 1 ? `${names[0]} or key` : "key"}
        onChange={(e) => setV(e.target.value)} onBlur={done} onKeyDown={(e) => { if (e.key === "Enter") done(); }} />
      <datalist id="wb-name-fields">{offered.slice(0, 50).map((o) => <option key={o} value={o} />)}</datalist>
    </label>
  );
}
