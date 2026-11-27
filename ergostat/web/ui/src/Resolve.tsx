import { lazy, type ReactNode } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { AppLink, Loading, Page } from "./components";
import { idOf, isProjection, itemPath } from "./lib/routes";
import { ownOf, useDashboards } from "./state/dashboards";

/* Every address but the server's, resolved as lib/routes.ts says: a projection's own dashboards, the model's
   dashboards, then its projections and their items, then ergostat's own pages. Old addresses (/items/NAME, /item/ID of a
   projection, /d/NAME, /loops) lead to the new ones while the model names nothing there. A new dashboard
   (the nav bar's +) is drawn wherever it was asked for, until it is saved under its name. */

const Diagram = lazy(() => import("./pages/diagram"));
const Goals = lazy(() => import("./pages/goals"));
const Agents = lazy(() => import("./pages/agents"));
const Agent = lazy(() => import("./pages/agents/AgentPage"));
const Projection = lazy(() => import("./pages/items/ProjectionPage"));
const Item = lazy(() => import("./pages/items/ItemPage"));
const Record = lazy(() => import("./pages/record"));
// a dashboard the model declares: loaded when one is shown, so the first load does not bring every panel
const Declared = lazy(() => import("./components/panels/Declared").then((m) => ({ default: m.DeclaredDashboard })));
const NewDashboard = lazy(() => import("./components/panels/NewDashboard"));

/** ergostat's own page for an address, a link to it from a dashboard drawn in its place. */
function OwnLink({ pathname, search }: { pathname: string; search: string }) {
  const q = new URLSearchParams(search);
  q.set("builtin", "1");
  return <AppLink className="small" to={`${pathname}?${q}`} title="What ergostat draws here when the model names nothing">ergostat's own page</AppLink>;
}

export default function Resolve() {
  const { pathname, search, state } = useLocation();
  const navigate = useNavigate();
  const { list, projections, failed } = useDashboards();
  const parts = pathname.split("/").filter(Boolean).map((s) => { try { return decodeURIComponent(s); } catch { return s; } });
  const [head = "", ...rest] = parts;
  const builtin = new URLSearchParams(search).get("builtin") === "1";
  const go = (to: string) => <Navigate replace to={to + search} />;

  if ((state as any)?.newDashboard) return <NewDashboard key={(state as any).newDashboard} onSaved={(name) => navigate(`/${encodeURIComponent(name)}`)} onCancel={() => navigate(-1)} />;
  if (!head) return go("/diagram");
  if (!list && !failed) return <Loading />;
  const dashboards = (list || []).filter((d) => d.name !== "default");
  const template = (page: string) => dashboards.find((d) => d.page === page);
  const named = dashboards.find((d) => d.name === head && !d.page && !d.projection);
  const projection = isProjection(head);
  const own = <OwnLink pathname={pathname} search={search} />;
  const declared = (name: string, bind?: Record<string, string>, resettable = true) =>
    <Declared key={`${name}:${JSON.stringify(bind || {})}`} name={name} bind={bind} actions={() => own} resettable={resettable} />;

  // 1. a projection's own list and show (its `dashboards:`)
  if (!builtin && projection) {
    const mine = ownOf(dashboards, head, rest.length ? "show" : "list");
    if (mine) return declared(mine.name, rest.length ? { item: idOf(head, rest.join("/")), projection: head } : { projection: head });
  }
  // 2. the model's dashboard at its name (one named as ergostat's page, or a projection, drawn in its place)
  if (!builtin && named && !rest.length) {
    return declared(named.name, projection ? { projection: head } : undefined, projection || (OWN_PAGES as readonly string[]).includes(head));
  }
  // 3. the model's projection and its items
  if (projection && !(builtin && (BUILT as readonly string[]).includes(head))) {
    if (!rest.length) {
      const t = !builtin && template("projection");
      return t ? declared(t.name, { projection: head }) : <Projection key={head} projection={head} />;
    }
    const id = idOf(head, rest.join("/"));
    const t = !builtin && template("item");
    return t ? declared(t.name, { item: id }) : <Item key={id} id={id} projection={head} />;
  }
  // the old addresses, while the model names nothing there
  if (head === "items" && projections) {
    const k = rest[0] || new URLSearchParams(search).get("projection");
    return k ? <Navigate replace to={`/${encodeURIComponent(k)}${search}`} /> : go("/diagram");
  }
  if (head === "d" && rest.length) return go(`/${encodeURIComponent(rest.join("/"))}`);
  if (head === "loops") return go("/goals");
  // 4. ergostat's own pages
  const page = BUILTIN_PAGES[head];
  if (page) return page(rest, { template: builtin ? undefined : template, declared, projections: !!projections, search });
  return (
    <Page title="Nothing here">
      <p className="muted">The model names nothing at {pathname}: no dashboard, no projection, and no page of ergostat's.{" "}
        <AppLink to="/diagram">The diagram</AppLink></p>
    </Page>
  );
}

const BUILT = ["diagram", "goals", "agents", "agent", "record", "item"] as const;
/** ergostat's own pages a dashboard of the same name is drawn in place of (Reset to ergostat's takes it out again). */
const OWN_PAGES = ["goals", "agents", "record"] as const;

type Ctx = {
  template?: (page: string) => { name: string } | undefined;
  declared: (name: string, bind?: Record<string, string>) => ReactNode;
  projections: boolean;
  search: string;
};
const BUILTIN_PAGES: Record<string, (rest: string[], c: Ctx) => ReactNode> = {
  diagram: () => <Diagram />,
  goals: () => <Goals />,
  agents: () => <Agents />,
  record: () => <Record />,
  agent: (rest, c) => {
    if (!rest.length) return <Navigate replace to="/agents" />;
    const t = c.template?.("agent");
    return t ? c.declared(t.name, { agent: rest.join("/") }) : <Agent key={rest.join("/")} name={rest.join("/")} />;
  },
  item: (rest, c) => {
    const id = rest.join("/");
    const remote = new URLSearchParams(c.search).has("remote");
    const there = !remote && c.projections ? itemPath(id) : null;          // an item of a projection: at the projection's address
    if (there) return <Navigate replace to={there + c.search} />;
    const t = !remote && c.template?.("item");
    return t ? c.declared(t.name, { item: id }) : <Item key={id} id={id} />;
  },
};
