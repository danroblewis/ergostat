import { lazy, Suspense, useMemo } from "react";
import { dur } from "../../../lib/format";
import type { Panel } from "../../../lib/query";
import { Chart } from "../../charts/Chart";
import { ProjectionStates } from "../../charts/ProjectionStates";
import { PanelFrame } from "../../charts/PanelView";
import { Plot } from "../../charts/Plot";
import { QueryPanel } from "../../charts/QueryPanel";
import { useDetail } from "../../Detail";
import { GoalDetail } from "../../GoalDetail";
import { ALL_COLUMNS, PANEL_COLUMNS, GoalsTable } from "../../GoalsTable";
import type { GoalColumn } from "../../goals";
import { ItemsTable } from "../../items";
import { Markdown } from "../../Markdown";
import { Async, Loading } from "../../ui";
import { ancillaryMark, scopedBy } from "../../../lib/scoped";
import { useDashboards } from "../../../state/dashboards";
import type { PanelBodyProps, PanelDef, PanelKind } from "../types";
import { usePanelApi } from "../usePanelApi";

/* Each kind of panel a dashboard may hold, by the name the model's `dashboards:` uses (spec/dashboards.py KINDS), each
   asking its own endpoint with exactly the parameters the panel declares. */

const DiagramPanel = lazy(() => import("../../diagram/DiagramPanel"));   // only when a dashboard has one: it brings ELK

/** The parameters a panel sends its endpoint: all but its words, its size and the page's own id. */
export function paramsOf(def: PanelDef, ...keys: string[]): Record<string, unknown> {
  return Object.fromEntries(keys.filter((k) => def[k] != null).map((k) => [k, def[k]]));
}
const listOf = (v: unknown): string[] | null =>
  Array.isArray(v) ? v.map(String) : typeof v === "string" && v ? v.split(",").map((x) => x.trim()).filter(Boolean) : null;

/** A query panel's declaration as the query engine's own Panel (lib/query.ts). */
export const asQueryPanel = (def: PanelDef): Panel => ({
  id: def.id || "", title: def.title || "", note: def.note, size: def.size, tall: def.tall, fit: def.fit, form: def.form || "line",
  queries: def.queries || [], display: def.display, options: def.options, layout: def.layout,
});

function NoteBody({ def }: PanelBodyProps) {
  return <div className="panel-text"><Markdown source={String(def.text || "")} /></div>;
}

/** The columns a goals panel shows: `columns` names them (or `all`), else the panel's few. */
export function goalColumns(v: unknown): GoalColumn[] {
  const asked = listOf(v);
  if (!asked) return PANEL_COLUMNS;
  if (asked.includes("all")) return ALL_COLUMNS;
  const known = ALL_COLUMNS.filter((c) => asked.includes(c));
  return known.length ? known : PANEL_COLUMNS;
}

/** Goals: each goal's row. `columns` (names, or `all`); `system`: the goals that system contains, an ancillary one
 *  greyer; a page may hand it `onOpen` (a click on a goal: else its detail opens beside the page) and `selected` (the
 *  goal shown as chosen). */
function GoalsBody({ def, every, refreshKey }: PanelBodyProps) {
  const loops = usePanelApi<Record<string, any>>("loops", { perf: 1 }, every, refreshKey);
  const s = scopedBy(useDashboards().table, def.system);
  const asked = listOf(def.goals);
  const detail = useDetail();
  const open = typeof def.onOpen === "function" ? def.onOpen as (name: string) => void
    : (name: string) => detail.open(`goal:${name}`, <GoalDetail key={name} name={name} />);
  return (
    <div className="panel-table">
      <Async state={loops}>
        {(data) => <GoalsTable loops={data} columns={goalColumns(def.columns)} caption={def.title || "Goals"}
          only={s ? Object.keys(data).filter((g) => s.has("goals", g) && (!asked || asked.includes(g))) : asked}
          mark={(g) => ancillaryMark(s, "goals", g)} label={s ? (g) => s.label("goals", g) : undefined} selected={def.selected ?? null} onOpen={open} />}
      </Async>
    </div>
  );
}

/** A chart of stocks and flows: `refs`, or with none a system's (`system`: the stocks and flows spec/scope.py says it
 *  contains, at most 8). */
function ChartBody({ def, every, refreshKey }: PanelBodyProps) {
  const own = listOf(def.refs);
  const sc = usePanelApi<any>(!own && typeof def.system === "string" ? "scope" : null, {}, null);
  const parts = sc.data?.systems?.[def.system]?.contains;
  const refs = own || (parts ? [...(parts.stocks || []).map((r: any) => `stock.${r.name}`),
    ...(parts.flows || []).map((r: any) => `flow.${r.name}`)].slice(0, 8) : null);
  const got = usePanelApi<any>(refs?.length ? "series" : null, { ...paramsOf(def, "points", "replay", "fan"), refs }, every, refreshKey);
  const d = got.data;
  if (refs && !refs.length) return <p className="muted">{def.system || "The top level"} has no stocks or flows of its own.</p>;
  if (!d) return got.error ? <p className="note lvl-error">{got.error.message}</p> : <Loading />;
  const series = (d.series || []).map((s: any) => ({ label: `${s.name}${s.unit ? ` (${s.unit}${s.per ? `/${s.per}` : ""})` : ""}`, values: s.values }));
  const units = new Set((d.series || []).map((s: any) => (s.per ? `/${s.per === "hour" ? "h" : s.per}` : s.unit || "")));
  if (!series.length) return <p className="muted">Nothing of these in the model: {refs?.join(", ")}.</p>;
  if (!series.some((s: any) => s.values.some((v: number | null) => v != null))) return <p className="muted">No readings of these in the window.</p>;
  return (
    <div className="panel-plot-col">
      <Plot times={d.times} series={series} kind="line" unit={units.size === 1 ? [...units][0] as string : ""} legend={series.length > 1} />
    </div>
  );
}

function ItemsBody({ def, every, refreshKey }: PanelBodyProps) {
  const got = usePanelApi<any>("items", { shown: 1, n: 25, ...paramsOf(def, "projection", "state", "where", "moved", "moved_since", "moved_until", "through", "followed", "search", "n") }, every, refreshKey);
  return (
    <div className="panel-table">
      <Async state={got}>
        {(d) => {
          const k = (d.projections || []).find((x: any) => x.name === def.projection);
          const its = (d.items || []).filter((i: any) => !def.projection || i.projection === def.projection);
          return its.length ? <ItemsTable items={its} show={k?.show || []} caption={def.title || `${def.projection} items`} />
            : <p className="muted">No items{def.state ? ` in ${def.state}` : ""}.</p>;
        }}
      </Async>
    </div>
  );
}

function StatesBody({ def, every, refreshKey }: PanelBodyProps) {
  const flow = usePanelApi<any>("items-flow", paramsOf(def, "projection", "points"), every, refreshKey);
  const fp = usePanelApi<any>(def.projection ? `projections/${encodeURIComponent(def.projection)}` : null, {}, every, refreshKey);
  return <ProjectionStates flow={flow.data} fp={fp.data} all={false} />;
}

function CycleTimeBody({ def, every, refreshKey }: PanelBodyProps) {
  const flow = usePanelApi<any>("items-flow", paramsOf(def, "projection", "points"), every, refreshKey);
  const d = flow.data;
  const since = flow.data?.since, until = flow.data?.until;
  const options = useMemo(() => ({                      // dots over the window, however few finished in it
    series: [{}, { label: "took", stroke: "#3b6fd4", fill: "#3b6fd4", paths: () => null, points: { show: true, size: 5 } }],
    scales: since != null && until != null ? { x: { time: true, range: () => [since, until] as [number, number] } } : {},
    axes: [{}, { size: 56, values: (_u: unknown, vs: number[]) => vs.map((v) => dur(v)) }],
  }), [since, until]);
  if (!d) return flow.error ? <p className="note lvl-error">{flow.error.message}</p> : <Loading />;
  if (!d.finished?.length) return <p className="muted">No {def.projection} finished in the window.</p>;
  return (
    <div>
      <Chart times={d.finished.map((f: any) => f.time)} series={[{ label: "took", values: d.finished.map((f: any) => f.took) }]}
        height={160} options={options as any} />
      <p className="muted small">{d.finished_total} finished{d.median != null ? `; the median took ${dur(d.median)}` : ""}.</p>
    </div>
  );
}

function NotDrawn({ def }: PanelBodyProps) {
  return <p className="note">A {def.panel} panel is not drawn on this page yet; its answer is at /api/dashboard.</p>;
}

/** Every kind of panel, by its name in `dashboards:`. */
export const CORE: Record<string, PanelKind> = {
  query: { label: "Query (PromQL or SQL)", needs: "queries", Frame: ({ def, every, refreshKey, tools }) => (
    <QueryPanel panel={asQueryPanel(def)} every={every} refreshKey={refreshKey} tools={tools} />) },
  diagram: { label: "Diagram", needs: "address", Frame: ({ def, tools }) => (
    <Suspense fallback={<PanelFrame panel={asQueryPanel(def)} tools={tools} className="panel-form-diagram"><Loading /></PanelFrame>}>
      <DiagramPanel def={def} tools={tools} />
    </Suspense>) },
  note: { label: "Note", needs: "text", Body: NoteBody },
  goals: { label: "Goals", Body: GoalsBody },
  chart: { label: "Chart of stocks and flows", Body: ChartBody },
  items: { label: "Items", needs: "projection", Body: ItemsBody },
  states: { label: "A projection's states over time", needs: "projection", Body: StatesBody },
  "cycle-time": { label: "A projection's cycle time", needs: "projection", Body: CycleTimeBody },
  scope: { label: "A goal's scope", needs: "goal", Body: NotDrawn },
  "items-graph": { label: "Items graph", Body: NotDrawn },
  timeline: { label: "Timeline", Body: NotDrawn },
};
