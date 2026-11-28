import { useEffect, useMemo, useRef, useState, type MouseEvent as RMouseEvent } from "react";
import type { JsonPath, PathMark } from "../../../components/JsonValues";
import { useSend } from "../../../hooks/useSend";
import { fieldName, guessType, isPath, ofKind, pathExpr, reads, solvedKey, TYPES, underAny, type Draft, type KindDef } from "./draft";
import { EventValues, short, type QEvent } from "./common";
import { Commit } from "./KindsStep";
import { Banner, type Live, type Opened } from "./opened";

/** A residual group opened (opened.tsx): shown in the kinds it names, as their samples, until it is fixed. */
export interface OpenedIn { o: Opened; live: Live | null; onUsual: () => void }

/* Step 4, the mapping: per kind of event, its key as solved from what it maps to the key's fields (✓ each part's
   expression, ✗ a part it does not tell, a click away from its mapping), one of its events shown as it reads (each
   value read into a field tagged with the field, a value nothing reads standing out, an ignored path hidden) beside
   the record that event makes. A value hovered (or clicked, or Enter on it) opens a panel floating by it: put it into a
   field (a key field among them), a new field, or ignore it (in every kind's events); hovered, the panel goes when the
   pointer leaves the value and the panel; clicked, it stays until the pointer leaves the panel, Escape or a click
   elsewhere. What another kind already maps by a plain path this kind's events have too is mapped here at once, said
   with a × to take each back. A kind whose sample events have every path mapped or ignored folds itself, a ✓ in its
   line; it opens again on a click. And the event's own time (time:). A residual group opened from the review (its
   no-key events, a refusal's, a split's object: opened.tsx) is shown in the kinds that took its events, as their
   samples, with a banner saying what it is and how many are left; the key parts it lacks, the field refused (and the
   value refused, marked in the event) or the key parts a split reads differently are highlighted. */

export interface MappingEdits {
  setTop: (k: "time", v: string) => void;
  addField: (name: string, type?: string) => void;
  setField: (name: string, part: "type" | "values" | "fold" | "description", v: string) => void;
  renameField: (from: string, to: string) => void;
  removeField: (name: string) => void;
  setKind: (kind: string, entry: string, v: string) => void;
  setKinds: (kind: string, pairs: [string, string][]) => void;
  createAndMap: (kind: string, field: string, type: string, expr: string) => void;
  ignore: (path: string) => void;
  setKey: (names: string[]) => void;
  /** a new field made and put at the end of the key, in one edit */
  addKeyField: (name: string, type: string) => void;
}

/** Every path in an event (its parts' and all within them), and its values' paths alone. */
function pathsOf(e: QEvent): { all: JsonPath[]; leaves: JsonPath[]; empties: Set<string> } {
  const all: JsonPath[] = [], leaves: JsonPath[] = [], empties = new Set<string>();
  const walk = (v: unknown, p: JsonPath) => {
    all.push(p);
    if (v !== null && typeof v === "object") {
      const es = Array.isArray(v) ? v.map((x, i) => [i, x] as [number, unknown]) : Object.entries(v as Record<string, unknown>);
      if (es.length) { for (const [k, x] of es) walk(x, [...p, k]); return; }
      empties.add(pathExpr(p));                    // an empty list or map: a leaf with nothing in it
    }
    leaves.push(p);
  };
  for (const [k, v] of [["type", e.type], ["key", e.item], ["source", e.source], ["data", e.data]] as [string, unknown][]) if (v != null) walk(v, [k]);
  return { all, leaves, empties };
}

/** The value at a path in an event. */
function valueAt(e: QEvent, path: JsonPath): unknown {
  const top: Record<string, unknown> = { type: e.type, key: e.item, source: e.source, data: e.data };
  let v: unknown = top;
  for (const p of path) v = v != null && typeof v === "object" ? (v as any)[p] : undefined;
  return v;
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
    <>
      <p><code>{expr}</code> = <code>{short(value)}</code>{" "}
        <button type="button" className="ghost" aria-label="Close" onClick={onDone}>×</button></p>
      <p>Into{" "}
        {draft.fields.map((f) => (
          <button key={f.name} type="button" disabled={!editable} onClick={done(() => ed.setKind(k.name, f.name, expr))}>{f.name}</button>
        ))}{" "}
        <button type="button" disabled={!editable} onClick={done(() => ed.ignore(expr))}>ignore this path</button>
      </p>
      <p>New field{" "}
        <input value={name} onChange={(e) => setName(e.target.value)} aria-label="The new field's name" className="mono" spellCheck={false}
          onKeyDown={(e) => { if (e.key === "Enter" && editable && ok) done(() => ed.createAndMap(k.name, name.trim(), type, expr))(); }} />{" "}
        <select value={type} onChange={(e) => setType(e.target.value)} aria-label="The new field's type">
          {TYPES.map((t) => <option key={t}>{t}</option>)}
        </select>{" "}
        <button type="button" disabled={!editable || !ok} onClick={done(() => ed.createAndMap(k.name, name.trim(), type, expr))}>Create and map</button>
        {taken && <span className="muted small"> (a field already)</span>}
      </p>
    </>
  );
}

type Pop = { path: JsonPath; value: unknown; x: number; y: number; pinned: boolean; kb: boolean };
const OPEN_MS = 250, GRACE_MS = 200;

function KindMapping({ k, draft, ed, editable, fold, opened }: {
  k: KindDef; draft: Draft; ed: MappingEdits; editable: boolean; fold: (evs: QEvent[]) => Record<string, unknown> | null;
  opened?: OpenedIn | null;
}) {
  const q = ofKind(draft.query, k.when);
  const body = useMemo(() => (q.trim() ? { query: q, limit: 5 } : null), [q]);
  const got = useSend<{ events: QEvent[] }>("events/query", body, 600);
  // a residual group opened here: its events are the samples while it is not fixed
  const live = opened?.live ?? null;
  const theirs = useMemo(() => (live ? live.events.filter((x) => x.kind === k.name) : []), [live, k.name]);
  const evs = useMemo(() => (theirs.length ? theirs : got.data?.events || []), [theirs, got.data]);
  const [at, setAt] = useState(0);
  const e = evs.length ? evs[Math.min(at, evs.length - 1)] : null;
  const [showIgnored, setShowIgnored] = useState(false);
  const [adding, setAdding] = useState<string[]>([]);
  const told: Record<string, string> = Object.fromEntries(k.values);
  const solved = solvedKey(draft.key, k);
  const [focus, setFocus] = useState<string | null>(null);
  useEffect(() => {                                   // a ✗ clicked: that field's mapping for this kind, ready to type
    if (!focus) return;
    const el = document.querySelector<HTMLInputElement>(`input[aria-label="${CSS.escape(`${k.name}: ${focus}`)}"]`);
    if (el) { el.focus(); el.scrollIntoView({ block: "nearest" }); setFocus(null); }
  });
  const hlKey = live?.key ?? [];                       // what the group opened highlights: key parts, a field refused
  const hlField = live?.field;
  const box = useRef<HTMLDetailsElement>(null);
  const token = opened?.o.token;
  useEffect(() => {                                   // opened: shown, scrolled to, its key parts' mappings ready to type
    if (token == null) return;
    setOpen(true);
    setAt(0);
    box.current?.scrollIntoView({ block: "start", behavior: "smooth" });
    if (live?.untold.length) setAdding((x) => [...new Set([...x, ...live.untold])]);
    const f = live?.key[0] ?? live?.field;
    if (f) setFocus(f);
  }, [token]);   // eslint-disable-line react-hooks/exhaustive-deps

  const base = (p: JsonPath): PathMark => {
    const x = pathExpr(p);
    if (underAny(x, draft.ignore)) return { ignored: true };
    for (const [f, ex] of k.values) if (reads(ex, x)) return { to: f };
    for (const kp of solved) if (kp.spread && kp.expr && reads(kp.expr, x)) return { to: kp.field };
    if (!draft.key.length && x === "key") return { to: "key" };
    if (draft.time && reads(draft.time, x)) return { to: "time" };
    return {};
  };
  // the value refused, marked where the field reads it (else wherever it is); a split's key parts read differently
  const flagged = (p: JsonPath, m: PathMark): string | undefined => {
    if (!live || !e) return undefined;
    if (hlField != null && JSON.stringify(valueAt(e, p)) === JSON.stringify(live.value) && (!told[hlField] || m.to === hlField))
      return `refused: ${short(live.why, 120)}`;
    if (m.to && hlKey.includes(m.to) && opened?.o.what === "split") return `the key's ${m.to}, read differently by the kinds`;
    return undefined;
  };
  const mark = (p: JsonPath): PathMark => {
    const m = base(p);
    const flag = flagged(p, m);
    return flag ? { ...m, flag } : m;
  };
  const paths = e ? pathsOf(e) : { all: [], leaves: [] };
  const nIgnored = paths.leaves.filter((p) => underAny(pathExpr(p), draft.ignore)).length;

  // every path left in its sample events: not read into a field (itself or what holds it), nor ignored
  const decided = (p: JsonPath) => { for (let i = p.length; i > 0; i--) { const m = mark(p.slice(0, i)); if (m.to || m.ignored) return true; } return false; };
  // an empty list or map counts as decided when, in another of its events, what it holds when not empty is decided
  // (`items: []` here, `items[0].instanceId` mapped there); else it is ignored or mapped like any value
  const all = evs.map(pathsOf);
  const decidedUnder = all.flatMap((x) => x.leaves.filter((p) => !x.empties.has(pathExpr(p)) && decided(p)).map(pathExpr));
  const settled = (p: JsonPath, empties: Set<string>) => {
    if (decided(p)) return true;
    const x = pathExpr(p);
    return empties.has(x) && decidedUnder.some((d) => d.startsWith(x + ".") || d.startsWith(x + "["));
  };
  const left = new Set(all.flatMap((x) => x.leaves.filter((p) => !settled(p, x.empties)).map(pathExpr))).size;
  const complete = evs.length > 0 && left === 0;
  const [open, setOpen] = useState(true);
  const wasComplete = useRef(false);
  useEffect(() => { if (complete && !wasComplete.current) setOpen(false); wasComplete.current = complete; }, [complete]);

  // what another kind maps by a plain path that this kind's events have too, mapped here at once: never a field this
  // kind has told already (one taken back stays taken back)
  const had = useRef(new Set<string>());
  for (const f of Object.keys(told)) had.current.add(f);
  const same = useMemo(() => {
    const present = new Set(evs.flatMap((x) => pathsOf(x).all.map(pathExpr)));
    const out: [string, string, string][] = [];
    for (const o of draft.kinds) {
      if (o.name === k.name) continue;
      for (const [f, ex] of o.values) {
        if (had.current.has(f) || !draft.fields.some((x) => x.name === f) || out.some(([g]) => g === f)) continue;
        if (isPath(ex) && present.has(ex.trim())) out.push([f, ex.trim(), o.name]);
      }
    }
    return out;
  }, [evs, draft, k.name]);   // eslint-disable-line react-hooks/exhaustive-deps
  const [auto, setAuto] = useState<[string, string, string][]>([]);
  const sameSig = JSON.stringify(same);
  useEffect(() => {
    if (!editable || !same.length) return;
    ed.setKinds(k.name, same.map(([f, ex]) => [f, ex]));
    setAuto((a) => [...a.filter(([f]) => !same.some(([g]) => g === f)), ...same]);
  }, [sameSig, editable]);   // eslint-disable-line react-hooks/exhaustive-deps
  const mapped = auto.filter(([f, ex]) => told[f]?.trim() === ex);
  const froms = [...new Set(mapped.map(([, , o]) => o))];

  // the floating panel: hovered after a moment, or clicked (pinned)
  const wrap = useRef<HTMLDivElement>(null);
  const popEl = useRef<HTMLDivElement>(null);
  const [pop, setPop] = useState<Pop | null>(null);
  const timers = useRef<{ open?: number; close?: number }>({});
  const stop = (w: "open" | "close") => { window.clearTimeout(timers.current[w]); timers.current[w] = undefined; };
  useEffect(() => () => { stop("open"); stop("close"); }, []);
  const closeSoon = () => { stop("close"); timers.current.close = window.setTimeout(() => setPop(null), GRACE_MS); };
  const openAt = (b: HTMLElement, pinned: boolean, kb = false) => {
    if (!e || !wrap.current) return;
    let path: JsonPath;
    try { path = JSON.parse(b.dataset.path || ""); } catch { return; }
    const w = wrap.current.getBoundingClientRect(), r = b.getBoundingClientRect();
    stop("open"); stop("close");
    setPop({ path, value: valueAt(e, path), x: Math.max(0, Math.min(r.left - w.left, w.width - 352)), y: r.bottom - w.top + 2, pinned, kb });
  };
  const valueOf = (ev: { target: EventTarget }) => (ev.target as HTMLElement).closest?.<HTMLElement>(".wb-sample button[data-path]") ?? null;
  const onOver = (ev: RMouseEvent) => {
    const b = valueOf(ev);
    if (!b) return;
    const here = !!pop && JSON.stringify(pop.path) === b.dataset.path;
    if (pop && (!pop.pinned || here)) stop("close");
    if (pop?.pinned || here) return;
    stop("open");
    timers.current.open = window.setTimeout(() => openAt(b, false), OPEN_MS);
  };
  const onOut = (ev: RMouseEvent) => {
    const b = valueOf(ev);
    if (!b || (ev.relatedTarget instanceof Node && b.contains(ev.relatedTarget))) return;
    stop("open");
    if (pop && !pop.pinned) closeSoon();
  };
  useEffect(() => {
    if (!pop) return;
    if (pop.kb) popEl.current?.querySelector<HTMLElement>("button:not([disabled]), input")?.focus();
    const key = (ev: KeyboardEvent) => { if (ev.key === "Escape") setPop(null); };
    const down = (ev: MouseEvent) => {
      const t = ev.target as HTMLElement;
      if (popEl.current?.contains(t) || t.closest?.(".wb-sample button[data-path]")) return;
      setPop(null);
    };
    document.addEventListener("keydown", key);
    document.addEventListener("mousedown", down);
    return () => { document.removeEventListener("keydown", key); document.removeEventListener("mousedown", down); };
  }, [pop]);

  const rows = [...k.values.map(([f]) => f), ...adding.filter((f) => !(f in told))];
  const untold = draft.fields.map((f) => f.name).filter((f) => !rows.includes(f));

  return (
    <details ref={box} className={`wb-map${complete ? " done" : ""}`} open={open} data-kind={k.name}
      onToggle={(ev) => setOpen((ev.currentTarget as HTMLDetailsElement).open)}>
      <summary>
        {complete && <span className="wb-done" aria-label="Every path mapped">✓ </span>}
        <strong>{k.name}</strong>{" "}
        {complete ? <span className="muted small" data-testid={`done-${k.name}`}>every path in its events mapped or ignored</span>
          : <code className="muted small">{short(k.when, 80)}</code>}
        {!complete && evs.length > 0 && <span className="muted small"> · {left} path{left === 1 ? "" : "s"} left</span>}
      </summary>
      {opened && <Banner o={opened.o} live={live} kind={k.name} onUsual={opened.onUsual} />}
      {mapped.length > 0 && (
        <p className="wb-same" data-testid={`same-${k.name}`}>
          {froms.map((o) => (
            <span key={o} className="wb-same-from">
              Mapped the same way as <strong>{o}</strong>:{" "}
              {mapped.filter(([, , x]) => x === o).map(([f, ex]) => (
                <span key={f} className="wb-same-one">
                  <code>{ex}</code> → {f}
                  <button type="button" className="ghost" disabled={!editable} aria-label={`Unmap ${f} for ${k.name}`}
                    onClick={() => ed.setKind(k.name, f, "")}>×</button>
                </span>
              ))}
            </span>
          ))}
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
                    <span key={kp.field} className={`${kp.expr ? "wb-key-ok" : "wb-key-no"}${hlKey.includes(kp.field) ? " wb-hl" : ""}`}>
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
            <tr key={f} className={f === hlField || hlKey.includes(f) ? "wb-hl" : undefined}>
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
      {got.error ? <p className="note lvl-error">{got.error}</p> : !e ? <p className="muted small">{got.data ? "None of its events in the query's result." : "Reading…"}</p> : (
        <>
          <p className="muted small wb-sample-nav">
            An event of it{evs.length > 1 && <>, {at + 1} of {evs.length}{" "}
              <button type="button" className="ghost" aria-label="The previous event" disabled={at === 0} onClick={() => { setPop(null); setAt(at - 1); }}>‹</button>
              <button type="button" className="ghost" aria-label="The next event" disabled={at >= evs.length - 1} onClick={() => { setPop(null); setAt(at + 1); }}>›</button></>}
            : point at a value to put it somewhere.
            {nIgnored > 0 && <>{" "}<button type="button" className="ghost small" aria-pressed={showIgnored}
              onClick={() => setShowIgnored(!showIgnored)}>{showIgnored ? "hide" : "show"} ignored ({nIgnored})</button></>}
          </p>
          <div className="wb-pair" ref={wrap}>
            <div className="wb-sample" aria-label={`An event of ${k.name}`} onMouseOver={onOver} onMouseOut={onOut}
              onClick={(ev) => { const b = valueOf(ev); if (b) openAt(b, true, ev.detail === 0); }}>
              <EventValues e={e} mark={mark} showIgnored={showIgnored} picked={pop ? JSON.stringify(pop.path) : undefined}
                onPick={() => {}} />
            </div>
            <Made e={e} kind={k.name} fold={fold} />
            {pop && (
              <div ref={popEl} className="wb-pop wb-picked" role="dialog" aria-label="The value picked" style={{ left: pop.x, top: pop.y }}
                onMouseEnter={() => stop("close")} onMouseLeave={closeSoon}>
                <Picked key={JSON.stringify(pop.path)} k={k} draft={draft} ed={ed} editable={editable} path={pop.path} value={pop.value}
                  onDone={() => setPop(null)} />
              </div>
            )}
          </div>
        </>
      )}
    </details>
  );
}

export function MappingStep({ draft, ed, editable, fold, opened }: {
  draft: Draft; ed: MappingEdits; editable: boolean; fold: (evs: QEvent[]) => Record<string, unknown> | null;
  /** a residual group opened from the review: shown in the kinds it names */
  opened?: OpenedIn | null;
}) {
  return (
    <>
      <p className="wb-row">
        <label>The event's own time <Commit className="mono" value={draft.time} label="The event's own time" disabled={!editable}
          placeholder="the recorded time" onCommit={(v) => ed.setTop("time", v)} /></label>
      </p>
      {draft.kinds.length === 0 ? <p className="muted">No kinds of event yet (step 3).</p>
        : draft.kinds.map((k) => <KindMapping key={k.name} k={k} draft={draft} ed={ed} editable={editable} fold={fold}
          opened={opened?.o.in.includes(k.name) ? opened : null} />)}
    </>
  );
}
