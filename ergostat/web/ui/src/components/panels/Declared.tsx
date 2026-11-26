import { useState, type ReactNode } from "react";
import { useApi } from "../../hooks/useApi";
import { Button, ErrorNote, Loading, Note, Page, Select } from "../ui";
import { DashboardView } from "./DashboardView";
import { normalizeDashboard } from "./normalize";
import type { DashboardDef } from "./types";

/* A dashboard the model declares (`dashboards:`, SPEC §4f), drawn as declared, each panel asking for its own answer:
   at /dashboard?name=NAME, at its own address (/d/NAME, with `nav:`), and in a page's place (`page:`), where `bind`
   gives the address's word (agent, item or kind) its panels' `$WORD` stands for. */

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

/** The declaration of a declared dashboard (its panels, `$WORD`s filled from `bind`). */
export function useDeclared(name: string, bind: Record<string, string> = {}) {
  const got = useApi<any>(`dashboard/${encodeURIComponent(name)}`, { plain: 1, ...bind }, { window: false });
  const d: DashboardDef | null = got.data ? normalizeDashboard(got.data) : null;
  return { d, error: got.error };
}

export function DeclaredDashboard({ name, bind, actions, every: everyFirst = "30s" }: {
  name: string; bind?: Record<string, string>;
  /** the page's own buttons beside the refresh, given the declaration once it is here */
  actions?: (d: DashboardDef | null) => ReactNode;
  every?: string;
}) {
  const { d, error } = useDeclared(name, bind);
  const [every, setEvery] = useState(everyFirst);
  const [refreshed, setRefreshed] = useState(0);
  return (
    <Page title={d?.title || name} className="dash" actions={(
      <span className="dash-actions">
        {actions?.(d)}
        <Refresh every={every} setEvery={setEvery} onNow={() => setRefreshed((n) => n + 1)} />
      </span>
    )}>
      {error && <ErrorNote error={error} />}
      {!d && !error && <Loading />}
      {d?.description && <Note>{d.description}</Note>}
      {d && <DashboardView panels={d.panels} every={EVERY[every] || null} refreshKey={refreshed} />}
    </Page>
  );
}
