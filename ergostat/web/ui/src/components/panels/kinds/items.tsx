import { useState, type ReactNode } from "react";
import { ancillaryMark, scopedBy } from "../../../lib/scoped";
import { useDashboards } from "../../../state/dashboards";
import { useTime } from "../../../state/time";
import { ProjectionStates } from "../../charts/ProjectionStates";
import {
  bucketWords, eventBuckets, EventsHistogram, FieldCharts, numericCandidates, numericSeries, StateTimeline, stateSpans,
} from "../../charts/ItemCharts";
import { PanelFrame } from "../../charts/PanelView";
import { FinishedNote, Pager } from "../../controls";
import { Decisions, entryOf, INBOX } from "../../Decisions";
import { nowS } from "../../../lib/format";
import {
  hasRelations, ItemFields, ItemHistory, ItemRefused, ItemRelations, ItemSummary, ItemWhy, whySays,
} from "../../itemParts";
import { hiddenStates, ItemsTable, ProjectionBar, ProjectionGraph } from "../../items";
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
   page, sort, size and finished), `page` (the list's page), `quiet` (a part with nothing to say is not drawn at all)
   and `folded` (a definition shown when asked). */

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

/** What the projection-summary and projection-states panels ask GET /api/items: the projection's frame alone (its
 *  counts, moves, ends, description, system), the list's answer when the page has asked it (any of that path that
 *  lists the projection). */
const frameParams = (def: PanelDef) => ({ projection: def.projection, n: 1, shown: 1, draft: def.draft });
const listsIt = (def: PanelDef) => (d: any) => !!d?.projections?.some((x: any) => x.name === def.projection);

function useFrame(def: PanelDef, every: number | null | undefined, refreshKey: unknown) {
  const got = usePanelAnswer<any>(def.projection ? "items" : null, frameParams(def), every, refreshKey, listsIt(def));
  return { got, k: got.data?.projections?.find((x: any) => x.name === def.projection) };
}

/** Its name, id pattern, how many items, its description and the system it is in. The page that is the projection's
 *  own draws its name as the page's heading (`heading: 1`, a page's key). */
function ProjectionSummaryFrame({ def, every, refreshKey, tools }: FrameProps) {
  const { got, k } = useFrame(def, every, refreshKey);
  return (
    <PanelFrame panel={{ ...asQueryPanel(def), title: def.title || "", note: def.note }} tools={tools}
      className={`panel-kind-${def.panel}${def.title ? "" : " panel-untitled"}`}>
      {k ? <ProjectionBar k={k} level={def.heading === 1 ? 1 : 2} />
        : got.error ? <p className="note lvl-error">{got.error.message}</p>
        : got.data ? <p className="muted">{String(def.projection)} is not one of the model's projections.</p> : <Loading />}
    </PanelFrame>
  );
}

/** Its graph of states: each state's count now, the moves its items made (with how many times), the arrivals, the
 *  moves back; a state not reached yet faded in its place, an end boxed double. A state chosen filters the page's list
 *  of it (`onState`, a page's key), else leads to its list in that state. `counts: false`: without the numbers. */
function ProjectionStatesFrame({ def, every, refreshKey, tools }: FrameProps) {
  const { got, k } = useFrame(def, every, refreshKey);
  return (
    <Framed def={{ fit: true, ...def }} title="Its states" tools={tools}>
      {k ? <ProjectionGraph k={k} state={def.state || null} counts={def.counts !== false}
        onState={typeof def.onState === "function" ? def.onState : undefined} />
        : got.error ? <p className="note lvl-error">{got.error.message}</p>
        : got.data ? <p className="muted">{String(def.projection)} is not one of the model's projections.</p> : <Loading />}
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
          const listed = d.items.filter((i: any) => i.projection === projection);
          // ergostat.inbox's: each one waiting a card answered in place (oldest first, as `ergostat inbox` lists them),
          // the rest its rows
          const inbox = projection === INBOX && (!state || state === "waiting") && !needle;
          const waits = inbox ? listed.filter((i: any) => i.state === "waiting").sort((a: any, b: any) => (a.fields?.asked ?? a.first) - (b.fields?.asked ?? b.first)) : [];
          const its = inbox ? listed.filter((i: any) => i.state !== "waiting") : listed;
          const now = nowS();
          const left = hiddenStates(k).filter((s) => k?.counts?.[s]);
          const nLeft = left.reduce((a, s) => a + k.counts[s], 0);
          const pager = (where: "top" | "foot") => (
            <Pager at={where} total={d.total} offset={d.offset} cut={d.cut} shown={its.length} size={size} what={needle ? "matches" : state || ""}
              onPage={(n) => set({ page: n > 1 ? n : null })} onSize={(n) => set({ n: n === 25 ? null : n, page: null })} />
          );
          return (
            <section className="sys-group projection-items">
              {inbox && <Decisions entries={waits.map((i: any) => entryOf(i, now))} />}
              {its.length ? (
                <>
                  {pager("top")}
                  <div className="panel-table">
                    <ItemsTable items={its} show={k?.show || []} sort={at.sort || ""} caption={`${projection} items`}
                      onSort={(s) => set({ sort: s || null, page: null })} />
                  </div>
                  {pager("foot")}
                </>
              ) : inbox ? null : (
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

/** Why it is not done, in a line, only while it is unfinished and something known holds it (never for an item of
 *  ergostat's built-in projections: their bookkeeping is ergostat's to move, not the owner's). */
function ItemWhyFrame({ def, every, refreshKey, tools }: FrameProps) {
  const { at } = useTime();                     // why is asked of the record as it is now, never at a past moment
  const own = String(def.item || "").startsWith("ergostat.");
  const got = usePanelAnswer<any>(def.item && !at && !own ? "why" : null, { item: def.item }, every === undefined ? 10000 : every, refreshKey);
  const why = got.data;
  if (def.quiet && (own || !whySays(why))) return null;
  return (
    <Framed def={def} title="Why isn't this done?" tools={tools}>
      {own ? <p className="muted">It is ergostat's own bookkeeping: ergostat moves it.</p>
        : at ? <p className="muted">Asked of the record as it is now; this page is at a past moment.</p>
        : whySays(why) ? <ItemWhy why={why} />
        : why ? <p className="muted">{why.done ? "It is done." : "Nothing known holds it up."}</p>
        : got.error ? <p className="note lvl-error">{got.error.message}</p> : <Loading />}
    </Framed>
  );
}

/** Its history: each event, newest first, with the move and the field changes it made (its fields' changes asked for:
 *  `history=all`, the page's answer when it has asked the same). */
function ItemHistoryFrame({ def, every, refreshKey, tools }: FrameProps) {
  const got = usePanelAnswer<any>(pathOf("items", def.item), { ...(def.projection ? { projection: def.projection } : {}), history: "all" },
    every, refreshKey, (d: any) => !!d?.history);
  return (
    <ItemPart def={def} title="History" note={(d) => `${d.events} events, newest first`} tools={tools} got={got}>
      {(d) => <ItemHistory d={d} />}
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

/** Each declared field's unit, where the projection gives one. */
const unitsOf = (d: any): Record<string, string> => Object.fromEntries(Object.entries<any>(d?.projection_of?.fields || {})
  .filter(([, x]) => x && typeof x.unit === "string").map(([f, x]) => [f, x.unit]));

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
      {() => (series.length ? <FieldCharts series={series} units={unitsOf(got.data)} />
        : <p className="muted">{field ? `${field} has not changed to two numbers.` : "No numeric field has changed twice."}</p>)}
    </ItemPart>
  );
}

const ItemSummaryFrame = part("Summary", (d) => <ItemSummary d={d} />);
const ItemRelationsFrame = part("Relations", (d) => <ItemRelations d={d} />, (d) => !hasRelations(d));
const ItemFieldsFrame = part("Fields", (d) => <ItemFields d={d} />);
const ItemRefusedFrame = part("Refused", (d) => <ItemRefused d={d} />, (d) => !d.refused?.length);

/** Its events per time bucket, by kind: its title says the bucket's size ("Its events per 10 minutes, by kind"). */
function ItemEventsHistogramFrame({ def, every, refreshKey, tools }: FrameProps) {
  const got = useItem(def, every, refreshKey);
  const b = eventBuckets(got.data);
  return (
    <ItemPart def={def} title={b ? `Its events per ${bucketWords(b.size)}, by kind` : "Its events over time"} tools={tools} got={got}
      nothing={() => !b} note={(d) => (d.record?.length < d.record_total ? `the latest ${d.record.length} of ${d.record_total}` : "")}>
      {() => (b ? <EventsHistogram b={b} /> : <p className="muted">No events.</p>)}
    </ItemPart>
  );
}

export const ITEMS: Record<string, PanelKind> = {
  projections: { label: "Projections, by system", Frame: ProjectionsFrame },
  "items-by-projection": { label: "Every projection's items", Frame: EveryProjectionFrame },
  "projection-now": { label: "A projection's states now", needs: "projection", Frame: ProjectionNowFrame },
  "projection-model": { label: "What in the model counts a projection", needs: "projection", Frame: ProjectionModelFrame },
  "projection-definition": { label: "A projection's definition", needs: "projection", Frame: ProjectionDefinitionFrame },
  "projection-summary": { label: "A projection: its name, count, description and system", needs: "projection", Frame: ProjectionSummaryFrame },
  "projection-states": { label: "A projection's graph of states", needs: "projection", Frame: ProjectionStatesFrame },
  "item-list": { label: "A projection's items, a page at a time", needs: "projection", Frame: ItemListFrame },
  "item-summary": { label: "An item: its projection, state and age", needs: "item", Frame: ItemSummaryFrame },
  "item-why": { label: "An item: why it is not done", needs: "item", Frame: ItemWhyFrame },
  "item-relations": { label: "An item: its relations", needs: "item", Frame: ItemRelationsFrame },
  "item-fields": { label: "An item: its fields", needs: "item", Frame: ItemFieldsFrame },
  "item-refused": { label: "An item: its refused events", needs: "item", Frame: ItemRefusedFrame },
  "item-history": { label: "An item: its history, each event with what it changed", needs: "item", Frame: ItemHistoryFrame },
  "item-state-timeline": { label: "An item: its states over time", needs: "item", Frame: ItemStateTimelineFrame },
  "item-field-chart": { label: "An item: its numeric fields over time", needs: "item", Frame: ItemFieldChartFrame },
  "item-events-histogram": { label: "An item: its events over time, by kind", needs: "item", Frame: ItemEventsHistogramFrame },
};
