import { useEffect, useState, type ReactNode } from "react";
import { Bars, Plot } from "../../../components/charts";
import { stamp } from "../../../lib/format";
import { n, Samples, short } from "./common";
import { howRead } from "./QueryStep";

/* Step 4, the review (POST /api/projections/review on the draft): every field's distribution, the lifecycles, the
   residual (each a count, opened to its samples), the comparison with the saved definition, and one object's
   timeline. What is unexplained is counted in `unexplained`, which the workbench keeps in sight above the steps. */

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

/** One line of the residual: its count, opened to what it holds. */
function Residue({ label, count, children }: { label: string; count: number; children?: ReactNode }) {
  if (!count) return <li className="muted"><span className="wb-kind-n">0</span> {label}</li>;
  return (
    <li>
      <details>
        <summary><span className="wb-kind-n lvl-warn">{n(count)}</span> {label}</summary>
        <div className="wb-residue">{children}</div>
      </details>
    </li>
  );
}

function Timeline({ t }: { t: any }) {
  if (!t.found) return <p className="muted">No object has the key <code>{t.key}</code>.</p>;
  return (
    <>
      <p className="small">{n(t.events)} events; now <strong>{t.state ?? "–"}</strong>{" "}
        <span className="muted">{Object.entries(t.fields || {}).map(([k, v]) => `${k} ${short(v, 30)}`).join(" · ")}</span></p>
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
    </>
  );
}

export function ReviewStep({ r, error, busy, item, onItem }: {
  r: any; error: string | null; busy: boolean; item: string; onItem: (k: string) => void;
}) {
  const [key, setKey] = useState(item);
  useEffect(() => setKey(item), [item]);
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
  const s = r.residual;
  const c = r.compared;
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

      <h3 className="small">The residual</h3>
      <ul className="wb-residual" aria-label="The residual">
        <Residue label="remainder: events no kind takes" count={s.remainder.count}>
          <ul className="wb-kinds">{s.remainder.kinds.map((k: any) => (
            <li key={k.when}><span className="wb-kind-n">{n(k.count)}</span> <code>{k.when}</code><Samples samples={k.samples} /></li>
          ))}</ul>
        </Residue>
        <Residue label="no key: taken, but keyed to nothing" count={s.no_key.count}>
          <p className="small">{Object.entries(s.no_key.by_kind || {}).map(([k, v]) => `${k} ${n(v as number)}`).join(" · ")}</p>
          <ul className="wb-kinds">{(s.no_key.kinds || []).map((k: any) => (
            <li key={k.when}><span className="wb-kind-n">{n(k.count)}</span> <code>{k.when}</code><Samples samples={k.samples} /></li>
          ))}</ul>
        </Residue>
        <Residue label="refused" count={s.refused.count}>
          <ul>{s.refused.groups.map((g: any, i: number) => (
            <li key={i}><span className="wb-kind-n">{n(g.count)}</span> {g.why} <span className="muted small">{(g.objects || []).slice(0, 3).join(", ")}</span></li>
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
            <li key={i}>only {g.kinds.join(", ")}: {n(g.objects)} objects <span className="muted small">{(g.samples || []).join(", ")}</span></li>
          ))}</ul>
        </Residue>
        <Residue label="possible merges: two things under one key" count={s.merges.count}>
          <ul>{s.merges.fields.map((g: any, i: number) => (
            <li key={i}><code>{g.field}</code> given twice: {n(g.objects)} objects <span className="muted small">{(g.samples || []).join(", ")}</span></li>
          ))}</ul>
        </Residue>
      </ul>

      {c && (
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
      )}

      {Object.keys(r.lifecycles || {}).length > 0 && <h3 className="small">Lifecycles</h3>}
      <div className="wb-dists">
        {Object.entries(r.lifecycles || {}).map(([f, l]) => <Lifecycle key={f} field={f} l={l} />)}
      </div>

      <h3 className="small">Its fields, across the objects</h3>
      {r.fields.length === 0 ? <p className="muted">No fields yet (step 3).</p> : (
        <div className="wb-dists">{r.fields.map((f: any) => <Distribution key={f.field} f={f} />)}</div>
      )}

      <h3 className="small">One object's timeline</h3>
      <div className="wb-row">
        <input className="wb-grow mono" list="wb-objects" value={key} onChange={(e) => setKey(e.target.value)} aria-label="An object's key"
          placeholder={r.objects.sample?.[0] || "an object's key"} onKeyDown={(e) => { if (e.key === "Enter") onItem(key.trim()); }} />
        <datalist id="wb-objects">{(r.objects.sample || []).map((k: string) => <option key={k} value={k} />)}</datalist>
        <button type="button" disabled={!key.trim()} onClick={() => onItem(key.trim())}>Show its timeline</button>
      </div>
      {r.objects.sample?.length > 0 && !item && (
        <p className="small muted">For example: {r.objects.sample.slice(0, 3).map((k: string) => (
          <button key={k} type="button" className="ghost mono" onClick={() => onItem(k)}>{k}</button>
        ))}</p>
      )}
      {r.timeline && <Timeline t={r.timeline} />}
    </div>
  );
}
