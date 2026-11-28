import { useEffect, useState, type ReactNode } from "react";
import { Bars, Plot } from "../../../components/charts";
import { stamp } from "../../../lib/format";
import { n, Samples, short } from "./common";
import { howRead } from "./QueryStep";

/* The review (POST /api/projections/review on the draft): step 5 in the main column (what the draft makes, what each
   kind took, the paths left to decide, the comparison with the saved definition), and the panel on the right (one
   object's record and lifespan, the residual, the lifecycles, every field's distribution). What is unexplained is
   counted in `unexplained`, which the workbench keeps in sight above the steps; a 0 is never shown. */

/** The residual's counts, by what the workbench calls each. */
export function unexplained(r: any): [string, number][] {
  const s = r?.residual;
  if (!s) return [];
  const idle = (r.kinds || []).filter((k: any) => k.count === 0).length;
  return ([
    ["remainder", s.remainder?.count ?? 0], ["no key", s.no_key?.count ?? 0], ["refused", s.refused?.count ?? 0],
    ["contradictions", s.contradictions?.count ?? 0], ["possible splits", s.splits?.count ?? 0],
    ["possible merges", s.merges?.count ?? 0], [idle === 1 ? "kind takes nothing" : "kinds take nothing", idle],
  ] as [string, number][]).filter(([, c]) => c > 0);
}

const iso = (s: string) => Date.parse(s) / 1000;
const val = (v: unknown) => (v === undefined ? "–" : short(v, 50));

function Distribution({ f }: { f: any }) {
  const head = (
    <h4>
      <code>{f.field}</code> <span className="muted small">{f.type || "any"}{f.declared ? "" : ", not declared"} · in {n(f.have)} of {n(f.objects)} objects
        {f.distinct != null ? ` · ${n(f.distinct)} values` : ""}{f.min != null ? ` · ${val(f.min)} to ${val(f.max)}` : ""}</span>
    </h4>
  );
  let body: ReactNode = null;
  if (f.histogram && typeof f.histogram[0]?.[0] === "string") {
    const times = f.histogram.map((b: any) => iso(b[0]));
    body = (
      <div className="wb-plot" aria-label={`${f.field}: a histogram over time`}>
        <Plot times={times} series={[{ label: "objects", values: f.histogram.map((b: any) => b[2]) }]} kind="bar" yMin={0} />
      </div>
    );
  } else if (f.histogram) {
    body = <Bars label={`${f.field}: a histogram`} rows={f.histogram.map((b: any) => ({ key: String(b[0]), label: `${short(b[0], 12)} to ${short(b[1], 12)}`, n: b[2] }))} />;
  } else if (f.top) {
    body = <Bars label={`${f.field}: its values`} rows={f.top.map(([v, c]: [unknown, number]) => ({ key: JSON.stringify(v), label: <code>{short(v, 40)}</code>, n: c }))}
      note={f.distinct > f.top.length ? `the top ${f.top.length} of ${n(f.distinct)}` : undefined} />;
  } else if (f.sizes) {
    body = <p className="muted small">sizes {f.sizes.min} to {f.sizes.max}, {f.sizes.mean} on average</p>;
  }
  return (
    <div className="wb-dist">
      {head}
      {body}
      {f.not_its_type ? <p className="lvl-warn small">{typeof f.not_its_type === "number" ? `${n(f.not_its_type)} not of its type` : short(f.not_its_type, 120)}</p> : null}
    </div>
  );
}

function Lifecycle({ field, l }: { field: string; l: any }) {
  return (
    <div className="wb-dist" data-testid={`lifecycle-${field}`}>
      <h4><code>{field}</code> <span className="muted small">its lifecycle, over {n(l.objects)} objects</span></h4>
      <p className="small">now: {Object.entries(l.now || {}).map(([v, c]) => `${v} ${n(c as number)}`).join(" · ") || "none"}</p>
      <Bars label={`${field}: its transitions`} rows={(l.transitions || []).map((t: any) => ({
        key: `${t.from}>${t.to}`, label: <span>{t.from ?? "(new)"} → {t.to}</span>, n: t.count, extra: `${n(t.objects)} objects`,
      }))} />
      {l.rare?.length > 0 && <p className="lvl-warn small">rare: {l.rare.map((t: any) => `${t.from} → ${t.to} (${t.count})`).join(", ")}</p>}
    </div>
  );
}

/** One line of the residual: its count, opened to what it holds; nothing at all when it is 0. */
function Residue({ label, count, children }: { label: string; count: number; children?: ReactNode }) {
  if (!count) return null;
  return (
    <li>
      <details>
        <summary><span className="wb-kind-n lvl-warn">{n(count)}</span> {label}</summary>
        <div className="wb-residue">{children}</div>
      </details>
    </li>
  );
}

/** An object: its record (its fields now) and its lifespan (its events in time order, which kind took each, each
    field's before → after), its state's path through its values above them. */
function Lifespan({ t }: { t: any }) {
  if (!t.found) return <p className="muted">No object has the key <code>{t.key}</code>.</p>;
  const moves = t.steps.filter((s: any) => s.move).map((s: any) => s.move);
  const path = moves.length ? [moves[0].from ?? "(new)", ...moves.map((m: any) => m.to)] : [];
  return (
    <>
      <ul className="jv wb-now" aria-label="The object's record">
        {t.state != null && <li><span className="jv-key">state</span> <strong>{t.state}</strong></li>}
        {Object.entries(t.fields || {}).map(([k, v]) => <li key={k}><span className="jv-key">{k}</span> <span className="jv-val">{short(v, 60)}</span></li>)}
      </ul>
      {path.length > 0 && <p className="small" data-testid="state-path">{path.join(" → ")}</p>}
      <table className="wb-table" aria-label="The object's timeline">
        <thead><tr><th>Event time</th><th>Kind</th><th>What it changed</th></tr></thead>
        <tbody>{t.steps.map((s: any) => (
          <tr key={s.id + s.time}>
            <td className="small">{stamp(s.time)}</td>
            <td>{s.kind ?? <span className="muted">none</span>}</td>
            <td className="small">
              {s.move && <div><strong>{s.move.from ?? "(new)"} → {s.move.to}</strong></div>}
              {(s.changes || []).map((c: any, i: number) => (
                <div key={i}><code>{c.field}</code> {val(c.before)} → {val(c.after)}</div>
              ))}
              {s.refused && <div className="lvl-error">refused: {short(s.refused, 120)}</div>}
              {s.unchanged && <div className="muted">changed nothing</div>}
            </td>
          </tr>
        ))}</tbody>
      </table>
      {t.steps_left ? <p className="muted small">{n(t.steps_left)} more events.</p> : null}
    </>
  );
}

/** Step 5, the review in the main column: what the draft makes, what each kind took, the comparison with the saved
    definition, and the paths no field reads yet (what is left to decide), each ignorable. */
export function ReviewStep({ r, error, busy, onIgnore, editable }: {
  r: any; error: string | null; busy: boolean; onIgnore: (path: string) => void; editable: boolean;
}) {
  if (error) return <p className="note lvl-error" role="alert">{error}</p>;
  if (!r) return <p className="muted">{busy ? "Reviewing the draft on the record…" : "Nothing to review yet."}</p>;
  if (!r.ok) {
    return (
      <div aria-live="polite">
        <p className="lvl-error"><strong>Does not check</strong></p>
        <ul className="try-errors">{r.errors.map((e: any, i: number) => <li key={i}>{e.line ? `line ${e.line}: ` : ""}{e.message}</li>)}</ul>
      </div>
    );
  }
  const c = r.compared;
  const u = r.unmapped;
  return (
    <div aria-busy={busy}>
      <p>
        <strong data-testid="review-objects">{n(r.objects.count)}</strong> objects from <strong>{n(r.read.events)}</strong> events,
        keyed by <code>{(r.objects.key || []).join(" / ")}</code>
        {r.objects.one_event ? <span className="muted">, {n(r.objects.one_event)} with one event</span> : null}
        <span className="muted small"> · {howRead(r.read)}</span>
      </p>
      <Bars label="What each kind of event took" rows={(r.kinds || []).map((k: any) => ({
        key: k.name, label: k.name, n: k.count, extra: `${n(k.objects)} objects`,
      }))} />
      {r.duplicates?.says && <p className="muted small">{r.duplicates.says}</p>}

      {u?.count > 0 && (
        <>
          <h3 className="small">Left to decide <span className="muted">paths in the kinds' events no field or key reads: map or ignore each</span></h3>
          <ul className="wb-kinds" aria-label="Unmapped paths">
            {u.paths.map((x: any) => (
              <li key={x.path} className="wb-unmapped">
                <span className="wb-kind-n">{n(x.events)}</span> <code>{x.path}</code>{" "}
                <span className="muted small">{x.kinds.join(", ")}</span>{" "}
                <button type="button" className="ghost small" disabled={!editable} onClick={() => onIgnore(x.path)}
                  aria-label={`Ignore ${x.path}`}>ignore</button>
              </li>
            ))}
          </ul>
          {u.paths_left ? <p className="muted small">{n(u.paths_left)} more.</p> : null}
        </>
      )}

      {c && (c.appear || c.disappear || c.change) ? (
        <>
          <h3 className="small">Against the saved definition</h3>
          <ul className="wb-residual" aria-label="Against the saved definition">
            <Residue label="objects appear" count={c.appear}><p className="small">{(c.appear_sample || []).join(", ")}</p></Residue>
            <Residue label="objects disappear" count={c.disappear}><p className="small">{(c.disappear_sample || []).join(", ")}</p></Residue>
            <Residue label="objects change" count={c.change}>
              <ul>{(c.fields || []).map((f: any) => (
                <li key={f.field}><code>{f.field}</code> in {n(f.objects)}
                  <ul>{(f.samples || []).map((x: any, i: number) => <li key={i} className="small">{x.key}: {val(x.saved)} → {val(x.draft)}</li>)}</ul>
                </li>
              ))}</ul>
            </Residue>
          </ul>
        </>
      ) : c ? <p className="muted small">✓ The same objects as the saved definition.</p> : null}
    </div>
  );
}

/** The objects the draft makes, one at a time: ‹ › to step through them (in key order), a search to jump to one by its
    key, and the one shown as its record and its change history (Lifespan). */
function Objects({ r, item, onItem }: { r: any; item: string; onItem: (k: string) => void }) {
  const keys: string[] = r.objects.keys || r.objects.sample || [];
  const [find, setFind] = useState("");
  useEffect(() => { if (!item && keys.length) onItem(keys[0]); }, [item, keys.length]);   // eslint-disable-line react-hooks/exhaustive-deps
  const i = keys.indexOf(item);
  const jump = () => {
    const w = find.trim();
    if (!w) return;
    onItem(keys.includes(w) ? w : keys.find((k) => k.includes(w)) ?? w);
  };
  const t = r.timeline;
  return (
    <section className="wb-objects" aria-label="Its objects">
      <h2 className="small">Its objects <span className="muted">{n(r.objects.count)}</span></h2>
      {!keys.length ? <p className="muted small">None yet: no event is keyed to an object.</p> : (
        <>
          <div className="wb-row wb-browse">
            <button type="button" className="ghost" aria-label="The previous object" disabled={i <= 0} onClick={() => onItem(keys[i - 1])}>‹</button>
            <span className="small" data-testid="object-at">{i < 0 ? "–" : n(i + 1)} of {n(keys.length)}{r.objects.count > keys.length ? "+" : ""}</span>
            <button type="button" className="ghost" aria-label="The next object" disabled={i >= keys.length - 1}
              onClick={() => onItem(keys[i < 0 ? 0 : i + 1])}>›</button>
            <input className="wb-grow mono" list="wb-objects" value={find} onChange={(e) => setFind(e.target.value)} aria-label="Find an object by its key"
              placeholder="find by key" onKeyDown={(e) => { if (e.key === "Enter") jump(); }} />
            <datalist id="wb-objects">{keys.slice(0, 200).map((k) => <option key={k} value={k} />)}</datalist>
          </div>
          {t && t.key === item ? <><p className="small"><code data-testid="object-key">{t.key}</code></p><Lifespan t={t} /></>
            : <p className="muted small">Reading…</p>}
        </>
      )}
    </section>
  );
}

/** The panel on the right, beside the steps: its key (set before any mapping), its objects one at a time, the
    lifecycles and each field's distribution, and the residual at the bottom (only what is not 0; all 0, one check). */
export function SidePanel({ r, item, onItem, keyPart, onOpen }: {
  r: any; item: string; onItem: (k: string) => void; keyPart: ReactNode;
  /** a residual group opened in the mapping step, its events there to map */
  onOpen?: (what: "no_key" | "refused" | "split", group: any) => void;
}) {
  if (!r?.ok) return <>{keyPart}<p className="muted small">{r ? "The draft does not check: see the review." : "Not reviewed yet."}</p></>;
  const s = r.residual;
  const none = unexplained(r).length === 0;
  const open = (what: "no_key" | "refused" | "split", g: any, label: string) => (onOpen && g ? (
    <>{" "}<button type="button" className="ghost small" aria-label={`Open ${label} in the mapping`} onClick={() => onOpen(what, g)}>open</button></>
  ) : null);
  const nkGroup = (k: string) => (s.no_key.groups || []).find((g: any) => g.kind === k);
  return (
    <>
      {keyPart}
      <Objects r={r} item={item} onItem={onItem} />

      {Object.keys(r.lifecycles || {}).length > 0 && <h2 className="small">Lifecycles</h2>}
      <div className="wb-dists">
        {Object.entries(r.lifecycles || {}).map(([f, l]) => <Lifecycle key={f} field={f} l={l} />)}
      </div>

      <h2 className="small">Its fields, across the objects</h2>
      {r.fields.length === 0 ? <p className="muted">No fields yet (step 1).</p> : (
        <div className="wb-dists">{r.fields.map((f: any) => <Distribution key={f.field} f={f} />)}</div>
      )}

      <h2 className="small wb-residual-h">The residual</h2>
      {none ? <p data-testid="residual-ok">✓ Nothing unexplained</p> : (
        <ul className="wb-residual" aria-label="The residual">
          <Residue label="remainder: events no kind takes" count={s.remainder.count}>
            <ul className="wb-kinds">{s.remainder.kinds.map((k: any) => (
              <li key={k.when}><span className="wb-kind-n">{n(k.count)}</span> <code>{k.when}</code><Samples samples={k.samples} /></li>
            ))}</ul>
          </Residue>
          <Residue label="no key: taken, but keyed to nothing" count={s.no_key.count}>
            <ul className="small" aria-label="No key, by kind">{Object.entries(s.no_key.by_kind || {}).map(([k, v]) => (
              <li key={k}><strong>{k}</strong> {n(v as number)}{s.no_key.lacks?.[k]?.length
                ? <>: tells no <code>{s.no_key.lacks[k].join(", ")}</code></>
                : <span className="muted">: a key field it maps reads no value</span>}{open("no_key", nkGroup(k), `${k}'s events with no key`)}</li>
            ))}</ul>
            <ul className="wb-kinds">{(s.no_key.kinds || []).map((k: any) => (
              <li key={k.when}><span className="wb-kind-n">{n(k.count)}</span> <code>{k.when}</code><Samples samples={k.samples} /></li>
            ))}</ul>
          </Residue>
          <Residue label="refused" count={s.refused.count}>
            <ul>{s.refused.groups.map((g: any, i: number) => (
              <li key={i}><span className="wb-kind-n">{n(g.count)}</span> {g.why} {typeof g.objects === "number" && <span className="muted small">({n(g.objects)} object{g.objects === 1 ? "" : "s"})</span>}
                {g.samples?.length > 0 && open("refused", g, `the events refused: ${short(g.why, 60)}`)}</li>
            ))}</ul>
          </Residue>
          <Residue label="contradictions: rare or impossible histories" count={s.contradictions.count}>
            <ul>{s.contradictions.rare.map((x: any, i: number) => (
              <li key={i}><code>{x.field}</code> {x.from} → {x.to}: {n(x.count)} <span className="muted small">{(x.samples || []).join(", ")}</span></li>
            ))}</ul>
            {s.contradictions.after_final > 0 && <p className="small">{n(s.contradictions.after_final)} moves out of a final state</p>}
          </Residue>
          <Residue label="possible splits: one thing under two keys" count={s.splits.count}>
            <ul>{s.splits.groups.map((g: any, i: number) => (
              <li key={i}>only {g.kinds.join(", ")}: {n(g.objects)} objects <span className="muted small">{(g.samples || []).join(", ")}</span>
                {g.events?.length > 0 && open("split", g, `the split keyed by ${g.kinds.join(", ")}`)}</li>
            ))}</ul>
          </Residue>
          <Residue label="possible merges: two things under one key" count={s.merges.count}>
            <ul>{s.merges.fields.map((g: any, i: number) => (
              <li key={i}><code>{g.field}</code> given twice: {n(g.objects)} objects <span className="muted small">{(g.samples || []).join(", ")}</span></li>
            ))}</ul>
          </Residue>
          <Residue label="kinds of event take nothing" count={(r.kinds || []).filter((k: any) => k.count === 0).length}>
            <p className="small">{(r.kinds || []).filter((k: any) => k.count === 0).map((k: any) => k.name).join(", ")}</p>
          </Residue>
        </ul>
      )}

    </>
  );
}
