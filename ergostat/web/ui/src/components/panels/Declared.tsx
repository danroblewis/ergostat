import { useState, type ReactNode } from "react";
import { useApi } from "../../hooks/useApi";
import { Button, ErrorNote, Loading, Note, Page, Select } from "../ui";
import { EditableDashboard, useEditing, type SaveTarget } from "./EditableDashboard";
import { normalizeDashboard } from "./normalize";
import type { DashboardDef } from "./types";

/* A dashboard the model declares (`dashboards:`, or a projection's own `dashboards:`; SPEC §4f), drawn as declared, each
   panel asking for its own answer: at its own address (/NAME), in place of one of ergostat's pages, for each agent,
   item or projection (`page:`), and a projection's own list and show at its addresses, where `bind` gives the
   address's words (agent, item, projection) its panels' `$WORD` stands for. Edited where it is drawn
   (EditableDashboard). */

export const EVERY: Record<string, number> = { Off: 0, "10s": 10000, "30s": 30000, "1m": 60000, "5m": 300000 };

/** How often the dashboard asks again, and now. */
export function Refresh({ every, setEvery, onNow }: { every: string; setEvery: (v: string) => void; onNow: () => void }) {
  return (
    <>
      <label className="muted small">Refresh <Select value={every} onChange={(e) => setEvery(e.target.value)} options={Object.keys(EVERY)} /></label>
      <Button onClick={onNow}>Refresh now</Button>
    </>
  );
}

/** The declaration of a declared dashboard (its panels as declared, `$WORD`s and all: the page fills them from `bind`). */
export function useDeclared(name: string) {
  const got = useApi<any>(`dashboard/${encodeURIComponent(name)}`, { plain: 1 }, { window: false });
  const d: DashboardDef | null = got.data ? normalizeDashboard(got.data) : null;
  return { d, error: got.error, refresh: got.refresh, projection: got.data?.projection as string | undefined,
    role: got.data?.role as "list" | "show" | undefined };
}

/** Where a declared dashboard is saved when it is edited where it is drawn: a projection's own under that projection,
 *  any other under its own name. */
export function targetOf(name: string, d: DashboardDef | null, projection?: string, role?: "list" | "show"): SaveTarget {
  return projection && role ? { projection, role } : { name, page: d?.page ?? null, nav: d?.nav ?? null };
}

export function DeclaredDashboard({ name, bind, actions, every: everyFirst = "30s", resettable = false }: {
  name: string; bind?: Record<string, string>;
  /** the page's own buttons beside the refresh, given the declaration once it is here */
  actions?: (d: DashboardDef | null) => ReactNode;
  every?: string;
  /** drawn in place of one of ergostat's own pages: Reset to ergostat's takes it out of the model again */
  resettable?: boolean;
}) {
  const { d, error, refresh, projection, role } = useDeclared(name);
  const [every, setEvery] = useState(everyFirst);
  const [refreshed, setRefreshed] = useState(0);
  const ed = useEditing({ base: d, target: d ? targetOf(name, d, projection, role) : null, saved: resettable || !!projection,
    bind, onDone: () => refresh() });
  return (
    <Page title={d?.title || bind?.item || bind?.agent || bind?.projection || name} className="dash" actions={(
      <span className="dash-actions">
        {!ed.editing && actions?.(d)}
        {!ed.editing && <Refresh every={every} setEvery={setEvery} onNow={() => setRefreshed((n) => n + 1)} />}
        {ed.bar}
      </span>
    )}>
      {error && <ErrorNote error={error} />}
      {!d && !error && <Loading />}
      {d?.description && <Note>{d.description}</Note>}
      {d && <EditableDashboard ed={ed} every={EVERY[every] || null} refreshKey={refreshed} />}
    </Page>
  );
}
