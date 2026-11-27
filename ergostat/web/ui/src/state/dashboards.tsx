import { createContext, useContext, useEffect, type ReactNode } from "react";
import { useLocation } from "react-router-dom";
import { useApi } from "../hooks/useApi";
import { setRouteTable } from "../lib/hrefs";
import { setProjections, type ProjectionRoute } from "../lib/routes";
import { resolve, type Resolved, type RouteTable } from "../lib/systemRoutes";

/* What the page's addresses name, asked for the whole app: the dashboards the model declares and its projections with
   their id globs and groups (GET /api/routes), and the route table: every system's scope, the segments of each, and
   which scopes contain each projection, goal and agent (GET /api/route-table, lib/systemRoutes.ts). Asked again every
   15 s, so a dashboard, projection or system added to the model shows without a reload. */

export type DashboardListed = {
  name: string; title: string; description?: string; panels: number; window?: number | null; declared: boolean;
  nav?: string | null; page?: string | null;
  /** a projection's own (`projections: P: dashboards:`): P, and which (list at /P, show at /P/REST) */
  projection?: string | null; role?: "list" | "show" | null;
  /** the system it is written in (its file's `defaults: system:`, or its own `system:`); none: the top level */
  system?: string | null;
};
type Routes = { dashboards: DashboardListed[]; projections: ProjectionRoute[]; reserved: string[]; builtin: string[] };

type Known = { list: DashboardListed[] | undefined; projections: ProjectionRoute[] | undefined; table: RouteTable | undefined;
  failed: boolean;
  /** ask again now (a dashboard was saved) */
  refresh: () => void };
const Ctx = createContext<Known>({ list: undefined, projections: undefined, table: undefined, failed: false, refresh: () => {} });

export function DashboardsProvider({ children }: { children: ReactNode }) {
  const { data, error, refresh } = useApi<Routes>("routes", {}, { every: 15000, window: false });
  const rt = useApi<RouteTable>("route-table", {}, { every: 15000, window: false });
  useEffect(() => { if (data) setProjections(data.projections || []); }, [data]);
  if (data) setProjections(data.projections || []);          // before this render's links are built
  if (rt.data) setRouteTable(rt.data);
  const again = () => { refresh(); rt.refresh(); };
  return <Ctx.Provider value={{ list: data?.dashboards, projections: data?.projections, table: rt.data,
    failed: (!!error && !data) || (!!rt.error && !rt.data), refresh: again }}>{children}</Ctx.Provider>;
}

export const useDashboards = () => useContext(Ctx);

/** What the address names (lib/systemRoutes.ts resolve), and the scope it is in: the system whose dashboards and
 *  projections the nav bar shows. An address that names nothing is at the top level. */
export function useAddress(): { at: Resolved | null; scope: string; table: RouteTable | undefined } {
  const { pathname } = useLocation();
  const { table } = useDashboards();
  const at = table ? resolve(table, pathname) : null;
  return { at, scope: at?.scope ?? "", table };
}

/** A projection's own dashboard (`list` or `show`), when the model declares one. */
export function ownOf(list: DashboardListed[] | undefined, projection: string, role: "list" | "show"): DashboardListed | undefined {
  return (list || []).find((d) => d.projection === projection && d.role === role);
}

/** The dashboard declared for a page of one thing (`page: agent|item|projection`): undefined while not known, else it or null. */
export function useTemplateFor(page: string): DashboardListed | null | undefined {
  const { list, failed } = useDashboards();
  if (failed) return null;
  if (!list) return undefined;
  return list.find((d) => d.page === page) || null;
}

export { dashboardHref } from "../lib/hrefs";
