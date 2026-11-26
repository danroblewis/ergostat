import { type ReactNode } from "react";
import { fmt } from "../../lib/format";
import { named, normalizeForm, recent, type Panel, type Result } from "../../lib/query";
import { Plot, valueText, type PlotSeries } from "./Plot";

/* One panel, on any page: its head (title, note, and the tools a page puts there) and its body as its form draws the answer. Ported
   forms: line (and area, stacked, step), bar over time, stat, table. The other plot families say they are not ported. */

const COLOURS = ["var(--c1, #3b6fd4)", "var(--c2, #d4823b)", "var(--c3, #3ba86b)", "var(--c4, #a03bd4)", "var(--c5, #d43b5c)", "var(--c6, #2a9db0)", "var(--c7, #8a8a2a)", "var(--c8, #b04a8a)"];
const last = (v: (number | null)[]) => { for (let i = v.length - 1; i >= 0; i--) if (v[i] != null) return v[i]; return null; };
const most = (v: (number | null)[]) => v.reduce<number | null>((m, x) => (x != null && (m == null || x > m) ? x : m), null);

interface Props {
  panel: Panel;
  /** its queries' answers (``usePanelResults``), undefined until the first comes */
  results: Result[] | undefined;
  loading?: boolean;
  /** the request's own failure (each query's is in its result) */
  error?: Error | null;
  /** drawn in the panel's head, after its title: a dashboard's edit buttons, say */
  tools?: ReactNode;
}

/** The series of every result on one time axis (the first that has times): what a plot over time draws. */
function onTime(results: Result[]): { times: number[]; series: PlotSeries[] } {
  const base = results.find((r) => r.times?.length)?.times || [];
  const series: PlotSeries[] = [];
  for (const r of results) for (const s of r.series || []) {
    if (!r.times || r.times === base || r.times.length === base.length) { series.push({ label: s.name || r.id, values: s.values }); continue; }
    const at = new Map(r.times.map((t, i) => [t, s.values[i]]));
    series.push({ label: s.name || r.id, values: base.map((t) => at.get(t) ?? null) });
  }
  return { times: base, series };
}

export function PanelView({ panel, results, loading, error, tools }: Props) {
  const { form, options } = normalizeForm(panel);
  const d = panel.display || {};
  const unit: string = d.unit ?? results?.find((r) => r.unit)?.unit ?? "";
  const got = results ? named(panel, results) : undefined;
  const errors = (got || []).filter((r) => r.error);
  const fine = (got || []).filter((r) => !r.error);

  let body: ReactNode;
  if (!got) body = <p className="muted">{loading ? "Loading…" : "No answer yet."}</p>;
  else if (!fine.length && errors.length) body = null;
  else if (form === "line" || (form === "bar" && !fine.some((r) => r.shape && r.shape !== "series"))) {
    const { times, series } = onTime(fine);
    const legendValues: string[] = d.legend_values || ["last"];
    body = !times.length || !series.length ? <p className="muted">Nothing recorded in this window.</p> : (
      <div className="panel-plot-col">
        <Plot times={times} series={series} kind={form === "bar" ? "bar" : "line"} fill={options.fill === "area"}
          stacked={options.stack === "stacked"} step={options.style === "step-after"} unit={unit} yMin={d.y?.min} />
        {(series.length > 1 || d.legend) && (
          <ul className="dash-legend" style={{ display: "flex", flexWrap: "wrap", gap: "0 1em", listStyle: "none", margin: 0, padding: 0, fontSize: "var(--text-sm)" }}>
            {series.map((s, i) => (
              <li key={i}>
                <span aria-hidden="true" style={{ color: COLOURS[i % COLOURS.length] }}>■</span> {s.label}{" "}
                <span className="muted">{legendValues.map((w) => `${w} ${valueText(w === "max" ? most(s.values) : last(s.values), unit)}`).join(", ")}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    );
  } else if (form === "stat") {
    const { series } = onTime(fine);
    body = (
      <div className="panel-stats" data-count={series.length}>
        {series.map((s, i) => {
          const values = d.recent ? recent(s.values, d.recent) : s.values;
          const v = d.whole ? fineWhole(s.values) : last(values);
          return (
            <div className="panel-stat" key={i}>
              {series.length > 1 && <div className="panel-stat-name"><span>{s.label}</span></div>}
              <div className="panel-stat-num">{v == null ? "–" : d.decimals != null && unit !== "s" ? `${v.toFixed(d.decimals)}${unit ? (unit.startsWith("/") ? "" : " ") + unit : ""}` : valueText(v, unit)}</div>
            </div>
          );
        })}
        {!series.length && <p className="muted">Nothing recorded in this window.</p>}
      </div>
    );
  } else if (form === "table") body = <ResultTable results={fine} unit={unit} />;
  else body = <p className="note">The {form} plot is not drawn on this page yet.</p>;

  return (
    <PanelFrame panel={panel} tools={tools} className={`panel-form-${form}`}>
      {error && <p className="note lvl-error" role="alert" style={{ margin: 0, fontSize: "var(--text-sm)" }}>{error.message}</p>}
      {errors.map((r) => <p key={r.id} className="note lvl-error" role="alert" style={{ margin: 0, fontSize: "var(--text-sm)" }}>{r.error}</p>)}
      {body}
    </PanelFrame>
  );
}

/** A panel's frame, whatever it draws: its size, its head (title, note, the tools a page puts there) and its body. */
export function PanelFrame({ panel, tools, className, children }: { panel: Panel; tools?: ReactNode; className?: string; children: ReactNode }) {
  return (
    <article className={`panel panel-${panel.size || "m"}${className ? ` ${className}` : ""}${panel.tall ? " panel-tall" : ""}${(panel as any).fit ? " panel-fit" : ""}`} data-panel={panel.id} aria-label={panel.title}>
      <header className="panel-head">
        <div className="panel-names">
          <h3 className="panel-title" title={panel.title}>{panel.title}</h3>
          {panel.note && <p className="panel-note">{panel.note}</p>}
        </div>
        {tools}
      </header>
      <div className="panel-body">{children}</div>
    </article>
  );
}

/** A number over the whole window: the median of the values read (a whole-window stat). */
function fineWhole(values: (number | null)[]): number | null {
  const v = values.filter((x): x is number => x != null).sort((a, b) => a - b);
  return v.length ? v[Math.floor(v.length / 2)] : null;
}

/** A table: a result's own columns and rows when it has them (SQL), else each series' last, least and most. */
function ResultTable({ results, unit }: { results: Result[]; unit: string }) {
  const grid = results.find((r) => Array.isArray(r.columns) && Array.isArray(r.rows));
  if (grid) return (
    <div className="panel-table">
      <table>
        <thead><tr>{grid.columns!.map((c) => <th key={c}>{c}</th>)}</tr></thead>
        <tbody>{grid.rows!.map((row, i) => <tr key={i}>{row.map((x, j) => <td key={j}>{typeof x === "number" ? fmt(x) : String(x ?? "")}</td>)}</tr>)}</tbody>
      </table>
    </div>
  );
  const { series } = onTime(results);
  return (
    <div className="panel-table">
      <table>
        <thead><tr><th>Series</th><th>Last</th><th>Min</th><th>Max</th></tr></thead>
        <tbody>
          {series.map((s, i) => {
            const v = s.values.filter((x): x is number => x != null);
            return (
              <tr key={i}>
                <td className="panel-table-name">{s.label}</td>
                <td>{valueText(last(s.values), unit)}</td>
                <td>{valueText(v.length ? Math.min(...v) : null, unit)}</td>
                <td>{valueText(v.length ? Math.max(...v) : null, unit)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
