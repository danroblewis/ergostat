import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { ErrorNote, Filters, FinishedToggle, ProjectionBar, Page, PAGE_SIZES, SearchBox, StatesChoice } from "../../components";
import { Contained } from "../../components/Contained";
import { EditableDashboard, useEditing } from "../../components/panels/EditableDashboard";
import { itemListParams } from "../../components/panels/kinds/items";
import { SharedAnswers } from "../../components/panels/shared";
import type { PanelDef } from "../../components/panels/types";
import { usePanelApi } from "../../components/panels/usePanelApi";
import { apiSend } from "../../lib/api";
import { draftKey, keptDrop, keptGet, keptSet, stepsKey } from "../../lib/kept";
import { PROJECTION_PANELS } from "../../lib/pages";
import { starter, useTry } from "./DefinitionEditor";
import { Workbench, WorkbenchYaml } from "./workbench/Workbench";

/* /PROJECTION, a dashboard made in advance (kindpage.js): its bar as the page's heading (a state chip filters the
   list), then its panels: Now (projection-now: its states over the window and how long its finished took), In the
   model (projection-model: what counts it, the goals and loops it is in), and its items
   (item-list: a page at a time, searched and sorted by the server). The page asks each answer once and hands it to
   its panels; the list's filters are in its head. Every choice is in the address: state=, q=, finished=show, sort=PROJECTION:field, page=PROJECTION:N, size=,
   states=all. Edited in place, it is saved as the projection's list dashboard (`dashboards: list:`, in the file the
   projection is defined in), drawn at /PROJECTION in place of this one.

   Editing also edits the projection's definition in the workbench (workbench/Workbench.tsx: query, kinds of event,
   mapping, review; the YAML at the very bottom of the page, below its panels), the draft tried on the record as it changes (DefinitionEditor.tsx), the
   page's panels drawing the draft's items (draft=ID) meanwhile; Save writes the definition into the model
   (POST /api/projections/save) and then the list dashboard if its panels changed; Cancel forgets both. A new
   projection (the nav bar's + after the projections, `creating`) opens here in edit mode with a starting definition. */

const SIZES = PAGE_SIZES;
const BASE = { title: "", panels: PROJECTION_PANELS };

export default function ProjectionPage({ projection, system = "", creating = false, onCreated, onCancel, proposed }: {
  projection: string; system?: string; creating?: boolean; onCreated?: () => void; onCancel?: () => void;
  /** a drafted definition a model change proposes (/?workbench=NAME&proposal=ID): opened in the workbench, to edit */
  proposed?: string;
}) {
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
  const [saved, setSaved] = useState(0);                  // asked again once a save is written
  const [text, setText] = useState<string | null>(null);  // the definition while editing
  const [was, setWas] = useState<string | null>(null);    // as it was when editing began

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
  const tried = useTry(projection, text, system);
  const ed = useEditing({
    base: BASE, target: { projection, role: "list" }, bind: { projection },
    before: async () => {
      if (text != null && (creating || text !== was)) {
        await apiSend("projections/save", { name: projection, yaml: text, system: system || undefined, new: creating || undefined });
      }
    },
    onDone: () => { forget(); setSaved((x) => x + 1); if (creating) onCreated?.(); },
    onCancel: () => { forget(); if (creating) onCancel?.(); },
  });
  // the draft kept for the tab while editing (lib/kept.ts), so that a reload or a remount loses no work: restored when
  // the page opens again, forgotten on Save or Cancel
  const kk = draftKey(system, projection);
  const forget = () => keptDrop(kk, stepsKey(system, projection));
  const fp = usePanelApi<any>(`projections/${encodeURIComponent(projection)}`, {}, 30000, saved);
  useEffect(() => { if ((creating || proposed != null || keptGet(kk)) && !ed.editing) ed.begin(); }, [creating, proposed]);   // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {                                       // editing: the definition as written (a new one: a start)
    if (!ed.editing) { setText(null); setWas(null); return; }
    if (text != null) return;
    if (proposed != null) {                               // the draft proposed, against the definition as written
      if (!creating && !fp.data && !fp.error) return;
      setText(proposed);
      setWas(creating || fp.error ? "" : (fp.data?.yaml ?? ""));
      return;
    }
    const kept = keptGet<{ text: string; was: string }>(kk);
    if (kept && typeof kept.text === "string") { setText(kept.text); setWas(typeof kept.was === "string" ? kept.was : kept.text); return; }
    const t = creating || fp.error ? starter(projection) : fp.data ? (fp.data.yaml ?? null) : null;
    if (t != null) { setText(t); setWas(t); }
  }, [ed.editing, fp.data, fp.error]);                    // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!ed.editing || text == null) return;
    if (creating || text !== was) keptSet(kk, { text, was }); else keptDrop(kk);
  }, [text, was]);                                        // eslint-disable-line react-hooks/exhaustive-deps
  const problems = useMemo(() => (tried.report && !tried.report.ok ? tried.report.errors : tried.report ? [] : undefined), [tried.report]);
  const draft: string | undefined = ed.editing && tried.report?.ok ? tried.report.draft : undefined;

  // what the address chooses, given to the list's panel and the states' (the first of each kind: the page's own)
  const listed = { state: state || undefined, q: needle || undefined, sort: sort || undefined,
    finished: showFin ? "show" : undefined, n: size, page: pg, onParams };
  const list: PanelDef = { panel: "item-list", projection, draft, ...listed };
  const decorate = (d: PanelDef): PanelDef => {
    const mine = d.projection === projection && draft ? { ...d, draft } : d;
    return mine.panel === "item-list" && mine.projection === projection ? { ...mine, ...listed }
      : mine.panel === "projection-now" ? { ...mine, states: all ? "all" : mine.states } : mine;
  };
  const asked = itemListParams(list);
  const items = usePanelApi<any>("items", asked, 5000, saved);
  const fpAsked = draft ? { draft } : {};
  const fpShown = usePanelApi<any>(draft ? `projections/${encodeURIComponent(projection)}` : null, fpAsked, 30000);
  const flowAsked = { projection, points: 60, draft };
  const flow = usePanelApi<any>("items-flow", flowAsked, 30000, saved);
  const k = items.data?.projections?.find((x: any) => x.name === projection);

  return (
    <div className="page projection-page">
      {k ? (
        <ProjectionBar k={k} level={1} state={state} onState={(st) => set({ state: st })} />
      ) : items.error && !creating ? (
        <Page title={projection}><ErrorNote error={items.error} /></Page>
      ) : (
        <h1>{projection}{creating && <span className="muted small"> (new: not in the model until it is saved)</span>}</h1>
      )}
      {ed.bar && <div className="page-edit">{ed.bar}</div>}
      {ed.editing && text != null && (
        <Contained label="The workbench">
          <Workbench name={projection} system={system} text={text} creating={creating}
            setText={(v) => setText((p) => (typeof v === "function" ? (p == null ? p : v(p)) : v))}
            />
        </Contained>
      )}
      <SharedAnswers answers={[
        { path: "items", params: asked, state: items },
        { path: `projections/${encodeURIComponent(projection)}`, params: fpAsked, state: draft ? fpShown : fp },
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
      {ed.editing && text != null && <WorkbenchYaml text={text} setText={(t) => setText(t)} problems={problems} />}
    </div>
  );
}
