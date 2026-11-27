import { itemPath, projectionsOfId, segs } from "./routes";
import { href, resolve, type RouteTable } from "./systemRoutes";

/* The page's addresses, built in one place: every link to an item, a projection, an agent, a goal, a dashboard or the
   diagram, each at its canonical address (lib/systemRoutes.ts href, over GET /api/route-table: the top-most scope that
   contains it, read from where it is defined). Until the table is here, a link is the old address, which the page
   leads to the same place (Resolve.tsx). */

let table: RouteTable | null = null;

/** The route table, set once the page has asked (state/dashboards.tsx), before the links of that render are built. */
export function setRouteTable(t: RouteTable | null): void {
  table = t;
}
export const routeTable = () => table;

const enc = encodeURIComponent;
const withQ = (to: string, q = "") => (q ? `${to}${to.includes("?") ? "&" : "?"}${q}` : to);

/** An item's page: its projection's address (/PROJECTION/REST in the scope that holds it), else /item/ID (one on a
 *  remote, one no projection of this model's matches, or one several match and none is named: listed there). */
export function itemHref(id: string, remote?: string, projection?: string | null): string {
  if (remote) return `/item/${segs(id)}?remote=${enc(remote)}`;
  if (!table) return itemPath(id, projection) || `/item/${segs(id)}`;
  const ks = projection ? [projection] : projectionsOfId(id).map((k) => k.name);
  return (ks.length === 1 && href(table, { kind: "item", id, projection: ks[0] })) || `/item/${segs(id)}`;
}
/** A projection's list: /PROJECTION in the scope that holds it (given `scope`, the top-most on that scope's chain). */
export const projectionHref = (name: string, q = "", scope?: string | null) =>
  withQ((table && href(table, { kind: "projection", name }, scope)) || `/${enc(name)}`, q);
export const agentHref = (name: string, scope?: string | null) =>
  (table && href(table, { kind: "agent", name }, scope)) || `/agents/${enc(name)}`;
export const goalHref = (name: string, scope?: string | null) =>
  (table && href(table, { kind: "goal", name }, scope)) || `/goals/${enc(name)}`;
/** A dashboard the model writes, by its full name (SYSTEM.NAME), or a default (overview, goals...) in `scope`. */
export const dashboardHref = (name: string, scope?: string | null) =>
  (table && href(table, { kind: "dashboard", name }, scope)) || `/${enc(name.includes(".") ? name.split(".").pop()! : name)}`;
/** A system's default dashboard (its Overview, Diagrams, Goals, Agents, Events): /SYSTEM/NAME, /NAME at the top level. */
export const scopeHref = (system: string | null | undefined, name = "overview", q = "") =>
  withQ((table && href(table, { kind: "dashboard", name }, system || "")) || `/${name}`, q);
/** A system's Events, narrowed (`q`: match=, item=, about=...). */
export const eventsHref = (q = "", system = "") => scopeHref(system, "events", q);

type DiagramAt = { view?: "dynamics" | "blocks" | "process"; system?: string; item?: string; projection?: string; around?: string; projections?: string };

/** The diagram, drawn the way asked: a system's Diagrams (its own address), in a view, or only what an item or a
 *  projection passed through (the Process view: only these projections, `projections`). */
export function diagramHref(at: DiagramAt = {}) {
  const q = new URLSearchParams();
  const known = !at.system || (table && at.system in table.scopes);
  for (const [k, v] of Object.entries(at)) if (v && !(k === "view" && v === "dynamics") && !(k === "system" && known)) q.set(k, v);
  return scopeHref(known ? at.system : "", "diagrams", q.toString());
}

/** A Diagram address read back: what diagramHref writes (a dashboard's diagram panel keeps its address), or the old
 *  /diagram?system=NAME. */
export function diagramOf(address: string): Required<DiagramAt> {
  const [path, query = ""] = address.split("?");
  const q = new URLSearchParams(query);
  const v = q.get("view");
  const at = table ? resolve(table, path) : null;
  const system = q.get("system") || (at && at.kind === "dashboard" ? at.scope : "") || "";
  return {
    view: v === "blocks" || v === "process" ? v : "dynamics",
    system, item: q.get("item") || "", projection: q.get("projection") || "", around: q.get("around") || "",
    projections: q.get("projections") || "",
  };
}
