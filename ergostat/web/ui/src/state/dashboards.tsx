import { createContext, useContext, type ReactNode } from "react";
import { useApi } from "../hooks/useApi";

/* The dashboards the model declares (GET /api/dashboards), asked for the whole app: the header's navigation shows
   those with `nav:`, and a page shows the one declared in its place (`page:`). Asked again every 15 s, so a dashboard
   accepted or edited in the model shows without a reload. */

export type DashboardListed = {
  name: string; title: string; description?: string; panels: number; window?: number | null; declared: boolean;
  nav?: string | null; page?: string | null;
};

const Ctx = createContext<{ list: DashboardListed[] | undefined; failed: boolean }>({ list: undefined, failed: false });

export function DashboardsProvider({ children }: { children: ReactNode }) {
  const { data, error } = useApi<DashboardListed[]>("dashboards", {}, { every: 15000, window: false });
  return <Ctx.Provider value={{ list: data, failed: !!error && !data }}>{children}</Ctx.Provider>;
}

export const useDashboards = () => useContext(Ctx);

/** The dashboard declared in a page's place: undefined while not known yet, null when there is none. */
export function useInPlaceOf(page: string): DashboardListed | null | undefined {
  const { list, failed } = useDashboards();
  if (failed) return null;                      // asked and not answered: the page's own
  if (!list) return undefined;
  return list.find((d) => d.page === page) || null;
}

/** A declared dashboard's own address. */
export const dashboardHref = (name: string) => `/d/${encodeURIComponent(name)}`;
