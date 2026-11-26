import { Link, Navigate, useNavigate, useSearchParams } from "react-router-dom";
import { Filters, FinishedToggle, Page, SearchBox, StatesChoice } from "../../components";
import { DashboardView } from "../../components/panels/DashboardView";
import type { PanelDef } from "../../components/panels/types";
import { kindHref } from "../../lib/hrefs";

/* /items, a dashboard made in advance: the overview of kinds (a `kinds` panel) when the address has only ?states= or
   the window; /items?kind=K goes to the kind's page; a search or any other filter lists every kind's newest (an
   `items-by-kind` panel). The page keeps its title and its filters, in the address (states=all, q=, finished=show). */

const OVERVIEW_KEYS = new Set(["states", "window", "at"]);
const OVERVIEW: PanelDef[] = [{ panel: "kinds", id: "kinds", title: "Kinds of item", size: "full", fit: true }];
const EVERY_KIND: PanelDef[] = [{ panel: "items-by-kind", id: "items-by-kind", title: "Each kind's newest", size: "full", fit: true }];

export default function ItemsPage() {
  const [q] = useSearchParams();
  const kind = q.get("kind");
  if (kind) {
    const rest = new URLSearchParams(q);
    rest.delete("kind");
    const s = rest.toString();
    return <Navigate replace to={kindHref(kind) + (s ? `?${s}` : "")} />;
  }
  const overview = [...q.keys()].every((k) => OVERVIEW_KEYS.has(k));
  return overview ? <Overview /> : <EveryKind />;
}

/** The overview: under each system, a card per kind with its counts, rates and its states over the window. */
function Overview() {
  const [q, setQ] = useSearchParams();
  const navigate = useNavigate();
  const all = q.get("states") === "all";
  const pick = (to: boolean) => setQ((p) => { const n = new URLSearchParams(p); if (to) n.set("states", "all"); else n.delete("states"); return n; }, { replace: true });
  return (
    <Page title="Items">
      <Filters>
        <SearchBox placeholder="Search kinds, ids and fields" onSearch={(w) => w && navigate(`/items?q=${encodeURIComponent(w)}`)} />
        <span className="rg-viewbar"><StatesChoice all={all} onChange={pick} /></span>
        <Link to="/items?view=list" className="small">every kind's list</Link>
      </Filters>
      <DashboardView panels={OVERVIEW.map((d) => ({ ...d, states: all ? "all" : undefined }))} every={15000} />
    </Page>
  );
}

/** Every kind's items (/items?view=list, or a search): under each system, each kind's newest, matched to the search. */
function EveryKind() {
  const [q, setQ] = useSearchParams();
  const needle = (q.get("q") || "").trim();
  const showFin = q.get("finished") === "show";
  const set = (k: string, v: string | null) =>
    setQ((p) => { const n = new URLSearchParams(p); if (v) n.set(k, v); else n.delete(k); if (!n.toString()) n.set("view", "list"); return n; }, { replace: true });
  return (
    <Page title="Items">
      <Filters>
        <SearchBox value={needle} live placeholder="Search kinds, ids and fields" onSearch={(w) => set("q", w || null)} />
        <FinishedToggle shown={showFin} onChange={(v) => set("finished", v ? "show" : null)} />
        <Link to="/items" className="small">the overview</Link>
      </Filters>
      <DashboardView panels={EVERY_KIND.map((d) => ({ ...d, q: needle || undefined, finished: showFin ? "show" : undefined }))} every={10000} />
    </Page>
  );
}
