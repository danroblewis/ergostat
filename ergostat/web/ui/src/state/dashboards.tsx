import { createContext, useContext, useEffect, type ReactNode } from "react";
import { useApi } from "../hooks/useApi";
import { setProjections, type ProjectionRoute } from "../lib/routes";

/* What the page's addresses name (GET /api/routes, lib/routes.ts), asked for the whole app: the dashboards the model
   declares (the header shows those with `nav:`), its projections with their id globs, and the server's own addresses. Asked
   again every 15 s, so a dashboard or projection added to the model shows without a reload. */

export type DashboardListed = {
  name: string; title: string; description?: string; panels: number; window?: number | null; declared: boolean;
  nav?: string | null; page?: string | null;
};
type Routes = { dashboards: DashboardListed[]; projections: ProjectionRoute[]; reserved: string[]; builtin: string[] };

const Ctx = createContext<{ list: DashboardListed[] | undefined; projections: ProjectionRoute[] | undefined; failed: boolean }>(
  { list: undefined, projections: undefined, failed: false });

export function DashboardsProvider({ children }: { children: ReactNode }) {
  const { data, error } = useApi<Routes>("routes", {}, { every: 15000, window: false });
  useEffect(() => { if (data) setProjections(data.projections || []); }, [data]);
  if (data) setProjections(data.projections || []);          // before this render's links are built
  return <Ctx.Provider value={{ list: data?.dashboards, projections: data?.projections, failed: !!error && !data }}>{children}</Ctx.Provider>;
}

export const useDashboards = () => useContext(Ctx);

/** The dashboard declared for a page of one thing (`page: agent|item|projection`): undefined while not known, else it or null. */
export function useTemplateFor(page: string): DashboardListed | null | undefined {
  const { list, failed } = useDashboards();
  if (failed) return null;
  if (!list) return undefined;
  return list.find((d) => d.page === page) || null;
}

/** A declared dashboard's own address: its name. */
export const dashboardHref = (name: string) => `/${encodeURIComponent(name)}`;
