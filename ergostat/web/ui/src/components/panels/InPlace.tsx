import { lazy, type ReactNode } from "react";
import { Link, useLocation, useSearchParams } from "react-router-dom";
import { useInPlaceOf } from "../../state/dashboards";
import { Loading } from "../ui";

// loaded only when a dashboard is declared in a page's place: the app's first load does not bring every kind of panel
const DeclaredDashboard = lazy(() => import("./Declared").then((m) => ({ default: m.DeclaredDashboard })));

/* One of the web page's own pages, or the dashboard the model declares in its place (`page:`, SPEC §4f): drawn with
   `bind`, the address's word its panels' `$WORD` stands for. ?builtin=1 shows ergostat's own page all the same. */
export function InPlace({ page, bind, children }: { page: string; bind?: Record<string, string>; children: ReactNode }) {
  const d = useInPlaceOf(page);
  const [q] = useSearchParams();
  const { pathname } = useLocation();
  if (q.get("builtin") === "1" || d === null) return <>{children}</>;
  if (d === undefined) return <Loading />;
  const own = new URLSearchParams(q);
  own.set("builtin", "1");
  return (
    <DeclaredDashboard name={d.name} bind={bind} actions={() => (
      <Link className="small" to={`${pathname}?${own}`} title={`Dashboard ${d.name} is drawn in this page's place (page: ${page})`}>
        ergostat's own page
      </Link>
    )} />
  );
}
