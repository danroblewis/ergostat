import { diagramHref } from "../../lib/hrefs";
import type { DashboardDef, PanelDef } from "./types";

/* A panel as written anywhere, made one shape: a draft kept by an older page (a query panel with no `panel`, a
   diagram as `form: diagram` with `diagram: {view, system}`), or one the model declares (its size with -tall). */

export function normalizePanel(x: any, i = 0): PanelDef {
  const p: PanelDef = { ...x };
  if (!p.panel) {
    if (p.form === "diagram") {
      const d = p.diagram || {};
      p.panel = "diagram";
      p.address = p.address || diagramHref({ view: d.view, system: d.system, item: d.item, projection: d.projection });
      delete p.diagram; delete p.form; delete p.queries;
    } else p.panel = "query";
  }
  if (typeof p.size === "string" && p.size.endsWith("-tall")) { p.size = p.size.slice(0, -5) as PanelDef["size"]; p.tall = true; }
  if (!p.id) p.id = `p${i + 1}`;
  return p;
}

export function normalizeDashboard(d: any): DashboardDef {
  return { title: d?.title || "Dashboard", description: d?.description, since: d?.since ?? d?.window ?? null,
    panels: (Array.isArray(d?.panels) ? d.panels : []).map(normalizePanel),
    ...(d?.name ? { name: d.name } : {}), ...(d?.nav != null ? { nav: d.nav } : {}), ...(d?.page ? { page: d.page } : {}) };
}
