import { useMemo } from "react";
import { dur, fmt, stamp } from "../../lib/format";
import { Chart } from "./Chart";

/* One item's own history as charts (the item-state-timeline, item-field-chart and item-events-histogram panels): its
   states as a band over time, each numeric field's values at each change, and its events per time bucket by kind. Each
   is worked out from the item's answer (GET /api/items/ID: its moves, its record, its fields' history) and draws
   nothing when there is nothing to show (`stateSpans`, `numericSeries`, `eventBuckets` say whether there is). */

const COLOURS = ["var(--c1, #3b6fd4)", "var(--c2, #d4823b)", "var(--c3, #3ba86b)", "var(--c4, #a03bd4)", "var(--c5, #d43b5c)",
  "var(--c6, #2a9db0)", "var(--c7, #8a8a2a)", "var(--c8, #b04a8a)"];
const colour = (i: number) => COLOURS[((i % COLOURS.length) + COLOURS.length) % COLOURS.length];
const NUMERIC = new Set(["number", "integer", "duration"]);

export interface Span { state: string; from: number; to: number }

/** Its states' spans, oldest first, from entered to left (the last to `now`, or to its last event when it is in a final
 *  state); from its moves, else from its `state` field's changes. Empty: it has no states over time to show. */
export function stateSpans(d: any, now: number): Span[] {
  const steps: { time: number; to: string }[] = (d?.moves || []).length
    ? d.moves.map((m: any) => ({ time: m.time, to: String(m.to) }))
    : (d?.history?.state || []).filter((c: any) => c.after != null && c.op !== "refused")
      .map((c: any) => ({ time: c.time, to: typeof c.after === "string" ? c.after : JSON.stringify(c.after) }));
  if (!steps.length) return [];
  const final: string[] = d?.projection_of?.final || [];
  const last = steps[steps.length - 1];
  const end = final.includes(last.to) ? Math.max(last.time, d.last ?? last.time) : Math.max(now, last.time);
  return steps.map((s, i) => ({ state: s.to, from: s.time, to: i + 1 < steps.length ? steps[i + 1].time : end }));
}

/** Its states in the projection's order (any it reached that is not declared, after them). */
function stateOrder(d: any, spans: Span[]): string[] {
  const declared: string[] = d?.projection_of?.states || [];
  const seen = [...new Set(spans.map((s) => s.state))];
  return [...declared.filter((s) => seen.includes(s)), ...seen.filter((s) => !declared.includes(s))];
}

/** Its states as one band over time, each value its colour, and the time spent in each. */
export function StateTimeline({ d, now }: { d: any; now: number }) {
  const spans = stateSpans(d, now);
  if (!spans.length) return null;
  const order = stateOrder(d, spans);
  const declared: string[] = d?.projection_of?.states || [];
  const col = (s: string) => colour(declared.includes(s) ? declared.indexOf(s) : declared.length + order.indexOf(s));
  const t0 = spans[0].from, t1 = Math.max(spans[spans.length - 1].to, t0 + 1), whole = t1 - t0;
  const spent = Object.fromEntries(order.map((s) => [s, spans.filter((x) => x.state === s).reduce((a, x) => a + (x.to - x.from), 0)]));
  return (
    <div className="item-timeline">
      <div className="item-timeline-band" role="img" aria-label={`Its states over time: ${spans.map((s) => s.state).join(", ")}`}>
        {spans.map((s, i) => (
          <span key={`${s.from}|${i}`} className="item-timeline-span" data-state={s.state}
            title={`${s.state}: ${stamp(s.from)} for ${dur(s.to - s.from)}`}
            style={{ left: `${(100 * (s.from - t0)) / whole}%`, width: `${Math.max(0.3, (100 * (s.to - s.from)) / whole)}%`, background: col(s.state) }} />
        ))}
      </div>
      <div className="item-timeline-axis muted small"><span>{stamp(t0)}</span><span>{stamp(t1)}</span></div>
      <table className="item-timeline-spent" aria-label="Time in each state">
        <tbody>
          {order.map((s) => (
            <tr key={s} data-state={s}>
              <th scope="row"><span className="item-swatch" style={{ background: col(s) }} />{s}</th>
              <td className="num">{dur(spent[s])}</td>
              <td className="num muted">{Math.round((100 * spent[s]) / whole)}%</td>
              <td className="num muted">{spans.filter((x) => x.state === s).length}×</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** The fields worth asking the history of: declared numeric (number, integer, duration) or a number now, changed at
 *  least twice (`field`: that one alone, whatever it is). */
export function numericCandidates(d: any, field?: string): string[] {
  const changes: Record<string, number> = d?.changes || {};
  const declared: Record<string, any> = d?.projection_of?.fields || {};
  const fields: Record<string, unknown> = d?.fields || {};
  return Object.keys(changes).filter((f) => f && (field ? f === field : true) && changes[f] >= 2
    && (field || NUMERIC.has(declared[f]?.type) || typeof fields[f] === "number"));
}

const asNumber = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);

/** Each candidate's values at each change, oldest first: those with at least two numbers. */
export function numericSeries(d: any, fields: string[]): { field: string; times: number[]; values: (number | null)[] }[] {
  return fields.map((f) => {
    const cs = (d?.history?.[f] || []).filter((c: any) => c.op !== "refused" && c.path === `/${f.replace(/~/g, "~0").replace(/\//g, "~1")}`);
    return { field: f, times: cs.map((c: any) => c.time), values: cs.map((c: any) => asNumber(c.after)) };
  }).filter((s) => s.values.filter((v) => v != null).length >= 2);
}

/** A small line chart of each numeric field's values, a point at each change. */
export function FieldCharts({ series }: { series: { field: string; times: number[]; values: (number | null)[] }[] }) {
  if (!series.length) return null;
  return (
    <div className="item-field-charts">
      {series.map((s) => (
        <figure key={s.field} className="item-field-chart" data-field={s.field}>
          <figcaption><strong>{s.field}</strong> <span className="muted small">{s.values.length} changes, now {fmt(s.values[s.values.length - 1])}</span></figcaption>
          <FieldChart s={s} />
        </figure>
      ))}
    </div>
  );
}

function FieldChart({ s }: { s: { field: string; times: number[]; values: (number | null)[] } }) {
  const series = useMemo(() => [{ label: s.field, values: s.values }], [s.field, s.values]);
  const options = useMemo(() => ({ series: [{}, { label: s.field, stroke: colour(0), width: 1.5, points: { show: true, size: 5 } }] } as any), [s.field]);
  return <Chart times={s.times} series={series} height={120} options={options} />;
}

export interface Buckets { start: number; size: number; kinds: string[]; counts: number[][] }

/** Its events (its record, the latest 500) counted per time bucket (about 30 from its first to its last), by kind of
 *  event: the projection's kind that took it, else its type. Null: no events. */
export function eventBuckets(d: any, n = 30): Buckets | null {
  const evs: any[] = (d?.record || []).filter((e: any) => typeof e.time === "number");
  if (!evs.length) return null;
  const lo = Math.min(...evs.map((e) => e.time)), hi = Math.max(...evs.map((e) => e.time));
  const size = Math.max(1, (hi - lo) / n), m = Math.max(1, Math.ceil((hi - lo) / size + 1e-9));
  const kindOf = (e: any) => String(e.kind || e.type || "event");
  const total: Record<string, number> = {};
  evs.forEach((e) => { total[kindOf(e)] = (total[kindOf(e)] || 0) + 1; });
  const kinds = Object.keys(total).sort((a, b) => total[b] - total[a] || a.localeCompare(b));
  const counts = kinds.map(() => new Array(m).fill(0));
  evs.forEach((e) => { counts[kinds.indexOf(kindOf(e))][Math.min(m - 1, Math.floor((e.time - lo) / size))] += 1; });
  return { start: lo, size, kinds, counts };
}

/** Its events per time bucket as stacked bars, a colour each kind, with each kind's count. */
export function EventsHistogram({ b }: { b: Buckets | null }) {
  if (!b) return null;
  const m = b.counts[0].length;
  const stack = Array.from({ length: m }, (_, i) => b.counts.reduce((a, c) => a + c[i], 0));
  const top = Math.max(1, ...stack);
  const W = 600, H = 120, w = W / m;
  return (
    <div className="item-histogram">
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" role="img" aria-label={`Its events per ${dur(b.size)}, by kind`}>
        {Array.from({ length: m }, (_, i) => {
          let y = H;
          return b.kinds.map((k, j) => {
            const n = b.counts[j][i];
            if (!n) return null;
            const h = (H * n) / top;
            y -= h;
            return <rect key={`${i}|${k}`} data-kind={k} x={i * w + 0.5} y={y} width={Math.max(1, w - 1)} height={h} fill={colour(j)}>
              <title>{`${k}: ${n} from ${stamp(b.start + i * b.size)}`}</title></rect>;
          });
        })}
      </svg>
      <div className="item-timeline-axis muted small"><span>{stamp(b.start)}</span><span>{top} at most per {dur(b.size)}</span>
        <span>{stamp(b.start + m * b.size)}</span></div>
      <ul className="item-histogram-kinds" aria-label="Its events by kind">
        {b.kinds.map((k, j) => (
          <li key={k} data-kind={k}><span className="item-swatch" style={{ background: colour(j) }} />{k}{" "}
            <span className="muted">{b.counts[j].reduce((a, x) => a + x, 0)}</span></li>
        ))}
      </ul>
    </div>
  );
}
