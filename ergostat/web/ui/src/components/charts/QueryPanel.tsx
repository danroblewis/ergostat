import { useEffect, useMemo, useRef, type ReactNode } from "react";
import { useApi } from "../../hooks/useApi";
import { encodeQuery, plan, split, type Answer, type Panel } from "../../lib/query";
import { useTime } from "../../state/time";
import { PanelView } from "./PanelView";

/* Panels that ask for their own answers, so a page shows a query anywhere with one element:
     <QueryPanel panel={{ id: "q", title: "Done", form: "line", queries: [{ source: "promql", text: "..." }] }} />
   Many panels on one page share one request: usePanelResults(panels), then a <PanelView> each. */

/** Every panel's queries in one request over the header's window, asked again every ``every`` ms (none: once) and
 *  whenever ``refreshKey`` changes (a page's "Refresh now"). */
export function usePanelResults(panels: Panel[], { every = 30000, points = 120, refreshKey }: { every?: number | null; points?: number; refreshKey?: unknown } = {}) {
  const { seconds, at } = useTime();
  const { queries, wanted } = useMemo(() => plan(panels), [panels]);
  const q = queries.length ? encodeQuery({ since: seconds, until: at, points, queries }) : null;
  const answer = useApi<Answer>(q ? "query" : null, { q }, { window: false, every: every || null });
  const byPanel = useMemo(() => split(panels, answer.data, wanted), [panels, answer.data, wanted]);
  const asked = useRef(refreshKey);
  useEffect(() => {
    if (asked.current === refreshKey) return;
    asked.current = refreshKey;
    answer.refresh();
  }, [refreshKey]); // eslint-disable-line react-hooks/exhaustive-deps
  return { byPanel, error: answer.error, loading: answer.loading, refresh: answer.refresh };
}

/** One panel that asks for its own answer. */
export function QueryPanel({ panel, every, tools, refreshKey }: { panel: Panel; every?: number | null; tools?: ReactNode; refreshKey?: unknown }) {
  const panels = useMemo(() => [panel], [panel]);
  const { byPanel, error, loading } = usePanelResults(panels, { every, refreshKey });
  return <PanelView panel={panel} results={byPanel.get(panel.id)} loading={loading} error={error} tools={tools} />;
}
