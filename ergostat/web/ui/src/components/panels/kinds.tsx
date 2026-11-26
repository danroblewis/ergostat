import { lazy, Suspense, useMemo } from "react";
import { dur } from "../../lib/format";
import type { Panel } from "../../lib/query";
import { Chart } from "../charts/Chart";
import { KindStates } from "../charts/KindStates";
import { PanelFrame } from "../charts/PanelView";
import { Plot } from "../charts/Plot";
import { QueryPanel } from "../charts/QueryPanel";
import { useDetail } from "../Detail";
import { GoalDetail } from "../GoalDetail";
import { PANEL_COLUMNS, GoalsTable } from "../GoalsTable";
import { ItemsTable } from "../items";
import { Markdown } from "../Markdown";
import { Async, Loading } from "../ui";
import type { PanelBodyProps, PanelDef, PanelKind } from "./types";
import { usePanelApi } from "./usePanelApi";

/* Each kind of panel a dashboard may hold, by the name the model's `dashboards:` uses (spec/dashboards.py KINDS), each
   asking its own endpoint with exactly the parameters the panel declares. */

const DiagramPanel = lazy(() => import("../diagram/DiagramPanel"));   // only when a dashboard has one: it brings ELK

/** The parameters a panel sends its endpoint: all but its words, its size and the page's own id. */
export function paramsOf(def: PanelDef, ...keys: string[]): Record<string, unknown> {
  return Object.fromEntries(keys.filter((k) => def[k] != null).map((k) => [k, def[k]]));
}
const listOf = (v: unknown): string[] | null =>
  Array.isArray(v) ? v.map(String) : typeof v === "string" && v ? v.split(",").map((x) => x.trim()).filter(Boolean) : null;

/** A query panel's declaration as the query engine's own Panel (lib/query.ts). */
export const asQueryPanel = (def: PanelDef): Panel => ({
  id: def.id || "", title: def.title || "", note: def.note, size: def.size, tall: def.tall, form: def.form || "line",
  queries: def.queries || [], display: def.display, options: def.options, layout: def.layout,
});

function NoteBody({ def }: PanelBodyProps) {
  return <div className="panel-text"><Markdown source={String(def.text || "")} /></div>;
}

function GoalsBody({ def, every, refreshKey }: PanelBodyProps) {
  const loops = usePanelApi<Record<string, any>>("loops", { perf: 1 }, every, refreshKey);
  const detail = useDetail();
  return (
    <div className="panel-table">
      <Async state={loops}>
        {(data) => <GoalsTable loops={data} only={listOf(def.goals)} columns={PANEL_COLUMNS} caption={def.title || "Goals"}
          onOpen={(name) => detail.open(`goal:${name}`, <GoalDetail key={name} name={name} />)} />}
      </Async>
    </div>
  );
}

function ChartBody({ def, every, refreshKey }: PanelBodyProps) {
  const got = usePanelApi<any>("series", paramsOf(def, "refs", "points", "replay", "fan"), every, refreshKey);
  const d = got.data;
  if (!d) return got.error ? <p className="note lvl-error">{got.error.message}</p> : <Loading />;
  const series = (d.series || []).map((s: any) => ({ label: `${s.name}${s.unit ? ` (${s.unit}${s.per ? `/${s.per}` : ""})` : ""}`, values: s.values }));
  const units = new Set((d.series || []).map((s: any) => (s.per ? `/${s.per === "hour" ? "h" : s.per}` : s.unit || "")));
  if (!series.length) return <p className="muted">Nothing of these in the model: {listOf(def.refs)?.join(", ")}.</p>;
  if (!series.some((s: any) => s.values.some((v: number | null) => v != null))) return <p className="muted">No readings of these in the window.</p>;
  return (
    <div className="panel-plot-col">
      <Plot times={d.times} series={series} kind="line" unit={units.size === 1 ? [...units][0] as string : ""} legend={series.length > 1} />
    </div>
  );
}

function ItemsBody({ def, every, refreshKey }: PanelBodyProps) {
  const got = usePanelApi<any>("items", { shown: 1, n: 25, ...paramsOf(def, "kind", "state", "where", "moved", "moved_since", "moved_until", "through", "followed", "search", "n") }, every, refreshKey);
  return (
    <div className="panel-table">
      <Async state={got}>
        {(d) => {
          const k = (d.kinds || []).find((x: any) => x.name === def.kind);
          const its = (d.items || []).filter((i: any) => !def.kind || i.kind === def.kind);
          return its.length ? <ItemsTable items={its} show={k?.show || []} caption={def.title || `${def.kind} items`} />
            : <p className="muted">No items{def.state ? ` in ${def.state}` : ""}.</p>;
        }}
      </Async>
    </div>
  );
}

function StatesBody({ def, every, refreshKey }: PanelBodyProps) {
  const flow = usePanelApi<any>("items-flow", paramsOf(def, "kind", "points"), every, refreshKey);
  const fp = usePanelApi<any>(def.kind ? `kinds/${encodeURIComponent(def.kind)}` : null, {}, every, refreshKey);
  return <KindStates flow={flow.data} fp={fp.data} all={false} />;
}

function CycleTimeBody({ def, every, refreshKey }: PanelBodyProps) {
  const flow = usePanelApi<any>("items-flow", paramsOf(def, "kind", "points"), every, refreshKey);
  const d = flow.data;
  const since = flow.data?.since, until = flow.data?.until;
  const options = useMemo(() => ({                      // dots over the window, however few finished in it
    series: [{}, { label: "took", stroke: "#3b6fd4", fill: "#3b6fd4", paths: () => null, points: { show: true, size: 5 } }],
    scales: since != null && until != null ? { x: { time: true, range: () => [since, until] as [number, number] } } : {},
    axes: [{}, { size: 56, values: (_u: unknown, vs: number[]) => vs.map((v) => dur(v)) }],
  }), [since, until]);
  if (!d) return flow.error ? <p className="note lvl-error">{flow.error.message}</p> : <Loading />;
  if (!d.finished?.length) return <p className="muted">No {def.kind} finished in the window.</p>;
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
export const KINDS: Record<string, PanelKind> = {
  query: { label: "Query (PromQL or SQL)", needs: "queries", Frame: ({ def, every, refreshKey, tools }) => (
    <QueryPanel panel={asQueryPanel(def)} every={every} refreshKey={refreshKey} tools={tools} />) },
  diagram: { label: "Diagram", needs: "address", Frame: ({ def, tools }) => (
    <Suspense fallback={<PanelFrame panel={asQueryPanel(def)} tools={tools} className="panel-form-diagram"><Loading /></PanelFrame>}>
      <DiagramPanel def={def} tools={tools} />
    </Suspense>) },
  note: { label: "Note", needs: "text", Body: NoteBody },
  goals: { label: "Goals", Body: GoalsBody },
  chart: { label: "Chart of stocks and flows", needs: "refs", Body: ChartBody },
  items: { label: "Items", needs: "kind", Body: ItemsBody },
  states: { label: "A kind's states over time", needs: "kind", Body: StatesBody },
  "cycle-time": { label: "A kind's cycle time", needs: "kind", Body: CycleTimeBody },
  scope: { label: "A goal's scope", needs: "goal", Body: NotDrawn },
  "items-graph": { label: "Items graph", Body: NotDrawn },
  timeline: { label: "Timeline", Body: NotDrawn },
};
