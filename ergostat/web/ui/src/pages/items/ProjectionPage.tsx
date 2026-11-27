import { useSearchParams } from "react-router-dom";
import { ErrorNote, Filters, FinishedToggle, ProjectionBar, Page, PAGE_SIZES, SearchBox, StatesChoice } from "../../components";
import { EditableDashboard, useEditing } from "../../components/panels/EditableDashboard";
import { itemListParams } from "../../components/panels/kinds/items";
import { SharedAnswers } from "../../components/panels/shared";
import type { PanelDef } from "../../components/panels/types";
import { usePanelApi } from "../../components/panels/usePanelApi";
import { PROJECTION_PANELS } from "../../lib/pages";

/* /PROJECTION, a dashboard made in advance (kindpage.js): its bar as the page's heading (a state chip filters the
   list), then its panels: Now (projection-now: its states over the window and how long its finished took), In the
   model (projection-model: what counts it, the goals and loops it is in), its definition (projection-definition), and its items
   (item-list: a page at a time, searched and sorted by the server). The page asks each answer once and hands it to
   its panels; the list's filters are in its head. Every choice is in the address: state=, q=, finished=show, sort=PROJECTION:field, page=PROJECTION:N, size=,
   states=all. Edited in place, it is saved as the projection's list dashboard (`dashboards: list:`, in the file the
   projection is defined in), drawn at /PROJECTION in place of this one. */

const SIZES = PAGE_SIZES;
const BASE = { title: "", panels: PROJECTION_PANELS };

export default function ProjectionPage({ projection }: { projection: string }) {
  const [q, setQ] = useSearchParams();
  // a value for another projection (page=gap:3) is not this one's
  const ofProjection = (v: string | null) => { const s = v || ""; const i = s.indexOf(":"); return i < 0 ? s : s.slice(0, i) === projection ? s.slice(i + 1) : ""; };
  const state = q.get("state");
  const needle = (q.get("q") || "").trim();
  const showFin = q.get("finished") === "show";
  const sort = ofProjection(q.get("sort"));
  const pg = Math.max(1, parseInt(ofProjection(q.get("page")), 10) || 1);
  const size = SIZES.includes(+(q.get("size") || 0)) ? +q.get("size")! : 25;
  const all = q.get("states") === "all";

  const set = (changes: Record<string, string | null>, keepPage = false) =>
    setQ((p) => {
      const n = new URLSearchParams(p);
      for (const [k, v] of Object.entries(changes)) { if (v) n.set(k, v); else n.delete(k); }
      if (!keepPage && !("page" in changes)) n.delete("page");   // a new filter or sort: page 1
      return n;
    }, { replace: true });

  // the list's choices, as the panel says them, into the address
  const onParams = (c: Record<string, string | number | null>) => {
    const out: Record<string, string | null> = {};
    if ("page" in c) out.page = c.page ? `${projection}:${c.page}` : null;
    if ("sort" in c) out.sort = c.sort ? `${projection}:${c.sort}` : null;
    if ("n" in c) out.size = c.n ? String(c.n) : null;
    if ("finished" in c) out.finished = c.finished ? String(c.finished) : null;
    set(out);
  };
  // what the address chooses, given to the list's panel and the states' (the first of each kind: the page's own)
  const listed = { state: state || undefined, q: needle || undefined, sort: sort || undefined,
    finished: showFin ? "show" : undefined, n: size, page: pg, onParams };
  const list: PanelDef = { panel: "item-list", projection, ...listed };
  const ed = useEditing({ base: BASE, target: { projection, role: "list" }, bind: { projection } });
  const decorate = (d: PanelDef): PanelDef => d.panel === "item-list" && d.projection === projection ? { ...d, ...listed }
    : d.panel === "projection-now" ? { ...d, states: all ? "all" : d.states } : d;
  const asked = itemListParams(list);
  const items = usePanelApi<any>("items", asked, 5000);
  const fp = usePanelApi<any>(`projections/${encodeURIComponent(projection)}`, {}, 30000);
  const flowAsked = { projection, points: 60 };
  const flow = usePanelApi<any>("items-flow", flowAsked, 30000);
  const k = items.data?.projections?.find((x: any) => x.name === projection);

  return (
    <div className="page projection-page">
      {k ? (
        <ProjectionBar k={k} level={1} state={state} onState={(st) => set({ state: st })} />
      ) : items.error ? (
        <Page title={projection}><ErrorNote error={items.error} /></Page>
      ) : (
        <h1>{projection}</h1>
      )}
      {ed.bar && <div className="page-edit">{ed.bar}</div>}
      <SharedAnswers answers={[
        { path: "items", params: asked, state: items },
        { path: `projections/${encodeURIComponent(projection)}`, state: fp },
        { path: "items-flow", params: flowAsked, state: flow },
      ]}>
        <EditableDashboard ed={ed} decorate={decorate} tools={(d) => d.panel === "projection-now" ? (
          <StatesChoice all={all} onChange={(v) => set({ states: v ? "all" : null }, true)} />
        ) : d.panel === "item-list" ? (
          <Filters>
            <SearchBox value={needle} live placeholder="Search ids and fields" onSearch={(w) => set({ q: w || null })} />
            {needle && items.data && (
              <span className="muted search-said" aria-live="polite">
                {items.data.total} match{items.data.total === 1 ? "" : "es"}, {items.data.finished ?? 0} finished
              </span>
            )}
            <FinishedToggle shown={showFin} onChange={(v) => set({ finished: v ? "show" : null })} />
            {state && (
              <span className="set-chip">
                state {state}{" "}
                <button type="button" className="ghost" title="Remove this filter" aria-label="Remove this filter" onClick={() => set({ state: null })}>×</button>
              </span>
            )}
          </Filters>
        ) : null} />
      </SharedAnswers>
    </div>
  );
}
