import { useState, type ReactNode } from "react";
import { ancillaryMark, scopedBy } from "../../../lib/scoped";
import { useDashboards } from "../../../state/dashboards";
import { useTime } from "../../../state/time";
import { ProjectionStates } from "../../charts/ProjectionStates";
import {
  eventBuckets, EventsHistogram, FieldCharts, numericCandidates, numericSeries, StateTimeline, stateSpans,
} from "../../charts/ItemCharts";
import { PanelFrame } from "../../charts/PanelView";
import { FinishedNote, Pager } from "../../controls";
import {
  CHANGES_SHOWN, hasPath, hasRelations, ItemChanges, ItemEvents, ItemFields, ItemMoves, ItemPath, ItemRefused, ItemRelations,
  ItemSummary, ItemWhy, whySays,
} from "../../itemParts";
import { hiddenStates, ItemsTable, ProjectionBar } from "../../items";
import { EveryProjection, ProjectionModel, ProjectionsOverview, ProcessMapLink } from "../../projectionParts";
import { Code } from "../../Markdown";
import { Async, Empty, Loading } from "../../ui";
import { usePanelAnswer } from "../shared";
import type { PanelBodyProps, PanelDef, PanelKind } from "../types";
import { asQueryPanel } from "./core";

/* The items group's kinds of panel (each also declared in ergostat/spec/dashboards.py, its items block): the
   projections' overview, every projection's newest, a projection's states, model, definition and paged list, and each part of one item. Each
   asks its own endpoint with exactly its parameters, unless the page has asked the same (panels/shared.tsx).

   A page binds a panel to its address with keys of its own, never declared in the model: `onParams(changes)` (a list's
   page, sort, size and finished; an item's changes asked for, `history`), `page` (the list's page), `quiet` (a part
   with nothing to say is not drawn at all) and `folded` (a definition shown when asked). */

type FrameProps = PanelBodyProps & { tools?: ReactNode };
type Changes = Record<string, string | number | null>;

/** A panel of this group, framed as every panel is, under its own title or the projection's; scrolled within the grid's
 *  height, unless it fits what it shows. */
function Framed({ def, title, note, tools, children }: { def: PanelDef; title: string; note?: string; tools?: ReactNode; children: ReactNode }) {
  return (
    <PanelFrame panel={{ ...asQueryPanel(def), title: def.title || title, note: def.note || note }} tools={tools}
      className={`panel-kind-${def.panel}`}>
      {def.fit ? children : <div className="panel-table">{children}</div>}
    </PanelFrame>
  );
}

const pathOf = (head: string, name: unknown) => (name ? `${head}/${encodeURIComponent(String(name))}` : null);

// ---- projections

function ProjectionsFrame({ def, every, refreshKey, tools }: FrameProps) {
  const got = usePanelAnswer<any>("items-overview", {}, every, refreshKey, true);
  const s = scopedBy(useDashboards().table, def.system);      // a system's: those it contains, an ancillary one greyer
  const of = (d: any) => (s ? { ...d, projections: d.projections.filter((k: any) => s.has("projections", k.name)) } : d);
  return (
    <Framed def={def} title="Projections" tools={tools}>
      <Async state={got}>{(d) => <ProjectionsOverview d={of(d)} all={def.states === "all"}
        mark={(n) => ancillaryMark(s, "projections", n)} />}</Async>
    </Framed>
  );
}

/** What the items-by-projection panel asks GET /api/items. */
export const everyProjectionParams = (def: PanelDef) =>
  ({ per_projection: def.per_projection ?? 25, shown: 1, q: (def.q || "").trim() || undefined, finished: def.finished });

function EveryProjectionFrame({ def, every, refreshKey, tools }: FrameProps) {
  const got = usePanelAnswer<any>("items", everyProjectionParams(def), every, refreshKey);
  return (
    <Framed def={def} title="Every projection's items" tools={tools}>
      <Async state={got}>{(d) => <EveryProjection d={d} needle={(def.q || "").trim()} showFin={def.finished === "show"} />}</Async>
    </Framed>
  );
}

function ProjectionNowFrame({ def, every, refreshKey, tools }: FrameProps) {
  const flow = usePanelAnswer<any>(def.projection ? "items-flow" : null, { projection: def.projection, points: def.points ?? 60, draft: def.draft }, every, refreshKey);
  const fp = usePanelAnswer<any>(pathOf("projections", def.projection), { draft: def.draft }, every, refreshKey, true);
  return (
    <Framed def={def} title="Now" tools={tools}>
      {/* (a block, not the body's flex column: a projection's flow is sized as a flex item of a row) */}
      <div>{flow.error && !flow.data ? <p className="note lvl-error">{flow.error.message}</p> : <ProjectionStates flow={flow.data} fp={fp.data} all={def.states === "all"} />}</div>
      {def.projection && <div><ProcessMapLink projection={def.projection} /></div>}
    </Framed>
  );
}

function ProjectionModelFrame({ def, every, refreshKey, tools }: FrameProps) {
  const fp = usePanelAnswer<any>(pathOf("projections", def.projection), { draft: def.draft }, every, refreshKey, true);
  return (
    <Framed def={def} title="In the model" tools={tools}>
      <Async state={fp}>{(d) => <ProjectionModel fp={d} />}</Async>
    </Framed>
  );
}

function ProjectionDefinitionFrame({ def, every, refreshKey, tools }: FrameProps) {
  const fp = usePanelAnswer<any>(pathOf("projections", def.projection), { draft: def.draft }, every, refreshKey, true);
  const code = fp.data?.definition ? <Code code={JSON.stringify(fp.data.definition, null, 2)} lang="json" />
    : fp.error ? <p className="note lvl-error">{fp.error.message}</p> : <Loading />;
  return (
    <Framed def={def} title="Definition" tools={tools}>
      {def.folded ? <details className="projection-def"><summary>As the model defines it</summary>{code}</details> : code}
    </Framed>
  );
}

/** What the item-list panel asks GET /api/items: a page of one projection's, searched and sorted by the server. */
export function itemListParams(def: PanelDef): Record<string, unknown> {
  const n = def.n ?? 25, page = Math.max(1, def.page ?? 1);
  return { projection: def.projection, n, offset: (page - 1) * n, shown: 1, state: def.state, q: (def.q || "").trim() || undefined,
    sort: def.sort, finished: def.finished, draft: def.draft };
}

function ItemListFrame({ def, every, refreshKey, tools }: FrameProps) {
  const bound = typeof def.onParams === "function";
  const [mine, setMine] = useState<Changes>({});            // its own page, sort, size and finished, unless bound
  const at: PanelDef = bound ? def : { ...def, ...mine };
  const set = (c: Changes) => (bound ? def.onParams(c) : setMine((m) => ({ ...m, page: null, ...c })));
  const got = usePanelAnswer<any>("items", itemListParams(at), every, refreshKey);
  const projection = def.projection, needle = (def.q || "").trim(), state = at.state, size = at.n ?? 25;
  const showFin = at.finished === "show";
  return (
    <Framed def={def} title="Items" tools={tools}>
      <Async state={got}>
        {(d) => {
          const k = d.projections?.find((x: any) => x.name === projection);
          const its = d.items.filter((i: any) => i.projection === projection);
          const left = hiddenStates(k).filter((s) => k?.counts?.[s]);
          const nLeft = left.reduce((a, s) => a + k.counts[s], 0);
          const pager = (where: "top" | "foot") => (
            <Pager at={where} total={d.total} offset={d.offset} cut={d.cut} shown={its.length} size={size} what={needle ? "matches" : state || ""}
              onPage={(n) => set({ page: n > 1 ? n : null })} onSize={(n) => set({ n: n === 25 ? null : n, page: null })} />
          );
          return (
            <section className="sys-group projection-items">
              {/* header: the projection's bar above its list, its graph of states (a state chosen there, the list's) */}
              {def.header && k && <ProjectionBar k={k} state={state || null} onState={(st) => set({ state: st, page: null })} />}
              {its.length ? (
                <>
                  {pager("top")}
                  <div className="panel-table">
                    <ItemsTable items={its} show={k?.show || []} sort={at.sort || ""} caption={`${projection} items`}
                      onSort={(s) => set({ sort: s || null, page: null })} />
                  </div>
                  {pager("foot")}
                </>
              ) : (
                <Empty>{needle ? "Nothing matches." : state ? `No ${projection} items in ${state}.` : "No items to show."}</Empty>
              )}
              {!showFin && !state && !needle && <FinishedNote n={nLeft} states={left} onShow={() => set({ finished: "show", page: null })} />}
            </section>
          );
        }}
      </Async>
    </Framed>
  );
}

// ---- one item

/** The item's answer (GET /api/items/ID), the page's when it has one; `history` asks for its changes. */
function useItem(def: PanelDef, every: number | null | undefined, refreshKey: unknown, history?: string) {
  return usePanelAnswer<any>(pathOf("items", def.item), { ...(def.projection ? { projection: def.projection } : {}),
    ...(history ? { history } : {}) }, every, refreshKey, !history);
}

/** An item's part, drawn once its answer is here; `nothing`: whether it has nothing to say, so that a quiet panel (a
 *  page's) is not drawn at all. */
function ItemPart({ def, title, note, tools, got, nothing, children }: {
  def: PanelDef; title: string; note?: (d: any) => string; tools?: ReactNode; got: { data?: any; error: Error | null };
  nothing?: (d: any) => boolean; children: (d: any) => ReactNode;
}) {
  const d = got.data;
  if (def.quiet && (!d || nothing?.(d))) return null;
  return (
    <Framed def={def} title={title} note={d && note ? note(d) : undefined} tools={tools}>
      {d ? children(d) : got.error ? <p className="muted">Nothing is recorded about {String(def.item)}.</p> : <Loading />}
    </Framed>
  );
}

function part(title: string, draw: (d: any, def: PanelDef) => ReactNode, nothing?: (d: any) => boolean, note?: (d: any) => string) {
  return function Part({ def, every, refreshKey, tools }: FrameProps) {
    const got = useItem(def, every, refreshKey);
    return <ItemPart def={def} title={title} note={note} tools={tools} got={got} nothing={nothing}>{(d) => draw(d, def)}</ItemPart>;
  };
}

function ItemWhyFrame({ def, every, refreshKey, tools }: FrameProps) {
  const { at } = useTime();                     // why is asked of the record as it is now, never at a past moment
  const got = usePanelAnswer<any>(def.item && !at ? "why" : null, { item: def.item }, every === undefined ? 10000 : every, refreshKey);
  const why = got.data;
  if (def.quiet && !whySays(why)) return null;
  return (
    <Framed def={def} title="Why isn't this done?" tools={tools}>
      {at ? <p className="muted">Asked of the record as it is now; this page is at a past moment.</p>
        : whySays(why) ? <ItemWhy why={why} />
        : why ? <p className="muted">{why.done ? "It is done." : "Nothing known holds it up."}</p>
        : got.error ? <p className="note lvl-error">{got.error.message}</p> : <Loading />}
    </Framed>
  );
}

function ItemChangesFrame({ def, every, refreshKey, tools }: FrameProps) {
  const bound = typeof def.onParams === "function";       // the page's fold: asked for only when opened
  const open = !bound || def.history != null;
  const of = def.history && def.history !== "all" ? String(def.history) : "";
  const got = useItem(def, every, refreshKey, open ? of || "all" : undefined);
  const total = (d: any) => `${Object.values<number>(d.changes || {}).reduce((a, b) => a + b, 0)} changes`;
  return (
    <ItemPart def={def} title="Changes" note={total} tools={tools} got={got}>
      {(d) => bound ? (
        <details className="history changes" id="changes" open={open}
          onToggle={(ev) => { const o = (ev.target as HTMLDetailsElement).open; if (o !== open) def.onParams({ history: o ? "all" : null }); }}>
          <summary>Each field's changes, the latest {CHANGES_SHOWN} of each</summary>
          {open && <ItemChanges d={d} of={of} all={() => def.onParams({ history: "all" })} />}
        </details>
      ) : <ItemChanges d={d} of={of} />}
    </ItemPart>
  );
}

/** The projection a further ask of the item names: the panel's, else the one its answer is of (an open projection's
 *  item is found by its projection alone). */
const ofItem = (def: PanelDef, d: any) => {
  const projection = def.projection || d?.projection;
  return projection ? { projection } : {};
};

/** Its states over time, a band; from its moves (else its `state` field's changes, asked for). */
function ItemStateTimelineFrame({ def, every, refreshKey, tools }: FrameProps) {
  const { at } = useTime();
  const now = at ?? Date.now() / 1000;
  const got = useItem(def, every, refreshKey);
  const byField = !!got.data && !(got.data.moves || []).length && (got.data.changes?.state || 0) > 0;
  const hist = usePanelAnswer<any>(byField ? pathOf("items", def.item) : null,
    { ...ofItem(def, got.data), history: "state" }, every, refreshKey);
  const d = byField ? hist.data : got.data;
  const state = byField ? { data: hist.data, error: hist.error ?? got.error } : got;
  return (
    <ItemPart def={def} title="Its states over time" tools={tools} got={state} nothing={(x) => !stateSpans(x, now).length}>
      {() => (stateSpans(d, now).length ? <StateTimeline d={d} now={now} /> : <p className="muted">It has no states over time.</p>)}
    </ItemPart>
  );
}

/** Its numeric fields over time: `field`'s, else each declared numeric (or a number) that changed at least twice. */
function ItemFieldChartFrame({ def, every, refreshKey, tools }: FrameProps) {
  const got = useItem(def, every, refreshKey);
  const field = typeof def.field === "string" && def.field.trim() ? def.field.trim() : undefined;
  const fields = numericCandidates(got.data, field);
  const hist = usePanelAnswer<any>(fields.length ? pathOf("items", def.item) : null,
    { ...ofItem(def, got.data), history: field || "all" }, every, refreshKey);
  const series = hist.data ? numericSeries(hist.data, fields) : [];
  const state = !got.data || !fields.length ? got : { data: hist.data, error: hist.error };
  return (
    <ItemPart def={def} title={field ? `${field} over time` : "Its numbers over time"} tools={tools} got={state}
      nothing={() => !series.length}>
      {() => (series.length ? <FieldCharts series={series} />
        : <p className="muted">{field ? `${field} has not changed to two numbers.` : "No numeric field has changed twice."}</p>)}
    </ItemPart>
  );
}

const ItemSummaryFrame = part("Summary", (d) => <ItemSummary d={d} />);
const ItemPathFrame = part("Where it went", (d) => <ItemPath d={d} />, (d) => !hasPath(d) && !d.eta?.why);
const ItemRelationsFrame = part("Relations", (d) => <ItemRelations d={d} />, (d) => !hasRelations(d));
const ItemFieldsFrame = part("Fields", (d, def) => (
  <ItemFields d={d} onChanges={typeof def.onParams === "function" ? (f) => def.onParams({ history: f }) : undefined} />));
const ItemRefusedFrame = part("Refused", (d) => <ItemRefused d={d} />, (d) => !d.refused?.length);
const ItemMovesFrame = part("How it moved", (d) => <ItemMoves d={d} />);
const ItemEventsFrame = part("Events", (d) => <ItemEvents d={d} />, undefined, (d) => `${d.events} on the record`);
const ItemEventsHistogramFrame = part("Its events over time",
  (d) => (eventBuckets(d) ? <EventsHistogram b={eventBuckets(d)} /> : <p className="muted">No events.</p>),
  (d) => !eventBuckets(d), (d) => (d.record?.length < d.record_total ? `the latest ${d.record.length} of ${d.record_total}` : ""));

export const ITEMS: Record<string, PanelKind> = {
  projections: { label: "Projections, by system", Frame: ProjectionsFrame },
  "items-by-projection": { label: "Every projection's items", Frame: EveryProjectionFrame },
  "projection-now": { label: "A projection's states now", needs: "projection", Frame: ProjectionNowFrame },
  "projection-model": { label: "What in the model counts a projection", needs: "projection", Frame: ProjectionModelFrame },
  "projection-definition": { label: "A projection's definition", needs: "projection", Frame: ProjectionDefinitionFrame },
  "item-list": { label: "A projection's items, a page at a time", needs: "projection", Frame: ItemListFrame },
  "item-summary": { label: "An item: its projection, state and age", needs: "item", Frame: ItemSummaryFrame },
  "item-why": { label: "An item: why it is not done", needs: "item", Frame: ItemWhyFrame },
  "item-path": { label: "An item: where it went", needs: "item", Frame: ItemPathFrame },
  "item-relations": { label: "An item: its relations", needs: "item", Frame: ItemRelationsFrame },
  "item-fields": { label: "An item: its fields", needs: "item", Frame: ItemFieldsFrame },
  "item-refused": { label: "An item: its refused events", needs: "item", Frame: ItemRefusedFrame },
  "item-moves": { label: "An item: how it moved", needs: "item", Frame: ItemMovesFrame },
  "item-events": { label: "An item: its events", needs: "item", Frame: ItemEventsFrame },
  "item-changes": { label: "An item: each field's changes", needs: "item", Frame: ItemChangesFrame },
  "item-state-timeline": { label: "An item: its states over time", needs: "item", Frame: ItemStateTimelineFrame },
  "item-field-chart": { label: "An item: its numeric fields over time", needs: "item", Frame: ItemFieldChartFrame },
  "item-events-histogram": { label: "An item: its events over time, by kind", needs: "item", Frame: ItemEventsHistogramFrame },
};
