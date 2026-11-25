import { fmt } from "../../lib/format";

/* A guide frame's behaviour over time (guide.js guidePlot): integrated here from the frame's equations (Euler), drawn
   as a small SVG with its lines labelled at their ends, never on each other. */

type Terms = [number, string[]][];
interface Run {
  label?: string;
  stocks: Record<string, number>;
  inputs: Record<string, [number, number][]>;
  aux: Record<string, Terms>;
  flows: Record<string, { terms: Terms; to?: string; from?: string }>;
  series: { of: string; dash?: boolean; label?: string }[];
}
export interface GuidePlot {
  runs: Run[];
  until: number;
  dt: number;
  x: string;
  y: string;
  band?: [number, number, string];
}

function simulate(run: Run, until: number, dt: number) {
  const vals = { ...run.stocks };
  const input = (name: string, t: number) => {
    let v = 0;
    for (const [t0, x] of run.inputs[name]) if (t >= t0 - 1e-9) v = x;
    return v;
  };
  const sum = (terms: Terms, env: Record<string, number>) =>
    terms.reduce((a, [c, vars]) => a + c * vars.reduce((x, v) => x * (env[v] ?? 0), 1), 0);
  const out: Record<string, [number, number][]> = Object.fromEntries(run.series.map((x) => [x.of, []]));
  for (let n = 0, t = 0; t <= until + 1e-9; n++, t = n * dt) {
    const env: Record<string, number> = { ...vals };
    for (const k of Object.keys(run.inputs)) env[k] = input(k, t);
    for (const [k, terms] of Object.entries(run.aux)) env[k] = sum(terms, env);
    for (const x of run.series) out[x.of].push([t, env[x.of]]);
    for (const f of Object.values(run.flows)) { // a flow runs one way: never below 0
      const rate = Math.max(0, sum(f.terms, env));
      if (f.to) vals[f.to] += rate * dt;
      if (f.from) vals[f.from] -= rate * dt;
    }
  }
  return out;
}

function nice(x: number) { // a round number at or above x
  if (x <= 0) return 1;
  const p = 10 ** Math.floor(Math.log10(x));
  const m = x / p;
  return (m <= 1 ? 1 : m <= 2 ? 2 : m <= 2.5 ? 2.5 : m <= 5 ? 5 : 10) * p;
}

export function Plot({ plot }: { plot: GuidePlot }) {
  const W = 320, H = 190, L = 44, R = 78, T = 14, B = 34;
  const lines: { pts: [number, number][]; dash?: boolean; label?: string }[] = [];
  for (const run of plot.runs) {
    const got = simulate(run, plot.until, plot.dt);
    for (const x of run.series) lines.push({ pts: got[x.of], dash: x.dash, label: x.label || run.label });
  }
  const top = nice(Math.max(...lines.flatMap((l) => l.pts.map((p) => p[1]))) * 1.05);
  const X = (t: number) => L + (t / plot.until) * (W - L - R);
  const Y = (v: number) => H - B - (Math.max(0, Math.min(v, top)) / top) * (H - T - B);
  const ends: number[] = [];
  const labels = lines.map((l) => {
    if (!l.label) return null;
    const [t, v] = l.pts[l.pts.length - 1];
    let y = Y(v) + 4;
    while (ends.some((e) => Math.abs(e - y) < 12)) y += 12;
    ends.push(y);
    return { x: X(t) + 5, y, text: l.label };
  });
  const mid = (T + H - B) / 2;
  return (
    <div className="g-plotbox">
      <svg className="g-plot" viewBox={`0 0 ${W} ${H}`} width={W} height={H} role="img" aria-label={`${plot.y} over ${plot.x}`}>
        {plot.band && (
          <>
            <rect className="g-band" x={X(plot.band[0])} y={T} width={X(plot.band[1]) - X(plot.band[0])} height={H - T - B} />
            <text className="g-tick" x={(X(plot.band[0]) + X(plot.band[1])) / 2} y={T + 12} textAnchor="middle">{plot.band[2]}</text>
          </>
        )}
        <path className="g-axis" d={`M${L},${T} V${H - B} H${W - R}`} />
        <text className="g-tick" x={L - 6} y={Y(0) + 4} textAnchor="end">0</text>
        <text className="g-tick" x={L - 6} y={Y(top) + 4} textAnchor="end">{fmt(top)}</text>
        <text className="g-tick" x={X(plot.until)} y={H - B + 14} textAnchor="middle">{String(plot.until)}</text>
        <text className="g-tick" x={L} y={H - B + 14} textAnchor="middle">0</text>
        <text className="g-name" x={(L + W - R) / 2} y={H - 6} textAnchor="middle">{plot.x}</text>
        <text className="g-name" x={12} y={mid} textAnchor="middle" transform={`rotate(-90 12 ${mid})`}>{plot.y}</text>
        {lines.map((l, k) => (
          <path
            key={k}
            className={"g-line" + (l.dash ? " dash" : "")}
            d={l.pts.map(([t, v], j) => `${j ? "L" : "M"}${X(t).toFixed(1)},${Y(v).toFixed(1)}`).join("")}
          />
        ))}
        {labels.map((x, k) => x && <text key={k} className="g-tick g-label" x={x.x} y={x.y}>{x.text}</text>)}
      </svg>
    </div>
  );
}
