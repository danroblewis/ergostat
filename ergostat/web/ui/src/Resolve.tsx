import { lazy, type ReactNode } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { AppLink, ErrorNote, Loading, Page } from "./components";
import { agentHref, dashboardHref, diagramHref, itemHref, projectionHref, scopeHref } from "./lib/hrefs";
import { idOf, projectionsOfId } from "./lib/routes";
import { resolve, type RouteTable } from "./lib/systemRoutes";
import { keptDrop, keptGet, keptSet, newProjectionKey } from "./lib/kept";
import { ownOf, useDashboards, type DashboardListed } from "./state/dashboards";

/* Every address but the server's, read one segment at a time from the top level by lib/systemRoutes.ts (the same rules
   as spec/routes.py, over GET /api/route-table): in each scope a segment is a dashboard (the model's, or a default:
   overview, diagrams, goals, agents, events), a projection the scope contains (its list; under it, its items), a goal
   or an agent under goals/ and agents/, or a subsystem. A deeper address of a thing also at a higher scope redirects
   (replace) to the top-most; a system's own address (/, /factory) to its Overview. ?builtin=1 draws ergostat's own
   page where the model's dashboard replaces it. Old addresses (/record, /diagram, /agent/NAME, /item/ID of one
   projection, /PROJECTION of a projection not at the top level, /items/NAME, /d/NAME, /loops) lead to their new ones;
   /item/ID stays the page of an id no projection sees, or several see. A new dashboard (the nav bar's +) is drawn
   wherever it was asked for, until it is saved under its name in that scope. */

const Overview = lazy(() => import("./pages/overview"));
const Diagram = lazy(() => import("./pages/diagram"));
const Goals = lazy(() => import("./pages/goals"));
const Goal = lazy(() => import("./pages/goals/GoalPage"));
const Agents = lazy(() => import("./pages/agents"));
const Agent = lazy(() => import("./pages/agents/AgentPage"));
const Projection = lazy(() => import("./pages/items/ProjectionPage"));
const Item = lazy(() => import("./pages/items/ItemPage"));
const Events = lazy(() => import("./pages/events"));
// a dashboard the model declares: loaded when one is shown, so the first load does not bring every panel
const Declared = lazy(() => import("./components/panels/Declared").then((m) => ({ default: m.DeclaredDashboard })));
const NewDashboard = lazy(() => import("./components/panels/NewDashboard"));

/** Each system's default dashboards, drawn by ergostat's own pages. */
const DEFAULT_PAGES: Record<string, (system: string) => ReactNode> = {
  overview: (system) => <Overview key={system} system={system} />,
  diagrams: (system) => <Diagram key={system} system={system} />,
  goals: (system) => <Goals key={system} system={system} />,
  agents: (system) => <Agents key={system} system={system} />,
  events: (system) => <Events key={system} system={system} />,
};

/** ergostat's own page for an address, a link to it from a dashboard drawn in its place. */
function OwnLink({ pathname, search }: { pathname: string; search: string }) {
  const q = new URLSearchParams(search);
  q.set("builtin", "1");
  return <AppLink className="small" to={`${pathname}?${q}`} title="What ergostat draws here when the model names nothing">ergostat's own page</AppLink>;
}

/** A dashboard's name in its system (factory.board is board in factory). */
const localOf = (name: string, system: string) => (system && name.startsWith(system + ".") ? name.slice(system.length + 1) : name);

/** An address with a query added ("?a=1" or "a=1"). */
const joined = (to: string, keep: string) => { const k = keep.replace(/^\?/, ""); return k ? `${to}${to.includes("?") ? "&" : "?"}${k}` : to; };

export default function Resolve() {
  const { pathname, search, hash, state } = useLocation();
  const navigate = useNavigate();
  const { list, table, failed } = useDashboards();
  const q = new URLSearchParams(search);
  const builtin = q.get("builtin") === "1";
  const go = (to: string, keep = search) => <Navigate replace to={joined(to, keep) + hash} />;

  if (!table || !list) return failed ? <Page title="ergostat"><ErrorNote error="The server does not answer the page's addresses (GET /api/route-table)." /></Page> : <Loading />;
  const at = resolve(table, pathname);
  if ((state as any)?.newDashboard) {
    const system = at?.scope ?? "";
    return <NewDashboard key={(state as any).newDashboard} system={system}
      onSaved={(name) => navigate(`${table.scopes[system]?.path.replace(/\/$/, "") || ""}/${encodeURIComponent(localOf(name, system))}`)}
      onCancel={() => navigate(-1)} />;
  }
  // the nav bar's + after the projections: until saved. Kept for the tab too (lib/kept.ts): a change to the address's
  // query (a search, the window) replaces the history entry without its state, and a reload drops it
  const st = state as any;
  const ask = st?.newProjection ? { name: String(st.newProjection), system: String(st.system || ""), at: st.at }
    : keptGet<{ name: string; system: string; at: unknown }>(newProjectionKey(pathname));
  if (ask && !(at?.kind === "projection" && at.name === ask.name)) {
    if (st?.newProjection) keptSet(newProjectionKey(pathname), ask);
    const done = () => keptDrop(newProjectionKey(pathname));
    return <Projection key={`new:${ask.name}:${ask.at}`} projection={ask.name} system={ask.system} creating
      onCreated={() => { done(); navigate(pathname, { replace: true }); }} onCancel={() => { done(); navigate(-1); }} />;
  }
  if (ask) keptDrop(newProjectionKey(pathname));                   // saved: the model has it now
  if (!at) return old(table, pathname, search, q, hash) ?? <NothingHere pathname={pathname} />;
  if (at.redirect) return go(at.redirect);                         // a deeper address: the top-most
  const system = at.scope;
  const own = <OwnLink pathname={pathname} search={search} />;
  const declared = (name: string, bind: Record<string, string>, resettable = true) =>
    <Declared key={`${name}:${JSON.stringify(bind)}`} name={name} bind={{ system, ...bind }} actions={() => own} resettable={resettable} />;
  const template = (page: string) => list.find((d) => d.page === page);

  switch (at.kind) {
    case "system":
      return go(scopeHref(system, "overview"));
    case "dashboard": {
      const local = localOf(at.name, system);
      if (local === "diagrams" && q.get("system") && q.get("system") !== system) {    // the old ?system=: its own
        const rest = new URLSearchParams(search);
        const s = rest.get("system")!;
        rest.delete("system");
        if (s in table.scopes) return go(diagramHref({ system: s }), rest.size ? `?${rest}` : "");
      }
      const mine: DashboardListed | undefined = list.find((d) => d.name === at.name && d.declared);
      if (at.projection) {                                         // the model's dashboard named as a projection there
        return builtin ? <Projection key={at.projection} projection={at.projection} />
          : declared(at.name, { projection: at.projection });
      }
      if (mine && !(builtin && DEFAULT_PAGES[local])) return declared(at.name, {}, !!DEFAULT_PAGES[local]);
      const page = DEFAULT_PAGES[local];
      return page ? page(system) : <NothingHere pathname={pathname} />;
    }
    case "projection": {
      const name = at.name;
      const mine = !builtin && ownOf(list, name, "list");
      if (mine) return declared(mine.name, { projection: name });
      const t = !builtin && template("projection");
      return t ? declared(t.name, { projection: name }) : <Projection key={name} projection={name} />;
    }
    case "item": {
      const name = at.name, id = at.id!;
      const mine = !builtin && ownOf(list, name, "show");
      if (mine) return declared(mine.name, { item: id, projection: name });
      const t = !builtin && template("item");
      return t ? declared(t.name, { item: id, projection: name }) : <Item key={`${name}:${id}`} id={id} projection={name} />;
    }
    case "goal":
      return <Goal key={at.name} name={at.name} />;
    case "agent": {
      const t = !builtin && template("agent");
      return t ? declared(t.name, { agent: at.name }) : <Agent key={at.name} name={at.name} />;
    }
  }
  return <NothingHere pathname={pathname} />;
}

/** An old address, at its new one where it has one; /item/ID (an id no projection, or several, see) drawn here. */
function old(t: RouteTable, pathname: string, search: string, q: URLSearchParams, hash = ""): ReactNode | null {
  const parts = pathname.split("/").filter(Boolean).map((s) => { try { return decodeURIComponent(s); } catch { return s; } });
  const [head = "", ...rest] = parts;
  const go = (to: string, keep = search) => <Navigate replace to={joined(to, keep) + hash} />;
  const without = (...ks: string[]) => { const n = new URLSearchParams(q); ks.forEach((k) => n.delete(k)); return n.toString(); };
  if (head === "record" && !rest.length) return go(scopeHref("", "events"));
  if (head === "diagram" && !rest.length) {
    const s = q.get("system") || "";
    return go(diagramHref({ system: s }), s in t.scopes ? without("system") : search);
  }
  if (head === "loops") return go(scopeHref("", "goals"));
  if (head === "agent" && rest.length) return go(agentHref(rest.join("/")));
  if (head === "agent") return go(scopeHref("", "agents"));
  if (head === "agents" && rest.length === 1) return <Agent key={rest[0]} name={rest[0]} />;   // one the model has not: said
  if (head === "d" && rest.length) return go(dashboardHref(rest.join("/")));
  if (head === "items") {
    const k = rest[0] || q.get("projection");
    return k ? go(projectionHref(k), without("projection")) : go(scopeHref("", "overview"), "");
  }
  if (head === "item" && rest.length) {
    const id = rest.join("/");
    const remote = q.has("remote");
    const ks = remote ? [] : projectionsOfId(id);
    const there = ks.length === 1 ? itemHref(id, undefined, ks[0].name) : null;   // an item of one projection: there
    if (there && !there.startsWith("/item/")) return go(there);
    return <Item key={id} id={id} projection={ks.length === 1 ? ks[0].name : undefined} />;
  }
  if (head in t.projections) {                     // a projection's old top-level address: the scope that holds it
    const to = rest.length ? itemHref(idOf(head, rest.join("/")), undefined, head) : projectionHref(head);
    if (to !== pathname) return go(to);
  }
  return null;
}

function NothingHere({ pathname }: { pathname: string }) {
  return (
    <Page title="Nothing here">
      <p className="muted">The model names nothing at {pathname}: no dashboard, no projection, no system and no page of
        ergostat's. <AppLink to={scopeHref("", "overview")}>The overview</AppLink></p>
    </Page>
  );
}
